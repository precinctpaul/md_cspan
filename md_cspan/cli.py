from __future__ import annotations

import argparse
import csv
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from md_cspan.client import CSpanApiError, CSpanClient
from md_cspan.config import load_settings


REPO_ROOT = Path(__file__).resolve().parents[1]

CATALOG_FIELDNAMES = [
    "member_name",
    "member_first",
    "member_last",
    "cspan_person_id",
    "event_title",
    "event_date",
    "cspan_url",
    "program_id",
    "public_id",
    "event_id",
    "jwplayer_id",
    "source_type",
    "event_type",
    "description",
    "runtime_seconds",
    "runtime",
    "thumbnail_url",
    "image_path",
    "caption_available",
    "transcript_available",
    "download_available",
    "media_url",
    "detail_fetched",
    "matched_keywords",
    "matched_people",
    "matched_topics",
    "content_bucket",
    "youtube_use",
    "priority_score",
    "status",
    "notes",
    "raw_search_json_path",
    "raw_detail_json_path",
]

INDEX_CATALOG_FIELDNAMES = CATALOG_FIELDNAMES + [
    "source_run",
]

SEEN_PROGRAM_FIELDNAMES = [
    "member_name",
    "program_id",
    "program_key",
    "first_seen_at",
    "last_seen_at",
    "event_date",
    "cspan_url",
    "source_run",
]

UPDATE_INDEX_SUMMARY_FIELDNAMES = [
    "run_started_at",
    "run_finished_at",
    "lookup_path",
    "catalog_path",
    "seen_path",
    "dry_run",
    "members_available",
    "members_processed",
    "rows_seen",
    "new_rows",
    "existing_rows",
    "api_errors",
    "rate_limited",
    "last_started_member_index",
    "last_started_member_name",
    "last_completed_member_index",
    "last_completed_member_name",
    "failed_member_index",
    "failed_member_name",
    "failed_reason",
    "suggested_resume_start_member_index",
    "suggested_resume_command",
    "person_name",
    "cspan_person_id",
    "programs_fetched",
    "added_rows",
    "already_seen",
    "skipped",
    "skip_reasons_summary",
    "empty_page_reached",
    "last_page_fetched",
    "last_page_program_count",
    "crawl_stop_reason",
    "notes",
]

UPDATE_INDEX_SKIPPED_FIELDNAMES = [
    "batch",
    "dry_run",
    "person_name",
    "cspan_person_id",
    "program_id",
    "program_title",
    "program_date",
    "program_url",
    "skip_reason",
    "raw_date",
    "raw_url",
    "notes",
]

TRACKED_PEOPLE_FIELDNAMES = [
    "name",
    "group",
    "role",
    "party_or_affiliation",
    "person_type",
    "aliases",
    "cspan_person_id",
    "active_from",
    "active_to",
    "notes",
]

REVIEWED_NO_CSPAN_PROFILE_FIELDNAMES = [
    "tracked_name",
    "review_status",
    "review_reason",
    "reviewed_at",
]

NO_CSPAN_PROFILE_STATUSES = {
    "no_cspan_profile_found",
    "no_safe_match_found",
}

ARCHIVE_COMPLETENESS_FIELDNAMES = [
    "person_name",
    "group",
    "role",
    "person_type",
    "cspan_person_id",
    "coverage_status",
    "crawl_floor_status",
    "crawl_floor_evidence",
    "catalog_rows_since",
    "seen_rows_since",
    "priority_rows_since",
    "browser_rows_since",
    "earliest_local_row",
    "latest_local_row",
    "program_id_rows",
    "blank_program_id_rows",
    "duplicate_member_program_groups",
    "warnings",
]

COVERAGE_EXCEPTIONS_FIELDNAMES = [
    "name",
    "group",
    "role",
    "person_type",
    "party_or_affiliation",
    "cspan_person_id",
    "coverage_status",
    "crawl_floor_status",
    "reviewed_no_profile_status",
    "reviewed_no_profile_reason",
    "catalog_rows",
    "seen_rows",
    "priority_rows",
    "browser_rows",
    "first_program_date",
    "last_program_date",
    "problem_summary",
    "recommended_next_step",
    "importance_bucket",
]

CSPAN_PERSON_ID_AUDIT_FIELDNAMES = [
    "name",
    "group",
    "role",
    "current_cspan_person_id",
    "lookup_status",
    "candidate_cspan_person_id",
    "candidate_cspan_name",
    "candidate_cspan_title",
    "confidence",
    "evidence_url",
    "evidence_text",
    "notes",
]

REVIEWED_CSPAN_PERSON_ID_FIELDNAMES = [
    "tracked_name",
    "cspan_person_id",
    "reviewed_candidate_name",
    "review_reason",
]


PRIORITY_CATALOG_FIELDNAMES = [
    "member_name",
    "matrix_priority",
    "matched_keywords",
    "match_source",
    "event_title",
    "event_date",
    "cspan_url",
    "program_id",
    "source_type",
    "event_type",
    "content_bucket",
    "youtube_use",
    "priority_score",
    "detail_fetched",
    "description",
    "match_strength",
    "strong_match_count",
    "broad_match_count",
    "review_flag",
]

UNMATCHED_PRIORITY_FIELDNAMES = [
    "member_name",
    "matrix_priority",
    "notes",
]

LEAD_EXPORT_FIELDNAMES = [
    "review_rank",
    "member_name",
    "matrix_priority",
    "priority_score",
    "match_strength",
    "strong_match_count",
    "broad_match_count",
    "matched_keywords",
    "event_title",
    "event_date",
    "cspan_url",
    "program_id",
    "source_type",
    "event_type",
    "content_bucket",
    "youtube_use",
    "detail_fetched",
    "description",
    "review_status",
    "review_notes",
]

HYDRATED_LEAD_FIELDNAMES = LEAD_EXPORT_FIELDNAMES + [
    "detail_fetch_status",
    "detail_fetch_error",
    "caption_available",
    "transcript_available",
    "download_available",
    "media_url",
    "raw_detail_json_path",
]

PRIORITY_SEARCH_FIELDS = [
    "event_title",
    "description",
    "matched_keywords",
    "matched_topics",
    "source_type",
    "event_type",
    "matched_people",
]

BROAD_PRIORITY_TERMS = {
    "costs",
    "cost",
    "affordable",
    "research",
    "china",
    "jobs",
    "job",
    "investment",
    "accountability",
    "infrastructure",
    "community",
    "communities",
    "families",
    "workers",
}

TOPIC_ALIASES_CSV = REPO_ROOT / "data/topic_aliases.csv"


ISSUE_KEYWORDS = {
    "health care": ["health care", "healthcare", "medicaid", "medicare", "obamacare", "aca"],
    "economy": ["economy", "inflation", "prices", "jobs", "tariff", "tariffs", "tax"],
    "immigration": ["immigration", "border", "asylum", "ice", "migrant", "migrants"],
    "democracy": ["democracy", "election", "voting", "rule of law", "constitution"],
    "public safety": ["public safety", "crime", "police", "violence"],
    "national security": ["national security", "defense", "military", "war", "veteran", "veterans"],
    "environment": ["epa", "water", "climate", "environment", "pollution", "pfas"],
    "education": ["education", "school", "schools", "student", "students"],
    "agriculture": ["agriculture", "farm", "farmer", "farmers", "fertilizer", "usda", "food supply"],
}

ACCOUNTABILITY_KEYWORDS = [
    "hearing",
    "question",
    "questioning",
    "testimony",
    "oversight",
    "secretary",
    "director",
    "administrator",
    "nominee",
    "subcommittee",
    "committee",
    "chairman",
    "yield back",
    "mr. chairman",
    "i ask unanimous consent",
    "testifies",
    "testify",
    "grilled",
]

FLOOR_KEYWORDS = [
    "house session",
    "senate session",
    "floor",
    "floor speech",
    "morning hour",
    "special order",
    "legislative business",
]

COMMITTEE_KEYWORDS = [
    "committee",
    "subcommittee",
    "hearing",
    "markup",
    "oversight",
    "testimony",
    "testifies",
    "testify",
]


def parse_param_pairs(pairs: list[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}

    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"Invalid parameter '{pair}'. Use key=value format.")

        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError(f"Invalid parameter '{pair}'. Key cannot be empty.")

        params[key] = value

    return params


def load_csv_rows(input_path: Path) -> list[dict[str, str]]:
    if not input_path.exists():
        raise ValueError(f"Input file does not exist: {input_path}")

    with input_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def write_csv_rows(output_path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_optional_csv_rows(input_path: Path) -> list[dict[str, str]]:
    if not input_path.exists():
        return []
    return load_csv_rows(input_path)


def usable_people_rows(people_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    usable_rows: list[dict[str, str]] = []
    for row in people_rows:
        cspan_person_id = row.get("cspan_person_id", "").strip()
        if not cspan_person_id:
            continue

        matched = row.get("matched", "").lower()
        match_rank = row.get("match_rank", "")
        is_lookup_row = "matched" in row or "match_rank" in row
        if is_lookup_row and not (matched == "yes" and match_rank in ("", "1")):
            continue

        normalized_row = dict(row)
        if not normalized_row.get("display_name", "").strip():
            normalized_row["display_name"] = normalized_row.get("name", "").strip()
        if not normalized_row.get("input_first", "").strip() and normalized_row.get("first", "").strip():
            normalized_row["input_first"] = normalized_row.get("first", "").strip()
        if not normalized_row.get("input_last", "").strip() and normalized_row.get("last", "").strip():
            normalized_row["input_last"] = normalized_row.get("last", "").strip()
        usable_rows.append(normalized_row)
    return usable_rows


def person_display_name(row: dict[str, str]) -> str:
    return (
        row.get("display_name", "").strip()
        or row.get("name", "").strip()
        or row.get("cspan_name", "").strip()
    )


def parse_people_filter(value: str) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def filter_people_by_exact_names(
    all_people_rows: list[dict[str, str]],
    usable_rows: list[dict[str, str]],
    requested_names: list[str],
) -> list[dict[str, str]]:
    if not requested_names:
        return usable_rows

    all_available_names = {person_display_name(row) for row in all_people_rows}
    missing_names = [name for name in requested_names if name not in all_available_names]
    if missing_names:
        raise ValueError(
            "Names passed to --only-people were not found in the people input: "
            + ", ".join(missing_names)
        )

    usable_names = {person_display_name(row) for row in usable_rows}
    skipped_names = [name for name in requested_names if name not in usable_names]
    for name in skipped_names:
        print(f"Skipping {name}: no usable C-SPAN person ID in input.")

    requested_name_set = set(requested_names)
    return [row for row in usable_rows if person_display_name(row) in requested_name_set]


def program_key_for_row(row: dict[str, Any]) -> str:
    program_id = row.get("program_id", "").strip()
    if program_id:
        return program_id

    return "|".join(
        [
            row.get("event_title", "").strip(),
            row.get("event_date", "").strip(),
            row.get("cspan_url", "").strip(),
        ]
    )


def member_program_key(row: dict[str, Any]) -> tuple[str, str]:
    return (row.get("member_name", "").strip(), program_key_for_row(row))


def row_member_name(row: dict[str, Any]) -> str:
    for field in ["member_name", "member", "matched_member", "speaker", "matched_name"]:
        value = row.get(field, "").strip()
        if value:
            return value
    return ""


def row_event_date(row: dict[str, Any]) -> str:
    for field in ["event_date", "program_date", "date"]:
        value = row.get(field, "").strip()
        if value:
            return value
    return ""


def row_title(row: dict[str, Any]) -> str:
    for field in ["event_title", "program_title", "title"]:
        value = row.get(field, "").strip()
        if value:
            return value
    return ""


def row_url_value(row: dict[str, Any]) -> str:
    for field in ["cspan_url", "program_url", "url", "video_url"]:
        value = row.get(field, "").strip()
        if value:
            return value
    return ""


def row_matches_member(row: dict[str, Any], member_name: str) -> bool:
    member_lower = member_name.lower()
    if row_member_name(row).lower() == member_lower:
        return True
    return member_lower in " ".join(str(value) for value in row.values()).lower()


def topic_aliases(topic: str) -> list[str]:
    clean_topic = topic.strip()
    aliases_by_topic = load_topic_alias_rows(TOPIC_ALIASES_CSV)
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


def normalize_person_name(value: str) -> str:
    value = (value or "").lower()
    value = value.replace(".", "")
    value = value.replace("-", " ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def person_name_variants(person: dict[str, str]) -> list[str]:
    variants = [person.get("name", "")]
    aliases = person.get("aliases", "")
    for alias in re.split(r"[;\n]+", aliases or ""):
        if alias.strip():
            variants.append(alias.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        key = normalize_person_name(variant)
        if key and key not in seen:
            seen.add(key)
            deduped.append(variant)
    return deduped


def person_role_terms(person: dict[str, str]) -> set[str]:
    text = " ".join(
        [
            person.get("role", ""),
            person.get("group", ""),
            person.get("party_or_affiliation", ""),
            person.get("person_type", ""),
        ]
    ).lower()
    role_terms: set[str] = set()
    for term in [
        "president",
        "vice president",
        "senator",
        "representative",
        "congressman",
        "congresswoman",
        "governor",
        "mayor",
        "secretary",
        "speaker",
        "leader",
        "press secretary",
        "attorney general",
        "treasury",
        "defense",
        "state",
        "white house",
        "democratic",
        "republican",
    ]:
        if term in text:
            role_terms.add(term)
    return role_terms


def cspan_title_matches_role_context(person: dict[str, str], candidate: dict[str, Any]) -> bool:
    role_text = " ".join(
        [
            person.get("role", ""),
            person.get("group", ""),
            person.get("party_or_affiliation", ""),
            person.get("person_type", ""),
        ]
    ).lower()
    title_text = str(candidate.get("title", "")).lower()

    if "speaker" in role_text:
        return "speaker" in title_text
    if "senate" in role_text or "senator" in role_text:
        return "senator" in title_text or "senate" in title_text
    if "house" in role_text or "representative" in role_text or "congress" in role_text:
        return "representative" in title_text or "house" in title_text or "speaker" in title_text
    if "president" in role_text and "vice president" not in role_text:
        return "president" in title_text
    if "vice president" in role_text:
        return "vice president" in title_text or "senator" in title_text
    if "press secretary" in role_text:
        return "press secretary" in title_text or "spokesperson" in title_text
    if "communications" in role_text:
        return "communications" in title_text or "spokesperson" in title_text
    if "secretary of state" in role_text:
        return "secretary" in title_text or "senator" in title_text
    if "treasury secretary" in role_text:
        return "secretary" in title_text
    if "secretary of defense" in role_text:
        return "secretary" in title_text
    if "deputy attorney general" in role_text:
        return "deputy attorney general" in title_text or "attorney general" in title_text

    role_terms = person_role_terms(person)
    if not role_terms:
        return True
    return any(term in title_text for term in role_terms)


def cspan_person_evidence_url(person: dict[str, Any]) -> str:
    person_id = str(person.get("id", "")).strip()
    if person_id:
        return f"https://www.c-span.org/person/?{person_id}"
    public_id = str(person.get("publicId", "")).strip()
    if public_id:
        return f"https://www.c-span.org/person/{public_id}"
    return ""


def cspan_person_evidence_text(person: dict[str, Any]) -> str:
    name = person.get("name", "")
    title = person.get("title", "")
    person_id = person.get("id", "")
    return " | ".join(part for part in [str(person_id), name, title] if part)


def cspan_candidate_matches_tracked_name_or_alias(
    tracked_person: dict[str, str],
    candidate_name: str,
) -> bool:
    candidate_name_key = normalize_person_name(candidate_name)
    variant_keys = {
        normalize_person_name(variant)
        for variant in person_name_variants(tracked_person)
    }
    return bool(candidate_name_key and candidate_name_key in variant_keys)


def score_cspan_person_candidate(
    tracked_person: dict[str, str],
    candidate: dict[str, Any],
    exact_name_match_count: int,
) -> tuple[str, str]:
    exact_name = cspan_candidate_matches_tracked_name_or_alias(
        tracked_person,
        str(candidate.get("name", "")),
    )
    role_context_matches = cspan_title_matches_role_context(tracked_person, candidate)

    if not exact_name:
        return ("low", "Candidate name is not an exact tracked-name or alias match.")
    if exact_name_match_count > 1:
        return ("needs_review", "Multiple exact-name candidates returned.")
    if not role_context_matches:
        return ("needs_review", "Exact name matched, but C-SPAN title did not clearly match tracked role/group context.")
    return ("high", "Single exact-name candidate with compatible role/title context.")


def best_cspan_person_candidate(
    tracked_person: dict[str, str],
    candidates: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, str, str]:
    if not candidates:
        return None, "not_found", "No C-SPAN people returned."

    variant_keys = {normalize_person_name(variant) for variant in person_name_variants(tracked_person)}
    exact_candidates = [
        candidate for candidate in candidates
        if normalize_person_name(str(candidate.get("name", ""))) in variant_keys
    ]
    if exact_candidates:
        candidate = exact_candidates[0]
        confidence, notes = score_cspan_person_candidate(tracked_person, candidate, len(exact_candidates))
        return candidate, confidence, notes

    return candidates[0], "low", "No exact-name candidate; first returned candidate requires review."


def cspan_person_query_terms(person: dict[str, str]) -> list[str]:
    return person_name_variants(person)


def select_best_audit_candidate(
    person: dict[str, str],
    candidate_groups: list[tuple[str, list[dict[str, Any]]]],
) -> tuple[dict[str, Any] | None, str, str, str]:
    fallback_candidate: dict[str, Any] | None = None
    fallback_confidence = "not_found"
    fallback_notes = "No C-SPAN people returned."
    fallback_query = ""

    for query_term, candidates in candidate_groups:
        candidate, confidence, notes = best_cspan_person_candidate(person, candidates)
        if candidate is None:
            continue
        if fallback_candidate is None:
            fallback_candidate = candidate
            fallback_confidence = confidence
            fallback_notes = notes
            fallback_query = query_term
        if confidence == "high":
            return candidate, confidence, f"{notes} Query used: {query_term}.", query_term

    if fallback_candidate is not None:
        return fallback_candidate, fallback_confidence, f"{fallback_notes} Query used: {fallback_query}.", fallback_query

    return None, "not_found", fallback_notes, ""


def load_topic_alias_rows(input_path: Path) -> dict[str, list[str]]:
    aliases_by_topic: dict[str, list[str]] = {}
    if not input_path.exists():
        return aliases_by_topic

    for row in load_optional_csv_rows(input_path):
        topic = row.get("topic", "").strip()
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


def row_text(row: dict[str, Any]) -> str:
    return " ".join(str(value) for value in row.values())


def row_matches_any_term(row: dict[str, Any], terms: list[str]) -> bool:
    text = row_text(row)
    return any(priority_term_matches(term, text) for term in terms if term.strip())


def row_matches_exact_topic(row: dict[str, Any], topic: str) -> bool:
    topic_key = normalize_topic_key(topic)
    for field in ["matrix_priority", "priority", "matched_keywords", "matched_terms", "matched_topics"]:
        values = parse_keyword_terms(row.get(field, ""))
        if any(normalize_topic_key(value) == topic_key for value in values):
            return True
    return False


def matrix_topic_values(input_path: Path) -> list[str]:
    topics = {
        row.get("priority", "").strip()
        for row in load_optional_csv_rows(input_path)
        if row.get("priority", "").strip()
    }
    return sorted(topics, key=str.lower)


def row_is_since(row: dict[str, Any], since: str) -> bool:
    if not since:
        return True
    event_date = row_event_date(row)[:10]
    if not event_date:
        return True
    return event_date >= since


def is_rate_limit_error(exc: CSpanApiError) -> bool:
    return "Status: 429" in str(exc)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def update_index_summary_path(output_new_path: Path) -> Path:
    name = output_new_path.name
    if "new_programs" in name:
        summary_name = name.replace("new_programs", "update_index", 1)
    else:
        summary_name = f"{output_new_path.stem}_summary{output_new_path.suffix}"

    if not summary_name.endswith(f"_summary{output_new_path.suffix}"):
        summary_name = f"{Path(summary_name).stem}_summary{output_new_path.suffix}"

    return output_new_path.with_name(summary_name)


def update_index_skipped_path(output_new_path: Path) -> Path:
    name = output_new_path.name
    if "new_programs" in name:
        skipped_name = name.replace("new_programs", "skipped_programs", 1)
    else:
        skipped_name = f"{output_new_path.stem}_skipped_programs{output_new_path.suffix}"

    return output_new_path.with_name(skipped_name)


def append_stem_suffix(path_value: str, suffix: str) -> str:
    path = Path(path_value)
    if path.suffix:
        return str(path.with_name(f"{path.stem}{suffix}{path.suffix}"))
    return f"{path_value}{suffix}"


def quote_windows_cmd_arg(value: Any) -> str:
    text = str(value)
    if text == "":
        return '""'
    if any(char.isspace() for char in text) or "," in text or "&" in text or "|" in text or "(" in text or ")" in text:
        return f'"{text.replace(chr(34), chr(34) + chr(34))}"'
    return text


def build_update_index_resume_command(
    args: argparse.Namespace,
    resume_start_member_index: int,
    failed_because_rate_limit: bool,
    selected_member_count: int,
    failed_selected_offset: int = 0,
    failed_page: int = 1,
    failed_cursor: str = "",
    selected_people_rows: list[dict[str, str]] | None = None,
    output_suffix: str = "_resume",
) -> str:
    original_start_member_index = max(1, int(args.start_member_index))
    original_limit_members = max(0, int(args.limit_members))
    if original_limit_members:
        consumed_before_failure = max(0, resume_start_member_index - original_start_member_index)
        resume_limit_members = max(1, original_limit_members - consumed_before_failure)
    else:
        resume_limit_members = 0

    if selected_member_count and resume_limit_members:
        resume_limit_members = min(resume_limit_members, selected_member_count)

    sleep_seconds = max(float(args.sleep_seconds), 2.0) if failed_because_rate_limit else float(args.sleep_seconds)
    lookup_flag = getattr(args, "lookup_source_flag", "--lookup")
    only_people_value = getattr(args, "only_people", "").strip()
    if only_people_value and selected_people_rows is not None:
        remaining_rows = selected_people_rows[max(0, failed_selected_offset) :]
        only_people_value = ",".join(person_display_name(row) for row in remaining_rows)

    command_parts = [
        "python",
        "-m",
        "md_cspan.cli",
        "update-index",
        lookup_flag,
        str(args.lookup),
        "--catalog",
        str(args.catalog),
        "--seen",
        str(args.seen),
        "--output-new",
        append_stem_suffix(str(args.output_new), output_suffix),
        "--raw-dir",
        append_stem_suffix(str(args.raw_dir), output_suffix),
        "--max-pages-per-member",
        str(args.max_pages_per_member),
        "--sleep-seconds",
        f"{sleep_seconds:g}",
    ]

    if only_people_value:
        command_parts.extend(["--only-people", only_people_value])
    else:
        command_parts.extend(
            [
                "--start-member-index",
                str(resume_start_member_index),
                "--limit-members",
                str(resume_limit_members),
            ]
        )
    if failed_page > 1:
        command_parts.extend(["--start-page", str(failed_page)])
    if failed_cursor:
        command_parts.extend(["--start-cursor", failed_cursor])
    if getattr(args, "sort", "date desc") != "date desc":
        command_parts.extend(["--sort", str(args.sort)])
    if getattr(args, "since", ""):
        command_parts.extend(["--since", str(args.since)])
    if getattr(args, "dry_run", False):
        command_parts.append("--dry-run")

    return " ".join(quote_windows_cmd_arg(part) for part in command_parts)


def parse_keyword_terms(value: str) -> list[str]:
    terms = []
    for term in re.split(r"[,\n;]+", value or ""):
        clean_term = term.strip()
        if clean_term:
            terms.append(clean_term)
    return terms


def build_priority_search_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(field, "")) for field in PRIORITY_SEARCH_FIELDS)


def priority_term_matches(term: str, searchable_text: str) -> bool:
    escaped_term = re.escape(term.strip())
    if not escaped_term:
        return False

    pattern = rf"(?<!\w){escaped_term}(?!\w)"
    return re.search(pattern, searchable_text, flags=re.IGNORECASE) is not None


def get_matrix_priority(row: dict[str, Any]) -> str:
    return row.get("matrix_priority", "") or row.get("priority", "")


def get_matched_keywords(row: dict[str, Any]) -> str:
    return row.get("matched_keywords", "") or row.get("matched_terms", "")


def lead_dedupe_key(row: dict[str, Any], index: int) -> tuple[str, str, str]:
    member_name = row.get("member_name", "")
    program_id = row.get("program_id", "")
    if program_id:
        return (member_name, program_id, "")

    return (
        member_name,
        "",
        "|".join(
            [
                row.get("event_title", ""),
                row.get("event_date", ""),
                get_matrix_priority(row),
            ]
        ),
    )


def lead_dedupe_score(row: dict[str, Any], index: int) -> tuple[int, int, str, int]:
    return (
        int(row.get("priority_score", 0) or 0),
        int(row.get("strong_match_count", 0) or 0),
        row.get("event_date", ""),
        -index,
    )


def program_from_lead_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("program_id", ""),
        "title": row.get("event_title", ""),
        "date": row.get("event_date", ""),
        "description": row.get("description", ""),
        "url": row.get("cspan_url", ""),
    }


def merge_detail_into_lead_row(
    row: dict[str, Any],
    catalog_row: dict[str, Any],
    detail_fetch_status: str,
    detail_fetch_error: str = "",
) -> dict[str, Any]:
    updated_row = dict(row)
    original_priority_score = row.get("priority_score", "")

    for field in [
        "event_title",
        "event_date",
        "cspan_url",
        "source_type",
        "event_type",
        "content_bucket",
        "youtube_use",
        "detail_fetched",
        "description",
        "caption_available",
        "transcript_available",
        "download_available",
        "media_url",
        "raw_detail_json_path",
    ]:
        value = catalog_row.get(field, "")
        if value:
            updated_row[field] = value

    updated_row["priority_score"] = original_priority_score
    updated_row["detail_fetch_status"] = detail_fetch_status
    updated_row["detail_fetch_error"] = detail_fetch_error
    updated_row.setdefault("review_status", "")
    updated_row.setdefault("review_notes", "")
    return updated_row


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value)
    return value.strip("_") or "unknown"


