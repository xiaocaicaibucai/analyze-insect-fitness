#!/usr/bin/env python3
"""Calculate auditable cohort demographic metrics from canonical records."""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any

from _shared import file_sha256, quantile, read_csv_records, write_csv, write_json


METRIC_ORDER = ["r", "lambda", "R0", "T", "doubling_time"]
OFFSPRING_MODES = {
    "cohort_total": {
        "fields": ["fecundity"],
        "description": "Confirmed total offspring or eggs recorded in the canonical fecundity field.",
    },
    "female_line": {
        "fields": ["female_offspring"],
        "description": (
            "Confirmed female offspring produced by a confirmed female-only analysis cohort. "
            "Every enrolled individual's sex must be known so preadult deaths are not silently discarded."
        ),
    },
    "sexed_total": {
        "fields": ["female_offspring", "male_offspring"],
        "description": "Female plus male offspring from rows where both sex-specific counts are present.",
    },
}
ORIGIN_DATE_FIELDS = {
    "cohort": "egg_date",
    "egg": "egg_date",
    "larva": "larva_date",
    "pupa": "pupa_date",
    "adult": "adult_emergence_date",
}


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_optional_float(value: Any, field: str) -> tuple[float | None, str | None]:
    if value in (None, ""):
        return None, None
    number = as_float(value)
    if number is None:
        return None, f"{field} must be a finite number when present."
    if number < 0:
        return None, f"{field} must be non-negative."
    return number, None


def offspring_value(observation: dict[str, str], mode: str) -> tuple[float | None, str | None]:
    fields = OFFSPRING_MODES[mode]["fields"]
    values: list[float | None] = []
    for field in fields:
        value, error = parse_optional_float(observation.get(field), field)
        if error:
            return None, error
        values.append(value)
    if mode == "sexed_total":
        if all(value is None for value in values):
            return None, None
        if any(value is None for value in values):
            return None, "sexed_total requires both female_offspring and male_offspring on each recorded row."
        return sum(value for value in values if value is not None), None
    return values[0], None


def analysis_ids_for_mode(
    ids: list[str],
    individuals: dict[str, dict[str, str]],
    mode: str,
) -> list[str]:
    if mode != "female_line":
        return ids
    unknown = [
        individual_id
        for individual_id in ids
        if (individuals[individual_id].get("sex") or "").strip().casefold() not in {"female", "male"}
    ]
    if unknown:
        preview = ", ".join(repr(value) for value in unknown[:10])
        remainder = f" and {len(unknown) - 10} more" if len(unknown) > 10 else ""
        raise ValueError(
            "female_line requires confirmed sex for every enrolled individual so immature deaths are not "
            f"silently excluded; unresolved IDs: {preview}{remainder}"
        )
    female_ids = [
        individual_id
        for individual_id in ids
        if (individuals[individual_id].get("sex") or "").strip().casefold() == "female"
    ]
    if not female_ids:
        raise ValueError("female_line requires at least one confirmed female in every treatment.")
    return female_ids


def as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def safe_exp(value: float) -> float:
    if value > 700:
        return math.inf
    if value < -745:
        return 0.0
    return math.exp(value)


def solve_r(contributions: dict[int, float]) -> float | None:
    if not contributions or sum(contributions.values()) <= 0:
        return None

    def equation(rate: float) -> float:
        return sum(safe_exp(-rate * (age + 1)) * value for age, value in contributions.items()) - 1.0

    if abs(equation(0.0)) < 1e-12:
        return 0.0
    lower, upper = -1.0, 1.0
    lower_value, upper_value = equation(lower), equation(upper)
    while lower_value < 0 and lower > -20:
        lower *= 2
        lower_value = equation(lower)
    while upper_value > 0 and upper < 20:
        upper *= 2
        upper_value = equation(upper)
    if not (lower_value >= 0 and upper_value <= 0):
        return None
    for _ in range(200):
        midpoint = (lower + upper) / 2
        value = equation(midpoint)
        if abs(value) < 1e-12:
            return midpoint
        if value > 0:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2


