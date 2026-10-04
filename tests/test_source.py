"""统一源校验：故意写错的数据必须被拒绝（确认校验器真的在工作）。"""
import os
import shutil
import tempfile
import unittest

import yaml

from helpers import ROOT, model_and_plan
from generator.model import SourceError, build_plan, load


class BrokenSource:
    def __init__(self):
        self.dir = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, "source"), os.path.join(self.dir, "source"))

    def edit(self, rel, fn):
        p = os.path.join(self.dir, "source", rel)
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        fn(data)
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def load(self):
        m = load(self.dir)
        return m, build_plan(m)

    def close(self):
        shutil.rmtree(self.dir)


def add_rule(service_id, rule, file="services/streaming.yaml"):
    def fn(data):
        for s in data["services"]:
            if s["id"] == service_id:
                s["rules"].append(rule)
                return
        raise KeyError(service_id)
    return file, fn


class SourceValidation(unittest.TestCase):
    def assertRejected(self, rel, fn, needle):
        b = BrokenSource()
        try:
            b.edit(rel, fn)
            with self.assertRaises(SourceError) as cm:
                b.load()
            self.assertIn(needle, str(cm.exception))
        finally:
            b.close()

    def test_current_source_is_valid(self):
        m, p = model_and_plan()
        self.assertGreater(len(p.product), 300)

    def test_residual_group_cannot_steal_independent_service(self):
        self.assertRejected(*add_rule("dazn", {"suffix": "tv.apple.com", "ev": "maintainer"}), "剩余集合")

    def test_shared_cloud_root_rejected(self):
        self.assertRejected(*add_rule("netflix", {"suffix": "amazonaws.com", "ev": "maintainer"}), "共享云")

    def test_google_shared_root_not_for_ai(self):
        f, fn = add_rule("google_ai", {"suffix": "googleusercontent.com", "ev": "maintainer"}, "services/ai.yaml")
        self.assertRejected(f, fn, "Google 共享根域")

    def test_duplicate_rule_rejected(self):
        self.assertRejected(*add_rule("netflix", {"suffix": "youtube.com", "ev": "dlc"}), "规则重复")

    def test_unknown_evidence_rejected(self):
        self.assertRejected(*add_rule("netflix", {"suffix": "netflix.example", "ev": "nope"}), "未登记的证据")

    def test_keyword_rule_needs_justification(self):
        self.assertRejected(*add_rule("netflix", {"keyword": "netflix", "ev": "dlc"}), "关键词规则")

    def test_exception_target_conflict_rejected(self):
        def fn(data):
            data["exceptions"].append({"domain": "s2.youtube.com", "target": "国外默认", "ev": "maintainer"})
        b = BrokenSource()
        try:
            b.edit("adblock.yaml", fn)
            with self.assertRaises(SourceError) as cm:
                b.load()
            self.assertIn("产品规则归属是 YouTube", str(cm.exception))
        finally:
            b.close()

    def test_unmatched_exception_needs_target(self):
        def fn(data):
            data["exceptions"].append({"domain": "login.unknown.example", "ev": "maintainer"})
        b = BrokenSource()
        try:
            b.edit("adblock.yaml", fn)
            with self.assertRaises(SourceError) as cm:
                b.load()
            self.assertIn("必须写明 target", str(cm.exception))
        finally:
            b.close()

    def test_paypal_must_not_follow_foreign_default(self):
        def fn(data):
            for g in data["groups"]:
                if g["name"] == "PayPal":
                    g["options"].append("国外默认")
        self.assertRejected("groups.yaml", fn, "PayPal 不得跟随国外默认")

    def test_group_member_must_be_region_or_entry(self):
        def fn(data):
            for g in data["groups"]:
                if g["name"] == "OpenAI":
                    g["options"] = ["Cursor"]
        self.assertRejected("groups.yaml", fn, "不是地区入口")

    def test_community_evidence_needs_upstream_mapping(self):
        # TELASA 在两个快照里都没有，服务没有登记 upstream；标成 dlc 必须被拒绝
        self.assertRejected(*add_rule("telasa", {"suffix": "telasa.example", "ev": "dlc"}), "没有登记 upstream.dlc")


class UpstreamEvidenceRecord(unittest.TestCase):
    """社区来源条目必须有固定快照的核对记录（docs/evidence/upstream-snapshot.json）。
    记录由 tools/check_upstream_evidence.py 在有上游检出目录时生成；这里不需要上游数据，只检查记录与统一源一致，
    防止改了规则却没有重新核对。"""

    @classmethod
    def setUpClass(cls):
        import json
        with open(os.path.join(ROOT, "docs", "evidence", "upstream-snapshot.json"), encoding="utf-8") as f:
            cls.rec = json.load(f)
        cls.m, cls.plan = model_and_plan()

    def test_snapshots_match_evidence_registry(self):
        self.assertEqual(self.rec["snapshots"]["dlc"]["commit"], str(self.m.evidence["dlc"]["snapshot"]))
        self.assertEqual(self.rec["snapshots"]["bm7"]["commit"], str(self.m.evidence["bm7-snap"]["snapshot"]))
        self.assertEqual(self.rec["summary"]["failures"], 0)

    def test_every_community_rule_is_backed(self):
        from generator.model import COMMUNITY_EV_SOURCE
        index = {(r["service"], r["kind"], r["value"]): r for r in self.rec["rules"]}
        problems = []
        for s in self.m.services:
            if s.file == "local.yaml":
                continue
            for r in s.rules:
                src = COMMUNITY_EV_SOURCE.get(r.ev)
                if not src:
                    continue
                got = index.get((s.id, r.kind, r.value))
                if got is None:
                    problems.append(f"{s.id} {r.kind},{r.value}：没有核对记录（改动后需要重新运行核对工具）")
                    continue
                if got["ev"] != r.ev or got[src]["status"] not in ("same", "covered"):
                    problems.append(f"{s.id} {r.kind},{r.value}：记录为 {got['ev']} / {got[src]['status']}")
                lists = set(s.upstream.get(src, []))
                if not any(h.split(":", 1)[0] in lists for h in got[src]["hits"]):
                    problems.append(f"{s.id} {r.kind},{r.value}：记录里的命中不在 upstream.{src} {sorted(lists)}")
        self.assertFalse(problems, "\n" + "\n".join(problems))

    def test_upstream_ads_under_products_are_handled(self):
        """category-ads-all 落在产品规则内的条目，四端都必须一致处理（自有拦截或误杀例外）。"""
        self.assertTrue(self.rec["ads_under_products"])
        self.assertFalse([x for x in self.rec["ads_under_products"] if x["handled_by"] == "未处理"])
        self.assertFalse(self.rec["ads_covering_rules"])
        recorded = {(x["kind"], x["value"]) for x in self.rec["ads_local"] if x["in_category_ads_all"]}
        for r in self.plan.ads_local:
            if r.ev == "dlc":
                self.assertIn((r.kind, r.value), recorded, f"自有拦截 {r.value} 标为 dlc 但记录里没有上游条目")


if __name__ == "__main__":
    unittest.main()
