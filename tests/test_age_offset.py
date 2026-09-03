from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "normalize_records.py"


class CanonicalAgeOffsetTest(unittest.TestCase):
    def normalize(self, source_rows: list[list[str]], mapping: dict[str, object]) -> list[dict[str, str]]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        source = base / "source.csv"
        contract = base / "mapping.json"
        output = base / "canonical"
        with source.open("w", encoding="utf-8", newline="") as handle:
            csv.writer(handle).writerows(source_rows)
        contract.write_text(json.dumps(mapping), encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                str(source),
                "--mapping",
                str(contract),
                "--output-dir",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        with (output / "observations.csv").open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))

    def test_event_long_day_one_can_map_to_age_zero(self) -> None:
        observations = self.normalize(
            [["id", "trt", "day", "eggs"], ["i1", "control", "1", "3"]],
            {
                "status": "confirmed",
                "header_row": 1,
                "layout": "event_long",
                "columns": {
                    "individual_id": "id",
                    "treatment": "trt",
                    "age": "day",
                    "fecundity": "eggs",
                },
                "missing_tokens": [""],
                "numeric_fields": ["age", "fecundity"],
                "age_origin": "cohort",
                "age_offset": -1,
            },
        )
        self.assertEqual(observations[0]["age"], "0")

    def test_wide_metric_can_override_sheet_offset(self) -> None:
        observations = self.normalize(
            [["id", "trt", "eggs_D1"], ["i1", "control", "3"]],
            {
                "status": "confirmed",
                "header_row": 1,
                "layout": "wide_cohort",
                "columns": {"individual_id": "id", "treatment": "trt"},
                "wide_metrics": [
                    {
                        "source_pattern": "^eggs_D(?P<day>\\d+)$",
                        "target": "fecundity",
                        "day_group": "day",
                        "age_origin": "cohort",
                        "age_offset": -1,
                    }
                ],
                "missing_tokens": [""],
                "numeric_fields": ["fecundity"],
                "age_offset": 0,
            },
        )
        self.assertEqual(observations[0]["age"], "0")


if __name__ == "__main__":
    unittest.main()
