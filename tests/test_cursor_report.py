"""对照报告核对工具（tools/check_cursor_report.py）：用户要求迁入的几类都到位，去向不同的条目都写明了处理。"""
import csv
import os
import sys
import unittest
from collections import Counter

from helpers import ROOT, model_and_plan

sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_cursor_report as ccr  # noqa: E402

SAME = "同组"
CN_ONLY = "同组（只写进 mihomo / sing-box）"


class CursorReport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(ccr.CSV, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        m, plan = model_and_plan()
        cls.cursor_rows, cls.reject_rows = ccr.analyze(rows, m, plan)

    def cats(self, group):
        return Counter(x["cat"] for x in self.cursor_rows if x["group"] == group)

    def test_requested_migrations_route_to_the_same_group(self):
        """2026-09-29 要求迁入的：Google 187 个国家域名、Microsoft 365 清单、41 条广告、72 条国内域名、claude.app、Apple AI。"""
        self.assertEqual(self.cats("Google"), Counter({SAME: 187}))
        self.assertEqual(self.cats("Microsoft"), Counter({SAME: 68}))
        self.assertEqual(self.cats("广告拦截"), Counter({SAME: 41}))
        self.assertEqual(self.cats("国内直连"), Counter({CN_ONLY: 70, SAME: 2}))
        self.assertEqual(self.cats("Apple AI"), Counter({SAME: 17, "已替换": 1}))
        self.assertIn(("claude.app", SAME), [(x["value"], x["cat"]) for x in self.cursor_rows if x["group"] == "Claude"])

    def test_every_difference_has_a_disposition(self):
        undocumented = [f"{x['group']} {x['value']}" for x in self.cursor_rows
                        if x["cat"] not in (SAME, CN_ONLY) and not x["note"]]
        undocumented += [f"{x['group']} {x['value']}" for x in self.reject_rows if not x["note"]]
        self.assertFalse(undocumented, "去向不同但没有写明处理：" + "、".join(undocumented))

    def test_adopted_removals_are_gone(self):
        state = {x["value"]: x["state"] for x in self.reject_rows}
        for v in ("sora.com", "azure.com", "byteoversea.com", "byteoversea.net"):
            self.assertEqual(state[v], "已不在", v)


if __name__ == "__main__":
    unittest.main()