def calculate_sample(
    sampled_ids: list[str],
    lifetimes: dict[str, int],
    offspring_by_id: dict[str, list[tuple[int, float]]],
) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    cohort_size = len(sampled_ids)
    if cohort_size == 0:
        return {metric: None for metric in METRIC_ORDER}, []
    maximum_age = max(
        [lifetimes[individual_id] for individual_id in sampled_ids]
        + [age for individual_id in sampled_ids for age, _ in offspring_by_id.get(individual_id, [])],
        default=0,
    )
    age_rows: list[dict[str, Any]] = []
    contributions: dict[int, float] = {}
    for age in range(maximum_age + 1):
        alive_count = sum(lifetimes[individual_id] >= age for individual_id in sampled_ids)
        fecundity_total = sum(
            value
            for individual_id in sampled_ids
            for event_age, value in offspring_by_id.get(individual_id, [])
            if event_age == age
        )
        lx = alive_count / cohort_size
        lx_mx = fecundity_total / cohort_size
        mx = lx_mx / lx if lx > 0 else None
        contributions[age] = lx_mx
        age_rows.append(
            {
                "age": age,
                "n_alive": alive_count,
                "lx": lx,
                "fecundity_total": fecundity_total,
                "mx": mx,
                "lx_mx": lx_mx,
            }
        )

    r0 = sum(contributions.values())
    rate = solve_r(contributions)
    finite_rate = math.exp(rate) if rate is not None else None
    generation_time = math.log(r0) / rate if rate not in (None, 0.0) and r0 > 0 else None
    doubling_time = math.log(2) / rate if rate is not None and rate > 0 else None
    metrics = {
        "r": rate,
        "lambda": finite_rate,
        "R0": r0,
        "T": generation_time,
        "doubling_time": doubling_time,
    }
    return metrics, age_rows


def converted_event_age(
    observation: dict[str, str],
    individual: dict[str, str],
    time_origin_field: str,
) -> tuple[int | None, str | None]:
    raw_age = as_float(observation.get("age"))
    if raw_age is None or raw_age < 0 or not raw_age.is_integer():
        return None, "Observation age must be a non-negative integer."
    age = int(raw_age)
    origin = (observation.get("age_origin") or "").strip().casefold()
    if origin in {"cohort", "egg"} and time_origin_field == "egg_date":
        return age, None
    origin_field = ORIGIN_DATE_FIELDS.get(origin)
    if not origin_field:
        return None, f"Unsupported or missing age_origin {origin!r}."
    if origin_field == time_origin_field:
        return age, None
    start = as_date(individual.get(time_origin_field))
    event_origin = as_date(individual.get(origin_field))
    if start is None or event_origin is None:
        return None, f"Cannot convert {origin!r} age without {time_origin_field} and {origin_field}."
    offset = (event_origin - start).days
    if offset < 0:
        return None, f"{origin_field} precedes {time_origin_field}."
    return offset + age, None