def normalize_people_response(data: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        people = data.get("people", [])
        if isinstance(people, list):
            return [item for item in people if isinstance(item, dict)]

    return []


def normalize_programs_response(data: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        for key in ("programs", "results", "items", "videos"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

    return []


def get_cursor(data: dict[str, Any] | list[Any]) -> str:
    if isinstance(data, dict):
        cursor = data.get("cursor", "")
        if cursor is None:
            return ""
        return str(cursor)
    return ""


def first_value(source: dict[str, Any], keys: list[str], default: str = "") -> str:
    for key in keys:
        value = source.get(key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            if value:
                return json.dumps(value, ensure_ascii=False)
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def first_value_from_sources(
    program: dict[str, Any],
    detail: dict[str, Any] | None,
    keys: list[str],
    default: str = "",
) -> str:
    detail_value = first_value(detail or {}, keys, "")
    if detail_value:
        return detail_value

    program_value = first_value(program, keys, "")
    if program_value:
        return program_value

    return default


def boolish_from_fields(source: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        if key in source:
            value = source.get(key)
            if isinstance(value, bool):
                return "yes" if value else "no"
            if value in (None, "", [], {}):
                return "no"
            return "yes"
    return "unknown"


def detect_keywords(text: str, keywords: list[str]) -> list[str]:
    text_lower = text.lower()
    matches: list[str] = []

    for keyword in keywords:
        if keyword.lower() in text_lower:
            matches.append(keyword)

    return matches


def detect_issue_topics(text: str) -> list[str]:
    text_lower = text.lower()
    topics: list[str] = []

    for topic, keywords in ISSUE_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            topics.append(topic)

    return topics


def searchable_text(program: dict[str, Any], detail: dict[str, Any] | None = None) -> str:
    pieces: list[str] = []

    for source in [program, detail or {}]:
        for key in [
            "title",
            "abstract",
            "description",
            "summary",
            "category",
            "format",
            "series",
            "location",
            "person",
            "persons",
            "subject",
            "subjects",
            "tag",
            "tags",
            "sponsor",
        ]:
            value = source.get(key)
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                pieces.append(json.dumps(value, ensure_ascii=False))
            else:
                pieces.append(str(value))

    return " ".join(pieces)


def infer_source_type(program: dict[str, Any], detail: dict[str, Any] | None) -> str:
    combined = searchable_text(program, detail).lower()

    if any(keyword in combined for keyword in COMMITTEE_KEYWORDS):
        return "committee / hearing"

    if any(keyword in combined for keyword in FLOOR_KEYWORDS):
        return "floor / chamber"

    category = first_value_from_sources(program, detail, ["category", "format", "series"], "")
    if category:
        return category

    return "unknown"


def infer_event_type(program: dict[str, Any], detail: dict[str, Any] | None) -> str:
    combined = searchable_text(program, detail).lower()
    url = first_value_from_sources(program, detail, ["videoLink", "url", "programUrl", "link"], "").lower()

    if "senate-committee" in url or "house-committee" in url:
        return "committee hearing"
    if "senate-proceeding" in url:
        return "senate proceeding"
    if "house-proceeding" in url:
        return "house proceeding"
    if "news-conference" in url:
        return "news conference"
    if "public-affairs-event" in url:
        return "public affairs event"
    if "interview" in url:
        return "interview"

    if "hearing" in combined:
        return "hearing"
    if "markup" in combined:
        return "markup"
    if "house session" in combined:
        return "house session"
    if "senate session" in combined:
        return "senate session"
    if "floor" in combined:
        return "floor speech"
    if "interview" in combined:
        return "interview"
    if "news conference" in combined or "press conference" in combined:
        return "news conference"

    return "unknown"


def classify_content_bucket(program: dict[str, Any], detail: dict[str, Any] | None = None) -> str:
    text = searchable_text(program, detail).lower()

    if any(keyword in text for keyword in ACCOUNTABILITY_KEYWORDS):
        return "Accountability Clip"

    topics = detect_issue_topics(text)
    if topics:
        return "Issue Explainer"

    if any(word in text for word in ["values", "service", "country", "democracy", "constitution"]):
        return "Values & Contrast"

    if any(word in text for word in ["district", "constituents", "community", "local"]):
        return "Practical Governance"

    return "Test Candidate"


def classify_youtube_use(
    content_bucket: str,
    source_type: str,
    program: dict[str, Any],
    detail: dict[str, Any] | None = None,
) -> str:
    text = searchable_text(program, detail).lower()

    if content_bucket == "Accountability Clip":
        return "Short + Longer Clip"

    if content_bucket == "Issue Explainer":
        return "Short + Longer Clip"

    if "floor" in source_type.lower() or "session" in source_type.lower():
        return "Short"

    if any(word in text for word in ["hearing", "committee", "testimony"]):
        return "Short + Longer Clip"

    return "Test Candidate"


def score_priority(program: dict[str, Any], detail: dict[str, Any] | None = None) -> int:
    text = searchable_text(program, detail).lower()
    score = 0

    if any(keyword in text for keyword in ACCOUNTABILITY_KEYWORDS):
        score += 30

    if any(keyword in text for keyword in COMMITTEE_KEYWORDS):
        score += 20

    if any(keyword in text for keyword in FLOOR_KEYWORDS):
        score += 15

    issue_topics = detect_issue_topics(text)
    score += min(len(issue_topics) * 8, 24)

    title = first_value_from_sources(program, detail, ["title"], "")
    if title:
        score += 5

    description = first_value_from_sources(program, detail, ["abstract", "description", "summary"], "")
    if description:
        score += 5

    return score


def format_runtime(runtime_seconds: str) -> str:
    if not runtime_seconds:
        return ""

    try:
        total_seconds = int(float(runtime_seconds))
    except ValueError:
        return runtime_seconds

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"

    return f"{minutes}:{seconds:02d}"


def build_cspan_url(program_id: str, public_id: str, program: dict[str, Any], detail: dict[str, Any] | None = None) -> str:
    existing = first_value_from_sources(
        program,
        detail,
        ["videoLink", "url", "programUrl", "link", "videoUrl", "canonicalUrl"],
        "",
    )
    if existing:
        return existing

    if public_id:
        return f"https://www.c-span.org/video/?{public_id}"

    if program_id:
        return f"https://www.c-span.org/program/{program_id}"

    return ""


def extract_program_id(program: dict[str, Any]) -> str:
    return first_value(
        program,
        ["id", "videoId", "videoID", "programId", "programID", "video_id", "program_id"],
        "",
    )


def build_thumbnail_url(image_path: str) -> str:
    if not image_path:
        return ""

    if image_path.startswith("http://") or image_path.startswith("https://"):
        return image_path

    clean_path = image_path.lstrip("/")
    return f"https://static.c-spanvideo.org/{clean_path}"


def build_catalog_row(
    member_name: str,
    member_first: str,
    member_last: str,
    cspan_person_id: str,
    program: dict[str, Any],
    detail: dict[str, Any] | None,
    detail_fetched: str,
    raw_search_json_path: str,
    raw_detail_json_path: str,
) -> dict[str, Any]:
    program_id = extract_program_id(program)

    title = first_value_from_sources(program, detail, ["title"], "")

    event_date = first_value_from_sources(
        program,
        detail,
        ["date", "time", "airDate", "eventDate", "startDate"],
        "",
    )

    description = first_value_from_sources(
        program,
        detail,
        ["description", "abstract", "summary"],
        "",
    )

    runtime_seconds = first_value_from_sources(
        program,
        detail,
        ["videoDuration", "runtime", "duration", "length"],
        "",
    )

    public_id = first_value_from_sources(program, detail, ["publicId", "publicID"], "")
    event_id = first_value_from_sources(program, detail, ["eventid", "eventId", "eventID"], "")
    jwplayer_id = first_value_from_sources(program, detail, ["jwplayerId", "jwPlayerId", "jwplayerID"], "")

    image_path = first_value_from_sources(
        program,
        detail,
        ["imagePath", "thumbnail", "thumbnailUrl", "image", "imageUrl"],
        "",
    )

    thumbnail_url = build_thumbnail_url(image_path)

    media_url = first_value_from_sources(
        program,
        detail,
        ["mediaUrl", "downloadUrl", "videoUrl", "mp4", "hlsUrl"],
        "",
    )

    combined_text = searchable_text(program, detail)
    matched_issue_topics = detect_issue_topics(combined_text)
    matched_accountability = detect_keywords(combined_text, ACCOUNTABILITY_KEYWORDS)
    matched_floor = detect_keywords(combined_text, FLOOR_KEYWORDS)
    matched_keywords = sorted(set(matched_accountability + matched_floor + matched_issue_topics))

    source_type = infer_source_type(program, detail)
    event_type = infer_event_type(program, detail)
    content_bucket = classify_content_bucket(program, detail)
    youtube_use = classify_youtube_use(content_bucket, source_type, program, detail)
    priority_score = score_priority(program, detail)

    source_for_availability = detail or program

    caption_available = boolish_from_fields(
        source_for_availability,
        ["caption", "captions", "captionUrl", "closedCaption", "closedCaptions", "srt", "vtt"],
    )
    transcript_available = boolish_from_fields(
        source_for_availability,
        ["transcript", "transcripts", "transcriptUrl", "text"],
    )
    download_available = "yes" if media_url else boolish_from_fields(
        source_for_availability,
        ["downloadUrl", "downloads", "media", "files", "videoFiles"],
    )

    return {
        "member_name": member_name,
        "member_first": member_first,
        "member_last": member_last,
        "cspan_person_id": cspan_person_id,
        "event_title": title,
        "event_date": event_date,
        "cspan_url": build_cspan_url(program_id, public_id, program, detail),
        "program_id": program_id,
        "public_id": public_id,
        "event_id": event_id,
        "jwplayer_id": jwplayer_id,
        "source_type": source_type,
        "event_type": event_type,
        "description": description,
        "runtime_seconds": runtime_seconds,
        "runtime": format_runtime(runtime_seconds),
        "thumbnail_url": thumbnail_url,
        "image_path": image_path,
        "caption_available": caption_available,
        "transcript_available": transcript_available,
        "download_available": download_available,
        "media_url": media_url,
        "detail_fetched": detail_fetched,
        "matched_keywords": "; ".join(matched_keywords),
        "matched_people": first_value_from_sources(program, detail, ["person", "persons"], ""),
        "matched_topics": "; ".join(matched_issue_topics),
        "content_bucket": content_bucket,
        "youtube_use": youtube_use,
        "priority_score": priority_score,
        "status": "new",
        "notes": "",
        "raw_search_json_path": raw_search_json_path,
        "raw_detail_json_path": raw_detail_json_path,
    }


def build_skipped_program_row(
    batch: str,
    dry_run: str,
    person_name: str,
    cspan_person_id: str,
    program: dict[str, Any],
    catalog_row: dict[str, Any] | None,
    skip_reason: str,
    notes: str = "",
) -> dict[str, Any]:
    raw_date = first_value(program, ["date", "time", "airDate", "eventDate", "startDate"], "")
    raw_url = first_value(program, ["videoLink", "url", "programUrl", "link", "videoUrl", "canonicalUrl"], "")

    return {
        "batch": batch,
        "dry_run": dry_run,
        "person_name": person_name,
        "cspan_person_id": cspan_person_id,
        "program_id": (catalog_row or {}).get("program_id", "") or extract_program_id(program),
        "program_title": (catalog_row or {}).get("event_title", "") or first_value(program, ["title"], ""),
        "program_date": (catalog_row or {}).get("event_date", "") or raw_date,
        "program_url": (catalog_row or {}).get("cspan_url", "") or raw_url,
        "skip_reason": skip_reason,
        "raw_date": raw_date,
        "raw_url": raw_url,
        "notes": notes,
    }


def increment_count(counts: dict[str, int], key: str, amount: int = 1) -> None:
    counts[key] = counts.get(key, 0) + amount


def counts_summary(counts: dict[str, int]) -> str:
    return "; ".join(f"{key}: {counts[key]}" for key in sorted(counts))


def cmd_raw(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    params = parse_param_pairs(args.param)
    data = client.get(args.path, params=params)

    if args.output:
        output_path = Path(args.output)
        client.save_json(data, output_path)
        print(f"Saved response to: {output_path}")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))

    return 0


def cmd_smoke_test(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    params = parse_param_pairs(args.param)
    data = client.get(args.path, params=params)

    output_path = Path("output") / "smoke_test_response.json"
    client.save_json(data, output_path)

    print("C-SPAN API smoke test succeeded.")
    print(f"Saved response to: {output_path}")
    return 0


def cmd_people_lookup(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_output_path = Path(args.raw_output)

    members = load_csv_rows(input_path)
    aliases_by_display_name: dict[str, list[dict[str, str]]] = {}
    aliases_path = getattr(args, "aliases", None)
    if aliases_path:
        for alias in load_csv_rows(Path(aliases_path)):
            alias_display_name = alias.get("display_name", "").strip()
            if alias_display_name:
                aliases_by_display_name.setdefault(alias_display_name, []).append(alias)

    output_rows: list[dict[str, Any]] = []
    raw_results: dict[str, Any] = {}

    for member in members:
        first = member.get("first", "").strip() or member.get("input_first", "").strip()
        last = member.get("last", "").strip() or member.get("input_last", "").strip()
        display_name = (
            member.get("display_name", "").strip()
            or member.get("name", "").strip()
            or f"{first} {last}".strip()
        )
        if display_name and not first and not last:
            name_parts = display_name.split()
            if len(name_parts) >= 2:
                first = name_parts[0]
                last = " ".join(name_parts[1:])

        if not first and not last and not display_name:
            continue

        params: dict[str, Any] = {}
        if first:
            params["first"] = first
        if last:
            params["last"] = last

        if not params and display_name:
            params["query"] = display_name

        print(f"Looking up person: {display_name}")

        data = client.get("/people", params=params)
        raw_results[display_name] = data

        people = normalize_people_response(data)
        lookup_method = "normal"
        alias_used = "no"
        alias_first = ""
        alias_last = ""
        alias_query = ""
        aliases_tried = False

        if not people:
            alias_attempts: list[dict[str, Any]] = []
            for alias in aliases_by_display_name.get(display_name, []):
                current_alias_first = alias.get("alias_first", "").strip()
                current_alias_last = alias.get("alias_last", "").strip()
                current_alias_query = alias.get("alias_query", "").strip()
                alias_params: dict[str, Any] = {}

                if current_alias_first:
                    alias_params["first"] = current_alias_first
                if current_alias_last:
                    alias_params["last"] = current_alias_last
                if current_alias_query:
                    alias_params["query"] = current_alias_query
                if not alias_params:
                    continue

                aliases_tried = True
                print(f"  Trying alias for {display_name}")
                alias_data = client.get("/people", params=alias_params)
                alias_attempts.append(
                    {
                        "alias_first": current_alias_first,
                        "alias_last": current_alias_last,
                        "alias_query": current_alias_query,
                        "response": alias_data,
                    }
                )
                people = normalize_people_response(alias_data)

                if people:
                    lookup_method = "alias"
                    alias_used = "yes"
                    alias_first = current_alias_first
                    alias_last = current_alias_last
                    alias_query = current_alias_query
                    break

            if alias_attempts:
                raw_results[display_name] = {
                    "normal": data,
                    "alias_attempts": alias_attempts,
                }

        if not people:
            output_rows.append(
                {
                    "display_name": display_name,
                    "input_first": first,
                    "input_last": last,
                    "matched": "no",
                    "match_rank": "",
                    "cspan_person_id": "",
                    "cspan_public_id": "",
                    "cspan_name": "",
                    "cspan_first_name": "",
                    "cspan_last_name": "",
                    "cspan_title": "",
                    "cspan_image_path": "",
                    "lookup_method": "alias" if aliases_tried else "normal",
                    "alias_used": "no",
                    "alias_first": "",
                    "alias_last": "",
                    "alias_query": "",
                    "notes": "No alias match returned" if aliases_tried else "No normal match returned",
                }
            )
            continue

        for index, person in enumerate(people, start=1):
            output_rows.append(
                {
                    "display_name": display_name,
                    "input_first": first,
                    "input_last": last,
                    "matched": "yes",
                    "match_rank": index,
                    "cspan_person_id": person.get("id", ""),
                    "cspan_public_id": person.get("publicId", ""),
                    "cspan_name": person.get("name", ""),
                    "cspan_first_name": person.get("firstName", ""),
                    "cspan_last_name": person.get("lastName", ""),
                    "cspan_title": person.get("title", ""),
                    "cspan_image_path": person.get("imagePath", ""),
                    "lookup_method": lookup_method,
                    "alias_used": alias_used,
                    "alias_first": alias_first,
                    "alias_last": alias_last,
                    "alias_query": alias_query,
                    "notes": "",
                }
            )

    fieldnames = [
        "display_name",
        "input_first",
        "input_last",
        "matched",
        "match_rank",
        "cspan_person_id",
        "cspan_public_id",
        "cspan_name",
        "cspan_first_name",
        "cspan_last_name",
        "cspan_title",
        "cspan_image_path",
        "lookup_method",
        "alias_used",
        "alias_first",
        "alias_last",
        "alias_query",
        "notes",
    ]

    write_csv_rows(output_path, output_rows, fieldnames)
    client.save_json(raw_results, raw_output_path)

    print("People lookup complete.")
    print(f"Saved CSV to: {output_path}")
    print(f"Saved raw JSON to: {raw_output_path}")
    return 0


def cmd_program_search(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    query = args.query.strip()
    if not query:
        raise ValueError("Query cannot be empty.")

    params: dict[str, Any] = {"query": query}

    if args.sort:
        params["sort"] = args.sort

    if args.cursor:
        params["cursor"] = args.cursor

    data = client.get("/programs/search", params=params)

    output_path = Path(args.output)
    raw_output_path = Path(args.raw_output)

    client.save_json(data, raw_output_path)

    programs = normalize_programs_response(data)
    cursor = get_cursor(data)

    rows: list[dict[str, Any]] = []

    for program in programs:
        rows.append(
            {
                "query": query,
                "video_id": extract_program_id(program),
                "title": program.get("title", ""),
                "date": program.get("date", ""),
                "format": program.get("format", ""),
                "category": program.get("category", ""),
                "series": program.get("series", ""),
                "location": program.get("location", ""),
                "person": program.get("person", ""),
                "personid": program.get("personid", ""),
                "subject": program.get("subject", ""),
                "tag": program.get("tag", ""),
                "abstract": program.get("abstract", "") or program.get("description", ""),
                "url": program.get("videoLink", "") or program.get("url", "") or program.get("programUrl", "") or program.get("link", ""),
                "thumbnail": build_thumbnail_url(program.get("imagePath", "") or program.get("thumbnail", "") or program.get("image", "")),
                "next_cursor": cursor,
            }
        )

    fieldnames = [
        "query",
        "video_id",
        "title",
        "date",
        "format",
        "category",
        "series",
        "location",
        "person",
        "personid",
        "subject",
        "tag",
        "abstract",
        "url",
        "thumbnail",
        "next_cursor",
    ]

    write_csv_rows(output_path, rows, fieldnames)

    print("Program search complete.")
    print(f"Programs returned: {len(rows)}")
    print(f"Saved CSV to: {output_path}")
    print(f"Saved raw JSON to: {raw_output_path}")

    if cursor:
        print(f"Next cursor: {cursor}")

    return 0


def cmd_person_program_search(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    person_id = str(args.person_id).strip()
    if not person_id:
        raise ValueError("person_id cannot be empty.")

    query = f"personid:{person_id}"

    if args.extra_query:
        query = f"{query} AND ({args.extra_query.strip()})"

    params: dict[str, Any] = {"query": query}

    if args.sort:
        params["sort"] = args.sort

    if args.cursor:
        params["cursor"] = args.cursor

    data = client.get("/programs/search", params=params)

    output_path = Path(args.output)
    raw_output_path = Path(args.raw_output)

    client.save_json(data, raw_output_path)

    programs = normalize_programs_response(data)
    cursor = get_cursor(data)

    rows: list[dict[str, Any]] = []

    for program in programs:
        rows.append(
            {
                "person_id": person_id,
                "query": query,
                "video_id": extract_program_id(program),
                "title": program.get("title", ""),
                "date": program.get("date", ""),
                "format": program.get("format", ""),
                "category": program.get("category", ""),
                "series": program.get("series", ""),
                "location": program.get("location", ""),
                "person": program.get("person", ""),
                "personid": program.get("personid", ""),
                "subject": program.get("subject", ""),
                "tag": program.get("tag", ""),
                "abstract": program.get("abstract", "") or program.get("description", ""),
                "url": program.get("videoLink", "") or program.get("url", "") or program.get("programUrl", "") or program.get("link", ""),
                "thumbnail": build_thumbnail_url(program.get("imagePath", "") or program.get("thumbnail", "") or program.get("image", "")),
                "next_cursor": cursor,
            }
        )

    fieldnames = [
        "person_id",
        "query",
        "video_id",
        "title",
        "date",
        "format",
        "category",
        "series",
        "location",
        "person",
        "personid",
        "subject",
        "tag",
        "abstract",
        "url",
        "thumbnail",
        "next_cursor",
    ]

    write_csv_rows(output_path, rows, fieldnames)

    print("Person program search complete.")
    print(f"Person ID: {person_id}")
    print(f"Query: {query}")
    print(f"Programs returned: {len(rows)}")
    print(f"Saved CSV to: {output_path}")
    print(f"Saved raw JSON to: {raw_output_path}")

    if cursor:
        print(f"Next cursor: {cursor}")

    return 0


def cmd_program_detail(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    video_id = str(args.video_id).strip()
    if not video_id:
        raise ValueError("video_id cannot be empty.")

    data = client.get(f"/programs/{video_id}")

    output_path = Path(args.output)
    client.save_json(data, output_path)

    print("Program detail fetch complete.")
    print(f"Video ID: {video_id}")
    print(f"Saved JSON to: {output_path}")
    return 0


def cmd_archive_catalog(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    input_path = Path(args.input)
    output_path = Path(args.output)
    raw_dir = Path(args.raw_dir)

    raw_search_dir = raw_dir / "search"
    raw_detail_dir = raw_dir / "detail"

    people_rows = load_csv_rows(input_path)
    catalog_rows: list[dict[str, Any]] = []

    max_pages_per_member = max(1, int(args.max_pages_per_member))
    start_member_index = max(1, int(args.start_member_index))
    limit_members = max(0, int(args.limit_members))
    sleep_seconds = max(0.0, float(args.sleep_seconds))
    detail_limit_per_member = args.detail_limit_per_member
    if detail_limit_per_member is not None:
        detail_limit_per_member = max(0, int(detail_limit_per_member))

    fetch_details = not args.skip_details
    dedupe_programs = args.dedupe_programs
    processed_members = 0
    seen_program_ids: set[str] = set()
    duplicate_program_ids_skipped = 0

    usable_people_rows = [
        row
        for row in people_rows
        if row.get("matched", "").lower() == "yes"
        and row.get("match_rank", "") in ("", "1")
        and row.get("cspan_person_id", "").strip()
    ]
    selected_people_rows = usable_people_rows[start_member_index - 1 :]
    if limit_members:
        selected_people_rows = selected_people_rows[:limit_members]

    for person_row in selected_people_rows:
        processed_members += 1

        cspan_person_id = person_row.get("cspan_person_id", "").strip()
        member_name = person_row.get("display_name", "") or person_row.get("cspan_name", "")
        member_first = person_row.get("input_first", "") or person_row.get("cspan_first_name", "")
        member_last = person_row.get("input_last", "") or person_row.get("cspan_last_name", "")

        member_slug = slugify(member_name)
        cursor = ""
        page = 1
        details_fetched_for_member = 0

        print(f"Building archive catalog for {member_name} ({cspan_person_id})")

        while page <= max_pages_per_member:
            query = f"personid:{cspan_person_id}"
            params: dict[str, Any] = {"query": query, "sort": args.sort}

            if cursor:
                params["cursor"] = cursor

            data = client.get("/programs/search", params=params)
            if sleep_seconds:
                time.sleep(sleep_seconds)

            raw_search_path = raw_search_dir / f"{member_slug}_personid_{cspan_person_id}_page_{page}.json"
            client.save_json(data, raw_search_path)

            programs = normalize_programs_response(data)
            print(f"  Page {page}: {len(programs)} programs")

            for program in programs:
                program_id = extract_program_id(program)
                if dedupe_programs and program_id:
                    if program_id in seen_program_ids:
                        duplicate_program_ids_skipped += 1
                        continue
                    seen_program_ids.add(program_id)

                detail: dict[str, Any] | None = None
                raw_detail_path = ""
                detail_fetched = "no"

                detail_limit_reached = (
                    detail_limit_per_member is not None
                    and details_fetched_for_member >= detail_limit_per_member
                )

                if fetch_details and program_id and not detail_limit_reached:
                    try:
                        detail_data = client.get(f"/programs/{program_id}")
                        if sleep_seconds:
                            time.sleep(sleep_seconds)

                        details_fetched_for_member += 1

                        if isinstance(detail_data, dict):
                            detail = detail_data
                        else:
                            detail = {"data": detail_data}

                        raw_detail_file = raw_detail_dir / member_slug / f"{program_id}.json"
                        client.save_json(detail_data, raw_detail_file)
                        raw_detail_path = str(raw_detail_file)
                        detail_fetched = "yes"
                    except CSpanApiError as exc:
                        detail = None
                        detail_fetched = "error"
                        raw_detail_path = ""
                        program["detail_error"] = str(exc)
                elif fetch_details and program_id and detail_limit_reached:
                    detail_fetched = "skipped_limit"

                row = build_catalog_row(
                    member_name=member_name,
                    member_first=member_first,
                    member_last=member_last,
                    cspan_person_id=cspan_person_id,
                    program=program,
                    detail=detail,
                    detail_fetched=detail_fetched,
                    raw_search_json_path=str(raw_search_path),
                    raw_detail_json_path=raw_detail_path,
                )

                if program.get("detail_error"):
                    row["notes"] = f"Detail fetch error: {program.get('detail_error')}"
                elif detail_fetched == "skipped_limit":
                    row["notes"] = "Detail fetch skipped because --detail-limit-per-member was reached."

                catalog_rows.append(row)

            cursor = get_cursor(data)
            if not cursor or not programs:
                break

            page += 1

    catalog_rows.sort(
        key=lambda row: (
            row.get("member_name", ""),
            row.get("event_date", ""),
            int(row.get("priority_score", 0) or 0),
        ),
        reverse=True,
    )

    write_csv_rows(output_path, catalog_rows, CATALOG_FIELDNAMES)

    print("Archive catalog complete.")
    print(f"Usable matched members available: {len(usable_people_rows)}")
    print(f"Start member index: {start_member_index}")
    print(f"Limit members: {limit_members}")
    print(f"Members processed: {processed_members}")
    print(f"Rows: {len(catalog_rows)}")
    if dedupe_programs:
        print(f"Duplicate program IDs skipped: {duplicate_program_ids_skipped}")
    print(f"Saved catalog to: {output_path}")
    print(f"Saved raw JSON under: {raw_dir}")
    return 0


def cmd_update_index(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    run_started_at = utc_timestamp()
    source_run = run_started_at

    people_path_arg = getattr(args, "people", "")
    lookup_path_arg = getattr(args, "lookup", "")
    if people_path_arg and lookup_path_arg:
        raise ValueError("Use either --lookup or --people, not both.")
    if people_path_arg:
        args.lookup = people_path_arg
        args.lookup_source_flag = "--people"
    else:
        args.lookup_source_flag = "--lookup"

    if not getattr(args, "lookup", ""):
        raise ValueError("Provide --lookup or --people.")

    lookup_path = Path(args.lookup)
    catalog_path = Path(args.catalog)
    seen_path = Path(args.seen)
    output_new_path = Path(args.output_new)
    summary_path = update_index_summary_path(output_new_path)
    skipped_path = update_index_skipped_path(output_new_path)
    raw_dir = Path(args.raw_dir)
    raw_search_dir = raw_dir / "search"

    people_rows = load_csv_rows(lookup_path)
    existing_catalog_rows = load_optional_csv_rows(catalog_path)
    existing_seen_rows = load_optional_csv_rows(seen_path)

    all_usable_people_rows = usable_people_rows(people_rows)
    requested_people_names = parse_people_filter(getattr(args, "only_people", ""))
    if requested_people_names:
        all_usable_people_rows = filter_people_by_exact_names(
            all_people_rows=people_rows,
            usable_rows=all_usable_people_rows,
            requested_names=requested_people_names,
        )

    start_member_index = max(1, int(args.start_member_index))
    limit_members = max(0, int(args.limit_members))
    selected_people_rows = all_usable_people_rows[start_member_index - 1 :]
    if limit_members:
        selected_people_rows = selected_people_rows[:limit_members]

    max_pages_per_member = max(1, int(args.max_pages_per_member))
    sleep_seconds = max(0.0, float(args.sleep_seconds))
    since = getattr(args, "since", "").strip()
    start_page = max(1, int(getattr(args, "start_page", 1)))
    start_cursor = getattr(args, "start_cursor", "").strip()
    if start_page > 1 and not start_cursor:
        raise ValueError("--start-page greater than 1 requires --start-cursor from a suggested resume command.")

    seen_rows_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in existing_seen_rows:
        member_name = row.get("member_name", "").strip()
        program_key = row.get("program_key", "").strip() or row.get("program_id", "").strip()
        if member_name and program_key:
            seen_rows_by_key[(member_name, program_key)] = dict(row)

    for row in existing_catalog_rows:
        member_name = row.get("member_name", "").strip()
        program_key = program_key_for_row(row)
        if member_name and program_key and (member_name, program_key) not in seen_rows_by_key:
            seen_rows_by_key[(member_name, program_key)] = {
                "member_name": member_name,
                "program_id": row.get("program_id", ""),
                "program_key": program_key,
                "first_seen_at": row.get("source_run", "") or run_started_at,
                "last_seen_at": row.get("source_run", "") or run_started_at,
                "event_date": row.get("event_date", ""),
                "cspan_url": row.get("cspan_url", ""),
                "source_run": row.get("source_run", "") or "catalog_seed",
            }

    new_rows: list[dict[str, Any]] = []
    skipped_rows: list[dict[str, Any]] = []
    person_summary_rows: list[dict[str, Any]] = []
    members_processed = 0
    rows_seen = 0
    new_row_count = 0
    existing_row_count = 0
    skipped_row_count = 0
    skip_reason_totals: dict[str, int] = {}
    api_errors = 0
    rate_limited = "no"
    notes: list[str] = []
    last_started_member_index = ""
    last_started_member_name = ""
    last_completed_member_index = ""
    last_completed_member_name = ""
    failed_member_index = ""
    failed_member_name = ""
    failed_reason = ""
    suggested_resume_start_member_index = ""
    suggested_resume_command = ""

    for selected_offset, person_row in enumerate(selected_people_rows):
        members_processed += 1
        current_member_index = start_member_index + selected_offset

        cspan_person_id = person_row.get("cspan_person_id", "").strip()
        member_name = person_row.get("display_name", "") or person_row.get("cspan_name", "")
        member_first = person_row.get("input_first", "") or person_row.get("cspan_first_name", "")
        member_last = person_row.get("input_last", "") or person_row.get("cspan_last_name", "")
        last_started_member_index = str(current_member_index)
        last_started_member_name = member_name

        member_slug = slugify(member_name)
        if selected_offset == 0:
            cursor = start_cursor
            page = start_page
        else:
            cursor = ""
            page = 1
        member_failed = False
        member_new_rows = 0
        member_existing_rows = 0
        member_programs_fetched = 0
        member_skipped_rows = 0
        member_skip_reason_counts: dict[str, int] = {}
        member_api_errors = 0
        empty_page_reached = "no"
        last_page_fetched = ""
        last_page_program_count = ""
        crawl_stop_reason = "completed"
        pages_fetched_for_member = 0

        print(f"Updating index for {member_name} ({cspan_person_id})")

        while pages_fetched_for_member < max_pages_per_member:
            query = f"personid:{cspan_person_id}"
            params: dict[str, Any] = {"query": query, "sort": args.sort}
            if cursor:
                params["cursor"] = cursor

            try:
                data = client.get("/programs/search", params=params)
            except CSpanApiError as exc:
                api_errors += 1
                member_api_errors += 1
                error_note = f"{member_name} page {page}: {exc}"
                notes.append(error_note.replace("\n", " "))
                member_failed = True
                crawl_stop_reason = "rate_limited" if is_rate_limit_error(exc) else "api_error"
                failed_member_index = str(current_member_index)
                failed_member_name = member_name
                failed_reason = "429 Too Many Requests" if is_rate_limit_error(exc) else str(exc).replace("\n", " ")
                suggested_resume_start_member_index = failed_member_index
                suggested_resume_command = build_update_index_resume_command(
                    args=args,
                    resume_start_member_index=current_member_index,
                    failed_because_rate_limit=is_rate_limit_error(exc),
                    selected_member_count=len(selected_people_rows),
                    failed_selected_offset=selected_offset,
                    failed_page=page,
                    failed_cursor=cursor,
                    selected_people_rows=selected_people_rows,
                )
                if is_rate_limit_error(exc):
                    rate_limited = "yes"
                    print("Rate limit hit; stopping update-index cleanly.")
                    print(f"Rate limited at member index {current_member_index}: {member_name}")
                    print(f"Suggested resume start index: {current_member_index}")
                    print(f"Suggested resume start page: {page}")
                    print("Suggested resume command:")
                    print(suggested_resume_command)
                    break

                print(f"  API error on page {page}; continuing to next member.")
                break

            raw_search_path = raw_search_dir / f"{member_slug}_personid_{cspan_person_id}_page_{page}.json"
            client.save_json(data, raw_search_path)

            programs = normalize_programs_response(data)
            rows_seen += len(programs)
            member_programs_fetched += len(programs)
            last_page_fetched = str(page)
            last_page_program_count = str(len(programs))
            pages_fetched_for_member += 1
            print(f"  Page {page}: {len(programs)} programs")

            page_has_row_on_or_after_since = False
            for program in programs:
                try:
                    row = build_catalog_row(
                        member_name=member_name,
                        member_first=member_first,
                        member_last=member_last,
                        cspan_person_id=cspan_person_id,
                        program=program,
                        detail=None,
                        detail_fetched="no",
                        raw_search_json_path=str(raw_search_path),
                        raw_detail_json_path="",
                    )
                except Exception as exc:
                    skip_reason = "row_build_failed"
                    skipped_row_count += 1
                    member_skipped_rows += 1
                    increment_count(skip_reason_totals, skip_reason)
                    increment_count(member_skip_reason_counts, skip_reason)
                    skipped_rows.append(
                        build_skipped_program_row(
                            batch=output_new_path.stem,
                            dry_run="yes" if args.dry_run else "no",
                            person_name=member_name,
                            cspan_person_id=cspan_person_id,
                            program=program,
                            catalog_row=None,
                            skip_reason=skip_reason,
                            notes=str(exc).replace("\n", " "),
                        )
                    )
                    continue

                row["source_run"] = source_run
                event_date = row.get("event_date", "")[:10]
                if since and event_date:
                    if event_date < since:
                        skip_reason = "before_since_date"
                        skipped_row_count += 1
                        member_skipped_rows += 1
                        increment_count(skip_reason_totals, skip_reason)
                        increment_count(member_skip_reason_counts, skip_reason)
                        skipped_rows.append(
                            build_skipped_program_row(
                                batch=output_new_path.stem,
                                dry_run="yes" if args.dry_run else "no",
                                person_name=member_name,
                                cspan_person_id=cspan_person_id,
                                program=program,
                                catalog_row=row,
                                skip_reason=skip_reason,
                                notes=f"Program date {event_date} is before --since {since}.",
                            )
                        )
                        continue
                    page_has_row_on_or_after_since = True
                elif since and not event_date:
                    page_has_row_on_or_after_since = True

                key = member_program_key(row)
                if key in seen_rows_by_key:
                    existing_row_count += 1
                    member_existing_rows += 1
                    seen_row = seen_rows_by_key[key]
                    seen_row["last_seen_at"] = run_started_at
                    seen_row["event_date"] = row.get("event_date", "")
                    seen_row["cspan_url"] = row.get("cspan_url", "")
                    continue

                new_row_count += 1
                member_new_rows += 1
                new_rows.append(row)
                seen_rows_by_key[key] = {
                    "member_name": row.get("member_name", ""),
                    "program_id": row.get("program_id", ""),
                    "program_key": key[1],
                    "first_seen_at": run_started_at,
                    "last_seen_at": run_started_at,
                    "event_date": row.get("event_date", ""),
                    "cspan_url": row.get("cspan_url", ""),
                    "source_run": source_run,
                }

            cursor = get_cursor(data)
            if not programs:
                empty_page_reached = "yes"
                crawl_stop_reason = "empty_page"
                break
            if not cursor:
                crawl_stop_reason = "completed"
                break
            if since and programs and not page_has_row_on_or_after_since:
                crawl_stop_reason = "reached_since_floor"
                break

            page += 1

        if (
            not member_failed
            and crawl_stop_reason == "completed"
            and pages_fetched_for_member >= max_pages_per_member
            and cursor
        ):
            crawl_stop_reason = "max_pages_reached"
            continue_start_page = int(last_page_fetched or page) + 1
            suggested_continue_command = build_update_index_resume_command(
                args=args,
                resume_start_member_index=current_member_index,
                failed_because_rate_limit=False,
                selected_member_count=len(selected_people_rows),
                failed_selected_offset=selected_offset,
                failed_page=continue_start_page,
                failed_cursor=cursor,
                selected_people_rows=selected_people_rows,
                output_suffix="_continue",
            )
            print(f"  Suggested continue start index: {current_member_index}")
            print(f"  Suggested continue start page: {continue_start_page}")
            print("  Suggested continue command:")
            print(f"  {suggested_continue_command}")
        elif (
            not member_failed
            and crawl_stop_reason == "completed"
            and pages_fetched_for_member >= max_pages_per_member
            and int(last_page_program_count or 0) > 0
            and not cursor
        ):
            print("  Page budget reached, but no next cursor was available; not printing a continue command.")

        if not member_failed:
            last_completed_member_index = str(current_member_index)
            last_completed_member_name = member_name
        person_summary_rows.append(
            {
                "person_name": member_name,
                "cspan_person_id": cspan_person_id,
                "programs_fetched": member_programs_fetched,
                "added_rows": member_new_rows,
                "already_seen": member_existing_rows,
                "skipped": member_skipped_rows,
                "skip_reasons_summary": counts_summary(member_skip_reason_counts),
                "empty_page_reached": empty_page_reached,
                "last_page_fetched": last_page_fetched,
                "last_page_program_count": last_page_program_count,
                "crawl_stop_reason": crawl_stop_reason,
                "api_errors": member_api_errors,
            }
        )
        print(f"  Added rows: {member_new_rows}; already seen: {member_existing_rows}; skipped: {member_skipped_rows}")
        if member_skip_reason_counts:
            print("  Skip reasons:")
            for reason, count in sorted(member_skip_reason_counts.items()):
                print(f"    {reason}: {count}")
        if member_api_errors:
            print(f"  API errors: {member_api_errors}")
        print(f"  Empty page reached: {empty_page_reached}")
        print(f"  Last page fetched: {last_page_fetched or 'n/a'}")
        print(f"  Stop reason: {crawl_stop_reason}")

        if rate_limited == "yes":
            break

        if sleep_seconds:
            time.sleep(sleep_seconds)

    catalog_rows_to_write = [dict(row) for row in existing_catalog_rows] + new_rows
    seen_rows_to_write = list(seen_rows_by_key.values())
    before_catalog_rows = len(existing_catalog_rows)
    after_catalog_rows = len(catalog_rows_to_write)
    duplicate_groups_after = [
        group_key
        for group_key, count in duplicate_member_program_counts(catalog_rows_to_write).items()
        if count > 1
    ]

    write_csv_rows(output_new_path, new_rows, INDEX_CATALOG_FIELDNAMES)
    write_csv_rows(skipped_path, skipped_rows, UPDATE_INDEX_SKIPPED_FIELDNAMES)
    if args.dry_run:
        notes.append("Dry run: catalog and seen ledger were not written.")
    else:
        write_csv_rows(catalog_path, catalog_rows_to_write, INDEX_CATALOG_FIELDNAMES)
        write_csv_rows(seen_path, seen_rows_to_write, SEEN_PROGRAM_FIELDNAMES)

    run_finished_at = utc_timestamp()
    run_summary_base = {
        "run_started_at": run_started_at,
        "run_finished_at": run_finished_at,
        "lookup_path": str(lookup_path),
        "catalog_path": str(catalog_path),
        "seen_path": str(seen_path),
        "dry_run": "yes" if args.dry_run else "no",
        "members_available": len(all_usable_people_rows),
        "members_processed": members_processed,
        "rows_seen": rows_seen,
        "new_rows": new_row_count,
        "existing_rows": existing_row_count,
        "api_errors": api_errors,
        "rate_limited": rate_limited,
        "last_started_member_index": last_started_member_index,
        "last_started_member_name": last_started_member_name,
        "last_completed_member_index": last_completed_member_index,
        "last_completed_member_name": last_completed_member_name,
        "failed_member_index": failed_member_index,
        "failed_member_name": failed_member_name,
        "failed_reason": failed_reason,
        "suggested_resume_start_member_index": suggested_resume_start_member_index,
        "suggested_resume_command": suggested_resume_command,
        "notes": " | ".join(notes),
    }
    summary_rows = [
        {
            **run_summary_base,
            "person_name": "(run total)",
            "cspan_person_id": "",
            "programs_fetched": rows_seen,
            "added_rows": new_row_count,
            "already_seen": existing_row_count,
            "skipped": skipped_row_count,
            "skip_reasons_summary": counts_summary(skip_reason_totals),
            "empty_page_reached": "",
            "last_page_fetched": "",
            "last_page_program_count": "",
            "crawl_stop_reason": "",
        }
    ]
    for person_summary_row in person_summary_rows:
        summary_rows.append({**run_summary_base, **person_summary_row, "notes": ""})
    write_csv_rows(summary_path, summary_rows, UPDATE_INDEX_SUMMARY_FIELDNAMES)

    print("Index update complete.")
    print(f"Dry run: {'yes' if args.dry_run else 'no'}")
    print(f"Usable matched members available: {len(all_usable_people_rows)}")
    if requested_people_names:
        print(f"Only people: {', '.join(requested_people_names)}")
    print(f"Start member index: {start_member_index}")
    print(f"Start page: {start_page}")
    print(f"Limit members: {limit_members}")
    print(f"Members processed: {members_processed}")
    print(f"Rows seen/fetched: {rows_seen}")
    print(f"Catalog rows before: {before_catalog_rows}")
    print(f"Catalog rows after: {after_catalog_rows}")
    print(f"New rows: {new_row_count}")
    print(f"Existing rows: {existing_row_count}")
    print(f"Skipped rows: {skipped_row_count}")
    print(f"Skip reasons total: {counts_summary(skip_reason_totals) or 'none'}")
    print(f"Duplicate member/person + program groups after run: {len(duplicate_groups_after)}")
    print(f"API errors: {api_errors}")
    print(f"Rate limited: {rate_limited}")
    print(f"Last started member index: {last_started_member_index}")
    print(f"Last started member name: {last_started_member_name}")
    print(f"Last completed member index: {last_completed_member_index}")
    print(f"Last completed member name: {last_completed_member_name}")
    if failed_member_index:
        print(f"Failed member index: {failed_member_index}")
        print(f"Failed member name: {failed_member_name}")
        print(f"Failed reason: {failed_reason}")
        print(f"Suggested resume start index: {suggested_resume_start_member_index}")
        if "--start-page" in suggested_resume_command:
            suggested_page_match = re.search(r"--start-page\s+(\d+)", suggested_resume_command)
            if suggested_page_match:
                print(f"Suggested resume start page: {suggested_page_match.group(1)}")
        print("Suggested resume command:")
        print(suggested_resume_command)
    if not args.dry_run:
        print(f"Catalog rows written: {len(catalog_rows_to_write)}")
        print(f"Seen ledger rows written: {len(seen_rows_to_write)}")
    print(f"Saved new rows to: {output_new_path}")
    print(f"Saved skipped rows to: {skipped_path}")
    print(f"Saved summary to: {summary_path}")
    print(f"Saved raw JSON under: {raw_dir}")
    return 0


def cmd_merge_catalogs(args: argparse.Namespace) -> int:
    catalog_rows: list[dict[str, Any]] = []
    seen_program_ids: set[str] = set()
    duplicate_program_ids_skipped = 0
    total_input_rows = 0

    for input_value in args.input:
        rows = load_csv_rows(Path(input_value))
        total_input_rows += len(rows)

        for row in rows:
            program_id = row.get("program_id", "").strip()
            if args.dedupe_programs and program_id:
                if program_id in seen_program_ids:
                    duplicate_program_ids_skipped += 1
                    continue
                seen_program_ids.add(program_id)

            catalog_rows.append(row)

    write_csv_rows(Path(args.output), catalog_rows, CATALOG_FIELDNAMES)

    print("Catalog merge complete.")
    print(f"Input files count: {len(args.input)}")
    print(f"Total input rows: {total_input_rows}")
    print(f"Output rows: {len(catalog_rows)}")
    print(f"Duplicate program IDs skipped: {duplicate_program_ids_skipped}")
    print(f"Saved merged catalog to: {args.output}")
    return 0


def cmd_priority_catalog(args: argparse.Namespace) -> int:
    catalog_rows = load_csv_rows(Path(args.catalog))
    priority_rows = load_csv_rows(Path(args.priorities))
    keyword_rows = load_csv_rows(Path(args.keywords))

    priorities_by_member: dict[str, list[str]] = {}
    for row in priority_rows:
        display_name = row.get("display_name", "").strip()
        priority = row.get("priority", "").strip()
        if display_name and priority:
            priorities_by_member.setdefault(display_name, []).append(priority)

    terms_by_priority: dict[str, list[str]] = {}
    source_by_priority: dict[str, str] = {}
    for row in keyword_rows:
        priority = row.get("priority", "").strip()
        if not priority:
            continue

        terms = parse_keyword_terms(row.get("keywords", ""))
        if terms:
            terms_by_priority[priority] = terms
            source_by_priority[priority] = "keywords"
        else:
            terms_by_priority[priority] = [priority]
            source_by_priority[priority] = "priority_phrase"

    matched_rows: list[dict[str, Any]] = []
    matched_member_priorities: set[tuple[str, str]] = set()
    members_with_catalog_rows = {
        row.get("member_name", "").strip()
        for row in catalog_rows
        if row.get("member_name", "").strip()
    }

    for catalog_row in catalog_rows:
        member_name = catalog_row.get("member_name", "").strip()
        member_priorities = priorities_by_member.get(member_name, [])
        if not member_priorities:
            continue

        searchable_text = build_priority_search_text(catalog_row)
        for priority in member_priorities:
            terms = terms_by_priority.get(priority, [priority])
            matched_terms = [term for term in terms if priority_term_matches(term, searchable_text)]
            if not matched_terms:
                continue

            strong_match_count = sum(1 for term in matched_terms if term.lower() not in BROAD_PRIORITY_TERMS)
            broad_match_count = len(matched_terms) - strong_match_count
            match_strength = "strong" if strong_match_count >= 1 else "broad_only"
            review_flag = "" if match_strength == "strong" else "REVIEW_BROAD_ONLY"
            base_priority_score = int(catalog_row.get("priority_score", 0) or 0)
            scored_priority_score = base_priority_score + (strong_match_count * 2) + broad_match_count

            matched_member_priorities.add((member_name, priority))
            matched_rows.append(
                {
                    "member_name": member_name,
                    "matrix_priority": priority,
                    "matched_keywords": "; ".join(matched_terms),
                    "match_source": source_by_priority.get(priority, "priority_phrase"),
                    "match_strength": match_strength,
                    "strong_match_count": strong_match_count,
                    "broad_match_count": broad_match_count,
                    "review_flag": review_flag,
                    "event_title": catalog_row.get("event_title", ""),
                    "event_date": catalog_row.get("event_date", ""),
                    "cspan_url": catalog_row.get("cspan_url", ""),
                    "program_id": catalog_row.get("program_id", ""),
                    "source_type": catalog_row.get("source_type", ""),
                    "event_type": catalog_row.get("event_type", ""),
                    "content_bucket": catalog_row.get("content_bucket", ""),
                    "youtube_use": catalog_row.get("youtube_use", ""),
                    "priority_score": scored_priority_score,
                    "detail_fetched": catalog_row.get("detail_fetched", ""),
                    "description": catalog_row.get("description", ""),
                }
            )

    unmatched_rows: list[dict[str, Any]] = []
    for member_name, priorities in priorities_by_member.items():
        for priority in priorities:
            if member_name not in members_with_catalog_rows:
                notes = "No catalog rows for member."
            elif (member_name, priority) not in matched_member_priorities:
                notes = "No matching catalog rows."
            else:
                continue

            unmatched_rows.append(
                {
                    "member_name": member_name,
                    "matrix_priority": priority,
                    "notes": notes,
                }
            )

    matched_rows.sort(key=lambda row: row.get("event_date", ""), reverse=True)
    matched_rows.sort(key=lambda row: -int(row.get("priority_score", 0) or 0))
    matched_rows.sort(key=lambda row: get_matrix_priority(row))
    matched_rows.sort(key=lambda row: row.get("member_name", ""))
    matched_rows.sort(key=lambda row: row.get("review_flag", ""))

    output_path = Path(args.output)
    unmatched_output_path = output_path.with_name(f"{output_path.stem}_unmatched_priorities{output_path.suffix}")
    write_csv_rows(output_path, matched_rows, PRIORITY_CATALOG_FIELDNAMES)
    write_csv_rows(unmatched_output_path, unmatched_rows, UNMATCHED_PRIORITY_FIELDNAMES)

    unique_priorities = {row.get("priority", "").strip() for row in priority_rows if row.get("priority", "").strip()}

    print("Priority catalog complete.")
    print(f"Catalog rows read: {len(catalog_rows)}")
    print(f"Members with catalog rows: {len(members_with_catalog_rows)}")
    print(f"Priority rows read: {len(priority_rows)}")
    print(f"Unique priorities read: {len(unique_priorities)}")
    print(f"Matched rows: {len(matched_rows)}")
    print(f"Members with at least one priority match: {len({row.get('member_name', '') for row in matched_rows})}")
    print(f"Unmatched member-priority pairs: {len(unmatched_rows)}")
    print(f"Saved priority catalog to: {output_path}")
    print(f"Saved unmatched priorities to: {unmatched_output_path}")
    return 0


def cmd_lead_export(args: argparse.Namespace) -> int:
    input_rows = load_csv_rows(Path(args.input))
    per_member = max(1, int(args.per_member))
    filtered_rows = []
    seen_exact_rows: set[tuple[str, str, str]] = set()
    duplicate_rows_skipped = 0

    for row in input_rows:
        if args.strong_only and row.get("review_flag", "") == "REVIEW_BROAD_ONLY":
            continue

        member_name = row.get("member_name", "")
        program_id = row.get("program_id", "")
        priority = get_matrix_priority(row)
        exact_key = (member_name, program_id, priority)
        if program_id and exact_key in seen_exact_rows:
            duplicate_rows_skipped += 1
            continue
        if program_id:
            seen_exact_rows.add(exact_key)

        filtered_rows.append(row)

    rows_before_dedupe = len(filtered_rows)
    rows_after_dedupe = rows_before_dedupe
    member_program_rows_skipped = 0
    if args.dedupe_programs_per_member:
        best_rows_by_key: dict[tuple[str, str, str], tuple[dict[str, Any], int]] = {}
        for index, row in enumerate(filtered_rows):
            key = lead_dedupe_key(row, index)
            current = best_rows_by_key.get(key)
            if current is None:
                best_rows_by_key[key] = (row, index)
                continue

            current_row, current_index = current
            if lead_dedupe_score(row, index) > lead_dedupe_score(current_row, current_index):
                best_rows_by_key[key] = (row, index)

        filtered_rows = [row for row, _index in sorted(best_rows_by_key.values(), key=lambda item: item[1])]
        rows_after_dedupe = len(filtered_rows)
        member_program_rows_skipped = rows_before_dedupe - rows_after_dedupe

    filtered_rows.sort(key=lambda row: row.get("event_date", ""), reverse=True)
    filtered_rows.sort(key=lambda row: -int(row.get("priority_score", 0) or 0))
    filtered_rows.sort(key=lambda row: row.get("member_name", ""))

    output_rows: list[dict[str, Any]] = []
    member_counts: dict[str, int] = {}
    for row in filtered_rows:
        member_name = row.get("member_name", "")
        current_count = member_counts.get(member_name, 0)
        if current_count >= per_member:
            continue

        review_rank = current_count + 1
        member_counts[member_name] = review_rank
        output_rows.append(
            {
                "review_rank": review_rank,
                "member_name": member_name,
                "matrix_priority": get_matrix_priority(row),
                "priority_score": row.get("priority_score", ""),
                "match_strength": row.get("match_strength", ""),
                "strong_match_count": row.get("strong_match_count", ""),
                "broad_match_count": row.get("broad_match_count", ""),
                "matched_keywords": get_matched_keywords(row),
                "event_title": row.get("event_title", ""),
                "event_date": row.get("event_date", ""),
                "cspan_url": row.get("cspan_url", ""),
                "program_id": row.get("program_id", ""),
                "source_type": row.get("source_type", ""),
                "event_type": row.get("event_type", ""),
                "content_bucket": row.get("content_bucket", ""),
                "youtube_use": row.get("youtube_use", ""),
                "detail_fetched": row.get("detail_fetched", ""),
                "description": row.get("description", ""),
                "review_status": "",
                "review_notes": "",
            }
        )

    write_csv_rows(Path(args.output), output_rows, LEAD_EXPORT_FIELDNAMES)

    print("Lead export complete.")
    print(f"Input rows: {len(input_rows)}")
    print(f"Rows after filters: {len(filtered_rows)}")
    print(f"Exact duplicate rows skipped: {duplicate_rows_skipped}")
    if args.dedupe_programs_per_member:
        print(f"Rows before dedupe: {rows_before_dedupe}")
        print(f"Rows after dedupe: {rows_after_dedupe}")
        print(f"Duplicate member-program rows skipped: {member_program_rows_skipped}")
    print(f"Per member limit: {per_member}")
    print(f"Output rows: {len(output_rows)}")
    print(f"Members included: {len(member_counts)}")
    print(f"Saved lead export to: {args.output}")
    return 0


def cmd_hydrate_leads(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    input_rows = load_csv_rows(Path(args.input))
    output_path = Path(args.output)
    raw_dir = Path(args.raw_dir)
    sleep_seconds = max(0.0, float(args.sleep_seconds))
    max_detail_calls = args.max_detail_calls
    if max_detail_calls is not None:
        max_detail_calls = max(0, int(max_detail_calls))

    rows_already_detailed = sum(1 for row in input_rows if row.get("detail_fetched", "") == "yes")
    program_ids_needing_detail = {
        row.get("program_id", "").strip()
        for row in input_rows
        if row.get("program_id", "").strip()
        and (args.force or row.get("detail_fetched", "") != "yes")
    }

    detail_cache: dict[str, dict[str, Any]] = {}
    output_rows: list[dict[str, Any]] = []
    detail_calls_attempted = 0
    detail_calls_succeeded = 0
    detail_calls_failed = 0

    for row in input_rows:
        program_id = row.get("program_id", "").strip()
        if not program_id:
            updated_row = dict(row)
            updated_row["detail_fetch_status"] = "skipped_no_program_id"
            updated_row["detail_fetch_error"] = ""
            output_rows.append(updated_row)
            continue

        if row.get("detail_fetched", "") == "yes" and not args.force:
            updated_row = dict(row)
            updated_row["detail_fetch_status"] = "already_detail"
            updated_row["detail_fetch_error"] = ""
            output_rows.append(updated_row)
            continue

        cached_detail = detail_cache.get(program_id)
        cache_hit = cached_detail is not None
        if cached_detail is None:
            if max_detail_calls is not None and detail_calls_attempted >= max_detail_calls:
                updated_row = dict(row)
                updated_row["detail_fetch_status"] = "max_detail_calls_reached"
                updated_row["detail_fetch_error"] = ""
                output_rows.append(updated_row)
                continue

            detail_calls_attempted += 1
            raw_detail_path = raw_dir / f"{program_id}.json"
            print(f"Fetching detail for program {program_id}")
            try:
                detail_data = client.get(f"/programs/{program_id}")
                if sleep_seconds:
                    time.sleep(sleep_seconds)

                client.save_json(detail_data, raw_detail_path)
                detail = detail_data if isinstance(detail_data, dict) else {"data": detail_data}
                cached_detail = {
                    "detail": detail,
                    "raw_detail_json_path": str(raw_detail_path),
                    "status": "fetched",
                    "error": "",
                }
                detail_cache[program_id] = cached_detail
                detail_calls_succeeded += 1
            except CSpanApiError as exc:
                if sleep_seconds:
                    time.sleep(sleep_seconds)

                cached_detail = {
                    "detail": None,
                    "raw_detail_json_path": "",
                    "status": "error",
                    "error": str(exc),
                }
                detail_cache[program_id] = cached_detail
                detail_calls_failed += 1

        detail = cached_detail.get("detail")
        if detail is None:
            updated_row = dict(row)
            updated_row["detail_fetch_status"] = cached_detail.get("status", "error")
            updated_row["detail_fetch_error"] = cached_detail.get("error", "")
            output_rows.append(updated_row)
            continue

        program = program_from_lead_row(row)
        catalog_row = build_catalog_row(
            member_name=row.get("member_name", ""),
            member_first="",
            member_last="",
            cspan_person_id="",
            program=program,
            detail=detail,
            detail_fetched="yes",
            raw_search_json_path="",
            raw_detail_json_path=cached_detail.get("raw_detail_json_path", ""),
        )

        status = "reused" if cache_hit and cached_detail.get("status") == "fetched" else cached_detail.get("status", "fetched")

        output_rows.append(
            merge_detail_into_lead_row(
                row,
                catalog_row,
                detail_fetch_status=status,
                detail_fetch_error="",
            )
        )

    write_csv_rows(output_path, output_rows, HYDRATED_LEAD_FIELDNAMES)

    print("Lead hydration complete.")
    print(f"Input rows: {len(input_rows)}")
    print(f"Rows already detail_fetched=yes: {rows_already_detailed}")
    print(f"Unique program IDs needing detail: {len(program_ids_needing_detail)}")
    print(f"Detail calls attempted: {detail_calls_attempted}")
    print(f"Detail calls succeeded: {detail_calls_succeeded}")
    print(f"Detail calls failed: {detail_calls_failed}")
    print(f"Output rows: {len(output_rows)}")
    print(f"Saved hydrated leads to: {output_path}")
    print(f"Saved raw detail JSON under: {raw_dir}")
    return 0


def cmd_audit_member(args: argparse.Namespace) -> int:
    member_name = args.member.strip()
    if not member_name:
        raise ValueError("--member cannot be blank.")

    since = args.since.strip()
    lookup_rows = load_optional_csv_rows(Path(args.lookup))
    catalog_rows = load_optional_csv_rows(Path(args.catalog))
    seen_rows = load_optional_csv_rows(Path(args.seen))
    priority_rows = load_optional_csv_rows(Path(args.priority_catalog))
    review_rows = load_optional_csv_rows(Path(args.review_csv))
    reviewed_rows = load_optional_csv_rows(Path(args.reviewed_csv)) if args.reviewed_csv else []

    lookup_match = next(
        (
            row
            for row in lookup_rows
            if row.get("display_name", "").strip().lower() == member_name.lower()
            or row.get("cspan_name", "").strip().lower() == member_name.lower()
        ),
        {},
    )
    cspan_person_id = lookup_match.get("cspan_person_id", "")
    search_terms = [member_name]
    if cspan_person_id:
        search_terms.append(f"personid:{cspan_person_id}")

    catalog_matches = [
        row for row in catalog_rows
        if row_matches_member(row, member_name) and row_is_since(row, since)
    ]
    seen_matches = [
        row for row in seen_rows
        if row_matches_member(row, member_name) and row_is_since(row, since)
    ]
    priority_matches = [
        row for row in priority_rows
        if row_matches_member(row, member_name) and row_is_since(row, since)
    ]
    review_matches = [
        row for row in review_rows
        if row_matches_member(row, member_name) and row_is_since(row, since)
    ]
    reviewed_matches = [
        row for row in reviewed_rows
        if row_matches_member(row, member_name) and row_is_since(row, since)
    ]

    duplicate_groups = [
        group_key
        for group_key, count in duplicate_member_program_counts(catalog_matches).items()
        if count > 1
    ]

    priority_program_keys = {member_program_key(row) for row in priority_matches}
    review_program_keys = {member_program_key(row) for row in review_matches}
    catalog_program_keys = {member_program_key(row) for row in catalog_matches}
    excluded_by_priority = len(catalog_program_keys - priority_program_keys)
    excluded_by_review_export = len(catalog_program_keys - review_program_keys)

    print("Member audit")
    print(f"Member name: {member_name}")
    print(f"C-SPAN person ID from lookup: {cspan_person_id}")
    print(f"Search terms used locally: {', '.join(search_terms)}")
    print(f"Date range: {since or 'all'} through current local CSV contents")
    print(f"Master catalog: {args.catalog}")
    print(f"Current review CSV: {args.review_csv}")
    if args.reviewed_csv:
        print(f"Reviewed CSV: {args.reviewed_csv}")
    print("")
    print(f"Count in master catalog: {len(catalog_matches)}")
    print(f"Count in seen ledger: {len(seen_matches)}")
    print(f"Count in priority catalog: {len(priority_matches)}")
    print(f"Count in current top review CSV: {len(review_matches)}")
    if args.reviewed_csv:
        print(f"Count in reviewed CSV: {len(reviewed_matches)}")
    else:
        print("Count in reviewed CSV: not checked")
    print(f"Count excluded by seen ledger: not applicable to master catalog; seen rows for member/date = {len(seen_matches)}")
    print(f"Count excluded by priority filters: {excluded_by_priority}")
    print(f"Count excluded by lead-export/dedupe/review narrowing: {excluded_by_review_export}")
    print(f"Duplicate member_name + program_id groups in master catalog matches: {len(duplicate_groups)}")
    print("")
    print("Top matching rows:")

    sorted_matches = sorted(
        catalog_matches,
        key=lambda row: row_event_date(row),
        reverse=True,
    )
    for index, row in enumerate(sorted_matches[:25], start=1):
        print(
            f"{index:>2}. {row_event_date(row)[:10]} | "
            f"{row_title(row)} | {row_url_value(row)} | {args.catalog}"
        )

    return 0


def cmd_audit_member_topic(args: argparse.Namespace) -> int:
    member_name = args.member.strip()
    topic = args.topic.strip()
    since = args.since.strip()
    if not member_name:
        raise ValueError("--member cannot be blank.")
    if not topic:
        raise ValueError("--topic cannot be blank.")

    catalog_rows = load_optional_csv_rows(Path(args.catalog))
    aliases = topic_aliases(topic)
    topic_only_rows = [
        row for row in catalog_rows
        if row_is_since(row, since) and row_matches_any_term(row, aliases)
    ]
    member_rows = [
        row for row in catalog_rows
        if row_is_since(row, since) and row_matches_member(row, member_name)
    ]
    exact_topic_rows = [
        row for row in member_rows
        if row_matches_exact_topic(row, topic)
    ]
    alias_topic_rows = [
        row for row in member_rows
        if row_matches_any_term(row, aliases)
    ]
    member_topic_missing_rows = [
        row for row in member_rows
        if not row_matches_any_term(row, aliases)
    ]
    topic_without_member_rows = [
        row for row in topic_only_rows
        if not row_matches_member(row, member_name)
    ]

    print("Member-topic audit")
    print(f"Member: {member_name}")
    print(f"Topic: {topic}")
    print(f"Topic aliases used: {', '.join(aliases)}")
    print(f"Date range: {since or 'all'} through current local CSV contents")
    print(f"Catalog: {args.catalog}")
    print("")
    print(f"Matching rows in master catalog: {len(alias_topic_rows)}")
    print(f"Matching rows by exact topic label: {len(exact_topic_rows)}")
    print(f"Matching rows by aliases: {len(alias_topic_rows)}")
    print(f"Matching rows where member is associated but topic is missing: {len(member_topic_missing_rows)}")
    print(f"Matching rows where topic appears but member is not associated: {len(topic_without_member_rows)}")
    print("")
    print("Top candidate rows:")

    sorted_candidates = sorted(alias_topic_rows, key=lambda row: row_event_date(row), reverse=True)
    for index, row in enumerate(sorted_candidates[:25], start=1):
        description = row.get("description", "").replace("\n", " ")
        print(
            f"{index:>2}. {row_event_date(row)[:10]} | {row_title(row)} | "
            f"{row_url_value(row)} | {description[:220]}"
        )

    return 0


def cmd_audit_cspan_person_ids(args: argparse.Namespace) -> int:
    settings = load_settings()
    client = CSpanClient(settings)

    all_tracked_people = load_tracked_people(Path(args.tracked_people))
    requested_people_names = parse_people_filter(getattr(args, "only_people", ""))
    tracked_people_by_name = {person.get("name", ""): person for person in all_tracked_people}
    tracked_people = [
        tracked_people_by_name[name]
        for name in requested_people_names
        if name in tracked_people_by_name
    ] if requested_people_names else all_tracked_people
    output_path = Path(args.output)
    raw_output_path = Path(args.raw_output)
    sleep_seconds = max(0.0, float(args.sleep_seconds))
    limit_missing = max(0, int(args.limit_missing))

    audit_rows: list[dict[str, Any]] = []
    raw_results: dict[str, Any] = {}
    missing_reviewed = 0
    stopped_after_rate_limit = False

    for missing_name in [name for name in requested_people_names if name not in tracked_people_by_name]:
        print(f"Skipping requested person not found in tracked_people.csv: {missing_name}")
        audit_rows.append(
            {
                "name": missing_name,
                "group": "",
                "role": "",
                "current_cspan_person_id": "",
                "lookup_status": "missing_requested_name",
                "candidate_cspan_person_id": "",
                "candidate_cspan_name": "",
                "candidate_cspan_title": "",
                "confidence": "not_checked",
                "evidence_url": "",
                "evidence_text": "",
                "notes": "Requested name was not found in tracked_people.csv.",
            }
        )

    for person in tracked_people:
        name = person.get("name", "")
        current_id = person.get("cspan_person_id", "").strip()
        base_row = {
            "name": name,
            "group": person.get("group", ""),
            "role": person.get("role", ""),
            "current_cspan_person_id": current_id,
            "lookup_status": "existing_id" if current_id else "",
            "candidate_cspan_person_id": "",
            "candidate_cspan_name": "",
            "candidate_cspan_title": "",
            "confidence": "existing" if current_id else "",
            "evidence_url": "",
            "evidence_text": "",
            "notes": "Existing C-SPAN person ID preserved." if current_id else "",
        }

        if current_id and not args.all:
            audit_rows.append(base_row)
            continue

        if stopped_after_rate_limit:
            base_row["lookup_status"] = "skipped_after_rate_limit"
            base_row["confidence"] = "not_checked"
            base_row["notes"] = "Skipped because C-SPAN returned 429 earlier in this audit run."
            audit_rows.append(base_row)
            continue

        if not current_id:
            if limit_missing and missing_reviewed >= limit_missing:
                base_row["lookup_status"] = "skipped_limit"
                base_row["confidence"] = "not_checked"
                base_row["notes"] = "--limit-missing reached before lookup."
                audit_rows.append(base_row)
                continue
            missing_reviewed += 1

        print(f"Auditing C-SPAN person ID: {name}")
        candidate_groups: list[tuple[str, list[dict[str, Any]]]] = []
        person_raw_results: dict[str, Any] = {}
        for query_term in cspan_person_query_terms(person):
            try:
                data = client.get("/people", params={"query": query_term})
            except CSpanApiError as exc:
                base_row["lookup_status"] = "api_error"
                base_row["confidence"] = "not_checked"
                base_row["notes"] = str(exc).replace("\n", " ")
                audit_rows.append(base_row)
                if is_rate_limit_error(exc):
                    stopped_after_rate_limit = True
                    print(f"Rate limited while auditing C-SPAN person IDs at: {name}")
                    print("Stopping remaining lookups cleanly; rerun later with a larger --sleep-seconds.")
                break

            person_raw_results[query_term] = data
            candidates = normalize_people_response(data)
            candidate_groups.append((query_term, candidates))
            candidate, confidence, _notes = best_cspan_person_candidate(person, candidates)
            if confidence == "high":
                break
            if sleep_seconds:
                time.sleep(sleep_seconds)

        if base_row["lookup_status"] == "api_error":
            raw_results[name] = person_raw_results
            continue

        raw_results[name] = person_raw_results
        candidate, confidence, notes, query_used = select_best_audit_candidate(person, candidate_groups)
        if candidate is None:
            base_row["lookup_status"] = "not_found"
            base_row["confidence"] = "none"
            base_row["notes"] = notes
        else:
            base_row["lookup_status"] = "candidate_found"
            base_row["candidate_cspan_person_id"] = candidate.get("id", "")
            base_row["candidate_cspan_name"] = candidate.get("name", "")
            base_row["candidate_cspan_title"] = candidate.get("title", "")
            base_row["confidence"] = confidence
            base_row["evidence_url"] = cspan_person_evidence_url(candidate)
            base_row["evidence_text"] = cspan_person_evidence_text(candidate)
            base_row["notes"] = notes

        audit_rows.append(base_row)
        if sleep_seconds:
            time.sleep(sleep_seconds)

    write_csv_rows(output_path, audit_rows, CSPAN_PERSON_ID_AUDIT_FIELDNAMES)
    client.save_json(raw_results, raw_output_path)

    high_confidence = sum(1 for row in audit_rows if row.get("confidence") == "high" and not row.get("current_cspan_person_id"))
    needs_review = sum(1 for row in audit_rows if row.get("confidence") in ("needs_review", "low"))
    not_found = sum(1 for row in audit_rows if row.get("lookup_status") == "not_found")
    existing = sum(1 for row in audit_rows if row.get("lookup_status") == "existing_id")
    api_errors = sum(1 for row in audit_rows if row.get("lookup_status") == "api_error")
    skipped_after_rate_limit = sum(1 for row in audit_rows if row.get("lookup_status") == "skipped_after_rate_limit")
    audit_incomplete = bool(api_errors or skipped_after_rate_limit)

    print("C-SPAN person ID audit complete.")
    print(f"Audit incomplete due to API limits/errors: {'yes' if audit_incomplete else 'no'}")
    print(f"Tracked people: {len(audit_rows)}")
    if requested_people_names:
        print(f"Only people: {', '.join(requested_people_names)}")
    print(f"Existing IDs preserved: {existing}")
    print(f"High-confidence blank-ID candidates: {high_confidence}")
    print(f"Needs review / low confidence: {needs_review}")
    print(f"Not found: {not_found}")
    print(f"API errors: {api_errors}")
    print(f"Skipped after rate limit: {skipped_after_rate_limit}")
    print(f"Saved audit CSV to: {output_path}")
    print(f"Saved raw lookup JSON to: {raw_output_path}")
    return 0


def cmd_apply_cspan_person_ids(args: argparse.Namespace) -> int:
    tracked_path = Path(args.tracked_people)
    input_path = Path(args.input)
    tracked_rows = load_csv_rows(tracked_path)
    audit_rows = load_csv_rows(input_path)

    candidates_by_name = {
        row.get("name", "").strip(): row
        for row in audit_rows
        if row.get("name", "").strip()
    }

    changes: list[tuple[str, str, str, str, str]] = []
    skipped_unsafe: list[tuple[str, str, str]] = []
    updated_rows: list[dict[str, Any]] = []
    for row in tracked_rows:
        updated_row = dict(row)
        name = row.get("name", "").strip()
        current_id = row.get("cspan_person_id", "").strip()
        audit_row = candidates_by_name.get(name, {})
        candidate_id = audit_row.get("candidate_cspan_person_id", "").strip()
        candidate_name = audit_row.get("candidate_cspan_name", "").strip()
        confidence = audit_row.get("confidence", "")
        exact_name_or_alias = cspan_candidate_matches_tracked_name_or_alias(row, candidate_name)

        if candidate_id and confidence == "high" and (args.overwrite or not current_id):
            if not exact_name_or_alias:
                skipped_unsafe.append((name, candidate_name, candidate_id))
                updated_rows.append(updated_row)
                continue
            if current_id != candidate_id:
                updated_row["cspan_person_id"] = candidate_id
                notes = updated_row.get("notes", "").strip()
                applied_note = f"Applied high-confidence C-SPAN ID from {input_path.name}."
                updated_row["notes"] = f"{notes} {applied_note}".strip()
                changes.append(
                    (
                        name,
                        row.get("group", "").strip(),
                        row.get("role", "").strip(),
                        current_id,
                        candidate_id,
                    )
                )

        updated_rows.append(updated_row)

    if args.dry_run:
        print("Dry run: no files written.")
    else:
        backup_path = tracked_path.with_name(f"{tracked_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{tracked_path.suffix}")
        backup_path.write_text(tracked_path.read_text(encoding="utf-8-sig"), encoding="utf-8")
        write_csv_rows(tracked_path, updated_rows, TRACKED_PEOPLE_FIELDNAMES)
        print(f"Backup written to: {backup_path}")

    print("C-SPAN person ID apply summary")
    print(f"Input audit: {input_path}")
    print(f"Tracked people file: {tracked_path}")
    print(f"Overwrite existing IDs: {'yes' if args.overwrite else 'no'}")
    print(f"Changes: {len(changes)}")
    for name, group, role, old_id, new_id in changes:
        old_text = old_id or "(blank)"
        context = " | ".join(part for part in [group, role] if part)
        context_text = f" [{context}]" if context else ""
        print(f"- {name}{context_text}: {old_text} -> {new_id}")
    if skipped_unsafe:
        print(f"Unsafe high-confidence rows skipped after exact-name/alias recheck: {len(skipped_unsafe)}")
        for name, candidate_name, candidate_id in skipped_unsafe:
            print(f"- {name}: candidate {candidate_name} ({candidate_id}) did not exactly match name or alias.")

    return 0


def cmd_apply_reviewed_cspan_person_ids(args: argparse.Namespace) -> int:
    tracked_path = Path(args.tracked_people)
    input_path = Path(args.input)
    tracked_rows = load_csv_rows(tracked_path)
    reviewed_rows = load_csv_rows(input_path)

    tracked_by_name = {
        row.get("name", "").strip(): row
        for row in tracked_rows
        if row.get("name", "").strip()
    }

    changes: list[tuple[str, str, str, str, str]] = []
    skipped_rows: list[tuple[str, str]] = []
    reviewed_by_name: dict[str, dict[str, str]] = {}

    for reviewed_row in reviewed_rows:
        tracked_name = reviewed_row.get("tracked_name", "").strip()
        cspan_person_id = reviewed_row.get("cspan_person_id", "").strip()
        reviewed_candidate_name = reviewed_row.get("reviewed_candidate_name", "").strip()
        review_reason = reviewed_row.get("review_reason", "").strip()

        if not tracked_name:
            skipped_rows.append(("(blank)", "tracked_name is required."))
            continue
        if tracked_name not in tracked_by_name:
            skipped_rows.append((tracked_name, "tracked_name not found in tracked_people.csv."))
            continue
        if not cspan_person_id or not cspan_person_id.isdigit():
            skipped_rows.append((tracked_name, "cspan_person_id is required and must be numeric."))
            continue
        if not reviewed_candidate_name:
            skipped_rows.append((tracked_name, "reviewed_candidate_name is required."))
            continue
        if not review_reason:
            skipped_rows.append((tracked_name, "review_reason is required."))
            continue
        if tracked_name in reviewed_by_name:
            skipped_rows.append((tracked_name, "duplicate tracked_name in reviewed input."))
            continue

        reviewed_by_name[tracked_name] = reviewed_row

    updated_rows: list[dict[str, Any]] = []
    for row in tracked_rows:
        updated_row = dict(row)
        tracked_name = row.get("name", "").strip()
        reviewed_row = reviewed_by_name.get(tracked_name)
        if not reviewed_row:
            updated_rows.append(updated_row)
            continue

        current_id = row.get("cspan_person_id", "").strip()
        new_id = reviewed_row.get("cspan_person_id", "").strip()
        if current_id and not args.overwrite:
            skipped_rows.append((tracked_name, f"existing cspan_person_id {current_id} preserved; use --overwrite to replace."))
            updated_rows.append(updated_row)
            continue
        if current_id == new_id:
            skipped_rows.append((tracked_name, f"existing cspan_person_id already equals {new_id}."))
            updated_rows.append(updated_row)
            continue

        updated_row["cspan_person_id"] = new_id
        notes = updated_row.get("notes", "").strip()
        applied_note = f"Applied reviewed C-SPAN ID from {input_path.name}: {reviewed_row.get('review_reason', '').strip()}."
        updated_row["notes"] = f"{notes} {applied_note}".strip()
        changes.append(
            (
                tracked_name,
                row.get("group", "").strip(),
                row.get("role", "").strip(),
                current_id,
                new_id,
            )
        )
        updated_rows.append(updated_row)

    if args.dry_run:
        print("Dry run: no files written.")
    else:
        backup_path = tracked_path.with_name(f"{tracked_path.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{tracked_path.suffix}")
        backup_path.write_text(tracked_path.read_text(encoding="utf-8-sig"), encoding="utf-8")
        write_csv_rows(tracked_path, updated_rows, TRACKED_PEOPLE_FIELDNAMES)
        print(f"Backup written to: {backup_path}")

    print("Reviewed C-SPAN person ID apply summary")
    print(f"Input reviewed CSV: {input_path}")
    print(f"Tracked people file: {tracked_path}")
    print(f"Overwrite existing IDs: {'yes' if args.overwrite else 'no'}")
    print(f"Changes: {len(changes)}")
    for name, group, role, old_id, new_id in changes:
        old_text = old_id or "(blank)"
        context = " | ".join(part for part in [group, role] if part)
        context_text = f" [{context}]" if context else ""
        print(f"- {name}{context_text}: {old_text} -> {new_id}")

    print(f"Skipped rows: {len(skipped_rows)}")
    for name, reason in skipped_rows:
        print(f"- {name}: {reason}")

    return 0


def load_tracked_people(input_path: Path) -> list[dict[str, str]]:
    tracked_rows = load_optional_csv_rows(input_path)
    people: list[dict[str, str]] = []
    seen_names: set[str] = set()
    for row in tracked_rows:
        name = row.get("name", "").strip() or row.get("display_name", "").strip()
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        normalized_row = {field: row.get(field, "").strip() for field in TRACKED_PEOPLE_FIELDNAMES}
        normalized_row["name"] = name
        people.append(normalized_row)
    return people


def load_reviewed_no_cspan_profiles(input_path: Path) -> dict[str, dict[str, str]]:
    reviewed: dict[str, dict[str, str]] = {}
    for row in load_optional_csv_rows(input_path):
        tracked_name = row.get("tracked_name", "").strip()
        review_status = row.get("review_status", "").strip()
        if not tracked_name:
            continue
        if review_status and review_status not in NO_CSPAN_PROFILE_STATUSES:
            continue
        reviewed[tracked_name.lower()] = {
            "tracked_name": tracked_name,
            "review_status": review_status,
            "review_reason": row.get("review_reason", "").strip(),
            "reviewed_at": row.get("reviewed_at", "").strip(),
        }
    return reviewed


def row_date_since(row: dict[str, Any], since: str) -> bool:
    if not since:
        return True
    event_date = row_event_date(row)[:10]
    return bool(event_date and event_date >= since)


def rows_for_person_since(
    rows: list[dict[str, Any]],
    person_name: str,
    since: str,
) -> list[dict[str, Any]]:
    person_key = person_name.strip().lower()
    return [
        row for row in rows
        if row_member_name(row).strip().lower() == person_key
        and row_date_since(row, since)
    ]


def program_id_stats(rows: list[dict[str, Any]]) -> tuple[int, int]:
    program_id_rows = sum(1 for row in rows if row.get("program_id", "").strip())
    return program_id_rows, len(rows) - program_id_rows


def archive_completeness_warnings(
    person: dict[str, str],
    catalog_rows: list[dict[str, Any]],
    seen_rows: list[dict[str, Any]],
    duplicate_group_count: int,
) -> str:
    warnings: list[str] = []
    if not person.get("cspan_person_id", "").strip():
        warnings.append("missing_cspan_person_id")
    if not catalog_rows:
        warnings.append("zero_catalog_rows_since")
    elif len(catalog_rows) < 3:
        warnings.append("low_catalog_rows_since")
    if len(seen_rows) < len(catalog_rows):
        warnings.append("seen_ledger_below_catalog")
    if duplicate_group_count:
        warnings.append(f"duplicate_member_program_groups={duplicate_group_count}")
    if any(not row.get("program_id", "").strip() for row in catalog_rows):
        warnings.append("blank_program_ids")
    return "; ".join(warnings)


def archive_coverage_status(
    person: dict[str, str],
    catalog_rows: list[dict[str, Any]],
    crawl_floor_evidence: str = "",
) -> str:
    if not person.get("cspan_person_id", "").strip():
        return "needs_manual_cspan_id_review"
    if not catalog_rows:
        if crawl_floor_evidence:
            return "no_current_congress_rows_found"
        return "needs_ingestion"
    if len(catalog_rows) < 3:
        return "has_id_low_local_rows"
    return "likely_complete_enough"


def summary_batch_name(summary_path: Path) -> str:
    name = summary_path.name
    if name.startswith("cspan_update_index_") and name.endswith("_summary.csv"):
        middle = name[len("cspan_update_index_") : -len("_summary.csv")]
        return f"cspan_new_programs_{middle}"
    return summary_path.stem.replace("_summary", "")


def load_summary_dry_run_by_batch(output_dir: Path) -> dict[str, bool]:
    dry_run_by_batch: dict[str, bool] = {}
    for summary_path in sorted(output_dir.glob("cspan_update_index_*_summary.csv")):
        summary_rows = load_optional_csv_rows(summary_path)
        summary_is_dry_run = any(
            row.get("dry_run", "").lower() == "yes"
            or "dry run:" in row.get("notes", "").lower()
            for row in summary_rows
        )
        dry_run_by_batch[summary_batch_name(summary_path)] = summary_is_dry_run
    return dry_run_by_batch


def load_crawl_floor_evidence(
    output_dir: Path,
    include_dry_run_evidence: bool = False,
) -> dict[tuple[str, str], str]:
    evidence_by_person: dict[tuple[str, str], str] = {}
    dry_run_by_batch = load_summary_dry_run_by_batch(output_dir)
    for skipped_path in sorted(output_dir.glob("cspan_skipped_programs_*.csv")):
        for row in load_optional_csv_rows(skipped_path):
            if row.get("skip_reason", "") != "before_since_date":
                continue
            batch = row.get("batch", "").strip()
            row_is_dry_run = row.get("dry_run", "").lower() == "yes" or dry_run_by_batch.get(batch, False)
            if row_is_dry_run and not include_dry_run_evidence:
                continue
            person_name = row.get("person_name", "").strip()
            cspan_person_id = row.get("cspan_person_id", "").strip()
            if not person_name and not cspan_person_id:
                continue
            evidence = f"before_since_date skip found in {skipped_path}"
            if person_name:
                evidence_by_person[("name", person_name.lower())] = evidence
            if cspan_person_id:
                evidence_by_person[("id", cspan_person_id)] = evidence

    for summary_path in sorted(output_dir.glob("cspan_update_index_*_summary.csv")):
        summary_rows = load_optional_csv_rows(summary_path)
        summary_is_dry_run = any(
            row.get("dry_run", "").lower() == "yes"
            or "dry run:" in row.get("notes", "").lower()
            for row in summary_rows
        )
        if summary_is_dry_run and not include_dry_run_evidence:
            continue

        for row in summary_rows:
            if row.get("person_name", "") == "(run total)":
                continue
            if row.get("empty_page_reached", "").lower() != "yes":
                continue
            person_name = row.get("person_name", "").strip()
            cspan_person_id = row.get("cspan_person_id", "").strip()
            if not person_name and not cspan_person_id:
                continue
            evidence = f"empty page reached in {summary_path}"
            if person_name:
                evidence_by_person[("name", person_name.lower())] = evidence
            if cspan_person_id:
                evidence_by_person[("id", cspan_person_id)] = evidence
    return evidence_by_person


def crawl_floor_status(
    person: dict[str, str],
    catalog_rows: list[dict[str, Any]],
    crawl_floor_evidence: str,
) -> str:
    if not person.get("cspan_person_id", "").strip():
        return "missing_cspan_person_id"
    if crawl_floor_evidence:
        return "reached_since_floor"
    if not catalog_rows:
        return "zero_current_congress_rows"
    return "not_yet_proven"


def evidence_for_person(
    evidence_by_person: dict[tuple[str, str], str],
    person: dict[str, str],
) -> str:
    cspan_person_id = person.get("cspan_person_id", "").strip()
    if cspan_person_id:
        evidence = evidence_by_person.get(("id", cspan_person_id), "")
        if evidence:
            return evidence
    return evidence_by_person.get(("name", person.get("name", "").strip().lower()), "")


def build_archive_completeness_rows(
    *,
    since: str,
    tracked_people_path: Path,
    catalog_path: Path,
    seen_path: Path,
    priority_leads_path: Path,
    browser_source_path: Path,
    evidence_dir: Path,
    reviewed_no_profile_path: Path | None = None,
    include_dry_run_evidence: bool = False,
) -> list[dict[str, Any]]:
    crawl_evidence_by_person = load_crawl_floor_evidence(
        evidence_dir,
        include_dry_run_evidence=include_dry_run_evidence,
    )
    tracked_people = load_tracked_people(tracked_people_path)
    catalog_rows = load_optional_csv_rows(catalog_path)
    seen_rows = load_optional_csv_rows(seen_path)
    priority_rows = load_optional_csv_rows(priority_leads_path)
    browser_rows = load_optional_csv_rows(browser_source_path)
    reviewed_no_profiles = (
        load_reviewed_no_cspan_profiles(reviewed_no_profile_path)
        if reviewed_no_profile_path is not None
        else {}
    )

    audit_rows: list[dict[str, Any]] = []
    for person in tracked_people:
        name = person.get("name", "")
        person_catalog_rows = rows_for_person_since(catalog_rows, name, since)
        person_seen_rows = rows_for_person_since(seen_rows, name, since)
        person_priority_rows = rows_for_person_since(priority_rows, name, since)
        person_browser_rows = rows_for_person_since(browser_rows, name, since)
        event_dates = sorted(
            row_event_date(row)[:10]
            for row in person_catalog_rows
            if row_event_date(row)
        )
        program_id_rows, blank_program_id_rows = program_id_stats(person_catalog_rows)
        duplicate_groups = [
            key for key, count in duplicate_member_program_counts(person_catalog_rows).items()
            if count > 1
        ]
        warnings = archive_completeness_warnings(
            person=person,
            catalog_rows=person_catalog_rows,
            seen_rows=person_seen_rows,
            duplicate_group_count=len(duplicate_groups),
        )
        crawl_floor_evidence = evidence_for_person(crawl_evidence_by_person, person)
        coverage_status = archive_coverage_status(person, person_catalog_rows, crawl_floor_evidence)
        floor_status = crawl_floor_status(person, person_catalog_rows, crawl_floor_evidence)
        reviewed_no_profile = reviewed_no_profiles.get(name.strip().lower(), {})

        audit_rows.append(
            {
                "person_name": name,
                "group": person.get("group", ""),
                "role": person.get("role", ""),
                "person_type": person.get("person_type", ""),
                "party_or_affiliation": person.get("party_or_affiliation", ""),
                "cspan_person_id": person.get("cspan_person_id", ""),
                "coverage_status": coverage_status,
                "crawl_floor_status": floor_status,
                "reviewed_no_profile_status": reviewed_no_profile.get("review_status", ""),
                "reviewed_no_profile_reason": reviewed_no_profile.get("review_reason", ""),
                "reviewed_no_profile_reviewed_at": reviewed_no_profile.get("reviewed_at", ""),
                "crawl_floor_evidence": crawl_floor_evidence,
                "catalog_rows_since": len(person_catalog_rows),
                "seen_rows_since": len(person_seen_rows),
                "priority_rows_since": len(person_priority_rows),
                "browser_rows_since": len(person_browser_rows),
                "earliest_local_row": event_dates[0] if event_dates else "",
                "latest_local_row": event_dates[-1] if event_dates else "",
                "program_id_rows": program_id_rows,
                "blank_program_id_rows": blank_program_id_rows,
                "duplicate_member_program_groups": len(duplicate_groups),
                "warnings": warnings,
            }
        )

    return audit_rows


def cmd_audit_archive_completeness(args: argparse.Namespace) -> int:
    since = args.since.strip() or "2025-01-03"
    output_path = Path(args.output)
    audit_rows = build_archive_completeness_rows(
        since=since,
        tracked_people_path=Path(args.tracked_people),
        catalog_path=Path(args.catalog),
        seen_path=Path(args.seen),
        priority_leads_path=Path(args.priority_leads),
        browser_source_path=Path(args.browser_source),
        evidence_dir=output_path.parent,
        reviewed_no_profile_path=Path(args.reviewed_no_profile),
        include_dry_run_evidence=args.include_dry_run_evidence,
    )

    write_csv_rows(output_path, audit_rows, ARCHIVE_COMPLETENESS_FIELDNAMES)

    people_with_catalog_rows = sum(1 for row in audit_rows if int(row["catalog_rows_since"]) > 0)
    missing_ids = sum(1 for row in audit_rows if not row["cspan_person_id"])
    zero_catalog_rows = sum(1 for row in audit_rows if int(row["catalog_rows_since"]) == 0)
    duplicate_groups_total = sum(int(row["duplicate_member_program_groups"]) for row in audit_rows)
    status_counts: dict[str, int] = {}
    crawl_floor_status_counts: dict[str, int] = {}
    for row in audit_rows:
        status = str(row["coverage_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
        floor_status = str(row["crawl_floor_status"])
        crawl_floor_status_counts[floor_status] = crawl_floor_status_counts.get(floor_status, 0) + 1

    print("Archive completeness audit")
    print(f"Since: {since}")
    print(f"Tracked people: {len(audit_rows)}")
    print(f"People with local catalog rows: {people_with_catalog_rows}")
    print(f"People missing C-SPAN person IDs: {missing_ids}")
    print(f"People with zero catalog rows since date: {zero_catalog_rows}")
    print(f"Duplicate member/person + program groups: {duplicate_groups_total}")
    print("Coverage status counts:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print("Crawl floor status counts:")
    for status, count in sorted(crawl_floor_status_counts.items()):
        print(f"  {status}: {count}")
    print(f"Catalog: {args.catalog}")
    print(f"Seen ledger: {args.seen}")
    print(f"Priority leads: {args.priority_leads}")
    print(f"Browser source: {args.browser_source}")
    print(f"Include dry-run crawl evidence: {'yes' if args.include_dry_run_evidence else 'no'}")
    print(f"Saved audit CSV to: {output_path}")
    print("")
    print("Rows by person:")
    for row in audit_rows:
        warning_text = row["warnings"] or "ok"
        print(
            f"- {row['person_name']} | {row['group']} | "
            f"coverage={row['coverage_status']} crawl_floor={row['crawl_floor_status']} "
            f"catalog={row['catalog_rows_since']} seen={row['seen_rows_since']} "
            f"priority={row['priority_rows_since']} browser={row['browser_rows_since']} "
            f"range={row['earliest_local_row'] or 'n/a'}..{row['latest_local_row'] or 'n/a'} "
            f"program_ids={row['program_id_rows']}/{row['catalog_rows_since']} | {warning_text}"
        )

    return 0


def coverage_exception_next_step(row: dict[str, Any]) -> str:
    coverage_status = str(row.get("coverage_status", ""))
    crawl_status = str(row.get("crawl_floor_status", ""))
    catalog_rows = int(row.get("catalog_rows_since", 0) or 0)
    reviewed_status = str(row.get("reviewed_no_profile_status", "")).strip()

    if reviewed_status:
        return "Reviewed as no safe C-SPAN profile/match; no ID apply unless new evidence appears."
    if coverage_status == "needs_manual_cspan_id_review" and catalog_rows == 0:
        return "Run targeted C-SPAN person ID audit or mark as no C-SPAN profile if verified."
    if coverage_status == "has_id_low_local_rows" and crawl_status == "not_yet_proven":
        return "Run targeted update-index crawl or verify low-volume profile."
    if coverage_status == "has_id_low_local_rows" and crawl_status == "reached_since_floor":
        return "Likely low-volume profile; verify if person is strategically important."
    if coverage_status == "no_current_congress_rows_found":
        return "No current-Congress C-SPAN rows found since date; no ingestion needed unless strategically important."
    return "Review coverage status and decide whether targeted lookup or crawl is needed."


def coverage_exception_importance_bucket(row: dict[str, Any]) -> str:
    priority_rows = int(row.get("priority_rows_since", 0) or 0)
    if priority_rows > 0:
        return "high"

    group = str(row.get("group", "")).strip().lower()
    if group == "majority democrats":
        return "high"
    medium_groups = {
        "the bench",
        "external democrats",
        "republican leadership",
        "trump administration",
        "other",
    }
    if group in medium_groups:
        return "medium"
    return "low"


def build_coverage_exception_row(row: dict[str, Any]) -> dict[str, Any]:
    problem_parts = [
        f"coverage={row.get('coverage_status', '')}",
        f"crawl_floor={row.get('crawl_floor_status', '')}",
        f"catalog_rows={row.get('catalog_rows_since', 0)}",
        f"seen_rows={row.get('seen_rows_since', 0)}",
    ]
    warnings = str(row.get("warnings", "")).strip()
    if warnings:
        problem_parts.append(f"warnings={warnings}")
    reviewed_status = str(row.get("reviewed_no_profile_status", "")).strip()
    if reviewed_status:
        problem_parts.append(f"reviewed_no_profile={reviewed_status}")

    return {
        "name": row.get("person_name", ""),
        "group": row.get("group", ""),
        "role": row.get("role", ""),
        "person_type": row.get("person_type", ""),
        "party_or_affiliation": row.get("party_or_affiliation", ""),
        "cspan_person_id": row.get("cspan_person_id", ""),
        "coverage_status": row.get("coverage_status", ""),
        "crawl_floor_status": row.get("crawl_floor_status", ""),
        "reviewed_no_profile_status": row.get("reviewed_no_profile_status", ""),
        "reviewed_no_profile_reason": row.get("reviewed_no_profile_reason", ""),
        "catalog_rows": row.get("catalog_rows_since", 0),
        "seen_rows": row.get("seen_rows_since", 0),
        "priority_rows": row.get("priority_rows_since", 0),
        "browser_rows": row.get("browser_rows_since", 0),
        "first_program_date": row.get("earliest_local_row", ""),
        "last_program_date": row.get("latest_local_row", ""),
        "problem_summary": "; ".join(problem_parts),
        "recommended_next_step": coverage_exception_next_step(row),
        "importance_bucket": coverage_exception_importance_bucket(row),
    }


def cmd_export_coverage_exceptions(args: argparse.Namespace) -> int:
    since = args.since.strip() or "2025-01-03"
    output_path = Path(args.output)
    audit_rows = build_archive_completeness_rows(
        since=since,
        tracked_people_path=Path(args.tracked_people),
        catalog_path=Path(args.catalog),
        seen_path=Path(args.seen),
        priority_leads_path=Path(args.priority_leads),
        browser_source_path=Path(args.browser_source),
        evidence_dir=output_path.parent,
        reviewed_no_profile_path=Path(args.reviewed_no_profile),
        include_dry_run_evidence=args.include_dry_run_evidence,
    )

    included_statuses = {"needs_manual_cspan_id_review", "has_id_low_local_rows"}
    if args.include_zero_current_congress:
        included_statuses.add("no_current_congress_rows_found")

    exception_rows = [
        build_coverage_exception_row(row)
        for row in audit_rows
        if row.get("coverage_status", "") in included_statuses
        and not (args.exclude_reviewed_no_profile and row.get("reviewed_no_profile_status", ""))
    ]
    exception_rows.sort(
        key=lambda row: (
            {"high": 0, "medium": 1, "low": 2}.get(str(row.get("importance_bucket", "")), 3),
            str(row.get("coverage_status", "")),
            str(row.get("group", "")),
            str(row.get("name", "")),
        )
    )

    write_csv_rows(output_path, exception_rows, COVERAGE_EXCEPTIONS_FIELDNAMES)

    status_counts: dict[str, int] = {}
    group_counts: dict[str, int] = {}
    for row in exception_rows:
        status = str(row.get("coverage_status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
        group = str(row.get("group", "")) or "(blank)"
        group_counts[group] = group_counts.get(group, 0) + 1

    print("Coverage exceptions export")
    print(f"Since: {since}")
    print(f"Total exceptions exported: {len(exception_rows)}")
    print("Counts by coverage_status:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print("Counts by group:")
    for group, count in sorted(group_counts.items()):
        print(f"  {group}: {count}")
    print(f"Output path: {output_path}")
    return 0


def cmd_mark_no_cspan_profile(args: argparse.Namespace) -> int:
    requested_names = parse_people_filter(args.only_people)
    if not requested_names:
        raise ValueError("--only-people is required.")

    review_status = args.review_status.strip()
    if review_status not in NO_CSPAN_PROFILE_STATUSES:
        raise ValueError(
            "--review-status must be one of: " + ", ".join(sorted(NO_CSPAN_PROFILE_STATUSES))
        )
    review_reason = args.review_reason.strip()
    if not review_reason:
        raise ValueError("--review-reason cannot be blank.")

    tracked_people = load_tracked_people(Path(args.tracked_people))
    tracked_names = {person.get("name", "") for person in tracked_people}
    missing_names = [name for name in requested_names if name not in tracked_names]
    if missing_names:
        raise ValueError(
            "Names passed to --only-people were not found in tracked_people.csv: "
            + ", ".join(missing_names)
        )

    output_path = Path(args.output)
    existing_rows = load_optional_csv_rows(output_path)
    rows_by_name = {
        row.get("tracked_name", "").strip(): {
            "tracked_name": row.get("tracked_name", "").strip(),
            "review_status": row.get("review_status", "").strip(),
            "review_reason": row.get("review_reason", "").strip(),
            "reviewed_at": row.get("reviewed_at", "").strip(),
        }
        for row in existing_rows
        if row.get("tracked_name", "").strip()
    }
    existing_order = [
        row.get("tracked_name", "").strip()
        for row in existing_rows
        if row.get("tracked_name", "").strip()
    ]

    reviewed_at = args.reviewed_at.strip() or utc_timestamp()[:10]
    changed_names: list[str] = []
    added_names: list[str] = []
    for name in requested_names:
        new_row = {
            "tracked_name": name,
            "review_status": review_status,
            "review_reason": review_reason,
            "reviewed_at": reviewed_at,
        }
        if name not in rows_by_name:
            existing_order.append(name)
            added_names.append(name)
        elif rows_by_name[name] != new_row:
            changed_names.append(name)
        rows_by_name[name] = new_row

    output_rows = [rows_by_name[name] for name in existing_order if name in rows_by_name]
    write_csv_rows(output_path, output_rows, REVIEWED_NO_CSPAN_PROFILE_FIELDNAMES)

    print("Reviewed no-C-SPAN-profile marks updated")
    print(f"Output path: {output_path}")
    print(f"Rows written: {len(output_rows)}")
    print(f"Added rows: {len(added_names)}")
    for name in added_names:
        print(f"- added: {name}")
    print(f"Updated rows: {len(changed_names)}")
    for name in changed_names:
        print(f"- updated: {name}")
    print(f"Review status: {review_status}")
    print(f"Reviewed at: {reviewed_at}")
    return 0


def cmd_audit_topic_aliases(args: argparse.Namespace) -> int:
    priorities_path = Path(args.priorities)
    aliases_path = Path(args.aliases)
    matrix_topics = matrix_topic_values(priorities_path)
    aliases_by_topic = load_topic_alias_rows(aliases_path)
    missing_topics = [
        topic for topic in matrix_topics
        if normalize_topic_key(topic) not in aliases_by_topic
    ]
    weak_topics = [
        topic for topic in matrix_topics
        if len(aliases_by_topic.get(normalize_topic_key(topic), [])) < 3
    ]

    print("Topic alias audit")
    print(f"Priorities: {priorities_path}")
    print(f"Aliases: {aliases_path}")
    print(f"Total matrix topics: {len(matrix_topics)}")
    print(f"Topics with aliases: {len(matrix_topics) - len(missing_topics)}")
    print(f"Topics missing aliases: {len(missing_topics)}")
    print(f"Topics with weak aliases (<3): {len(weak_topics)}")
    print("")

    if missing_topics:
        print("Missing aliases:")
        for topic in missing_topics:
            print(f"- {topic}")
        print("")

    if weak_topics:
        print("Weak aliases:")
        for topic in weak_topics:
            count = len(aliases_by_topic.get(normalize_topic_key(topic), []))
            print(f"- {topic}: {count}")
        print("")

    print("Alias count per topic:")
    for topic in matrix_topics:
        count = len(aliases_by_topic.get(normalize_topic_key(topic), []))
        print(f"- {topic}: {count}")

    return 0


def duplicate_member_program_counts(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        program_id = row.get("program_id", "").strip()
        if not program_id:
            continue
        key = (row_member_name(row), program_id)
        counts[key] = counts.get(key, 0) + 1
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="md_cspan",
        description="Majority Democrats C-SPAN archive tooling.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    raw_parser = subparsers.add_parser(
        "raw",
        help="Call a C-SPAN API path and print or save the raw JSON response.",
    )
    raw_parser.add_argument("path", help="API path or full URL. Example: /programs/search")
    raw_parser.add_argument("--param", action="append", default=[], help="Query parameter in key=value format. Can be repeated.")
    raw_parser.add_argument("--output", help="Optional output JSON path.")
    raw_parser.set_defaults(func=cmd_raw)

    smoke_parser = subparsers.add_parser(
        "smoke-test",
        help="Run one test request and save the response to output/smoke_test_response.json.",
    )
    smoke_parser.add_argument("path", help="API path or full URL to test.")
    smoke_parser.add_argument("--param", action="append", default=[], help="Query parameter in key=value format. Can be repeated.")
    smoke_parser.set_defaults(func=cmd_smoke_test)

    people_parser = subparsers.add_parser(
        "people-lookup",
        help="Look up C-SPAN person IDs for members listed in a CSV.",
    )
    people_parser.add_argument("--input", default="data/members.csv", help="Input CSV with first,last,display_name columns.")
    people_parser.add_argument("--output", default="output/people_lookup.csv", help="Output CSV path.")
    people_parser.add_argument("--raw-output", default="output/people_lookup_raw.json", help="Raw JSON output path.")
    people_parser.add_argument("--aliases", help="Optional CSV with display_name,alias_first,alias_last,alias_query columns.")
    people_parser.set_defaults(func=cmd_people_lookup)

    program_search_parser = subparsers.add_parser(
        "program-search",
        help="Search C-SPAN programs using the /programs/search endpoint.",
    )
    program_search_parser.add_argument("--query", required=True, help="Lucene query string for program search.")
    program_search_parser.add_argument("--sort", default="date desc", help="Sort option. Example: date desc")
    program_search_parser.add_argument("--cursor", default="", help="Optional pagination cursor.")
    program_search_parser.add_argument("--output", default="output/program_search.csv", help="Output CSV path.")
    program_search_parser.add_argument("--raw-output", default="output/program_search_raw.json", help="Raw JSON output path.")
    program_search_parser.set_defaults(func=cmd_program_search)

    person_program_parser = subparsers.add_parser(
        "person-program-search",
        help="Search programs by C-SPAN person ID.",
    )
    person_program_parser.add_argument("--person-id", required=True, help="C-SPAN person ID.")
    person_program_parser.add_argument("--extra-query", default="", help="Optional additional Lucene query to AND with personid.")
    person_program_parser.add_argument("--sort", default="date desc", help="Sort option. Example: date desc")
    person_program_parser.add_argument("--cursor", default="", help="Optional pagination cursor.")
    person_program_parser.add_argument("--output", default="output/person_program_search.csv", help="Output CSV path.")
    person_program_parser.add_argument("--raw-output", default="output/person_program_search_raw.json", help="Raw JSON output path.")
    person_program_parser.set_defaults(func=cmd_person_program_search)

    program_detail_parser = subparsers.add_parser(
        "program-detail",
        help="Fetch details for a single C-SPAN program/video ID.",
    )
    program_detail_parser.add_argument("--video-id", required=True, help="C-SPAN video/program ID.")
    program_detail_parser.add_argument("--output", default="output/program_detail.json", help="Output JSON path.")
    program_detail_parser.set_defaults(func=cmd_program_detail)

    archive_parser = subparsers.add_parser(
        "archive-catalog",
        help="Build a v0.1 C-SPAN member archive catalog from people_lookup.csv.",
    )
    archive_parser.add_argument("--input", default="output/people_lookup.csv", help="Input people lookup CSV.")
    archive_parser.add_argument("--output", default="output/cspan_archive_catalog.csv", help="Output archive catalog CSV.")
    archive_parser.add_argument("--raw-dir", default="output/raw", help="Folder for raw search/detail JSON.")
    archive_parser.add_argument("--sort", default="date desc", help="C-SPAN sort option. Example: date desc")
    archive_parser.add_argument("--max-pages-per-member", default=1, type=int, help="Maximum paginated result pages per member.")
    archive_parser.add_argument("--start-member-index", default=1, type=int, help="Start at this 1-based usable matched member index.")
    archive_parser.add_argument("--limit-members", default=0, type=int, help="Only process the first N matched people. Use 0 for no limit.")
    archive_parser.add_argument("--sleep-seconds", default=0.0, type=float, help="Sleep this many seconds after each C-SPAN API request.")
    archive_parser.add_argument("--detail-limit-per-member", default=None, type=int, help="Only fetch details for the first N programs per member.")
    archive_parser.add_argument("--skip-details", action="store_true", help="Skip /programs/{videoId} detail fetches.")
    archive_parser.add_argument("--dedupe-programs", action="store_true", help="Skip duplicate program IDs, preserving the first encountered row.")
    archive_parser.set_defaults(func=cmd_archive_catalog)

    update_index_parser = subparsers.add_parser(
        "update-index",
        help="Update a persistent member/program C-SPAN discovery index.",
    )
    update_index_parser.add_argument("--lookup", default="", help="Reviewed people lookup CSV.")
    update_index_parser.add_argument("--people", default="", help="Tracked people CSV. Alias for --lookup.")
    update_index_parser.add_argument("--catalog", required=True, help="Persistent master catalog CSV.")
    update_index_parser.add_argument("--seen", required=True, help="Persistent seen-program ledger CSV.")
    update_index_parser.add_argument("--output-new", required=True, help="Output CSV containing only newly discovered rows.")
    update_index_parser.add_argument("--raw-dir", default="output/raw_update_index", help="Folder for raw search JSON.")
    update_index_parser.add_argument("--sort", default="date desc", help="C-SPAN sort option. Example: date desc")
    update_index_parser.add_argument("--max-pages-per-member", default=1, type=int, help="Maximum paginated result pages per member.")
    update_index_parser.add_argument("--start-member-index", default=1, type=int, help="Start at this 1-based usable matched member index.")
    update_index_parser.add_argument("--start-page", default=1, type=int, help="Start the first processed person at this 1-based C-SPAN result page. Use with --start-cursor from a suggested resume command.")
    update_index_parser.add_argument("--start-cursor", default="", help="C-SPAN cursor for --start-page, normally copied from a suggested resume command.")
    update_index_parser.add_argument("--limit-members", default=0, type=int, help="Only process N matched people. Use 0 for no limit.")
    update_index_parser.add_argument("--limit-people", dest="limit_members", default=argparse.SUPPRESS, type=int, help="Alias for --limit-members.")
    update_index_parser.add_argument("--only-people", default="", help="Comma-separated exact person names to crawl, preserving input CSV order.")
    update_index_parser.add_argument("--sleep-seconds", default=1.0, type=float, help="Sleep this many seconds between member searches.")
    update_index_parser.add_argument("--since", default="", help="Only add programs on or after this YYYY-MM-DD date.")
    update_index_parser.add_argument("--dry-run", action="store_true", help="Search and write output-new/summary without writing catalog or seen ledger.")
    update_index_parser.set_defaults(func=cmd_update_index)

    audit_id_parser = subparsers.add_parser(
        "audit-cspan-person-ids",
        help="Conservatively audit missing C-SPAN person IDs for tracked people.",
    )
    audit_id_parser.add_argument("--tracked-people", default="data/tracked_people.csv", help="Tracked people metadata CSV.")
    audit_id_parser.add_argument("--output", default="output/cspan_person_id_audit.csv", help="Output audit CSV path.")
    audit_id_parser.add_argument("--raw-output", default="output/cspan_person_id_audit_raw.json", help="Raw C-SPAN lookup JSON path.")
    audit_id_parser.add_argument("--sleep-seconds", default=1.0, type=float, help="Sleep this many seconds between C-SPAN people lookups.")
    audit_id_parser.add_argument("--limit-missing", default=0, type=int, help="Only look up this many missing IDs. Use 0 for no cap.")
    audit_id_parser.add_argument("--only-people", default="", help="Comma-separated exact tracked person names to audit, preserving supplied order.")
    audit_id_parser.add_argument("--all", action="store_true", help="Also re-check people who already have a C-SPAN ID.")
    audit_id_parser.set_defaults(func=cmd_audit_cspan_person_ids)

    apply_id_parser = subparsers.add_parser(
        "apply-cspan-person-ids",
        help="Apply only high-confidence C-SPAN person ID audit results to tracked_people.csv.",
    )
    apply_id_parser.add_argument("--input", required=True, help="Input cspan_person_id_audit.csv.")
    apply_id_parser.add_argument("--tracked-people", default="data/tracked_people.csv", help="Tracked people metadata CSV to update.")
    apply_id_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing C-SPAN person IDs when audit confidence is high.")
    apply_id_parser.add_argument("--dry-run", action="store_true", help="Print changes without writing tracked_people.csv.")
    apply_id_parser.set_defaults(func=cmd_apply_cspan_person_ids)

    apply_reviewed_id_parser = subparsers.add_parser(
        "apply-reviewed-cspan-person-ids",
        help="Apply manually reviewed C-SPAN person IDs from a CSV.",
    )
    apply_reviewed_id_parser.add_argument("--input", required=True, help="Reviewed CSV with tracked_name,cspan_person_id,reviewed_candidate_name,review_reason.")
    apply_reviewed_id_parser.add_argument("--tracked-people", default="data/tracked_people.csv", help="Tracked people metadata CSV to update.")
    apply_reviewed_id_parser.add_argument("--overwrite", action="store_true", help="Overwrite existing C-SPAN person IDs.")
    apply_reviewed_id_parser.add_argument("--dry-run", action="store_true", help="Print changes without writing tracked_people.csv.")
    apply_reviewed_id_parser.set_defaults(func=cmd_apply_reviewed_cspan_person_ids)

    merge_parser = subparsers.add_parser(
        "merge-catalogs",
        help="Merge archive catalog CSVs.",
    )
    merge_parser.add_argument("--input", action="append", required=True, help="Input archive catalog CSV. Can be repeated.")
    merge_parser.add_argument("--output", required=True, help="Output merged catalog CSV path.")
    merge_parser.add_argument("--dedupe-programs", action="store_true", help="Skip duplicate program IDs, preserving the first encountered row.")
    merge_parser.set_defaults(func=cmd_merge_catalogs)

    priority_parser = subparsers.add_parser(
        "priority-catalog",
        help="Find local catalog rows matching member priorities.",
    )
    priority_parser.add_argument("--catalog", required=True, help="Existing archive catalog CSV.")
    priority_parser.add_argument("--priorities", required=True, help="CSV with display_name,priority rows.")
    priority_parser.add_argument("--keywords", required=True, help="CSV with priority,keywords,notes rows.")
    priority_parser.add_argument("--output", required=True, help="Output priority catalog CSV path.")
    priority_parser.set_defaults(func=cmd_priority_catalog)

    lead_parser = subparsers.add_parser(
        "lead-export",
        help="Export a per-member review list from a scored priority catalog.",
    )
    lead_parser.add_argument("--input", required=True, help="Input scored priority catalog CSV.")
    lead_parser.add_argument("--output", required=True, help="Output lead review CSV path.")
    lead_parser.add_argument("--per-member", default=5, type=int, help="Maximum rows to keep per member.")
    lead_parser.add_argument("--strong-only", action="store_true", help="Exclude rows flagged REVIEW_BROAD_ONLY.")
    lead_parser.add_argument("--dedupe-programs-per-member", action="store_true", help="Keep one row per member/program before ranking.")
    lead_parser.set_defaults(func=cmd_lead_export)

    hydrate_parser = subparsers.add_parser(
        "hydrate-leads",
        help="Fetch program details for an existing lead-export CSV.",
    )
    hydrate_parser.add_argument("--input", required=True, help="Input lead-export CSV.")
    hydrate_parser.add_argument("--output", required=True, help="Output hydrated lead CSV.")
    hydrate_parser.add_argument("--raw-dir", default="output/raw_hydrated_priority_leads", help="Folder for raw detail JSON.")
    hydrate_parser.add_argument("--sleep-seconds", default=1.0, type=float, help="Sleep this many seconds after each detail request.")
    hydrate_parser.add_argument("--force", action="store_true", help="Refetch rows even when detail_fetched is already yes.")
    hydrate_parser.add_argument("--max-detail-calls", default=None, type=int, help="Only make this many detail calls. Intended for testing.")
    hydrate_parser.set_defaults(func=cmd_hydrate_leads)

    audit_parser = subparsers.add_parser(
        "audit-member",
        help="Audit local CSV/index coverage for one member.",
    )
    audit_parser.add_argument("--member", required=True, help="Member display name to audit.")
    audit_parser.add_argument("--since", default="", help="Only count rows on or after this YYYY-MM-DD date.")
    audit_parser.add_argument("--lookup", default="output/people_lookup_majority_democrats_reviewed.csv", help="Reviewed people lookup CSV.")
    audit_parser.add_argument("--catalog", default="output/cspan_member_programs_all.csv", help="Master catalog CSV.")
    audit_parser.add_argument("--seen", default="output/cspan_seen_programs.csv", help="Seen ledger CSV.")
    audit_parser.add_argument("--priority-catalog", default="output/cspan_priority_catalog_md_wordbound_renamed.csv", help="Priority catalog CSV to compare.")
    audit_parser.add_argument("--review-csv", default="output/cspan_priority_leads_md_top_unique_programs_wordbound_renamed.csv", help="Review/export CSV to compare.")
    audit_parser.add_argument("--reviewed-csv", default="", help="Optional reviewed CSV to compare.")
    audit_parser.set_defaults(func=cmd_audit_member)

    audit_topic_parser = subparsers.add_parser(
        "audit-member-topic",
        help="Audit local CSV/index coverage for one member + topic.",
    )
    audit_topic_parser.add_argument("--member", required=True, help="Member display name to audit.")
    audit_topic_parser.add_argument("--topic", required=True, help="Matrix topic to audit.")
    audit_topic_parser.add_argument("--since", default="", help="Only count rows on or after this YYYY-MM-DD date.")
    audit_topic_parser.add_argument("--catalog", default="output/cspan_member_programs_all.csv", help="Master catalog CSV.")
    audit_topic_parser.set_defaults(func=cmd_audit_member_topic)

    audit_alias_parser = subparsers.add_parser(
        "audit-topic-aliases",
        help="Audit topic alias coverage against the member matrix priorities.",
    )
    audit_alias_parser.add_argument("--priorities", default="data/member_priorities.csv", help="Matrix priorities CSV.")
    audit_alias_parser.add_argument("--aliases", default=str(TOPIC_ALIASES_CSV), help="Topic aliases CSV.")
    audit_alias_parser.set_defaults(func=cmd_audit_topic_aliases)

    audit_archive_parser = subparsers.add_parser(
        "audit-archive-completeness",
        help="Audit tracked-person archive coverage from a target date.",
    )
    audit_archive_parser.add_argument("--since", default="2025-01-03", help="Only count rows on or after this YYYY-MM-DD date.")
    audit_archive_parser.add_argument("--tracked-people", default="data/tracked_people.csv", help="Tracked people metadata CSV.")
    audit_archive_parser.add_argument("--catalog", default="output/cspan_member_programs_all.csv", help="Master catalog CSV.")
    audit_archive_parser.add_argument("--seen", default="output/cspan_seen_programs.csv", help="Seen ledger CSV.")
    audit_archive_parser.add_argument("--priority-leads", default="output/cspan_priority_leads_new_programs_md_depth3_merged.csv", help="Priority lead/export CSV to compare.")
    audit_archive_parser.add_argument("--browser-source", default="output/cspan_member_programs_all.csv", help="CSV source representing what the browser can show.")
    audit_archive_parser.add_argument("--reviewed-no-profile", default="data/reviewed_no_cspan_profile.csv", help="Reviewed no-C-SPAN-profile CSV.")
    audit_archive_parser.add_argument("--output", default="output/cspan_archive_completeness_audit.csv", help="Output audit CSV path.")
    audit_archive_parser.add_argument("--include-dry-run-evidence", action="store_true", help="Allow dry-run update summaries to count as crawl-floor evidence.")
    audit_archive_parser.set_defaults(func=cmd_audit_archive_completeness)

    export_exceptions_parser = subparsers.add_parser(
        "export-coverage-exceptions",
        help="Export a focused triage CSV for tracked-person coverage exceptions.",
    )
    export_exceptions_parser.add_argument("--since", default="2025-01-03", help="Only count rows on or after this YYYY-MM-DD date.")
    export_exceptions_parser.add_argument("--tracked-people", default="data/tracked_people.csv", help="Tracked people metadata CSV.")
    export_exceptions_parser.add_argument("--catalog", default="output/cspan_member_programs_all.csv", help="Master catalog CSV.")
    export_exceptions_parser.add_argument("--seen", default="output/cspan_seen_programs.csv", help="Seen ledger CSV.")
    export_exceptions_parser.add_argument("--priority-leads", default="output/cspan_priority_leads_new_programs_md_depth3_merged.csv", help="Priority lead/export CSV to compare.")
    export_exceptions_parser.add_argument("--browser-source", default="output/cspan_member_programs_all.csv", help="CSV source representing what the browser can show.")
    export_exceptions_parser.add_argument("--reviewed-no-profile", default="data/reviewed_no_cspan_profile.csv", help="Reviewed no-C-SPAN-profile CSV.")
    export_exceptions_parser.add_argument("--output", default="output/cspan_coverage_exceptions.csv", help="Output coverage exceptions CSV path.")
    export_exceptions_parser.add_argument("--include-zero-current-congress", action="store_true", help="Also include people with proven no current-Congress rows.")
    export_exceptions_parser.add_argument("--exclude-reviewed-no-profile", action="store_true", help="Exclude people already marked as reviewed no profile/no safe match.")
    export_exceptions_parser.add_argument("--include-dry-run-evidence", action="store_true", help="Allow dry-run update summaries to count as crawl-floor evidence.")
    export_exceptions_parser.set_defaults(func=cmd_export_coverage_exceptions)

    mark_no_profile_parser = subparsers.add_parser(
        "mark-no-cspan-profile",
        help="Create or update reviewed no-C-SPAN-profile marks for tracked people.",
    )
    mark_no_profile_parser.add_argument("--tracked-people", default="data/tracked_people.csv", help="Tracked people metadata CSV.")
    mark_no_profile_parser.add_argument("--output", default="data/reviewed_no_cspan_profile.csv", help="Reviewed no-C-SPAN-profile CSV to write.")
    mark_no_profile_parser.add_argument("--only-people", required=True, help="Comma-separated exact tracked person names to mark.")
    mark_no_profile_parser.add_argument("--review-status", required=True, choices=sorted(NO_CSPAN_PROFILE_STATUSES), help="Reviewed no-profile status.")
    mark_no_profile_parser.add_argument("--review-reason", required=True, help="Human review reason for the mark.")
    mark_no_profile_parser.add_argument("--reviewed-at", default="", help="Review date or timestamp. Defaults to today's UTC date.")
    mark_no_profile_parser.set_defaults(func=cmd_mark_no_cspan_profile)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)
    except (ValueError, CSpanApiError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
