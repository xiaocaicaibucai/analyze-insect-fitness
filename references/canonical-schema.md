# Canonical schema

Use two linked flat files. Keep source provenance on every normalized record.

## `individuals.csv`

One row represents one focal insect from the initial cohort.

| Field | Meaning | Requirement |
|---|---|---|
| `individual_id` | Unique focal individual identifier | Required |
| `treatment` | Confirmed treatment label | Required for comparisons |
| `biological_replicate` | Independent cage, block, mother, cohort, or run | Required for replicate bootstrap |
| `technical_replicate` | Non-independent measurement repeat | Optional |
| `egg_date` | Egg-laying or cohort-entry date | Required when egg is time origin |
| `larva_date` | First larval date | Optional |
| `pupa_date` | First pupal date | Optional |
| `adult_emergence_date` | Adult emergence date | Required for adult-relative daily data |
| `sex` | `female`, `male`, or empty if unknown | Required for two-sex interpretation |
| `death_stage` | Stage at death or final observed stage | Recommended |
| `death_date` | Date of confirmed death | Required for complete cohort life table |
| `record_status` | `complete`, `censored`, `lost`, `technical_failure`, or confirmed equivalent | Required |
| `source_sheet` | Source worksheet name | Required |
| `source_row` | 1-based source row | Required |

Do not put a censored date into `death_date`. Record the final observation separately and route to a censoring-aware extension.

## `observations.csv`

One row represents one observation interval for one focal insect.

| Field | Meaning |
|---|---|
| `individual_id` | Link to `individuals.csv` |
| `treatment` | Confirmed treatment |
| `biological_replicate` | Confirmed independent unit |
| `observation_date` | Observation date when available |
| `age` | Zero-based numeric age or interval index after the confirmed source-to-canonical offset |
| `age_origin` | `cohort`, `egg`, `larva`, `pupa`, `adult`, or explicit custom origin |
| `stage` | Stage at observation |
| `sex` | Sex at observation when known |
| `alive` | `yes`, `no`, or empty when not assessed |
| `fecundity` | Offspring produced by the focal reproductive parent during this parent's age interval, using the confirmed offspring definition |
| `hosts_offered` | Hosts made available during the interval |
| `parasitized` | Hosts confirmed parasitized |
| `host_killed` | Hosts killed without double-counting `parasitized` |
| `female_offspring` | Emerged female offspring |
| `male_offspring` | Emerged male offspring |
| `record_status` | Interval status or censoring marker |
| `note` | Short source note |
| `source_sheet` | Source worksheet name |
| `source_row` | 1-based source row |
| `source_column` | Source column for wide-to-long records; empty for event-long records |

Store counts as non-negative numeric values. Leave unresolved values empty and record them in `issues.csv`; never store symbols such as `-`, `NA`, or `未统计` in numeric canonical fields.

Preserve the original day label in source provenance. A source field called `day 1` is not automatically canonical age `1`: confirm whether it represents the first interval after cohort entry (canonical age `0`) or true completed age `1`, then record the transformation in the mapping contract.

## `issues.csv`

Use these fields:

- `severity`: `error` or `warning`;
- `source_sheet`, `source_row`, `source_column`;
- `code`: stable machine-readable issue code;
- `raw_value`;
- `message`;
- `suggested_action`.

Any error blocks formal calculation. Warnings remain in the audit trail.
