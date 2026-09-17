#!/usr/bin/env python3
"""Build canonical port-area events and a visibility data-quality register from source CSV files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path


EVENT_COLUMNS = [
    "canonical_event_id",
    "port_call_id",
    "port_code",
    "vessel_type_code",
    "port_area_code",
    "berth_code",
    "ata",
    "atd",
    "source_row_count",
    "source_response_count",
    "source_chunks",
    "source_positions",
    "canonicalisation_decision",
    "completed_event_status",
]

ISSUE_COLUMNS = [
    "canonical_event_id",
    "issue_type",
    "severity",
    "state",
    "affected_source_rows",
    "port_call_id",
    "port_code",
    "source_chunks",
    "remediation_rule",
]


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def event_key(row: dict[str, object]) -> str:
    fields = ["port_call_id", "port_area_code", "berth_code", "ata", "atd"]
    return json.dumps([row[field] for field in fields], separators=(",", ":"))


def event_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def source_row_fingerprint(row: dict[str, object]) -> str:
    content = {
        "port_call_id": row["port_call_id"],
        "port_code": row["port_code"],
        "vessel_type_code": row["vessel_type_code"],
        "port_area_code": row["port_area_code"],
        "berth_code": row["berth_code"],
        "ata": row["ata"],
        "atd": row["atd"],
        "ata_source": row["ata_source"],
        "atd_source": row["atd_source"],
        "ata_timestamp": row["ata_timestamp"],
        "atd_timestamp": row["atd_timestamp"],
    }
    encoded = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


def read_source_csv(input_dir: Path) -> tuple[dict, list[dict[str, object]]]:
    manifest_path = input_dir / "backfill_manifest.csv"
    rows_path = input_dir / "port_area_details.csv"
    if not manifest_path.exists() or not rows_path.exists():
        raise RuntimeError("Expected backfill_manifest.csv and port_area_details.csv in the input directory")

    with manifest_path.open(newline="") as file:
        chunks = list(csv.DictReader(file))
    with rows_path.open(newline="") as file:
        rows = list(csv.DictReader(file))
    if not chunks or not rows:
        raise RuntimeError("Published CSV input is empty")

    required_columns = {
        "source_chunk", "response_index", "area_sequence", "port_call_id", "port_code", "vessel_type_code",
        "port_area_code", "berth_code", "ata", "ata_source", "ata_timestamp", "atd", "atd_source", "atd_timestamp",
    }
    if not required_columns.issubset(rows[0]):
        raise RuntimeError("Published port-area CSV is missing required columns")
    for row in rows:
        row["port_call_id"] = int(row["port_call_id"])
        row["response_index"] = int(row["response_index"])
        row["area_sequence"] = int(row["area_sequence"])
        for field in required_columns - {"source_chunk", "response_index", "area_sequence", "port_call_id"}:
            if row[field] == "":
                row[field] = None
        row["actual_event_fingerprint"] = source_row_fingerprint(row)

    return {
        "source_record_count": sum(int(chunk["source_response_count"]) for chunk in chunks),
        "chunk_count": len(chunks),
    }, rows


def completed_event_status(row: dict[str, object]) -> str:
    ata = parse_timestamp(row["ata"])
    atd = parse_timestamp(row["atd"])
    if ata is None and atd is None:
        return "blocked_missing_ata_and_atd"
    if ata is None:
        return "blocked_missing_ata"
    if atd is None:
        return "blocked_missing_atd"
    if atd < ata:
        return "blocked_negative_actual_interval"
    return "eligible"


def build_events(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    grouped_rows: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped_rows[event_key(row)].append(row)

    events: list[dict[str, object]] = []
    issues: list[dict[str, object]] = []
    for key, candidate_group in grouped_rows.items():
        fingerprint_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in candidate_group:
            fingerprint_groups[str(row["actual_event_fingerprint"])].append(row)
        has_conflicting_variants = len(fingerprint_groups) > 1

        for fingerprint, group in fingerprint_groups.items():
            first = group[0]
            identifier = event_id(f"{key}|{fingerprint}" if has_conflicting_variants else key)
            source_chunks = ";".join(sorted({str(row["source_chunk"]) for row in group}))
            positions = ";".join(
                f"{row['source_chunk']}#{row['response_index']}.{row['area_sequence']}" for row in group
            )
            response_positions = {(row["source_chunk"], row["response_index"]) for row in group}
            duplicate_rows = len(group) - 1
            status = completed_event_status(first)
            decision = "review_required_conflicting_variant" if has_conflicting_variants else "retained_as_distinct_port_area_event"
            if duplicate_rows:
                decision = "collapsed_same_actual_event"
            event = {
                "canonical_event_id": identifier,
                "port_call_id": first["port_call_id"],
                "port_code": first["port_code"],
                "vessel_type_code": first["vessel_type_code"],
                "port_area_code": first["port_area_code"],
                "berth_code": first["berth_code"],
                "ata": first["ata"],
                "atd": first["atd"],
                "source_row_count": len(group),
                "source_response_count": len(response_positions),
                "source_chunks": source_chunks,
                "source_positions": positions,
                "canonicalisation_decision": decision,
                "completed_event_status": status,
            }
            events.append(event)

            if has_conflicting_variants:
                issues.append(
                    {
                        "canonical_event_id": identifier,
                        "issue_type": "conflicting_candidate_variant",
                        "severity": "review_required",
                        "state": "open_source_conflict",
                        "affected_source_rows": len(candidate_group),
                        "port_call_id": first["port_call_id"],
                        "port_code": first["port_code"],
                        "source_chunks": source_chunks,
                        "remediation_rule": "Keep each source variant separate until a source-precedence rule is approved.",
                    }
                )
            elif duplicate_rows:
                issues.append(
                    {
                        "canonical_event_id": identifier,
                        "issue_type": "duplicate_actual_event",
                        "severity": "review_required",
                        "state": "resolved_by_canonicalisation",
                        "affected_source_rows": len(group),
                        "port_call_id": first["port_call_id"],
                        "port_code": first["port_code"],
                        "source_chunks": source_chunks,
                        "remediation_rule": "Collapse identical actual-event fingerprints and retain complete source lineage.",
                    }
                )
            if status != "eligible":
                issues.append(
                    {
                        "canonical_event_id": identifier,
                        "issue_type": status.removeprefix("blocked_"),
                        "severity": "blocking",
                        "state": "open_source_gap",
                        "affected_source_rows": len(group),
                        "port_call_id": first["port_call_id"],
                        "port_code": first["port_code"],
                        "source_chunks": source_chunks,
                        "remediation_rule": "Exclude from completed-event coverage and retain in the exception register.",
                    }
                )
    return events, issues


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summary_rows(manifest: dict, source_rows: list[dict[str, object]], events: list[dict[str, object]], issues: list[dict[str, object]]) -> list[dict[str, object]]:
    event_count = len(events)
    completed_count = sum(event["completed_event_status"] == "eligible" for event in events)
    missing_ata_count = sum("missing_ata" in str(event["completed_event_status"]) for event in events)
    missing_atd_count = sum("missing_atd" in str(event["completed_event_status"]) for event in events)
    negative_count = sum(event["completed_event_status"] == "blocked_negative_actual_interval" for event in events)
    duplicate_count = sum(event["source_row_count"] > 1 for event in events)
    return [
        {"metric": "source_response_records", "count": manifest["source_record_count"], "denominator": "", "rate": "", "note": "Reconciled to the published request manifest."},
        {"metric": "raw_port_area_rows", "count": len(source_rows), "denominator": "", "rate": "", "note": "Nested quality grain before canonicalisation."},
        {"metric": "canonical_port_area_events", "count": event_count, "denominator": "", "rate": "", "note": "Distinct canonical event keys."},
        {"metric": "collapsed_duplicate_source_rows", "count": len(source_rows) - event_count, "denominator": len(source_rows), "rate": f"{(len(source_rows) - event_count) / len(source_rows):.4f}", "note": "Extra source rows represented by an identical canonical event."},
        {"metric": "eligible_completed_events", "count": completed_count, "denominator": event_count, "rate": f"{completed_count / event_count:.4f}", "note": "Has ATA, ATD, and a non-negative actual interval."},
        {"metric": "events_missing_ata", "count": missing_ata_count, "denominator": event_count, "rate": f"{missing_ata_count / event_count:.4f}", "note": "Blocked from completed-event coverage."},
        {"metric": "events_missing_atd", "count": missing_atd_count, "denominator": event_count, "rate": f"{missing_atd_count / event_count:.4f}", "note": "Blocked from completed-event coverage."},
        {"metric": "negative_actual_intervals", "count": negative_count, "denominator": event_count, "rate": f"{negative_count / event_count:.4f}", "note": "Blocked from completed-event coverage."},
        {"metric": "exception_register_rows", "count": len(issues), "denominator": "", "rate": "", "note": "One event may have more than one issue."},
        {"metric": "duplicate_source_events", "count": duplicate_count, "denominator": event_count, "rate": f"{duplicate_count / event_count:.4f}", "note": "Resolved by retaining one event with full lineage."},
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True, help="Directory containing published source CSV files")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite:
        parser.error(f"Output directory is not empty: {args.output_dir}; use --overwrite after reviewing it")
    try:
        manifest, source_rows = read_source_csv(args.input_dir)
        events, issues = build_events(source_rows)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        write_csv(args.output_dir / "canonical_port_area_events.csv", events, EVENT_COLUMNS)
        write_csv(args.output_dir / "exception_register.csv", issues, ISSUE_COLUMNS)
        write_csv(
            args.output_dir / "quality_summary.csv",
            summary_rows(manifest, source_rows, events, issues),
            ["metric", "count", "denominator", "rate", "note"],
        )
    except (OSError, ValueError, json.JSONDecodeError, RuntimeError) as error:
        print(f"quality dataset build failed: {error}", file=sys.stderr)
        return 1

    print(f"quality dataset built: {len(source_rows)} source port-area rows, {len(events)} canonical events, {len(issues)} exception rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
