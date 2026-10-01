"""Send simulator telemetry JSONL into the IncidentLens API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib import request


def post_event(api_url: str, event: dict) -> dict:
    payload = json.dumps(event).encode("utf-8")
    http_request = request.Request(
        api_url.rstrip("/") + "/events",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def send_jsonl(path: str | Path, api_url: str) -> list[dict]:
    responses: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as telemetry_file:
        for line_number, line in enumerate(telemetry_file, start=1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on line {line_number}: {exc}") from exc
            responses.append(post_event(api_url, event))
    return responses


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="POST telemetry JSONL to the IncidentLens API.")
    parser.add_argument("--telemetry-input", required=True, help="Path to simulator telemetry JSONL.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="Base API URL.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    responses = send_jsonl(args.telemetry_input, args.api_url)
    print(f"Sent {len(responses)} telemetry events to {args.api_url.rstrip('/')}/events")
    if responses:
        print(json.dumps(responses[-1], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
