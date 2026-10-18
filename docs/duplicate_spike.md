# Duplicate-spike detection

The brief's Task E asks for detection of duplicate spikes. Duplicates here are repeated placements: the same product
shown twice in the same position type on one page, or again on a later page (pagination drift). Deduplication keeps
the first occurrence and drops the rest; this check watches how many it has to drop.

## Measurement
Each target-hour stores `duplicate_count` in `target_hour_status`: the placements dropped at the deduplication stage
(`duplicate_placement` plus `cross_page_duplicate`). `NULL` means not measured (rows written before the column
existed, or an hour that never ran). For one hour, over the enabled targets:

| Quantity | Definition |
|---|---|
| `duplicates` | sum of `duplicate_count` |
| `kept` | sum of `row_count` (placements kept) |
| `rate` | `duplicates / (kept + duplicates)` |

`gold_hour_summary` shows `duplicates` and `duplicate_rate_pct` for every hour.

## When it triggers
An hour is a spike when all three hold:

1. `duplicates >= 10` (`duplicate_spike_min_count`): a handful of repeats is normal.
2. `rate >= 2%` (`duplicate_spike_min_rate`): the repeats are a real share of the units seen.
3. `rate >= 5x` the rolling median rate of earlier complete hours (`duplicate_spike_multiplier`), where the baseline is
   the up to six (`duplicate_baseline_runs`) most recent earlier hours in which every target finished (`success` or
   `zero_result`) and was measured. It applies once three such hours exist; before that, rules 1 and 2 decide alone.

The check never reports an hour that is still running, or one where any target has no measurement, so a half-finished
hour cannot look like a spike. The thresholds are in `config/settings.yaml` under `alerts` and are my own defaults;
they have not been tuned on real data.

## What happens
A spike is one more trigger on the hour's incident (`duplicate_spike`, WARNING). It is aggregated with any other
trigger for the same hour, deduplicated and cooled down like the others, and resolved with one recovery email when a
rerun or backfill no longer shows it. The email gives the counts, the rate, the threshold that applied (with the
baseline when it was the deciding rule), the affected targets, and a next step that points to the dashboard
Quarantine tab and the raw pages.

## Tests
`tests/test_duplicate_spike.py`, using the fixture `tests/fixtures/duplicate_spike.html`:

- a spike after three clean hours is detected, with exact counts (15 duplicates of 45 units, 33.3%), the email text,
  the quarantine evidence and the Gold hour summary;
- the generated 50-keyword mock hour (one duplicate) is not a spike;
- 3 duplicates at a 33% rate do not alert (below the count floor);
- a 10% hour after a 4% baseline does not alert, while a 33% hour does (the baseline rule);
- with fewer than three baseline hours the fixed thresholds decide;
- a clean rerun resolves the incident and sends one recovery;
- a running or partly measured hour is never reported.

## Limits
Only duplicates removed by deduplication are counted; records rejected for other reasons are in the quarantine tables.
The check looks at one hour at a time, with no seasonality.


## Reproducible dashboard demonstration

I use `python -m scripts.demo_duplicate_spike` to create a controlled duplicate-spike incident in a separate demo database. The script uses a fake mailer and does not send real email or change the main pipeline database. I open that database in a separate Streamlit process by setting `DB_PATH` for that process. The dashboard evidence is saved as `screenshots/15_duplicate_spike_incident.png`.
