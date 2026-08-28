#!/usr/bin/env python3
"""Summarize parasitoid performance without converting missing counts to zero."""

from __future__ import annotations

import argparse
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from _shared import file_sha256, quantile, read_csv_records, write_csv, write_json


COUNT_FIELDS = ["hosts_offered", "parasitized", "host_killed", "female_offspring", "male_offspring"]
RATE_METRICS = ["parasitism_rate", "direct_host_kill_rate", "total_host_impact_rate", "emergence_rate", "female_fraction"]
MEAN_METRICS = [f"{field}_per_individual" for field in COUNT_FIELDS]


def optional_number(value: Any, row_number: int, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"observations.csv row {row_number}: {field} is not numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"observations.csv row {row_number}: {field} must be finite and non-negative")
    return number


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator > 0 else None


def rate_from_complete_rows(
    records: list[dict[str, float | None]],
    numerator_fields: list[str],
    denominator_field: str,
) -> tuple[float | None, int]:
    required = numerator_fields + [denominator_field]
    complete = [record for record in records if all(record[field] is not None for field in required)]
    numerator = sum(sum(float(record[field]) for field in numerator_fields) for record in complete)
    denominator = sum(float(record[denominator_field]) for record in complete)
    return safe_ratio(numerator, denominator), len(complete)


def metrics_for_ids(
    sampled_ids: list[str],
    records_by_id: dict[str, list[dict[str, float | None]]],
) -> tuple[dict[str, float | None], dict[str, int]]:
    records = [record for individual_id in sampled_ids for record in records_by_id[individual_id]]
    metrics: dict[str, float | None] = {}
    valid_n: dict[str, int] = {}
    metrics["parasitism_rate"], valid_n["parasitism_rate"] = rate_from_complete_rows(
        records, ["parasitized"], "hosts_offered"
    )
    metrics["direct_host_kill_rate"], valid_n["direct_host_kill_rate"] = rate_from_complete_rows(
        records, ["host_killed"], "hosts_offered"
    )
    metrics["total_host_impact_rate"], valid_n["total_host_impact_rate"] = rate_from_complete_rows(
        records, ["parasitized", "host_killed"], "hosts_offered"
    )
    metrics["emergence_rate"], valid_n["emergence_rate"] = rate_from_complete_rows(
        records, ["female_offspring", "male_offspring"], "parasitized"
    )
    metrics["female_fraction"], valid_n["female_fraction"] = rate_from_complete_rows(
        records, ["female_offspring"], "all_offspring"
    )

    for field in COUNT_FIELDS:
        totals = []
        for individual_id in sampled_ids:
            measurements = [record[field] for record in records_by_id[individual_id] if record[field] is not None]
            if measurements:
                totals.append(sum(float(value) for value in measurements))
        metric = f"{field}_per_individual"
        metrics[metric] = sum(totals) / len(totals) if totals else None
        valid_n[metric] = len(totals)
    return metrics, valid_n


def bootstrap_ids(
    ids: list[str],
    replicate_by_id: dict[str, str],
    unit: str,
    rng: random.Random,
) -> list[str]:
    if unit == "individual":
        return [rng.choice(ids) for _ in ids]
    clusters: dict[str, list[str]] = defaultdict(list)
    for individual_id in ids:
        replicate = replicate_by_id.get(individual_id, "")
        if not replicate:
            raise ValueError(f"biological_replicate is missing for individual {individual_id!r}")
        clusters[replicate].append(individual_id)
    labels = sorted(clusters)
    if len(labels) < 3:
        raise ValueError("At least three biological replicates per treatment are required for replicate bootstrap.")
    return [individual_id for label in (rng.choice(labels) for _ in labels) for individual_id in clusters[label]]


def run(args: argparse.Namespace) -> None:
    observation_path = Path(args.observations).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    rows = read_csv_records(observation_path)
    if not rows:
        raise ValueError("observations.csv contains no records.")

    records_by_id: dict[str, list[dict[str, float | None]]] = defaultdict(list)
    treatment_by_id: dict[str, str] = {}
    replicate_by_id: dict[str, str] = {}
    interval_markers: dict[str, set[str]] = defaultdict(set)
    for row_number, row in enumerate(rows, start=2):
        individual_id = (row.get("individual_id") or "").strip()
        treatment = (row.get("treatment") or "").strip()
        replicate = (row.get("biological_replicate") or "").strip()
        if not individual_id or not treatment:
            raise ValueError(f"observations.csv row {row_number}: individual_id and treatment are required")
        if individual_id in treatment_by_id and treatment_by_id[individual_id] != treatment:
            raise ValueError(f"observations.csv row {row_number}: treatment changes for {individual_id!r}")
        if individual_id in replicate_by_id and replicate_by_id[individual_id] not in {"", replicate} and replicate:
            raise ValueError(f"observations.csv row {row_number}: biological replicate changes for {individual_id!r}")
        treatment_by_id[individual_id] = treatment
        if replicate:
            replicate_by_id[individual_id] = replicate

        record = {field: optional_number(row.get(field), row_number, field) for field in COUNT_FIELDS}
        offered, parasitized, killed = record["hosts_offered"], record["parasitized"], record["host_killed"]
        if offered is not None and parasitized is not None and parasitized > offered:
            raise ValueError(f"observations.csv row {row_number}: parasitized exceeds hosts_offered")
        if offered is not None and killed is not None and killed > offered:
            raise ValueError(f"observations.csv row {row_number}: host_killed exceeds hosts_offered")
        if offered is not None and parasitized is not None and killed is not None and parasitized + killed > offered:
            raise ValueError(
                f"observations.csv row {row_number}: parasitized + host_killed exceeds hosts_offered; overlap semantics are unresolved"
            )
        if record["female_offspring"] is not None and record["male_offspring"] is not None:
            record["all_offspring"] = float(record["female_offspring"]) + float(record["male_offspring"])
        else:
            record["all_offspring"] = None
        records_by_id[individual_id].append(record)
        marker = (row.get("observation_date") or row.get("age") or f"source_row:{row_number}").strip()
        interval_markers[individual_id].add(marker)

    individual_rows: list[dict[str, Any]] = []
    for individual_id in sorted(records_by_id):
        records = records_by_id[individual_id]
        totals: dict[str, float | None] = {}
        observed: dict[str, int] = {}
        for field in COUNT_FIELDS:
            values = [record[field] for record in records if record[field] is not None]
            totals[field] = sum(float(value) for value in values) if values else None
            observed[f"{field}_observed_intervals"] = len(values)
        offered = totals["hosts_offered"]
        parasitized = totals["parasitized"]
        killed = totals["host_killed"]
        female = totals["female_offspring"]
        male = totals["male_offspring"]
        offspring = female + male if female is not None and male is not None else None
        days = len(interval_markers[individual_id])
        individual_rows.append(
            {
                "individual_id": individual_id,
                "treatment": treatment_by_id[individual_id],
                "biological_replicate": replicate_by_id.get(individual_id, ""),
                **totals,
                **observed,
                "parasitism_rate": safe_ratio(parasitized, offered) if parasitized is not None and offered is not None else None,
                "direct_host_kill_rate": safe_ratio(killed, offered) if killed is not None and offered is not None else None,
                "total_host_impact_rate": safe_ratio(parasitized + killed, offered)
                if parasitized is not None and killed is not None and offered is not None
                else None,
                "emergence_rate": safe_ratio(offspring, parasitized)
                if offspring is not None and parasitized is not None
                else None,
                "female_fraction": safe_ratio(female, offspring)
                if female is not None and offspring is not None
                else None,
                "observed_intervals": days,
            }
        )

    groups: dict[str, list[str]] = defaultdict(list)
    for individual_id, treatment in treatment_by_id.items():
        groups[treatment].append(individual_id)
    rng = random.Random(args.seed)
    metric_rows: list[dict[str, Any]] = []
    group_metadata: dict[str, Any] = {}
    for treatment in sorted(groups):
        ids = sorted(groups[treatment])
        estimate, valid_n = metrics_for_ids(ids, records_by_id)
        bootstrap_values: dict[str, list[float]] = defaultdict(list)
        for _ in range(args.resamples):
            sampled_ids = bootstrap_ids(ids, replicate_by_id, args.bootstrap_unit, rng)
            result, _ = metrics_for_ids(sampled_ids, records_by_id)
            for metric, value in result.items():
                if value is not None and math.isfinite(value):
                    bootstrap_values[metric].append(value)
        group_metadata[treatment] = {
            "individuals": len(ids),
            "biological_replicates": len({replicate_by_id.get(individual_id, "") for individual_id in ids} - {""}),
            "observation_intervals": sum(len(records_by_id[individual_id]) for individual_id in ids),
        }
        for metric in RATE_METRICS + MEAN_METRICS:
            values = bootstrap_values.get(metric, [])
            metric_rows.append(
                {
                    "treatment": treatment,
                    "metric": metric,
                    "estimate": estimate.get(metric),
                    "ci_lower": quantile(values, 0.025),
                    "ci_upper": quantile(values, 0.975),
                    "valid_n": valid_n.get(metric, 0),
                    "valid_unit": "observation_interval" if metric in RATE_METRICS else "individual",
                    "requested_resamples": args.resamples,
                    "calculable_resamples": len(values),
                    "calculable_fraction": len(values) / args.resamples if args.resamples else "",
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(
        output_dir / "individual_metrics.csv",
        [
            "individual_id",
            "treatment",
            "biological_replicate",
            *COUNT_FIELDS,
            *(f"{field}_observed_intervals" for field in COUNT_FIELDS),
            *RATE_METRICS,
            "observed_intervals",
        ],
        individual_rows,
    )
    write_csv(
        output_dir / "metrics.csv",
        [
            "treatment",
            "metric",
            "estimate",
            "ci_lower",
            "ci_upper",
            "valid_n",
            "valid_unit",
            "requested_resamples",
            "calculable_resamples",
            "calculable_fraction",
        ],
        metric_rows,
    )
    write_json(
        output_dir / "methods.json",
        {
            "analysis": "parasitoid_event_performance_summary",
            "missing_value_rule": "Missing counts remain missing; rates use only rows with every required numerator and denominator.",
            "bootstrap_unit": args.bootstrap_unit,
            "requested_resamples": args.resamples,
            "seed": args.seed,
            "groups": group_metadata,
            "definitions": {
                "parasitism_rate": "sum(parasitized) / sum(hosts_offered) over complete pairs",
                "direct_host_kill_rate": "sum(host_killed) / sum(hosts_offered) over complete pairs",
                "total_host_impact_rate": "sum(parasitized + host_killed) / sum(hosts_offered) over complete triples; assumes disjoint outcomes",
                "emergence_rate": "sum(female_offspring + male_offspring) / sum(parasitized) over complete records",
                "female_fraction": "sum(female_offspring) / sum(all sexed offspring) over complete records",
            },
            "input": str(observation_path),
            "input_sha256": file_sha256(observation_path),
            "script_sha256": file_sha256(Path(__file__)),
            "interpretation_boundary": "Intervals are descriptive within treatment and are not treatment-difference tests.",
        },
    )
    print(f"Calculated parasitoid metrics for {len(groups)} treatment group(s): {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize parasitoid event performance.")
    parser.add_argument("--observations", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--bootstrap-unit", choices=["individual", "biological_replicate"], default="biological_replicate")
    parser.add_argument("--resamples", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()
    if args.resamples < 0:
        parser.error("--resamples must be non-negative")
    try:
        run(args)
    except (OSError, ValueError) as exc:
        print(f"Parasitoid calculation failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
