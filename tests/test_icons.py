"""策略组图标（2026-10-05 起启用，用户 2026-10-04 的要求）。图标只影响显示，不影响分流。

图片在用户自己的图标仓库里，不在本工程里；本工程只把图片地址写进 Loon（img-url）、Quantumult X（img-url）、
mihomo（icon），sing-box 没有图标字段。这里检查：
  - 每个策略组写的是它自己的那张图，地址和图标仓库公布的写法一致；
  - 已经写进配置、图还没有传到图标仓库的组可以登记在 icons.yaml 的 pending 里，地址写法相同
    （2026-10-06 的 Apple Push 这样登记过半天，当天图传到图标仓库以后挪进了 available；现在 pending 是空的）；
  - 地址可以原样放进用逗号分隔参数的一行里；
  - 关掉图标后，产物里除了图标什么都不变；
  - 组找不到图时，公开产物直接生成失败。
图片文件是否真的在图标仓库里，由 tools/check_icons.py 拿图标仓库的检出目录核对（需要那个目录，不在自动测试里）。"""
import copy
import json
import re
import unittest
from urllib.parse import unquote

from helpers import build, model_and_plan, parsed, text

from generator import model as model_mod

BASE = "https://raw.githubusercontent.com/ixxooxo-alt/icon/main/256px/"
# 这几个地址照抄自图标仓库自己公布的清单（icon-urls.json 的 url_256px；2026-10-04 的提交 0f50f8f 时抄的，到 10 月 5 日的 2d43eae 该文件没有变）：
# 名字里有空格、加号、间隔号、斜杠、汉字的各取一个，用来核对本工程的编码方式和它一致
PUBLISHED = {
    "OpenAI": BASE + "OpenAI.png",
    "X": BASE + "X.png",
    "Google AI": BASE + "Google%20AI.png",
    "Disney+": BASE + "Disney%2B.png",
    "其他 AI": BASE + "%E5%85%B6%E4%BB%96%20AI.png",
    "Apple Music/TV": BASE + "Apple%20Music%EF%BC%8FTV.png",
    "PayPal·美国固定": BASE + "PayPal%C2%B7%E7%BE%8E%E5%9B%BD%E5%9B%BA%E5%AE%9A.png",
    "香港·手动优先": BASE + "%E9%A6%99%E6%B8%AF%C2%B7%E6%89%8B%E5%8A%A8%E4%BC%98%E5%85%88.png",
}
WITH_ICONS = ("loon", "quantumultx", "mihomo-profile", "mihomo-core", "loon-strict", "quantumultx-strict")
# Loon / Quantumult X / mihomo 的策略组总数：业务组 43 个（2026-10-06 加了 Apple Push，之前是 42 个）+ 专用入口 1 个
# （PayPal·美国固定；Netflix·解锁入口 2026-10-07 取消，待决事项第 3 项）+ 地区入口 7 个 + 六个地区各 5 个模式组 30 个。
# 增减策略组时要同时改这里
GROUPS = 81


def icons_in(client: str, source: str = None) -> dict:
    """{策略组名: 图标地址}，直接从产物文本里读（没有图标的组不出现）。"""
    out = {}
    if client.startswith("mihomo"):
        conf = parsed(client) if source is None else __import__("yaml").safe_load(source)
        for g in conf["proxy-groups"]:
            if "icon" in g:
                out[g["name"]] = g["icon"]
        return out
    t = text(client) if source is None else source
    section, want = None, "Proxy Group" if client.startswith("loon") else "policy"
    for line in t.splitlines():
        if line.startswith("["):
            section = line.strip("[]")
            continue
        if section != want or not line.strip() or line.startswith(("#", ";")):
            continue
        if client.startswith("loon"):
            name = line.split(" = ", 1)[0]
            m = re.search(r",img-url = (\S+)$", line)
        else:
            name = line.split("=", 1)[1].split(",", 1)[0].strip()
            m = re.search(r", img-url=(\S+)$", line)
        if m:
            out[name] = m.group(1)
    return out


def group_names(client: str) -> list:
    if client.startswith("mihomo"):
        return [g["name"] for g in parsed(client)["proxy-groups"]]
    c = parsed(client)
    return list(c["groups"] if client.startswith("loon") else c["policies"])