def prepare_data(
    individual_path: Path,
    observation_path: Path,
    time_origin_field: str,
    offspring_mode: str,
) -> tuple[
    dict[str, dict[str, str]],
    dict[str, int],
    dict[str, list[tuple[int, float]]],
    dict[str, list[str]],
]:
    individual_rows = read_csv_records(individual_path)
    observation_rows = read_csv_records(observation_path)
    if not individual_rows:
        raise ValueError("individuals.csv contains no records.")

    individuals: dict[str, dict[str, str]] = {}
    lifetimes: dict[str, int] = {}
    errors: list[str] = []
    for row_number, row in enumerate(individual_rows, start=2):
        individual_id = (row.get("individual_id") or "").strip()
        if not individual_id:
            errors.append(f"individuals.csv row {row_number}: missing individual_id")
            continue
        if individual_id in individuals:
            errors.append(f"individuals.csv row {row_number}: duplicate individual_id {individual_id!r}")
            continue
        status = (row.get("record_status") or "").strip().casefold()
        complete_endpoint = status in {"complete", "dead", "observed_death", "死亡", "完整"} or status.startswith("dead_")
        if not complete_endpoint:
            errors.append(
                f"individuals.csv row {row_number}: record_status {status!r} is not a confirmed complete death endpoint"
            )
        start = as_date(row.get(time_origin_field))
        death = as_date(row.get("death_date"))
        if start is None or death is None:
            errors.append(
                f"individuals.csv row {row_number}: valid {time_origin_field} and death_date are required"
            )
            continue
        lifetime = (death - start).days
        if lifetime < 0:
            errors.append(f"individuals.csv row {row_number}: death precedes time origin")
            continue
        individuals[individual_id] = row
        lifetimes[individual_id] = lifetime

    offspring_by_id: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row_number, observation in enumerate(observation_rows, start=2):
        individual_id = (observation.get("individual_id") or "").strip()
        offspring, offspring_error = offspring_value(observation, offspring_mode)
        if offspring_error:
            errors.append(f"observations.csv row {row_number}: {offspring_error}")
            continue
        if offspring is None:
            continue
        individual = individuals.get(individual_id)
        if individual is None:
            errors.append(f"observations.csv row {row_number}: unknown individual_id {individual_id!r}")
            continue
        if offspring > 0 and (individual.get("sex") or "").strip().casefold() == "male":
            errors.append(
                f"observations.csv row {row_number}: positive offspring is attached to male individual {individual_id!r}"
            )
            continue
        age, error = converted_event_age(observation, individual, time_origin_field)
        if error or age is None:
            errors.append(f"observations.csv row {row_number}: {error}")
            continue
        if age > lifetimes[individual_id]:
            errors.append(
                f"observations.csv row {row_number}: fecundity age {age} exceeds confirmed lifetime {lifetimes[individual_id]}"
            )
            continue
        offspring_by_id[individual_id].append((age, offspring))

    if errors:
        preview = "\n".join(f"- {item}" for item in errors[:30])
        remainder = f"\n- ... and {len(errors) - 30} more" if len(errors) > 30 else ""
        raise ValueError(f"Life-table eligibility checks failed:\n{preview}{remainder}")

    groups: dict[str, list[str]] = defaultdict(list)
    for individual_id, row in individuals.items():
        treatment = (row.get("treatment") or "").strip()
        if not treatment:
            raise ValueError(f"Treatment is missing for individual {individual_id!r}.")
        groups[treatment].append(individual_id)
    return individuals, lifetimes, offspring_by_id, groups


def clusters_for_ids(
    ids: list[str],
    individuals: dict[str, dict[str, str]],
) -> dict[str, list[str]]:
    clusters: dict[str, list[str]] = defaultdict(list)
    for individual_id in ids:
        replicate = (individuals[individual_id].get("biological_replicate") or "").strip()
        if not replicate:
            raise ValueError(f"biological_replicate is missing for individual {individual_id!r}.")
        clusters[replicate].append(individual_id)
    return clusters


def bootstrap_ids(
    ids: list[str],
    individuals: dict[str, dict[str, str]],
    unit: str,
    rng: random.Random,
) -> list[str]:
    if unit == "individual":
        return [rng.choice(ids) for _ in ids]
    clusters = clusters_for_ids(ids, individuals)
    labels = sorted(clusters)
    if len(labels) < 3:
        raise ValueError("At least three biological replicates per treatment are required for replicate bootstrap.")
    sampled_labels = [rng.choice(labels) for _ in labels]
    return [individual_id for label in sampled_labels for individual_id in clusters[label]]


