---
name: analyze-insect-fitness
description: Inspect, map, normalize, route, calculate, and report insect fitness data from XLSX, XLSM, CSV, or TSV files. Use when Codex needs to整理昆虫或寄生蜂原始表格, reconcile wide/long/messy life-history records, propose traceable field mappings, calculate age-stage two-sex demographic metrics such as r, lambda, R0, and T, summarize parasitoid parasitism or host-killing performance, audit replicate and missing-value semantics, or prepare reproducible fitness-analysis outputs. Also trigger on requests mentioning 昆虫适合度、两性生命表、生命表参数、寄生蜂适合度、寄生率、寄主致死率、种群增长率、TWOSEX-MSChart 数据整理, or AI-assisted routing of insect experimental data.
---

# Analyze Insect Fitness

## Goal

Turn heterogeneous insect life-history tables into traceable canonical records, then run only calculations supported by the confirmed design and available data.

Keep AI decisions and numerical calculations separate:

- Use AI to understand context, propose mappings, identify ambiguities, and explain method choices.
- Use bundled scripts to inspect, normalize, calculate, bootstrap, and export reproducible results.
- Never let AI silently redefine zero, missingness, death, censoring, experimental units, time origin, sex ratio, or offspring type.

## Core workflow

### 1. Establish the scientific contract

Confirm the focal species or system, treatment comparison, intended meaning of fitness, experimental unit, observation unit, primary endpoint, time origin, and intended use of the result.

Distinguish these targets:

- Demographic fitness: population growth from survival, development, and reproduction.
- Individual reproductive performance: lifetime or interval offspring contribution.
- Parasitoid biocontrol performance: parasitism, host killing, emergence, and female offspring.
- Relative evolutionary fitness: competition or allele-frequency change; do not analyze this in v1.

Do not start formal calculation while any field that changes the analysis remains unresolved.

### 2. Preserve and profile the input

Keep the source file unchanged. Work in a separate output directory.

Run:

```bash
python3 scripts/profile_input.py INPUT_FILE --output-dir OUTPUT_DIR/profile
```

For XLSX input, use a Python runtime with `openpyxl`. In Codex desktop, load workspace dependencies and prefer the bundled Python runtime. If `openpyxl` is unavailable, use the spreadsheet skill to export the relevant sheet as CSV without altering the original.

Legacy `.xls` files are not read directly in v1. Convert them to `.xlsx` or CSV while preserving the original file.

Read `input_profile.json`, the sheet previews, and each draft mapping. Treat every generated mapping as a proposal, never as approval.

### 3. Review blocking ambiguities

Explicitly resolve:

- Whether `0` means observed none, structural zero, or not observed.
- Whether blank, `NA`, `-`, `未记`, and `未统计` share the same meaning.
- Whether a record denotes death, escape, censoring, or technical failure.
- Which column identifies the independent biological replicate.
- Whether time starts at egg laying, hatching, emergence, or treatment.
- Whether reproduction means eggs, parasitized hosts, emerged offspring, daughters, or all offspring.
- Whether sex ratio is male fraction or female fraction.
- Whether individual identifiers are unique across sheets, batches, and treatments.

Stop and ask the user when these cannot be determined from the source or study design.

### 4. Freeze a mapping contract

Read [mapping-contract.md](references/mapping-contract.md) and [canonical-schema.md](references/canonical-schema.md).

Edit a draft mapping into an explicit JSON contract. Preserve:

- source sheet and 1-based header row;
- source-to-canonical column mappings;
- value dictionaries for treatment, sex, stage, and status;
- accepted missing tokens;
- date and numeric fields;
- wide daily-metric patterns and their time origin;
- repeated-header and duplicate-ID policy.

Never include an ambiguous token in `missing_tokens` merely to make normalization succeed.

### 5. Normalize deterministically

Run:

```bash
python3 scripts/normalize_records.py INPUT_FILE \
  --mapping CONFIRMED_MAPPING.json \
  --output-dir OUTPUT_DIR/canonical
```

Inspect `individuals.csv`, `observations.csv`, `issues.csv`, and `provenance.json` before calculation. Resolve all error-severity issues. Preserve warning-severity issues in the final audit trail.

### 6. Route the data

Read [method-selection.md](references/method-selection.md).

Use these v1 routes:

- Complete cohort plus dated survival/death and age-specific fecundity → two-sex demographic life table.
- Adult parasitoid event records with offered/parasitized/killed hosts or sexed offspring → parasitoid performance summary.
- Only lifetime totals, body size proxies, ambiguous dates, or unresolved replicate structure → descriptive output or request clarification; do not manufacture a life table.
- Competition frequencies, MPM/IPM, Pool-seq, or genomic selection → report as outside v1 and propose a separate extension.

### 7. Calculate only after authorization

For cohort life tables:

```bash
python3 scripts/life_table.py \
  --individuals OUTPUT_DIR/canonical/individuals.csv \
  --observations OUTPUT_DIR/canonical/observations.csv \
  --output-dir OUTPUT_DIR/life_table \
  --bootstrap-unit biological_replicate \
  --resamples 10000 \
  --seed 20260826
```

For parasitoid event data:

```bash
python3 scripts/parasitoid_metrics.py \
  --observations OUTPUT_DIR/canonical/observations.csv \
  --output-dir OUTPUT_DIR/parasitoid \
  --bootstrap-unit biological_replicate \
  --resamples 10000 \
  --seed 20260826
```

Parasitoid rates use only observation rows containing every required numerator and denominator. Missing counts remain missing, and the result reports `valid_n`; they are never converted to observed zeros.

Use individual-level bootstrap only when individuals are the independent experimental units. Use replicate-level bootstrap when cages, blocks, mothers, cohorts, or experimental runs are the independent units.

### 8. Audit and report

Read [statistical-guardrails.md](references/statistical-guardrails.md).

Report:

- sample size and experimental unit;
- estimate, confidence interval, and bootstrap-calculable fraction;
- exact fitness definition and time unit;
- missing, censored, excluded, duplicate, and unresolved records;
- whether inference is descriptive or supports a treatment comparison;
- all mapping, normalization, software, parameter, and random-seed metadata.

Do not infer significance by comparing separate confidence intervals. Do not treat individual offspring as independent replicates of the mother or cage.

## Required outputs

Create a compact reproducible package:

```text
profile/
  input_profile.json
  mapping_proposals/
  previews/
mapping.json
canonical/
  individuals.csv
  observations.csv
  issues.csv
  provenance.json
results/
  metrics.csv
  age_table.csv or individual_metrics.csv
  methods.json
```

Keep the original input outside this package or include it read-only with its checksum.

## Stop conditions

Pause before calculation when:

- treatment, time origin, outcome definition, or experimental unit is unclear;
- treatment and batch are inseparable;
- a key group has fewer than three valid biological replicates;
- exclusion or reinterpretation could change the conclusion;
- deaths and censoring cannot be distinguished;
- offspring type or sex-ratio denominator is ambiguous;
- normalization still contains error-severity issues.

## Scope boundary

Version 1 supports data intake, canonicalization, cohort demographic metrics, and parasitoid event summaries. Keep matrix population models, competition selection coefficients, genomic time-series inference, density-dependent models, and publication-grade treatment inference outside v1 unless the user explicitly approves an extension.
