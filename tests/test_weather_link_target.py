#!/usr/bin/env python3
"""
Tests for Plan 09-04 Task 1: _same_to_county_ugc pure helper + _FIPS_STATE_POSTAL table.

Unit tests covering:
- Correct SAME→county-UGC derivation for known FIPS codes (CA/006037, OK/040109, TX/048201)
- Rejection of None, empty, 5-digit, non-numeric-state, and unknown-state inputs (omit-not-fake D-10)
- Derived values always satisfy _valid_ugc allowlist
- _FIPS_STATE_POSTAL table coverage (>=56 entries, spot-checks: CA/OK/TX/DC/PR)
"""

import importlib.util
import os
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "claude-statusline.py")


def _load_script_module():
    """Import claude-statusline.py as a module (does not run main)."""
    spec = importlib.util.spec_from_file_location("claude_statusline", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestSameToCountyUgc(unittest.TestCase):
    """Unit tests for _same_to_county_ugc() and _FIPS_STATE_POSTAL."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _load_script_module()
        cls.fn = cls.mod._same_to_county_ugc
        cls.table = cls.mod._FIPS_STATE_POSTAL

    # -------------------------------------------------------------------
    # Success cases
    # -------------------------------------------------------------------

    def test_ca_los_angeles(self):
        """SAME 006037 → CAC037 (CA state FIPS 06, county FIPS 037)."""
        result = self.fn("006037")
        self.assertEqual(result, "CAC037",
                         f"Expected 'CAC037', got {result!r}")

    def test_ok_oklahoma_county(self):
        """SAME 040109 → OKC109 (OK state FIPS 40, county FIPS 109)."""
        result = self.fn("040109")
        self.assertEqual(result, "OKC109",
                         f"Expected 'OKC109', got {result!r}")

    def test_tx_harris_county(self):
        """SAME 048201 → TXC201 (TX state FIPS 48, county FIPS 201)."""
        result = self.fn("048201")
        self.assertEqual(result, "TXC201",
                         f"Expected 'TXC201', got {result!r}")

    def test_success_cases_pass_valid_ugc(self):
        """Every successful result must satisfy _valid_ugc (returns non-None)."""
        success_inputs = ["006037", "040109", "048201"]
        for inp in success_inputs:
            result = self.fn(inp)
            self.assertIsNotNone(result, f"_same_to_county_ugc({inp!r}) returned None")
            validated = self.mod._valid_ugc(result)
            self.assertIsNotNone(
                validated,
                f"_valid_ugc({result!r}) returned None for input {inp!r} — "
                f"derived code must satisfy the UGC allowlist"
            )

    # -------------------------------------------------------------------
    # Rejection / omit-not-fake cases (D-10)
    # -------------------------------------------------------------------

    def test_none_returns_none(self):
        """None input → None (D-10 omit-not-fake)."""
        self.assertIsNone(self.fn(None))

    def test_empty_string_returns_none(self):
        """Empty string → None."""
        self.assertIsNone(self.fn(""))

    def test_five_digit_returns_none(self):
        """5-digit string (short FIPS) → None; must not raise IndexError."""
        self.assertIsNone(self.fn("12345"))

    def test_non_numeric_state_returns_none(self):
        """SAME with non-numeric state field ('0xx037') → None."""
        self.assertIsNone(self.fn("0xx037"))

    def test_unknown_state_fips_returns_none(self):
        """State FIPS 99 not in _FIPS_STATE_POSTAL → None (D-10)."""
        self.assertIsNone(self.fn("099037"))

    def test_non_numeric_full_returns_none(self):
        """All-alpha string → None; does not raise."""
        self.assertIsNone(self.fn("abcdef"))

    def test_seven_digit_returns_none(self):
        """7-digit string (too long) → None."""
        self.assertIsNone(self.fn("0060370"))

    # -------------------------------------------------------------------
    # _FIPS_STATE_POSTAL table coverage
    # -------------------------------------------------------------------

    def test_table_has_minimum_56_entries(self):
        """_FIPS_STATE_POSTAL must have at least 56 entries (50 states + DC + 5 territories)."""
        self.assertGreaterEqual(
            len(self.table), 56,
            f"Table has {len(self.table)} entries; expected >= 56"
        )

    def test_table_ca(self):
        """_FIPS_STATE_POSTAL['06'] == 'CA'."""
        self.assertEqual(self.table.get("06"), "CA")

    def test_table_ok(self):
        """_FIPS_STATE_POSTAL['40'] == 'OK'."""
        self.assertEqual(self.table.get("40"), "OK")

    def test_table_tx(self):
        """_FIPS_STATE_POSTAL['48'] == 'TX'."""
        self.assertEqual(self.table.get("48"), "TX")

    def test_table_dc(self):
        """_FIPS_STATE_POSTAL['11'] == 'DC'."""
        self.assertEqual(self.table.get("11"), "DC")

    def test_table_pr(self):
        """_FIPS_STATE_POSTAL['72'] == 'PR'."""
        self.assertEqual(self.table.get("72"), "PR")

    def test_table_guam(self):
        """_FIPS_STATE_POSTAL['66'] == 'GU'."""
        self.assertEqual(self.table.get("66"), "GU")

    def test_table_vi(self):
        """_FIPS_STATE_POSTAL['78'] == 'VI'."""
        self.assertEqual(self.table.get("78"), "VI")

    def test_table_as(self):
        """_FIPS_STATE_POSTAL['60'] == 'AS'."""
        self.assertEqual(self.table.get("60"), "AS")

    def test_table_mp(self):
        """_FIPS_STATE_POSTAL['69'] == 'MP'."""
        self.assertEqual(self.table.get("69"), "MP")


if __name__ == "__main__":
    unittest.main()
