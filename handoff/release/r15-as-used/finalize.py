"""把文档里的占位符 ⟦…⟧ 换成最终运行得到的数字，并核对文档里写的数字和日志、产物一致（r15 用的；照 r14-as-used/finalize.py 改的）。
r15 处理 GPT 对 r14 的审核；代码定稿一次（2026-10-13 03:56）；变异检查被工作环境重新启动打断过一次，分两段跑完。
数字都从日志和产物里读。用法（在工程根目录）：python3 handoff/release/r15-as-used/finalize.py <变异日志目录> [--dry]"""
import datetime, json, os, re, subprocess, sys

D = os.path.abspath(sys.argv[1])
dry = "--dry" in sys.argv
ev = "docs/evidence"
RUN_DAY = "2026-10-13"                                                            # 全部检查、一次性核对、快照、变异检查都在这一天
MUT_DAYS = ("2026-10-13", "2026-10-13")       # 变异检查分两段：04:23 前后工作环境重新启动，第一段停下；05:11 起跑剩下的
DIGEST = "a8c850f9865a0dd12f4820deb9eb08a67cd12f80202a7e07054806a45612b8e2"     # r15：生成器 1.8.0、统一源 2026.10.13-1
N_TESTS, N_MUT, N_MIHOMO_DNS = "266", 122, "15"
ENV = "Python：Python 3.13.16，PyYAML：6.0.1"
R14 = "3f45668"                                                                   # GPT 审的 r14
W = os.path.expanduser("~/proxy-work")

# ---- 这一版特有的说法（从日志里读到以后照抄；下面的断言核对它们确实在日志 / 报告里）----
RR_RESOLVED, RR_RESOLVED_STD = "261", "43"                                      # 为了判断 IP 规则而在本机解析过的域名：总数、标准版里解析了的
RR_OUTBOUND = (                                                                  # 出站核对、节点收到的目标、组切换以后（照日志原文）
    "[符合] 出站时的解析 8 个主机 × 3 种出口（走代理的组换成 SOCKS5 走 TCP、SOCKS5 走 UDP、WireGuard 走 TCP；SOCKS5 出口连本机的 SOCKS5 接收端，WireGuard 出口连本机空端口；none = 三类替身都没有收到）：官方内核与人工期望一致",
    "qwen.ai：socks5-tcp → none，节点收到 domain，socks5-udp → foreign，节点收到 ip，wireguard-tcp → foreign",
    "download.microsoft.com：socks5-tcp → none，节点收到 domain，socks5-udp → foreign，节点收到 ip，wireguard-tcp → foreign",
    "chatgpt.com：socks5-tcp → none，节点收到 domain，socks5-udp → foreign，节点收到 ip，wireguard-tcp → foreign",
    "never-listed-site.org：socks5-tcp → foreign，节点收到 domain，socks5-udp → foreign，节点收到 ip，wireguard-tcp → foreign",
    "www.qq.com：socks5-tcp → domestic，节点收到 -，socks5-udp → domestic，节点收到 -，wireguard-tcp → domestic",
    "www.apple.com：socks5-tcp → domestic，节点收到 -，socks5-udp → domestic，节点收到 -，wireguard-tcp → domestic",
    "tlu.dl.delivery.mp.microsoft.com：socks5-tcp → domestic，节点收到 -，socks5-udp → domestic，节点收到 -，wireguard-tcp → domestic",
    "time.windows.com：socks5-tcp → domestic，节点收到 -，socks5-udp → domestic，节点收到 -，wireguard-tcp → domestic",
    "[符合] 默认直连的组切到代理以后 4 个主机 × 3 种出口（走代理的组换成 SOCKS5 走 TCP、SOCKS5 走 UDP、WireGuard 走 TCP；SOCKS5 出口连本机的 SOCKS5 接收端，WireGuard 出口连本机空端口；none = 三类替身都没有收到）：官方内核与人工期望一致",
    "www.apple.com：socks5-tcp → none，节点收到 domain，socks5-udp → foreign，节点收到 ip，wireguard-tcp → foreign",
    "www.apple.com.cn：socks5-tcp → none，节点收到 domain，socks5-udp → domestic（已知限制的现状，见 docs/06），节点收到 ip，wireguard-tcp → domestic（已知限制的现状，见 docs/06）",
    "api.bilibili.com：socks5-tcp → none，节点收到 domain，socks5-udp → domestic（已知限制的现状，见 docs/06），节点收到 ip，wireguard-tcp → domestic（已知限制的现状，见 docs/06）",
    "自检：去掉 nameserver-policy 里走代理组的产品域名那一层后，wireguard-tcp 下 download.microsoft.com → domestic、qwen.ai → domestic——只有这一类变回国内 DNS，这一层仍然需要",
    "自检：去掉 nameserver-policy 里走代理组的产品域名那一层后，socks5-udp 下 download.microsoft.com → domestic、qwen.ai → domestic——只有这一类变回国内 DNS，这一层仍然需要")
