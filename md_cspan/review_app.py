from __future__ import annotations

import csv
import re
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from flask import Flask, render_template_string, request


HOST = "127.0.0.1"
PORT = 5055

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = Path("output/cspan_member_programs_all.csv")
CURATED_SOURCE_OPTIONS = [
    ("Master Catalog", Path("output/cspan_member_programs_all.csv")),
    ("Priority Leads", Path("output/cspan_priority_leads_new_programs_md_depth3_merged.csv")),
    ("Top Unique Programs", Path("output/cspan_priority_leads_md_top_unique_programs_wordbound_renamed.csv")),
    ("Archive Catalog", Path("output/cspan_archive_catalog.csv")),
]

URL_COLUMNS = ["cspan_url", "program_url", "url", "video_url"]
MEMBER_COLUMNS = ["member", "member_name", "matched_member", "speaker", "matched_name"]
TITLE_COLUMNS = ["event_title", "program_title", "title"]
DATE_COLUMNS = ["event_date", "program_date", "date"]
DESCRIPTION_COLUMNS = ["description", "summary"]
KEYWORD_COLUMNS = ["matched_keywords", "matched_terms", "matched_topics"]
PRIORITY_COLUMNS = ["matrix_priority", "priority"]
TOPIC_COLUMNS = [*PRIORITY_COLUMNS, *KEYWORD_COLUMNS]
MEMBER_PRIORITIES_CSV = Path("data/member_priorities.csv")
TOPIC_ALIASES_CSV = Path("data/topic_aliases.csv")

FILTER_SPECS = [
    ("keyword", "Keyword / topic", TOPIC_COLUMNS),
    ("source_type", "Source type", ["source_type"]),
    ("event_type", "Event type", ["event_type"]),
]

GROUP_OPTIONS = [
    ("none", "None"),
    ("member", "Member"),
    ("keyword", "Keyword / Topic"),
    ("source_type", "Source type"),
    ("event_type", "Event type"),
]

SORT_OPTIONS = [
    ("best", "Best match", "", "asc", "compound_default"),
    ("newest", "Newest first", "", "desc", "row_date"),
    ("oldest", "Oldest first", "", "asc", "row_date"),
    ("member_az", "Member A-Z", "", "asc", "row_member"),
    ("score_desc", "Score high to low", "", "desc", "row_score"),
    ("score_asc", "Score low to high", "", "asc", "row_score"),
]


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        csv_path_value = request.args.get("csv_path") or default_csv_path()
        query = request.args.get("q", "").strip()
        member_filter = request.args.get("member", "").strip()
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        min_priority_score = request.args.get("min_priority_score", "").strip()
        sort_value = request.args.get("sort", "").strip()
        requested_group_by = request.args.get("group_by", "").strip()
        selected_filters = {
            filter_id: request.args.get(filter_id, "").strip()
            for filter_id, _label, _columns in FILTER_SPECS
        }
        selected_topic = selected_filters.get("keyword", "")
        active_terms_param = request.args.get("active_terms")
        active_terms = resolve_active_terms(selected_topic, active_terms_param)
        active_terms_are_narrowed = active_terms_param is not None

        rows: list[dict[str, str]] = []
        fieldnames: list[str] = []
        visible_rows: list[dict[str, Any]] = []
        grouped_rows: list[dict[str, Any]] = []
        error = ""

        try:
            rows, fieldnames = load_csv(csv_path_value)
            sort_options = available_sort_options(fieldnames)
            sort_value = resolve_sort_value(sort_value, member_filter, sort_options)
            group_options = available_group_options(member_filter)
            group_by = resolve_group_by(requested_group_by, member_filter, group_options)
            alias_note = alias_note_for_filter(
                rows,
                member_filter,
                selected_topic,
                active_terms if active_terms_are_narrowed else None,
            )
            visible_rows = filter_rows(
                rows=rows,
                query=query,
                member_filter=member_filter,
                selected_filters=selected_filters,
                active_terms=active_terms,
                active_terms_are_narrowed=active_terms_are_narrowed,
                date_from=date_from,
                date_to=date_to,
                min_priority_score=min_priority_score,
            )
            visible_rows = sort_rows(visible_rows, sort_value)
            grouped_rows = group_rows(visible_rows, group_by)
        except Exception as exc:
            error = str(exc)
            sort_options = []
            group_options = available_group_options(member_filter)
            group_by = resolve_group_by(requested_group_by, member_filter, group_options)
            alias_note = ""

        return render_template_string(
            TEMPLATE,
            csv_path=csv_path_value,
            current_source_label=source_label(csv_path_value),
            source_options=source_options(),
            rows=visible_rows,
            grouped_rows=grouped_rows,
            total_rows=len(rows),
            visible_count=len(visible_rows),
            fieldnames=fieldnames,
            member_values=unique_values(rows, MEMBER_COLUMNS),
            filter_specs=available_filter_specs(fieldnames),
            filter_options=filter_options(rows, fieldnames, member_filter),
            selected_filters=selected_filters,
            selected_topic=selected_topic,
            related_terms=related_topic_terms(selected_topic),
            active_terms=active_terms,
            active_terms_are_narrowed=active_terms_are_narrowed,
            active_terms_value=active_terms_value(selected_topic, active_terms, active_terms_param),
            query=query,
            member_filter=member_filter,
            date_from=date_from,
            date_to=date_to,
            min_priority_score=min_priority_score,
            sort_value=sort_value,
            sort_options=sort_options,
            group_by=group_by,
            group_options=group_options,
            view_mode_label=view_mode_label(member_filter),
            view_mode_detail=view_mode_detail(group_by),
            has_priority_score=has_any_column(fieldnames, ["priority_score"]),
            error=error,
            alias_note=alias_note,
            card_value=card_value,
            topic_aliases=topic_aliases,
            active_term_toggle_url=active_term_toggle_url,
            context_helper_text=context_helper_text,
            cell_text=cell_text,
            all_fields=all_fields,
        )

    return app


