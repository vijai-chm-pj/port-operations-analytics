# Data dictionary

## Published Q1 snapshot

`data/q1-2025/` is the reproducible analysis package committed with this repository. It is a one-time extract from the Fintraffic Digitraffic Port Call API for `[2025-01-01T00:00:00Z, 2025-04-01T00:00:00Z)`, published under CC BY 4.0 with attribution to Fintraffic / digitraffic.fi.

| File | Grain | Purpose |
|---|---|---|
| `backfill_manifest.csv` | One API request chunk | Reconcile the Q1 request boundary and source checksums |
| `source_responses.csv` | One source API response | Count and investigate source-level overlap |
| `port_area_details.csv` | One nested source port-area row | Input to the source-quality notebook |
| `canonical_port_area_events.csv` | One canonical actual port-area event | Input to exception and coverage analysis |
| `exception_register.csv` | One event-quality issue | Input to root-cause analysis |
| `quality_summary.csv` | One quality metric | Reconciliation summary |

The original API JSON payloads remain local-only. The CSV package contains only the fields needed to inspect this portfolio analysis.

## Source port-area detail

`port_area_details.csv` retains the source fields used to reproduce the canonicalisation decision.

| Fields | Description |
|---|---|
| `source_chunk`, `response_index`, `area_sequence` | Request and nested-row lineage |
| `port_call_id`, `port_code`, `vessel_type_code`, `port_area_code`, `berth_code` | Source event identity fields |
| `ata`, `atd` | Actual arrival and departure timestamps |
| `ata_source`, `atd_source`, `ata_timestamp`, `atd_timestamp` | Provenance and recorded time of each actual milestone |
| `eta`, `etd`, `eta_source`, `etd_source`, `eta_timestamp`, `etd_timestamp` | Forecast fields retained only to inspect source variants; not used as actual-event identity |

## Canonical port-area event

`canonical_port_area_events.csv` is a published derived dataset created by `src/build_quality_dataset.py`. It contains allowlisted operational fields only.

| Field | Description |
|---|---|
| `canonical_event_id` | Deterministic identifier for the canonical actual port-area event |
| `port_call_id` | Fintraffic source port-call identifier |
| `port_code` | Visited port code from `portToVisit` |
| `vessel_type_code` | Source vessel-type code |
| `port_area_code` | Port-area code from the nested source record |
| `berth_code` | Berth code from the nested source record |
| `ata` / `atd` | Actual arrival and departure timestamps, UTC when present |
| `source_row_count` | Raw nested rows represented by the canonical event |
| `source_response_count` | Source API responses represented by the canonical event |
| `source_chunks` | Daily request chunks that supplied the event |
| `source_positions` | Response and nested-row positions for traceability |
| `canonicalisation_decision` | Whether the event was retained or duplicate actual-event rows were collapsed |
| `completed_event_status` | `eligible` or the reason it is blocked from completed-event coverage |

## Exception register

`exception_register.csv` contains one row per event-quality issue.

| Field | Description |
|---|---|
| `issue_type` | Missing actual timestamp, invalid sequence, duplicate actual event, or conflicting source variant |
| `severity` | `blocking` or `review_required` |
| `state` | Whether the issue remains an open source gap or was resolved by canonicalisation |
| `affected_source_rows` | Number of raw nested rows represented by the issue |
| `remediation_rule` | Downstream handling applied by the build |

## Boundaries

The derived outputs exclude agent names, free text, booking-like references, and other fields that are unnecessary for this portfolio. Actual-event timestamps are not delay, wait-time, or customer-impact metrics.
