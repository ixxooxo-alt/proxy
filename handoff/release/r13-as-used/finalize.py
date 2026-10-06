"""把文档里的占位符 ⟦…⟧ 换成最终运行得到的数字，并核对文档里写的数字和日志、产物一致（r13 用的；照 r12-as-used/finalize.py 改的）。
数字都从日志和产物里读。用法（在工程根目录）：python3 handoff/release/r13-as-used/finalize.py <变异日志目录> [--dry]"""
import datetime, json, os, re, subprocess, sys

D = os.path.abspath(sys.argv[1])
dry = "--dry" in sys.argv
ev = "docs/evidence"
RUN_DAY = "2026-10-06"
DIGEST = "3390e37f8d26dbbbe4016d2b94320c1ee08eb7779862dcdd289d117dfd4a3349"     # 与 r12 相同：source/、generator/、build.py 没有改
N_TESTS, N_MUT, N_MIHOMO_DNS = "247", 100, "12"
ENV = "Python：Python 3.13.16，PyYAML：6.0.1"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


man = json.load(open("dist/manifest.json", encoding="utf-8"))
digest = man["source_sha256"]
assert man["source_version"] == "2026.10.06-1" and man["generator_version"] == "1.5.0", man
assert digest == DIGEST, digest
freeze = read(os.path.expanduser("~/proxy-work/freeze-time.txt")).strip()          # 定稿时记下的时间（UTC）
state = subprocess.run(["bash", "handoff/release/code_state.sh"], capture_output=True, text=True, check=True).stdout.strip()
assert state == read(os.path.expanduser("~/proxy-work/freeze-state.txt")).strip(), "代码在定稿之后变过"
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
          "test_each_kind_of_reply_is_told_apart"):
    assert re.search(rf"^{t} \(.*\) \.\.\.", tests, re.M) or f"{t} (" in tests, t
assert "DeprecationWarning" not in tests

