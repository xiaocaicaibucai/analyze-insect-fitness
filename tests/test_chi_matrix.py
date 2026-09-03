from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from chi_matrix import audit_chi_sections, detect_chi_sections  # noqa: E402


class ChiMatrixAuditTest(unittest.TestCase):
    def test_detects_repeated_treatment_sections(self) -> None:
        rows = [
            ["AG", "AG"],
            [None, "number", "sex", None, "N1", "N2", "adult", "egg"],
            [None, 1, "F", 6, 2, 3, 4, 0, 5, 0],
            [None, 2, "N", 6, 2, -2, None, None],
            [None, "A-"],
            [None, "number", "sex", None, "N1", "N2", "adult", "egg"],
            ["A-", 1, "M", 6, 2, 3, 5],
            [None, 2, "F", 6, 2, 3, 3, 0, 4],
        ]
        sections = detect_chi_sections(rows)
        self.assertEqual([section["group"] for section in sections], ["AG", "A-"])
        self.assertEqual([section["record_count"] for section in sections], [2, 2])
        self.assertTrue(sections[0]["stage_columns"][0]["header_missing"])

    def test_flags_fecundity_gaps_and_lifetime_conflicts(self) -> None:
        rows = [
            ["AG"],
            ["number", "sex", "egg_stage", "N1", "adult", "egg"],
            [1, "F", 6, 2, 3, 0, None, 4, 1],
            [2, "F", 6, 2, 2, 0, 5, 1],
            [3, "N", 6, -2, None],
        ]
        sections = detect_chi_sections(rows)
        _, issues = audit_chi_sections(rows, sections)
        codes = {issue["code"] for issue in issues}
        self.assertIn("fecundity_internal_gap", codes)
        self.assertIn("fecundity_after_adult_lifetime", codes)
        self.assertIn("chi_semantics_require_confirmation", codes)


if __name__ == "__main__":
    unittest.main()