class Icons(unittest.TestCase):
    def test_every_group_carries_its_own_icon(self):
        m, _ = model_and_plan()
        renamed = m.icons["renamed"]
        for client in WITH_ICONS:
            names = group_names(client)
            icons = icons_in(client)
            self.assertEqual(len(names), GROUPS, client)
            self.assertEqual(sorted(icons), sorted(names), f"{client}：每个策略组都要有图标，也不能多出别的")
            for name, url in icons.items():
                self.assertTrue(url.startswith(BASE) and url.endswith(".png"), f"{client} {name}: {url}")
                file_name = unquote(url[len(BASE):-len(".png")])
                self.assertEqual(file_name, renamed.get(name, name), f"{client} {name} 写的不是它自己的图：{url}")
            self.assertEqual(len(set(icons.values())), len(icons), f"{client}：两个组用了同一个地址")
            # 这一个不在图标仓库的地址清单（icon-urls.json）里：图是 2026-10-06 单独加的（提交 f250126），
            # 图标仓库在 README 里给的链接就是这个写法
            self.assertEqual(icons["Apple Push"], BASE + "Apple%20Push.png", client)

    def test_urls_match_what_the_icon_repository_publishes(self):
        for client in WITH_ICONS:
            icons = icons_in(client)
            for name, url in PUBLISHED.items():
                self.assertEqual(icons[name], url, f"{client} {name}")

    def test_urls_are_safe_inside_a_comma_separated_line(self):
        """Loon / Quantumult X 的一行用逗号分隔参数：地址里不能有逗号、空格、引号这些。"""
        for client in WITH_ICONS:
            for name, url in icons_in(client).items():
                self.assertRegex(url, r"^https://[A-Za-z0-9.-]+/[A-Za-z0-9._~%/-]+$", f"{client} {name}")
        # 每个组一行，图标参数在行尾，而且只出现一次
        for client, mark in (("loon", "img-url = "), ("quantumultx", "img-url="),
                             ("loon-strict", "img-url = "), ("quantumultx-strict", "img-url=")):
            lines = [ln for ln in text(client).splitlines() if mark in ln and not ln.startswith("#")]
            self.assertEqual(len(lines), GROUPS, client)
            for ln in lines:
                self.assertEqual(ln.count("img-url"), 1, ln[:60])
                self.assertRegex(ln, r"img-url ?= ?https://\S+\.png$", ln[:60])

    def test_singbox_has_no_icon_fields(self):
        for client in ("singbox-1.14", "singbox-1.12"):
            conf = json.loads(text(client))
            keys = {k for o in conf["outbounds"] for k in o}
            self.assertFalse({k for k in keys if "icon" in k or "img" in k}, client)
            self.assertNotIn("ixxooxo-alt/icon", text(client), client)

    def test_registry_covers_exactly_the_groups(self):
        m, _ = model_and_plan()
        ic = m.icons
        self.assertTrue(ic["enabled"])
        self.assertRegex(ic["checked_commit"], r"^[0-9a-f]{40}$")
        used = {m.icon_file(n) for n in group_names("mihomo-core")}
        # 已经写进配置、图还没有传到图标仓库的组登记在 pending 里。现在没有：2026-10-06 加的 Apple Push 当天下午
        # 由用户传到了图标仓库（提交 f250126），已经挪进 available。以后再有这样的组，这里和 icons.yaml 一起改
        self.assertEqual(ic["pending"], [])
        self.assertIn("Apple Push", ic["available"])
        self.assertFalse(set(ic["pending"]) & set(ic["available"]))
        self.assertLessEqual(set(ic["pending"]), used)
        self.assertLessEqual(used, set(ic["available"]) | set(ic["pending"]))
        self.assertEqual(sorted(set(ic["available"]) - used), ["DIRECT", "Netflix·解锁入口", "REJECT", "无可用节点"],
                         "icons.yaml 的说明里写着：图标仓库里多出来、没有用到的只有这四张")
        self.assertEqual(len(ic["available"]), len(set(ic["available"])))

    def test_a_group_whose_icon_is_not_uploaded_yet_can_be_registered_as_pending(self):
        """图还没传到图标仓库、但地址已经定了的组：登记在 pending 里，配置照样写它的地址，产物和图在 available 里时逐字相同。
        两边都没登记才算“没有图标”（那种情况由下面 test_missing_icon… 检查）。"""
        m, plan = model_and_plan()
        moved = copy.copy(m)
        moved.icons = {**m.icons, "available": [x for x in m.icons["available"] if x != "Apple Push"], "pending": ["Apple Push"]}
        self.assertEqual(model_mod._check_icons(moved.icons), [])
        self.assertEqual(moved.icon_url("Apple Push"), BASE + "Apple%20Push.png")
        self.assertEqual(build.render_public(moved, plan), build.render_public(m, plan))
        gone = copy.copy(m)
        gone.icons = {**m.icons, "available": [x for x in m.icons["available"] if x != "Apple Push"], "pending": []}
        with self.assertRaises(model_mod.SourceError) as cm:
            build.render_public(gone, plan)
        self.assertIn("Apple Push", str(cm.exception))

    def test_switching_icons_off_changes_nothing_else(self):
        m, plan = model_and_plan()
        off = copy.copy(m)
        off.icons = {**m.icons, "enabled": False}
        files = build.render_public(off, plan)
        strip = {"loon/loon.conf": r",img-url = \S+$", "quantumultx/quantumultx.conf": r", img-url=\S+$",
                 "loon/loon-strict.conf": r",img-url = \S+$", "quantumultx/quantumultx-strict.conf": r", img-url=\S+$",
                 "mihomo/mihomo-core.yaml": r"^    icon: \S+\n", "mihomo/mihomo-profile.yaml": r"^    icon: \S+\n"}
        on = build.render_public(m, plan)
        for rel, pattern in strip.items():
            self.assertNotIn("ixxooxo-alt/icon", files[rel], rel)
            without = re.sub(pattern, "", on[rel], flags=re.M)
            # Loon / Quantumult X 的那一行说明图标的注释在关掉以后仍然保留，所以两边逐字相同
            self.assertEqual(without, files[rel], f"{rel}：关掉图标后，除了图标参数以外还有别的地方变了")
        for rel in ("sing-box/sing-box-1.14.json", "sing-box/sing-box-1.12.json"):
            self.assertEqual(on[rel], files[rel], rel)

    def test_missing_icon_fails_the_public_build_but_not_a_private_one(self):
        m, plan = model_and_plan()
        broken = copy.copy(m)
        broken.icons = {**m.icons, "available": [x for x in m.icons["available"] if x != "OpenAI"]}
        with self.assertRaises(model_mod.SourceError) as cm:
            build.render_public(broken, plan)
        self.assertIn("OpenAI", str(cm.exception))
        self.assertIn("没有图标", str(cm.exception))
        broken.icons_strict = False          # 带本地覆盖的私密模型：不给这个组写图标，其余照常
        self.assertIsNone(broken.icon_url("OpenAI"))
        self.assertEqual(broken.icon_url("Claude"), BASE + "Claude.png")
        files = build.render_public(broken, plan)
        self.assertNotIn("OpenAI.png", files["loon/loon.conf"])
        self.assertIn("Claude.png", files["loon/loon.conf"])

    def test_bad_registry_is_rejected(self):
        good = model_and_plan()[0].icons
        check = model_mod._check_icons
        self.assertEqual(check(good), [])
        self.assertEqual(check({"enabled": False, "base_url": "乱写也没关系"}), [], "没启用时不检查其余字段")
        for change, needle in (({"base_url": "http://example.com/a/"}, "base_url"),
                               ({"base_url": "https://example.com/a"}, "base_url"),
                               ({"base_url": "https://example.com/a b/"}, "base_url"),
                               ({"base_url": "https://example.com/a,b/"}, "base_url"),
                               ({"ext": "png"}, "ext"),
                               ({"available": []}, "available"),
                               ({"available": good["available"] + ["OpenAI"]}, "重复"),
                               ({"available": [x for x in good["available"] if x != "Apple Music／TV"]}, "renamed"),
                               ({"available": good["available"] + ["a/b"]}, "斜杠"),
                               ({"pending": ["OpenAI"]}, "不该再留在 pending"),
                               ({"pending": ["a/b"]}, "斜杠"),
                               ({"pending": ["甲", "甲"]}, "重复"),
                               ({"pending": "Apple Push"}, "pending"),
                               ({"enabled": "yes"}, "enabled")):
            errors = check({**good, **change})
            self.assertTrue(any(needle in e for e in errors), f"{change} 应该被拒绝，得到 {errors}")


if __name__ == "__main__":
    unittest.main()
