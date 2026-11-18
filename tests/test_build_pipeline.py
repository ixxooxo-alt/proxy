"""生成流程的可靠性（2026-09-30 审核 F07 / F09 / F10 / F11）：
失败时不改动现有产物；写盘前拦住结构错误；--check 校验 manifest；local.yaml 只进私密产物。"""
import contextlib
import hashlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

import yaml

from helpers import ROOT, build, outputs, simple_spec
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

    def test_failure_in_the_middle_of_a_write_leaves_no_temp_file(self):
        """全项目复核 F09：临时文件已经建好、写到一半出错（例如磁盘写满）。以前它要等写完才登记，出错时没人删，留在目录里。"""
        real_open = open
        calls = {"n": 0}

        class HalfWritten:
            def __init__(self, f):
                self.f = f

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                self.f.close()
                return False

            def write(self, text):
                self.f.write(text[:1])
                self.f.flush()
                raise OSError("模拟：写到一半磁盘写满")

        def flaky_open(path, *a, **k):
            f = real_open(path, *a, **k)
            if ".new-" in str(path):
                calls["n"] += 1
                if calls["n"] == 2:
                    return HalfWritten(f)
            return f
        with mock.patch("builtins.open", side_effect=flaky_open):
            with self.assertRaises(OSError):
                build.write_all(self.writes())
        self.assertEqual(calls["n"], 2, "第二个文件写到一半出错")
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
            # Stash 完整版选择组上的 interval（2026-10-31）：漏写、写成 0（Stash 只认负数为“不测”）
            ("project.yaml", lambda d: d["health_check"].pop("stash_select_interval_s")),
            ("project.yaml", lambda d: d["health_check"].update(stash_select_interval_s=0)),
            # 正数也不收：完整版的选择组只能不测（和写盘前检查一致，GPT 审核 r21 送审稿的建议）
            ("project.yaml", lambda d: d["health_check"].update(stash_select_interval_s=600)),
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