icu = read(f"{ev}/icu-check.log")
assert "13 条（宽 7 条、严 6 条）× 2283 个节点名（其中 625 个有手写的期望）" in icu
assert "× 2306 个节点名" in icu
m = re.search(r"ICU 平均每次匹配：宽 (\d+) 微秒、严 (\d+) 微秒.*?Loon (\d+) 毫秒，Quantumult X（26 个策略各一条）(\d+) 毫秒", icu)
assert m, "icu-check.log 里没有耗时行"
icu_time = (f"这次运行 ICU 平均每次匹配：宽的 {m.group(1)} 微秒、严的 {m.group(2)} 微秒（含调用开销）；按 300 个节点估算 Loon 约 {m.group(3)} 毫秒、"
            f"Quantumult X 约 {m.group(4)} 毫秒（每次运行有出入，这台机器和 r12 的不是同一台：r12 那次是 29 / 51 毫秒，r10 时几次运行是 36–38 / 63–66 毫秒；手机会慢几倍）")
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
assert rr.count(f"连接 6 条、查询 {N_MIHOMO_DNS} 条，收到查询的替身与正常那一遍完全相同；其中 4 条只有境外替身收到") == 1
assert rr.count("连接 6 条、查询 22 条，收到查询的替身与正常那一遍完全相同；其中 6 条只有境外替身收到") == 2
assert "[不符合]" not in rr and "\n全部一致\n" in rr and "处不一致" not in rr and "全集" not in rr
for needle in ("node gateway.lan → system", "node homeproxy → system", "direct nas.lan → system", "printer.lan A → system",
               "www.taobao.com A → fake-ip", "printer A → domestic（已知限制的现状，见 docs/06）",
               "chatgpt.com A → fake-ip", "api.openai.com HTTPS → empty", "claude.ai TXT → foreign", "never-listed-query.net A → fake-ip",
               "never-listed-txt.net TXT → foreign", "www.qq.com TXT → domestic", "google.cn AAAA → empty",
               "qwen.ai TXT → domestic（已知限制的现状，见 docs/06）",
               "proxied www.youtube.com → none", "proxied gemini.google.com → none", "proxied chat.qwen.ai → none",
               "unlisted never-listed-site.org → foreign", "unlisted r1.test.dnsleaktest.com → foreign",
               "unlisted never-listed-site.org → dns-foreign", "unlisted r1.test.dnsleaktest.com → dns-foreign",
               "国内 DNS 与路由的逐条扫描", "mihomo：扫了 224266 个代表主机",
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

snap = json.load(open("tests/data/real_sets.json", encoding="utf-8"))
assert snap["generated"] == RUN_DAY and snap["source_version"] == "2026.10.06-1", (snap["generated"], snap["source_version"])
mh = snap["official"]["mihomo"]
assert mh["dial"]["node gateway.lan"] == "system" and mh["dns"]["printer A"] == "domestic" and len(mh["dial_sha256"]) == 64
assert mh["dns"]["google.cn AAAA"] == "empty" and mh["dns_foreign_silent"]["google.cn AAAA"] == "empty"
assert mh["dial"]["proxied www.youtube.com"] == "none" and mh["dial"]["unlisted never-listed-site.org"] == "foreign"
assert len(snap["sizes"]["loon"]) == 3 and all(v["ip_resolving"] == 0 for v in snap["sizes"]["loon"].values())
cons = snap["consistency"]
assert len(cons["mihomo"]["mismatch"]) == 364 and len(cons["singbox"]["mismatch"]) == 5 and len(cons["singbox112"]["mismatch"]) == 5
assert len(snap["hosts"]) == 256 and len(snap["ips"]) == 28
assert "逐条扫描" in snap["about"] and "全集" not in snap["about"]

cmp12 = read(f"{ev}/与上一版的对比.md")
assert cmp12.startswith("# 版本对比：r12 → r13\n"), cmp12[:40]
assert "| r12 | 625 | 0 | 625 | 0 |" in cmp12 and "| r13 | 625 | 0 | 625 | 0 |" in cmp12
assert "共 2247 个名字" in cmp12 and "### 手动组的归属变了（0 个）" in cmp12 and "成员变了（0 个）" in cmp12
assert cmp12.count("逐字节相同。") == 8, cmp12.count("逐字节相同。")
assert cmp12.count("和 r12 的一模一样。") == 3
for needle in ("## 六、严格版", "大小：标准版 240,438 字节，严格版 242,175 字节", "大小：标准版 403,167 字节，严格版 405,351 字节",
               "- 新增：`GEOIP,CN,国内直连,no-resolve`", "- 删除：`GEOIP,CN,国内直连`",
               "`loon/rules/cn-domains.list`：165,603 字节，规则 6,132 条（DOMAIN 12、DOMAIN-SUFFIX 6,120）",
               "`quantumultx/rules/cn-domains.list`：196,295 字节，规则 6,132 条（HOST 12、HOST-SUFFIX 6,120）",
               "`quantumultx/rules/domain-fallback.list`：629 字节，规则 1 条（HOST-KEYWORD 1）"):
    assert needle in cmp12, needle
cmp7 = read(f"{ev}/与r7的对比.md")
assert cmp7.startswith("# 版本对比：r7 → r13\n"), cmp7[:40]
assert "| r7 | 578 | 47 | 534 | 91 |" in cmp7 and "| r13 | 625 | 0 | 625 | 0 |" in cmp7
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
    how = "r13 定稿以后一次跑完，两批并行"
else:
    window = "两批并行，分 " + str(len(segs)) + " 段：" + "；".join(
        f"{s['start'][11:16]}–{s['end'][11:16]} UTC 跑完 {len(s['ids'])} 类" for s in segs) + "；前面的段被工作环境重启打断，段与段之间代码没有改动"
    how = f"r13 定稿以后分 {len(segs)} 段跑完（工作环境中途重启过），段与段之间代码没有改动"
fresh = res["fresh"]
assert fresh["solo"] == [], fresh
for name, test in (("M91", "test_mihomo_unmatched_names_ask_only_the_foreign_doh"), ("M92", "test_singbox_unmatched_names_ask_only_dns_foreign"),
                   ("M99", "test_singbox_unmatched_names_ask_only_dns_foreign"), ("M100", "test_each_kind_of_reply_is_told_apart")):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] {name} "))
    assert test in l and "输出含预期信息" in l, l[:300]
for i in list(range(71, N_MUT + 1)):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] M{i} "))
    if f"M{i}" not in res["not_seen"]:
        assert "输出含预期信息" in l, l[:200]
assert "DeprecationWarning" not in mut
partial_names = sorted(x for v in res["partial"].values() for x in v)
print("部分运行的：", res["partial"], "；未见预期信息：", res["not_seen"])
assert partial_names == sorted(["M6", "M9", "M31", "M89", "M90"]), res["partial"]
PARTIAL_TEXT = ("“恢复关键词 siri”“azure.com 放回 Microsoft”“用回肯定前瞻”和国内域名清单数据文件被改坏的两类（M89、M90）由统一源校验直接拒绝（生成器不肯生成，测试大面积报错）；"
                "严格版的结构被改坏的几类（M76–M78、M80–M82）和“清空 `proxy-server-nameserver`”被写盘前的检查拦住，生成流程的那批测试因此失败，同时另有路由用例失败；"
                "“图标登记里漏了 Apple Push”在生成时直接报错；")
