"""把文档里的占位符 ⟦…⟧ 换成最终运行得到的数字，并核对文档里写的数字和日志、产物一致（r14 用的；照 r13-as-used/finalize.py 改的）。
数字都从日志和产物里读。用法（在工程根目录）：python3 handoff/release/r14-as-used/finalize.py <变异日志目录> [--dry]"""
import datetime, json, os, re, subprocess, sys

D = os.path.abspath(sys.argv[1])
dry = "--dry" in sys.argv
ev = "docs/evidence"
RUN_DAY = "2026-10-07"
DIGEST = "a72e446d96b6c83c9858f4b5ecb482ed1787ac55a5e0a64e2fa94f18380f1acc"     # r14：生成器 1.6.0 改了 mihomo 的 DNS 段
N_TESTS, N_MUT, N_MIHOMO_DNS = "254", 104, "13"
ENV = "Python：Python 3.13.16，PyYAML：6.0.1"
R13 = "bf42e8b"                                                                   # GPT 审的 r13（只改文档的那次提交，配置与 4510096 相同）


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


man = json.load(open("dist/manifest.json", encoding="utf-8"))
digest = man["source_sha256"]
assert man["source_version"] == "2026.10.07-1" and man["generator_version"] == "1.6.0", man
assert digest == DIGEST, digest
freeze = read(os.path.expanduser("~/proxy-work/freeze14-time.txt")).strip()        # 定稿时记下的时间（UTC）
state = subprocess.run(["bash", "handoff/release/code_state.sh"], capture_output=True, text=True, check=True).stdout.strip()
assert state == read(os.path.expanduser("~/proxy-work/freeze14-state.txt")).strip(), "代码在定稿之后变过"
assert freeze.startswith(RUN_DAY), freeze

# 每份日志开头：统一源摘要是当前的、退出码 0、运行环境和日期；记下开始时间和文件时间
LOGS = ("tests.log", "icu-check.log", "official-check.log", "real-route-check.log", "upstream-field-check.log",
        "upstream-evidence-check.log", "cursor-report-check.log", "icons-check.log", "cn-list-check.log")