RR_OUTBOUND_COUNTS = {                                                            # sing-box 两个版本各一遍：哪些行两遍都有、哪些只在一个版本里
    "[符合] 出站时的解析 8 个主机 × 3 种出口（走代理的组换成 SOCKS 走 TCP、SOCKS 走 UDP、WireGuard 端点走 TCP；SOCKS 出口连本机的 SOCKS5 接收端）：官方内核与人工期望一致": 2,
    "[符合] 默认直连的组切到代理以后 4 个主机 × 3 种出口（走代理的组换成 SOCKS 走 TCP、SOCKS 走 UDP、WireGuard 端点走 TCP；SOCKS 出口连本机的 SOCKS5 接收端）：官方内核与人工期望一致": 2,
    "qwen.ai：socks-tcp → none，节点收到 domain，socks-udp → none，节点收到 -（现状：内核没有发出，见 docs/06），wireguard-tcp → dns-foreign": 1,   # 1.14.1
    "qwen.ai：socks-tcp → none，节点收到 domain，socks-udp → none，节点收到 domain，wireguard-tcp → dns-foreign": 1,                                # 1.12.0
    "api.bilibili.com：socks-tcp → none，节点收到 domain，socks-udp → none，节点收到 -（现状：内核没有发出，见 docs/06），wireguard-tcp → dns-foreign": 1,
    "api.bilibili.com：socks-tcp → none，节点收到 domain，socks-udp → none，节点收到 domain，wireguard-tcp → dns-foreign": 1,
    "never-listed-site.org：socks-tcp → dns-foreign，节点收到 ip，socks-udp → dns-foreign，节点收到 ip，wireguard-tcp → dns-foreign": 2,
    "time.windows.com：socks-tcp → dns-cn，节点收到 -，socks-udp → dns-cn，节点收到 -，wireguard-tcp → dns-cn": 2,
    "www.qq.com：socks-tcp → dns-cn，节点收到 -，socks-udp → dns-cn，节点收到 -，wireguard-tcp → dns-cn": 4,                                       # 出站、组切换以后两段 × 两个版本
}
UE_NEEDLE = "核对域名规则 856 条，社区来源 561 条；产品规则下的上游广告条目 48 条；更宽的广告条目 0 条"
CMP_NEEDLES = ("大小：241,939 → 241,985 字节。", "大小：404,459 → 404,505 字节。", "大小：280,272 → 280,322 字节。", "大小：280,455 → 280,505 字节。",
               "大小：79,132 → 79,164 字节。", "大小：79,158 → 79,190 字节。", "大小：243,271 → 243,317 字节。", "大小：406,436 → 406,482 字节。",
               "**Rule**：新增 1 条，删除 0 条，改动 0 条；两版都有的条目顺序不变。", "- 新增：`DOMAIN-SUFFIX,afpapi.alimama.com,广告拦截`",
               "**filter_local**：新增 1 条，删除 0 条，改动 0 条；两版都有的条目顺序不变。", "- 新增：`host-suffix, afpapi.alimama.com, 广告拦截`",
               "**规则（rules）**：新增 1 条，删除 0 条，改动 0 条；两版都有的条目顺序不变。",
               "**路由规则（route.rules）**：新增 0 条，删除 0 条，改动 1 条；两版都有的条目顺序不变。", "：加上 `\"afpapi.alimama.com\"`",
               "没有变化的分段：DNS（dns）（14 条）、策略组（proxy-groups）（81 条）、其余设置（13 条）。",
               "没有变化的分段：DNS（dns）（14 条）、策略组（proxy-groups）（81 条）、其余设置（18 条）。",
               "没有变化的分段：DNS 服务器（dns.servers）（4 条）、DNS 规则（dns.rules）（9 条）、规则集（route.rule_set）（5 条）、出站与策略组（outbounds）（64 条）",
               "## 六、严格版", "大小：标准版 241,985 字节，严格版 243,317 字节", "大小：标准版 404,505 字节，严格版 406,482 字节",
               "- 新增：`GEOIP,CN,国内直连,no-resolve`", "- 删除：`GEOIP,CN,国内直连`",
               "`loon/rules/cn-domains.list`：165,629 字节，规则 6,133 条（DOMAIN 12、DOMAIN-SUFFIX 6,121）。和 r14 的一模一样。",
               "`quantumultx/rules/cn-domains.list`：196,326 字节，规则 6,133 条（HOST 12、HOST-SUFFIX 6,121）。和 r14 的一模一样。",
               "`quantumultx/rules/cn-domains-max.list`：3,521,641 字节，规则 111,182 条（HOST 252、HOST-SUFFIX 110,930）。和 r14 相比：新增 0 条、删除 0 条（规则相同，只有注释不同）。",
               "`quantumultx/rules/domain-fallback.list`：629 字节，规则 1 条（HOST-KEYWORD 1）。和 r14 的一模一样。")
CMP_CELL = ("八份配置都只多了一条拦截规则 `afpapi.alimama.com`（Loon、Quantumult X、mihomo 是新增的一条规则；sing-box 是拦截的那条路由规则里多一个后缀）和注释里的版本号，"
            "策略组、DNS（mihomo 的 `nameserver-policy`、sing-box 的 DNS 规则）、规则集都没有变；大清单副本的规则相同、只有注释不同（文件头多一行：本项目改了什么、哪天改的、GPL-2.0 原文的地址）；"
            "两份自有清单和域名兜底文件和 r14 的一模一样")
MUT_R15 = {}                                                                      # M119–M122 → 发现它的那一项测试（照变异日志）
MUT_R15_TEXT = ""
R15_REAL_CELL = ("路由 270 个目标（r14 是 269 个，多了 `afpapi.alimama.com`）在 mihomo v1.19.31、sing-box v1.14.1 与 v1.12.0 上都与人工期望一致；"
                 "出站时的解析：8 个主机 × mihomo 三种出口、sing-box 三种出口（两个版本），SOCKS 那几种另核对节点收到的目标；默认直连的组切到代理以后 4 个主机 × 同样的出口——都与人工期望一致"
                 "（sing-box 1.14.1 经 SOCKS 走 UDP 那一格按现状写成“节点没收到”，mihomo 上 `www.apple.com.cn`、`api.bilibili.com` 切到代理以后经 UDP、WireGuard 问国内 DNS 那几格写成现状）；"
                 "去掉产品域名那一层的自检在 WireGuard 走 TCP、SOCKS5 走 UDP 下都看得见；逐条扫描两个内核走代理组的仍是 0 个（`docs/evidence/real-route-check.log`）")
