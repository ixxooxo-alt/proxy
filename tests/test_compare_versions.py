"""tools/compare_versions.py：上一版与当前版的对比工具。
它只出报告、不参与生成，但报告是交给审核方看“这一版到底改了什么”的依据，所以拆分和比较的逻辑也要有检查。"""
import contextlib
import io
import os
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import compare_versions as cv  # noqa: E402

LOON_OLD = """# 注释
[General]
ipv6 = false
[Remote Filter]
F-HK = NameRegex, FilterKey = "OLD-HK"
[Proxy Group]
香港·手动 = select,F-HK
香港·自动 = url-test,F-HK,url = http://x/,interval = 300
[Rule]
DOMAIN-SUFFIX,a.example,甲
DOMAIN-SUFFIX,b.example,乙
FINAL,甲
"""
LOON_NEW = """[General]
ipv6 = false
[Remote Filter]
F-HK = NameRegex, FilterKey = "NEW-HK"
F-HK-AUTO = NameRegex, FilterKey = "NEW-HK-STRICT"
[Proxy Group]
香港·手动 = select,F-HK
香港·自动 = url-test,F-HK-AUTO,url = http://x/,interval = 300
[Rule]
DOMAIN-SUFFIX,a.example,甲
DOMAIN-SUFFIX,c.example,丙
DOMAIN-SUFFIX,b.example,乙
FINAL,甲
"""


