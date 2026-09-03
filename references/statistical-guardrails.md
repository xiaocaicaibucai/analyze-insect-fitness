# Statistical guardrails

## Experimental units

Identify the unit independently assigned to treatment. Individuals sharing a mother, cage, host patch, cohort, block, or experimental run may not be independent.

Bootstrap the independent unit. Never bootstrap offspring as independent replicates of their mother.

Resample a complete individual or cluster history. Never resample daily rows independently because doing so breaks within-individual survival and reproduction dependence.

## Missingness and censoring

Keep these states distinct:

- observed zero;
- not observed;
- not applicable;
- confirmed death;
- escaped or lost;
- right-censored alive record;
- technical failure.

For parasitoid event summaries, calculate each rate only from rows with its required numerator and denominator. Report the eligible observation count for each metric; do not fill a missing count with zero.

The v2 life-table script requires complete death endpoints. Route censoring to a survival-model extension.

## Bootstrap interpretation

Report the number of requested resamples, seed, resampling unit, and calculable fraction. Some resamples can contain no reproductive individual, so `r` and `T` have no finite estimate. Do not silently omit this fact.

Prefer bootstrap to jackknife for nonlinear life-table parameters. For final reporting, check whether interval limits are stable at increasing resample counts; 100,000 is common in the TWOSEX-MSChart literature but is not a substitute for checking the design and sampling unit.

When any results are noncalculable, report `noncalculable_resamples` and `ci_scope`. An interval based only on finite results is conditional on calculable samples. If that fraction is scientifically consequential, do not use the interval for treatment inference; review cohort size, preadult mortality, reproductive success, and the chosen method.

Intervals from separate treatment groups are descriptive. Their overlap or non-overlap is not a treatment-difference test.

When direct contrasts are requested, freeze the design before resampling:

- independent treatments: resample each treatment independently;
- matched blocks or repeated experimental runs: resample shared replicate labels together;
- unresolved, partially matched, or nested designs: stop and use a model appropriate to that hierarchy.

A percentile interval for a pairwise difference is more direct than comparing separate intervals, but it is not automatically a hypothesis test and does not control multiplicity across many treatments or metrics.

## Biological interpretation

Use `r` as the main demographic fitness summary when timing matters. Report `R0`, `lambda`, and `T` as complementary quantities.

For parasitoids, report demographic fitness and biocontrol performance separately. More daughters, higher parasitism, and greater host killing are related but not interchangeable.

For haplodiploid wasps, total offspring does not automatically equal evolutionary fitness. Sex allocation, mating opportunity, and reproductive value may require a separate model.

The presence of males in a cohort file does not by itself make the Euler-Lotka growth rate sensitive to male longevity or fertility. Inspect the male-invariance diagnostic and use a mating-function model when male limitation is part of the claim.

## Reporting floor

Always report:

- raw and valid `n`;
- independent replicate count;
- effect estimate and interval;
- fecundity and time units;
- mapping and exclusion rules;
- error and warning counts;
- software version or script checksum;
- random seed;
- noncalculable bootstrap count and CI scope;
- conclusion boundary.