starts, ends = [], []
for name in LOGS:
    t = read(f"{ev}/{name}")
    head = t.split("\n\n", 1)[0]
    assert f"统一源摘要：{digest}" in head, name
    assert ENV in head and f"运行时间（UTC）：{RUN_DAY}" in head, (name, head[:200])
    assert re.search(r"^退出码：0$", t, re.M), name
    assert "scratchpad" not in t and "/tmp/claude" not in t and "/root/.claude" not in t, name
    starts.append(re.search(r"运行时间（UTC）：(\S+ \S+)", head).group(1))
    ends.append(datetime.datetime.fromtimestamp(os.path.getmtime(f"{ev}/{name}"), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
assert min(starts) > freeze, (min(starts), freeze)
checks_window = f"{min(starts)[11:16]}–{max(ends)[11:16]} UTC"

tests = read(f"{ev}/tests.log")
m = re.search(r"^Ran (\d+) tests in [\d.]+s\n\nOK\b(.*)$", tests, re.M)
assert m, "tests.log 里没有 OK"
assert "skipped" not in m.group(2), "有跳过的测试：" + m.group(2)
assert m.group(1) == N_TESTS, m.group(1)
for t in ("test_mihomo_unmatched_names_ask_only_the_foreign_doh", "test_singbox_unmatched_names_ask_only_dns_foreign",
          "test_each_kind_of_reply_is_told_apart",
          # r14 加的 7 项和改写的 1 项
          "test_policy_lookup_follows_mihomos_domain_trie", "test_mihomo_product_names_go_to_the_foreign_dns",
          "test_names_ending_in_a_pointer_after_labels_are_read", "test_singbox_and_mihomo_both_have_the_product_layer",
          "test_cases_cover_the_point_of_the_check", "test_recorded_official_runs_match_the_cases",
          "test_mihomo_never_hands_a_proxied_name_to_the_domestic_dns", "test_self_check_sees_the_product_layer"):
    assert re.search(rf"^{t} \(.*\) \.\.\. ok$", tests, re.M), t
assert "test_singbox_and_mihomo_differ_as_documented" not in tests
assert "DeprecationWarning" not in tests
# 各测试文件的项数从日志里数
per_file = {}
for mod, _cls, _name in set(re.findall(r"\((test_\w+)\.(\w+)\.(\w+)\)", tests)):
    per_file[mod] = per_file.get(mod, 0) + 1
assert sum(per_file.values()) == int(N_TESTS), per_file
assert (per_file["test_real_data"], per_file["test_strict"], per_file["test_dns_lan"]) == (41, 30, 13), per_file

icu = read(f"{ev}/icu-check.log")
assert "13 条（宽 7 条、严 6 条）× 2283 个节点名（其中 625 个有手写的期望）" in icu
assert "× 2306 个节点名" in icu
m = re.search(r"ICU 平均每次匹配：宽 (\d+) 微秒、严 (\d+) 微秒.*?Loon (\d+) 毫秒，Quantumult X（26 个策略各一条）(\d+) 毫秒", icu)
assert m, "icu-check.log 里没有耗时行"
icu_time = (f"这次运行 ICU 平均每次匹配：宽的 {m.group(1)} 微秒、严的 {m.group(2)} 微秒（含调用开销）；按 300 个节点估算 Loon 约 {m.group(3)} 毫秒、"
            f"Quantumult X 约 {m.group(4)} 毫秒（每次运行有出入：r13 那次在同一台机器上是 49 / 93 毫秒，r12 是 29 / 51 毫秒（另一台机器），"
            f"r10 时几次运行是 36–38 / 63–66 毫秒；手机会慢几倍）")
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
assert f"用例与排除项共 280 条，不同的目标 260 个；DNS 去向用例 sing-box 22 条、mihomo {N_MIHOMO_DNS} 条，拨号解析用例 sing-box 12 条、mihomo 12 条" in rr
assert rr.count("[符合] 路由 260 条") == 3 and rr.count("[符合] DNS 去向 22 条") == 2 and rr.count(f"[符合] DNS 去向 {N_MIHOMO_DNS} 条") == 1, "real-route-check.log"
assert rr.count("[符合] 连接时的解析 12 条") == 3 and rr.count("只有它管的这几条变了，这一处仍然需要") == 3 and rr.count("这两处修正仍然需要") == 2
assert rr.count("[符合] 境外 DNS 不应答") == 3
assert rr.count(f"连接 6 条、查询 {N_MIHOMO_DNS} 条，收到查询的替身与正常那一遍完全相同；其中 5 条只有境外替身收到") == 1
assert rr.count("连接 6 条、查询 22 条，收到查询的替身与正常那一遍完全相同；其中 6 条只有境外替身收到") == 2
assert "[不符合]" not in rr and "\n全部一致\n" in rr and "处不一致" not in rr and "全集" not in rr
for needle in ("node gateway.lan → system", "node homeproxy → system", "direct nas.lan → system", "printer.lan A → system",
               "www.taobao.com A → fake-ip", "printer A → domestic（已知限制的现状，见 docs/06）",
               "chatgpt.com A → fake-ip", "api.openai.com HTTPS → empty", "claude.ai TXT → foreign", "never-listed-query.net A → fake-ip",
               "never-listed-txt.net TXT → foreign", "www.qq.com TXT → domestic", "google.cn AAAA → empty",
               "qwen.ai TXT → foreign", "tlu.dl.delivery.mp.microsoft.com TXT → domestic",
               "proxied www.youtube.com → none", "proxied gemini.google.com → none", "proxied chat.qwen.ai → none",
               "unlisted never-listed-site.org → foreign", "unlisted r1.test.dnsleaktest.com → foreign",
               "unlisted never-listed-site.org → dns-foreign", "unlisted r1.test.dnsleaktest.com → dns-foreign",
               # 出站时的解析（r14）
               "[符合] 出站时的解析 8 个主机 × 3 种出口",
               "qwen.ai：socks5-tcp → none，socks5-udp → foreign，wireguard-tcp → foreign",
               "download.microsoft.com：socks5-tcp → none，socks5-udp → foreign，wireguard-tcp → foreign",
               "chatgpt.com：socks5-tcp → none，socks5-udp → foreign，wireguard-tcp → foreign",
               "never-listed-site.org：socks5-tcp → foreign，socks5-udp → foreign，wireguard-tcp → foreign",
               "www.qq.com：socks5-tcp → domestic，socks5-udp → domestic，wireguard-tcp → domestic",
               "www.apple.com：socks5-tcp → domestic，socks5-udp → domestic，wireguard-tcp → domestic",
               "tlu.dl.delivery.mp.microsoft.com：socks5-tcp → domestic，socks5-udp → domestic，wireguard-tcp → domestic",
               "time.windows.com：socks5-tcp → none，socks5-udp → foreign，wireguard-tcp → foreign（已知限制的现状，见 docs/06）",
               "自检：去掉 nameserver-policy 里走代理组的产品域名那一层后，WireGuard 出口下 download.microsoft.com → domestic、qwen.ai → domestic——只有这一类变回国内 DNS，这一层仍然需要",
               # 逐条扫描
               "国内 DNS 与路由的逐条扫描", "mihomo：扫了 224266 个代表主机",
               "名字会交给国内 DNS 的 222593 个：路由是国内直连 / 直连 / 拦截的 222361 个；归默认直连、可以切换的组的 10 个；走代理组的 222 个",
               "走代理组：来自 geosite:private、路由交给 国外默认 的 222 个",
               "[符合] 官方内核核对 432 个主机",
               "自检：去掉 nameserver-policy 里“走代理组的产品域名”那一层再扫，走代理组的从 222 个变成 364 个——这一层仍然需要，这项核对看得见它要防的错误",
               "[符合] 多出来的 142 个（产品域名那一层管到的）交给官方内核查 TXT：都只由境外 DNS 的替身收到",
               "去掉 DNS 规则里“走代理组的产品域名”那一层再扫，走代理组的从 5 个变成 152 个",
               "Loon 订阅的上游规则文件 3 个，按 IP 判断的规则共 187 条：都带 no-resolve",
               "[loon] AdvertisingLite.list：域名 0、后缀 0、关键词 187、IP 段 187（都带 no-resolve）",
               "[loon] ChinaMax_Domain.list：域名 268、后缀 111009、关键词 0、IP 段 0"):
    assert needle in rr, needle
assert "qwen.ai TXT → domestic" not in rr
assert rr.count("[符合] 出站时的解析 8 个主机 × 2 种出口") == 2
for needle in ("qwen.ai：socks-udp → none，wireguard-tcp → dns-foreign", "download.microsoft.com：socks-udp → none，wireguard-tcp → dns-foreign",
               "chatgpt.com：socks-udp → none，wireguard-tcp → dns-foreign", "never-listed-site.org：socks-udp → dns-foreign，wireguard-tcp → dns-foreign",
               "www.qq.com：socks-udp → dns-cn，wireguard-tcp → dns-cn", "www.apple.com：socks-udp → dns-cn，wireguard-tcp → dns-cn",
               "tlu.dl.delivery.mp.microsoft.com：socks-udp → dns-cn，wireguard-tcp → dns-cn",
               "time.windows.com：socks-udp → none，wireguard-tcp → dns-cn（已知限制的现状，见 docs/06）"):
    assert rr.count(needle) == 2, needle
assert rr.count("扫了 19531 个代表主机") == 2
assert rr.count("名字会交给国内 DNS 的 17679 个：路由是国内直连 / 直连 / 拦截的 17673 个；归默认直连、可以切换的组的 1 个；走代理组的 5 个") == 2
assert rr.count("[符合] 官方内核核对 206 个主机") == 2
assert rr.count("280 条，全部符合人工期望") == 4
assert rr.count("为了判断 IP 规则而在本机解析过的域名：251 个里 44 个") == 2 and rr.count("为了判断 IP 规则而在本机解析过的域名：251 个里 0 个") == 2
assert "release 分支 f7c0420" in rr and "rule-set 分支 be94d52" in rr
m = re.search(r"检查了 (\d+) 个字段 / 取值", read(f"{ev}/upstream-field-check.log"))
assert m and m.group(1) == "4531", m and m.group(1)      # docs/05 写的是“与 r12、r13 相同”
fields = f"{int(m.group(1)):,}"
ic = read(f"{ev}/icons-check.log")
assert "f250126f57228b0b32f3445b21078e382e6152e9" in ic and "合计 7,037,391 字节" in ic and "81 个地址逐个相同" in ic
assert ic.count("82 个策略组的图标都在图标仓库里，是 PNG，尺寸对") == 6 and "还没有上传" not in ic and "全部符合" in ic
assert "1 个图在图标仓库里、清单没有收，没有比：Apple Push" in ic
cn = read(f"{ev}/cn-list-check.log")
assert "与按固定快照重新生成的逐字节相同：后缀 6142 条、精确域名 12 条（快照 c1c2cf0d，2026-09-22）" in cn and "与上游的 LICENSE 相同" in cn
ue = read(f"{ev}/upstream-evidence-check.log")
assert "核对域名规则 857 条，社区来源 559 条；产品规则下的上游广告条目 30 条；更宽的广告条目 0 条" in ue and "检查通过" in ue

snap = json.load(open("tests/data/real_sets.json", encoding="utf-8"))
assert snap["generated"] == RUN_DAY and snap["source_version"] == "2026.10.07-1", (snap["generated"], snap["source_version"])
mh = snap["official"]["mihomo"]
assert mh["dial"]["node gateway.lan"] == "system" and mh["dns"]["printer A"] == "domestic" and len(mh["dial_sha256"]) == 64
assert mh["dns"]["google.cn AAAA"] == "empty" and mh["dns_foreign_silent"]["google.cn AAAA"] == "empty"
assert mh["dns"]["qwen.ai TXT"] == "foreign" and mh["dns"]["tlu.dl.delivery.mp.microsoft.com TXT"] == "domestic"
assert mh["dial"]["proxied www.youtube.com"] == "none" and mh["dial"]["unlisted never-listed-site.org"] == "foreign"
assert mh["outbound"]["mihomo-wireguard-tcp"]["qwen.ai"] == "foreign" and mh["outbound_without_product_layer"]["qwen.ai"] == "domestic"
assert all("domestic" not in (v["qwen.ai"], v["download.microsoft.com"], v["chatgpt.com"], v["time.windows.com"]) for v in mh["outbound"].values())
for fam in ("singbox", "singbox112"):
    ob = snap["official"][fam]["outbound"]
    assert ob["singbox-wireguard-tcp"]["qwen.ai"] == "dns-foreign" and ob["singbox-wireguard-tcp"]["time.windows.com"] == "dns-cn", fam
assert len(snap["sizes"]["loon"]) == 3 and all(v["ip_resolving"] == 0 for v in snap["sizes"]["loon"].values())
cons = snap["consistency"]
assert len(cons["mihomo"]["mismatch"]) == 222 and len(cons["singbox"]["mismatch"]) == 5 and len(cons["singbox112"]["mismatch"]) == 5
assert cons["mihomo"]["without_product_dns_rules"] == 364 and cons["mihomo"]["product_layer_checked"] == 142 and cons["mihomo"]["official_checked"] == 432
assert cons["singbox"]["without_product_dns_rules"] == 152
assert len(snap["hosts"]) == 256 and len(snap["ips"]) == 28
assert "逐条扫描" in snap["about"] and "全集" not in snap["about"]

cmp13 = read(f"{ev}/与上一版的对比.md")
assert cmp13.startswith("# 版本对比：r13 → r14\n"), cmp13[:40]
assert "| r13 | 625 | 0 | 625 | 0 |" in cmp13 and "| r14 | 625 | 0 | 625 | 0 |" in cmp13
assert "共 2247 个名字" in cmp13 and "### 手动组的归属变了（0 个）" in cmp13 and "成员变了（0 个）" in cmp13
assert cmp13.count("逐字节相同。") == 2, cmp13.count("逐字节相同。")                    # sing-box 两份
assert cmp13.count("和 r13 的一模一样。") == 3                                         # 三个规则文件
assert cmp13.count("各分段的条目完全相同；两个文件的差别只在拆分时不计入的内容里") == 4  # Loon、Quantumult X 四份：只差版本号那一行注释
assert cmp13.count("- 删除一行：`# 统一源版本 2026.10.06-1；") == 4 and cmp13.count("- 新增一行：`# 统一源版本 2026.10.07-1；") == 4
for needle in ("大小：252,962 → 278,625 字节。", "大小：253,145 → 278,808 字节。",
               "**DNS（dns）**：新增 0 条，删除 0 条，改动 1 条；两版都有的条目顺序不变。", "- 改动 `nameserver-policy`：",
               "有差异的分段和 `mihomo/mihomo-profile.yaml` 的一模一样（DNS（dns）），不重复列出。",
               "没有变化的分段：策略组（proxy-groups）（82 条）、规则（rules）（975 条）",
               "## 六、严格版", "大小：标准版 240,438 字节，严格版 242,175 字节", "大小：标准版 403,167 字节，严格版 405,351 字节",
               "- 新增：`GEOIP,CN,国内直连,no-resolve`", "- 删除：`GEOIP,CN,国内直连`",
               "`loon/rules/cn-domains.list`：165,603 字节，规则 6,132 条（DOMAIN 12、DOMAIN-SUFFIX 6,120）",
               "`quantumultx/rules/cn-domains.list`：196,295 字节，规则 6,132 条（HOST 12、HOST-SUFFIX 6,120）",
               "`quantumultx/rules/domain-fallback.list`：629 字节，规则 1 条（HOST-KEYWORD 1）"):
    assert needle in cmp13, needle
assert cmp13.count("**DNS（dns）**") == 1                                              # 只有 mihomo 的 DNS 段变了
cmp7 = read(f"{ev}/与r7的对比.md")
assert cmp7.startswith("# 版本对比：r7 → r14\n"), cmp7[:40]
assert "| r7 | 578 | 47 | 534 | 91 |" in cmp7 and "| r14 | 625 | 0 | 625 | 0 |" in cmp7
assert "共 2247 个名字" in cmp7 and "### 手动组的归属变了（47 个）" in cmp7 and "成员变了（53 个）" in cmp7

mut = read(f"{ev}/mutations.log")
assert digest in mut.split("\n\n", 1)[0] and state in mut.split("\n\n", 1)[0]
ids = sorted(int(x) for x in re.findall(r"^\[发现\] M(\d+) ", mut, re.M))
bad = re.findall(r"^\[(?:未发现|超时)\] .*$", mut, re.M)
assert ids == list(range(1, N_MUT + 1)) and not bad, (ids, bad)
assert mut.rstrip().endswith(f"合计 {N_MUT}/{N_MUT} 被发现")
res = json.load(open(os.path.join(D, "mut-result.json"), encoding="utf-8"))
assert res["digest"] == digest and res["n"] == N_MUT and res["python"] == "Python 3.13.16" and res["pyyaml"] == "6.0.1", res
assert res["full"] == N_TESTS, res["full"]
assert res["state"] == state
segs = res["segments"]
assert all(s["start"].startswith(RUN_DAY) and s["end"].startswith(RUN_DAY) for s in segs), segs
assert all(s["start"] > freeze for s in segs), (segs, freeze)
if len(segs) == 1:
    window = f"两批并行，{segs[0]['start'][11:16]}–{segs[0]['end'][11:16]} UTC，一次跑完"
else:
    window = "两批并行，分 " + str(len(segs)) + " 段：" + "；".join(
        f"{s['start'][11:16]}–{s['end'][11:16]} UTC 跑完 {len(s['ids'])} 类" for s in segs) + "；前面的段被工作环境重启打断，段与段之间代码没有改动"
fresh = res["fresh"]
assert fresh["solo"] == [], fresh
NEW_TESTS = {"M101": "test_names_ending_in_a_pointer_after_labels_are_read", "M102": "test_mihomo_product_names_go_to_the_foreign_dns",
             "M103": "test_mihomo_product_names_go_to_the_foreign_dns", "M104": "test_policy_lookup_follows_mihomos_domain_trie"}
for name, test in [("M91", "test_mihomo_unmatched_names_ask_only_the_foreign_doh"), ("M92", "test_singbox_unmatched_names_ask_only_dns_foreign"),
                   ("M99", "test_singbox_unmatched_names_ask_only_dns_foreign"), ("M100", "test_each_kind_of_reply_is_told_apart")] + list(NEW_TESTS.items()):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] {name} "))
    assert test in l and "输出含预期信息" in l, l[:300]
# M102 另由出站时的解析（快照记录对不上现在的配置）和逐条扫描发现：看失败项里有哪些，写进文档
m102 = next(x for x in mut.splitlines() if x.startswith("[发现] M102 "))
m102_items = re.findall(r"'([^']+)'", re.search(r"失败项 \[(.*?)\]", m102).group(1))
for i in list(range(71, N_MUT + 1)):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] M{i} "))
    if f"M{i}" not in res["not_seen"]:
        assert "输出含预期信息" in l, l[:200]
