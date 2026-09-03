#!/usr/bin/env python3
"""Calculate auditable cohort demographic metrics from canonical records."""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

from _shared import file_sha256, quantile, read_csv_records, write_csv, write_json


METRIC_ORDER = ["r", "lambda", "R0", "T", "doubling_time"]
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
    fecundity_by_id: dict[str, list[tuple[int, float]]],
) -> tuple[dict[str, float | None], list[dict[str, Any]]]:
    cohort_size = len(sampled_ids)
    if cohort_size == 0:
        return {metric: None for metric in METRIC_ORDER}, []
    maximum_age = max(
        [lifetimes[individual_id] for individual_id in sampled_ids]
        + [age for individual_id in sampled_ids for age, _ in fecundity_by_id.get(individual_id, [])],
        default=0,
    )
    age_rows: list[dict[str, Any]] = []
    contributions: dict[int, float] = {}
    for age in range(maximum_age + 1):
        alive_count = sum(lifetimes[individual_id] >= age for individual_id in sampled_ids)
        fecundity_total = sum(
            value
            for individual_id in sampled_ids
            for event_age, value in fecundity_by_id.get(individual_id, [])
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

    fecundity_by_id: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row_number, observation in enumerate(observation_rows, start=2):
        individual_id = (observation.get("individual_id") or "").strip()
        fecundity = as_float(observation.get("fecundity"))
        if fecundity is None:
            continue
        if fecundity < 0:
            errors.append(f"observations.csv row {row_number}: negative fecundity")
            continue
        individual = individuals.get(individual_id)
        if individual is None:
            errors.append(f"observations.csv row {row_number}: unknown individual_id {individual_id!r}")
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
        fecundity_by_id[individual_id].append((age, fecundity))

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
    return individuals, lifetimes, fecundity_by_id, groups


def bootstrap_ids(
    ids: list[str],
    individuals: dict[str, dict[str, str]],
    unit: str,
    rng: random.Random,
) -> list[str]:
    if unit == "individual":
        return [rng.choice(ids) for _ in ids]
    clusters: dict[str, list[str]] = defaultdict(list)
    for individual_id in ids:
        replicate = (individuals[individual_id].get("biological_replicate") or "").strip()
        if not replicate:
            raise ValueError(f"biological_replicate is missing for individual {individual_id!r}.")
        clusters[replicate].append(individual_id)
    labels = sorted(clusters)
    if len(labels) < 3:
        raise ValueError("At least three biological replicates per treatment are required for replicate bootstrap.")
    sampled_labels = [rng.choice(labels) for _ in labels]
    return [individual_id for label in sampled_labels for individual_id in clusters[label]]


def run(args: argparse.Namespace) -> None:
    individual_path = Path(args.individuals).expanduser().resolve()
    observation_path = Path(args.observations).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    individuals, lifetimes, fecundity_by_id, groups = prepare_data(
        individual_path, observation_path, args.time_origin_field
    )

    rng = random.Random(args.seed)
    metric_rows: list[dict[str, Any]] = []
    age_table_rows: list[dict[str, Any]] = []
    group_metadata: dict[str, Any] = {}
    for treatment in sorted(groups):
        ids = groups[treatment]
        estimate, age_rows = calculate_sample(ids, lifetimes, fecundity_by_id)
        for row in age_rows:
            age_table_rows.append({"treatment": treatment, "cohort_n": len(ids), **row})

        bootstrap_values: dict[str, list[float]] = defaultdict(list)
        for _ in range(args.resamples):
            sampled_ids = bootstrap_ids(ids, individuals, args.bootstrap_unit, rng)
            metrics, _ = calculate_sample(sampled_ids, lifetimes, fecundity_by_id)
            for metric, value in metrics.items():
                if value is not None and math.isfinite(value):
                    bootstrap_values[metric].append(value)

        replicates = {
            (individuals[individual_id].get("biological_replicate") or "").strip()
            for individual_id in ids
        }
        group_metadata[treatment] = {
            "cohort_n": len(ids),
            "biological_replicates": len(replicates - {""}),
            "reproductive_individuals": sum(
                1 for individual_id in ids if sum(value for _, value in fecundity_by_id.get(individual_id, [])) > 0
            ),
        }
        for metric in METRIC_ORDER:
            values = bootstrap_values.get(metric, [])
            if args.resamples == 0:
                ci_scope = "not_requested"
            elif len(values) == args.resamples:
                ci_scope = "all_resamples"
            else:
                ci_scope = "conditional_on_calculable_resamples"
            metric_rows.append(
                {
                    "treatment": treatment,
                    "metric": metric,
                    "estimate": estimate.get(metric),
                    "ci_lower": quantile(values, 0.025),
                    "ci_upper": quantile(values, 0.975),
                    "requested_resamples": args.resamples,
                    "calculable_resamples": len(values),
                    "noncalculable_resamples": args.resamples - len(values),
                    "calculable_fraction": len(values) / args.resamples if args.resamples else "",
                    "ci_scope": ci_scope,
                    "time_unit": args.time_unit,
                    "fecundity_unit": args.fecundity_unit,
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "metrics.csv",
        [
            "treatment",
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
        ["treatment", "cohort_n", "age", "n_alive", "lx", "fecundity_total", "mx", "lx_mx"],
        age_table_rows,
    )
    write_json(
        output_dir / "methods.json",
        {
            "analysis": "two_sex_cohort_lx_mx_core_metrics",
            "implementation_scope": (
                "Uses all initial-cohort individuals to calculate lx, mx, lx*mx, R0, r, lambda, T, and "
                "doubling time. It does not calculate full age-stage outputs such as sxj, fxj, exj, or vxj."
            ),
            "time_origin_field": args.time_origin_field,
            "time_unit": args.time_unit,
            "fecundity_unit": args.fecundity_unit,
            "unlisted_fecundity_is_zero": args.confirm_unlisted_fecundity_zero,
            "bootstrap_unit": args.bootstrap_unit,
            "requested_resamples": args.resamples,
            "seed": args.seed,
            "groups": group_metadata,
            "formulas": {
                "lx": "number of initial-cohort individuals alive at age x / initial cohort size",
                "lx_mx": "confirmed offspring produced at age x / initial cohort size",
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
            ],
            "inputs": {
                "individuals": str(individual_path),
                "individuals_sha256": file_sha256(individual_path),
                "observations": str(observation_path),
                "observations_sha256": file_sha256(observation_path),
            },
            "script_sha256": file_sha256(Path(__file__)),
            "interpretation_boundary": (
                "Intervals are descriptive within treatment and are not treatment-difference tests. "
                "This is a two-sex cohort lx-mx core analysis, not a full age-stage TWOSEX-MSChart analysis."
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
    parser.add_argument(
        "--confirm-unlisted-fecundity-zero",
        action="store_true",
        required=True,
        help=(
            "Required acknowledgement that absent individual-age fecundity records are confirmed observed "
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
