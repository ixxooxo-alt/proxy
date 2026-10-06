"""把文档里的占位符 ⟦…⟧ 换成最终运行得到的数字，并核对文档里写的数字和日志、产物一致。
数字都从日志和产物里读。用法：finalize.py [--dry]（在工程根目录运行）"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
dry = "--dry" in sys.argv
ev = "docs/evidence"
RUN_DAY = "2026-10-06"
DIGEST = "3390e37f8d26dbbbe4016d2b94320c1ee08eb7779862dcdd289d117dfd4a3349"
N_TESTS, N_MUT = "244", 98


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


man = json.load(open("dist/manifest.json", encoding="utf-8"))
digest = man["source_sha256"]
assert man["source_version"] == "2026.10.06-1" and man["generator_version"] == "1.5.0", man
assert digest == DIGEST, digest

# 每份日志开头：统一源摘要是当前的、退出码 0、运行环境和日期
for name in ("tests.log", "icu-check.log", "official-check.log", "real-route-check.log", "upstream-field-check.log",
             "upstream-evidence-check.log", "cursor-report-check.log", "icons-check.log", "cn-list-check.log"):
    t = read(f"{ev}/{name}")
    head = t.split("\n\n", 1)[0]
    assert f"统一源摘要：{digest}" in head, name
    assert "Python：Python 3.11.17，PyYAML：6.0.1" in head and f"运行时间（UTC）：{RUN_DAY}" in head, (name, head[:200])
    assert re.search(r"^退出码：0$", t, re.M), name
    assert "scratchpad" not in t and "/tmp/claude" not in t, name

tests = read(f"{ev}/tests.log")
m = re.search(r"^Ran (\d+) tests in [\d.]+s\n\nOK\b(.*)$", tests, re.M)
assert m, "tests.log 里没有 OK"
assert "skipped" not in m.group(2), "有跳过的测试：" + m.group(2)
assert m.group(1) == N_TESTS, m.group(1)

icu = read(f"{ev}/icu-check.log")
assert "13 条（宽 7 条、严 6 条）× 2283 个节点名（其中 625 个有手写的期望）" in icu
assert "× 2306 个节点名" in icu
m = re.search(r"ICU 平均每次匹配：宽 (\d+) 微秒、严 (\d+) 微秒.*?Loon (\d+) 毫秒，Quantumult X（26 个策略各一条）(\d+) 毫秒", icu)
assert m, "icu-check.log 里没有耗时行"
icu_time = (f"这次运行 ICU 平均每次匹配：宽的 {m.group(1)} 微秒、严的 {m.group(2)} 微秒（含调用开销）；按 300 个节点估算 Loon 约 {m.group(3)} 毫秒、"
            f"Quantumult X 约 {m.group(4)} 毫秒（每次运行有出入，r10 时几次运行是 36–38 / 63–66 毫秒，r11 那次是 39 / 67 毫秒；手机会慢几倍）")
long_lines = re.findall(r"^长名字（120、400 个字符两档，共 (\d+) 个）.*?，(ICU|Python)：(.*?)；最慢的一次 ([\d.]+) 毫秒", icu, re.M)
assert len(long_lines) == 2 and all(x[0] == "860" and "全部按时结束，分组与逐步判断完全一致" in x[2] for x in long_lines), long_lines
long_time = "最慢的一次：" + "、".join(f"{eng} {float(ms):.1f} 毫秒" for _, eng, _, ms in long_lines)

off = read(f"{ev}/official-check.log")
assert "节点 2283 个（手写期望：手动组 625 个、自动类组 625 个）" in off and "只进手动组的 72 个" in off
assert "节点 2306 个（手写期望：手动组 24 个、自动类组 24 个）" in off
assert off.count("[符合]") >= 12 and "[不符" not in off and "全部符合预期" in off
assert "if “respect-rules” is turned on, “proxy-server-nameserver” cannot be empty" in off
assert "disallow empty `proxy-server-nameserver` when `proxy-server-nameserver-policy` is set" in off

rr = read(f"{ev}/real-route-check.log")
assert "用例与排除项共 280 条，不同的目标 260 个；DNS 去向用例 sing-box 22 条、mihomo 11 条，拨号解析用例 sing-box 12 条、mihomo 12 条" in rr
assert rr.count("[符合] 路由 260 条") == 3 and rr.count("[符合] DNS 去向 22 条") == 2 and rr.count("[符合] DNS 去向 11 条") == 1, "real-route-check.log"
assert rr.count("[符合] 连接时的解析 12 条") == 3 and rr.count("只有它管的这几条变了，这一处仍然需要") == 3 and rr.count("这两处修正仍然需要") == 2
assert rr.count("[符合] 境外 DNS 不应答") == 3
assert rr.count("连接 6 条、查询 11 条，收到查询的替身与正常那一遍完全相同；其中 4 条只有境外替身收到") == 1
assert rr.count("连接 6 条、查询 22 条，收到查询的替身与正常那一遍完全相同；其中 6 条只有境外替身收到") == 2
assert "[不符合]" not in rr and "\n全部一致\n" in rr and "处不一致" not in rr
for needle in ("node gateway.lan → system", "node homeproxy → system", "direct nas.lan → system", "printer.lan A → system",
               "www.taobao.com A → fake-ip", "printer A → domestic（已知限制的现状，见 docs/06）",
               "chatgpt.com A → fake-ip", "api.openai.com HTTPS → empty", "claude.ai TXT → foreign", "never-listed-query.net A → fake-ip",
               "never-listed-txt.net TXT → foreign", "www.qq.com TXT → domestic", "qwen.ai TXT → domestic（已知限制的现状，见 docs/06）",
               "proxied www.youtube.com → none", "proxied gemini.google.com → none", "proxied chat.qwen.ai → none",
               "unlisted never-listed-site.org → foreign", "unlisted r1.test.dnsleaktest.com → foreign",
               "unlisted never-listed-site.org → dns-foreign", "unlisted r1.test.dnsleaktest.com → dns-foreign",
               "mihomo：扫了 224266 个代表主机",
               "名字会交给国内 DNS 的 222733 个：路由是国内直连 / 直连 / 拦截的 222359 个；归默认直连、可以切换的组的 10 个；走代理组的 364 个",
               "[符合] 官方内核核对 574 个主机",
               "去掉 DNS 规则里“走代理组的产品域名”那一层再扫，走代理组的从 5 个变成 152 个",
               "Loon 订阅的上游规则文件 3 个，按 IP 判断的规则共 187 条：都带 no-resolve",
               "[loon] AdvertisingLite.list：域名 0、后缀 0、关键词 187、IP 段 187（都带 no-resolve）",
               "[loon] ChinaMax_Domain.list：域名 268、后缀 111009、关键词 0、IP 段 0"):
    assert needle in rr, needle
assert rr.count("扫了 19531 个代表主机") == 2
assert rr.count("名字会交给国内 DNS 的 17679 个：路由是国内直连 / 直连 / 拦截的 17673 个；归默认直连、可以切换的组的 1 个；走代理组的 5 个") == 2
assert rr.count("[符合] 官方内核核对 206 个主机") == 2
assert rr.count("280 条，全部符合人工期望") == 4
assert rr.count("为了判断 IP 规则而在本机解析过的域名：251 个里 44 个") == 2 and rr.count("为了判断 IP 规则而在本机解析过的域名：251 个里 0 个") == 2
assert "release 分支 f7c0420" in rr and "rule-set 分支 be94d52" in rr
m = re.search(r"检查了 (\d+) 个字段 / 取值", read(f"{ev}/upstream-field-check.log"))
assert m and m.group(1) == "4531", m and m.group(1)
fields = f"{int(m.group(1)):,}"
ic = read(f"{ev}/icons-check.log")
assert "f250126f57228b0b32f3445b21078e382e6152e9" in ic and "合计 7,037,391 字节" in ic and "81 个地址逐个相同" in ic
assert ic.count("82 个策略组的图标都在图标仓库里，是 PNG，尺寸对") == 6 and "还没有上传" not in ic and "全部符合" in ic
assert "1 个图在图标仓库里、清单没有收，没有比：Apple Push" in ic
cn = read(f"{ev}/cn-list-check.log")
assert "与按固定快照重新生成的逐字节相同：后缀 6142 条、精确域名 12 条（快照 c1c2cf0d，2026-09-22）" in cn and "与上游的 LICENSE 相同" in cn
ue = read(f"{ev}/upstream-evidence-check.log")
assert "核对域名规则 857 条，社区来源 559 条；产品规则下的上游广告条目 30 条；更宽的广告条目 0 条" in ue and "检查通过" in ue
cur = read(f"{ev}/cursor-report-check.log")

snap = json.load(open("tests/data/real_sets.json", encoding="utf-8"))
assert snap["generated"] == "2026-10-06" and snap["source_version"] == "2026.10.06-1", (snap["generated"], snap["source_version"])
mh = snap["official"]["mihomo"]
assert mh["dial"]["node gateway.lan"] == "system" and mh["dns"]["printer A"] == "domestic" and len(mh["dial_sha256"]) == 64
assert mh["dial"]["proxied www.youtube.com"] == "none" and mh["dial"]["unlisted never-listed-site.org"] == "foreign"
assert {"dial_without_node_policy", "dial_without_follow_policy", "dial_without_lan_policy", "dns_without_lan_policy",
        "dial_foreign_silent", "dns_foreign_silent"} <= set(mh), sorted(mh)
assert len(snap["sizes"]["loon"]) == 3 and all(v["ip_resolving"] == 0 for v in snap["sizes"]["loon"].values())
cons = snap["consistency"]
assert len(cons["mihomo"]["mismatch"]) == 364 and len(cons["singbox"]["mismatch"]) == 5 and len(cons["singbox112"]["mismatch"]) == 5
assert len(snap["hosts"]) == 256 and len(snap["ips"]) == 28

cmp11 = read(f"{ev}/与上一版的对比.md")
assert cmp11.startswith("# 版本对比：r11 → r12\n"), cmp11[:40]
assert "| r11 | 625 | 0 | 625 | 0 |" in cmp11 and "| r12 | 625 | 0 | 625 | 0 |" in cmp11
assert "共 2247 个名字" in cmp11 and "### 手动组的归属变了（0 个）" in cmp11 and "成员变了（0 个）" in cmp11
for needle in ("大小：239,978 → 240,438 字节", "大小：402,915 → 403,167 字节", "大小：252,453 → 252,962 字节", "大小：252,636 → 253,145 字节",
               "大小：78,042 → 78,487 字节", "大小：78,068 → 78,513 字节",
               "- 新增：`DOMAIN-SUFFIX,push.apple.com,Apple Push`", "- 新增：`host-suffix, push.apple.com, Apple Push`",
               "- 新增：`{\"domain_suffix\": [\"push.apple.com\"], \"outbound\": \"Apple Push\"}`",
               "<domain_suffix 655 条、domain 108 条>", "<domain_suffix 656 条、domain 108 条>",
               "## 六、严格版", "大小：标准版 240,438 字节，严格版 242,175 字节", "大小：标准版 403,167 字节，严格版 405,351 字节",
               "- 新增：`GEOIP,CN,国内直连,no-resolve`", "- 删除：`GEOIP,CN,国内直连`",
               "`loon/rules/cn-domains.list`：165,603 字节，规则 6,132 条（DOMAIN 12、DOMAIN-SUFFIX 6,120）",
               "`quantumultx/rules/cn-domains.list`：196,295 字节，规则 6,132 条（HOST 12、HOST-SUFFIX 6,120）",
               "`quantumultx/rules/domain-fallback.list`：629 字节，规则 1 条（HOST-KEYWORD 1）"):
    assert needle in cmp11, needle
assert cmp11.count("是这一版新增的严格版") == 2
cmp7 = read(f"{ev}/与r7的对比.md")
assert cmp7.startswith("# 版本对比：r7 → r12\n"), cmp7[:40]
assert "| r7 | 578 | 47 | 534 | 91 |" in cmp7 and "| r12 | 625 | 0 | 625 | 0 |" in cmp7
assert "共 2247 个名字" in cmp7 and "### 手动组的归属变了（47 个）" in cmp7 and "成员变了（53 个）" in cmp7

mut = read(f"{ev}/mutations.log")
assert digest in mut.split("\n\n", 1)[0]
ids = sorted(int(x) for x in re.findall(r"^\[发现\] M(\d+) ", mut, re.M))
bad = re.findall(r"^\[(?:未发现|超时)\] .*$", mut, re.M)
assert ids == list(range(1, N_MUT + 1)) and not bad, (ids, bad)
assert mut.rstrip().endswith(f"合计 {N_MUT}/{N_MUT} 被发现")
res = json.load(open(os.path.join(HERE, "mut-result.json"), encoding="utf-8"))
assert res["digest"] == digest and res["n"] == N_MUT and res["python"] == "Python 3.11.17" and res["pyyaml"] == "6.0.1", res
assert res["full"] == N_TESTS, res["full"]
assert res["state"] == read(os.path.join(HERE, "code-state-at-start.txt")).strip()
segs = res["segments"]
assert all(s["start"].startswith(RUN_DAY) and s["end"].startswith(RUN_DAY) for s in segs), segs
if len(segs) == 1:
    window = f"两批并行，{segs[0]['start'][11:16]}–{segs[0]['end'][11:16]} UTC，一次跑完"
    how = "2026-10-06 第三次定稿以后一次跑完，两批并行"
else:
    window = "两批并行，分 " + str(len(segs)) + " 段：" + "；".join(
        f"{s['start'][11:16]}–{s['end'][11:16]} UTC 跑完 {len(s['ids'])} 类" for s in segs) + "；前面的段被工作环境重启打断，段与段之间代码没有改动"
    how = f"2026-10-06 第三次定稿以后分 {len(segs)} 段跑完（工作环境中途重启过），段与段之间代码没有改动"
fresh = res["fresh"]
assert fresh["solo"] == ["M91", "M92"], fresh
for i in list(range(71, 76)) + list(range(76, N_MUT + 1)):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] M{i} "))
    if f"M{i}" not in res["not_seen"]:
        assert "输出含预期信息" in l, l[:200]
line98 = next(l for l in mut.splitlines() if l.startswith("[发现] M98 "))
assert "test_upstream_lists_have_no_ip_rule_that_would_make_loon_strict_resolve" in line98, line98[:300]
partial_names = sorted(x for v in res["partial"].values() for x in v)
print("部分运行的：", res["partial"], "；未见预期信息：", res["not_seen"])
PARTIAL_EXPECTED = sorted(["M6", "M9", "M31", "M89", "M90"])
if PARTIAL_EXPECTED is not None:
    assert partial_names == PARTIAL_EXPECTED, res["partial"]
PARTIAL_TEXT = ("“恢复关键词 siri”“azure.com 放回 Microsoft”“用回肯定前瞻”和国内域名清单数据文件被改坏的两类（M89、M90）由统一源校验直接拒绝（生成器不肯生成，测试大面积报错）；"
                "严格版的结构被改坏的几类（M76–M78、M80–M82）和“清空 `proxy-server-nameserver`”被写盘前的检查拦住，生成流程的那批测试因此失败，同时另有路由用例失败；"
                "“图标登记里漏了 Apple Push”在生成时直接报错；")
mut_cell = (f"{N_MUT} 类全部被发现，都是 2026-10-06 第三次定稿以后在上面这个摘要的代码上跑的（{window}）。“记录对应现在的配置”那两项——规则与 DNS 两段的摘要、拨号摘要——"
            f"对改了规则、DNS 或出站的变异都会报：{N_MUT} 类里前一项报了 {len(fresh['with']['routing'])} 类、后一项报了 {len(fresh['with']['dial'])} 类，"
            "只靠这两项发现的有 2 类——M91、M92（mihomo 默认的 DNS 换成国内的、sing-box 路由里的 `resolve` 改用国内 DNS）：离线测试不重跑官方内核，它们表现为“官方内核的记录过期”，"
            "失败信息提示重新运行 `tools/check_real_routes.py`。把这两处改动套到副本上实际重跑过一次（2026-10-06，一次性核对，脚本不在交付包里）："
            "两个“没被域名规则接住的域名”在 mihomo 上变成只问国内 DNS、在 sing-box 两个版本上变成问 `dns-cn`，工具报 9 处不一致、拒绝写快照。"
            "其余 96 类都另有针对那个错误本身的测试失败。M45（回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，"
            "那一项把匹配放在带超时的子进程里，等满 5 分钟后失败并给出提示。" + PARTIAL_TEXT + "其余由对应的测试发现，每一类的失败项见日志")
values = {"ICU_TIME": icu_time, "LONG_TIME": long_time, "FIELDS": fields, "MUT_CELL": mut_cell,
          "MUT_RESULT": f"{N_MUT} 类全部被发现（`docs/evidence/mutations.log`；{how}）。其中 M91、M92 两类只表现为“官方内核的记录过期”，要重跑核对工具才看得到具体的错，实际重跑过一次确认（`docs/05` 变异检查一行）。",
          "MUT_STATE": f"{N_MUT} 类全部被发现"}

# 产物大小、摘要与文档里写的一致
sizes = {rel: os.path.getsize(os.path.join("dist", rel)) for rel in man["outputs"]}
assert (sizes["loon/loon.conf"], sizes["quantumultx/quantumultx.conf"], sizes["mihomo/mihomo-profile.yaml"], sizes["mihomo/mihomo-core.yaml"],
        sizes["sing-box/sing-box-1.14.json"], sizes["sing-box/sing-box-1.12.json"]) == (240438, 403167, 252962, 253145, 78487, 78513), sizes
assert (sizes["loon/loon-strict.conf"], sizes["quantumultx/quantumultx-strict.conf"], sizes["loon/rules/cn-domains.list"],
        sizes["quantumultx/rules/cn-domains.list"], sizes["quantumultx/rules/domain-fallback.list"]) == (242175, 405351, 165603, 196295, 629), sizes
doc05 = read("docs/05-验收记录.md")
for rel, v in man["outputs"].items():
    sha = v["sha256"] if isinstance(v, dict) else v
    assert f"`{sha[:8]}…`" in doc05, rel
assert digest in doc05
assert man["rule_counts"] == {"lan_and_system": 24, "ad_exceptions": 10, "ads_local": 71, "product": 851, "service_ip": 14,
                              "product_by_client": {"mihomo": 851, "singbox": 851, "loon": 781, "quantumultx": 781},
                              "strict_real_ip_direct": 8, "strict_cn_domains": {"loon": 6132, "quantumultx": 6132}}, man["rule_counts"]
sys.path.insert(0, ".")
from generator.model import load          # noqa: E402
mdl = load(".", include_local=False)
lo = [len(v.encode()) for v in mdl.node_regexes().values()]
st = [len(v.encode()) for v in mdl.node_regexes_strict().values()]
assert (min(lo), max(lo), min(st), max(st)) == (12955, 15682, 11820, 15084), (min(lo), max(lo), min(st), max(st))

for k, v in values.items():
    print(f"⟦{k}⟧ = {v[:260]}")
files = ["README.md", "README.zh-CN.md", "PROJECT_STATE.md", "00-审核说明.md"] + sorted(os.path.join("docs", f) for f in os.listdir("docs") if f.endswith(".md"))
left = []
for p in files:
    s = read(p)
    s2 = re.sub(r"⟦([^⟧]+)⟧", lambda mm: values[mm.group(1)], s)
    if s2 != s and not dry:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(s2)
    if s2 != s:
        print("已替换：" if not dry else "会替换：", p, len(re.findall(r"⟦", s)))
    left += [(p, x) for x in re.findall(r"⟦[^⟧]*⟧", s2)]
print("剩余占位符：", left)
assert not left
# 文档里的关键数字
for p, needles in (("README.md", ["tests-244%20passing", "244 automated tests", "2026.10.06-1", "625 hand-labelled", "12–16 KB", "Seven rounds of external input",
                                  "43 service groups", "82 policy groups", "260 targets", "loon-strict.conf"]),
                   ("README.zh-CN.md", ["自动测试 244 项", "2026.10.06-1", "625 个人工写期望", "2283 个假节点", "每条 12–16 KB", "约 240 KB", "约 403 KB", "外部意见一共 7 轮",
                                        "82 个策略组", "260 个目标", "loon-strict.conf", "17,679 个里 5 个", "222,733 个里 364 个"]),
                   ("PROJECT_STATE.md", ["244 项", "2026.10.06-1（r12）", "生成器 1.5.0", "每条 12–16 KB", "T23 第 7 轮", "98 类全部被发现", "需求决定项 20 项"]),
                   ("00-审核说明.md", ["197 → 244 项", "75 → 98 类", "1.4.1 → 1.5.0", "注入 98 类错误", "本轮（r12，统一源 2026.10.06-1）", "14 → 20 项"]),
                   ("docs/05-验收记录.md", ["244 项全部通过", "98 类错误", "2026.10.06-1（r12）", "Python 3.11.17，PyYAML 6.0.1", "2283 个假节点", "860 个 120 / 400 个字符",
                                            "4,531 个字段", "260 个目标", "第三次定稿", "`tests/test_real_data.py`，35 项", "`tests/test_strict.py`，30 项"]),
                   ("docs/02-语法依据与能力矩阵.md", ["宽的 13.0–15.7 KB，严的 11.8–15.1 KB", "`tests/test_regions.py` 65 项", "625 个人工写期望的节点名", "v1.19.20",
                                                    "## Loon / Quantumult X 严格版用到的写法（2026-10-06）", "82 个地址指向的文件都在", "ExampleRule.lsr"]),
                   ("docs/03-DNS决策表.md", ["## mihomo：三个解析器各管各的（2026-10-05）", "## Loon / Quantumult X：严格版（2026-10-06）",
                                            "## 走代理的域名不交给国内 DNS：三项固定核对与全集一致性（2026-10-06）", "## 客户端这一侧：哪些设置会让上面的设计不成立（2026-10-06）",
                                            "49 个顶级域", "110,712 条", "187 条 IP 段"]),
                   ("docs/06-已知限制与待决事项.md", ["625 个带期望的节点名", "| 14 | 不带点的名字", "| 20 | Quantumult X 的 `[dns]` 要不要加 `no-system`",
                                                    "## 2026-10-06（r12）：严格版、Apple Push、全集一致性核对之后仍然存在的限制", "第 15–20 项是这一轮新列的"]),
                   ("docs/08-外部审核记录.md", ["197 → 244 项", "75 → 98 类", "2283 个假节点", "## 第 7 轮：2026-10-06，GPT 对做法的两段意见", "docs/evidence/gpt-r12-design/"]),
                   ("docs/09-真机验收操作清单.md", ["对应统一源 2026.10.06-1（r12）", "DNS 覆写", "## 1b. 严格版", "| 13. 换个网络再看一次（可选）"]),
                   ("docs/01-导入、更新、诊断与回滚.md", ["这一版（r12）是 `2026.10.06-1`", "DNS 覆写", "v1.19.20", "## 每个客户端要手动确认的开关（2026-10-06）", "f250126"]),
                   ("docs/07-需求对照.md", ["### 2026-10-06（r11 交付之后，r12）", "cd63eba", "49 个"]),
                   ("docs/00-需求原文.md", ["在已经完成的基础上继续", "你就在你的云端跑吧", "按这个做", "docs/evidence/gpt-r12-design/"])):
    s = read(p)
    for n in needles:
        assert n in s, (p, n)
# 旧的说法不应再作为现状出现（历史记录里的除外，逐个看过）
stale = {"197 项全部通过": [], "注入 75 类": [], "tests-197": [], "自动测试 197 项": [], "197 automated": [], "243 项": [], "97 类": ["docs/00-需求原文.md"], "注入 97 类": [],
         "9e21de7d671fb457": [], "统一源 2026.10.05-2（r11）　生成器": [], "对应统一源 2026.10.05-2（r11）": [],
         "原文没有另外存档": [], "图还没有传上去": [], "50 个顶级域": [], "等 50 个": [], "81 个策略组各带": [], "81 个策略组各一个地址": []}
for p in files:
    s = read(p)
    for k, allowed in stale.items():
        if k in s and p not in allowed:
            raise AssertionError(f"{p} 里还有旧的说法：{k}")
print("核对通过")