mut_cell = (f"{N_MUT} 类全部被发现，都是 r13 定稿（{freeze[:16]} UTC）以后在上面这个摘要、这个代码状态的代码上跑的（{window}）。"
            "“记录对应现在的配置”那两项——规则与 DNS 两段的摘要、拨号摘要——对改了规则、DNS 或出站的变异都会报："
            f"{N_MUT} 类里前一项报了 {len(fresh['with']['routing'])} 类、后一项报了 {len(fresh['with']['dial'])} 类；**只靠这两项发现的一类都没有了**——"
            "r12 时 M91、M92（mihomo 默认的 DNS 换成国内的、sing-box 路由里的 `resolve` 改用国内 DNS）只靠它们，这一版补了静态断言，"
            "M91、M92 和新加的 M99（sing-box 的境外 DNS 不再经国外默认发出）都由 `tests/test_dns_lan.py` 的两项直接发现；"
            "M100（核对工具又只读 A 记录）由 `tests/test_real_data.py` 的 `ProbeReplyParsing` 发现。"
            "M45（回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，"
            "那一项把匹配放在带超时的子进程里，等满 5 分钟后失败并给出提示。" + PARTIAL_TEXT + "其余由对应的测试发现，每一类的失败项见日志")

probe = read("handoff/notes/r12_review_probes.out")
for needle in ("6/6 与审核方的结果相同", "product_cn 142 个", "A    ：fake-ip 142 个", "AAAA ：empty 142 个", "HTTPS：empty 142 个",
               "qwen.ai 的 TXT：domestic", "product_cn 142 个，AAAA ：假 IPv6 地址（2001:2::0/64 里的） 142 个",
               "product_cn 142 个，AAAA ：empty 142 个"):
    assert needle in probe, needle
assert probe.count("product_cn 142 个，HTTPS：empty 142 个") == 2
before = read("handoff/notes/r12_review_probes.before-fix.out")
assert before.count("product_cn 142 个，AAAA ：empty 142 个") == 2, "修之前那次两遍都报了空应答"
probe_cell = ("审核报告第二节第 7 条：6 个节点服务器名字交给哪一类 DNS，6 个都与审核方的结果相同。第 8 条：快照里归为 product_cn 的 142 个主机，"
              "交付的配置下 A 全是假地址，AAAA、HTTPS 全是空应答，三类替身都没有收到；`qwen.ai` 的 TXT 交给国内 DNS——与审核方的复测相同。"
              "第三节第 4 点：托管版配置照 Clash Verge Rev v2.5.7 开虚拟网卡的改法改两处（`dns.ipv6: true`、`fake-ip-range6: 2001:2::0/64`），"
              "带内核认的 `SKIP_SYSTEM_IPV6_CHECK=1`（当作有公网 IPv6）时，142 个主机的 AAAA 都拿到 `2001:2::` 开头的假地址，HTTPS 仍空，替身都没有收到；"
              "不带（这台机器没有公网 IPv6）时 AAAA 仍空。修核对工具之前跑的同一个实验，两遍都报“AAAA 空应答 142 个”——这就是那个缺陷")

values = {"ICU_TIME": icu_time, "LONG_TIME": long_time, "FIELDS": fields, "MUT_CELL": mut_cell, "PROBE_CELL": probe_cell,
          "tests_n": N_TESTS, "mut_n": str(N_MUT), "mihomo_dns_n": N_MIHOMO_DNS, "code_state": state, "freeze_utc": freeze[:16],
          "mut_window": window, "checks_window": checks_window,
          "run_window": f"{RUN_DAY}（UTC）", "run_day_en": RUN_DAY}

