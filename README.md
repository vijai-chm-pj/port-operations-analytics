# Port-call Visibility Data Quality Monitor

Independent maritime analytics portfolio. **Status: Q1 2025 source backfill, canonicalisation, exception analysis, source-forecast review, and four-method residual comparison are implemented.**

Repository: https://github.com/vijai-chm-pj/port-operations-analytics

## Objective
Determine whether a port-call event feed is reliable enough for downstream shipment-visibility workflows. The project traces missing, inconsistent, and ambiguous milestones back to the source record, quantifies their coverage, evaluates source-provided ETA/ETD fields with point-in-time controls, and tests whether statistical, fixed Quick ML, or Optimized ML residual corrections justify their complexity.

## Q1 2025 result

- Reconciled 7,135 raw API responses across 90 daily request chunks.
- Normalized 7,176 nested source rows into 7,172 canonical actual port-area events with source lineage.
- Resolved four duplicate actual-event rows without deleting their source evidence.
- Found 7,081 events eligible for completed-event coverage (98.73%); 91 events remain open source gaps because actual timestamps are incomplete.
- Found no negative actual-arrival to actual-departure sequence.
- Retained 6,893 arrival forecasts (96.54% coverage) and 6,799 departure forecasts (95.83% coverage) after excluding forecasts recorded after the actual milestone.
- Measured source-forecast P90 absolute error of 1.50 hours for arrival and 2.00 hours for departure in the eligible population.
- On March arrival events, Source, Quick ML, and Optimized ML produced MAE of 3.96/3.95/3.94 hours, median absolute error of 0.08/0.07/0.06, and P90 of 1.50/1.49/1.49. Optimized improved over Quick by only 0.003/0.001/0.001 hours before rounding.
- On March departure events, Source, Quick, and Optimized produced MAE of 2.18/2.14/2.14 hours, median absolute error of 0.17/0.07/0.07, and P90 of 2.00/1.97/1.97. Optimized was slightly worse than Quick before rounding by 0.001/0.005/0.008 hours.
- The statistical correction did not improve MAE or P90 consistently. The extra preprocessing and search add negligible arrival gain and slightly worse departure error metrics, so Q1 does not justify optimization complexity.

This establishes data completeness, consistency, and a descriptive baseline for the retained source forecasts. It does not measure shipment delay, proprietary model accuracy, operational performance, or customer impact.

## Read this project in order

1. **This README** — the question, result, and scope.
2. **[Notebook 01](notebooks/01_q1_2025_data_quality.ipynb)** — prove that the published Q1 source snapshot is complete enough to inspect.
3. **[Notebook 02](notebooks/02_q1_2025_exception_analysis.ipynb)** — explain duplicate events, missing milestones, and completed-event coverage.
4. **[Notebook 03](notebooks/03_q1_2025_forecast_quality.ipynb)** — evaluate forecast coverage, point-in-time eligibility, error, and source-level exceptions with SQL.
5. **[Notebook 04](notebooks/04_q1_2025_baseline_vs_ml.ipynb)** — compare Source, Statistical, fixed Quick ML, and Optimized ML on identical March events.
6. **[Methodology](docs/methodology.md)** — the exact data model, quality rules, canonicalisation decision, and forecast-evaluation contract.
7. **[Data dictionary](docs/data-dictionary.md)** — field-level reference for the derived outputs.

The notebooks are the main story. `src/` contains only the reusable ingestion and quality-build steps behind that story.

## Repository structure

```text
README.md                         project question, scope, and Q1 result
notebooks/
  01_q1_2025_data_quality.ipynb   reconcile the source and define the population
  02_q1_2025_exception_analysis.ipynb
                                  trace exceptions and report coverage
  03_q1_2025_forecast_quality.ipynb
                                  evaluate source forecasts with DuckDB SQL
  04_q1_2025_baseline_vs_ml.ipynb
                                  compare Source, Statistical, Quick, and Optimized forecasts
src/                              repeatable ingestion and quality-build logic
data/q1-2025/                     published Q1 CSV snapshot used by all four notebooks
docs/
  methodology.md                  rules and decisions behind the analysis
  data-dictionary.md              field-level reference
```

