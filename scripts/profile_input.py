#!/usr/bin/env python3
"""Profile insect-fitness spreadsheets and emit draft mapping contracts."""

from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from _shared import (
    clean_scalar,
    is_blank,
    load_tables,
    make_headers,
    normalize_token,
    parse_date_value,
    parse_number_value,
    row_is_repeated_header,
    write_json,
)


ALIASES = {
    "individual_id": ["individualid", "insectid", "waspid", "sampleid", "id", "虫号", "蜂号", "编号id", "编号", "样本id"],
    "treatment": ["treatment", "trt", "group", "grp", "处理grp", "处理", "组别", "实验组"],
    "biological_replicate": ["biologicalreplicate", "replicate", "rep", "block", "cage", "重复", "批次", "区组", "笼"],
    "technical_replicate": ["technicalreplicate", "techrep", "技术重复"],
    "egg_date": ["eggdate", "ovipositiondate", "产卵日", "卵期开始", "卵日"],
    "larva_date": ["larvadate", "hatchdate", "幼虫日", "孵化日"],
    "pupa_date": ["pupadate", "pupationdate", "化蛹日", "蛹日"],
    "adult_emergence_date": ["adultemergencedate", "emergencedate", "eclosiondate", "羽化日", "羽化日期"],
    "observation_date": ["observationdate", "obsdate", "recorddate", "记录日期", "观察日期"],
    "death_date": ["deathdate", "死亡日", "死亡日期", "结束日期"],
    "death_stage": ["deathstage", "死亡龄期", "死亡阶段"],
    "adult_longevity": ["adultlongevity", "longevity", "lifespan", "成虫寿命", "寿命"],
    "age": ["aged", "age", "day", "days", "日龄", "天数", "观察日"],
    "age_origin": ["ageorigin", "timeorigin", "时间起点"],
    "stage": ["stage", "lifestage", "阶段", "龄期"],
    "sex": ["sex", "gender", "性别"],
    "alive": ["alive", "survival", "存活", "存活状态", "死活"],
    "fecundity": ["fecundity", "eggcount", "eggs", "offspring", "totaloffspring", "产卵", "产卵数", "总子代", "子代数"],
    "hosts_offered": ["hostsoffered", "hostoffered", "providedhosts", "供试寄主", "提供寄主"],
    "parasitized": ["parasitized", "parasitised", "parasitism", "寄生数", "被寄生"],
    "host_killed": ["hostkilled", "hostdead", "killedhosts", "寄主致死", "杀死寄主"],
    "female_offspring": ["femaleoffspring", "foffspring", "daughters", "雌性后代", "雌后代"],
    "male_offspring": ["maleoffspring", "moffspring", "sons", "雄性后代", "雄后代"],
    "offspring_sex_counts": ["fm", "offspringsex", "子代性比", "雌雄后代"],
    "record_status": ["recordstatus", "status", "状态", "记录状态"],
    "note": ["note", "notes", "remark", "remarks", "备注", "说明"],
}

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
COUNT_FIELDS = NUMERIC_FIELDS - {"adult_longevity", "age"}
MISSING_MARKERS = {"na", "n/a", "null", "none", "-", "--", "未记", "未统计", "缺失", "无记录"}


def candidate_scores(header: str) -> list[tuple[str, float]]:
    token = normalize_token(header)
    scores: list[tuple[str, float]] = []
    for canonical, aliases in ALIASES.items():
        normalized_aliases = {normalize_token(alias) for alias in aliases}
        canonical_token = normalize_token(canonical)
        if token == canonical_token or token in normalized_aliases:
            score = 1.0
        else:
            matches = [alias for alias in normalized_aliases | {canonical_token} if len(alias) >= 3 and (alias in token or token in alias)]
            score = 0.82 if matches else 0.0
        if score:
            scores.append((canonical, score))
    scores.sort(key=lambda item: (-item[1], item[0]))
    return scores


