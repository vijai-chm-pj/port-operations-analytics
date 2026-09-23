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

The original API JSON remains local-only. The repository includes a Q1 CSV snapshot with allowlisted analytical fields, request windows, source checksums, and derived outputs so all four notebooks can run after cloning.

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

## Source-forecast evaluation

ETA and ETD are evaluated separately at the canonical-event grain. A forecast is eligible only when its forecast value, recorded timestamp, and corresponding actual milestone are present, and the forecast was recorded before or at the actual milestone. If duplicate source rows map to one canonical event, the latest eligible forecast is selected with `ROW_NUMBER()`; full source lineage remains available for review.

| Metric | Definition |
|---|---|
| Forecast coverage | Eligible forecasts divided by canonical events with the corresponding actual milestone |
| Signed error | `actual_time - forecast_time`; positive means actual occurred later than forecast |
| Absolute error | Absolute value of signed error |
| Lead time | `actual_time - forecast_recorded_time` |
| Post-actual leakage | Forecast recorded after the actual milestone; excluded from error metrics |

The ±6, ±12, and ±24 hour bands are descriptive review thresholds, not service-level targets.

### Q1 2025 source-forecast outcome

| Milestone | Actual events | Eligible forecasts | Coverage | Median absolute error | P90 absolute error |
|---|---:|---:|---:|---:|---:|
| Arrival | 7,140 | 6,893 | 96.54% | 0.08 hours | 1.50 hours |
| Departure | 7,095 | 6,799 | 95.83% | 0.15 hours | 2.00 hours |

The point-in-time rule excludes 168 arrival forecasts and 255 departure forecasts recorded after the actual milestone. Error by lead time is non-monotonic, especially for forecasts retained seven or more days before actual, so source timestamp semantics require investigation before the values are treated as predictive performance.

## Residual-model experiment

The experiment asks whether a correction learned from earlier events improves the retained source forecast. Arrival and departure are trained separately. Every method is evaluated on the same point-in-time eligible March rows.

| Element | Definition |
|---|---|
| Target | `actual_time - source_forecast_time`, in hours |
| Adjusted forecast | `source_forecast_time + predicted_residual` |
| Statistical correction | Median train residual by `port_code + vessel_type_code + forecast_horizon_band`; fall back to the milestone's global train median |
| Quick ML | Fixed histogram gradient boosting with `absolute_error`, ordinal categorical encoding, and raw horizon/calendar features |
| Optimized ML | Histogram gradient boosting with rare-category grouping, signed `log1p` horizon, negative-horizon flag, and cyclical hour/weekday features |
| Model selection | Fixed 16-configuration grid using January development and February validation through `PredefinedSplit`; loss remains `absolute_error` |
| Final evaluation | Refit the selected Optimized pipeline on January–February, then evaluate March alongside the fixed Quick model |

Actual timestamps define the target and time split but are not model features. Actual-derived lead time, actual provenance, source chunk, and post-milestone fields are excluded. Milestone is the experiment partition, not a feature. Categorical encoders and rare-category grouping are fitted inside the training pipeline; March is not used for preprocessing or parameter selection.

The grid contains two values each for learning rate, maximum leaf nodes, minimum samples per leaf, and L2 regularization: 16 configurations per milestone. Arrival selected `0.03 / 15 / 50 / 1.0` with February validation MAE of 0.58 hours. Departure selected `0.08 / 15 / 20 / 0.0` with validation MAE of 1.56 hours.

### March 2025 comparison

| Milestone | Method | Events | MAE | Median absolute error | P90 absolute error |
|---|---|---:|---:|---:|---:|
| Arrival | Source forecast | 2,408 | 3.96 hours | 0.08 hours | 1.50 hours |
| Arrival | Statistical correction | 2,408 | 4.03 hours | 0.07 hours | 1.50 hours |
| Arrival | Quick ML | 2,408 | 3.95 hours | 0.07 hours | 1.49 hours |
| Arrival | Optimized ML | 2,408 | 3.94 hours | 0.06 hours | 1.49 hours |
| Departure | Source forecast | 2,375 | 2.18 hours | 0.17 hours | 2.00 hours |
| Departure | Statistical correction | 2,375 | 2.22 hours | 0.08 hours | 2.05 hours |
| Departure | Quick ML | 2,375 | 2.14 hours | 0.07 hours | 1.97 hours |
| Departure | Optimized ML | 2,375 | 2.14 hours | 0.07 hours | 1.97 hours |

For arrival, Optimized ML improves MAE, median absolute error, and P90 over Source by 0.013/0.019/0.011 hours and over Quick by only 0.003/0.001/0.001 hours before rounding. For departure, Optimized improves those metrics over Source by 0.038/0.095/0.026 hours but is worse than Quick by 0.001/0.005/0.008 hours. The statistical correction improves the median but does not improve MAE or P90 consistently.

The extra preprocessing and 16-configuration search provide negligible arrival gain and slightly worse departure error metrics relative to Quick ML. The Q1 result does not justify optimization complexity.

The source contains one retained forecast state per row rather than a full revision history. One March arrival forecast has an 8,083.78-hour source error, so MAE is sensitive to source anomalies; median and P90 provide more robust context for the typical and tail populations.

## Limits

- One public source does not establish cross-source agreement.
- The source contains one retained forecast state per row rather than a complete revision history, so accuracy evolution and reporting-latency performance are out of scope. The source-forecast evaluation is a descriptive baseline; the residual-model experiment is limited to this one-quarter sample.
- The January–March experiment covers one quarter and does not establish production generalisation or stability across seasons and source changes.
- `ATD - ATA` is not shipment delay, berth waiting time, cargo handling time, port performance, or customer impact.
- Missing milestones are traced to the source event, but the upstream operational cause cannot be established from this dataset.
