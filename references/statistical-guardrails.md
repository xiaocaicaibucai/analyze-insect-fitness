# Statistical guardrails

## Experimental units

Identify the unit independently assigned to treatment. Individuals sharing a mother, cage, host patch, cohort, block, or experimental run may not be independent.

Bootstrap the independent unit. Never bootstrap offspring as independent replicates of their mother.

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

The v1 life-table script requires complete death endpoints. Route censoring to a survival-model extension.

## Bootstrap interpretation

Report the number of requested resamples, seed, resampling unit, and calculable fraction. Some resamples can contain no reproductive individual, so `r` and `T` have no finite estimate. Do not silently omit this fact.

Intervals from separate treatment groups are descriptive. Their overlap or non-overlap is not a treatment-difference test.

## Biological interpretation

Use `r` as the main demographic fitness summary when timing matters. Report `R0`, `lambda`, and `T` as complementary quantities.

For parasitoids, report demographic fitness and biocontrol performance separately. More daughters, higher parasitism, and greater host killing are related but not interchangeable.

For haplodiploid wasps, total offspring does not automatically equal evolutionary fitness. Sex allocation, mating opportunity, and reproductive value may require a separate model.

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
- conclusion boundary.
