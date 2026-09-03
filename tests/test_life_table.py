from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "life_table.py"
GOLDEN = ROOT / "tests" / "fixtures" / "chi_equation_golden.json"


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class LifeTableLiteratureInvariantsTest(unittest.TestCase):
    def run_case(self, resamples: int) -> tuple[list[dict[str, str]], dict[str, object]]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        individuals = base / "individuals.csv"
        observations = base / "observations.csv"
        output = base / "result"
        write_csv(
            individuals,
            [
                "individual_id",
                "treatment",
                "biological_replicate",
                "egg_date",
                "death_date",
                "record_status",
            ],
            [
                {
                    "individual_id": "female-1",
                    "treatment": "control",
                    "biological_replicate": "r1",
                    "egg_date": "2026-01-01",
                    "death_date": "2026-01-05",
                    "record_status": "complete",
                },
                {
                    "individual_id": "male-1",
                    "treatment": "control",
                    "biological_replicate": "r2",
                    "egg_date": "2026-01-01",
                    "death_date": "2026-01-05",
                    "record_status": "complete",
                },
            ],
        )
        write_csv(
            observations,
            ["individual_id", "age", "age_origin", "fecundity"],
            [{"individual_id": "female-1", "age": "2", "age_origin": "cohort", "fecundity": "4"}],
        )
        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--individuals",
                str(individuals),
                "--observations",
                str(observations),
                "--output-dir",
                str(output),
                "--bootstrap-unit",
                "individual",
                "--confirm-unlisted-fecundity-zero",
                "--resamples",
                str(resamples),
                "--seed",
                "7",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        with (output / "metrics.csv").open(encoding="utf-8", newline="") as handle:
            metrics = list(csv.DictReader(handle))
        methods = json.loads((output / "methods.json").read_text(encoding="utf-8"))
        return metrics, methods

    def test_zero_indexed_euler_lotka_identity(self) -> None:
        rows, methods = self.run_case(resamples=0)
        by_metric = {row["metric"]: row for row in rows}
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        expected = golden["expected"]
        self.assertAlmostEqual(float(by_metric["R0"]["estimate"]), expected["R0"])
        self.assertAlmostEqual(float(by_metric["r"]["estimate"]), expected["r"], places=10)
        self.assertAlmostEqual(float(by_metric["lambda"]["estimate"]), expected["lambda"], places=10)
        self.assertAlmostEqual(float(by_metric["T"]["estimate"]), expected["T"], places=10)
        self.assertEqual(by_metric["r"]["ci_scope"], "not_requested")
        self.assertEqual(methods["analysis"], "cohort_euler_lotka_core_metrics")
        self.assertEqual(methods["offspring_mode"], "cohort_total")

    def test_noncalculable_bootstrap_samples_are_exposed(self) -> None:
        rows, _ = self.run_case(resamples=50)
        by_metric = {row["metric"]: row for row in rows}
        r_row = by_metric["r"]
        r_calculable = int(r_row["calculable_resamples"])
        self.assertGreater(r_calculable, 0)
        self.assertLess(r_calculable, 50)
        self.assertEqual(int(r_row["noncalculable_resamples"]), 50 - r_calculable)
        self.assertEqual(r_row["ci_scope"], "conditional_on_calculable_resamples")
        self.assertEqual(by_metric["R0"]["calculable_resamples"], "50")
        self.assertEqual(by_metric["R0"]["ci_scope"], "all_resamples")


if __name__ == "__main__":
    unittest.main()