assert "DeprecationWarning" not in mut
partial_names = sorted(x for v in res["partial"].values() for x in v)
print("部分运行的：", res["partial"], "；未见预期信息：", res["not_seen"], "；M102 的失败项：", m102_items)
assert partial_names == sorted(["M6", "M9", "M31", "M89", "M90"]), res["partial"]
PARTIAL_TEXT = ("“恢复关键词 siri”“azure.com 放回 Microsoft”“用回肯定前瞻”和国内域名清单数据文件被改坏的两类（M89、M90）由统一源校验直接拒绝（生成器不肯生成，测试大面积报错）；"
                "严格版的结构被改坏的几类（M76–M78、M80–M82）和“清空 `proxy-server-nameserver`”被写盘前的检查拦住，生成流程的那批测试因此失败，同时另有路由用例失败；"
                "“图标登记里漏了 Apple Push”在生成时直接报错；")
mut_cell = (f"{N_MUT} 类全部被发现，都是 r14 定稿（{freeze[:16]} UTC）以后在上面这个摘要、这个代码状态的代码上跑的（{window}）。"
            "“记录对应现在的配置”那两项——规则与 DNS 两段的摘要、拨号摘要——对改了规则、DNS 或出站的变异都会报："
            f"{N_MUT} 类里前一项报了 {len(fresh['with']['routing'])} 类、后一项报了 {len(fresh['with']['dial'])} 类；只靠这两项发现的一类都没有（r13 起）。"
            "这一轮新加的四类：M101（读名字时又只在第一个字节看压缩指针）由 `tests/test_real_data.py` 的 `test_names_ending_in_a_pointer_after_labels_are_read` 发现；"
            "M102（mihomo 的 `nameserver-policy` 又没有产品域名那一层）、M103（那一层把默认直连的组也交给境外 DNS）由 `tests/test_dns_lan.py` 的 "
            "`test_mihomo_product_names_go_to_the_foreign_dns` 发现，M102 同时让“记录对应现在的配置”那两项失败；"
            "M104（核对工具按“第一条命中”查）由 `test_policy_lookup_follows_mihomos_domain_trie` 发现。"
            "M45（回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，"
            "那一项把匹配放在带超时的子进程里，等满 5 分钟后失败并给出提示。" + PARTIAL_TEXT + "其余由对应的测试发现，每一类的失败项见日志")