class StalePrivateFiles(unittest.TestCase):
    """全项目复核 F08：同一个输出目录先带节点生成、再只带订阅生成，上一次的 sing-box 配置和两份报告还在 private/ 里，
    却不在新的清单里。不删（可能是你自己放的），在私密清单的 not_refreshed 和终端上标出来，写明来源。"""
    NODES = os.path.join(ROOT, "tests", "node_samples.yaml")
    SUB = "https://sub.example.invalid/fake"
    STALE = {"sing-box-1.14.json", "sing-box-1.12.json", "sing-box-simple-1.14.json", "sing-box-simple-1.12.json",
             "sing-box-节点转换报告.txt", "节点分组报告.txt"}

    def setUp(self):
        self.out = tempfile.mkdtemp()
        self.pdir = os.path.join(self.out, "private")

    def tearDown(self):
        shutil.rmtree(self.out)

    def run_build(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(build.main(["--out", self.out, *args]), 0)
        return buf.getvalue()

    def manifest(self):
        with open(os.path.join(self.pdir, "manifest.json"), encoding="utf-8") as f:
            return json.load(f)

    def files(self):
        out = {}
        for n in os.listdir(self.pdir):
            with open(os.path.join(self.pdir, n), "rb") as f:
                out[n] = f.read()
        return out

    def test_files_not_refreshed_are_listed_and_kept(self):
        out = self.run_build("--sub-url", self.SUB, "--singbox-nodes", self.NODES)
        self.assertNotIn("不是这一次生成的", out)
        first = self.manifest()
        self.assertEqual(first["not_refreshed"], {})
        self.assertTrue(self.STALE <= set(first["outputs"]))
        before = self.files()
        # 第二次只给订阅：sing-box 的四份和两份报告不会重新生成
        out = self.run_build("--sub-url", self.SUB)
        man = self.manifest()
        self.assertEqual(set(man["not_refreshed"]), self.STALE)
        self.assertFalse(set(man["outputs"]) & self.STALE, "新清单的 outputs 只列这一次生成的")
        after = self.files()
        for n in self.STALE:
            self.assertEqual(after[n], before[n], f"{n} 不删、不改")
            item = man["not_refreshed"][n]
            self.assertEqual(item["sha256"], hashlib.sha256(before[n]).hexdigest())
            self.assertIn(f"以前生成的（当时的统一源 {first['source_version']}、生成器 {first['generator_version']}）",
                          item["origin"])
            self.assertRegex(item["modified"], r"^\d{4}-\d\d-\d\d \d\d:\d\d$")
        self.assertIn(f"还有 {len(self.STALE)} 个文件不是这一次生成的", out)
        for n in self.STALE:
            self.assertIn(n, out)
        second = man
        # 第三次还是只给订阅：来源沿用上一次清单里记的；另放一个自己的文件、改一个旧文件
        with open(os.path.join(self.pdir, "我的笔记.txt"), "w", encoding="utf-8") as f:
            f.write("x\n")
        with open(os.path.join(self.pdir, "节点分组报告.txt"), "a", encoding="utf-8") as f:
            f.write("改过\n")
        self.run_build("--sub-url", self.SUB)
        man = self.manifest()
        self.assertEqual(set(man["not_refreshed"]), self.STALE | {"我的笔记.txt"})
        self.assertEqual(man["not_refreshed"]["sing-box-1.14.json"], second["not_refreshed"]["sing-box-1.14.json"])
        self.assertIn("自己放的", man["not_refreshed"]["我的笔记.txt"]["origin"])
        self.assertEqual(man["not_refreshed"]["节点分组报告.txt"]["origin"], "上一次的私密清单里有它，之后又被改过",
                         "改过的文件不能说成是生成的")
        self.assertTrue(os.path.exists(os.path.join(self.pdir, "我的笔记.txt")))
        # 再带上节点：都刷新了，只剩自己放的那个
        self.run_build("--sub-url", self.SUB, "--singbox-nodes", self.NODES)
        self.assertEqual(set(self.manifest()["not_refreshed"]), {"我的笔记.txt"})

    def test_no_private_inputs_this_time(self):
        """这一次什么私密输入都没给：不写私密清单（旧的照旧留着），终端照样提示整个目录都不是这一次的。"""
        self.run_build("--singbox-nodes", self.NODES)
        before = self.files()
        out = self.run_build()
        self.assertEqual(self.files(), before)
        self.assertIn(f"还有 {len(before)} 个文件不是这一次生成的", out)
        self.assertNotIn("not_refreshed 一项", out, "这一次没有写私密清单，不能叫人去看它")


class DnsLayersForFixedDirect(unittest.TestCase):
    """第三份全项目复核 F01、F03、F04：要真实地址的名单在 mihomo 上全交给国内 DNS；local.yaml 里写在走代理的产品下面的直连规则，
    mihomo、sing-box 的 DNS 都交给国内；sing-box 开 reverse_mapping；和要真实地址的名单冲突的规则在读规则源时就报错。"""

    def test_every_real_ip_name_goes_to_domestic_dns_on_mihomo(self):
        import yaml as _yaml
        from helpers import model_and_plan
        m = model_and_plan()[0]
        lan = set(m.project["lan"]["domain_suffix"])
        want = [("+." + x["suffix"]) if "suffix" in x else x["domain"] for x in m.project["dns"]["real_ip"]
                if not ("suffix" in x and x["suffix"] in lan)]
        self.assertTrue({"+.msftconnecttest.com", "+.msftncsi.com", "captive.apple.com"} <= set(want))
        for name in ("mihomo/mihomo-core.yaml", "mihomo/mihomo-profile.yaml", "mihomo/mihomo-simple-core.yaml",
                     "mihomo/mihomo-simple-profile.yaml"):
            dns = _yaml.safe_load(outputs()[name])["dns"]
            domestic = dns["nameserver-policy"]["geosite:cn"]
            for w in want:
                self.assertEqual(dns["nameserver-policy"].get(w), domestic, f"{name}：{w} 要交给国内 DNS（以前落到境外 DNS）")

    def test_singbox_maps_real_addresses_back_to_names(self):
        for v in ("sing-box/sing-box-1.14.json", "sing-box/sing-box-1.12.json", "sing-box/sing-box-simple-1.14.json",
                  "sing-box/sing-box-simple-1.12.json"):
            self.assertIs(json.loads(outputs()[v])["dns"].get("reverse_mapping"), True, v)

    def test_local_direct_rule_under_a_proxied_product_uses_domestic_dns(self):
        t = TempRoot()
        try:
            t.write("local.yaml", "extra_services:\n  - id: my_mirror\n    group: DIRECT\n    title: 自己的镜像\n"
                                  "    rules:\n      - {suffix: cn-mirror.github.com, ev: my-note}\n"
                                  "      - {suffix: corp.example.com, ev: my-note}\n"
                                  "evidence:\n  my-note: {kind: maintainer, note: 测试用}\n")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(t.build("--singbox-nodes", os.path.join(ROOT, "tests", "node_samples.yaml")), 0)
            with open(os.path.join(t.out, "private", "mihomo-profile.yaml"), encoding="utf-8") as f:
                pol = yaml.safe_load(f)["dns"]["nameserver-policy"]
            self.assertEqual(pol["+.cn-mirror.github.com"], pol["geosite:cn"], "github.com 走代理，下面的直连规则要交给国内 DNS")
            self.assertNotIn("+.corp.example.com", pol, "没被走代理的规则盖住的，照旧不写（和国内直连的规则一样）")
            with open(os.path.join(t.out, "private", "sing-box-1.14.json"), encoding="utf-8") as f:
                rules = json.load(f)["dns"]["rules"]
            hit = [i for i, r in enumerate(rules) if "cn-mirror.github.com" in (r.get("domain_suffix") or [])]
            proxied = [i for i, r in enumerate(rules) if r.get("rule_set") == "product-proxied"]
            self.assertTrue(hit and rules[hit[0]]["server"] == "dns-cn" and hit[0] < proxied[0], rules[:8])
        finally:
            t.close()

    def test_rules_clashing_with_the_real_ip_list_are_rejected(self):
        t = TempRoot()
        try:
            t.write("local.yaml", "extra_services:\n  - id: my_time\n    group: 国外默认\n    title: 测试\n"
                                  "    rules:\n      - {domain: time.windows.com, ev: my-note}\n"
                                  "evidence:\n  my-note: {kind: maintainer, note: 测试用}\n")
            err = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                self.assertEqual(t.build(), 2)
            self.assertIn("在要真实地址的名单", err.getvalue())
        finally:
            t.close()


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
        self.assertEqual(verify.check_outputs(outputs(), spec=simple_spec()), [], "当前产物本身不应有任何结构问题")

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

    def test_detects_node_outbounds_that_lose_tls_or_cannot_start(self):
        """全项目复核（2026-11-18）F01–F03 的最后一道：转换器再出错，写盘前也要拦住——只能走 TLS 的协议没开 TLS（F01）、
        tls.insecure 写了却不是 true（F02：只在订阅要求跳过证书校验时写）、packet_encoding 不是 sing-box 认的值（F03）。"""
        def probs(*obs):
            conf = {"outbounds": [{"type": "direct", "tag": "D"}, *obs], "route": {"rules": [], "final": "D"}}
            return "\n".join(verify.check_singbox(json.dumps(conf)))

        base = {"tag": "n", "server": "x.example.net", "server_port": 443}
        for t, extra in (("trojan", {"password": "p"}), ("hysteria2", {"password": "p"}),
                         ("tuic", {"uuid": "u", "password": "p"}), ("anytls", {"password": "p"})):
            self.assertIn("节点 n（" + t + "）没有开 TLS", probs({"type": t, **base, **extra}))
            self.assertIn("没有开 TLS", probs({"type": t, **base, **extra, "tls": {"enabled": False}}))
            self.assertEqual(probs({"type": t, **base, **extra, "tls": {"enabled": True}}), "")
        for t in ("vmess", "vless", "http"):
            self.assertEqual(probs({"type": t, **base, "uuid": "u"} if t != "http" else {"type": t, **base}), "", f"{t} 可以不加密")
        for t in ("vmess", "vless"):
            for v in ("packet", "foo"):
                self.assertIn(f"节点 n 的 packet_encoding 是 '{v}'", probs({"type": t, **base, "uuid": "u", "packet_encoding": v}))
            for v in ("packetaddr", "xudp", ""):
                self.assertEqual(probs({"type": t, **base, "uuid": "u", "packet_encoding": v}), "", (t, v))
        for v in (False, "true", 1):
            self.assertIn("节点 n 的 tls.insecure 是", probs({"type": "http", **base, "tls": {"enabled": True, "insecure": v}}))
        self.assertEqual(probs({"type": "http", **base, "tls": {"enabled": True, "insecure": True}}), "")

    def test_detects_values_singbox_does_not_accept(self):
        """F03 的同一类和第二份复核 C2：转换器再漏了，写盘前也拦住 sing-box 不认的取值、Reality 不带 uTLS、
        不该有的 multiplex、单个数字的端口段、写错的 Reality 公钥 / short_id。"""
        def probs(*obs):
            conf = {"outbounds": [{"type": "direct", "tag": "D"}, *obs], "route": {"rules": [], "final": "D"}}
            return "\n".join(verify.check_singbox(json.dumps(conf)))

        base = {"tag": "n", "server": "x.example.net", "server_port": 443}
        tls = {"enabled": True}
        pk = "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA"
        for ob, needle in (({"type": "shadowsocks", "method": "aes-128-ccm", "password": "p"}, "节点 n 的 method 是"),
                           ({"type": "vmess", "uuid": "u", "security": "aes-128-ctr"}, "节点 n 的 security 是"),
                           ({"type": "vless", "uuid": "u", "flow": "xtls-rprx-direct"}, "节点 n 的 flow 是"),
                           ({"type": "tuic", "uuid": "u", "password": "p", "congestion_control": "newreno", "tls": tls},
                            "节点 n 的 congestion_control 是"),
                           ({"type": "trojan", "password": "p", "tls": {**tls, "utls": {"enabled": True, "fingerprint": "none"}}},
                            "节点 n 的 tls.utls.fingerprint 是"),
                           ({"type": "vmess", "uuid": "u", "multiplex": {"enabled": True, "protocol": "mplex"}},
                            "节点 n 的 multiplex.protocol 是"),
                           ({"type": "vless", "uuid": "u", "tls": {**tls, "reality": {"enabled": True, "public_key": pk, "short_id": ""}}},
                            "用了 Reality 却没有 uTLS"),
                           ({"type": "socks", "multiplex": {"enabled": True, "protocol": "h2mux"}}, "写了 multiplex"),
                           ({"type": "hysteria2", "password": "p", "tls": tls, "server_ports": ["443", "20000:30000"]},
                            "server_ports 每一项都要写成 a:b"),
                           ({"type": "vless", "uuid": "u", "tls": {**tls, "utls": {"enabled": True, "fingerprint": "chrome"},
                                                                    "reality": {"enabled": True, "public_key": pk, "short_id": "None"}}},
                            "Reality 公钥或 short_id 写法不对")):
            self.assertIn(needle, probs({**base, **ob}), ob)
        for ob in ({"type": "shadowsocks", "method": "none", "password": "p"},
                   {"type": "vmess", "uuid": "u", "security": "zero", "multiplex": {"enabled": False, "protocol": "mplex"}},
                   {"type": "vless", "uuid": "u", "flow": "", "tls": {**tls, "utls": {"enabled": True, "fingerprint": "chrome"},
                                                                       "reality": {"enabled": True, "public_key": pk, "short_id": "ab"}}},
                   {"type": "hysteria2", "password": "p", "tls": tls, "server_ports": ["443:443", "20000:30000"]},
                   {"type": "tuic", "uuid": "u", "password": "p", "tls": tls}):
            self.assertEqual(probs({**base, **ob}), "", ob)

    def test_detects_loon_values_and_deprecated_parameters(self):
        """第二份复核 C1、C7：Loon 的 ip-mode 以前写成官方取值里没有的 ipv4-only，dns-reject-mode 写成 LoopbackIP，
        还写着已弃用的 switch-node-after-failure-times（官方“通用配置”页，2026-11-18 读取）。"""
        def probs(general):
            return "\n".join(verify.check_loon("[General]\n" + "\n".join(general) + "\n[Rule]\nFINAL,DIRECT\n"))
        self.assertIn("ip-mode = ipv4-only 不是 Loon 认的取值", probs(["ip-mode = ipv4-only"]))
        self.assertIn("dns-reject-mode = LoopbackIP 不是 Loon 认的取值", probs(["dns-reject-mode = LoopbackIP"]))
        for key in ("switch-node-after-failure-times = 3", "ipv6 = false", "force-http-engine-hosts = a.example.com",
                    "skip-first-packet = true"):
            self.assertIn("已弃用的参数", probs([key]), key)
        self.assertEqual(probs(["ip-mode = v4-only", "dns-reject-mode = LOOPBACKIP", "udp-fallback-mode = REJECT"]), "")
        for name in ("loon/loon.conf", "loon/loon-strict.conf", "loon/loon-simple.conf", "loon/loon-simple-strict.conf"):
            general = [x for x in verify._sections(outputs()[name])["General"] if "=" in x]
            self.assertIn("ip-mode = v4-only", general, name)
            self.assertIn("dns-reject-mode = LOOPBACKIP", general, name)
            self.assertFalse([x for x in general if x.split("=")[0].strip() in verify.LOON_DEPRECATED], name)

    def test_detects_mihomo_dns_settings_the_core_would_refuse(self):
        """审核 r10 的 R10-F01 之后用到 proxy-server-nameserver-policy。mihomo 对它和 respect-rules 都有同一个要求：
        proxy-server-nameserver 不能为空，否则拒绝加载（v1.19.31 config/config.go 的 parseDNS；用官方内核试过，三种写法都被拒绝）。
        写盘前就拦住。当前生成的配置两项都开着、服务器不为空，所以没有问题。"""
        def problems(dns):
            return "\n".join(verify.check_mihomo(yaml.safe_dump({"dns": dns, "proxy-groups": [], "rules": []}, allow_unicode=True)))

        servers = ["https://223.5.5.5/dns-query"]
        policy = {"+.lan": ["system"], "*": ["system"]}
        self.assertEqual(problems({"respect-rules": True, "proxy-server-nameserver": servers,
                                   "proxy-server-nameserver-policy": policy}), "")
        self.assertIn("respect-rules 打开时 dns.proxy-server-nameserver 不能为空",
                      problems({"respect-rules": True, "proxy-server-nameserver": []}))
        self.assertIn("写了 dns.proxy-server-nameserver-policy 时 dns.proxy-server-nameserver 不能为空",
                      problems({"proxy-server-nameserver-policy": policy}))
        both = problems({"respect-rules": True, "proxy-server-nameserver-policy": policy})
        self.assertEqual(both.count("不能为空"), 2)
        self.assertEqual(problems({"respect-rules": False}), "", "两项都没开时，不写 proxy-server-nameserver 不算问题")
        self.assertIn("dns.proxy-server-nameserver-policy 的 * 没有写 DNS 服务器",
                      problems({"proxy-server-nameserver": servers, "proxy-server-nameserver-policy": {"*": []}}))
        for client in ("mihomo/mihomo-core.yaml", "mihomo/mihomo-profile.yaml"):
            dns = yaml.safe_load(outputs()[client])["dns"]
            self.assertTrue(dns["respect-rules"] and dns["proxy-server-nameserver"] and dns["proxy-server-nameserver-policy"], client)
            self.assertEqual(verify.check_mihomo(outputs()[client]), [], client)


if __name__ == "__main__":
    unittest.main()