H8 = "docs/08-外部审核记录.md"
DOC_NEEDLES_R15 = (
    ("README.md", ["tests-266%20passing", "266 automated tests", "2026.10.13-1", "This is r15", "625 hand-labelled", "12–16 KB",
                   "43 service groups", "81 policy groups", "270 targets", "loon-strict.conf", "15 on mihomo", "561 community-sourced",
                   "Ten rounds of external input", "unsupported address", "tests were run on Linux (Python 3.13) in a cloud session on 2026-10-13 (UTC)"]),
    ("README.zh-CN.md", ["自动测试 266 项", "2026.10.13-1", "（r15：处理 GPT 对 r14 的审核", "625 个人工写期望", "2283 个假节点",
                         "每条 12–16 KB", "81 个策略组", "270 个目标", "mihomo 15 条", "r14 起两个内核都是 0 个", "Python 3.13.16",
                         "561 条社区来源规则", "外部意见一共 10 轮", "这一版的检查是 2026-10-13（UTC）在云端会话里跑的", "sing-box 17,701 个代表主机"]),
    ("PROJECT_STATE.md", ["266 项", "r15：统一源 2026.10.13-1", "生成器 1.8.0", "T28 第 10 轮", "122 类全部被发现", "第 21 项 2026-10-13 定了（维持现状）", "11. Stash",
                          "确认 266 项通过", "`2026.10.13-1` 是 r15"]),
    ("00-审核说明.md", ["## 本轮（r15，统一源 2026.10.13-1）改了什么", "259 → 266 项", "118 → 122 类", "269 → 270 个", "注入 122 类",
                        "都在 2026-10-13（UTC）", "代码 2026-10-13 03:56 UTC 定稿", "handoff/notes/r14_review_probes.out", "## 本轮请重点看",
                        "--old-label r14 --new-label r15"]),
    ("docs/05-验收记录.md", ["266 项全部通过", "注入 122 类错误", "2026.10.13-1（r15", "Python 3.13.16，PyYAML 6.0.1", "2283 个假节点",
                             "860 个 120 / 400 个字符", "270 个目标", "03:56 定稿", "mihomo 15 条", "`tests/test_real_data.py`，45 项", "`tests/test_strict.py`，33 项",
                             "`tests/test_compare_versions.py`，13 项", "222,353 个里走代理组的 0 个", "官方内核核对了其中 214 个", "81 个策略组", "6,949,624 字节",
                             "111,182 条", "自有拦截 98", "122 类全部被发现", "与上一版（r14）对比", "GPT 审核 r14 给待决事项第 21 项的做法"]),
    ("docs/02-语法依据与能力矩阵.md", ["270 个目标", "81 个策略组", "6,949,624 字节", "`cn-domains-max.list`", "**1.14.1 没有发出**", "`tests/test_regions.py` 65 项",
                                     "v1.19.20", "## Loon / Quantumult X 严格版用到的写法（2026-10-06）", "ExampleRule.lsr"]),
    ("docs/03-DNS决策表.md", ["| mihomo | 224,087 个", "| sing-box（两个版本相同） | 19,548 个代表主机", "290 条用例和排除项", "现在 732 条", "111,047 条",
                             "6,133 条", "653 个后缀", "1.14.1 没有发出这个包", "## 出站时的解析：代理出口会不会再解析目标（2026-10-07，r14）",
                             "**节点收到的到底是什么**", "`system` 指的是谁", "187 条 IP 段", "49 个顶级域", "110,712 条"]),
    ("docs/06-已知限制与待决事项.md", ["## 2026-10-13（r15）：处理 GPT 对 r14 的审核", "自有拦截另有 98 条", "| 21 | 默认直连、可以切到代理的组", "③",
                                      "## 2026-10-13 你定下的事项", "| ① 维持现状 | **配置不变**",
                                      "| 17 | 把“国内直连”组切到“国外默认”以后", "## 2026-10-07 你定下的事项", "870 条服务规则", "105,317 条"]),
    (H8, ["## 第 10 轮：2026-10-13，GPT 审核 r14", "259 → 266 项", "118 → 122 类", "docs/evidence/gpt-r14/", "r14_review_probes.out", "## 第 9 轮", "270 个目标"]),
    ("docs/09-真机验收操作清单.md", ["对应统一源 2026.10.13-1", "81 个策略组", "111,182 条", "unsupported address", "## 1b. 严格版", "afpapi.alimama.com",
                                     "courier-push-apple.com.akadns.net"]),
    ("docs/01-导入、更新、诊断与回滚.md", ["2026.10.13-1", "81 个策略组", "--bm7", "DNS 覆写", "v1.19.20", "f250126", "2001:2::"]),
    ("docs/07-需求对照.md", ["### 2026-10-12 至 10-13", "R14-F02", "cd63eba", "r15 的数字：270 个目标", "10-13 13:29“21 维持现状”"]),
    ("docs/00-需求原文.md", ["## 补充（2026-10-12 至 10-13", "如果能读到的话先不写，等到审核意见改过来，你完成最终版再写", "默认的国内域名哪个国内直连直接写死",
                             "改 另外新增一个需求 stash 配置文件 你可以弄好 clah 再写 stash 的配置 两者接近",
                             "## 补充（2026-10-13，r15 出版本期间；对话中给出，照录）", "> 21 维持现状"]),
)
# 旧的说法不应再作为现状出现（历史记录里的除外：docs/00 只追加，docs/08 是逐轮的记录）
STALE = {k: [] for k in (
    "tests-259", "259 automated", "自动测试 259 项", "259 项全部通过", "确认 259 项通过", "注入 118 类", "这份说明对应 `2026.10.07-2`",
    "source version **2026.10.07-2**", "对应统一源 2026.10.07-2", "This is r14", "这一版（r14）是", "把这一版（r14）", "269 targets", "289 条用例和排除项",
    "| sing-box（两个版本相同） | 19,546", "| mihomo | 224,085", "17,699 个代表主机", "自有拦截另有 97 条", "自有拦截 97（", "外部意见一共 9 轮", "Nine rounds",
    "r10–r13 逐字相同", "域名原样交给节点，没有解析", "r12–r14 都没有推到", "r12、r13、r14 交付时都没有推", "r12–r14 交付时都没有推",
    "247 项全部通过", "注入 100 类", "注入 104 类", "tests-247", "tests-254", "自动测试 247 项", "自动测试 254 项", "247 automated", "254 automated",
    "确认 247 项通过", "确认 254 项通过", "104 类全部被发现", "mihomo 13 条", "13 条 DNS 去向", "12 条 DNS 去向", "qwen.ai` TXT → 国内（已知限制的现状）",
    "222,593 个里 222 个", "222,593 个里走代理组的 222 个", "核对了其中 432 个", "核对了其中 574 个", "对应统一源 2026.10.06-1（r13）", "（r13；与 r12 相同",
    "统一源 2026.10.06-1（r13）　生成器", "这份说明对应 `2026.10.07-1`", "source version **2026.10.07-1**", "r14：统一源 2026.10.07-1",
    "按旧的办法会算错", "按旧办法会算错", "只在 Loon 严格版直连；", "系统 DNS（路由器 / 公司内网的 DNS）", "写在配置文件里不起作用，只能在这里开",
    "只能在 App 里开**", "Netflix 默认“Netflix·解锁入口”", "需求决定项 20 项", "第 15、17–20 项还没有答复")}
