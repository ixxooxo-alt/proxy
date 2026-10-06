"""本地覆盖（固定节点、已验证解锁节点、自定义规则）与私密产物隔离。"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import yaml

from helpers import ROOT, build, emulate
from generator import emit_loon, emit_mihomo, emit_qx
from generator.model import build_plan, load


class LocalOverrides(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        shutil.copytree(os.path.join(ROOT, "source"), os.path.join(self.dir, "source"))
        local = {
            "special_entries": {
                "paypal_fixed": {"pinned_node_name": "美国 PayPal 专用 (01)"},
                "netflix_entry": {"verified_node_regex": "^(日本 03|日本 05)$", "verified_region": "jp",
                                  "verified_at": "2026-09-30"},
            },
            "extra_services": [{"id": "my_company", "group": "DIRECT", "title": "公司内网",
                                "rules": [{"suffix": "corp.example.com", "ev": "my-note"}]}],
            "evidence": {"my-note": {"kind": "maintainer", "note": "测试"}},
        }
        with open(os.path.join(self.dir, "source", "local.yaml"), "w", encoding="utf-8") as f:
            yaml.safe_dump(local, f, allow_unicode=True)
        self.m = load(self.dir)
        self.p = build_plan(self.m)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_pinned_paypal_and_verified_netflix(self):
        conf = yaml.safe_load(emit_mihomo.build(self.m, self.p, "profile"))
        g = {x["name"]: x for x in conf["proxy-groups"]}
        rx = g["PayPal·美国固定"]["filter"]
        self.assertTrue(re.search(rx, "美国 PayPal 专用 (01)"))
        for other in ("美国 PayPal 专用 (01) 备用", "x美国 PayPal 专用 (01)", "美国 PayPal 专用 01", "美国 01"):
            self.assertFalse(re.search(rx, other), "固定节点只认完整名称")
        for bad in (",", '"', "`", " "):
            self.assertNotIn(bad, rx, "固定节点的正则也要能原样写进 Loon / QX 的一行")
        self.assertEqual(g["PayPal·美国固定"]["empty-fallback"], "REJECT", "固定节点被删除时明确失败")
        self.assertEqual(g["Netflix·解锁入口"]["type"], "fallback")
        self.assertEqual(g["Netflix·解锁入口"]["filter"], "^(日本 03|日本 05)$")
        loon = emit_loon.build(self.m, self.p)
        self.assertIn(f'F-PAYPAL = NameRegex, FilterKey = "{rx}"', loon)
        self.assertIn("PayPal·美国固定 = select,F-PAYPAL", loon)
        self.assertIn("Netflix·解锁入口 = fallback,F-NETFLIX", loon)
        qx = emit_qx.build(self.m, self.p)
        self.assertIn("available=Netflix·解锁入口, server-tag-regex=^(日本 03|日本 05)$", qx)

    def test_extra_local_rules_route(self):
        conf = yaml.safe_load(emit_mihomo.build(self.m, self.p, "profile"))
        fx = emulate.Fixtures({"dns": {}, "geoip": {"cn": []}, "geosite": {}, "ad_list": []})
        self.assertEqual(emulate.mihomo_route(conf, emulate.Conn(host="git.corp.example.com"), fx), "DIRECT")


class ReducedModes(unittest.TestCase):
    def test_three_modes(self):
        d = tempfile.mkdtemp()
        try:
            shutil.copytree(os.path.join(ROOT, "source"), os.path.join(d, "source"))
            pp = os.path.join(d, "source", "project.yaml")
            with open(pp, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            data["enabled_region_modes"] = ["manual_first", "manual", "auto"]
            with open(pp, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
            m = load(d)
            p = build_plan(m)
            conf = emulate.parse_loon(emit_loon.build(m, p))
            self.assertEqual(len(conf["groups"]), 70)       # 82 个组去掉六个地区各两种模式（2026-10-06 加 Apple Push 之前是 81 → 69）
            self.assertEqual(conf["groups"]["香港"]["members"], ["香港·手动优先", "香港·手动", "香港·自动"])
        finally:
            shutil.rmtree(d)


class CrossPlatform(unittest.TestCase):
    def test_cross_drive_output_dir(self):
        """Windows 上输出目录与项目不在同一盘符时 os.path.relpath 会抛 ValueError（外部审核发现），生成不能因此失败。"""
        from unittest import mock
        out = tempfile.mkdtemp()
        real_relpath = os.path.relpath

        def fake_relpath(path, start=os.curdir):
            if os.path.abspath(path).startswith(os.path.abspath(out)):
                raise ValueError("path is on mount 'C:', start on mount 'D:'")
            return real_relpath(path, start)
        try:
            with mock.patch("os.path.relpath", side_effect=fake_relpath):
                self.assertEqual(build.main(["--out", out]), 0)
            self.assertTrue(os.path.exists(os.path.join(out, "loon", "loon.conf")))
        finally:
            shutil.rmtree(out)

    def test_digest_uses_forward_slashes(self):
        """模拟 Windows 的路径分隔符：摘要里的相对路径必须统一成 “/”，否则同一份源在不同系统上摘要不同。"""
        from unittest import mock
        real = build._source_files()
        real_relpath = os.path.relpath

        def win_relpath(path, start=os.curdir):
            return real_relpath(path, start).replace("/", "\\")
        with mock.patch("os.sep", "\\"), mock.patch("os.path.relpath", side_effect=win_relpath):
            simulated = build._source_files()
        self.assertEqual([r for r, _ in simulated], [r for r, _ in real])
        self.assertFalse(any("\\" in r for r, _ in simulated))


class PrivateOutputs(unittest.TestCase):
    def test_subscription_only_in_private_dir(self):
        out = tempfile.mkdtemp()
        secret = "https://sub.example.org/api/v1/client/subscribe?token=SECRET123"
        old = os.environ.get("SUB_URLS")
        os.environ["SUB_URLS"] = secret
        try:
            rc = build.main(["--out", out])
            self.assertEqual(rc, 0)
            for dirpath, _, names in os.walk(out):
                for n in names:
                    p = os.path.join(dirpath, n)
                    with open(p, encoding="utf-8") as f:
                        content = f.read()
                    if os.sep + "private" + os.sep in p:
                        continue
                    self.assertNotIn("SECRET123", content, f"公开产物 {p} 泄漏了订阅")
            with open(os.path.join(out, "private", "loon.conf"), encoding="utf-8") as f:
                self.assertIn("SECRET123", f.read())
            self.assertTrue(os.path.exists(os.path.join(out, "private", "请勿分享.txt")))
        finally:
            if old is None:
                os.environ.pop("SUB_URLS", None)
            else:
                os.environ["SUB_URLS"] = old
            shutil.rmtree(out)


class GitIgnore(unittest.TestCase):
    """工程从 2026-10-05 起放进 Git 仓库（用户的 GitHub 公开仓库）。带订阅的私密产物和个人覆盖不能被提交：
    “订阅链接、Token、密钥、密码和证书私钥不得进入公开产物、普通日志、交接摘要或 Git 提交”。"""
    PRIVATE = ("dist/private/loon.conf", "dist/private/manifest.json", "dist/private/sing-box-1.14.json",
               "dist/private/请勿分享.txt", "source/local.yaml")
    PUBLIC = ("dist/loon/loon.conf", "dist/manifest.json", "source/local.example.yaml", "source/project.yaml", "build.py")

    def test_private_paths_are_listed(self):
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
        self.assertIn("dist/private/", lines)
        self.assertIn("source/local.yaml", lines)
        self.assertFalse([ln for ln in lines if ln.startswith("!")], "不用“!”开头的反向规则：它能把上面忽略掉的文件又放回来")

    @unittest.skipUnless(shutil.which("git"), "需要 git")
    def test_git_really_ignores_them(self):
        d = tempfile.mkdtemp()
        try:
            shutil.copy(os.path.join(ROOT, ".gitignore"), d)
            for rel in self.PRIVATE + self.PUBLIC:
                path = os.path.join(d, *rel.split("/"))
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("x\n")
            env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "HOME": d}
            subprocess.run(["git", "init", "-q", d], check=True, env=env, capture_output=True)
            r = subprocess.run(["git", "-C", d, "-c", "core.quotepath=off", "status", "--porcelain", "-uall"],
                               check=True, env=env, capture_output=True, text=True, encoding="utf-8")
            seen = {line[3:] for line in r.stdout.splitlines()}
            for rel in self.PRIVATE:
                self.assertNotIn(rel, seen, f"{rel} 会被 git add 收进去")
            for rel in self.PUBLIC:
                self.assertIn(rel, seen, f"{rel} 是公开内容，不该被忽略")
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