assert "test_recorded_official_runs_used_the_current_rules" in " ".join(m102_items) and "test_recorded_dial_runs_used_the_current_dial_config" in " ".join(m102_items), m102_items


# 一次性核对：GPT 审 r13 的实验，r13 和这一版的配置各一遍
def parse_probe(text):
    """→ {(内核, 出口, 流量): {主机: 去向}}；内核是 mihomo / sing-box。"""
    out, core, key = {}, None, None
    for ln in text.splitlines():
        if ln.startswith("mihomo："):
            core = "mihomo"
        elif ln.startswith("sing-box："):
            core = "sing-box"
        mm = re.match(r"^(\S+)\s+(TCP|UDP（目标写域名）|UDP（目标是假地址）)$", ln)
        if mm:
            key = (core, mm.group(1), mm.group(2))
            out[key] = {}
            continue
        mm = re.match(r"^    (\S+)\s+→ (\S+?)(?:（|$)", ln)
        if mm and key:
            out[key][mm.group(1)] = mm.group(2)
    return out


p13, p14 = read("handoff/notes/r13_review_probes.r13.out"), read("handoff/notes/r13_review_probes.out")
assert "统一源版本 2026.10.06-1" in p13.split("\n")[1] and "统一源版本 2026.10.07-1" in p14.split("\n")[1]
assert "Mihomo Meta v1.19.31" in p13 and "sing-box version 1.14.1" in p13 and "Mihomo Meta v1.19.31" in p14 and "sing-box version 1.14.1" in p14
r13p, r14p = parse_probe(p13), parse_probe(p14)
assert set(r13p) == set(r14p) and len(r13p) == 16, sorted(r13p)
resolving = [k for k in r13p if k[0] == "mihomo" and (k[2] != "TCP" or k[1] == "wireguard") and k[1] != "wireguard+remote-dns"]
assert len(resolving) == 8, resolving                                    # UDP 7 种 + WireGuard 的 TCP
for k in resolving:
    assert r13p[k] == {"qwen.ai": "domestic", "chatgpt.com": "foreign", "www.qq.com": "domestic"}, (k, r13p[k])
    assert r14p[k] == {"qwen.ai": "foreign", "chatgpt.com": "foreign", "www.qq.com": "domestic"}, (k, r14p[k])