STALE.update({"118 类全部被发现": [H8], "269 个目标": [H8], "r14：统一源 2026.10.07-2": [H8], "100 类全部被发现": [H8], "mihomo 12 条": [H8],
              "mihomo 的 11 条": [H8], "（系统 DNS，即路由器": [H8], "境外 DNS 连不上时，内核没有转去问": [H8], "没有逐行比过": [H8],
              "82 个策略组": [H8, "docs/00-需求原文.md"]})
# 第 21 项 2026-10-13 定了（维持现状）：“等你选”这类说法只能留在 docs/00 的原话和当时的落实说明里
STALE.update({k: ["docs/00-需求原文.md"] for k in ("仍等用户选", "仍然等你选", "仍然等用户选", "仍等使用者选", "还等你选", "awaits the owner", "waiting for the owner",
                                                 "第 21 项还挂着", "使用者还没有选", "等你在 ① ② 里选", "第 21 项（等你选）", "第 21 项等用户选")})


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def mtime(p):
    return datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


man = json.load(open("dist/manifest.json", encoding="utf-8"))
digest = man["source_sha256"]
assert man["source_version"] == "2026.10.13-1" and man["generator_version"] == "1.8.0", man
assert digest == DIGEST, digest
freeze = read(f"{W}/freeze15-time.txt").strip()                                   # 定稿时记下的时间（UTC）
state = subprocess.run(["bash", "handoff/release/code_state.sh"], capture_output=True, text=True, check=True).stdout.strip()
assert state == read(f"{W}/freeze15-state.txt").strip(), "代码在定稿之后变过"
assert freeze == "2026-10-13 03:56:40", freeze
assert state == "9d8929a137ec5b163c73ed35cc1a3914a398e33c08a99201ae8712b9002b72e8", state

# 每份日志开头：统一源摘要是当前的、退出码 0、运行环境和日期；记下开始时间和文件时间
LOGS = ("tests.log", "icu-check.log", "official-check.log", "real-route-check.log", "upstream-field-check.log",
        "upstream-evidence-check.log", "cursor-report-check.log", "icons-check.log", "cn-list-check.log")
starts, ends = {}, {}
for name in LOGS:
    t = read(f"{ev}/{name}")
    head = t.split("\n\n", 1)[0]
    assert f"统一源摘要：{digest}" in head, name
    assert ENV in head and f"运行时间（UTC）：{RUN_DAY}" in head, (name, head[:200])
    assert re.search(r"^退出码：0$", t, re.M), name
    assert "scratchpad" not in t and "/tmp/claude" not in t and "/root/.claude" not in t, name
    starts[name] = re.search(r"运行时间（UTC）：(\S+ \S+)", head).group(1)
    ends[name] = mtime(f"{ev}/{name}")
assert min(starts.values()) > freeze, (min(starts.values()), freeze)
checks_window = f"{min(starts.values())[11:16]}–{max(ends.values())[11:16]} UTC"
ct = read(f"{W}/checks15-time.txt").split("\n")
assert ct[0] > freeze and ct[0] <= min(starts.values()) and ct[1] >= max(ends.values()), ct
assert read(f"{W}/checks15.out").rstrip().endswith("全部检查通过。\nexit 0"), "run_checks.sh 没有以“全部检查通过。”结束"
rr_secs = (datetime.datetime.fromisoformat(ends["real-route-check.log"]) - datetime.datetime.fromisoformat(starts["real-route-check.log"])).total_seconds()
rr_minutes = str(round(rr_secs / 60))

tests = read(f"{ev}/tests.log")
m = re.search(r"^Ran (\d+) tests in [\d.]+s\n\nOK\b(.*)$", tests, re.M)
assert m, "tests.log 里没有 OK"
assert "skipped" not in m.group(2), "有跳过的测试：" + m.group(2)
assert m.group(1) == N_TESTS, m.group(1)
NEW_R15 = ("test_bm7_ads_entries_are_recorded_in_the_snapshot", "test_records_names_and_addresses", "test_blocked_environment_is_an_error_not_a_result",
           "test_socks_node_gets_the_name_over_tcp", "test_switched_groups_follow_the_documented_split",
           "test_domain_trie_checks_patterns_like_mihomo", "test_max_copy_says_what_was_changed_and_when")
for t in ("test_mihomo_unmatched_names_ask_only_the_foreign_doh", "test_singbox_unmatched_names_ask_only_dns_foreign",
          "test_each_kind_of_reply_is_told_apart", "test_policy_lookup_follows_mihomos_domain_trie", "test_mihomo_product_names_go_to_the_foreign_dns",
          "test_names_ending_in_a_pointer_after_labels_are_read", "test_singbox_and_mihomo_both_have_the_product_layer",
          "test_cases_cover_the_point_of_the_check", "test_recorded_official_runs_match_the_cases",
          "test_mihomo_never_hands_a_proxied_name_to_the_domestic_dns", "test_self_check_sees_the_product_layer",
          "test_domestic_direct_is_fixed", "test_change_that_only_reorders_an_item_says_so", "test_rule_list_doc_counts_each_own_list_from_its_own_data") + NEW_R15:
    # 测试带说明文字时，unittest -v 把“... ok”写在说明的那一行，不在名字那一行；整体是 OK（上面已经断言），这里只核对它们确实跑了
    assert re.search(rf"^{t} \(test_\w+\.\w+\.{t}\)", tests, re.M), t
assert "DeprecationWarning" not in tests
per_file = {}
for mod, _cls, _name in set(re.findall(r"\((test_\w+)\.(\w+)\.(\w+)\)", tests)):
    per_file[mod] = per_file.get(mod, 0) + 1
assert sum(per_file.values()) == int(N_TESTS), per_file
assert (per_file["test_real_data"], per_file["test_strict"], per_file["test_dns_lan"], per_file["test_compare_versions"],
        per_file["test_local_and_private"], per_file["test_icons"], per_file["test_source"]) == (45, 33, 14, 13, 9, 9, 18), per_file