class Units(unittest.TestCase):
    def setUp(self):
        self.labels = cv.Labels([("上一版 ", {"hk": "OLD-HK"}), ("宽 ", {"hk": "NEW-HK"}), ("严 ", {"hk": "NEW-HK-STRICT"})])

    def diff(self, old, new, rel="loon/loon.conf"):
        rows, same = cv.diff_units(cv.units_of(old, rel, self.labels), cv.units_of(new, rel, self.labels))
        return {sec: (added, removed, changed, order_ok) for sec, added, removed, changed, order_ok in rows}, same

    def test_loon_sections_are_compared_item_by_item(self):
        rows, same = self.diff(LOON_OLD, LOON_NEW)
        self.assertEqual(same, ["General（1 条）"])
        added, removed, changed, order_ok = rows["Remote Filter"]
        self.assertEqual(added, ['F-HK-AUTO = NameRegex, FilterKey = "<筛选：严 hk>"'])
        self.assertEqual((removed, order_ok), ([], True))
        self.assertEqual([(k, a, b) for k, a, b in changed],
                         [("F-HK", 'F-HK = NameRegex, FilterKey = "<筛选：上一版 hk>"', 'F-HK = NameRegex, FilterKey = "<筛选：宽 hk>"')])
        added, removed, changed, order_ok = rows["Proxy Group"]
        self.assertEqual((added, removed, [k for k, _, _ in changed]), ([], [], ["香港·自动"]))
        self.assertIn("去掉 `F-HK`；加上 `F-HK-AUTO`", cv._token_diff(changed[0][1], changed[0][2]))
        added, removed, changed, order_ok = rows["Rule"]
        self.assertEqual((added, removed, changed, order_ok), (["DOMAIN-SUFFIX,c.example,丙"], [], [], True))

    def test_reordering_of_kept_rules_is_reported(self):
        swapped = LOON_OLD.replace("DOMAIN-SUFFIX,a.example,甲\nDOMAIN-SUFFIX,b.example,乙\n",
                                   "DOMAIN-SUFFIX,b.example,乙\nDOMAIN-SUFFIX,a.example,甲\n")
        rows, _ = self.diff(LOON_OLD, swapped)
        self.assertEqual(rows["Rule"], ([], [], [], False), "两条规则换了先后：没有新增和删除，但顺序变了")

    def test_identical_text_has_no_rows(self):
        rows, same = self.diff(LOON_OLD, LOON_OLD)
        self.assertEqual(rows, {})
        self.assertEqual(len(same), 4)

    def test_comment_only_difference_is_stated_not_hidden(self):
        """两版只差注释（例如开头的版本号）：各分段逐条相同，但文件不同。报告要把有差别的行列出来，
        不能只写“没有变化”，也不能写成“和另一个产物的差异一模一样”（r8 → r9 的 Loon / Quantumult X 就是这种情况）。"""
        newer = LOON_OLD.replace("# 注释\n", "# 注释 第二版\n")
        self.assertEqual(self.diff(LOON_OLD, newer)[0], {})
        self.assertEqual(cv.raw_line_diff(LOON_OLD, newer), [("删除", "# 注释"), ("新增", "# 注释 第二版")])
        seen = {}
        first = "\n".join(cv.output_diff_lines(LOON_OLD, newer, "loon/loon.conf", self.labels, seen))
        second = "\n".join(cv.output_diff_lines(LOON_OLD, newer, "quantumultx/quantumultx.conf", self.labels, seen))
        for text in (first, second):
            self.assertIn("各分段的条目完全相同", text)
            self.assertIn("- 删除一行：`# 注释`", text)
            self.assertIn("- 新增一行：`# 注释 第二版`", text)
            self.assertNotIn("一模一样", text)
        self.assertEqual(seen, {}, "没有分段差异时不参与“和另一个产物一模一样”的合并")
        self.assertEqual(cv.output_diff_lines(LOON_OLD, LOON_OLD, "loon/loon.conf", self.labels, seen), ["逐字节相同。", ""])

    def test_identical_differences_are_listed_once(self):
        """同一个客户端的两份产物差异一模一样时，第二份只写“和第一份一样”，不重复列。"""
        seen = {}
        a = cv.output_diff_lines(LOON_OLD, LOON_NEW, "loon/loon.conf", self.labels, seen)
        b = cv.output_diff_lines(LOON_OLD, LOON_NEW, "loon/loon.conf", self.labels, seen)
        self.assertIn("- 新增：`DOMAIN-SUFFIX,c.example,丙`", a)
        self.assertTrue(any("一模一样（Remote Filter、Proxy Group、Rule）" in x for x in b), b)
        self.assertNotIn("- 新增：`DOMAIN-SUFFIX,c.example,丙`", b)

    def test_same_kind_of_change_on_many_items_is_listed_once(self):
        """很多条目改法相同、只是各自的地址不同（给每个策略组加上它自己的图标地址）：合并成一条，
        免得把别的改动淹没；改法不同的那一条仍然单独列出。"""
        names = ["甲", "乙", "丙", "丁", "戊", "己"]
        old = "[Proxy Group]\n" + "".join(f"{n} = select,DIRECT\n" for n in names) + "庚 = select,DIRECT\n"
        new = ("[Proxy Group]\n" + "".join(f"{n} = select,DIRECT,img-url = https://img.example/{i}.png\n" for i, n in enumerate(names))
               + "庚 = select,REJECT\n")
        lines = cv.output_diff_lines(old, new, "loon/loon.conf", self.labels, {})
        text = "\n".join(lines)
        self.assertIn("改动 7 条", text)
        self.assertIn("- 改动 6 条（`甲`、`乙`、`丙` 等，改法相同）：加上 `img-url = <各自的地址>`", lines)
        self.assertIn("- 改动 `庚`：去掉 `DIRECT`；加上 `REJECT`", lines)
        self.assertNotIn("img.example/3.png", text)
        # 不到合并的条数时逐条列出，地址原样保留
        few = cv.collapse_changes([(n, f"{n} = select,DIRECT", f"{n} = select,DIRECT,img-url = https://img.example/{n}.png")
                                   for n in names[:cv.COLLAPSE_AT - 1]])
        self.assertEqual(len(few), cv.COLLAPSE_AT - 1)
        self.assertIn("https://img.example/甲.png", few[0][1])

    def test_same_change_in_every_region_is_listed_once(self):
        """每个地区的组都做了同一种改动、只是各自的地区（和各自的地址）不同：合并成一条，并写明“各自的地区”。
        一种改动一条：换成宽的那条的、换成严的那条的分开列。"""
        regions = ["hk", "jp", "kr", "tw", "sg", "us"]
        labels = cv.Labels([("上一版 ", {r: f"OLD-{r}" for r in regions}), ("宽 ", {r: f"LOOSE-{r}" for r in regions}),
                            ("严 ", {r: f"STRICT-{r}" for r in regions})])
        old = "[policy]\n" + "".join(f"static={r}-手动, server-tag-regex=OLD-{r}\nurl-latency-benchmark={r}-自动, server-tag-regex=OLD-{r}\n"
                                     for r in regions)
        new = "[policy]\n" + "".join(f"static={r}-手动, server-tag-regex=LOOSE-{r}, img-url=https://img.example/{r}-m.png\n"
                                     f"url-latency-benchmark={r}-自动, server-tag-regex=STRICT-{r}, img-url=https://img.example/{r}-a.png\n"
                                     for r in regions)
        lines = cv.output_diff_lines(old, new, "quantumultx/quantumultx.conf", labels, {})
        merged = [x for x in lines if x.startswith("- 改动 6 条")]
        self.assertEqual(len(merged), 2, lines)
        for text, tier in ((merged[0], "宽"), (merged[1], "严")):
            for piece in ("去掉 `server-tag-regex=<筛选：上一版 各自的地区>`", f"server-tag-regex=<筛选：{tier} 各自的地区>", "img-url=<各自的地址>"):
                self.assertIn(piece, text)
        self.assertIn("`static=hk-手动`", merged[0])
        self.assertIn("`url-latency-benchmark=hk-自动`", merged[1])
        # Loon 的策略组引用的是筛选的名字（F-HK、F-HK-AUTO），同样按“各自的地区”合并
        ids = ["HK", "JP", "KR", "TW", "SG", "US"]
        old = "[Proxy Group]\n" + "".join(f"{i}自动 = url-test,F-{i},interval = 300\n" for i in ids)
        new = "[Proxy Group]\n" + "".join(f"{i}自动 = url-test,F-{i}-AUTO,interval = 300\n" for i in ids)
        lines = cv.output_diff_lines(old, new, "loon/loon.conf", labels, {})
        self.assertIn("- 改动 6 条（`HK自动`、`JP自动`、`KR自动` 等，改法相同）：去掉 `F-<各自的地区>`；加上 `F-<各自的地区>-AUTO`", lines)
        self.assertNotIn("img.example", "\n".join(lines))

    def test_singbox_units(self):
        old = '{"dns": {"servers": [{"tag": "a"}], "rules": [{"rule_set": "x", "server": "a"}], "final": "a"},' \
              ' "route": {"rules": [{"domain_suffix": ["a.example", "b.example"], "outbound": "甲"}], "rule_set": [], "final": "甲"},' \
              ' "outbounds": [{"type": "direct", "tag": "甲"}]}'
        new = '{"dns": {"servers": [{"tag": "a"}], "rules": [{"domain": ["q.example"], "server": "a"}, {"rule_set": "x", "server": "a"}], "final": "a"},' \
              ' "route": {"rules": [{"domain_suffix": ["a.example", "b.example", "c.example"], "outbound": "甲"}],' \
              ' "rule_set": [{"type": "inline", "tag": "p", "rules": [{"domain_suffix": ["m.example", "n.example"]}]}], "final": "甲"},' \
              ' "outbounds": [{"type": "direct", "tag": "甲"}]}'
        rows, same = self.diff(old, new, "sing-box/sing-box-1.14.json")
        self.assertEqual(rows["DNS 规则（dns.rules）"][0], ['{"domain": ["q.example"], "server": "a"}'])
        self.assertTrue(rows["DNS 规则（dns.rules）"][3])
        added, removed, changed, _ = rows["路由规则（route.rules）"]
        self.assertEqual((added, removed, len(changed)), ([], [], 1), "只多了一个域名的规则算同一条的改动")
        self.assertEqual(cv._token_diff(changed[0][1], changed[0][2]), '加上 `"c.example"`')
        self.assertEqual(rows["规则集（route.rule_set）"][0], ['{"type": "inline", "tag": "p", "rules": "<domain_suffix 2 条>"}'])
        self.assertIn("出站与策略组（outbounds）（1 条）", same)

    def test_kinds_of_mismatch(self):
        self.assertIsNone(cv.kind(["hk"], ["hk"]))
        self.assertIn("哪个组都没进", cv.kind(["hk"], []))
        self.assertIn("提示行没排除", cv.kind([], ["hk"]))
        self.assertIn("不该进自动类组", cv.kind([], ["jp", "us"], auto=True))
        # 自动类组该进没进，可能是被当成说不清落地，也可能是被当成提示行：说法里不能只认定其中一种
        self.assertIn("说不清落地，或被当成提示行", cv.kind(["us"], [], auto=True))
        self.assertEqual(cv.kind(["hk"], ["hk", "us"]), "多进了别的地区")
        self.assertEqual(cv.kind(["us"], ["other"]), "没认出来，掉进其他地区")