def header_score(row: list[Any]) -> float:
    nonempty = [value for value in row if not is_blank(value)]
    if not nonempty:
        return -1.0
    strings = [value for value in nonempty if isinstance(value, str)]
    hits = sum(1 for value in nonempty if candidate_scores(str(value)))
    unique = len({normalize_token(value) for value in nonempty}) / len(nonempty)
    return hits * 6 + len(nonempty) * 0.35 + len(strings) / len(nonempty) + unique


def detect_header_row(rows: list[list[Any]], max_scan: int) -> int:
    limit = min(len(rows), max_scan)
    scored = [(index, header_score(rows[index])) for index in range(limit)]
    return max(scored, key=lambda item: item[1])[0] if scored else 0


def classify_value(value: Any) -> str:
    if is_blank(value):
        return "blank"
    if isinstance(value, (datetime, date)):
        return "date"
    number, number_error = parse_number_value(value)
    if number_error is None and number is not None:
        return "numeric"
    parsed_date, date_error = parse_date_value(value)
    if date_error is None and parsed_date:
        return "date_text"
    return "text"


def detect_wide_metric_families(headers: list[str]) -> list[dict[str, Any]]:
    families: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for header in headers:
        match = re.fullmatch(r"(.+?)(\d+)", header.strip())
        if not match:
            continue
        prefix, index_text = match.groups()
        prefix_token = normalize_token(prefix)
        if not any(term in prefix_token for term in ["egg", "fecund", "offspring", "产卵", "子代"]):
            continue
        families[prefix].append((header, int(index_text)))

    results = []
    for prefix, members in families.items():
        if len(members) < 2:
            continue
        members.sort(key=lambda item: item[1])
        pattern = f"^{re.escape(prefix)}(?P<day>\\d+)$"
        results.append(
            {
                "prefix": prefix,
                "source_columns": [header for header, _ in members],
                "indices": [index for _, index in members],
                "suggested_mapping": {
                    "source_pattern": pattern,
                    "target": "fecundity",
                    "age_origin": "CONFIRM_adult_or_cohort",
                    "day_group": "day",
                },
            }
        )
    return results


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_") or "sheet"