icu = read(f"{ev}/icu-check.log")
assert "13 条（宽 7 条、严 6 条）× 2283 个节点名（其中 625 个有手写的期望）" in icu
assert "× 2306 个节点名" in icu
m = re.search(r"ICU 平均每次匹配：宽 (\d+) 微秒、严 (\d+) 微秒.*?Loon (\d+) 毫秒，Quantumult X（26 个策略各一条）(\d+) 毫秒", icu)
assert m, "icu-check.log 里没有耗时行"
icu_time = (f"这次运行 ICU 平均每次匹配：宽的 {m.group(1)} 微秒、严的 {m.group(2)} 微秒（含调用开销）；按 300 个节点估算 Loon 约 {m.group(3)} 毫秒、"
            f"Quantumult X 约 {m.group(4)} 毫秒（每次运行有出入：同一台机器上 r14 那次是 52 / 91 毫秒，r13 是 49 / 93 毫秒，r12 是 29 / 51 毫秒（另一台机器），"
            f"r10 时几次运行是 36–38 / 63–66 毫秒；这一次和变异检查同时跑、机器更忙；手机会慢几倍）")
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
assert f"用例与排除项共 290 条，不同的目标 270 个；DNS 去向用例 sing-box 22 条、mihomo {N_MIHOMO_DNS} 条，拨号解析用例 sing-box 12 条、mihomo 12 条" in rr
assert rr.count("[符合] 路由 270 条") == 3 and rr.count("[符合] DNS 去向 22 条") == 2 and rr.count(f"[符合] DNS 去向 {N_MIHOMO_DNS} 条") == 1, "real-route-check.log"
assert rr.count("[符合] 连接时的解析 12 条") == 3 and rr.count("只有它管的这几条变了，这一处仍然需要") == 3 and rr.count("这两处修正仍然需要") == 2
assert rr.count("[符合] 境外 DNS 不应答") == 3
assert rr.count(f"连接 6 条、查询 {N_MIHOMO_DNS} 条，收到查询的替身与正常那一遍完全相同；其中 5 条只有境外替身收到") == 1
assert rr.count("连接 6 条、查询 22 条，收到查询的替身与正常那一遍完全相同；其中 6 条只有境外替身收到") == 2
assert "[不符合]" not in rr and "\n全部一致\n" in rr and "处不一致" not in rr and "全集" not in rr
assert "operation not permitted" not in rr
for needle, n in RR_OUTBOUND_COUNTS.items():
    assert rr.count(needle) == n, (needle, rr.count(needle))
for needle in ("node gateway.lan → system", "node homeproxy → system", "direct nas.lan → system", "printer.lan A → system",
               "www.taobao.com A → fake-ip", "printer A → system", "tplinkwifi.net A → system", "time.windows.com A → domestic",
               "chatgpt.com A → fake-ip", "api.openai.com HTTPS → empty", "claude.ai TXT → foreign", "never-listed-query.net A → fake-ip",
               "never-listed-txt.net TXT → foreign", "www.qq.com TXT → domestic", "google.cn AAAA → empty",
               "qwen.ai TXT → foreign", "tlu.dl.delivery.mp.microsoft.com TXT → domestic",
               "proxied www.youtube.com → none", "proxied gemini.google.com → none", "proxied chat.qwen.ai → none",
               "unlisted never-listed-site.org → foreign", "unlisted r1.test.dnsleaktest.com → foreign",
               "unlisted never-listed-site.org → dns-foreign", "unlisted r1.test.dnsleaktest.com → dns-foreign",
               "自检：去掉 nameserver-policy 里交给系统 DNS 的几条（局域网后缀、不带点的名字、private 集合；改成国内 DNS）后，printer.lan A → domestic、"
               "nas.home.arpa A → domestic、printer A → domestic、tplinkwifi.net A → domestic、direct nas.lan → domestic",
               # 逐条扫描
               "国内 DNS 与路由的逐条扫描",
               "mihomo：扫了 224087 个代表主机（集合条目 222448 个、规则的值 1639 个；集合规模 {'cn': 111224}；正则 0 条、关键词 0 条取不出代表主机，没有扫）",
               "名字会交给国内 DNS 的 222353 个：路由是国内直连 / 直连 / 拦截的 222339 个；归默认直连、可以切换的组的 14 个；走代理组的 0 个",
               "[符合] 官方内核核对 214 个主机（走代理组的和默认直连组的全部，另抽 200 个）",
               "自检：去掉 nameserver-policy 里“走代理组的产品域名”那一层再扫，走代理组的从 0 个变成 136 个——这一层仍然需要，这项核对看得见它要防的错误",
               "[符合] 多出来的 136 个（产品域名那一层管到的）交给官方内核查 TXT：都只由境外 DNS 的替身收到",
               "去掉 DNS 规则里“走代理组的产品域名”那一层再扫，走代理组的从 0 个变成 130 个",
               "Loon 订阅的上游规则文件 3 个，按 IP 判断的规则共 187 条：都带 no-resolve",
               "[loon] AdvertisingLite.list：域名 0、后缀 0、关键词 187、IP 段 187（都带 no-resolve）",
               "[loon] ChinaMax_Domain.list：域名 268、后缀 111009、关键词 0、IP 段 0",
               "（只在 DNS 段里用到的：private 131）") + RR_OUTBOUND:
    assert needle in rr, needle
assert "qwen.ai TXT → domestic" not in rr and "printer A → domestic（" not in rr
assert rr.count("扫了 19548 个代表主机（集合条目 17996 个、规则的值 1552 个；集合规模 {'geosite-cn': 9303}；正则 8 条") == 2
assert rr.count("名字会交给国内 DNS 的 17701 个：路由是国内直连 / 直连 / 拦截的 17701 个；归默认直连、可以切换的组的 0 个；走代理组的 0 个") == 2
assert rr.count("[符合] 官方内核核对 200 个主机") == 2
assert rr.count("290 条，全部符合人工期望") == 4
assert rr.count(f"为了判断 IP 规则而在本机解析过的域名：{RR_RESOLVED} 个里 {RR_RESOLVED_STD} 个") == 2 and rr.count(f"为了判断 IP 规则而在本机解析过的域名：{RR_RESOLVED} 个里 0 个") == 2
assert "release 分支 f7c0420" in rr and "rule-set 分支 be94d52" in rr
m = re.search(r"检查了 (\d+) 个字段 / 取值", read(f"{ev}/upstream-field-check.log"))
assert m, "upstream-field-check.log 里没有字段数"
fields = f"{int(m.group(1)):,}"
ic = read(f"{ev}/icons-check.log")
assert "f250126f57228b0b32f3445b21078e382e6152e9" in ic and "合计 6,949,624 字节" in ic and "80 个地址逐个相同" in ic
assert ic.count("81 个策略组的图标都在图标仓库里，是 PNG，尺寸对") == 6 and "还没有上传" not in ic and "全部符合" in ic
assert "1 个图在图标仓库里、清单没有收，没有比：Apple Push" in ic
cn = read(f"{ev}/cn-list-check.log")
assert "source/data/cn-domains.txt 与按固定快照重新生成的逐字节相同：后缀 6142 条、精确域名 12 条（快照 c1c2cf0d，2026-09-22）" in cn
assert "source/data/cn-domains-max.txt 与按固定快照重新生成的逐字节相同：后缀 111009 条、精确域名 268 条（快照 51d2e1dd，2026-09-21）" in cn
assert "source/data/LICENSE-domain-list-community.txt 与上游的 LICENSE 相同" in cn and "source/data/LICENSE-ios_rule_script.txt 与上游的 LICENSE 相同（GPL-2.0）" in cn
assert "--bm7" in cn.split("\n\n", 1)[0], "cn-list-check.log 的命令里要带 --bm7（核对大清单副本）"
ue = read(f"{ev}/upstream-evidence-check.log")
assert UE_NEEDLE in ue and "检查通过" in ue, ue[-800:]
assert "Cursor 版共 533 条：同组 429，同组（只写进 mihomo / sing-box） 70，无专门规则 18，不同组 15，已替换 1。" in read(f"{ev}/cursor-迁入核对.md")