def paired_bootstrap_ids(
    groups: dict[str, list[str]],
    individuals: dict[str, dict[str, str]],
    rng: random.Random,
) -> dict[str, list[str]]:
    clusters = {treatment: clusters_for_ids(ids, individuals) for treatment, ids in groups.items()}
    label_sets = {treatment: set(by_label) for treatment, by_label in clusters.items()}
    first_treatment = sorted(groups)[0]
    expected = label_sets[first_treatment]
    mismatched = [treatment for treatment, labels in label_sets.items() if labels != expected]
    if mismatched:
        raise ValueError(
            "paired_by_replicate requires identical biological_replicate labels in every treatment; "
            f"mismatched treatments: {', '.join(sorted(mismatched))}"
        )
    labels = sorted(expected)
    if len(labels) < 3:
        raise ValueError("At least three matched biological replicates are required for paired contrasts.")
    sampled_labels = [rng.choice(labels) for _ in labels]
    return {
        treatment: [individual_id for label in sampled_labels for individual_id in clusters[treatment][label]]
        for treatment in groups
    }


def finite_difference(first: float | None, second: float | None) -> float | None:
    if first is None or second is None:
        return None
    difference = first - second
    return difference if math.isfinite(difference) else None


def interval_scope(calculable: int, requested: int) -> str:
    if requested == 0:
        return "not_requested"
    if calculable == requested:
        return "all_resamples"
    return "conditional_on_calculable_resamples"


def male_invariance_row(
    treatment: str,
    ids: list[str],
    individuals: dict[str, dict[str, str]],
    lifetimes: dict[str, int],
    offspring_by_id: dict[str, list[tuple[int, float]]],
    offspring_mode: str,
) -> dict[str, Any]:
    male_ids = [
        individual_id
        for individual_id in ids
        if (individuals[individual_id].get("sex") or "").strip().casefold() == "male"
    ]
    if offspring_mode == "female_line":
        return {
            "treatment": treatment,
            "male_n": len(male_ids),
            "short_male_lifetime": "",
            "long_male_lifetime": "",
            "r_short_male": "",
            "r_long_male": "",
            "r_difference": "",
            "R0_difference": "",
            "status": "not_applicable_female_line",
            "interpretation": "Male records are outside the confirmed female-only analysis cohort.",
        }
    if not male_ids:
        return {
            "treatment": treatment,
            "male_n": 0,
            "short_male_lifetime": "",
            "long_male_lifetime": "",
            "r_short_male": "",
            "r_long_male": "",
            "r_difference": "",
            "R0_difference": "",
            "status": "not_applicable_no_males",
            "interpretation": "No male records were available for this diagnostic.",
        }
    short_lifetimes = dict(lifetimes)
    long_lifetimes = dict(lifetimes)
    long_value = max(lifetimes[individual_id] for individual_id in ids)
    for individual_id in male_ids:
        short_lifetimes[individual_id] = 0
        long_lifetimes[individual_id] = long_value
    short_metrics, _ = calculate_sample(ids, short_lifetimes, offspring_by_id)
    long_metrics, _ = calculate_sample(ids, long_lifetimes, offspring_by_id)
    r_difference = finite_difference(long_metrics["r"], short_metrics["r"])
    r0_difference = finite_difference(long_metrics["R0"], short_metrics["R0"])
    calculable = r_difference is not None and r0_difference is not None
    invariant = calculable and abs(r_difference) <= 1e-12 and abs(r0_difference) <= 1e-12
    return {
        "treatment": treatment,
        "male_n": len(male_ids),
        "short_male_lifetime": 0,
        "long_male_lifetime": long_value,
        "r_short_male": short_metrics["r"],
        "r_long_male": long_metrics["r"],
        "r_difference": r_difference,
        "R0_difference": r0_difference,
        "status": "invariant" if invariant else "noncalculable" if not calculable else "changed",
        "interpretation": (
            "Male longevity does not enter this Euler-Lotka growth equation; do not interpret the metric as "
            "a mating-limited two-sex growth rate."
            if invariant
            else "Review the selected estimand and source records before interpreting male demographic effects."
        ),
    }