for k in [k for k in r13p if k[0] == "mihomo" and k not in resolving]:   # SOCKS5、Shadowsocks 的 TCP，WireGuard 远程解析
    assert r13p[k] == r14p[k] == {"qwen.ai": "none", "chatgpt.com": "none", "www.qq.com": "domestic"}, (k, r13p[k], r14p[k])
for k in [k for k in r13p if k[0] == "sing-box"]:
    assert r13p[k] == r14p[k], k                                         # sing-box 的配置两版逐字节相同
    want = ({"qwen.ai": "dns-foreign", "chatgpt.com": "dns-foreign", "www.qq.com": "dns-cn", "time.windows.com": "dns-cn"} if k[1] == "wireguard"
            else {"qwen.ai": "none", "chatgpt.com": "none", "www.qq.com": "dns-cn", "time.windows.com": "none"})
    assert r13p[k] == want, (k, r13p[k])
probe_cell = ("r13 的配置（`r13_review_probes.r13.out`）：走代理的组换成 SOCKS5、Shadowsocks 出口时，`qwen.ai` 走 TCP 没有被解析；"
              "走 UDP（目标写域名、目标是假地址两种）、换成 Trojan 走 UDP、换成 WireGuard 走 TCP 和 UDP 时，`qwen.ai` 的 A、AAAA 查询都由国内 DNS 的替身收到——"
              "WireGuard 的那两种与审核报告一致，UDP 的那几种是核实时自查出来的；WireGuard 打开 `remote-dns-resolve`（查询走隧道）时三类替身都没有收到。"
              "`chatgpt.com` 在会解析的那几种里都问境外，`www.qq.com`（直连）都问国内。"
              "**这一版的配置**（`r13_review_probes.out`）：同样那 8 种会解析的情况，`qwen.ai` 都只问境外 DNS，其余结果不变。"
              "sing-box 1.14.1（两版的配置逐字节相同，结果也相同）：SOCKS、Shadowsocks 的 TCP、UDP 都没有解析走代理的名字；"
              "WireGuard 端点走 TCP、UDP 时 `qwen.ai`、`chatgpt.com` 问 `dns-foreign`，`time.windows.com` 问 `dns-cn`（待决事项第 15 项）")