def default_csv_path() -> str:
    default_path = REPO_ROOT / DEFAULT_CSV
    if default_path.exists():
        return str(DEFAULT_CSV)

    options = source_options()
    return options[0]["path"] if options else str(DEFAULT_CSV)


def resolve_repo_path(path_value: str) -> Path:
    if not path_value:
        raise ValueError("CSV path cannot be blank.")

    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def load_csv(path_value: str) -> tuple[list[dict[str, str]], list[str]]:
    csv_path = resolve_repo_path(path_value)
    if not csv_path.exists():
        raise ValueError(f"CSV file does not exist: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]

    return rows, fieldnames


def source_options() -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for label, path in CURATED_SOURCE_OPTIONS:
        full_path = REPO_ROOT / path
        if full_path.exists():
            options.append({"label": label, "path": str(path)})
    return options


def source_label(path_value: str) -> str:
    normalized = str(Path(path_value))
    for label, path in CURATED_SOURCE_OPTIONS:
        if normalized == str(path):
            return label
    return "Custom CSV"


def has_any_column(fieldnames: list[str], columns: list[str]) -> bool:
    return any(column in fieldnames for column in columns)


def available_filter_specs(fieldnames: list[str]) -> list[tuple[str, str, list[str]]]:
    return [
        spec for spec in FILTER_SPECS
        if has_any_column(fieldnames, spec[2])
    ]


def available_sort_options(fieldnames: list[str]) -> list[tuple[str, str, str, str, str]]:
    options: list[tuple[str, str, str, str, str]] = []
    for option in SORT_OPTIONS:
        _value, _label, field, _direction, kind = option
        if kind == "compound_default":
            options.append(option)
        elif kind == "row_date" and has_any_column(fieldnames, DATE_COLUMNS):
            options.append(option)
        elif kind == "row_member" and has_any_column(fieldnames, MEMBER_COLUMNS):
            options.append(option)
        elif kind == "row_score" and has_any_column(fieldnames, ["priority_score", "lead_score"]):
            options.append(option)
        elif field in fieldnames:
            options.append(option)
    if not options:
        options.append(("source", "Source order", "", "asc", "text"))
    return options


def available_group_options(member_filter: str) -> list[tuple[str, str]]:
    if member_filter:
        return [option for option in GROUP_OPTIONS if option[0] != "member"]
    return GROUP_OPTIONS


def resolve_group_by(
    requested_group_by: str,
    member_filter: str,
    group_options: list[tuple[str, str]],
) -> str:
    allowed_values = {value for value, _label in group_options}
    default_group_by = "none"
    if requested_group_by in allowed_values:
        return requested_group_by
    return default_group_by


def resolve_sort_value(
    requested_sort_value: str,
    member_filter: str,
    sort_options: list[tuple[str, str, str, str, str]],
) -> str:
    allowed_values = {value for value, _label, _field, _direction, _kind in sort_options}
    if requested_sort_value in allowed_values:
        return requested_sort_value

    preferred_value = "best" if member_filter else "newest"
    if preferred_value in allowed_values:
        return preferred_value
    return sort_options[0][0] if sort_options else ""


def view_mode_label(member_filter: str) -> str:
    return "Member View" if member_filter else "All Members Feed"


def view_mode_detail(group_by: str) -> str:
    if group_by == "none":
        return "Sorted globally"
    label = next((label for value, label in GROUP_OPTIONS if value == group_by), group_by)
    return f"Grouped by {label}"


def first_present(row: dict[str, str], columns: list[str]) -> str:
    for column in columns:
        value = row.get(column, "").strip()
        if value:
            return value
    return ""


def split_terms(value: str) -> list[str]:
    terms: list[str] = []
    for raw_part in value.replace(";", ",").split(","):
        part = raw_part.strip()
        if part:
            terms.append(part)
    return terms


def values_for_columns(row: dict[str, str], columns: list[str]) -> list[str]:
    values: list[str] = []
    for column in columns:
        value = row.get(column, "").strip()
        if not value:
            continue
        if column in KEYWORD_COLUMNS:
            values.extend(split_terms(value))
        else:
            values.append(value)
    return values


def unique_values(rows: list[dict[str, str]], columns: list[str]) -> list[str]:
    values: set[str] = set()
    for row in rows:
        values.update(values_for_columns(row, columns))
    return sorted(values, key=str.lower)


def filter_options(rows: list[dict[str, str]], fieldnames: list[str], member_filter: str) -> dict[str, list[str]]:
    options: dict[str, list[str]] = {}
    for filter_id, _label, columns in available_filter_specs(fieldnames):
        if filter_id == "keyword":
            options[filter_id] = topic_values_for_member(rows, member_filter)
        else:
            option_rows = rows
            if member_filter:
                option_rows = [row for row in rows if row_member(row) == member_filter]
            options[filter_id] = unique_values(option_rows, columns)
    return options


def matrix_priority_rows() -> list[dict[str, str]]:
    path = REPO_ROOT / MEMBER_PRIORITIES_CSV
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def matrix_topics_for_member(member_filter: str) -> list[str]:
    if not member_filter:
        return unique_values(matrix_priority_rows(), ["priority"])

    topics = {
        row.get("priority", "").strip()
        for row in matrix_priority_rows()
        if row.get("display_name", "").strip() == member_filter
        and row.get("priority", "").strip()
    }
    return sorted(topics, key=str.lower)


def topic_aliases(topic: str) -> list[str]:
    clean_topic = topic.strip()
    aliases_by_topic = load_topic_alias_rows()
    terms = aliases_by_topic.get(normalize_topic_key(clean_topic), [clean_topic])
    deduped_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in terms:
        key = term.lower()
        if term and key not in seen_terms:
            seen_terms.add(key)
            deduped_terms.append(term)
    return deduped_terms


def related_topic_terms(topic: str) -> list[str]:
    topic_key = normalize_topic_key(topic)
    return [
        term for term in topic_aliases(topic)
        if normalize_topic_key(term) != topic_key
    ]


def resolve_active_terms(topic: str, active_terms_param: str | None) -> list[str]:
    related_terms = related_topic_terms(topic)
    if not topic or active_terms_param is None:
        return related_terms

    requested_keys = {
        normalize_topic_key(term)
        for term in active_terms_param.split(",")
        if term.strip()
    }
    return [
        term for term in related_terms
        if normalize_topic_key(term) in requested_keys
    ]


def active_terms_value(
    topic: str,
    active_terms: list[str],
    active_terms_param: str | None,
) -> str:
    if not topic or active_terms_param is None:
        return ""

    return ",".join(active_terms)


def active_term_toggle_url(term: str, selected_topic: str, active_terms: list[str]) -> str:
    related_terms = related_topic_terms(selected_topic)
    related_keys = [normalize_topic_key(related_term) for related_term in related_terms]
    active_keys = {normalize_topic_key(active_term) for active_term in active_terms}
    term_key = normalize_topic_key(term)

    if term_key in active_keys:
        active_keys.remove(term_key)
    else:
        active_keys.add(term_key)

    next_active_terms = [
        related_term for related_term, related_key in zip(related_terms, related_keys)
        if related_key in active_keys
    ]

    args = request.args.to_dict(flat=True)
    if len(next_active_terms) == len(related_terms):
        args.pop("active_terms", None)
    else:
        args["active_terms"] = ",".join(next_active_terms)

    query = urlencode(args)
    return f"/?{query}" if query else "/"


def context_helper_text(
    selected_topic: str,
    active_terms: list[str],
    active_terms_are_narrowed: bool,
) -> str:
    if not selected_topic:
        return ""
    if active_terms_are_narrowed:
        term_list = ", ".join(active_terms) if active_terms else "none"
        return f"Filtering {selected_topic} to active related terms: {term_list}"
    return f"Showing {selected_topic} using all related terms by default."


def split_alias_terms(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;\n]+", value or "") if part.strip()]


def normalize_topic_key(value: str) -> str:
    key = re.sub(r"\s+", " ", (value or "").strip().lower())
    return re.sub(r"\s*/\s*", "/", key)


def load_topic_alias_rows() -> dict[str, list[str]]:
    path = REPO_ROOT / TOPIC_ALIASES_CSV
    if not path.exists():
        return {}

    aliases_by_topic: dict[str, list[str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            topic = (row.get("topic") or "").strip()
            if not topic:
                continue

            terms = [topic, *split_alias_terms(row.get("aliases", ""))]
            deduped_terms: list[str] = []
            seen_terms: set[str] = set()
            for term in terms:
                key = term.lower()
                if term and key not in seen_terms:
                    seen_terms.add(key)
                    deduped_terms.append(term)
            aliases_by_topic[normalize_topic_key(topic)] = deduped_terms
    return aliases_by_topic


def topic_values_for_member(rows: list[dict[str, str]], member_filter: str) -> list[str]:
    scoped_rows = rows
    if member_filter:
        scoped_rows = [row for row in rows if row_member(row) == member_filter]

    matrix_topics = matrix_topics_for_member(member_filter)
    if member_filter and matrix_topics:
        return matrix_topics

    topics = set(matrix_topics)
    topics.update(unique_values(scoped_rows, TOPIC_COLUMNS))
    return sorted(topics, key=str.lower)


def row_url(row: dict[str, str]) -> str:
    return first_present(row, URL_COLUMNS)


def row_member(row: dict[str, str]) -> str:
    return first_present(row, MEMBER_COLUMNS)


def row_title(row: dict[str, str]) -> str:
    return first_present(row, TITLE_COLUMNS)


def row_date(row: dict[str, str]) -> str:
    return first_present(row, DATE_COLUMNS)


def row_priority_score(row: dict[str, str]) -> str:
    return first_present(row, ["priority_score", "lead_score"])


def card_value(row: dict[str, str], kind: str) -> str:
    card_columns = {
        "member": MEMBER_COLUMNS,
        "title": TITLE_COLUMNS,
        "date": DATE_COLUMNS,
        "score": ["priority_score", "lead_score"],
        "matrix_priority": PRIORITY_COLUMNS,
        "keywords": KEYWORD_COLUMNS,
        "match_strength": ["match_strength"],
        "strong_match_count": ["strong_match_count"],
        "broad_match_count": ["broad_match_count"],
        "source_type": ["source_type"],
        "event_type": ["event_type"],
        "content_bucket": ["content_bucket"],
        "youtube_use": ["youtube_use"],
        "description": DESCRIPTION_COLUMNS,
        "url": URL_COLUMNS,
    }
    return first_present(row, card_columns.get(kind, []))


def all_fields(row: dict[str, str]) -> list[tuple[str, str]]:
    return [
        (key, value)
        for key, value in row.items()
        if not key.startswith("_")
    ]


def cell_text(value: str, max_length: int = 700) -> str:
    if len(value) <= max_length:
        return value
    return f"{value[:max_length].rstrip()}..."


def parse_date_value(value: str) -> str:
    return (value or "")[:10]


def parse_number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def row_matches_dropdown(row: dict[str, str], columns: list[str], selected_value: str) -> bool:
    if not selected_value:
        return True
    return selected_value in values_for_columns(row, columns)


def normalized_match_text(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[/_-]+", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stem_match_token(token: str) -> str:
    token = token.strip().lower()
    for suffix in ["ing", "ed", "es", "s"]:
        if len(token) > len(suffix) + 3 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def term_match_patterns(term: str) -> list[str]:
    normalized_term = normalized_match_text(term)
    if not normalized_term:
        return []

    patterns = [normalized_term]
    tokens = normalized_term.split()
    if len(tokens) == 1:
        stem = stem_match_token(tokens[0])
        if stem and stem != tokens[0]:
            patterns.append(stem)
    return patterns


def term_matches_text(term: str, text: str) -> bool:
    normalized_text = normalized_match_text(text)
    if not normalized_text:
        return False

    for pattern in term_match_patterns(term):
        escaped_pattern = re.escape(pattern)
        if " " in pattern:
            if re.search(rf"(?<!\w){escaped_pattern}(?!\w)", normalized_text):
                return True
        elif re.search(rf"(?<!\w){escaped_pattern}\w*", normalized_text):
            return True
    return False


def row_topic_searchable_text(row: dict[str, str]) -> str:
    return " ".join(
        str(row.get(column, ""))
        for column in [
            *TITLE_COLUMNS,
            *DESCRIPTION_COLUMNS,
            *KEYWORD_COLUMNS,
            *PRIORITY_COLUMNS,
            "content_bucket",
            "source_type",
            "event_type",
        ]
    )


def row_active_term_matches(row: dict[str, str], active_terms: list[str]) -> list[str]:
    searchable_text = row_topic_searchable_text(row)
    return [
        term for term in active_terms
        if term_matches_text(term, searchable_text)
    ]


def row_matches_topic(
    row: dict[str, str],
    selected_value: str,
    active_terms: list[str] | None = None,
    active_terms_are_narrowed: bool = False,
) -> bool:
    if not selected_value:
        return True

    if active_terms_are_narrowed:
        return bool(row_active_term_matches(row, active_terms or []))

    if selected_value in values_for_columns(row, TOPIC_COLUMNS):
        return True

    searchable_text = row_topic_searchable_text(row)
    return any(term_matches_text(term, searchable_text) for term in topic_aliases(selected_value))


def alias_note_for_filter(
    rows: list[dict[str, str]],
    member_filter: str,
    selected_topic: str,
    active_terms: list[str] | None = None,
) -> str:
    if not member_filter or not selected_topic:
        return ""

    aliases = active_terms if active_terms is not None else related_topic_terms(selected_topic)
    if not aliases:
        return ""

    member_rows = [row for row in rows if row_member(row) == member_filter]
    exact_matches = [row for row in member_rows if selected_topic in values_for_columns(row, TOPIC_COLUMNS)]
    alias_matches = [
        row for row in member_rows
        if row_matches_topic(row, selected_topic, active_terms, active_terms_are_narrowed=active_terms is not None)
        and row not in exact_matches
    ]
    if not alias_matches:
        return ""

    preview = ", ".join(aliases[:5])
    if len(aliases) > 5:
        preview = f"{preview}..."
    return f"Showing matches for {selected_topic} using related terms: {preview}"


def filter_rows(
    rows: list[dict[str, str]],
    query: str,
    member_filter: str,
    selected_filters: dict[str, str],
    active_terms: list[str] | None,
    active_terms_are_narrowed: bool,
    date_from: str,
    date_to: str,
    min_priority_score: str,
) -> list[dict[str, Any]]:
    query_lower = query.lower()
    min_score = parse_number(min_priority_score) if min_priority_score else None
    visible_rows: list[dict[str, Any]] = []

    for index, row in enumerate(rows):
        if query_lower:
            searchable_text = " ".join(
                str(row.get(column, ""))
                for column in [
                    *MEMBER_COLUMNS,
                    *TITLE_COLUMNS,
                    *DESCRIPTION_COLUMNS,
                    *KEYWORD_COLUMNS,
                    *PRIORITY_COLUMNS,
                    "content_bucket",
                    "youtube_use",
                    "source_type",
                    "event_type",
                    "match_strength",
                ]
            ).lower()
            if query_lower not in searchable_text:
                continue

        if member_filter and row_member(row) != member_filter:
            continue

        failed_dropdown = False
        for filter_id, _label, columns in FILTER_SPECS:
            selected_value = selected_filters.get(filter_id, "")
            if filter_id == "keyword":
                matches_dropdown = row_matches_topic(
                    row,
                    selected_value,
                    active_terms,
                    active_terms_are_narrowed,
                )
            else:
                matches_dropdown = row_matches_dropdown(row, columns, selected_value)
            if not matches_dropdown:
                failed_dropdown = True
                break
        if failed_dropdown:
            continue

        date_value = parse_date_value(row_date(row))
        if date_from and date_value and date_value < date_from:
            continue
        if date_to and date_value and date_value > date_to:
            continue

        if min_score is not None and parse_number(row_priority_score(row)) < min_score:
            continue

        display_row = dict(row)
        display_row["_row_index"] = index
        display_row["_url"] = row_url(row)
        if active_terms_are_narrowed and selected_filters.get("keyword", ""):
            display_row["_active_matches"] = "; ".join(row_active_term_matches(row, active_terms or []))
        visible_rows.append(display_row)

    return visible_rows


def sort_key_value(row: dict[str, Any], field: str, kind: str) -> Any:
    if kind == "compound_default":
        return (
            row_member(row).lower(),
            -parse_number(row_priority_score(row)),
            reverse_date_key(row_date(row)),
        )
    if kind == "row_date":
        return parse_date_value(row_date(row))
    if kind == "row_member":
        return row_member(row).lower()
    if kind == "row_score":
        return parse_number(row_priority_score(row))
    if not field:
        return row.get("_row_index", 0)
    value = row.get(field, "")
    if kind == "number":
        return parse_number(value)
    if kind == "date":
        return parse_date_value(value)
    return str(value).lower()


def reverse_date_key(value: str) -> str:
    date_value = parse_date_value(value)
    if not date_value:
        return "9999-99-99"
    return "".join(str(9 - int(char)) if char.isdigit() else char for char in date_value)


def sort_rows(rows: list[dict[str, Any]], sort_value: str) -> list[dict[str, Any]]:
    option = next((option for option in SORT_OPTIONS if option[0] == sort_value), None)
    if option is None:
        return rows

    _value, _label, field, direction, kind = option
    return sorted(
        rows,
        key=lambda row: sort_key_value(row, field, kind),
        reverse=direction == "desc",
    )


def group_label_for_row(row: dict[str, Any], group_by: str) -> str:
    if group_by == "member":
        return row_member(row) or "Unknown member"
    if group_by == "keyword":
        return first_present(row, TOPIC_COLUMNS) or "No keyword / topic"
    if group_by == "source_type":
        return row.get("source_type", "") or "No source type"
    if group_by == "event_type":
        return row.get("event_type", "") or "No event type"
    return ""


def group_rows(rows: list[dict[str, Any]], group_by: str) -> list[dict[str, Any]]:
    if group_by == "none":
        return [{"label": "", "count": len(rows), "rows": rows}]

    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        label = group_label_for_row(row, group_by)
        grouped.setdefault(label, []).append(row)

    return [
        {"label": label, "count": len(grouped[label]), "rows": grouped[label]}
        for label in sorted(grouped, key=str.lower)
    ]


TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>C-SPAN Matrix Browser</title>
  <style>
    @font-face {
      font-family: "Pathway Extreme";
      src: url("/static/fonts/PathwayExtreme-VariableFont_opsz,wdth,wght.ttf") format("truetype");
      font-weight: 100 900;
      font-style: normal;
      font-display: swap;
    }
    @font-face {
      font-family: "Pathway Extreme";
      src: url("/static/fonts/PathwayExtreme-Italic-VariableFont_opsz,wdth,wght.ttf") format("truetype");
      font-weight: 100 900;
      font-style: italic;
      font-display: swap;
    }
    :root {
      --brand: #0D4D6E;
      --brand-dark: #08354c;
      --brand-soft: #e7f1f6;
      --accent: #62b6cb;
      --bg: #eef3f7;
      --panel: #ffffff;
      --panel-soft: #f7fafc;
      --ink: #102033;
      --muted: #64748b;
      --line: #d7e1ea;
      --line-strong: #b8c9d6;
      --green: #087f5b;
      --shadow: 0 18px 45px rgba(15, 23, 42, 0.10);
      --soft-shadow: 0 8px 24px rgba(15, 23, 42, 0.07);
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      font-family: "Pathway Extreme", Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
      background:
        radial-gradient(circle at top left, rgba(98, 182, 203, 0.23), transparent 34rem),
        linear-gradient(180deg, #f7fafc 0%, var(--bg) 100%);
      color: var(--ink);
    }
    a {
      color: inherit;
    }
    label {
      display: block;
      margin-bottom: 7px;
      color: #38546a;
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 0.075em;
      text-transform: uppercase;
    }
    input, select, button {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 11px 12px;
      font: inherit;
      background: #ffffff;
      color: var(--ink);
    }
    input, select {
      min-height: 43px;
      box-shadow: 0 1px 0 rgba(15, 23, 42, 0.03);
    }
    input:focus, select:focus {
      border-color: var(--brand);
      box-shadow: 0 0 0 4px rgba(13, 77, 110, 0.15);
      outline: none;
    }
    button, .button {
      cursor: pointer;
      border: 0;
      background: var(--brand);
      color: #ffffff;
      font-weight: 800;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      border-radius: 12px;
      padding: 12px 14px;
      box-shadow: 0 10px 20px rgba(13, 77, 110, 0.20);
    }
    button:hover, .button:hover {
      background: var(--brand-dark);
    }
    .topbar {
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(255, 255, 255, 0.92);
      border-bottom: 1px solid rgba(184, 201, 214, 0.8);
      backdrop-filter: blur(16px);
    }
    .topbar-inner {
      max-width: 1480px;
      margin: 0 auto;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 18px;
    }
    .brand-lockup {
      display: flex;
      align-items: center;
      gap: 13px;
      min-width: 0;
    }
    .brand-mark {
      width: 42px;
      height: 42px;
      border-radius: 14px;
      display: grid;
      place-items: center;
      background: linear-gradient(135deg, var(--brand), #12698f);
      color: white;
      font-weight: 900;
      letter-spacing: -0.06em;
      box-shadow: 0 12px 28px rgba(13, 77, 110, 0.28);
    }
    h1 {
      margin: 0;
      color: var(--brand-dark);
      font-size: 22px;
      line-height: 1.1;
      letter-spacing: -0.035em;
    }
    .subtitle {
      margin-top: 2px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }
    .top-stats {
      display: flex;
      align-items: center;
      justify-content: flex-end;
      gap: 10px;
      flex-wrap: wrap;
    }
    .stat-pill {
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 11px;
      background: #ffffff;
      color: #426176;
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }
    .stat-pill strong {
      color: var(--brand);
    }
    .app-shell {
      max-width: 1480px;
      margin: 0 auto;
      padding: 22px 24px 34px;
    }
    .browser-form {
      display: grid;
      grid-template-columns: 320px minmax(0, 1fr);
      gap: 22px;
      align-items: start;
    }
    .sidebar {
      position: sticky;
      top: 86px;
      display: grid;
      gap: 14px;
      max-height: calc(100vh - 108px);
      overflow: auto;
      padding-right: 2px;
    }
    .sidebar-card, .content-card, .result-row, .empty, .error, .notice {
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--soft-shadow);
    }
    .sidebar-card {
      padding: 18px;
    }
    .sidebar-title {
      margin: 0 0 3px;
      color: var(--brand-dark);
      font-size: 16px;
      font-weight: 900;
      letter-spacing: -0.025em;
    }
    .sidebar-note {
      margin: 0 0 17px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .filter-stack {
      display: grid;
      gap: 14px;
    }
    .date-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .source-path {
      margin-top: 8px;
      color: #8495a5;
      font-size: 11px;
      line-height: 1.35;
      overflow-wrap: anywhere;
    }
    .main-pane {
      min-width: 0;
      display: grid;
      gap: 16px;
    }
    .hero-card {
      padding: 15px 18px;
      background:
        linear-gradient(135deg, rgba(13, 77, 110, 0.96), rgba(18, 105, 143, 0.92)),
        var(--brand);
      border-radius: 22px;
      color: #ffffff;
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
    }
    .hero-card::after {
      content: "";
      position: absolute;
      right: -68px;
      top: -105px;
      width: 220px;
      height: 220px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.10);
    }
    .hero-content {
      position: relative;
      z-index: 1;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 210px;
      gap: 14px;
      align-items: center;
    }
    .mode-eyebrow {
      display: inline-flex;
      width: fit-content;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 5px 9px;
      background: rgba(255, 255, 255, 0.14);
      border: 1px solid rgba(255, 255, 255, 0.23);
      font-size: 11px;
      font-weight: 900;
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }
    .hero-card h2 {
      margin: 8px 0 4px;
      font-size: clamp(22px, 2.8vw, 31px);
      line-height: 1.02;
      letter-spacing: -0.045em;
    }
    .hero-card p {
      margin: 0;
      max-width: 780px;
      color: rgba(255, 255, 255, 0.82);
      font-size: 12px;
      line-height: 1.42;
    }
    .sort-control label {
      color: rgba(255, 255, 255, 0.78);
    }
    .sort-control select {
      border-color: rgba(255, 255, 255, 0.28);
    }
    .search-card {
      padding: 18px;
    }
    .search-row {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 160px;
      gap: 12px;
      align-items: end;
    }
    .search-card input {
      min-height: 48px;
      font-size: 15px;
    }
    .helper-text {
      margin: 9px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .context-card {
      padding: 18px;
    }
    .context-head {
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: start;
      margin-bottom: 13px;
    }
    .context-title {
      margin: 0;
      color: var(--brand-dark);
      font-size: 18px;
      font-weight: 900;
      letter-spacing: -0.03em;
    }
    .context-subtitle {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }
    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      max-width: 100%;
      border-radius: 999px;
      padding: 6px 10px;
      background: var(--brand-soft);
      border: 1px solid #c8ddea;
      color: var(--brand-dark);
      font-size: 12px;
      font-weight: 800;
      line-height: 1.25;
    }
    .chip.soft {
      background: #f8fafc;
      color: #52677a;
    }
    .chip.topic {
      background: var(--brand);
      border-color: var(--brand);
      color: #ffffff;
      box-shadow: 0 8px 18px rgba(13, 77, 110, 0.18);
    }
    .chip.toggle {
      text-decoration: none;
      transition: background 120ms ease, border-color 120ms ease, color 120ms ease, opacity 120ms ease;
    }
    .chip.toggle.active {
      background: var(--brand-soft);
      border-color: #9ecbdc;
      color: var(--brand-dark);
    }
    .chip.toggle.inactive {
      background: #ffffff;
      border-color: #e2e8f0;
      color: #8a9aad;
      opacity: 0.68;
      text-decoration: line-through;
      text-decoration-thickness: 1px;
    }
    .chip.toggle:hover {
      opacity: 1;
      border-color: var(--brand);
    }
    .notice {
      padding: 13px 16px;
      color: var(--brand-dark);
      background: #eef8fc;
      border-color: #bee3ef;
      font-size: 13px;
      font-weight: 750;
    }
    .error {
      padding: 13px 16px;
      border-color: #fecaca;
      background: #fef2f2;
      color: #7f1d1d;
      font-weight: 750;
    }
    .results-panel {
      display: grid;
      gap: 12px;
    }
    .results-header {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: end;
      padding: 2px 2px 0;
    }
    .results-header h3 {
      margin: 0;
      color: var(--brand-dark);
      font-size: 20px;
      letter-spacing: -0.035em;
    }
    .results-header p {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 12px;
    }
    .result-list {
      display: grid;
      gap: 13px;
    }
    .result-group {
      display: grid;
      gap: 11px;
      margin-bottom: 18px;
    }
    .group-heading {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      padding: 12px 3px 4px;
      border-bottom: 1px solid rgba(13, 77, 110, 0.18);
    }
    .group-title {
      color: var(--brand-dark);
      font-size: 19px;
      font-weight: 950;
      letter-spacing: -0.035em;
    }
    .group-count {
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    .result-row {
      display: grid;
      grid-template-columns: 188px minmax(0, 1fr) 138px;
      gap: 19px;
      align-items: start;
      padding: 20px;
      transition: transform 120ms ease, box-shadow 120ms ease, border-color 120ms ease;
    }
    .result-row:hover {
      transform: translateY(-1px);
      border-color: var(--line-strong);
      box-shadow: var(--shadow);
    }
    .member-block {
      min-width: 0;
    }
    .member {
      color: var(--brand);
      font-size: 18px;
      font-weight: 950;
      line-height: 1.18;
      letter-spacing: -0.03em;
      overflow-wrap: anywhere;
    }
    .date {
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
      font-weight: 850;
    }
    .program-title {
      margin: 0;
      color: #16263a;
      font-size: 19px;
      font-weight: 900;
      line-height: 1.3;
      letter-spacing: -0.025em;
      overflow-wrap: anywhere;
    }
    .meta-line {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin-top: 11px;
    }
    .fact {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      padding: 5px 8px;
      background: #f3f7fa;
      border: 1px solid var(--line);
      color: #51687b;
      font-size: 11px;
      font-weight: 850;
      line-height: 1.2;
    }
    .matched-line {
      margin-top: 12px;
      color: #40596c;
      font-size: 13px;
      line-height: 1.5;
      overflow-wrap: anywhere;
    }
    .matched-line strong {
      color: var(--brand-dark);
    }
    .description {
      margin-top: 12px;
      color: #41576a;
      font-size: 14px;
      line-height: 1.56;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    .actions {
      display: grid;
      gap: 10px;
      justify-items: stretch;
    }
    .button.open {
      background: var(--brand);
      white-space: nowrap;
      font-size: 12px;
      box-shadow: 0 10px 20px rgba(13, 77, 110, 0.18);
    }
    .no-url {
      text-align: center;
      color: var(--muted);
      font-size: 12px;
      font-weight: 800;
    }
    details {
      color: var(--muted);
    }
    .fields-toggle {
      grid-column: 1 / -1;
      margin-top: -4px;
    }
    summary {
      cursor: pointer;
      color: var(--brand);
      font-size: 12px;
      font-weight: 900;
      text-align: right;
    }
    .raw-grid {
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: 200px minmax(0, 1fr);
      gap: 7px 12px;
      margin-top: 12px;
      padding-top: 12px;
      border-top: 1px solid var(--line);
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .raw-key {
      color: #52677a;
      font-weight: 900;
    }
    .empty {
      padding: 20px;
      color: var(--muted);
      line-height: 1.55;
    }
    code {
      border-radius: 7px;
      padding: 2px 5px;
      background: #e9eef3;
      color: var(--brand-dark);
    }
    @media (max-width: 1050px) {
      .browser-form {
        grid-template-columns: 1fr;
      }
      .sidebar {
        position: static;
        max-height: none;
        overflow: visible;
      }
      .filter-stack {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }
    }
    @media (max-width: 760px) {
      .topbar-inner, .app-shell {
        padding-left: 14px;
        padding-right: 14px;
      }
      .topbar-inner, .hero-content, .search-row, .result-row {
        grid-template-columns: 1fr;
      }
      .topbar-inner {
        display: grid;
      }
      .top-stats {
        justify-content: start;
      }
      .filter-stack, .date-grid {
        grid-template-columns: 1fr;
      }
      .result-row {
        gap: 12px;
      }
      summary {
        text-align: left;
      }
      .raw-grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <header class="topbar">
    <div class="topbar-inner">
      <div class="brand-lockup">
        <div class="brand-mark">MD</div>
        <div>
          <h1>C-SPAN Matrix Browser</h1>
          <div class="subtitle">Read-only member/topic exploration for C-SPAN program leads</div>
        </div>
      </div>
      <div class="top-stats">
        <div class="stat-pill">Source: <strong>{{ current_source_label }}</strong></div>
        <div class="stat-pill">Total: <strong>{{ total_rows }}</strong></div>
        <div class="stat-pill">Visible: <strong>{{ visible_count }}</strong></div>
      </div>
    </div>
  </header>

  <main class="app-shell">
    <form id="browser_filters" method="get" action="/" class="browser-form">
      {% if selected_topic and active_terms_value %}
        <input type="hidden" id="active_terms_state" name="active_terms" value="{{ active_terms_value }}">
      {% endif %}
      <aside class="sidebar" aria-label="Filters">
        <section class="sidebar-card">
          <h2 class="sidebar-title">Matrix Filters</h2>
          <p class="sidebar-note">Narrow the local catalog by member, matrix topic, source, event type, and date.</p>
          <div class="filter-stack">
            <div>
              <label for="csv_path">Source</label>
              <select id="csv_path" name="csv_path" data-autosubmit>
                {% for option in source_options %}
                  <option value="{{ option.path }}" {% if option.path == csv_path %}selected{% endif %}>{{ option.label }}</option>
                {% endfor %}
              </select>
              <div class="source-path">{{ csv_path }}</div>
            </div>
            <div>
              <label for="member">Member</label>
              <select id="member" name="member" data-autosubmit>
                <option value="">All Members</option>
                {% for member in member_values %}
                  <option value="{{ member }}" {% if member == member_filter %}selected{% endif %}>{{ member }}</option>
                {% endfor %}
              </select>
            </div>

            {% for filter_id, label, columns in filter_specs %}
              <div>
                <label for="{{ filter_id }}">{{ label }}</label>
                <select id="{{ filter_id }}" name="{{ filter_id }}" data-autosubmit>
                  <option value="">All</option>
                  {% for option in filter_options.get(filter_id, []) %}
                    <option value="{{ option }}" {% if option == selected_filters.get(filter_id, "") %}selected{% endif %}>{{ option }}</option>
                  {% endfor %}
                </select>
              </div>
            {% endfor %}

            <div class="date-grid">
              <div>
                <label for="date_from">Date From</label>
                <input id="date_from" name="date_from" value="{{ date_from }}" placeholder="YYYY-MM-DD" data-autosubmit>
              </div>
              <div>
                <label for="date_to">Date To</label>
                <input id="date_to" name="date_to" value="{{ date_to }}" placeholder="YYYY-MM-DD" data-autosubmit>
              </div>
            </div>
            {% if has_priority_score %}
              <div>
                <label for="min_priority_score">Min Priority Score</label>
                <input id="min_priority_score" name="min_priority_score" value="{{ min_priority_score }}" placeholder="0" data-autosubmit>
              </div>
            {% endif %}
            <div>
              <label for="group_by">Group By</label>
              <select id="group_by" name="group_by" data-autosubmit>
                {% for value, label in group_options %}
                  <option value="{{ value }}" {% if value == group_by %}selected{% endif %}>{{ label }}</option>
                {% endfor %}
              </select>
            </div>
          </div>
        </section>
      </aside>

      <section class="main-pane">
        {% if error %}
          <div class="error">{{ error }}</div>
        {% endif %}

        <section class="hero-card">
          <div class="hero-content">
            <div>
              <div class="mode-eyebrow">{{ view_mode_label }} · {{ view_mode_detail }}</div>
              <h2>{{ member_filter or "All Members" }}</h2>
              <p>
                Browse the local C-SPAN matrix by member priorities, source metadata, dates, and topic aliases.
                The browser is read-only and uses only local CSV data.
              </p>
            </div>
            <div class="sort-control">
              <label for="sort">Sort Results</label>
              <select id="sort" name="sort" data-autosubmit>
                {% for value, label, field, direction, kind in sort_options %}
                  <option value="{{ value }}" {% if value == sort_value %}selected{% endif %}>{{ label }}</option>
                {% endfor %}
              </select>
            </div>
          </div>
        </section>

        <section class="content-card search-card">
          <div class="search-row">
            <div>
              <label for="q">Global Search</label>
              <input id="q" name="q" value="{{ query }}" placeholder="Search titles, descriptions, members, keywords" data-debounce-submit>
            </div>
            <div>
              <label>&nbsp;</label>
              <button type="submit">Search</button>
            </div>
          </div>
          <p class="helper-text">Typing auto-searches after a short pause. Dropdown and date changes update immediately.</p>
        </section>

        <section class="content-card context-card">
          <div class="context-head">
            <div>
              <h3 class="context-title">Priority Topics & Related Terms</h3>
              <p class="context-subtitle">
                {% if selected_topic %}
                  {{ context_helper_text(selected_topic, active_terms, active_terms_are_narrowed) }}
                {% elif member_filter %}
                  Matrix topics available for <strong>{{ member_filter }}</strong>.
                {% else %}
                  Select a member or topic to focus the matrix context.
                {% endif %}
              </p>
            </div>
            <span class="chip">{{ visible_count }} visible</span>
          </div>
          <div class="chip-row">
            {% if selected_topic %}
              <span class="chip topic">{{ selected_topic }}</span>
              {% for term in related_terms %}
                <a
                  class="chip toggle {% if term in active_terms %}active{% else %}inactive{% endif %}"
                  href="{{ active_term_toggle_url(term, selected_topic, active_terms) }}"
                  title="{% if term in active_terms %}Turn off{% else %}Turn on{% endif %} {{ term }}"
                >{{ term }}</a>
              {% endfor %}
            {% elif member_filter %}
              {% for topic in filter_options.get("keyword", [])[:18] %}
                <span class="chip soft">{{ topic }}</span>
              {% endfor %}
            {% else %}
              <span class="chip soft">All members</span>
              <span class="chip soft">Global feed</span>
              <span class="chip soft">{{ current_source_label }}</span>
            {% endif %}
          </div>
        </section>

        {% if alias_note %}
          <div class="notice">{{ alias_note }}</div>
        {% endif %}

        {% if rows %}
          <section class="results-panel">
            <div class="results-header">
              <div>
                <h3>Program Leads</h3>
                <p>{{ visible_count }} local row{% if visible_count != 1 %}s{% endif %} · {{ current_source_label }}</p>
              </div>
              <span class="chip">{{ view_mode_detail }}</span>
            </div>
            <div class="result-list">
              {% for group in grouped_rows %}
                <section class="result-group">
                  {% if group.label %}
                    <div class="group-heading">
                      <div class="group-title">{{ group.label }}</div>
                      <div class="group-count">{{ group.count }} result{% if group.count != 1 %}s{% endif %}</div>
                    </div>
                  {% endif %}
                  {% for row in group.rows %}
                    <article class="result-row">
                      <div class="member-block">
                        <div class="member">{{ card_value(row, "member") or "Unknown member" }}</div>
                        {% if card_value(row, "date") %}<div class="date">{{ card_value(row, "date")[:10] }}</div>{% endif %}
                      </div>
                      <div>
                        <h4 class="program-title">{{ card_value(row, "title") or "Untitled C-SPAN program" }}</h4>
                        <div class="meta-line">
                          {% if card_value(row, "score") %}<span class="fact">Score {{ card_value(row, "score") }}</span>{% endif %}
                          {% if card_value(row, "matrix_priority") %}<span class="fact">{{ card_value(row, "matrix_priority") }}</span>{% endif %}
                        </div>
                        {% if card_value(row, "keywords") %}
                          <div class="matched-line"><strong>Matched:</strong> {{ card_value(row, "keywords") }}</div>
                        {% endif %}
                        {% if row.get("_active_matches", "") %}
                          <div class="matched-line"><strong>Active match:</strong> {{ row.get("_active_matches", "") }}</div>
                        {% endif %}
                        {% if card_value(row, "description") %}
                          <div class="description">{{ cell_text(card_value(row, "description"), 360) }}</div>
                        {% endif %}
                      </div>
                      <div class="actions">
                        {% if row["_url"] %}
                          <a class="button open" href="{{ row['_url'] }}" target="_blank" rel="noopener noreferrer">Open C-SPAN</a>
                        {% else %}
                          <span class="no-url">No URL</span>
                        {% endif %}
                      </div>
                      <details class="fields-toggle">
                        <summary>All fields</summary>
                        <div class="raw-grid">
                          {% for key, value in all_fields(row) %}
                            <div class="raw-key">{{ key }}</div>
                            <div>{{ value }}</div>
                          {% endfor %}
                        </div>
                      </details>
                    </article>
                  {% endfor %}
                </section>
              {% endfor %}
            </div>
          </section>
        {% elif not error %}
          <div class="empty">
            {% if member_filter and selected_filters.get("keyword", "") %}
              No local catalog rows matched {{ member_filter }} + {{ selected_filters.get("keyword", "") }}.
              <br><br>
              This does not prove C-SPAN has no results. Try clearing the topic filter or running the
              <code>audit-member-topic</code> diagnostic.
            {% else %}
              No rows match the current filters.
            {% endif %}
          </div>
        {% endif %}
      </section>
    </form>
  </main>
  <script>
    (function () {
      const form = document.getElementById("browser_filters");
      if (!form) {
        return;
      }

      const submitForm = function () {
        if (form.requestSubmit) {
          form.requestSubmit();
        } else {
          form.submit();
        }
      };

      const keywordSelect = document.getElementById("keyword");
      const activeTermsState = document.getElementById("active_terms_state");
      const clearActiveTerms = function () {
        if (activeTermsState) {
          activeTermsState.value = "";
          activeTermsState.removeAttribute("name");
        }
      };

      form.querySelectorAll("[data-autosubmit]").forEach(function (element) {
        element.addEventListener("change", function () {
          if (element === keywordSelect) {
            clearActiveTerms();
          }
          submitForm();
        });
      });

      let searchTimer = null;
      form.querySelectorAll("[data-debounce-submit]").forEach(function (element) {
        element.addEventListener("input", function () {
          window.clearTimeout(searchTimer);
          searchTimer = window.setTimeout(submitForm, 400);
        });
      });
    }());
  </script>
</body>
</html>
"""


def main() -> None:
    app = create_app()
    url = f"http://{HOST}:{PORT}"
    print(f"Starting md_cspan Matrix Browser at {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    app.run(host=HOST, port=PORT, debug=False)


if __name__ == "__main__":
    main()
