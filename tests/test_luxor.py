"""Luxor-bot tesztek: beolvasás és egészségfigyelés. Futtatás: python -m unittest discover -s tests -v"""
import datetime as dt
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import luxor_bot as lb       # noqa: E402
import luxor_health as lh    # noqa: E402

NUMS = [53, 72, 50, 4, 41, 45, 40, 6, 69, 52, 1, 2, 3, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16,
        17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34]   # 42 szám, húzási sorrend


class Parse(unittest.TestCase):
    def test_csv(self):
        line = "2026;45;2026.11.07.;38;16;34;42;" + ";".join(map(str, NUMS))
        r = lb.parse_source(line)
        self.assertEqual((r[0]["year"], r[0]["week"], r[0]["nums"]), (2026, 45, NUMS))

    def test_latest_page_keeps_order(self):
        html = "<h3>45. hét - november 7. (szombat)</h3><ul>" + "".join(f"<li>{n}</li>" for n in NUMS) + "</ul>"
        r = lb.parse_source(html, today=dt.date(2026, 11, 8))
        self.assertEqual((r[0]["week"], r[0]["nums"]), (45, NUMS))

    def test_rejects_short(self):
        html = "<h3>45. hét - november 7. (szombat)</h3>" + " ".join(map(str, NUMS[:20]))
        self.assertEqual(lb.parse_source(html, today=dt.date(2026, 11, 8)), [])


class Health(unittest.TestCase):
    def test_source_alert_once_and_recovery(self):
        st = {}
        msgs = [lh.note_source(st, "u", False, error="404") for _ in range(5)]
        self.assertEqual(sum(1 for m in msgs if m), 1)
        self.assertIn("helyreállt", lh.note_source(st, "u", True, 1, (2026, 46)))

    def test_consistency_order_and_set(self):
        st = {}
        a = {"year": 2026, "week": 46, "nums": NUMS}
        b = {"year": 2026, "week": 46, "nums": sorted(NUMS)}
        msgs = lh.check_consistency(st, {"csv": [a], "page": [b]})
        self.assertEqual(len(msgs), 1)
        self.assertIn("más sorrendben", msgs[0])
        self.assertEqual(lh.check_consistency(st, {"csv": [a], "page": [b]}), [])  # csak egyszer

    def test_missing_result(self):
        st, tip = {}, {"for_draw": "2026-11-28"}
        self.assertIsNone(lh.missing_result(st, tip, dt.datetime(2026, 11, 29, 11, 0)))
        self.assertIsNotNone(lh.missing_result(st, tip, dt.datetime(2026, 11, 29, 12, 10)))
        self.assertIsNone(lh.missing_result(st, tip, dt.datetime(2026, 11, 29, 13, 0)))


if __name__ == "__main__":
    unittest.main()
