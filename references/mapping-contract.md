# Mapping contract

Create one JSON file per source sheet and freeze it before normalization.

## Wide cohort example

```json
{
  "status": "confirmed",
  "sheet": "01_规整宽表",
  "header_row": 1,
  "layout": "wide_cohort",
  "columns": {
    "individual_id": "individual_id",
    "treatment": "treatment",
    "biological_replicate": "block",
    "egg_date": "egg_date",
    "larva_date": "larva_date",
    "pupa_date": "pupa_date",
    "adult_emergence_date": "adult_emergence_date",
    "sex": "sex",
    "death_stage": "death_stage",
    "death_date": "death_date",
    "record_status": "record_status"
  },
  "wide_metrics": [
    {
      "source_pattern": "^eggs_D(?P<day>\\d+)$",
      "target": "fecundity",
      "age_origin": "adult",
      "day_group": "day"
    }
  ],
  "age_offset": -1,
  "value_maps": {
    "sex": {
      "F": "female",
      "M": "male"
    }
  },
  "missing_tokens": ["", "NA", "N/A"],
  "date_fields": ["egg_date", "larva_date", "pupa_date", "adult_emergence_date", "death_date"],
  "numeric_fields": [],
  "exclude_repeated_header": true
}
```

## Event-long example

```json
{
  "status": "confirmed",
  "sheet": "02_事件纵表",
  "header_row": 1,
  "layout": "event_long",
  "columns": {
    "individual_id": "WaspID",
    "treatment": "Trt",
    "biological_replicate": "Replicate",
    "observation_date": "obs_date",
    "age": "age_d",
    "stage": "stage",
    "alive": "Alive",
    "hosts_offered": "Hosts_offered",
    "parasitized": "Parasitized",
    "host_killed": "Host_killed",
    "female_offspring": "F_offspring",
    "male_offspring": "M_offspring",
    "note": "note"
  },
  "value_maps": {
    "alive": {
      "Y": "yes",
      "N": "no"
    }
  },
  "missing_tokens": ["", "NA", "N/A"],
  "date_fields": ["observation_date"],
  "numeric_fields": ["age", "hosts_offered", "parasitized", "host_killed", "female_offspring", "male_offspring"],
  "age_origin": "adult",
  "age_offset": 0,
  "exclude_repeated_header": true
}
```

## Contract rules

- Set `status` to `confirmed` only after the user or study documentation resolves blocking semantics.
- Use canonical fields as keys and exact source headers as values.
- Put all code harmonization in `value_maps`; preserve the raw value through source provenance and issues.
- List only confirmed missing tokens. A dash may mean zero, not applicable, missing, or not observed.
- List all numeric canonical fields in `numeric_fields`. Negative counts are errors.
- List date fields in `date_fields`. Supply `default_year` only when the year is known from study metadata.
- Use named regex groups for wide metrics. The default examples use `day`.
- Set `age_offset` explicitly after confirming the source convention. Use `-1` only when source `day 1` denotes the first interval and must become canonical age `0`; use `0` when the source is already zero-based or records true completed age. Wide-metric specifications may override the sheet-level offset.
- Do not combine female and male offspring into one value unless the source definition explicitly supports it.