def profile_sheet(
    name: str,
    rows: list[list[Any]],
    metadata: dict[str, Any],
    max_scan: int,
    preview_rows: int,
) -> tuple[dict[str, Any], dict[str, Any], list[list[Any]]]:
    if not rows:
        empty_profile = {
            "sheet": name,
            "rows": 0,
            "columns": 0,
            "header_row": None,
            "issues": [{"code": "empty_sheet", "severity": "error", "message": "Worksheet is empty."}],
        }
        return empty_profile, {"status": "draft_requires_confirmation", "sheet": name}, []

    header_index = detect_header_row(rows, max_scan)
    headers = make_headers(rows[header_index])
    data_rows = rows[header_index + 1 :]
    repeated_rows = [header_index + 2 + index for index, row in enumerate(data_rows) if row_is_repeated_header(row, headers)]
    usable_rows = [row for row in data_rows if not row_is_repeated_header(row, headers) and any(not is_blank(value) for value in row)]

    columns = []
    source_to_candidate: dict[str, tuple[str, float]] = {}
    for column_index, header in enumerate(headers):
        values = [row[column_index] if column_index < len(row) else None for row in usable_rows]
        types = Counter(classify_value(value) for value in values)
        samples = []
        seen = set()
        for value in values:
            if is_blank(value):
                continue
            cleaned = clean_scalar(value)
            marker = repr(cleaned)
            if marker not in seen:
                seen.add(marker)
                samples.append(cleaned)
            if len(samples) >= 8:
                break
        candidates = candidate_scores(header)
        if candidates:
            source_to_candidate[header] = candidates[0]
        numeric_values = []
        missing_tokens = Counter()
        normalized_missing_markers = {
            normalize_token(marker) for marker in MISSING_MARKERS if normalize_token(marker)
        }
        for value in values:
            number, error = parse_number_value(value)
            if error is None and number is not None:
                numeric_values.append(float(number))
            token = normalize_token(value)
            if not is_blank(value) and token in normalized_missing_markers:
                missing_tokens[str(value).strip()] += 1
        columns.append(
            {
                "source_header": header,
                "column_index": column_index + 1,
                "nonempty": sum(not is_blank(value) for value in values),
                "types": dict(types),
                "unique_nonempty": len({str(clean_scalar(value)) for value in values if not is_blank(value)}),
                "sample_values": samples,
                "candidate_mappings": [{"canonical": canonical, "confidence": score} for canonical, score in candidates[:3]],
                "negative_numeric_count": sum(value < 0 for value in numeric_values),
                "recognized_missing_tokens": dict(missing_tokens),
            }
        )

    wide_families = detect_wide_metric_families(headers)
    indexed_sources = {source for family in wide_families for source in family["source_columns"]}
    best_by_canonical: dict[str, tuple[str, float]] = {}
    for source, (canonical, confidence) in source_to_candidate.items():
        if source in indexed_sources:
            continue
        previous = best_by_canonical.get(canonical)
        if previous is None or confidence > previous[1]:
            best_by_canonical[canonical] = (source, confidence)

    proposed_columns = {canonical: source for canonical, (source, confidence) in best_by_canonical.items() if confidence >= 0.8}
    issues: list[dict[str, Any]] = []
    if header_index > 0:
        issues.append(
            {
                "code": "preamble_or_multilevel_header",
                "severity": "warning",
                "message": f"Detected header on row {header_index + 1}; earlier rows require review.",
            }
        )
    merged = metadata.get("merged_ranges", {}).get(name, [])
    if merged:
        issues.append(
            {
                "code": "merged_cells",
                "severity": "warning",
                "message": f"Worksheet contains {len(merged)} merged range(s).",
                "ranges": merged,
            }
        )
    if repeated_rows:
        issues.append(
            {
                "code": "repeated_header_rows",
                "severity": "error",
                "message": "Header-like rows occur inside the data region.",
                "rows": repeated_rows,
            }
        )

    available = set(proposed_columns)
    has_event_metric = bool(available & {"hosts_offered", "parasitized", "host_killed", "female_offspring", "male_offspring"})
    has_event_time = bool(available & {"age", "observation_date"})
    event_like = has_event_metric and has_event_time

    id_source = proposed_columns.get("individual_id")
    if id_source and not event_like:
        id_index = headers.index(id_source)
        ids = [str(row[id_index]).strip() for row in usable_rows if id_index < len(row) and not is_blank(row[id_index])]
        duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
        if duplicates:
            issues.append(
                {
                    "code": "duplicate_individual_ids",
                    "severity": "error",
                    "message": "Individual identifiers are not unique after trimming whitespace.",
                    "examples": duplicates[:10],
                }
            )

    for column in columns:
        candidates = column["candidate_mappings"]
        canonical = candidates[0]["canonical"] if candidates else None
        if column["negative_numeric_count"] and canonical in COUNT_FIELDS:
            issues.append(
                {
                    "code": "negative_count",
                    "severity": "error",
                    "source_column": column["source_header"],
                    "count": column["negative_numeric_count"],
                    "message": "Negative values occur in a count-like field.",
                }
            )
        if column["recognized_missing_tokens"]:
            issues.append(
                {
                    "code": "missing_token_semantics",
                    "severity": "warning",
                    "source_column": column["source_header"],
                    "tokens": column["recognized_missing_tokens"],
                    "message": "Confirm the meaning of every nonblank missing-value token.",
                }
            )
        nonblank_types = {key for key, count in column["types"].items() if key != "blank" and count > 0}
        if len(nonblank_types) > 1:
            issues.append(
                {
                    "code": "mixed_column_types",
                    "severity": "warning",
                    "source_column": column["source_header"],
                    "types": sorted(nonblank_types),
                    "message": "Column contains mixed data representations.",
                }
            )

    sex_source = proposed_columns.get("sex")
    if sex_source:
        sex_index = headers.index(sex_source)
        sex_codes = sorted({str(row[sex_index]).strip() for row in usable_rows if sex_index < len(row) and not is_blank(row[sex_index])})
        normalized_sex = {normalize_token(value) for value in sex_codes}
        if len(normalized_sex) > 2:
            issues.append(
                {
                    "code": "mixed_sex_codes",
                    "severity": "warning",
                    "source_column": sex_source,
                    "codes": sex_codes,
                    "message": "Multiple sex code systems require an explicit value map.",
                }
            )

    if wide_families and {"individual_id", "treatment", "sex", "death_date"}.issubset(available) and bool(available & {"egg_date", "adult_emergence_date"}):
        layout = "wide_cohort"
        route = "cohort_life_table_candidate"
    elif has_event_metric and has_event_time and {"individual_id", "treatment"}.issubset(available):
        layout = "event_long"
        route = "parasitoid_event_candidate"
    else:
        layout = "summary_or_unknown"
        route = "manual_confirmation_required"

    blocking = any(issue["severity"] == "error" for issue in issues) or route == "manual_confirmation_required"
    draft = {
        "status": "draft_requires_confirmation",
        "sheet": name,
        "header_row": header_index + 1,
        "layout": layout,
        "route": route,
        "columns": proposed_columns,
        "wide_metrics": [family["suggested_mapping"] for family in wide_families],
        "value_maps": {
            "sex": {"F": "female", "M": "male", "♀": "female", "♂": "male", "雌": "female", "雄": "male", "female": "female", "male": "male"},
            "alive": {"Y": "yes", "N": "no", "yes": "yes", "no": "no"},
        },
        "missing_tokens": ["", "NA", "N/A"],
        "date_fields": sorted(field for field in proposed_columns if field in DATE_FIELDS),
        "numeric_fields": sorted(field for field in proposed_columns if field in NUMERIC_FIELDS),
        "age_origin": "CONFIRM",
        "exclude_repeated_header": True,
        "blocking_review_required": blocking,
    }
    profile = {
        "sheet": name,
        "rows": len(rows),
        "columns": len(headers),
        "header_row": header_index + 1,
        "data_rows_after_header": len(data_rows),
        "nonblank_data_rows": len(usable_rows),
        "formula_count": metadata.get("formula_counts", {}).get(name, 0),
        "wide_metric_families": wide_families,
        "route_proposal": route,
        "requires_confirmation": blocking or bool(issues),
        "column_profiles": columns,
        "issues": issues,
    }
    return profile, draft, rows[: header_index + 1 + preview_rows]


