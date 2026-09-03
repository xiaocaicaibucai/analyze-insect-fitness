#!/usr/bin/env python3
"""Detect and audit prepared Chi/TWOSEX-style individual matrices."""

from __future__ import annotations

from collections import Counter
from typing import Any

from _shared import is_blank, normalize_token, parse_number_value


ID_HEADERS = {"number", "id", "individualid", "编号", "虫号", "蜂号"}
SEX_HEADERS = {"sex", "gender", "性别"}
ADULT_HEADERS = {"adult", "adultlongevity", "成虫", "成虫寿命", "寿命"}
FECUNDITY_HEADERS = {"egg", "eggs", "fecundity", "产卵", "产卵数"}
FEMALE_CODES = {"f", "female", "雌", "♀"}
MALE_CODES = {"m", "male", "雄", "♂"}
IMMATURE_CODES = {"n"}


def _find_header(row: list[Any], accepted: set[str]) -> int | None:
    for index, value in enumerate(row):
        if normalize_token(value) in accepted:
            return index
    return None


def _header_spec(row: list[Any]) -> dict[str, int] | None:
    id_index = _find_header(row, ID_HEADERS)
    sex_index = _find_header(row, SEX_HEADERS)
    adult_index = _find_header(row, ADULT_HEADERS)
    fecundity_index = _find_header(row, FECUNDITY_HEADERS)
    if None in {id_index, sex_index, adult_index, fecundity_index}:
        return None
    assert id_index is not None and sex_index is not None
    assert adult_index is not None and fecundity_index is not None
    if not (id_index < sex_index < adult_index < fecundity_index):
        return None
    return {
        "id_index": id_index,
        "sex_index": sex_index,
        "adult_index": adult_index,
        "fecundity_index": fecundity_index,
    }


def _group_label(rows: list[list[Any]], header_index: int, id_index: int) -> str:
    for row_index in range(header_index - 1, max(-1, header_index - 4), -1):
        candidates = []
        for value in rows[row_index][: id_index + 1]:
            if is_blank(value):
                continue
            token = normalize_token(value)
            if token not in ID_HEADERS | SEX_HEADERS | ADULT_HEADERS | FECUNDITY_HEADERS:
                candidates.append(str(value).strip())
        if candidates:
            return candidates[0]
    return f"section_{header_index + 1}"


def detect_chi_sections(rows: list[list[Any]]) -> list[dict[str, Any]]:
    """Return conservative section metadata without assigning biological semantics."""
    header_rows = [(index, spec) for index, row in enumerate(rows) if (spec := _header_spec(row))]
    sections: list[dict[str, Any]] = []
    for position, (header_index, spec) in enumerate(header_rows):
        next_header = header_rows[position + 1][0] if position + 1 < len(header_rows) else len(rows)
        records = []
        for row_index in range(header_index + 1, next_header):
            row = rows[row_index]
            if spec["id_index"] >= len(row) or spec["sex_index"] >= len(row):
                continue
            if is_blank(row[spec["id_index"]]) or is_blank(row[spec["sex_index"]]):
                continue
            sex_token = normalize_token(row[spec["sex_index"]])
            if sex_token not in FEMALE_CODES | MALE_CODES | IMMATURE_CODES:
                continue
            records.append(row_index)
        if not records:
            continue
        header = rows[header_index]
        stage_columns = []
        for index in range(spec["sex_index"] + 1, spec["adult_index"]):
            value = header[index] if index < len(header) else None
            stage_columns.append(
                {
                    "column_index": index + 1,
                    "source_header": str(value).strip() if not is_blank(value) else f"unnamed_{index + 1}",
                    "header_missing": is_blank(value),
                }
            )
        sections.append(
            {
                "group": _group_label(rows, header_index, spec["id_index"]),
                "header_row": header_index + 1,
                "first_data_row": records[0] + 1,
                "last_data_row": records[-1] + 1,
                "record_rows": [index + 1 for index in records],
                "record_count": len(records),
                "id_column": spec["id_index"] + 1,
                "sex_column": spec["sex_index"] + 1,
                "stage_columns": stage_columns,
                "adult_column": spec["adult_index"] + 1,
                "fecundity_start_column": spec["fecundity_index"] + 1,
                "fecundity_header": str(header[spec["fecundity_index"]]).strip(),
            }
        )
    return sections


def _number(value: Any) -> float | None:
    number, error = parse_number_value(value)
    return float(number) if error is None and number is not None else None


def _issue(
    severity: str,
    row: int | str,
    column: int | str,
    code: str,
    raw_value: Any,
    message: str,
    action: str,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "source_sheet": "",
        "source_row": row,
        "source_column": column,
        "code": code,
        "raw_value": raw_value,
        "message": message,
        "suggested_action": action,
    }