sr = read("handoff/notes/r13_strict_routes.out")
for needle in ("条目 111277 条（后缀 111009，精确 268，关键词 0）",
               "Loon 严格版远程规则顺序：AdvertisingLite.list → AdvertisingLite_Domain.list → ChinaMax_Domain.list → cn-domains.list → FINAL 国外默认",
               "Quantumult X 严格版远程规则顺序：AdvertisingLite.list → cn-domains.list → domain-fallback.list → final 国外默认",
               "  国内直连 / 国外默认：105317 条（94.64%）", "  国内直连 / 国内直连：5728 条（5.15%）", "  广告拦截 / 广告拦截：152 条（0.14%）",
               "  Microsoft / Microsoft：54 条（0.05%）", "  Google / Google：10 条（0.01%）",
               "    ChinaMax_Domain.list / cn-domains.list：5715 条", "    AdvertisingLite_Domain.list / AdvertisingLite.list：97 条",
               "    本地规则 / 本地规则：96 条", "    AdvertisingLite.list / AdvertisingLite.list：52 条",
               "  国内直连 / 国外默认：105380 条（94.70%）"):
    assert needle in sr, needle
po = read("handoff/notes/r14_policy_order.out")
for needle in ("统一源版本 2026.10.07-1", "nameserver-policy：742 个键，普通域名写法 745 条；比较的主机 2235 个",
               "1. 交付的书写顺序：域名树和“第一条命中”结果不同的主机 0 个",
               "2. 把普通域名写法的先后倒过来：域名树的结果变了的 0 个；“第一条命中”的结果变了的 3 个",
               "    delivery.mp.microsoft.com：倒过来以前 国内，倒过来以后 境外"):
    assert needle in po, needle
order_cell = ("配置里 `nameserver-policy` 的 742 个键（普通域名写法 745 条），每条写法本身、一个子域、两级子域，共 2,235 个主机：按交付的书写顺序，"
              "域名树和“第一条命中”（r13 的核对工具）结果相同，一个不差；把普通域名写法的先后倒过来，域名树一个都不变，“第一条命中”有 3 个变了"
              "（`delivery.mp.microsoft.com` 和它的两个子域从国内变成境外）。也就是说这一版配置的结论不依赖先后，改工具是为了不依赖一个 mihomo 并不看的先后")

values = {"ICU_TIME": icu_time, "LONG_TIME": long_time, "FIELDS": fields, "MUT_CELL": mut_cell, "PROBE_CELL": probe_cell, "ORDER_CELL": order_cell,
          "tests_n": N_TESTS, "mut_n": str(N_MUT), "mihomo_dns_n": N_MIHOMO_DNS, "code_state": state, "freeze_utc": freeze[:16],
          "mut_window": window, "checks_window": checks_window,
          "run_window": f"{RUN_DAY}（UTC）", "run_day_en": RUN_DAY}