def write_preview(path: Path, rows: list[list[Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        for row in rows:
            writer.writerow([clean_scalar(value) for value in row])


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile insect-fitness tabular inputs and generate draft mapping contracts.")
    parser.add_argument("input_file")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--sheet", help="Profile only one worksheet.")
    parser.add_argument("--header-scan-rows", type=int, default=20)
    parser.add_argument("--preview-rows", type=int, default=20)
    args = parser.parse_args()

    tables, metadata = load_tables(args.input_file)
    selected = {args.sheet: tables[args.sheet]} if args.sheet else tables
    output_dir = Path(args.output_dir).expanduser().resolve()
    profiles = []
    for name, rows in selected.items():
        profile, draft, preview = profile_sheet(name, rows, metadata, args.header_scan_rows, args.preview_rows)
        profiles.append(profile)
        slug = safe_name(name)
        write_json(output_dir / "mapping_proposals" / f"{slug}.json", draft)
        write_preview(output_dir / "previews" / f"{slug}.csv", preview)

    summary = {
        "source": metadata,
        "sheet_count": len(selected),
        "sheets": profiles,
        "notice": "Every mapping is a draft. Confirm scientific semantics before normalization or calculation.",
    }
    write_json(output_dir / "input_profile.json", summary)
    print(f"Profiled {len(selected)} sheet(s). Output: {output_dir / 'input_profile.json'}")


if __name__ == "__main__":
    main()