snap = json.load(open("tests/data/real_sets.json", encoding="utf-8"))
assert snap["generated"] == RUN_DAY and snap["source_version"] == "2026.10.13-1", (snap["generated"], snap["source_version"])
mh = snap["official"]["mihomo"]
assert mh["dial"]["node gateway.lan"] == "system" and mh["dns"]["printer A"] == "system" and len(mh["dial_sha256"]) == 64
assert mh["dns"]["tplinkwifi.net A"] == "system" and mh["dns"]["time.windows.com A"] == "domestic"
assert mh["dns"]["qwen.ai TXT"] == "foreign" and mh["dns"]["tlu.dl.delivery.mp.microsoft.com TXT"] == "domestic"
assert mh["outbound"]["mihomo-wireguard-tcp"]["qwen.ai"] == "foreign" and mh["outbound_without_product_layer"]["qwen.ai"] == "domestic"
assert mh["outbound_without_product_layer_udp"]["qwen.ai"] == "domestic" and mh["outbound_without_product_layer_udp"]["chatgpt.com"] == "foreign"
assert all("domestic" not in (v["qwen.ai"], v["download.microsoft.com"], v["chatgpt.com"]) for v in mh["outbound"].values())
assert mh["outbound_received"]["mihomo-socks5-tcp"]["qwen.ai"] == "domain" and mh["outbound_received"]["mihomo-socks5-udp"]["qwen.ai"] == "ip"
assert mh["outbound_switched"]["mihomo-wireguard-tcp"] == {"api.bilibili.com": "domestic", "www.apple.com": "foreign", "www.apple.com.cn": "domestic", "www.qq.com": "domestic"}
assert mh["outbound_switched"]["mihomo-socks5-udp"] == mh["outbound_switched"]["mihomo-wireguard-tcp"]
sb, sb12 = snap["official"]["singbox"], snap["official"]["singbox112"]
for fam in (sb, sb12):
    assert fam["outbound"]["singbox-wireguard-tcp"]["qwen.ai"] == "dns-foreign" and fam["outbound"]["singbox-wireguard-tcp"]["time.windows.com"] == "dns-cn"
    assert fam["outbound_received"]["singbox-socks-tcp"]["qwen.ai"] == "domain" and fam["outbound_received"]["singbox-socks-tcp"]["never-listed-site.org"] == "ip"
    assert fam["outbound_switched"]["singbox-wireguard-tcp"]["api.bilibili.com"] == "dns-foreign"
assert sb["outbound_received"]["singbox-socks-udp"]["qwen.ai"] == "-" and sb12["outbound_received"]["singbox-socks-udp"]["qwen.ai"] == "domain"
assert len(snap["sizes"]["loon"]) == 3 and all(v["ip_resolving"] == 0 for v in snap["sizes"]["loon"].values())
cons = snap["consistency"]
assert len(cons["mihomo"]["mismatch"]) == 0 and len(cons["singbox"]["mismatch"]) == 0 and len(cons["singbox112"]["mismatch"]) == 0
assert cons["mihomo"]["without_product_dns_rules"] == 136 and cons["mihomo"]["product_layer_checked"] == 136 and cons["mihomo"]["official_checked"] == 214
assert cons["singbox"]["without_product_dns_rules"] == 130
assert len(snap["hosts"]) == 266 and len(snap["ips"]) == 28
assert "逐条扫描" in snap["about"] and "全集" not in snap["about"]

cmp14 = read(f"{ev}/与上一版的对比.md")
assert cmp14.startswith("# 版本对比：r14 → r15\n"), cmp14[:40]
assert "| r14 | 625 | 0 | 625 | 0 |" in cmp14 and "| r15 | 625 | 0 | 625 | 0 |" in cmp14
assert "共 2247 个名字" in cmp14 and "### 手动组的归属变了（0 个）" in cmp14 and "成员变了（0 个）" in cmp14
assert not re.search(r"^- 改动 `[^`]*`：\s*$", cmp14, re.M), "还有说不出改了什么的“改动”"
for needle in CMP_NEEDLES:
    assert needle in cmp14, needle
cmp7 = read(f"{ev}/与r7的对比.md")
assert cmp7.startswith("# 版本对比：r7 → r15\n"), cmp7[:40]
assert "| r7 | 578 | 47 | 534 | 91 |" in cmp7 and "| r15 | 625 | 0 | 625 | 0 |" in cmp7
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
assert [s["start"][:10] for s in segs] == list(MUT_DAYS) and [s["end"][:10] for s in segs] == list(MUT_DAYS), segs
assert all(s["start"] > freeze for s in segs), (segs, freeze)
assert len(segs) == 2 and [len(x["ids"]) for x in segs] == [24, 98], [(x["start"], x["end"], len(x["ids"])) for x in segs]
env2 = read(f"{W}/env15-seg2.txt")
assert f"code_state {state}" in env2 and "Python 3.13.16" in env2 and "PyYAML 6.0.1" in env2 and "libicui18n.so.74" in env2 and "SOURCES ok=17 bad=0" in env2, env2
assert segs[0]["end"] < env2[:19] < segs[1]["start"], (segs, env2[:19])
window = ("三批并行，分 2 段：" + "；".join(f"{x['start'][11:16]}–{x['end'][11:16]} UTC 跑完 {len(x['ids'])} 类" for x in segs) + "；"
          "前一段被工作环境重新启动打断（机器重启，后台进程随之停止；正在跑的那几类没有留下结果，在后一段里从头重跑），两段之间代码没有改动；"
          f"后一段开始前（{env2[11:16]}）重新核对过代码状态和运行环境：Python、PyYAML、ICU 的版本，官方程序和上游数据的 SHA-256、上游源码的提交号，都和前一段相同")
