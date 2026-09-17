# Methodology

## Decision context

This project asks whether a public port-call event feed is reliable enough for downstream shipment-visibility workflows. The output is a traceable event-quality dataset and exception register, not a delay prediction or port-performance ranking.

## Source and scope

| Element | Definition |
|---|---|
| Source | Fintraffic Digitraffic Port Call API, CC BY 4.0 |
| Time window | `[2025-01-01T00:00:00Z, 2025-04-01T00:00:00Z)` |
| Raw grain | One API response version per snapshot; `portCallId` identifies the source call |
| Quality grain | One nested `portAreaDetails` row linked to a source response and daily request chunk |
| Derived grain | One canonical actual port-area event |

The original API JSON remains local-only. The repository includes a Q1 CSV snapshot with allowlisted analytical fields, request windows, source checksums, and derived outputs so both notebooks can run after cloning.

## Quality rules

| Check | Downstream handling |
|---|---|
| ATA or ATD missing | Keep in the exception register; exclude from completed-event coverage |
| `ATD < ATA` | Keep in the exception register; exclude from completed-event coverage |
| Same actual event appears more than once | Collapse only after the actual-event identity agrees; retain full source lineage |
| Same candidate identity has conflicting actual details | Keep variants separate and open a review item; never choose a winner automatically |
| Missing source lineage | Do not publish a downstream summary |

An event is eligible for completed-event coverage only when ATA and ATD are present and `ATD >= ATA`.

## Canonicalisation rule

The candidate identity is:

`portCallId + portAreaCode + berthCode + ATA + ATD`

Rows are collapsed only when their actual-event fingerprint also agrees: visited port, vessel type, port area, berth, ATA, ATD, their sources, and their recorded timestamps. ETA and ETD are retained in the source snapshot for inspection, but do not create separate completed actual events.

Multi-area calls are not duplicates by themselves. Distinct child records remain separate when their actual-event identities differ.

## Q1 2025 outcome

| Outcome | Count |
|---|---:|
| Source API responses | 7,135 |
| Raw nested port-area rows | 7,176 |
| Canonical actual events | 7,172 |
| Collapsed duplicate source rows | 4 |
| Eligible completed events | 7,081 (98.73%) |
| Open source-gap events | 91 |
| Negative actual intervals | 0 |

The four collapsed rows represent actual events already present in the source: three repeat across daily request chunks and one repeats within a parent response with only forecast ETA/ETD fields differing. No conflicting actual-event variant was found in this backfill.

## Limits

- One public source does not establish cross-source agreement.
- Historical prediction snapshots are unavailable, so prediction accuracy and reporting latency are out of scope.
- `ATD - ATA` is not shipment delay, berth waiting time, cargo handling time, port performance, or customer impact.
- Missing milestones are traced to the source event, but the upstream operational cause cannot be established from this dataset.
