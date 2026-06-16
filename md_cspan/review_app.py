from __future__ import annotations

import csv
import re
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

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
            alias_note = alias_note_for_filter(rows, member_filter, selected_filters.get("keyword", ""))
            visible_rows = filter_rows(
                rows=rows,
                query=query,
                member_filter=member_filter,
                selected_filters=selected_filters,
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


def term_matches_text(term: str, text: str) -> bool:
    escaped_term = re.escape(term.strip())
    if not escaped_term:
        return False
    return re.search(rf"(?<!\w){escaped_term}(?!\w)", text, flags=re.IGNORECASE) is not None


def row_matches_topic(row: dict[str, str], selected_value: str) -> bool:
    if not selected_value:
        return True

    if selected_value in values_for_columns(row, TOPIC_COLUMNS):
        return True

    searchable_text = " ".join(
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
    return any(term_matches_text(term, searchable_text) for term in topic_aliases(selected_value))


def alias_note_for_filter(rows: list[dict[str, str]], member_filter: str, selected_topic: str) -> str:
    if not member_filter or not selected_topic:
        return ""

    aliases = [term for term in topic_aliases(selected_topic) if term.lower() != selected_topic.lower()]
    if not aliases:
        return ""

    member_rows = [row for row in rows if row_member(row) == member_filter]
    exact_matches = [row for row in member_rows if selected_topic in values_for_columns(row, TOPIC_COLUMNS)]
    alias_matches = [
        row for row in member_rows
        if row_matches_topic(row, selected_topic)
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
                matches_dropdown = row_matches_topic(row, selected_value)
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
  <title>md_cspan Matrix Browser</title>
  <style>
    :root {
      --bg: #f5f7fb;
      --panel: #ffffff;
      --ink: #172033;
      --muted: #64748b;
      --line: #dbe3ef;
      --brand: #0D4D6E;
      --green: #059669;
      --slate: #475569;
      --soft: #eef4ff;
    }
    body {
      margin: 0;
      font-family: "Pathway Extreme", Arial, Helvetica, sans-serif;
      background: var(--bg);
      color: var(--ink);
    }
    .page {
      max-width: 1180px;
      margin: 0 auto;
      padding: 18px;
    }
    header {
      background: var(--brand);
      color: white;
      border-radius: 0 0 18px 18px;
      margin-bottom: 16px;
      box-shadow: 0 4px 16px rgba(15, 23, 42, 0.18);
    }
    header .page {
      padding-top: 16px;
      padding-bottom: 16px;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 26px;
      letter-spacing: -0.02em;
    }
    label {
      display: block;
      margin-bottom: 4px;
      font-size: 12px;
      font-weight: 700;
      color: inherit;
    }
    input, select, button {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font: inherit;
      background: white;
      color: var(--ink);
    }
    input:focus, select:focus {
      border-color: var(--brand);
      box-shadow: 0 0 0 3px rgba(13, 77, 110, 0.16);
      outline: none;
    }
    button, .button {
      cursor: pointer;
      border: 0;
      background: var(--brand);
      color: white;
      font-weight: 700;
      text-decoration: none;
      display: inline-block;
      text-align: center;
      border-radius: 8px;
      padding: 9px 12px;
    }
    .button.open {
      background: var(--green);
      white-space: nowrap;
    }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px 14px;
      color: #d7deea;
      font-size: 13px;
      overflow-wrap: anywhere;
    }
    .filters-card, .error, .result-card {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      box-shadow: 0 1px 4px rgba(15, 23, 42, 0.08);
    }
    .filters-card {
      padding: 14px;
      margin-bottom: 14px;
      position: sticky;
      top: 0;
      z-index: 4;
    }
    .filters {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      align-items: end;
    }
    .error {
      padding: 12px;
      margin-bottom: 12px;
      border-color: #fecaca;
      background: #fef2f2;
      color: #7f1d1d;
    }
    .notice {
      padding: 12px;
      margin-bottom: 12px;
      border: 1px solid #bfdbfe;
      border-radius: 14px;
      background: #eff6ff;
      color: var(--brand);
      box-shadow: 0 1px 4px rgba(15, 23, 42, 0.06);
    }
    .mode-card {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 11px 14px;
      margin-bottom: 14px;
      background: #f8fbfd;
      border: 1px solid #c8ddea;
      border-radius: 14px;
      color: var(--brand);
      font-weight: 800;
      box-shadow: 0 1px 4px rgba(15, 23, 42, 0.05);
    }
    .mode-detail {
      color: var(--muted);
      font-size: 13px;
      font-weight: 700;
    }
    .result-list {
      display: grid;
      gap: 14px;
    }
    .result-group {
      display: grid;
      gap: 12px;
      margin-bottom: 22px;
    }
    .group-heading {
      padding: 10px 2px 2px;
      border-bottom: 2px solid rgba(13, 77, 110, 0.18);
    }
    .group-title {
      color: var(--brand);
      font-size: 22px;
      font-weight: 800;
      letter-spacing: -0.02em;
    }
    .group-count {
      color: var(--muted);
      font-size: 13px;
      margin-top: 3px;
    }
    .result-card {
      padding: 16px;
    }
    .result-top {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 12px;
      align-items: start;
    }
    .member {
      font-size: 26px;
      font-weight: 700;
      color: var(--brand);
      letter-spacing: -0.02em;
      line-height: 1.12;
      overflow-wrap: anywhere;
    }
    .program-title {
      margin: 7px 0 8px;
      font-size: 16px;
      font-weight: 700;
      color: #334155;
      line-height: 1.32;
      overflow-wrap: anywhere;
    }
    .facts {
      display: flex;
      flex-wrap: wrap;
      gap: 7px;
      margin: 8px 0;
      color: var(--muted);
      font-size: 13px;
    }
    .fact {
      background: var(--soft);
      border: 1px solid #c8ddea;
      border-radius: 999px;
      padding: 4px 8px;
    }
    .description {
      margin: 12px 0;
      line-height: 1.45;
      overflow-wrap: anywhere;
      white-space: pre-wrap;
    }
    details {
      margin-top: 12px;
      color: var(--muted);
    }
    summary {
      cursor: pointer;
      font-weight: 700;
      color: var(--brand);
    }
    .raw-grid {
      display: grid;
      grid-template-columns: 220px minmax(0, 1fr);
      gap: 6px 10px;
      margin-top: 8px;
      font-size: 12px;
      overflow-wrap: anywhere;
    }
    .raw-key {
      font-weight: 700;
      color: var(--slate);
    }
    .empty {
      padding: 16px;
      color: var(--muted);
    }
    @media (max-width: 850px) {
      .meta-grid, .filters, .result-top {
        grid-template-columns: 1fr;
      }
      .filters-card {
        position: static;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="page">
      <h1>md_cspan Matrix Browser</h1>
      <div class="meta-grid">
        <div><strong>Source:</strong> {{ current_source_label }}</div>
        <div><strong>Total rows:</strong> {{ total_rows }}</div>
        <div><strong>Visible rows:</strong> {{ visible_count }}</div>
        <div style="font-size: 12px; opacity: 0.78;"><strong>Path:</strong> {{ csv_path }}</div>
      </div>
    </div>
  </header>

  <main class="page">
    {% if error %}
      <div class="error">{{ error }}</div>
    {% endif %}
    {% if alias_note %}
      <div class="notice">{{ alias_note }}</div>
    {% endif %}

    <form id="browser_filters" method="get" action="/" class="filters-card">
      <div class="filters">
        <div>
          <label for="csv_path">Source</label>
          <select id="csv_path" name="csv_path" data-autosubmit>
            {% for option in source_options %}
              <option value="{{ option.path }}" {% if option.path == csv_path %}selected{% endif %}>{{ option.label }}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label for="q">Global search</label>
          <input id="q" name="q" value="{{ query }}" placeholder="title, description, member, keywords" data-debounce-submit>
        </div>
        <div>
          <label for="member">Member</label>
          <select id="member" name="member" data-autosubmit>
            <option value="">All</option>
            {% for member in member_values %}
              <option value="{{ member }}" {% if member == member_filter %}selected{% endif %}>{{ member }}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label for="sort">Sort</label>
          <select id="sort" name="sort" data-autosubmit>
            {% for value, label, field, direction, kind in sort_options %}
              <option value="{{ value }}" {% if value == sort_value %}selected{% endif %}>{{ label }}</option>
            {% endfor %}
          </select>
        </div>
        <div>
          <label for="group_by">Group by</label>
          <select id="group_by" name="group_by" data-autosubmit>
            {% for value, label in group_options %}
              <option value="{{ value }}" {% if value == group_by %}selected{% endif %}>{{ label }}</option>
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

        <div>
          <label for="date_from">Date from</label>
          <input id="date_from" name="date_from" value="{{ date_from }}" placeholder="YYYY-MM-DD" data-autosubmit>
        </div>
        <div>
          <label for="date_to">Date to</label>
          <input id="date_to" name="date_to" value="{{ date_to }}" placeholder="YYYY-MM-DD" data-autosubmit>
        </div>
        {% if has_priority_score %}
          <div>
            <label for="min_priority_score">Min priority score</label>
            <input id="min_priority_score" name="min_priority_score" value="{{ min_priority_score }}" placeholder="0" data-autosubmit>
          </div>
        {% endif %}
        <div>
          <label>&nbsp;</label>
          <button type="submit">Search / Filter / Sort</button>
        </div>
      </div>
    </form>

    {% if rows %}
      <div class="mode-card">
        <div>{{ view_mode_label }}</div>
        <div class="mode-detail">{{ view_mode_detail }}</div>
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
              <article class="result-card">
                <div class="result-top">
                  <div>
                    <div class="member">{{ card_value(row, "member") or "Unknown member" }}</div>
                    <div class="program-title">{{ card_value(row, "title") or "Untitled C-SPAN program" }}</div>
                    <div class="facts">
                      {% if card_value(row, "date") %}<span class="fact">{{ card_value(row, "date")[:10] }}</span>{% endif %}
                      {% if card_value(row, "score") %}<span class="fact">Score: {{ card_value(row, "score") }}</span>{% endif %}
                      {% if card_value(row, "source_type") %}<span class="fact">{{ card_value(row, "source_type") }}</span>{% endif %}
                      {% if card_value(row, "event_type") %}<span class="fact">{{ card_value(row, "event_type") }}</span>{% endif %}
                    </div>
                    {% if card_value(row, "keywords") %}
                      <div class="facts"><span class="fact">Matched: {{ card_value(row, "keywords") }}</span></div>
                    {% endif %}
                  </div>
                  <div>
                    {% if row["_url"] %}
                      <a class="button open" href="{{ row['_url'] }}" target="_blank" rel="noopener noreferrer">Open C-SPAN</a>
                    {% else %}
                      <span class="fact">No URL</span>
                    {% endif %}
                  </div>
                </div>

                {% if card_value(row, "description") %}
                  <div class="description">{{ cell_text(card_value(row, "description")) }}</div>
                {% endif %}

                <details>
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
    {% elif not error %}
      <div class="filters-card empty">
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

      form.querySelectorAll("[data-autosubmit]").forEach(function (element) {
        element.addEventListener("change", submitForm);
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