fresh = res["fresh"]
assert fresh["solo"] == [], fresh
NEW_TESTS = {"M101": "test_names_ending_in_a_pointer_after_labels_are_read", "M102": "test_mihomo_product_names_go_to_the_foreign_dns",
             "M103": "test_mihomo_product_names_go_to_the_foreign_dns", "M104": "test_policy_lookup_follows_mihomos_domain_trie",
             "M108": "test_mihomo_sends_lan_suffixes_to_system_dns_first", "M109": "test_mihomo_sends_lan_suffixes_to_system_dns_first",
             "M110": "test_both_use_the_larger_upstream_list", "M111": "test_max_copy_is_the_upstream_list_minus_locally_covered_entries",
             "M114": "test_defaults", "M115": "test_apple_ai_before_apple",
             "M116": "test_change_that_only_reorders_an_item_says_so", "M117": "test_rule_list_doc_counts_each_own_list_from_its_own_data",
             "M118": "test_domestic_direct_is_fixed"}
NEW_TESTS.update(MUT_R15)
for name, test in [("M91", "test_mihomo_unmatched_names_ask_only_the_foreign_doh"), ("M92", "test_singbox_unmatched_names_ask_only_dns_foreign"),
                   ("M99", "test_singbox_unmatched_names_ask_only_dns_foreign"), ("M100", "test_each_kind_of_reply_is_told_apart")] + list(NEW_TESTS.items()):
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
PARTIAL_TEXT = ("“恢复关键词 siri”“azure.com 放回 Microsoft”“用回肯定前瞻”、国内域名清单数据文件被改坏的两类（M89、M90）"
                "由统一源校验直接拒绝（生成器不肯生成，测试大面积报错）；大清单副本的数据文件被手改（M111）生成时没有拦住，"
                "由 `tests/test_strict.py` 的 `test_max_copy_is_the_upstream_list_minus_locally_covered_entries` 发现；"
                "严格版的结构被改坏的几类（M76–M78、M80–M82）和“清空 `proxy-server-nameserver`”被写盘前的检查拦住，生成流程的那批测试因此失败，同时另有路由用例失败；"
                "“图标登记里漏了 Apple Push”在生成时直接报错；")
mut_cell = (f"{N_MUT} 类全部被发现，都是 r15 定稿（{freeze[:16]} UTC）以后在上面这个摘要、这个代码状态的代码上跑的（{window}）。"
            "“记录对应现在的配置”那两项——规则与 DNS 两段的摘要、拨号摘要——对改了规则、DNS 或出站的变异都会报："
            f"{N_MUT} 类里前一项报了 {len(fresh['with']['routing'])} 类、后一项报了 {len(fresh['with']['dial'])} 类；只靠这两项发现的一类都没有（r13 起）。"
            "处理 GPT 审核 r14 新加的四类：" + MUT_R15_TEXT +
            "处理 GPT 审核 r13 加的四类：M101（读名字时又只在第一个字节看压缩指针）由 `tests/test_real_data.py` 的 `test_names_ending_in_a_pointer_after_labels_are_read` 发现；"
            "M102（mihomo 的 `nameserver-policy` 又没有产品域名那一层）、M103（那一层把默认直连的组也交给境外 DNS）由 `tests/test_dns_lan.py` 的 "
            "`test_mihomo_product_names_go_to_the_foreign_dns` 发现；M104（核对工具按“第一条命中”查）由 `test_policy_lookup_follows_mihomos_domain_trie` 发现。"
            "你 2026-10-07 定下的各项对应的 M105–M115，各由对应的测试发现（例如 M108、M109 由 `test_mihomo_sends_lan_suffixes_to_system_dns_first`，M110 由 `test_both_use_the_larger_upstream_list`，"
            "M114 由 `test_defaults`，M115 由 `test_apple_ai_before_apple`）；r14 出版本时查出的 M116、M117 分别由 `test_change_that_only_reorders_an_item_says_so`、"
            "`test_rule_list_doc_counts_each_own_list_from_its_own_data` 发现；第 17 项对应的 M118（“国内直连”又能切到国外默认）由 `tests/test_structure.py` 的 `test_domestic_direct_is_fixed` 发现。"
            "M45（回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，"
            "那一项把匹配放在带超时的子进程里，等满 5 分钟后失败并给出提示。" + PARTIAL_TEXT + "其余由对应的测试发现，每一类的失败项见日志")


# 一次性核对：审核方给第 21 项的做法（R14-F01），在这一版的配置上跑
def parse_probe(text):
    """→ {(标题, 状态, 出口 流量): {主机: 去向}}"""
    out, title = {}, None
    for ln in text.splitlines():
        if ln.startswith("== "):
            title = ln[3:]
            continue
        mm = re.match(r"^  (.+?)，(\S+ (?:TCP|UDP))：(.*)$", ln)
        if mm and title:
            out[(title, mm.group(1), mm.group(2))] = dict(x.split(" → ") for x in mm.group(3).split("，"))
    return out


