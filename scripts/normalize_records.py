#!/usr/bin/env python3
"""Normalize a confirmed insect-fitness mapping into canonical CSV files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from _shared import (
    clean_scalar,
    file_sha256,
    is_blank,
    load_tables,
    make_headers,
    normalize_token,
    parse_date_value,
    parse_number_value,
    row_is_repeated_header,
    select_sheet,
    write_csv,
    write_json,
)


INDIVIDUAL_FIELDS = [
    "individual_id",
    "treatment",
    "biological_replicate",
    "technical_replicate",
    "egg_date",
    "larva_date",
    "pupa_date",
    "adult_emergence_date",
    "sex",
    "death_stage",
    "death_date",
    "record_status",
    "source_sheet",
    "source_row",
]

OBSERVATION_FIELDS = [
    "individual_id",
    "treatment",
    "biological_replicate",
    "observation_date",
    "age",
    "age_origin",
    "stage",
    "sex",
    "alive",
    "fecundity",
    "hosts_offered",
    "parasitized",
    "host_killed",
    "female_offspring",
    "male_offspring",
    "record_status",
    "note",
    "source_sheet",
    "source_row",
    "source_column",
]

DATE_FIELDS = {
    "egg_date",
    "larva_date",
    "pupa_date",
    "adult_emergence_date",
    "observation_date",
    "death_date",
}
NUMERIC_FIELDS = {
    "adult_longevity",
    "age",
    "fecundity",
    "hosts_offered",
    "parasitized",
    "host_killed",
    "female_offspring",
    "male_offspring",
}
COUNT_FIELDS = {
    "fecundity",
    "hosts_offered",
    "parasitized",
    "host_killed",
    "female_offspring",
    "male_offspring",
}
OBSERVATION_DATA_FIELDS = {
    "observation_date",
    "age",
    "stage",
    "alive",
    "fecundity",
    "hosts_offered",
    "parasitized",
    "host_killed",
    "female_offspring",
    "male_offspring",
    "note",
}


def confirmation_placeholders(value: Any, path: str = "mapping") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(confirmation_placeholders(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(confirmation_placeholders(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        marker = value.strip().upper()
        if marker == "CONFIRM" or marker.startswith("CONFIRM_"):
            found.append(path)
    return found


def add_issue(
    issues: list[dict[str, Any]],
    severity: str,
    code: str,
    message: str,
    sheet: str,
    row: int | str = "",
    column: str = "",
    raw_value: Any = "",
    suggested_action: str = "Review the source and mapping contract.",
) -> None:
    issues.append(
        {
            "severity": severity,
            "source_sheet": sheet,
            "source_row": row,
            "source_column": column,
            "code": code,
            "raw_value": clean_scalar(raw_value),
            "message": message,
            "suggested_action": suggested_action,
        }
    )


def missing_matcher(tokens: list[Any]):
    accepted = {str(token).strip().casefold() for token in tokens}
    accepted.add("")

    def is_missing(value: Any) -> bool:
        return is_blank(value) or str(value).strip().casefold() in accepted

    return is_missing


def mapped_value(raw: Any, value_map: dict[str, Any]) -> Any:
    if not value_map:
        return raw
    text = str(raw).strip()
    if text in value_map:
        return value_map[text]
    normalized = normalize_token(text)
    for source, target in value_map.items():
        if normalize_token(source) == normalized:
            return target
    return raw


def convert_value(
    canonical: str,
    raw: Any,
    mapping: dict[str, Any],
    is_missing,
    issues: list[dict[str, Any]],
    sheet: str,
    row_number: int,
    source_column: str,
) -> Any:
    if is_missing(raw):
        return ""
    value_map = mapping.get("value_maps", {}).get(canonical, {})
    value = mapped_value(raw, value_map)

    date_fields = set(mapping.get("date_fields", [])) | DATE_FIELDS
    numeric_fields = set(mapping.get("numeric_fields", [])) | NUMERIC_FIELDS
    if canonical in date_fields:
        parsed, error = parse_date_value(value, mapping.get("default_year"))
        if error:
            add_issue(
                issues,
                "error",
                error,
                f"Could not parse {canonical} as a confirmed calendar date.",
                sheet,
                row_number,
                source_column,
                raw,
                "Correct the source value or add an explicit date rule to the mapping.",
            )
            return ""
        return parsed or ""
    if canonical in numeric_fields:
        parsed, error = parse_number_value(value)
        if error:
            add_issue(
                issues,
                "error",
                error,
                f"Could not parse {canonical} as numeric.",
                sheet,
                row_number,
                source_column,
                raw,
                "Correct the source value or confirm it as missing in the mapping.",
            )
            return ""
        if parsed is not None and canonical in COUNT_FIELDS and parsed < 0:
            add_issue(
                issues,
                "error",
                "negative_count",
                f"{canonical} cannot be negative.",
                sheet,
                row_number,
                source_column,
                raw,
                "Correct the count; do not reinterpret a negative value silently.",
            )
            return ""
        return "" if parsed is None else parsed
    return str(value).strip() if isinstance(value, str) else clean_scalar(value)


def normalize(input_file: Path, mapping_path: Path, output_dir: Path) -> int:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    if mapping.get("status") != "confirmed":
        raise ValueError("Mapping status must be 'confirmed' before normalization.")
    placeholders = confirmation_placeholders(mapping)
    if placeholders:
        raise ValueError(
            "Confirmed mapping still contains unresolved CONFIRM placeholder(s): " + ", ".join(placeholders)
        )

    tables, source_metadata = load_tables(input_file)
    sheet, rows = select_sheet(tables, mapping.get("sheet"))
    header_row = int(mapping.get("header_row", 1))
    if header_row < 1 or header_row > len(rows):
        raise ValueError(f"header_row {header_row} is outside worksheet {sheet!r}.")
    headers = make_headers(rows[header_row - 1])
    header_index = {header: index for index, header in enumerate(headers)}
    columns: dict[str, str] = mapping.get("columns", {})
    missing_sources = sorted({source for source in columns.values() if source not in header_index})
    if missing_sources:
        raise ValueError(f"Mapped source column(s) not found: {', '.join(missing_sources)}")

    is_missing = missing_matcher(mapping.get("missing_tokens", [""]))
    issues: list[dict[str, Any]] = []
    individuals: dict[str, dict[str, Any]] = {}
    observations: list[dict[str, Any]] = []
    layout = mapping.get("layout")
    if layout not in {"wide_cohort", "event_long"}:
        raise ValueError(f"Layout {layout!r} is not supported by the v1 normalizer.")
    try:
        age_offset = int(mapping.get("age_offset", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("age_offset must be an integer.") from exc
    wide_specs: list[tuple[dict[str, Any], re.Pattern[str], list[tuple[str, re.Match[str]]]]] = []
    for spec in mapping.get("wide_metrics", []):
        pattern = re.compile(spec["source_pattern"])
        matches = [(header, match) for header in headers if (match := pattern.fullmatch(header))]
        if not matches:
            add_issue(
                issues,
                "error",
                "wide_pattern_no_match",
                f"Wide metric pattern {spec['source_pattern']!r} matched no columns.",
                sheet,
                column=spec["source_pattern"],
            )
        wide_specs.append((spec, pattern, matches))

    excluded_repeated_headers = 0
    for offset, row in enumerate(rows[header_row:], start=header_row + 1):
        if not any(not is_blank(value) for value in row):
            continue
        if row_is_repeated_header(row, headers):
            if mapping.get("exclude_repeated_header", False):
                excluded_repeated_headers += 1
                continue
            add_issue(
                issues,
                "error",
                "repeated_header_row",
                "A repeated header occurs inside the data region.",
                sheet,
                offset,
            )
            continue

        raw_by_header = {
            header: row[index] if index < len(row) else None for header, index in header_index.items()
        }
        converted: dict[str, Any] = {}
        for canonical, source in columns.items():
            converted[canonical] = convert_value(
                canonical,
                raw_by_header.get(source),
                mapping,
                is_missing,
                issues,
                sheet,
                offset,
                source,
            )

        individual_id = str(converted.get("individual_id", "")).strip()
        if not individual_id:
            add_issue(
                issues,
                "error",
                "missing_individual_id",
                "The focal individual identifier is missing.",
                sheet,
                offset,
                columns.get("individual_id", ""),
            )
            continue

        individual_record = {field: converted.get(field, "") for field in INDIVIDUAL_FIELDS}
        individual_record.update({"individual_id": individual_id, "source_sheet": sheet, "source_row": offset})
        if individual_id not in individuals:
            individuals[individual_id] = individual_record
        elif layout == "wide_cohort":
            add_issue(
                issues,
                "error",
                "duplicate_individual_id",
                f"Individual {individual_id!r} occurs more than once in a wide cohort.",
                sheet,
                offset,
                columns.get("individual_id", ""),
                individual_id,
                "Resolve duplicate identity before calculation.",
            )
        else:
            existing = individuals[individual_id]
            for field in ["treatment", "biological_replicate", "technical_replicate", "sex"]:
                candidate = individual_record.get(field, "")
                if candidate not in ("", None) and existing.get(field, "") not in ("", None, candidate):
                    add_issue(
                        issues,
                        "error",
                        "inconsistent_individual_attribute",
                        f"{field} changes across rows for individual {individual_id!r}.",
                        sheet,
                        offset,
                        columns.get(field, ""),
                        candidate,
                    )
                elif existing.get(field, "") in ("", None) and candidate not in ("", None):
                    existing[field] = candidate

        base_observation = {
            field: converted.get(field, "") for field in OBSERVATION_FIELDS
        }
        base_observation.update(
            {
                "individual_id": individual_id,
                "treatment": converted.get("treatment", ""),
                "biological_replicate": converted.get("biological_replicate", ""),
                "sex": converted.get("sex", ""),
                "age_origin": converted.get("age_origin", mapping.get("age_origin", "")),
                "source_sheet": sheet,
                "source_row": offset,
                "source_column": "",
            }
        )
        if base_observation.get("age") not in ("", None):
            raw_age = base_observation["age"]
            if not isinstance(raw_age, (int, float)) or isinstance(raw_age, bool):
                add_issue(
                    issues,
                    "error",
                    "age_not_numeric",
                    "Canonical age must be numeric before applying age_offset.",
                    sheet,
                    offset,
                    columns.get("age", ""),
                    raw_age,
                    "Add age to numeric_fields and confirm age_offset.",
                )
                base_observation["age"] = ""
            else:
                adjusted_age = raw_age + age_offset
                if adjusted_age < 0:
                    add_issue(
                        issues,
                        "error",
                        "negative_normalized_age",
                        "Applying age_offset produced a negative canonical age.",
                        sheet,
                        offset,
                        columns.get("age", ""),
                        raw_age,
                        "Confirm the source day convention and age_offset.",
                    )
                    base_observation["age"] = ""
                else:
                    base_observation["age"] = adjusted_age

        if layout == "event_long":
            if any(base_observation.get(field) not in ("", None) for field in OBSERVATION_DATA_FIELDS):
                observations.append(base_observation)
        elif layout == "wide_cohort":
            for spec, _, matches in wide_specs:
                target = spec["target"]
                day_group = spec.get("day_group", "day")
                for source, match in matches:
                    raw_value = raw_by_header.get(source)
                    if is_missing(raw_value):
                        continue
                    value = convert_value(
                        target,
                        raw_value,
                        mapping,
                        is_missing,
                        issues,
                        sheet,
                        offset,
                        source,
                    )
                    if value == "":
                        continue
                    try:
                        spec_age_offset = int(spec.get("age_offset", age_offset))
                        age: Any = int(match.group(day_group)) + spec_age_offset
                    except (IndexError, TypeError, ValueError):
                        add_issue(
                            issues,
                            "error",
                            "invalid_wide_age",
                            f"Could not extract an integer age from {source!r}.",
                            sheet,
                            offset,
                            source,
                            match.groupdict(),
                        )
                        continue
                    if age < 0:
                        add_issue(
                            issues,
                            "error",
                            "negative_normalized_age",
                            "Applying age_offset produced a negative canonical age.",
                            sheet,
                            offset,
                            source,
                            match.group(day_group),
                            "Confirm the source day convention and age_offset.",
                        )
                        continue
                    observation = dict(base_observation)
                    observation.update(
                        {
                            "age": age,
                            "age_origin": spec.get("age_origin", mapping.get("age_origin", "")),
                            target: value,
                            "source_column": source,
                        }
                    )
                    observations.append(observation)

    if excluded_repeated_headers:
        add_issue(
            issues,
            "warning",
            "excluded_repeated_headers",
            f"Excluded {excluded_repeated_headers} confirmed repeated header row(s).",
            sheet,
            suggested_action="Retain this exclusion in the audit trail.",
        )

    id_counts = Counter(record["individual_id"] for record in individuals.values())
    if any(count > 1 for count in id_counts.values()):
        raise AssertionError("Internal normalization error: individual identifiers are not unique.")

    for observation in observations:
        sex = str(observation.get("sex") or "").casefold()
        if sex not in {"", "female", "male"}:
            add_issue(
                issues,
                "error",
                "unmapped_sex_code",
                "Sex must be mapped to female, male, or empty.",
                sheet,
                observation["source_row"],
                columns.get("sex", ""),
                observation.get("sex"),
                "Add the source code to value_maps.sex or leave confirmed unknown sex empty.",
            )
        alive = str(observation.get("alive") or "").casefold()
        if alive not in {"", "yes", "no"}:
            add_issue(
                issues,
                "error",
                "unmapped_alive_code",
                "Alive status must be mapped to yes, no, or empty.",
                sheet,
                observation["source_row"],
                columns.get("alive", ""),
                observation.get("alive"),
                "Add the source code to value_maps.alive.",
            )
        offered = observation.get("hosts_offered")
        parasitized = observation.get("parasitized")
        killed = observation.get("host_killed")
        if isinstance(offered, (int, float)):
            if isinstance(parasitized, (int, float)) and parasitized > offered:
                add_issue(
                    issues,
                    "error",
                    "parasitized_exceeds_offered",
                    "Parasitized hosts exceed hosts offered.",
                    sheet,
                    observation["source_row"],
                    columns.get("parasitized", ""),
                    parasitized,
                )
            if isinstance(killed, (int, float)) and killed > offered:
                add_issue(
                    issues,
                    "error",
                    "killed_exceeds_offered",
                    "Directly killed hosts exceed hosts offered.",
                    sheet,
                    observation["source_row"],
                    columns.get("host_killed", ""),
                    killed,
                )
            if isinstance(parasitized, (int, float)) and isinstance(killed, (int, float)) and parasitized + killed > offered:
                add_issue(
                    issues,
                    "warning",
                    "host_impact_exceeds_offered",
                    "Parasitized plus directly killed hosts exceed hosts offered; verify overlap semantics.",
                    sheet,
                    observation["source_row"],
                    raw_value=parasitized + killed,
                    suggested_action="Confirm whether host-killed counts exclude parasitized hosts.",
                )

    issue_fields = [
        "severity",
        "source_sheet",
        "source_row",
        "source_column",
        "code",
        "raw_value",
        "message",
        "suggested_action",
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "individuals.csv", INDIVIDUAL_FIELDS, individuals.values())
    write_csv(output_dir / "observations.csv", OBSERVATION_FIELDS, observations)
    write_csv(output_dir / "issues.csv", issue_fields, issues)
    severity_counts = Counter(issue["severity"] for issue in issues)
    provenance = {
        "source": source_metadata,
        "mapping_file": str(mapping_path.resolve()),
        "mapping_sha256": file_sha256(mapping_path),
        "script_sha256": file_sha256(Path(__file__)),
        "sheet": sheet,
        "layout": layout,
        "header_row": header_row,
        "individual_count": len(individuals),
        "observation_count": len(observations),
        "issue_counts": dict(severity_counts),
        "calculation_blocked": severity_counts.get("error", 0) > 0,
    }
    write_json(output_dir / "provenance.json", provenance)
    print(
        f"Normalized {len(individuals)} individual(s) and {len(observations)} observation(s); "
        f"errors={severity_counts.get('error', 0)}, warnings={severity_counts.get('warning', 0)}."
    )
    return 2 if severity_counts.get("error", 0) else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize insect-fitness records from a confirmed mapping contract.")
    parser.add_argument("input_file")
    parser.add_argument("--mapping", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        exit_code = normalize(
            Path(args.input_file).expanduser().resolve(),
            Path(args.mapping).expanduser().resolve(),
            Path(args.output_dir).expanduser().resolve(),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Normalization failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
