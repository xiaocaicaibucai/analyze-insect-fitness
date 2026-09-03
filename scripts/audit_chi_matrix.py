#!/usr/bin/env python3
"""Audit a prepared Chi/TWOSEX-style matrix without calculating metrics."""

from __future__ import annotations

import argparse
from pathlib import Path

from _shared import load_tables, select_sheet, write_csv, write_json
from chi_matrix import audit_chi_sections, detect_chi_sections


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit prepared Chi/TWOSEX-style individual matrices.")
    parser.add_argument("input_file")
    parser.add_argument("--sheet", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    tables, metadata = load_tables(args.input_file)
    sheet, rows = select_sheet(tables, args.sheet)
    sections = detect_chi_sections(rows)
    if not sections:
        raise ValueError(f"No prepared Chi/TWOSEX-style section was detected in worksheet {sheet!r}.")
    summaries, issues = audit_chi_sections(rows, sections)
    for issue in issues:
        issue["source_sheet"] = sheet

    output_dir = Path(args.output_dir).expanduser().resolve()
    errors = sum(issue["severity"] == "error" for issue in issues)
    warnings = sum(issue["severity"] == "warning" for issue in issues)
    source_metadata = {
        "source_file": metadata["source_file"],
        "sha256": metadata["sha256"],
        "format": metadata["format"],
        "formula_count": metadata.get("formula_counts", {}).get(sheet, 0),
        "merged_ranges": metadata.get("merged_ranges", {}).get(sheet, []),
    }
    write_json(
        output_dir / "chi_matrix_audit.json",
        {
            "source": source_metadata,
            "sheet": sheet,
            "layout": "chi_prepared_matrix",
            "status": "blocked" if errors else "requires_confirmation",
            "formal_calculation_ready": False,
            "section_count": len(summaries),
            "sections": summaries,
            "issue_counts": {"error": errors, "warning": warnings},
            "notice": (
                "This audit recognizes mechanical Chi-style patterns only; it does not confirm "
                "biological semantics or authorize calculation."
            ),
        },
    )
    write_csv(
        output_dir / "issues.csv",
        [
            "severity",
            "source_sheet",
            "source_row",
            "source_column",
            "code",
            "raw_value",
            "message",
            "suggested_action",
        ],
        issues,
    )
    print(f"Audited {len(summaries)} Chi-style section(s); errors={errors}, warnings={warnings}: {output_dir}")


if __name__ == "__main__":
    main()