def audit_chi_sections(
    rows: list[list[Any]], sections: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Audit matrix mechanics; negative duration and N-code semantics remain unconfirmed."""
    summaries: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    width = max((len(row) for row in rows), default=0)
    for section in sections:
        group = section["group"]
        sex_counts: Counter[str] = Counter()
        seen_ids: set[str] = set()
        reproductive_rows = 0
        for source_row in section["record_rows"]:
            row = rows[source_row - 1]

            def get(column: int) -> Any:
                return row[column - 1] if column - 1 < len(row) else None

            individual_id = str(get(section["id_column"])).strip()
            sex_raw = str(get(section["sex_column"])).strip()
            sex = normalize_token(sex_raw)
            sex_counts[sex_raw] += 1
            if individual_id in seen_ids:
                issues.append(
                    _issue(
                        "error",
                        source_row,
                        section["id_column"],
                        "duplicate_chi_individual_id",
                        individual_id,
                        f"Duplicate individual identifier within Chi matrix group {group!r}.",
                        "Resolve or explicitly namespace duplicate individual identifiers.",
                    )
                )
            seen_ids.add(individual_id)

            stage_values = [(item, _number(get(item["column_index"]))) for item in section["stage_columns"]]
            negatives = [(item, value) for item, value in stage_values if value is not None and value < 0]
            adult = _number(get(section["adult_column"]))
            if sex in IMMATURE_CODES:
                if len(negatives) != 1 or adult is not None:
                    issues.append(
                        _issue(
                            "error",
                            source_row,
                            section["sex_column"],
                            "invalid_immature_death_encoding",
                            sex_raw,
                            "An N-coded row must have exactly one negative stage duration and no adult duration under the detected convention.",
                            "Confirm the N/negative-marker convention, then repair the row or use an explicit status field.",
                        )
                    )
            elif sex in FEMALE_CODES | MALE_CODES:
                if negatives or adult is None or adult <= 0:
                    issues.append(
                        _issue(
                            "error",
                            source_row,
                            section["adult_column"],
                            "invalid_adult_duration",
                            get(section["adult_column"]),
                            "An adult F/M row must have positive stage durations and a positive adult duration.",
                            "Repair the duration fields or mark the record as unresolved.",
                        )
                    )

            fecundity = [get(column) for column in range(section["fecundity_start_column"], width + 1)]
            numeric_fecundity: list[float | None] = []
            for offset, value in enumerate(fecundity):
                if is_blank(value):
                    numeric_fecundity.append(None)
                    continue
                number = _number(value)
                if number is None or number < 0:
                    issues.append(
                        _issue(
                            "error",
                            source_row,
                            section["fecundity_start_column"] + offset,
                            "invalid_daily_fecundity",
                            value,
                            "Daily fecundity must be a non-negative numeric value when present.",
                            "Repair the value or preserve it as unresolved missing data.",
                        )
                    )
                numeric_fecundity.append(number)
            positive = [value for value in numeric_fecundity if value is not None and value > 0]
            if positive:
                reproductive_rows += 1
            if sex not in FEMALE_CODES and positive:
                issues.append(
                    _issue(
                        "error",
                        source_row,
                        section["fecundity_start_column"],
                        "fecundity_on_nonfemale_row",
                        sum(positive),
                        "Positive daily fecundity occurs on a row not coded as female.",
                        "Confirm row alignment and the biological parent represented by the record.",
                    )
                )
            if sex in FEMALE_CODES and adult is not None and adult > 0:
                nonblank_positions = [index + 1 for index, value in enumerate(numeric_fecundity) if value is not None]
                last_recorded = max(nonblank_positions, default=0)
                if last_recorded == 0:
                    issues.append(
                        _issue(
                            "error",
                            source_row,
                            section["fecundity_start_column"],
                            "female_fecundity_unrecorded",
                            "",
                            "Female adult row has no explicit daily fecundity observations.",
                            "Distinguish a confirmed nonreproductive female from missing observation history.",
                        )
                    )
                else:
                    internal_blanks = [
                        index + 1 for index, value in enumerate(numeric_fecundity[:last_recorded]) if value is None
                    ]
                    if internal_blanks:
                        issues.append(
                            _issue(
                                "error",
                                source_row,
                                section["fecundity_start_column"] + internal_blanks[0] - 1,
                                "fecundity_internal_gap",
                                "",
                                f"Daily fecundity has {len(internal_blanks)} blank interval(s) before a later recorded value.",
                                "Recover the observations or explicitly confirm whether each gap is zero or missing.",
                            )
                        )
                    if last_recorded > adult:
                        issues.append(
                            _issue(
                                "error",
                                source_row,
                                section["fecundity_start_column"] + int(adult),
                                "fecundity_after_adult_lifetime",
                                last_recorded,
                                f"Daily fecundity extends to interval {last_recorded}, beyond adult duration {int(adult)}.",
                                "Check whether longevity and fecundity rows were aligned to the same individual.",
                            )
                        )
                    elif adult - last_recorded > 1:
                        issues.append(
                            _issue(
                                "error",
                                source_row,
                                section["fecundity_start_column"] + last_recorded,
                                "fecundity_horizon_shorter_than_adult_life",
                                int(adult - last_recorded),
                                f"Daily fecundity stops {int(adult - last_recorded)} interval(s) before the recorded adult duration ends.",
                                "Confirm whether trailing intervals are observed zeros, missing observations, or a row-alignment error.",
                            )
                        )

        for item in section["stage_columns"]:
            if item["header_missing"]:
                issues.append(
                    _issue(
                        "error",
                        section["header_row"],
                        item["column_index"],
                        "missing_stage_duration_header",
                        "",
                        "A duration column between sex and adult has no stage header.",
                        "Name the biological stage explicitly (for example egg) before normalization.",
                    )
                )
        summaries.append(
            {
                **{key: value for key, value in section.items() if key != "record_rows"},
                "sex_counts": dict(sex_counts),
                "reproductive_rows": reproductive_rows,
                "negative_duration_semantics": "CONFIRM_death_marker_and_absolute_duration",
                "immature_code_semantics": "CONFIRM_N_means_preadult_death_not_unknown_sex",
                "daily_fecundity_age_origin": "CONFIRM_first_adult_interval_and_offset",
            }
        )

    if sections:
        issues.append(
            _issue(
                "warning",
                "",
                "",
                "chi_semantics_require_confirmation",
                "",
                "Detected Chi-style encodings are mechanical patterns, not confirmed biological meanings.",
                "Confirm stage labels, N and negative-duration semantics, time origin, offspring unit, and inclusion rules before normalization.",
            )
        )
    return summaries, issues
