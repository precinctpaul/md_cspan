from __future__ import annotations

from pathlib import Path


CLI_PATH = Path("md_cspan") / "cli.py"


UPDATED_CMD_ARCHIVE_CATALOG = '''def cmd_archive_catalog(args: argparse.Namespace) -> int:
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


'''


def replace_function(source: str, function_name: str, replacement: str, next_function_name: str) -> str:
    start_marker = f"def {function_name}("
    end_marker = f"def {next_function_name}("

    start = source.find(start_marker)
    if start == -1:
        raise RuntimeError(f"Could not find {start_marker}")

    end = source.find(end_marker, start)
    if end == -1:
        raise RuntimeError(f"Could not find {end_marker} after {start_marker}")

    return source[:start] + replacement + source[end:]


def add_import_time(source: str) -> str:
    if "import time\n" in source:
        return source

    anchor = "import re\n"
    if anchor not in source:
        raise RuntimeError("Could not find import re anchor.")

    return source.replace(anchor, anchor + "import time\n", 1)


def add_archive_parser_args(source: str) -> str:
    if "--limit-members" in source and "--sleep-seconds" in source and "--detail-limit-per-member" in source:
        return source

    anchor = '''    archive_parser.add_argument("--max-pages-per-member", default=1, type=int, help="Maximum paginated result pages per member.")
'''
    addition = '''    archive_parser.add_argument("--limit-members", default=0, type=int, help="Only process the first N matched people. Use 0 for no limit.")
    archive_parser.add_argument("--sleep-seconds", default=0.0, type=float, help="Sleep this many seconds after each C-SPAN API request.")
    archive_parser.add_argument("--detail-limit-per-member", default=None, type=int, help="Only fetch details for the first N programs per member.")
'''

    if anchor not in source:
        raise RuntimeError("Could not find archive parser --max-pages-per-member anchor.")

    return source.replace(anchor, anchor + addition, 1)


def main() -> int:
    if not CLI_PATH.exists():
        raise SystemExit(f"Could not find {CLI_PATH}. Run this from the repo root.")

    source = CLI_PATH.read_text(encoding="utf-8")
    updated = add_import_time(source)
    updated = replace_function(
        updated,
        function_name="cmd_archive_catalog",
        replacement=UPDATED_CMD_ARCHIVE_CATALOG,
        next_function_name="build_parser",
    )
    updated = add_archive_parser_args(updated)

    if updated == source:
        print("No changes needed.")
        return 0

    CLI_PATH.write_text(updated, encoding="utf-8")
    print(f"Updated {CLI_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())