# 产物大小、摘要与文档里写的一致（与 r12 相同）
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
# dist/ 与 r12 的提交逐字节相同
r12 = subprocess.run(["git", "diff", "--stat", "beae635", "--", "dist"], capture_output=True, text=True, check=True).stdout
assert r12.strip() == "", r12

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
for p, needles in (("README.md", ["tests-247%20passing", "247 automated tests", "2026.10.06-1", "This is r13", "Eight rounds of external input",
                                  "625 hand-labelled", "12–16 KB", "43 service groups", "82 policy groups", "260 targets", "loon-strict.conf"]),
                   ("README.zh-CN.md", ["自动测试 247 项", "2026.10.06-1", "（r13；配置与 r12 逐字节相同", "625 个人工写期望", "2283 个假节点", "每条 12–16 KB",
                                        "外部意见一共 8 轮", "82 个策略组", "260 个目标", "mihomo 12 条", "17,679 个代表主机里 5 个", "222,733 个里 364 个", "Python 3.13.16"]),
                   ("PROJECT_STATE.md", ["247 项", "r13：统一源 2026.10.06-1", "生成器 1.5.0", "T24 第 8 轮", "100 类全部被发现", "需求决定项 20 项"]),
                   ("00-审核说明.md", ["244 → 247 项", "98 → 100 类", "11 → 12 条", "本轮（r13，统一源 2026.10.06-1）", "注入 100 类错误", "都在 2026-10-06（UTC）"]),
                   ("docs/05-验收记录.md", ["247 项全部通过", "100 类错误", "2026.10.06-1（r13", "Python 3.13.16，PyYAML 6.0.1", "2283 个假节点",
                                            "860 个 120 / 400 个字符", "4,531 个字段", "260 个目标", "只定稿这一次", state,
                                            "`tests/test_real_data.py`，35 项", "`tests/test_strict.py`，30 项", "google.cn` AAAA → 空应答"]),
                   ("docs/02-语法依据与能力矩阵.md", ["宽的 13.0–15.7 KB，严的 11.8–15.1 KB", "`tests/test_regions.py` 65 项", "v1.19.20", "12 条 DNS 去向",
                                                    "## Loon / Quantumult X 严格版用到的写法（2026-10-06）", "ExampleRule.lsr"]),
                   ("docs/03-DNS决策表.md", ["## 走代理的域名不交给国内 DNS：三项固定核对与逐条扫描（2026-10-06；2026-10-07 修订）",
                                            "## 客户端这一侧：哪些设置会让上面的设计不成立（2026-10-06；2026-10-07 补充）", "`system` 指的是谁",
                                            "fake-ip-range6", "查询 12 条，其中 4 条只有境外替身收到", "第 ③ 项能说明的只有这些", "105,446 条（94.8%）",
                                            "49 个顶级域", "110,712 条", "187 条 IP 段", "v0.4.24"]),
                   ("docs/06-已知限制与待决事项.md", ["| 14 | 不带点的名字", "| 20 | Quantumult X 的 `[dns]` 要不要加 `no-system`",
                                                    "## 2026-10-07（r13）：处理 GPT 对 r12 的审核时新写明的限制", "105,446 条（94.8%）"]),
                   ("docs/08-外部审核记录.md", ["## 第 8 轮：2026-10-06，GPT 审核 r12（交付包）", "244 → 247 项", "98 → 100 类", "docs/evidence/gpt-r12/",
                                              "### 补充：Apple Push 的 DNS 别名（2026-10-07，用户贴来的一段）",
                                              "## 第 7 轮：2026-10-06，GPT 对做法的两段意见"]),
                   ("docs/09-真机验收操作清单.md", ["DNS 覆写", "## 1b. 严格版", "| 13. 换个网络再看一次（可选）", "Mac 上开着虚拟网卡时一定要试这一下",
                                                   "courier-push-apple.com.akadns.net"]),
                   ("docs/01-导入、更新、诊断与回滚.md", ["DNS 覆写", "v1.19.20", "## 每个客户端要手动确认的开关（2026-10-06）", "f250126", "2001:2::"]),
                   ("docs/07-需求对照.md", ["### 2026-10-07（GPT 审核 r12 之后，r13）", "cd63eba", "49 个", "mihomo 12 条"]),
                   ("docs/00-需求原文.md", ["在已经完成的基础上继续", "按这个做", "## 补充（2026-10-07，GPT 审核 r12 之后，对话中给出，照录）",
                                           "先读 CLAUDE.md 和 handoff/README.md，照里面说的搭好检查环境并确认全部检查通过。"])):
    s = read(p)
    for n in needles:
        assert n in s, (p, n)
# 旧的说法不应再作为现状出现（历史记录里的除外，逐个看过）
HIST = ["docs/00-需求原文.md", "docs/08-外部审核记录.md"]
stale = {"244 项全部通过": [], "注入 98 类": [], "tests-244": [], "自动测试 244 项": [], "244 automated": [], "98 类全部被发现": ["docs/08-外部审核记录.md"],
         "mihomo 11 条": ["docs/08-外部审核记录.md"], "查询 11 条": [], "11 条 DNS 去向": [],
         "（系统 DNS，即路由器": ["docs/08-外部审核记录.md"], "系统 DNS（路由器 / 公司内网的 DNS）": [], "写在配置文件里不起作用，只能在这里开": [],
         "境外 DNS 连不上时，内核没有转去问": ["docs/08-外部审核记录.md"], "只能在 App 里开**": [],
         "对应统一源 2026.10.06-1（r12）": [], "这一版（r12）是 `2026.10.06-1`": [],
         "统一源 2026.10.06-1（r12）　生成器": [], "没有逐行比过": []}
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