## Selected data source
Fintraffic Digitraffic / Portnet port calls: https://www.digitraffic.fi/en/marine-traffic/

Three historical sample windows returned 448 port calls with identifiable visited ports. A one-time Q1 2025 backfill collected 7,135 source response records in 90 daily chunks. The published `data/q1-2025/` CSV snapshot contains the selected source fields, request manifest, and analysis outputs used by the notebooks. One `portCallId` appeared in two source chunks because its nested port-area timestamps span two days; it is retained as a data-quality finding, not silently deduplicated. This does not certify full historical completeness.

Source: Fintraffic / digitraffic.fi, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Transformations include field selection, normalization, quality checks and aggregation. See [source terms](https://www.digitraffic.fi/en/terms-of-service/).

Repository code is available under the [MIT License](LICENSE). The Q1 data snapshot has separate [source attribution](data/ATTRIBUTION.md).

## Evidence
[`notebooks/01_q1_2025_data_quality.ipynb`](notebooks/01_q1_2025_data_quality.ipynb) reads the published Q1 CSV snapshot, reconciles the 7,135 source records to the manifest, profiles 7,176 nested port-area records, and reports missing actual timestamps, invalid sequences, and duplicate candidate keys. It does not silently deduplicate or label an `ATD - ATA` interval as a delay KPI.

[`notebooks/02_q1_2025_exception_analysis.ipynb`](notebooks/02_q1_2025_exception_analysis.ipynb) traces the exception patterns to a canonical event rule. It reconciles 7,176 published source rows to 7,172 canonical actual events, retains full lineage for four collapsed duplicate rows, and reports 7,081 eligible completed events (98.73% coverage).

[`notebooks/03_q1_2025_forecast_quality.ipynb`](notebooks/03_q1_2025_forecast_quality.ipynb) uses DuckDB SQL to select the latest forecast recorded before each actual milestone, prevent look-ahead leakage, and compare coverage and error across arrival, departure, lead-time, and port segments. The results describe the Fintraffic source fields only.

[`notebooks/04_q1_2025_baseline_vs_ml.ipynb`](notebooks/04_q1_2025_baseline_vs_ml.ipynb) compares Source, Statistical, fixed Quick ML, and Optimized ML on identical March rows. Optimized ML groups rare categories, transforms horizon with signed `log1p`, adds a negative-horizon flag and cyclical time features, and searches a fixed 16-configuration grid from January development to February validation before refitting on January–February.

To run the analysis locally:

```bash
python -m pip install -r requirements.txt
jupyter nbconvert --to notebook --execute --inplace notebooks/01_q1_2025_data_quality.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/02_q1_2025_exception_analysis.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/03_q1_2025_forecast_quality.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/04_q1_2025_baseline_vs_ml.ipynb
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
This is an analogue of visibility-data quality work, not a reproduction of any company's proprietary system. The original API JSON is retained locally; the repository publishes only allowlisted analytical fields and the resulting Q1 snapshot under the source licence. The public source has one feed and one retained forecast state per source row, so it cannot prove cross-source conflict resolution, forecast-revision performance, proprietary model accuracy, production generalisation, or business savings. One March arrival forecast has an 8,083.78-hour source error, making MAE sensitive to source anomalies; median and P90 provide the robust context. Port stay is not shipment delay or berth waiting time. No employer data or credentials. Synthetic test fixtures must be labelled and excluded from real findings.

## Next step
Use the four published notebooks as evidence for data-quality, root-cause, SQL, forecast monitoring, and evidence-based model selection during the application and interview process. Broader temporal coverage and forecast-revision history would be required before reconsidering optimization complexity.
