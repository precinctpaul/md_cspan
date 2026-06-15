from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from md_cspan.client import CSpanClient, CSpanApiError
from md_cspan.config import load_settings


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
    raw_parser.add_argument(
        "path",
        help="API path or full URL. Example: /videos/search",
    )
    raw_parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Query parameter in key=value format. Can be repeated.",
    )
    raw_parser.add_argument(
        "--output",
        help="Optional output JSON path.",
    )
    raw_parser.set_defaults(func=cmd_raw)

    smoke_parser = subparsers.add_parser(
        "smoke-test",
        help="Run one test request and save the response to output/smoke_test_response.json.",
    )
    smoke_parser.add_argument(
        "path",
        help="API path or full URL to test.",
    )
    smoke_parser.add_argument(
        "--param",
        action="append",
        default=[],
        help="Query parameter in key=value format. Can be repeated.",
    )
    smoke_parser.set_defaults(func=cmd_smoke_test)

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