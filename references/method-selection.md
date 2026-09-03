# Method selection

## Cohort Euler-Lotka core analysis

Route here only when the initial cohort is identifiable and each individual has a confirmed time origin, death endpoint, sex when known, and age-specific fecundity.

Read [literature-foundation.md](literature-foundation.md) before selecting this route for formal calculation or reporting.

Primary outputs:

- age-specific survival: `lx = n_alive_at_x / initial_cohort_n`;
- age-specific maternity: `lx_mx = fecundity_at_x / initial_cohort_n`;
- age-specific fecundity: `mx = lx_mx / lx` when `lx > 0`;
- net reproductive rate: `R0 = sum(lx * mx)`;
- intrinsic rate of increase: solve `sum(exp(-r * (x + 1)) * lx * mx) = 1`;
- finite rate of increase: `lambda = exp(r)`;
- mean generation time: `T = log(R0) / r` when defined;
- doubling time: `log(2) / r` when `r > 0`.

Choose the offspring estimand before calculation:

- `cohort_total` reads the canonical `fecundity` field;
- `female_line` restricts the analysis cohort to confirmed females and reads daughters only; every enrolled individual's sex must be known so preadult deaths are not silently discarded;
- `sexed_total` sums female and male offspring only where both are recorded.

Do not choose an estimand merely because its column is populated. Match it to the biological claim and report it. For haplodiploid parasitoids, total offspring and female-line replacement can lead to different conclusions.

For `cohort_total` and `sexed_total`, use the complete initial cohort denominator, including individuals that die before adulthood. For `female_line`, use the confirmed female analysis cohort only and require known sex for every enrolled individual. Report the fecundity unit, such as eggs, emerged offspring, or daughters.

Confirm that every unlisted individual-age fecundity event means observed or structural zero before passing `--confirm-unlisted-fecundity-zero`. If absence can mean a missed observation, stop and repair or model the observation process rather than silently converting absence to zero.

Index normalized age from zero. Confirm whether the source's first recorded day is age interval zero or one before mapping it; this changes the Euler-Lotka exponent and therefore `r`.

Do not call adult-only observations a complete cohort life table.

The bundled script does not calculate `s_xj`, `f_xj`, stage overlap, life expectancy, reproductive value, stable distributions, mating functions, or population projections. Describe its output as a cohort Euler-Lotka core analysis, not a full age-stage, mating-limited two-sex analysis.

Read `male_invariance_diagnostics.csv`. If changing recorded male longevity leaves `r` and `R0` unchanged, state that male demography is not represented in the growth equation. Do not use the presence of male records alone as evidence of a mating-limited model.

`cohort_total` follows the published Chi `lx-mx` core equations. The bundled golden fixture checks equation-level compatibility only; it does not certify complete parity with every version or option of TWOSEX-MSChart.

## Treatment contrasts

Use `--contrast-design independent` only for independently assigned treatment groups. Use `paired_by_replicate` only when the same block or replicate labels occur in every treatment and represent genuine matching. Leave the setting as `none` when the design is unresolved.

Report the direction as `treatment_a - treatment_b`, the calculable resample count, and whether the interval is conditional. These percentile intervals contain no multiplicity correction and should not be described as publication-grade treatment tests without a confirmed inference plan.

## Parasitoid event summary

Route here when observation intervals contain one or more of:

- hosts offered;
- parasitized hosts;
- hosts killed independently of parasitism;
- emerged female or male offspring.

Report parasitism rate, direct host-kill rate, total host-impact rate, emergence rate, female fraction, and per-individual totals when denominators are available.

Keep parasitism and direct host killing separate to prevent double counting.

These are descriptive event summaries. A survival-weighted net predation or parasitism rate requires complete age/stage-specific performance and survival histories and is outside v2.

## Descriptive-only route

Use descriptive output when data contain only lifetime totals, body size, longevity, or a partial adult window. State that population growth cannot be identified without cohort survival and age-specific reproduction.

## Outside v2

Do not force these inputs into a life table:

- genotype-frequency competition trajectories;
- Pool-seq or allele-frequency time series;
- stage-transition census matrices;
- density- or frequency-dependent fitness;
- local mate competition or inclusive-fitness models;
- censored survival requiring a survival model.

Propose a separate, explicitly approved extension for these analyses.