class AgainstItself(unittest.TestCase):
    def test_comparing_the_project_with_itself_reports_no_change(self):
        """拿当前工程当“上一版”：节点分组没有任何名字变化；有 dist/ 时六个产物都逐字节相同。
        顺带核对 --out：结果写到指定的文件，缺省的那份（docs/evidence/与上一版的对比.md）不动。"""
        default = os.path.join(ROOT, cv.OUT)

        def default_bytes():
            if not os.path.exists(default):
                return None
            with open(default, "rb") as f:
                return f.read()

        before = default_bytes()
        with tempfile.TemporaryDirectory() as d:
            target = os.path.join(d, "对比.md")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = cv.main(["--old", ROOT, "--old-label", "甲", "--new-label", "乙", "--write", "--out", target])
            with open(target, encoding="utf-8") as f:
                out = f.read()
        self.assertEqual(rc, 0)
        self.assertIn("已写入", buf.getvalue())
        self.assertTrue(out.startswith("# 版本对比：甲 → 乙\n"))
        self.assertIn(" --write --out ", out.splitlines()[2])
        self.assertEqual(default_bytes(), before, "--out 指到别处时不该改动缺省的那份")
        self.assertIn("### 手动组的归属变了（0 个）", out)
        self.assertIn("只是自动 / 故障转移 / 负载均衡的成员变了（0 个）", out)
        self.assertRegex(out, r"\| 乙 \| (\d+) \| 0 \| \1 \| 0 \|")
        if os.path.exists(os.path.join(ROOT, "dist", "loon", "loon.conf")):
            self.assertEqual(out.count("逐字节相同。"), 6)
            self.assertNotIn("顺序变了", out)


if __name__ == "__main__":
    unittest.main()
