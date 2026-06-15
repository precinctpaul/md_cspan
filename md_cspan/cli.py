from __future__ import annotations

import argparse
import csv
import json
import re
import time
from pathlib import Path
from typing import Any

from md_cspan.client import CSpanApiError, CSpanClient
from md_cspan.config import load_settings


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
    output_rows: list[dict[str, Any]] = []
    raw_results: dict[str, Any] = {}

    for member in members:
        first = member.get("first", "")
        last = member.get("last", "")
        display_name = member.get("display_name", "") or f"{first} {last}".strip()

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
                    "notes": "No match returned",
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
    limit_members = max(0, int(args.limit_members))
    sleep_seconds = max(0.0, float(args.sleep_seconds))
    detail_limit_per_member = args.detail_limit_per_member
    if detail_limit_per_member is not None:
        detail_limit_per_member = max(0, int(detail_limit_per_member))

    fetch_details = not args.skip_details
    processed_members = 0

    for person_row in people_rows:
        if person_row.get("matched", "").lower() != "yes":
            continue

        if person_row.get("match_rank", "") not in ("", "1"):
            continue

        cspan_person_id = person_row.get("cspan_person_id", "").strip()
        if not cspan_person_id:
            continue

        if limit_members and processed_members >= limit_members:
            break

        processed_members += 1

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
    print(f"Members processed: {processed_members}")
    print(f"Rows: {len(catalog_rows)}")
    print(f"Saved catalog to: {output_path}")
    print(f"Saved raw JSON under: {raw_dir}")
    return 0


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
    archive_parser.add_argument("--limit-members", default=0, type=int, help="Only process the first N matched people. Use 0 for no limit.")
    archive_parser.add_argument("--sleep-seconds", default=0.0, type=float, help="Sleep this many seconds after each C-SPAN API request.")
    archive_parser.add_argument("--detail-limit-per-member", default=None, type=int, help="Only fetch details for the first N programs per member.")
    archive_parser.add_argument("--skip-details", action="store_true", help="Skip /programs/{videoId} detail fetches.")
    archive_parser.set_defaults(func=cmd_archive_catalog)

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