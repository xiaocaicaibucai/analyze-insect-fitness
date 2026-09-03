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


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


class LifeTableV2Test(unittest.TestCase):
    def make_workspace(self) -> tuple[Path, Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name)
        return base / "individuals.csv", base / "observations.csv", base / "result"

    def run_script(
        self,
        individuals: Path,
        observations: Path,
        output: Path,
        *extra: str,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--individuals",
                str(individuals),
                "--observations",
                str(observations),
                "--output-dir",
                str(output),
                "--confirm-unlisted-fecundity-zero",
                *extra,
            ],
            check=check,
            capture_output=True,
            text=True,
        )

    def write_two_sex_case(self, individuals: Path, observations: Path) -> None:
        write_csv(
            individuals,
            [
                "individual_id",
                "treatment",
                "biological_replicate",
                "egg_date",
                "death_date",
                "record_status",
                "sex",
            ],
            [
                {
                    "individual_id": "female-1",
                    "treatment": "control",
                    "biological_replicate": "r1",
                    "egg_date": "2026-01-01",
                    "death_date": "2026-01-05",
                    "record_status": "complete",
                    "sex": "female",
                },
                {
                    "individual_id": "male-1",
                    "treatment": "control",
                    "biological_replicate": "r2",
                    "egg_date": "2026-01-01",
                    "death_date": "2026-01-03",
                    "record_status": "complete",
                    "sex": "male",
                },
            ],
        )
        write_csv(
            observations,
            [
                "individual_id",
                "age",
                "age_origin",
                "fecundity",
                "female_offspring",
                "male_offspring",
            ],
            [
                {
                    "individual_id": "female-1",
                    "age": "2",
                    "age_origin": "cohort",
                    "fecundity": "4",
                    "female_offspring": "1",
                    "male_offspring": "3",
                }
            ],
        )

    def test_offspring_modes_and_male_invariance_diagnostic(self) -> None:
        expected_r0 = {"cohort_total": 2.0, "female_line": 1.0, "sexed_total": 2.0}
        for mode, expected in expected_r0.items():
            with self.subTest(mode=mode):
                individuals, observations, output = self.make_workspace()
                self.write_two_sex_case(individuals, observations)
                self.run_script(
                    individuals,
                    observations,
                    output,
                    "--bootstrap-unit",
                    "individual",
                    "--resamples",
                    "0",
                    "--offspring-mode",
                    mode,
                )
                metrics = {row["metric"]: row for row in read_csv(output / "metrics.csv")}
                self.assertAlmostEqual(float(metrics["R0"]["estimate"]), expected)
                diagnostic = read_csv(output / "male_invariance_diagnostics.csv")[0]
                expected_status = "not_applicable_female_line" if mode == "female_line" else "invariant"
                self.assertEqual(diagnostic["status"], expected_status)
                if mode != "female_line":
                    self.assertAlmostEqual(float(diagnostic["r_difference"]), 0.0)
                methods = json.loads((output / "methods.json").read_text(encoding="utf-8"))
                self.assertEqual(methods["offspring_mode"], mode)

    def test_sexed_total_rejects_partial_sex_counts(self) -> None:
        individuals, observations, output = self.make_workspace()
        self.write_two_sex_case(individuals, observations)
        rows = read_csv(observations)
        rows[0]["male_offspring"] = ""
        write_csv(observations, list(rows[0]), rows)
        result = self.run_script(
            individuals,
            observations,
            output,
            "--bootstrap-unit",
            "individual",
            "--resamples",
            "0",
            "--offspring-mode",
            "sexed_total",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires both female_offspring and male_offspring", result.stderr)

    def test_female_line_rejects_unknown_initial_sex(self) -> None:
        individuals, observations, output = self.make_workspace()
        self.write_two_sex_case(individuals, observations)
        rows = read_csv(individuals)
        rows[1]["sex"] = ""
        write_csv(individuals, list(rows[0]), rows)
        result = self.run_script(
            individuals,
            observations,
            output,
            "--bootstrap-unit",
            "individual",
            "--resamples",
            "0",
            "--offspring-mode",
            "female_line",
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires confirmed sex for every enrolled individual", result.stderr)

    def test_independent_treatment_contrast(self) -> None:
        individuals, observations, output = self.make_workspace()
        individual_rows: list[dict[str, str]] = []
        observation_rows: list[dict[str, str]] = []
        for treatment, offspring in [("A", "4"), ("B", "2")]:
            for sex in ["female", "male"]:
                individual_id = f"{treatment}-{sex}"
                individual_rows.append(
                    {
                        "individual_id": individual_id,
                        "treatment": treatment,
                        "biological_replicate": f"{treatment}-{sex}",
                        "egg_date": "2026-01-01",
                        "death_date": "2026-01-05",
                        "record_status": "complete",
                        "sex": sex,
                    }
                )
                if sex == "female":
                    observation_rows.append(
                        {
                            "individual_id": individual_id,
                            "age": "2",
                            "age_origin": "cohort",
                            "fecundity": offspring,
                        }
                    )
        write_csv(individuals, list(individual_rows[0]), individual_rows)
        write_csv(observations, list(observation_rows[0]), observation_rows)
        self.run_script(
            individuals,
            observations,
            output,
            "--bootstrap-unit",
            "individual",
            "--resamples",
            "80",
            "--seed",
            "11",
            "--contrast-design",
            "independent",
        )
        contrasts = {row["metric"]: row for row in read_csv(output / "treatment_contrasts.csv")}
        self.assertAlmostEqual(float(contrasts["R0"]["estimate_difference"]), 1.0)
        self.assertEqual(contrasts["R0"]["contrast_design"], "independent")
        self.assertEqual(contrasts["R0"]["calculable_resamples"], "80")

    def test_paired_contrast_preserves_replicate_matching(self) -> None:
        individuals, observations, output = self.make_workspace()
        individual_rows: list[dict[str, str]] = []
        observation_rows: list[dict[str, str]] = []
        for treatment, base in [("A", 2), ("B", 1)]:
            for replicate in range(1, 4):
                individual_id = f"{treatment}-r{replicate}"
                individual_rows.append(
                    {
                        "individual_id": individual_id,
                        "treatment": treatment,
                        "biological_replicate": f"r{replicate}",
                        "egg_date": "2026-01-01",
                        "death_date": "2026-01-05",
                        "record_status": "complete",
                        "sex": "female",
                    }
                )
                observation_rows.append(
                    {
                        "individual_id": individual_id,
                        "age": "2",
                        "age_origin": "cohort",
                        "fecundity": str(base + replicate - 1),
                    }
                )
        write_csv(individuals, list(individual_rows[0]), individual_rows)
        write_csv(observations, list(observation_rows[0]), observation_rows)
        self.run_script(
            individuals,
            observations,
            output,
            "--bootstrap-unit",
            "biological_replicate",
            "--resamples",
            "60",
            "--seed",
            "13",
            "--contrast-design",
            "paired_by_replicate",
        )
        contrasts = {row["metric"]: row for row in read_csv(output / "treatment_contrasts.csv")}
        self.assertAlmostEqual(float(contrasts["R0"]["estimate_difference"]), 1.0)
        self.assertAlmostEqual(float(contrasts["R0"]["ci_lower"]), 1.0)
        self.assertAlmostEqual(float(contrasts["R0"]["ci_upper"]), 1.0)


if __name__ == "__main__":
    unittest.main()