p15 = read("handoff/notes/r14_review_probes.out")
assert "统一源 2026.10.13-1" in p15.split("\n")[0] and "Mihomo Meta v1.19.31" in p15.split("\n")[0]
assert mtime("handoff/notes/r14_review_probes.out") > freeze
pt = read(f"{W}/probe15-time.txt").split("\n")
probe_window = f"（{pt[0].split()[-1][:5]}–{pt[1].split()[-1][:5]} UTC）"
assert pt[0].split()[-2] == RUN_DAY and pt[0].split()[-1] > freeze[11:], pt
pr = parse_probe(p15)
assert len(pr) == 8, sorted(pr)
OURS, THEIRS = "交付的配置（DNS 设置与 r14 相同）", "审核方的做法（direct-nameserver: [system]，follow-policy: false）"
STAY, SWITCH = "默认直连的组保持直连", "Apple / Bilibili 港澳台切到测试节点"
for how in ("wireguard TCP", "socks5 UDP"):
    for st in (STAY, SWITCH):
        assert pr[(OURS, st, how)] == {"www.apple.com.cn": "domestic", "api.bilibili.com": "domestic", "www.qq.com": "domestic",
                                       "router.lan": "system", "qwen.ai": "foreign"}, (st, how)
    assert pr[(THEIRS, STAY, how)] == {"www.apple.com.cn": "system", "api.bilibili.com": "system", "www.qq.com": "system",
                                       "router.lan": "system", "qwen.ai": "foreign"}, how
    assert pr[(THEIRS, SWITCH, how)] == {"www.apple.com.cn": "foreign", "api.bilibili.com": "foreign", "www.qq.com": "system",
                                         "router.lan": "system", "qwen.ai": "foreign"}, how
probe_cell = ("**这一版的配置**：Apple、Apple Music/TV、Apple Push、Bilibili 港澳台保持直连和切到测试节点两种情况下，`www.apple.com.cn`、`api.bilibili.com` "
              "经 WireGuard 走 TCP、经 SOCKS5 走 UDP 时都由国内 DNS 的替身收到（这两个名字在上游国内域名集合里）；`www.qq.com` 问国内，`router.lan` 问系统 DNS 的替身，"
              "走代理的 `qwen.ai` 问境外。**审核方的做法**（`direct-nameserver: [system]`、`direct-nameserver-follow-policy: false`，"
              "`nameserver-policy` 里把这两个名字交给境外 DNS——审核方的复现脚本也只加了这两个）：保持直连时这两个名字由系统 DNS 的替身收到，"
              "切到测试节点以后由境外 DNS 的替身收到；`www.qq.com`、`router.lan` 一直由系统 DNS 的替身收到，`qwen.ai` 一直问境外——与审核报告里的表一致。"
              "系统 DNS 的替身代表“认得局域网名字、把国内网站交给国内 DNS 的路由器”，它只是本机的一个替身，不能说明哪台真实的路由器做得到")

values = {"ICU_TIME": icu_time, "LONG_TIME": long_time, "FIELDS": fields, "MUT_CELL": mut_cell, "PROBE_CELL": probe_cell,
          "CMP_CELL": CMP_CELL, "R15_REAL_CELL": R15_REAL_CELL, "tests_n": N_TESTS, "mut_n": str(N_MUT), "mihomo_dns_n": N_MIHOMO_DNS,
          "code_state": state, "freeze_utc": freeze[:16], "mut_window": window, "checks_window": checks_window, "probe_window": probe_window,
          "run_window": f"{RUN_DAY}（UTC）", "run_day_en": RUN_DAY, "rr_minutes": rr_minutes}

# 产物大小、摘要与文档里写的一致
sizes = {rel: os.path.getsize(os.path.join("dist", rel)) for rel in man["outputs"]}
assert (sizes["loon/loon.conf"], sizes["quantumultx/quantumultx.conf"], sizes["mihomo/mihomo-profile.yaml"], sizes["mihomo/mihomo-core.yaml"],
        sizes["sing-box/sing-box-1.14.json"], sizes["sing-box/sing-box-1.12.json"]) == (241985, 404505, 280322, 280505, 79164, 79190), sizes
assert (sizes["loon/loon-strict.conf"], sizes["quantumultx/quantumultx-strict.conf"], sizes["loon/rules/cn-domains.list"],
        sizes["quantumultx/rules/cn-domains.list"], sizes["quantumultx/rules/cn-domains-max.list"],
        sizes["quantumultx/rules/domain-fallback.list"]) == (243317, 406482, 165629, 196326, 3521641, 629), sizes
doc05 = read("docs/05-验收记录.md")
for rel, v in man["outputs"].items():
    sha = v["sha256"] if isinstance(v, dict) else v
    assert f"`{sha[:8]}…`" in doc05, rel
assert digest in doc05 and state in doc05
changed = subprocess.run(["git", "diff", "--name-only", R14, "--", "dist"], capture_output=True, text=True, check=True).stdout.split()
assert sorted(changed) == sorted(["dist/manifest.json", "dist/mihomo/mihomo-core.yaml", "dist/mihomo/mihomo-profile.yaml", "dist/loon/loon.conf",
                                  "dist/loon/loon-strict.conf", "dist/quantumultx/quantumultx.conf", "dist/quantumultx/quantumultx-strict.conf",
                                  "dist/sing-box/sing-box-1.14.json", "dist/sing-box/sing-box-1.12.json",
                                  "dist/quantumultx/rules/cn-domains-max.list"]), changed
pol = __import__("yaml").safe_load(read("dist/mihomo/mihomo-core.yaml"))["dns"]["nameserver-policy"]
assert len(pol) == 745 and sum(1 for v in pol.values() if v == ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"]) == 732, len(pol)
assert sum(1 for v in pol.values() if v == ["system"]) == 3 and sum(1 for v in pol.values() if v == ["https://223.5.5.5/dns-query", "https://1.12.12.12/dns-query"]) == 10

for k, v in values.items():
    print(f"⟦{k}⟧ = {v[:200]}")
files = (["README.md", "README.zh-CN.md", "PROJECT_STATE.md", "00-审核说明.md"] + sorted(os.path.join("docs", f) for f in os.listdir("docs") if f.endswith(".md")))
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
DOC_NEEDLES = DOC_NEEDLES_R15
for p, needles in DOC_NEEDLES:
    s = read(p)
    for n in needles:
        assert n in s, (p, n)
# 旧的说法不应再作为现状出现（历史记录里的除外，逐个看过）
HIST = ["docs/00-需求原文.md", "docs/08-外部审核记录.md"]
for p in files:
    s = read(p)
    for k, allowed in STALE.items():
        if k in s and p not in allowed:
            raise AssertionError(f"{p} 里还有旧的说法：{k}")
    # “全集”只能出现在说明旧名字的地方
    if p not in HIST:
        for mm in re.finditer("全集", s):
            ctx = s[max(0, mm.start() - 8):mm.start() + 12]
            assert re.search(r"叫(它)?“全集|“全集一致性”改名|“全集一致性”→|原“全集", ctx), (p, ctx)
print("核对通过")
