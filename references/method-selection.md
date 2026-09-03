# Method selection

## Two-sex cohort `lx-mx` core analysis

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

Use the initial cohort denominator, including individuals that die before adulthood. Report the fecundity unit, such as eggs, emerged offspring, or daughters.

Confirm that every unlisted individual-age fecundity event means observed or structural zero before passing `--confirm-unlisted-fecundity-zero`. If absence can mean a missed observation, stop and repair or model the observation process rather than silently converting absence to zero.

Index normalized age from zero. Confirm whether the source's first recorded day is age interval zero or one before mapping it; this changes the Euler-Lotka exponent and therefore `r`.

Do not call adult-only observations a complete cohort life table.

The bundled script does not calculate `s_xj`, `f_xj`, stage overlap, life expectancy, reproductive value, stable distributions, or population projections. Describe its output as a two-sex cohort `lx-mx` core analysis, not a full age-stage, two-sex analysis.

## Parasitoid event summary

Route here when observation intervals contain one or more of:

- hosts offered;
- parasitized hosts;
- hosts killed independently of parasitism;
- emerged female or male offspring.

Report parasitism rate, direct host-kill rate, total host-impact rate, emergence rate, female fraction, and per-individual totals when denominators are available.

Keep parasitism and direct host killing separate to prevent double counting.

These are descriptive event summaries. A survival-weighted net predation or parasitism rate requires complete age/stage-specific performance and survival histories and is outside v1.

## Descriptive-only route

Use descriptive output when data contain only lifetime totals, body size, longevity, or a partial adult window. State that population growth cannot be identified without cohort survival and age-specific reproduction.

## Outside v1

Do not force these inputs into a life table:

- genotype-frequency competition trajectories;
- Pool-seq or allele-frequency time series;
- stage-transition census matrices;
- density- or frequency-dependent fitness;
- local mate competition or inclusive-fitness models;
- censored survival requiring a survival model.

Propose a separate, explicitly approved extension for these analyses.
