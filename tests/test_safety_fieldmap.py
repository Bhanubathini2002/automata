"""Safety: fieldmap must ABORT on SSN/DOB/citizenship/clearance — never invent answers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pipeline.apply_tier_a import fieldmap as FM


class TestSafetyFieldmap(unittest.TestCase):
    def test_ssn_aborts(self):
        self.assertEqual(FM.resolve("Social Security Number"), FM.ABORT)
        self.assertEqual(FM.resolve("SSN"), FM.ABORT)

    def test_dob_aborts(self):
        self.assertEqual(FM.resolve("Date of Birth"), FM.ABORT)
        self.assertEqual(FM.resolve("DOB"), FM.ABORT)

    def test_citizenship_aborts(self):
        self.assertEqual(FM.resolve("Are you a U.S. citizen?"), FM.ABORT)
        self.assertEqual(FM.resolve("Citizenship status"), FM.ABORT)

    def test_clearance_aborts(self):
        self.assertEqual(FM.resolve("Do you have a security clearance?"), FM.ABORT)
        self.assertEqual(FM.resolve("TS/SCI clearance level"), FM.ABORT)

    def test_work_auth_does_not_abort(self):
        v = FM.resolve("Are you legally authorized to work in the United States?")
        self.assertNotEqual(v, FM.ABORT)
        self.assertIsNotNone(v)

    def test_polarity_safe_rejects_negation_flip(self):
        self.assertFalse(FM.polarity_safe("Yes", "No"))
        self.assertTrue(FM.polarity_safe("Yes", "Yes"))
        self.assertTrue(FM.polarity_safe("No", "No, I am not a veteran"))

    def test_fuzzy_prefer_not(self):
        opts = ["Yes", "No", "Prefer not to say", "Decline to answer"]
        self.assertEqual(FM.fuzzy_option(FM.PREFER_NOT, opts), "Prefer not to say")


if __name__ == "__main__":
    unittest.main()