def run(args: argparse.Namespace) -> None:
    individual_path = Path(args.individuals).expanduser().resolve()
    observation_path = Path(args.observations).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    individuals, lifetimes, offspring_by_id, groups = prepare_data(
        individual_path, observation_path, args.time_origin_field, args.offspring_mode
    )
    analysis_groups = {
        treatment: analysis_ids_for_mode(ids, individuals, args.offspring_mode)
        for treatment, ids in groups.items()
    }
    if args.contrast_design != "none" and len(analysis_groups) < 2:
        raise ValueError("A treatment contrast requires at least two treatment groups.")
    if args.contrast_design != "none" and args.resamples == 0:
        raise ValueError("A treatment contrast requires --resamples greater than zero.")
    if args.contrast_design == "paired_by_replicate" and args.bootstrap_unit != "biological_replicate":
        raise ValueError("paired_by_replicate contrasts require --bootstrap-unit biological_replicate.")

    rng = random.Random(args.seed)
    metric_rows: list[dict[str, Any]] = []
    age_table_rows: list[dict[str, Any]] = []
    diagnostic_rows: list[dict[str, Any]] = []
    group_metadata: dict[str, Any] = {}
    estimates: dict[str, dict[str, float | None]] = {}
    bootstrap_metrics: dict[str, list[dict[str, float | None]]] = {}
    for treatment in sorted(analysis_groups):
        ids = analysis_groups[treatment]
        estimate, age_rows = calculate_sample(ids, lifetimes, offspring_by_id)
        estimates[treatment] = estimate
        for row in age_rows:
            row["offspring_total"] = row.pop("fecundity_total")
            age_table_rows.append(
                {
                    "treatment": treatment,
                    "offspring_mode": args.offspring_mode,
                    "cohort_n": len(ids),
                    **row,
                }
            )

        treatment_bootstraps: list[dict[str, float | None]] = []
        for _ in range(args.resamples):
            sampled_ids = bootstrap_ids(ids, individuals, args.bootstrap_unit, rng)
            metrics, _ = calculate_sample(sampled_ids, lifetimes, offspring_by_id)
            treatment_bootstraps.append(metrics)
        bootstrap_metrics[treatment] = treatment_bootstraps

        replicates = {
            (individuals[individual_id].get("biological_replicate") or "").strip()
            for individual_id in ids
        }
        group_metadata[treatment] = {
            "source_cohort_n": len(groups[treatment]),
            "analysis_cohort_n": len(ids),
            "biological_replicates": len(replicates - {""}),
            "reproductive_individuals": sum(
                1 for individual_id in ids if sum(value for _, value in offspring_by_id.get(individual_id, [])) > 0
            ),
        }
        diagnostic_rows.append(
            male_invariance_row(
                treatment,
                groups[treatment],
                individuals,
                lifetimes,
                offspring_by_id,
                args.offspring_mode,
            )
        )
        for metric in METRIC_ORDER:
            values = [
                value
                for sample in treatment_bootstraps
                for value in [sample.get(metric)]
                if value is not None and math.isfinite(value)
            ]
            metric_rows.append(
                {
                    "treatment": treatment,
                    "offspring_mode": args.offspring_mode,
                    "metric": metric,
                    "estimate": estimate.get(metric),
                    "ci_lower": quantile(values, 0.025),
                    "ci_upper": quantile(values, 0.975),
                    "requested_resamples": args.resamples,
                    "calculable_resamples": len(values),
                    "noncalculable_resamples": args.resamples - len(values),
                    "calculable_fraction": len(values) / args.resamples if args.resamples else "",
                    "ci_scope": interval_scope(len(values), args.resamples),
                    "time_unit": args.time_unit,
                    "fecundity_unit": args.fecundity_unit,
                }
            )

    contrast_bootstraps = bootstrap_metrics
    if args.contrast_design == "paired_by_replicate":
        contrast_bootstraps = {treatment: [] for treatment in analysis_groups}
        for _ in range(args.resamples):
            sampled_by_treatment = paired_bootstrap_ids(analysis_groups, individuals, rng)
            for treatment, sampled_ids in sampled_by_treatment.items():
                metrics, _ = calculate_sample(sampled_ids, lifetimes, offspring_by_id)
                contrast_bootstraps[treatment].append(metrics)

    contrast_rows: list[dict[str, Any]] = []
    if args.contrast_design != "none":
        for treatment_a, treatment_b in combinations(sorted(analysis_groups), 2):
            for metric in METRIC_ORDER:
                values = [
                    difference
                    for sample_a, sample_b in zip(
                        contrast_bootstraps[treatment_a], contrast_bootstraps[treatment_b]
                    )
                    for difference in [finite_difference(sample_a.get(metric), sample_b.get(metric))]
                    if difference is not None
                ]
                contrast_rows.append(
                    {
                        "treatment_a": treatment_a,
                        "treatment_b": treatment_b,
                        "direction": "treatment_a_minus_treatment_b",
                        "offspring_mode": args.offspring_mode,
                        "metric": metric,
                        "estimate_difference": finite_difference(
                            estimates[treatment_a].get(metric), estimates[treatment_b].get(metric)
                        ),
                        "ci_lower": quantile(values, 0.025),
                        "ci_upper": quantile(values, 0.975),
                        "requested_resamples": args.resamples,
                        "calculable_resamples": len(values),
                        "noncalculable_resamples": args.resamples - len(values),
                        "ci_scope": interval_scope(len(values), args.resamples),
                        "contrast_design": args.contrast_design,
                    }
                )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "metrics.csv",
        [
            "treatment",
            "offspring_mode",
            "metric",
            "estimate",
            "ci_lower",
            "ci_upper",
            "requested_resamples",
            "calculable_resamples",
            "noncalculable_resamples",
            "calculable_fraction",
            "ci_scope",
            "time_unit",
            "fecundity_unit",
        ],
        metric_rows,
    )
    write_csv(
        output_dir / "age_table.csv",
        [
            "treatment",
            "offspring_mode",
            "cohort_n",
            "age",
            "n_alive",
            "lx",
            "offspring_total",
            "mx",
            "lx_mx",
        ],
        age_table_rows,
    )
    write_csv(
        output_dir / "male_invariance_diagnostics.csv",
        [
            "treatment",
            "male_n",
            "short_male_lifetime",
            "long_male_lifetime",
            "r_short_male",
            "r_long_male",
            "r_difference",
            "R0_difference",
            "status",
            "interpretation",
        ],
        diagnostic_rows,
    )
    write_csv(
        output_dir / "treatment_contrasts.csv",
        [
            "treatment_a",
            "treatment_b",
            "direction",
            "offspring_mode",
            "metric",
            "estimate_difference",
            "ci_lower",
            "ci_upper",
            "requested_resamples",
            "calculable_resamples",
            "noncalculable_resamples",
            "ci_scope",
            "contrast_design",
        ],
        contrast_rows,
    )
    write_json(
        output_dir / "methods.json",
        {
            "analysis": "cohort_euler_lotka_core_metrics",
            "implementation_scope": (
                "Uses all initial-cohort individuals for cohort_total and sexed_total, or the confirmed female "
                "analysis cohort for female_line, to calculate lx, mx, lx*mx, R0, r, lambda, T, and doubling "
                "time. It does not calculate full age-stage outputs such as sxj, fxj, exj, or vxj."
            ),
            "chi_compatibility": (
                "cohort_total mode follows the published Chi lx-mx core equations and zero-based x+1 convention. "
                "It is not a certification of full numerical parity with TWOSEX-MSChart."
            ),
            "offspring_mode": args.offspring_mode,
            "offspring_mode_description": OFFSPRING_MODES[args.offspring_mode]["description"],
            "time_origin_field": args.time_origin_field,
            "time_unit": args.time_unit,
            "fecundity_unit": args.fecundity_unit,
            "unlisted_offspring_is_zero": args.confirm_unlisted_fecundity_zero,
            "bootstrap_unit": args.bootstrap_unit,
            "contrast_design": args.contrast_design,
            "contrast_interval": (
                "Pairwise percentile bootstrap interval for treatment_a minus treatment_b. No multiplicity "
                "adjustment or null-centered p-value is provided."
                if args.contrast_design != "none"
                else "not_requested"
            ),
            "male_invariance_diagnostic": (
                "Recomputes the core metrics after setting recorded male lifetimes to zero and to the group maximum. "
                "Invariance indicates that male longevity is not represented in the Euler-Lotka growth equation; "
                "the diagnostic is not applicable to female_line mode."
            ),
            "requested_resamples": args.resamples,
            "seed": args.seed,
            "groups": group_metadata,
            "formulas": {
                "lx": "number of selected analysis-cohort individuals alive at age x / analysis cohort size",
                "lx_mx": "confirmed offspring produced at age x / analysis cohort size",
                "mx": "lx_mx / lx when lx > 0",
                "R0": "sum(lx * mx)",
                "r": "root of sum(exp(-r * (x + 1)) * lx * mx) = 1",
                "lambda": "exp(r)",
                "T": "log(R0) / r when r is non-zero",
                "doubling_time": "log(2) / r when r > 0",
            },
            "age_index_convention": "x begins at 0; the discrete Euler-Lotka exponent uses x + 1",
            "bootstrap_interval": "2.5th and 97.5th percentiles of finite/calculable bootstrap estimates",
            "noncalculable_policy": (
                "Noncalculable results are counted against requested resamples and are not imputed. "
                "Intervals are conditional when ci_scope is conditional_on_calculable_resamples."
            ),
            "literature_basis": [
                "https://doi.org/10.1093/ee/17.1.26",
                "https://doi.org/10.1127/entomologia/2020/0936",
                "https://doi.org/10.1111/jen.12002",
                "https://doi.org/10.1127/entomologia/2022/1653",
                "https://doi.org/10.1093/aesa/saaf001",
                "https://doi.org/10.1111/afe.70035",
            ],
            "inputs": {
                "individuals": str(individual_path),
                "individuals_sha256": file_sha256(individual_path),
                "observations": str(observation_path),
                "observations_sha256": file_sha256(observation_path),
            },
            "script_sha256": file_sha256(Path(__file__)),
            "interpretation_boundary": (
                "This is a cohort Euler-Lotka core analysis, not a mating-function model or a full age-stage "
                "TWOSEX-MSChart analysis. Contrast intervals are exploratory unless the design, resampling unit, "
                "and multiplicity plan support the intended inference."
            ),
        },
    )
    print(f"Calculated life-table metrics for {len(groups)} treatment group(s): {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate cohort demographic fitness metrics.")
    parser.add_argument("--individuals", required=True)
    parser.add_argument("--observations", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bootstrap-unit", choices=["individual", "biological_replicate"], default="biological_replicate")
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260826)
    parser.add_argument("--time-origin-field", default="egg_date", choices=["egg_date", "larva_date", "pupa_date", "adult_emergence_date"])
    parser.add_argument("--time-unit", default="day")
    parser.add_argument("--fecundity-unit", default="confirmed_offspring_count")
    parser.add_argument("--offspring-mode", choices=sorted(OFFSPRING_MODES), default="cohort_total")
    parser.add_argument(
        "--contrast-design",
        choices=["none", "independent", "paired_by_replicate"],
        default="none",
        help="Optional pairwise bootstrap contrasts; choose only after confirming the experimental design.",
    )
    parser.add_argument(
        "--confirm-unlisted-fecundity-zero",
        action="store_true",
        required=True,
        help=(
            "Required acknowledgement that absent individual-age offspring records are confirmed observed "
            "or structural zeros rather than missed observations."
        ),
    )
    args = parser.parse_args()
    if args.resamples < 0:
        parser.error("--resamples must be non-negative")
    try:
        run(args)
    except (OSError, ValueError) as exc:
        print(f"Life-table calculation failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