# 产物大小、摘要与文档里写的一致
sizes = {rel: os.path.getsize(os.path.join("dist", rel)) for rel in man["outputs"]}
assert (sizes["loon/loon.conf"], sizes["quantumultx/quantumultx.conf"], sizes["mihomo/mihomo-profile.yaml"], sizes["mihomo/mihomo-core.yaml"],
        sizes["sing-box/sing-box-1.14.json"], sizes["sing-box/sing-box-1.12.json"]) == (240438, 403167, 278625, 278808, 78487, 78513), sizes
assert (sizes["loon/loon-strict.conf"], sizes["quantumultx/quantumultx-strict.conf"], sizes["loon/rules/cn-domains.list"],
        sizes["quantumultx/rules/cn-domains.list"], sizes["quantumultx/rules/domain-fallback.list"]) == (242175, 405351, 165603, 196295, 629), sizes
doc05 = read("docs/05-验收记录.md")
for rel, v in man["outputs"].items():
    sha = v["sha256"] if isinstance(v, dict) else v
    assert f"`{sha[:8]}…`" in doc05, rel
assert digest in doc05
# dist/ 与 r13 的提交相比：只有 mihomo 两份、Loon / Quantumult X 四份（版本号那一行）和 manifest 变了
changed = subprocess.run(["git", "diff", "--name-only", R13, "--", "dist"], capture_output=True, text=True, check=True).stdout.split()
assert sorted(changed) == sorted(["dist/manifest.json", "dist/mihomo/mihomo-core.yaml", "dist/mihomo/mihomo-profile.yaml", "dist/loon/loon.conf",
                                  "dist/loon/loon-strict.conf", "dist/quantumultx/quantumultx.conf", "dist/quantumultx/quantumultx-strict.conf"]), changed
for rel in ("loon/loon.conf", "loon/loon-strict.conf", "quantumultx/quantumultx.conf", "quantumultx/quantumultx-strict.conf"):
    d = subprocess.run(["git", "diff", "-U0", R13, "--", f"dist/{rel}"], capture_output=True, text=True, check=True).stdout
    body = [x for x in d.splitlines() if x[:1] in "+-" and not x.startswith(("+++", "---"))]
    assert len(body) == 2 and all("统一源版本" in x for x in body), (rel, body)
