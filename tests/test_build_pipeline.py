"""生成流程的可靠性（2026-09-30 审核 F07 / F09 / F10 / F11）：
失败时不改动现有产物；写盘前拦住结构错误；--check 校验 manifest；local.yaml 只进私密产物。"""
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from helpers import ROOT, build, outputs
from generator import verify


def _tree(d):
    out = {}
    for dirpath, _, names in os.walk(d):
        for n in names:
            p = os.path.join(dirpath, n)
            with open(p, encoding="utf-8") as f:
                out[os.path.relpath(p, d)] = f.read()
    return out


class TempRoot:
    """复制一份 source/ 到临时目录，便于改坏或加 local.yaml 后调用 build.main(root=...)。"""

    def __init__(self):
        self.dir = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, "source"), os.path.join(self.dir, "source"))
        self.out = os.path.join(self.dir, "out")

    def edit_yaml(self, rel, fn):
        p = os.path.join(self.dir, "source", rel)
        with open(p, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        fn(data)
        with open(p, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)

    def write(self, rel, text):
        with open(os.path.join(self.dir, "source", rel), "w", encoding="utf-8") as f:
            f.write(text)

    def build(self, *args):
        return build.main(["--out", self.out, *args], root=self.dir)

    def close(self):
        shutil.rmtree(self.dir)


class Transaction(unittest.TestCase):
    """F07：全部成功才替换。"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        for n in ("a.txt", "b.txt"):
            with open(os.path.join(self.d, n), "w", encoding="utf-8") as f:
                f.write("OLD")

    def tearDown(self):
        shutil.rmtree(self.d)

    def writes(self):
        return {os.path.join(self.d, n): "NEW" for n in ("a.txt", "b.txt", "sub/c.txt")}

    def assert_untouched(self):
        self.assertEqual(_tree(self.d), {"a.txt": "OLD", "b.txt": "OLD"})

    def test_failure_while_replacing_rolls_back(self):
        real = os.replace
        calls = {"n": 0}

        def flaky(src, dst):
            if ".new-" in src:
                calls["n"] += 1
                if calls["n"] == 2:
                    raise OSError("模拟：第二个文件替换失败")
            return real(src, dst)
        with mock.patch("os.replace", side_effect=flaky):
            with self.assertRaises(OSError):
                build.write_all(self.writes())
        self.assert_untouched()

    def test_failure_while_staging_leaves_everything(self):
        real_open = open
        calls = {"n": 0}

        def flaky_open(path, *a, **k):
            if ".new-" in str(path):
                calls["n"] += 1
                if calls["n"] == 3:
                    raise OSError("模拟：磁盘写满")
            return real_open(path, *a, **k)
        with mock.patch("builtins.open", side_effect=flaky_open):
            with self.assertRaises(OSError):
                build.write_all(self.writes())
        self.assert_untouched()

    def test_success_replaces_all(self):
        build.write_all(self.writes())
        self.assertEqual(_tree(self.d), {"a.txt": "NEW", "b.txt": "NEW", os.path.join("sub", "c.txt"): "NEW"})


class PipelineFailures(unittest.TestCase):
    def setUp(self):
        self.t = TempRoot()
        self.assertEqual(self.t.build(), 0)
        self.before = _tree(self.t.out)

    def tearDown(self):
        self.t.close()

    def assert_unchanged(self):
        self.assertEqual(_tree(self.t.out), self.before)

    def test_private_step_failure_keeps_public_untouched(self):
        """节点文件读不到：以前公开产物已经被换成新版，私密产物还是旧的（F07）。"""
        self.t.edit_yaml("project.yaml", lambda d: d["project"].update(source_version="9999.01.01-1"))
        rc = self.t.build("--singbox-nodes", os.path.join(self.t.dir, "不存在.yaml"))
        self.assertEqual(rc, 3)
        self.assert_unchanged()

    def test_structural_errors_rejected_before_writing(self):
        """F09 复现的三种输入，以及拼错的字段、重复的键，都要在写盘前失败。"""
        cases = [
            ("adblock.yaml", lambda d: d["exceptions"].append(
                {"suffix": "example-unknown.org", "target": "不存在的组", "ev": "maintainer", "why": "x"})),
            ("groups.yaml", lambda d: [g["options"].append("国外默认") for g in d["groups"] if g["name"] == "国外默认"]),
            ("adblock.yaml", lambda d: d["local_ads"].append({"suffix": "https://ads.example.com/x", "ev": "maintainer"})),
            ("adblock.yaml", lambda d: d["local_ads"].append({"sufix": "ads.example.com", "ev": "maintainer"})),
        ]
        for rel, fn in cases:
            p = os.path.join(self.t.dir, "source", rel)
            with open(p, encoding="utf-8") as f:
                orig = f.read()
            self.t.edit_yaml(rel, fn)
            self.assertEqual(self.t.build(), 2, rel)
            self.assert_unchanged()
            self.t.write(rel, orig)
        # 重复键：PyYAML 默认让后一个悄悄覆盖前一个
        p = os.path.join(self.t.dir, "source", "groups.yaml")
        with open(p, encoding="utf-8") as f:
            orig = f.read()
        self.t.write("groups.yaml", orig.replace("groups:\n", "groups:\n", 1) + "\ngroups: []\n")
        self.assertEqual(self.t.build(), 2)
        self.assert_unchanged()


class ManifestCheck(unittest.TestCase):
    """F10：--check 也核对 manifest；摘要包含 build.py、不含 local.yaml。"""

    def test_check_detects_manifest_tampering(self):
        t = TempRoot()
        try:
            self.assertEqual(t.build(), 0)
            self.assertEqual(t.build("--check"), 0)
            mp = os.path.join(t.out, "manifest.json")
            with open(mp, encoding="utf-8") as f:
                data = json.load(f)
            data["source_version"] = "0000"
            data["outputs"] = {}
            with open(mp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            self.assertEqual(t.build("--check"), 1)
            os.remove(os.path.join(t.out, "loon", "loon.conf"))
            self.assertEqual(t.build("--check"), 1)
        finally:
            t.close()

    def test_digest_covers_build_py_but_not_local_yaml(self):
        rels = [r for r, _ in build._source_files()]
        self.assertIn("build.py", rels)
        self.assertNotIn("source/local.yaml", rels)


class LocalOnlyInPrivate(unittest.TestCase):
    """F11：local.yaml 里的公司域名、固定节点名只出现在 dist/private/。"""

    def test_local_overlay_goes_to_private_only(self):
        t = TempRoot()
        try:
            t.write("local.yaml", yaml.safe_dump({
                "special_entries": {"paypal_fixed": {"pinned_node_name": "美国 我的固定节点 07"}},
                "extra_services": [{"id": "my_company", "group": "DIRECT", "title": "公司内网",
                                    "rules": [{"suffix": "corp-secret.example.com", "ev": "my-note"}]}],
                "evidence": {"my-note": {"kind": "maintainer", "note": "测试"}},
            }, allow_unicode=True))
            self.assertEqual(t.build(), 0)
            tree = _tree(t.out)
            public = {k: v for k, v in tree.items() if not k.startswith("private" + os.sep)}
            private = {k: v for k, v in tree.items() if k.startswith("private" + os.sep)}
            for k, v in public.items():
                self.assertNotIn("corp-secret.example.com", v, k)
                self.assertNotIn("我的固定节点", v, k)
            joined = "\n".join(private.values())
            self.assertIn("corp-secret.example.com", joined)
            self.assertIn("我的固定节点", joined)
            pm = json.loads(private[os.path.join("private", "manifest.json")])
            self.assertTrue(pm["local_yaml_sha256"])
            self.assertEqual(t.build("--check"), 0, "公开产物不受 local.yaml 影响，--check 仍然一致")
        finally:
            t.close()


class Verifier(unittest.TestCase):
    """verify 模块本身能发现引用错误、自引用和重名。"""

    def test_detects_broken_references(self):
        bad_mihomo = yaml.safe_dump({
            "proxy-groups": [{"name": "A", "type": "select", "proxies": ["A", "不存在"]},
                             {"name": "B", "type": "select", "proxies": ["C"]},
                             {"name": "C", "type": "select", "proxies": ["B"]}],
            "rules": ["DOMAIN,x.example.com,不存在的组", "MATCH,A"]}, allow_unicode=True)
        probs = verify.check_mihomo(bad_mihomo)
        text = "\n".join(probs)
        for needle in ("不存在", "引用了自己", "循环", "不存在的组"):
            self.assertIn(needle, text)
        bad_sb = json.dumps({"outbounds": [{"type": "direct", "tag": "X"}, {"type": "direct", "tag": "X"},
                                           {"type": "selector", "tag": "S", "outbounds": ["Y"]}],
                             "route": {"rules": [{"outbound": "Z"}], "final": "S"}})
        text = "\n".join(verify.check_singbox(bad_sb))
        for needle in ("重名", "Y", "Z"):
            self.assertIn(needle, text)

    def test_detects_broken_rule_set_and_dns_references(self):
        """规则集、DNS 服务器的引用也在写盘前检查（DNS 上的产品规则引用内联规则集 product-proxied）。"""
        bad = json.dumps({
            "outbounds": [{"type": "direct", "tag": "D"}],
            "dns": {"servers": [{"type": "local", "tag": "dns-a"}],
                    "rules": [{"rule_set": "没有这个集合", "server": "dns-a"}, {"domain": ["x.example"], "server": "没有这个服务器"}],
                    "final": "也没有这个"},
            "route": {"rules": [{"rule_set": ["geosite-x", "另一个没有的"], "outbound": "D"}],
                      "rule_set": [{"type": "inline", "tag": "geosite-x", "rules": []},
                                   {"type": "inline", "tag": "geosite-x", "rules": []}], "final": "D"}})
        text = "\n".join(verify.check_singbox(bad))
        for needle in ("规则集标签重名", "DNS 规则引用了不存在的规则集 没有这个集合", "路由规则引用了不存在的规则集 另一个没有的",
                       "DNS 规则指向不存在的服务器 没有这个服务器", "dns.final 指向不存在的服务器 也没有这个"):
            self.assertIn(needle, text)
        self.assertNotIn("不存在的规则集 geosite-x", text)
        self.assertEqual(verify.check_outputs(outputs()), [], "当前产物本身不应有任何结构问题")

    def test_detects_broken_dial_resolver_references(self):
        """拨号解析用到的 DNS 服务器（审核 r9 的 F02 之后新用到的字段）：路由规则的 resolve 动作、出站的 domain_resolver、
        route.default_domain_resolver 指向不存在的服务器时，写盘前就拒绝。"""
        bad = json.dumps({
            "outbounds": [{"type": "direct", "tag": "D"},
                          {"type": "socks", "tag": "节点甲", "server": "gateway.lan", "server_port": 1080, "domain_resolver": "没有的甲"},
                          {"type": "socks", "tag": "节点乙", "server": "b.lan", "server_port": 1080, "domain_resolver": {"server": "没有的乙"}},
                          {"type": "socks", "tag": "节点丙", "server": "c.lan", "server_port": 1080, "domain_resolver": "dns-a"}],
            "dns": {"servers": [{"type": "local", "tag": "dns-a"}], "rules": [], "final": "dns-a"},
            "route": {"rules": [{"domain_suffix": ["lan"], "action": "resolve", "server": "没有的丁"},
                                {"action": "resolve", "server": "dns-a"}, {"action": "resolve"}],
                      "rule_set": [], "final": "D", "default_domain_resolver": "没有的戊"}})
        text = "\n".join(verify.check_singbox(bad))
        for needle in ("出站 节点甲 的 domain_resolver 指向不存在的 DNS 服务器 没有的甲",
                       "出站 节点乙 的 domain_resolver 指向不存在的 DNS 服务器 没有的乙",
                       "路由规则的 resolve 动作指向不存在的 DNS 服务器 没有的丁",
                       "route.default_domain_resolver 指向不存在的 DNS 服务器 没有的戊"):
            self.assertIn(needle, text)
        self.assertNotIn("节点丙", text)
        self.assertEqual(text.count("resolve 动作"), 1, "指向存在的服务器、或者没写服务器的 resolve 不算问题")


if __name__ == "__main__":
    unittest.main()
