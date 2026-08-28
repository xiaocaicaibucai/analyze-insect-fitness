# Method selection

## Two-sex demographic life table

Route here only when the initial cohort is identifiable and each individual has a confirmed time origin, death endpoint, sex when known, and age-specific fecundity.

Primary outputs:

- net reproductive rate: `R0 = sum(lx * mx)`;
- intrinsic rate of increase: solve `sum(exp(-r * (x + 1)) * lx * mx) = 1`;
- finite rate of increase: `lambda = exp(r)`;
- mean generation time: `T = log(R0) / r` when defined;
- doubling time: `log(2) / r` when `r > 0`.

Use the initial cohort denominator, including individuals that die before adulthood. Report the fecundity unit, such as eggs, emerged offspring, or daughters.

Do not call adult-only observations a complete cohort life table.

## Parasitoid event summary

Route here when observation intervals contain one or more of:

- hosts offered;
- parasitized hosts;
- hosts killed independently of parasitism;
- emerged female or male offspring.

Report parasitism rate, direct host-kill rate, total host-impact rate, emergence rate, female fraction, per-individual totals, and per-observation-day totals when denominators are available.

Keep parasitism and direct host killing separate to prevent double counting.

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
