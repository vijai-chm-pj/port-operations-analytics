# Q1 2025 published data snapshot

This folder makes the four analysis notebooks runnable after cloning the repository.

The data flow is Fintraffic API → source CSV snapshot → canonical-event and exception CSV → notebooks.

`q1-2025/` contains the allowlisted analytical fields selected from a one-time Fintraffic Digitraffic Port Call API backfill for `[2025-01-01T00:00:00Z, 2025-04-01T00:00:00Z)`. The original JSON responses are retained locally and are not required to run the notebooks.

Read [`../docs/data-dictionary.md`](../docs/data-dictionary.md) for each file's grain and field definitions, and [`ATTRIBUTION.md`](ATTRIBUTION.md) for licence details.
