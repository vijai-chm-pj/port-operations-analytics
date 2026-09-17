# Port-call Visibility Data Quality Monitor

Independent maritime analytics portfolio. **Status: Q1 2025 source backfill, canonicalisation, and exception analysis are implemented; portfolio release review is in progress.**

Repository: https://github.com/vijai-chm-pj/port-operations-analytics

## Objective
Determine whether a port-call event feed is reliable enough for downstream shipment-visibility workflows. The project traces missing, inconsistent, and ambiguous milestones back to the source record, quantifies their coverage, and documents a remediation rule.

## Q1 2025 result

- Reconciled 7,135 raw API responses across 90 daily request chunks.
- Normalized 7,176 nested source rows into 7,172 canonical actual port-area events with source lineage.
- Resolved four duplicate actual-event rows without deleting their source evidence.
- Found 7,081 events eligible for completed-event coverage (98.73%); 91 events remain open source gaps because actual timestamps are incomplete.
- Found no negative actual-arrival to actual-departure sequence.

This establishes data completeness and consistency for the defined population only. It does not measure shipment delay, ETA accuracy, operational performance, or customer impact.

## Read this project in order

1. **This README** — the question, result, and scope.
2. **[Notebook 01](notebooks/01_q1_2025_data_quality.ipynb)** — prove that the raw Q1 source is complete enough to inspect.
3. **[Notebook 02](notebooks/02_q1_2025_exception_analysis.ipynb)** — explain duplicate events, missing milestones, and completed-event coverage.
4. **[Methodology](docs/methodology.md)** — the exact data model, quality rules, and canonicalisation decision.
5. **[Data dictionary](docs/data-dictionary.md)** — field-level reference for the derived outputs.

The notebooks are the main story. `src/` contains only the reusable ingestion and quality-build steps behind that story.

## Repository structure

```text
README.md                         project question, scope, and Q1 result
notebooks/
  01_q1_2025_data_quality.ipynb   reconcile the source and define the population
  02_q1_2025_exception_analysis.ipynb
                                  trace exceptions and report coverage
src/                              repeatable ingestion and quality-build logic
data/q1-2025/                     published Q1 CSV snapshot used by both notebooks
docs/
  methodology.md                  rules and decisions behind the analysis
  data-dictionary.md              field-level reference
```

## Selected data source
Fintraffic Digitraffic / Portnet port calls: https://www.digitraffic.fi/en/marine-traffic/

Three historical sample windows returned 448 port calls with identifiable visited ports. A one-time Q1 2025 backfill collected 7,135 source response records in 90 daily chunks. The published `data/q1-2025/` CSV snapshot contains the selected source fields, request manifest, and analysis outputs used by the notebooks. One `portCallId` appeared in two source chunks because its nested port-area timestamps span two days; it is retained as a data-quality finding, not silently deduplicated. This does not certify full historical completeness.

Source: Fintraffic / digitraffic.fi, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Planned transformations include field selection, normalization, quality checks and aggregation. See [source terms](https://www.digitraffic.fi/en/terms-of-service/).

Repository code is available under the [MIT License](LICENSE). The Q1 data snapshot has separate [source attribution](data/ATTRIBUTION.md).

## Evidence
[`notebooks/01_q1_2025_data_quality.ipynb`](notebooks/01_q1_2025_data_quality.ipynb) reads the published Q1 CSV snapshot, reconciles the 7,135 source records to the manifest, profiles 7,176 nested port-area records, and reports missing actual timestamps, invalid sequences, and duplicate candidate keys. It does not silently deduplicate or label an `ATD - ATA` interval as a delay KPI.

[`notebooks/02_q1_2025_exception_analysis.ipynb`](notebooks/02_q1_2025_exception_analysis.ipynb) traces the exception patterns to a canonical event rule. It reconciles 7,176 published source rows to 7,172 canonical actual events, retains full lineage for four collapsed duplicate rows, and reports 7,081 eligible completed events (98.73% coverage).

To run it locally:

```bash
python -m pip install -r requirements.txt
jupyter nbconvert --to notebook --execute --inplace notebooks/01_q1_2025_data_quality.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/02_q1_2025_exception_analysis.ipynb
```

To refresh the source snapshot from the API, use a new local output directory and review the changed CSV files before replacing `data/q1-2025/`:

```bash
python src/fetch_port_calls.py \
  --start 2025-01-01T00:00:00Z \
  --end 2025-04-01T00:00:00Z \
  --output-dir raw/backfills/q1-2025-refresh \
  --csv-dir data/q1-2025-refresh
python src/build_quality_dataset.py \
  --input-dir data/q1-2025-refresh \
  --output-dir data/q1-2025-refresh \
  --overwrite
```

## Boundaries
This is an analogue of visibility-data quality work, not a reproduction of any company's proprietary system. The original API JSON is retained locally; the repository publishes only allowlisted analytical fields and the resulting Q1 snapshot under the source licence. The public source has one feed and no historical prediction snapshots, so it cannot prove cross-source conflict resolution, event latency semantics, ETA accuracy, or business savings. Port stay is not shipment delay or berth waiting time. No employer data or credentials. Synthetic test fixtures must be labelled and excluded from real findings.

## Next step
Review the portfolio package and decide whether a dashboard would communicate a recurring operational question better than the executed notebooks. The repository starts private; public portfolio release follows data/license and content review.