pol = __import__("yaml").safe_load(read("dist/mihomo/mihomo-core.yaml"))["dns"]["nameserver-policy"]
assert len(pol) == 742 and sum(1 for v in pol.values() if v == ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"]) == 739, len(pol)

for k, v in values.items():
    print(f"⟦{k}⟧ = {v[:200]}")
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
if dry:
    sys.exit(0)
assert not left
# 文档里的关键数字和这一版的说法
for p, needles in (("README.md", ["tests-254%20passing", "254 automated tests", "2026.10.07-1", "This is r14", "625 hand-labelled", "12–16 KB",
                                  "43 service groups", "82 policy groups", "260 targets", "loon-strict.conf", "13 on mihomo"]),
                   ("README.zh-CN.md", ["自动测试 254 项", "2026.10.07-1", "（r14；处理的是 GPT 对 r13 的审核", "625 个人工写期望", "2283 个假节点",
                                        "每条 12–16 KB", "82 个策略组", "260 个目标", "mihomo 13 条", "17,679 个代表主机里 5 个",
                                        "222,593 个里 222 个", "Python 3.13.16"]),
                   ("PROJECT_STATE.md", ["254 项", "r14：统一源 2026.10.07-1", "生成器 1.6.0", "T25 第 9 轮", "104 类全部被发现", "需求决定项 20 项",
                                         "11. Stash"]),
                   ("00-审核说明.md", ["247 → 254 项", "100 → 104 类", "12 → 13 条", "364 → 222", "注入 104 类", "都在 2026-10-07（UTC）",
                                       "handoff/notes/r14_policy_order.out"]),
                   ("docs/05-验收记录.md", ["254 项全部通过", "注入 104 类错误", "2026.10.07-1（r14", "Python 3.13.16，PyYAML 6.0.1", "2283 个假节点",
                                            "860 个 120 / 400 个字符", "4,531 个字段", "260 个目标", "只定稿这一次", state, "mihomo 13 条",
                                            f"`tests/test_real_data.py`，{per_file['test_real_data']} 项", f"`tests/test_strict.py`，{per_file['test_strict']} 项",
                                            "google.cn` AAAA → 空应答", "222,593 个里走代理组的 222 个", "官方内核核对了其中 432 个",
                                            "105,317 条（94.6%）", "**出站时的解析**（r14 新增"]),
                   ("docs/02-语法依据与能力矩阵.md", ["宽的 13.0–15.7 KB，严的 11.8–15.1 KB", "`tests/test_regions.py` 65 项", "v1.19.20", "13 条 DNS 去向",
                                                    "## Loon / Quantumult X 严格版用到的写法（2026-10-06）", "ExampleRule.lsr",
                                                    "| 代理出口转发 UDP、经 WireGuard 这类出口时，会不会在本机解析目标域名"]),
                   ("docs/03-DNS决策表.md", ["## 走代理的域名不交给国内 DNS：三项固定核对与逐条扫描（2026-10-06；2026-10-07 修订）",
                                            "## 客户端这一侧：哪些设置会让上面的设计不成立（2026-10-06；2026-10-07 补充）", "`system` 指的是谁",
                                            "fake-ip-range6", "## 出站时的解析：代理出口会不会再解析目标（2026-10-07，r14）",
                                            "| mihomo（r14） | 224,266 个", "105,317 条", "49 个顶级域", "110,712 条", "187 条 IP 段", "v0.4.24"]),
                   ("docs/06-已知限制与待决事项.md", ["| 14 | 不带点的名字", "| 20 | Quantumult X 的 `[dns]` 要不要加 `no-system`",
                                                    "## 2026-10-07（r13）：处理 GPT 对 r12 的审核时新写明的限制", "105,317 条（94.6%）"]),
                   ("docs/08-外部审核记录.md", ["## 第 9 轮", "247 → 254 项", "100 → 104 类", "docs/evidence/gpt-r13/", "r14_policy_order.out",
                                              "## 第 8 轮：2026-10-06，GPT 审核 r12（交付包）", "## 第 7 轮：2026-10-06，GPT 对做法的两段意见"]),
                   ("docs/09-真机验收操作清单.md", ["DNS 覆写", "## 1b. 严格版", "| 13. 换个网络再看一次（可选）", "Mac 上开着虚拟网卡时一定要试这一下",
                                                   "courier-push-apple.com.akadns.net"]),
                   ("docs/01-导入、更新、诊断与回滚.md", ["DNS 覆写", "v1.19.20", "## 每个客户端要手动确认的开关（2026-10-06）", "f250126", "2001:2::"]),
                   ("docs/07-需求对照.md", ["### 2026-10-07（GPT 审核 r13 之后，r14）", "cd63eba", "49 个", "mihomo 13 条"]),
                   ("docs/00-需求原文.md", ["在已经完成的基础上继续", "按这个做", "## 补充（2026-10-07，GPT 审核 r12 之后，对话中给出，照录）",
                                           "先读 CLAUDE.md 和 handoff/README.md，照里面说的搭好检查环境并确认全部检查通过。",
                                           "改 另外新增一个需求 stash 配置文件 你可以弄好 clah 再写 stash 的配置 两者接近"])):
    s = read(p)
    for n in needles:
        assert n in s, (p, n)
# 旧的说法不应再作为现状出现（历史记录里的除外，逐个看过）
HIST = ["docs/00-需求原文.md", "docs/08-外部审核记录.md"]
stale = {"247 项全部通过": [], "注入 100 类": [], "tests-247": [], "自动测试 247 项": [], "247 automated": [], "再跑一次 247 项": [], "确认 247 项通过": [],
         "100 类全部被发现": ["docs/08-外部审核记录.md"],
         "mihomo 12 条": ["docs/08-外部审核记录.md"], "查询 12 条": [], "12 条 DNS 去向": [], "mihomo 的 11 条": ["docs/08-外部审核记录.md"],
         "qwen.ai` TXT → 国内（已知限制的现状）": [],
         "222,733 个里 364 个": ["docs/05-验收记录.md"], "222,733 个里走代理组的 364 个": [], "核对了其中 574 个": [], "跑了其中 574 个": [], "mihomo 574 个": [],
         "对应统一源 2026.10.06-1（r13）": [], "（r13；与 r12 相同": [], "统一源 2026.10.06-1（r13）　生成器": [],
         "按旧的办法会算错": [], "按旧办法会算错": [],
         "sing-box 1.14.1 / 1.12.0 实测": [], "sing-box 1.14.1、1.12.0 实测": [],
         "只在 Loon 严格版直连；": [],
         "（系统 DNS，即路由器": ["docs/08-外部审核记录.md"], "系统 DNS（路由器 / 公司内网的 DNS）": [], "写在配置文件里不起作用，只能在这里开": [],
         "境外 DNS 连不上时，内核没有转去问": ["docs/08-外部审核记录.md"], "只能在 App 里开**": [],
         "没有逐行比过": ["docs/08-外部审核记录.md"]}     # docs/08 第 8 轮第 6 点引用这句旧话，说明它被换掉了（核对时看过）
# docs/08 第 9 轮“我自己的错”第 5 条引用 r13 的“mihomo 的 11 条”；docs/05 的“（r13 是 222,733 个里 364 个）”是对比旧数（2026-10-07 核对时看过）
for p in files:
    s = read(p)
    for k, allowed in stale.items():
        if k in s and p not in allowed:
            raise AssertionError(f"{p} 里还有旧的说法：{k}")
    # “全集”只能出现在说明旧名字的地方
    if p not in HIST:
        for mm in re.finditer("全集", s):
            ctx = s[max(0, mm.start() - 8):mm.start() + 12]
            assert re.search(r"叫(它)?“全集|“全集一致性”改名|“全集一致性”→|原“全集", ctx), (p, ctx)
print("核对通过")
