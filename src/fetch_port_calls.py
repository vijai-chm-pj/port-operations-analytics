#!/usr/bin/env python3
"""Download Fintraffic port calls as a bounded, reproducible backfill."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://meri.digitraffic.fi/api/port-call/v1/port-calls"
MAX_RECORDS_PER_REQUEST = 1_000


def write_csv(path: Path, rows: list[dict[str, object]], overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise RuntimeError(f"CSV already exists: {path}; use --overwrite after reviewing it")
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_source_snapshot(raw_dir: Path, csv_dir: Path, manifest: dict, overwrite: bool) -> None:
    csv_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, object]] = []
    response_rows: list[dict[str, object]] = []
    area_rows: list[dict[str, object]] = []

    for chunk in manifest["chunks"]:
        manifest_rows.append(
            {
                "source_chunk": chunk["file"],
                "ata_from": chunk["ata_from"],
                "ata_to_exclusive": chunk["ata_to_exclusive"],
                "fetched_at": chunk["fetched_at"],
                "api_data_updated_time": chunk.get("api_data_updated_time", ""),
                "source_response_count": chunk["record_count"],
                "source_sha256": chunk["sha256"],
            }
        )
        payload = json.loads((raw_dir / chunk["file"]).read_text())
        for response_index, call in enumerate(payload["portCalls"], start=1):
            response_rows.append(
                {
                    "source_chunk": chunk["file"],
                    "response_index": response_index,
                    "port_call_id": call["portCallId"],
                    "port_code": call.get("portToVisit"),
                    "vessel_type_code": call.get("vesselTypeCode"),
                }
            )
            for area_sequence, area in enumerate(call.get("portAreaDetails", []), start=1):
                area_rows.append(
                    {
                        "source_chunk": chunk["file"],
                        "response_index": response_index,
                        "area_sequence": area_sequence,
                        "port_call_id": call["portCallId"],
                        "port_code": call.get("portToVisit"),
                        "vessel_type_code": call.get("vesselTypeCode"),
                        "port_area_code": area.get("portAreaCode"),
                        "berth_code": area.get("berthCode"),
                        "ata": area.get("ata"),
                        "ata_source": area.get("ataSource"),
                        "ata_timestamp": area.get("ataTimestamp"),
                        "atd": area.get("atd"),
                        "atd_source": area.get("atdSource"),
                        "atd_timestamp": area.get("atdTimestamp"),
                        "eta": area.get("eta"),
                        "eta_source": area.get("etaSource"),
                        "eta_timestamp": area.get("etaTimestamp"),
                        "etd": area.get("etd"),
                        "etd_source": area.get("etdSource"),
                        "etd_timestamp": area.get("etdTimestamp"),
                    }
                )

    write_csv(csv_dir / "backfill_manifest.csv", manifest_rows, overwrite)
    write_csv(csv_dir / "source_responses.csv", response_rows, overwrite)
    write_csv(csv_dir / "port_area_details.csv", area_rows, overwrite)


def parse_utc(value: str) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Invalid UTC timestamp: {value}") from error
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise argparse.ArgumentTypeError("Timestamp must use UTC, for example 2025-01-01T00:00:00Z")
    return timestamp.astimezone(UTC)


def format_utc(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def filename_timestamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y%m%dT%H%M%SZ")


def request_port_calls(start: datetime, end: datetime, user_agent: str, attempts: int) -> bytes:
    query = urlencode({"ataFrom": format_utc(start), "ataTo": format_utc(end)})
    request = Request(
        f"{API_URL}?{query}",
        headers={"Accept": "application/json", "Accept-Encoding": "gzip", "Digitraffic-User": user_agent},
    )
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=45) as response:
                payload = response.read()
                if payload.startswith(b"\x1f\x8b"):
                    return gzip.decompress(payload)
                return payload
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            if error.code == 500 and "1000" in body:
                raise ResultLimitError(body) from error
            if error.code not in {429, 500, 502, 503, 504} or attempt == attempts:
                raise RuntimeError(f"API returned HTTP {error.code} for {format_utc(start)} to {format_utc(end)}: {body[:300]}") from error
        except URLError as error:
            if attempt == attempts:
                raise RuntimeError(f"Network error for {format_utc(start)} to {format_utc(end)}: {error.reason}") from error
        time.sleep(attempt)
    raise RuntimeError("Request retry loop ended unexpectedly")


class ResultLimitError(Exception):
    pass


def split_window(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    midpoint = start + (end - start) / 2
    if midpoint <= start or midpoint >= end:
        raise RuntimeError(f"Cannot split request window further: {format_utc(start)} to {format_utc(end)}")
    return midpoint.replace(microsecond=0), end


def validate_response(payload: bytes, start: datetime, end: datetime) -> dict:
    try:
        response = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(f"API returned invalid JSON for {format_utc(start)} to {format_utc(end)}") from error
    calls = response.get("portCalls") if isinstance(response, dict) else None
    if not isinstance(calls, list):
        raise RuntimeError(f"API response has no portCalls array for {format_utc(start)} to {format_utc(end)}")
    if len(calls) >= MAX_RECORDS_PER_REQUEST:
        raise ResultLimitError(f"Response contains {len(calls)} records")
    if any(not isinstance(call, dict) or call.get("portCallId") is None for call in calls):
        raise RuntimeError(f"Response has a missing portCallId for {format_utc(start)} to {format_utc(end)}")
    return response


def chunk_details(file_name: str, payload: bytes, response: dict, start: datetime, end: datetime, fetched_at: str) -> dict:
    return {
        "file": file_name,
        "request_url": f"{API_URL}?{urlencode({'ataFrom': format_utc(start), 'ataTo': format_utc(end)})}",
        "ata_from": format_utc(start),
        "ata_to_exclusive": format_utc(end),
        "fetched_at": fetched_at,
        "api_data_updated_time": response.get("dataUpdatedTime"),
        "record_count": len(response["portCalls"]),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def download_window(start: datetime, end: datetime, output_dir: Path, user_agent: str, attempts: int, chunks: list[dict]) -> None:
    file_name = f"port_calls__{filename_timestamp(start)}__{filename_timestamp(end)}.json"
    file_path = output_dir / file_name
    if file_path.exists():
        payload = file_path.read_bytes()
        response = validate_response(payload, start, end)
        fetched_at = format_utc(datetime.fromtimestamp(file_path.stat().st_mtime, UTC))
        chunks.append(chunk_details(file_name, payload, response, start, end, fetched_at))
        return

    try:
        payload = request_port_calls(start, end, user_agent, attempts)
        response = validate_response(payload, start, end)
    except ResultLimitError:
        middle, _ = split_window(start, end)
        download_window(start, middle, output_dir, user_agent, attempts, chunks)
        download_window(middle, end, output_dir, user_agent, attempts, chunks)
        return

    file_path.write_bytes(payload)
    chunks.append(chunk_details(file_name, payload, response, start, end, format_utc(datetime.now(UTC))))


def run_backfill(start: datetime, end: datetime, output_dir: Path, initial_hours: int, user_agent: str, attempts: int, resume: bool) -> dict:
    if output_dir.exists() and not resume:
        raise RuntimeError(f"Output directory already exists: {output_dir}; use --resume only after reviewing partial files")
    output_dir.mkdir(parents=True, exist_ok=True)
    if (output_dir / "manifest.json").exists() and not resume:
        raise RuntimeError(f"Completed manifest already exists: {output_dir / 'manifest.json'}")
    chunks: list[dict] = []
    current = start
    while current < end:
        next_window = min(current + timedelta(hours=initial_hours), end)
        download_window(current, next_window, output_dir, user_agent, attempts, chunks)
        current = next_window

    seen_ids: set[int] = set()
    duplicate_ids: set[int] = set()
    for chunk in chunks:
        response = json.loads((output_dir / chunk["file"]).read_text())
        for call in response["portCalls"]:
            call_id = call["portCallId"]
            if call_id in seen_ids:
                duplicate_ids.add(call_id)
            seen_ids.add(call_id)

    manifest = {
        "source": "Fintraffic Digitraffic port-call API",
        "license": "CC BY 4.0; attribution required",
        "backfill_status": "complete_with_source_overlaps" if duplicate_ids else "complete",
        "backfill_start": format_utc(start),
        "backfill_end_exclusive": format_utc(end),
        "initial_window_hours": initial_hours,
        "chunk_count": len(chunks),
        "source_record_count": sum(chunk["record_count"] for chunk in chunks),
        "distinct_port_call_ids": len(seen_ids),
        "duplicate_port_call_id_count": len(duplicate_ids),
        "duplicate_port_call_ids": sorted(duplicate_ids),
        "chunks": chunks,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=parse_utc, required=True)
    parser.add_argument("--end", type=parse_utc, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--csv-dir", type=Path, required=True, help="Directory for the published source CSV snapshot")
    parser.add_argument("--initial-window-hours", type=int, default=24)
    parser.add_argument("--digitraffic-user", default="port-operations-analytics/1.0")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing CSV snapshot after review")
    args = parser.parse_args()

    if args.end <= args.start:
        parser.error("--end must be later than --start")
    if args.initial_window_hours < 1:
        parser.error("--initial-window-hours must be at least 1")
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    try:
        manifest = run_backfill(args.start, args.end, args.output_dir, args.initial_window_hours, args.digitraffic_user, args.attempts, args.resume)
        write_source_snapshot(args.output_dir, args.csv_dir, manifest, args.overwrite)
    except RuntimeError as error:
        print(f"backfill failed: {error}", file=sys.stderr)
        return 1

    print(
        f"backfill {manifest['backfill_status']}: {manifest['source_record_count']} records, "
        f"{manifest['distinct_port_call_ids']} distinct portCallId values, {manifest['chunk_count']} chunks; "
        f"wrote source CSV snapshot to {args.csv_dir}"
    )
    if manifest["duplicate_port_call_id_count"]:
        print(
            f"review required: {manifest['duplicate_port_call_id_count']} portCallId values appear in multiple source chunks; raw records were retained",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
