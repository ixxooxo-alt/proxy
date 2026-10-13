"""把文档里的占位符 ⟦…⟧ 换成最终运行得到的数字，并核对文档里写的数字和日志、产物一致（r16 用的；照 r15-as-used/finalize.py 改的）。
r16 处理 GPT 对 r15 的审核，另加 Stash 的两份配置；代码定稿一次（2026-10-13 11:42）；变异检查被工作环境停掉打断过一次，分两段跑完；
变异检查跑完以后重新生成了规则证据的记录（只多了 Stash 这个客户端名），再跑了一遍全部检查——交付的日志是这一遍的。
数字都从日志和产物里读。用法（在工程根目录）：python3 handoff/release/r16-as-used/finalize.py <变异日志目录> [--dry]"""
import datetime, filecmp, json, os, re, subprocess, sys

D = os.path.abspath(sys.argv[1])
dry = "--dry" in sys.argv
ev = "docs/evidence"
RUN_DAY = "2026-10-13"                                                            # 全部检查、一次性核对、快照、变异检查都在这一天
DIGEST = "cd8f4cc874b1f4b462d0349531e0ffd4c1edb90ed4d2a61709cc5ae671dda4cf"     # r16：生成器 1.9.0、统一源 2026.10.13-2
STATE = "c613987e17944ae25087a0e8bece3ded4215204f0eb3631b55256f2b04a6a1a9"
FREEZE = "2026-10-13 11:42:07"
N_TESTS, N_MUT, N_MIHOMO_DNS = "294", 141, "15"
ENV = "Python：Python 3.13.16，PyYAML：6.0.1"
R15 = "dc90da7"                                                                   # GPT 审的 r15
W = os.path.expanduser("~/proxy-work")

# ---- 这一版特有的说法（从日志里读到以后照抄；下面的断言核对它们确实在日志 / 报告里）----
RR_RESOLVED = "261"
RR_OUTBOUND = (                                                                  # 出站核对、节点收到的目标、组切换以后（照日志原文；和 r15 相同）
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
CURSOR_NEEDLE = "Cursor 版共 533 条：同组 429，同组（只写进 mihomo / sing-box / Stash） 70，无专门规则 18，不同组 15，已替换 1。"
CMP_NEEDLES = ("大小：241,985 → 241,985 字节。", "大小：404,505 → 404,505 字节。", "大小：280,322 → 280,322 字节。", "大小：280,505 → 280,505 字节。",
               "大小：79,164 → 79,164 字节。", "大小：79,190 → 79,190 字节。", "大小：243,317 → 243,317 字节。", "大小：406,482 → 406,482 字节。",
               "- 删除一行：`# 统一源版本 2026.10.13-1；目标：Loon 3.x（规则匹配顺序依据官方文档：本地 > 插件 > 订阅，域名规则先于 IP 规则，要求 3.0.3+）`",
               "- 新增一行：`# 统一源版本 2026.10.13-2；目标：Loon 3.x（规则匹配顺序依据官方文档：本地 > 插件 > 订阅，域名规则先于 IP 规则，要求 3.0.3+）`",
               "r15 没有这个文件：Stash 的配置是 2026-10-13 新增的（r16），和 mihomo 那份的关系见 `docs/02`“Stash”一节。",
               "r15 没有这个文件：Stash 的配置是 2026-10-13 新增的（r16），和 mihomo 那份的关系见 `docs/02`“Stash”一节；严格版和同一版标准版的差别见第六节。",
               "## 六、严格版", "### `stash/stash-strict.yaml` 对照 `stash/stash.yaml`", "大小：标准版 251,084 字节，严格版 252,016 字节。",
               "没有变化的分段：DNS（dns）（4 条）、策略组（proxy-groups）（81 条）。",
               "**规则（rules）**：新增 2 条，删除 1 条，改动 0 条；两版都有的条目顺序不变。",
               "- 新增：`RULE-SET,国内域名-ChinaMax,国内直连`", "- 新增：`GEOIP,CN,国内直连,no-resolve`", "- 删除：`GEOIP,CN,国内直连`",
               "**其余设置**：新增 1 条，删除 0 条，改动 0 条；两版都有的条目顺序不变。",
               "大小：标准版 241,985 字节，严格版 243,317 字节", "大小：标准版 404,505 字节，严格版 406,482 字节",
               "`loon/rules/cn-domains.list`：165,629 字节，规则 6,133 条（DOMAIN 12、DOMAIN-SUFFIX 6,121）。和 r15 的一模一样。",
               "`quantumultx/rules/cn-domains.list`：196,326 字节，规则 6,133 条（HOST 12、HOST-SUFFIX 6,121）。和 r15 的一模一样。",
               "`quantumultx/rules/cn-domains-max.list`：3,521,714 字节，规则 111,182 条（HOST 252、HOST-SUFFIX 110,930）。和 r15 相比：新增 0 条、删除 0 条（规则相同，只有注释不同）。",
               "`quantumultx/rules/domain-fallback.list`：629 字节，规则 1 条（HOST-KEYWORD 1）。和 r15 的一模一样。")
CMP_CELL = ("Loon、Quantumult X、mihomo 的六份配置只有文件头注释里的统一源版本号变了（各分段的条目完全相同，大小不变），策略组、规则、DNS 都没有变；"
            "sing-box 的两份逐字节相同；Stash 的两份是这一版新增的；大清单副本的规则相同、只有注释不同（文件头多一句“这个文件的内容最后一次改动”）；"
            "两份自有清单和域名兜底文件和 r15 的一模一样")
R16_REAL_CELL = ("路由 270 个目标（和 r15 相同）在 mihomo v1.19.31、sing-box v1.14.1 与 v1.12.0 上都与人工期望一致；DNS 去向、连接时的解析、境外 DNS 不应答、"
                 "出站时的解析（含节点收到的目标）、默认直连的组切到代理以后，结果和 r15 逐条相同；逐条扫描两个内核走代理组的仍是 0 个。"
                 "Stash 只有模拟器：两份各 290 条全部符合期望；为了判断 IP 规则在本机解析过的域名，标准版 261 个里 16 个、严格版 0 个"
                 "（`docs/evidence/real-route-check.log`）")
H8 = "docs/08-外部审核记录.md"
DOC_NEEDLES_R16 = (
    ("README.md", ["tests-294%20passing", "294 automated tests", "2026.10.13-2", "This is r16", "632 hand-labelled", "12–16 KB",
                   "43 service groups", "81 policy groups", "270 targets", "stash-strict.yaml", "15 on mihomo", "561 community-sourced",
                   "Eleven rounds of external input", "unsupported address", "item 22 of `docs/06`", "One rule source. Five clients.",
                   "tests were run on Linux (Python 3.13) in a cloud session on 2026-10-13 (UTC)"]),
    ("README.zh-CN.md", ["自动测试 294 项", "2026.10.13-2", "（r16：新加 Stash 的两份配置", "632 个人工写期望", "2290 个假节点",
                         "每条 12–16 KB", "81 个策略组", "270 个目标", "mihomo 15 条", "r14 起两个内核都是 0 个", "Python 3.13.16",
                         "561 条社区来源规则", "外部意见一共 11 轮", "这一版的检查是 2026-10-13（UTC）在云端会话里跑的", "sing-box 17,701 个代表主机",
                         "`docs/06` 第 22 项", "`dist/stash/stash.yaml`"]),
    ("PROJECT_STATE.md", ["r16：统一源 2026.10.13-2", "生成器 1.9.0", "T29 第 11 轮", "第 22 项", "确认 294 项通过", "需要再跑一次 294 项", "r16：2026-10-13 11:42 定稿以后"]),
    ("00-审核说明.md", ["## 本轮（r16，统一源 2026.10.13-2）改了什么", "266 → 294 项", "122 → 141 类", "公开产物 13 → 15 个",
                        "都在 2026-10-13（UTC）", "代码 2026-10-13 11:42 UTC 定稿", "handoff/notes/r15_review_probes.out", "## 本轮请重点看"]),
    ("docs/05-验收记录.md", ["294 项全部通过", "逐一注入 141 类错误", "2026.10.13-2（r16", "Python 3.13.16，PyYAML 6.0.1", "2290 个假节点",
                             "860 个 120 / 400 个字符", "270 个目标", "**11:42 定稿**", "mihomo 15 条", "`tests/test_real_data.py`，47 项", "`tests/test_strict.py`，34 项",
                             "`tests/test_stash.py`，23 项", "`tests/test_regions.py`，66 项", "`tests/test_compare_versions.py`，13 项",
                             "222,353 个里走代理组的 0 个", "官方内核核对了其中 214 个", "81 个策略组", "6,949,624 字节", "111,182 条", "111,328 条",
                             "自有拦截 98", "141 类全部被发现", "与上一版（r15）对比", "GPT 审核 r15 建议的 sing-box UDP 定位", "Stash 是 16 个",
                             "| Stash iOS | Stash iPadOS | Stash macOS |"]),
    ("docs/02-语法依据与能力矩阵.md", ["270 个目标", "81 个策略组", "6,949,624 字节", "`cn-domains-max.list`", "**1.14.1 没有发出**", "`tests/test_regions.py` 66 项",
                                     "v1.19.20", "## Loon / Quantumult X 严格版用到的写法（2026-10-06）", "ExampleRule.lsr", "## Stash（2026-10-13，r16）", "2290 个节点名"]),
    ("docs/03-DNS决策表.md", ["| mihomo | 224,087 个", "| sing-box（两个版本相同） | 19,548 个代表主机", "290 条用例和排除项", "现在 732 条", "111,047 条",
                             "6,133 条", "653 个后缀", "1.14.1 没有发出这个包", "## 出站时的解析：代理出口会不会再解析目标（2026-10-07，r14）",
                             "**节点收到的到底是什么**", "`system` 指的是谁", "187 条 IP 段", "49 个顶级域", "110,712 条", "## Stash（2026-10-13，r16）", "定位到了“组”这一层"]),
    ("docs/06-已知限制与待决事项.md", ["## 2026-10-13（r16）：Stash 的配置，和处理 GPT 对 r15 的审核", "| 22 | sing-box 1.14.1", "自有拦截另有 98 条",
                                      "| 21 | 默认直连、可以切到代理的组", "## 2026-10-13 你定下的事项", "| ① 维持现状 | **配置不变**",
                                      "## 2026-10-07 你定下的事项", "870 条服务规则", "105,317 条", "632 个带期望的节点名"]),
    (H8, ["## 第 11 轮：2026-10-13，GPT 审核 r15", "266 → 294 项", "122 → 141 类", "docs/evidence/gpt-r15/", "r15_review_probes.out", "## 第 10 轮", "270 个目标"]),
    ("docs/09-真机验收操作清单.md", ["对应统一源 2026.10.13-2", "81 个策略组", "111,182 条", "unsupported address", "## 1b. 严格版", "## 1c. Stash",
                                     "afpapi.alimama.com", "courier-push-apple.com.akadns.net", "251,084 字节"]),
    ("docs/01-导入、更新、诊断与回滚.md", ["2026.10.13-2", "81 个策略组", "--bm7", "DNS 覆写", "v1.19.20", "f250126", "2001:2::", "stash.yaml"]),
    ("docs/07-需求对照.md", ["### 2026-10-12 至 10-13", "R14-F02", "cd63eba", "### 2026-10-13（GPT 审核 r15 之后，r16）", "632 个人工写期望的节点名"]),
    ("docs/00-需求原文.md", ["## 补充（2026-10-12 至 10-13", "改吧 改完连 stash 一起写最好再让他审核终版",
                             "## 补充（2026-10-13，r16 出版本期间；对话中给出，照录）", "> 继续"]),
    ("handoff/README.md", ["## 13. r16 的补充", "r13–r16", "第 10–13 节"]),
)
# 旧的说法不应再作为现状出现（历史记录里的除外：docs/00 只追加，docs/08 是逐轮的记录）
STALE = {k: [] for k in (
    "tests-266", "266 automated", "自动测试 266 项", "266 项全部通过", "确认 266 项通过", "注入 122 类", "这份说明对应 `2026.10.13-1`",
    "source version **2026.10.13-1**", "对应统一源 2026.10.13-1", "This is r15", "Ten rounds of external input", "外部意见一共 10 轮",
    "625 hand-labelled", "625 个人工写期望", "2283 个假节点", "2283 个节点名", "One rule source. Four clients.", "生成四种客户端",
    "r12–r15 都没有推到", "r12–r15 交付时都没有推", "公开产物是 13 个", "生成 13 个公开产物", "test_thirteen_public_outputs",
    "同组（只写进 mihomo / sing-box）", "只写进 mihomo / singbox：", "1.12.0 正常）", "1.12.0 不会）", "and 1.12.0 does not.",
    "配置约 180 KB", "`tests/test_regions.py` 65 项", "`tests/test_regions.py`，65 项", "`tests/test_real_data.py`，45 项",
    "`tests/test_strict.py`，33 项", "r10–r15 用的是同一批文件", "这份说明对应 `2026.10.07-2`", "This is r14")}
STALE.update({"625 个": [H8, "docs/00-需求原文.md", "docs/05-验收记录.md", "docs/07-需求对照.md", "docs/02-语法依据与能力矩阵.md"],
              "122 类全部被发现": [H8], "r15：统一源 2026.10.13-1": [H8], "2247 个名字": [H8, "docs/02-语法依据与能力矩阵.md"]})
# 第 22 项等你定：不能写成已经定了
STALE.update({k: ["docs/00-需求原文.md"] for k in ("第 22 项已定", "第 22 项你选了")})


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def mtime(p):
    return datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


man = json.load(open("dist/manifest.json", encoding="utf-8"))
digest = man["source_sha256"]
assert man["source_version"] == "2026.10.13-2" and man["generator_version"] == "1.9.0", man
assert digest == DIGEST, digest
freeze = read(f"{W}/freeze16-time.txt").strip()                                   # 定稿时记下的时间（UTC）
state = subprocess.run(["bash", "handoff/release/code_state.sh"], capture_output=True, text=True, check=True).stdout.strip()
assert state == read(f"{W}/freeze16-state.txt").strip(), "代码在定稿之后变过"
assert freeze == FREEZE and state == STATE, (freeze, state)

# ---- 变异检查（先读：全部检查的第二遍要在它之后）----
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
assert len(segs) == 2 and [len(x["ids"]) for x in segs] == [19, 122], [(x["start"], x["end"], len(x["ids"])) for x in segs]
assert all(s["start"][:10] == RUN_DAY and s["end"][:10] == RUN_DAY for s in segs), segs
assert all(s["start"] > freeze for s in segs), (segs, freeze)
assert segs[0]["ids"] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 21], segs[0]["ids"]
env2 = read(f"{W}/env16-seg2.txt")
assert f"code_state {state}" in env2 and "Python 3.13.16" in env2 and "PyYAML 6.0.1" in env2 and "libicui18n.so.74" in env2 and "SOURCES ok=17 bad=0" in env2, env2
assert segs[0]["end"] < env2[:19] < segs[1]["start"], (segs, env2[:19])
mut_end = segs[1]["end"]
window = ("三批并行，分 2 段：" + "；".join(f"{x['start'][11:16]}–{x['end'][11:16]} UTC 跑完 {len(x['ids'])} 类" for x in segs) + "；"
          "前一段停在工作环境停掉的时候（机器停了，后台进程随之停止；正在跑的那几类没有留下结果，在后一段里从头重跑），两段之间代码没有改动；"
          f"后一段开始前（{env2[11:16]}）重新核对过代码状态和运行环境：Python、PyYAML、ICU 的版本，官方程序和上游数据的 SHA-256、上游源码的提交号，都和前一段相同")
fresh = res["fresh"]
assert fresh["solo"] == [], fresh

# ---- 全部检查（变异检查跑完、规则证据的记录重新生成以后的那一遍）----
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
assert min(starts.values()) > mut_end, (min(starts.values()), mut_end)
regen = mtime(f"{ev}/upstream-snapshot.json")                                       # 规则证据的记录重新生成的时间
assert mut_end < regen < min(starts.values()), (mut_end, regen, min(starts.values()))
assert mtime(f"{ev}/上游规则对照.md") == regen or abs((datetime.datetime.fromisoformat(mtime(f"{ev}/上游规则对照.md")) - datetime.datetime.fromisoformat(regen)).total_seconds()) < 5
checks_window = f"{min(starts.values())[11:16]}–{max(ends.values())[11:16]} UTC"
ct = read(f"{W}/checks16b-time.txt").split("\n")
assert ct[0] > mut_end and ct[0] <= min(starts.values()) and ct[1] >= max(ends.values()), ct
assert read(f"{W}/checks16b.out").rstrip().endswith("全部检查通过。\nexit 0"), "run_checks.sh 没有以“全部检查通过。”结束"
c1 = read(f"{W}/checks16-time.txt").split("\n")                                   # 定稿以后、和变异检查同时跑的第一遍
assert c1[0] > freeze and read(f"{W}/checks16.out").rstrip().endswith("全部检查通过。\nexit 0"), c1

tests = read(f"{ev}/tests.log")
m = re.search(r"^Ran (\d+) tests in [\d.]+s\n\nOK\b(.*)$", tests, re.M)
assert m, "tests.log 里没有 OK"
assert "skipped" not in m.group(2), "有跳过的测试：" + m.group(2)
assert m.group(1) == N_TESTS, m.group(1)
assert "ResourceWarning" not in tests and "DeprecationWarning" not in tests
NEW_R16 = ("test_stash_uses_system_dns_for_lan_suffixes", "test_stash_strict_domestic_list_is_recorded", "test_refuses_what_rfc1928_says_to_refuse",
           "test_stash", "test_dns_block", "test_nothing_that_needs_stash_3_6_or_3_4", "test_wildcard_keys_are_quoted_like_the_docs",
           "test_header_says_what_was_checked", "test_each_filter_group_picks_exactly_its_own_placeholder", "test_one_placeholder_per_region_that_cannot_connect",
           "test_pinned_paypal_node_keeps_its_placeholder", "test_placeholders_are_in_the_hand_written_node_name_expectations",
           "test_strict_list_catches_what_both_geosite_sets_miss", "test_generated_outputs_pass_the_structure_check", "test_groups_are_the_mihomo_groups",
           "test_rule_provider_is_the_documented_text_form", "test_standard_rules_are_the_mihomo_rules", "test_strict_differs_from_standard_only_where_intended",
           "test_strict_resolves_nothing_for_rule_matching", "test_build_refuses_a_broken_stash_config", "test_empty_group", "test_filter_without_include_all",
           "test_missing_placeholder", "test_placeholder_that_could_connect", "test_strict_geoip_that_resolves", "test_strict_list_before_geolocation",
           "test_unknown_rule_set_and_unused_provider", "test_max_copy_change_date_follows_content", "test_fifteen_public_outputs")
for t in ("test_mihomo_unmatched_names_ask_only_the_foreign_doh", "test_singbox_unmatched_names_ask_only_dns_foreign",
          "test_records_names_and_addresses", "test_socks_node_gets_the_name_over_tcp", "test_switched_groups_follow_the_documented_split",
          "test_domain_trie_checks_patterns_like_mihomo", "test_max_copy_says_what_was_changed_and_when", "test_domestic_direct_is_fixed") + NEW_R16:
    # 测试带说明文字时，unittest -v 把“... ok”写在说明的那一行，不在名字那一行；整体是 OK（上面已经断言），这里只核对它们确实跑了
    assert re.search(rf"^{t} \(test_\w+\.\w+\.{t}\)", tests, re.M), t
assert "test_thirteen_public_outputs" not in tests
per_file = {}
for mod, _cls, _name in set(re.findall(r"\((test_\w+)\.(\w+)\.(\w+)\)", tests)):
    per_file[mod] = per_file.get(mod, 0) + 1
assert sum(per_file.values()) == int(N_TESTS), per_file
assert (per_file["test_real_data"], per_file["test_strict"], per_file["test_dns_lan"], per_file["test_compare_versions"],
        per_file["test_local_and_private"], per_file["test_icons"], per_file["test_source"], per_file["test_stash"], per_file["test_regions"]) \
    == (47, 34, 15, 13, 9, 9, 18, 23, 66), per_file

icu = read(f"{ev}/icu-check.log")
assert "13 条（宽 7 条、严 6 条）× 2290 个节点名（其中 632 个有手写的期望）" in icu
assert "× 2313 个节点名" in icu
m = re.search(r"ICU 平均每次匹配：宽 (\d+) 微秒、严 (\d+) 微秒.*?Loon (\d+) 毫秒，Quantumult X（26 个策略各一条）(\d+) 毫秒", icu)
assert m, "icu-check.log 里没有耗时行"
icu_time = (f"这次运行 ICU 平均每次匹配：宽的 {m.group(1)} 微秒、严的 {m.group(2)} 微秒（含调用开销）；按 300 个节点估算 Loon 约 {m.group(3)} 毫秒、"
            f"Quantumult X 约 {m.group(4)} 毫秒（每次运行有出入：同一个云端会话里，定稿以后和变异检查同时跑的第一遍是 14 / 8 微秒、43 / 75 毫秒，"
            f"r15 是 42 / 75 毫秒，r14 是 52 / 91 毫秒，r13 是 49 / 93 毫秒——中间工作环境重启过，不一定是同一台机器；r12 是 29 / 51 毫秒（另一台机器），"
            f"r10 时几次运行是 36–38 / 63–66 毫秒；手机会慢几倍）")
long_lines = re.findall(r"^长名字（120、400 个字符两档，共 (\d+) 个）.*?，(ICU|Python)：(.*?)；最慢的一次 ([\d.]+) 毫秒", icu, re.M)
assert len(long_lines) == 2 and all(x[0] == "860" and "全部按时结束，分组与逐步判断完全一致" in x[2] for x in long_lines), long_lines
long_time = ("最慢的一次：" + "、".join(f"{eng} {float(ms):.1f} 毫秒" for _, eng, _, ms in long_lines)
             + "（每次运行有出入：定稿以后和变异检查同时跑的第一遍是 ICU 33.3、Python 6.9 毫秒，r15 是 17.6、6.8 毫秒）")

off = read(f"{ev}/official-check.log")
assert "节点 2290 个（手写期望：手动组 632 个、自动类组 632 个）" in off and "只进手动组的 72 个" in off
assert "节点 2313 个（手写期望：手动组 24 个、自动类组 24 个）" in off
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
               "[stash] ChinaMax_Domain_For_Clash.txt：SHA-256 7722df98aedeb67b3572a9043ecf8edce6fe0dc89acbc684d1079eaa5e7994ed（1634434 字节",
               "（只在 DNS 段里用到的：private 131）") + RR_OUTBOUND:
    assert needle in rr, needle
assert "qwen.ai TXT → domestic" not in rr and "printer A → domestic（" not in rr
assert rr.count("扫了 19548 个代表主机（集合条目 17996 个、规则的值 1552 个；集合规模 {'geosite-cn': 9303}；正则 8 条") == 2
assert rr.count("名字会交给国内 DNS 的 17701 个：路由是国内直连 / 直连 / 拦截的 17701 个；归默认直连、可以切换的组的 0 个；走代理组的 0 个") == 2
assert rr.count("[符合] 官方内核核对 200 个主机") == 2
assert rr.count("290 条，全部符合人工期望") == 6
assert rr.count(f"为了判断 IP 规则而在本机解析过的域名：{RR_RESOLVED} 个里 43 个") == 2 and rr.count(f"为了判断 IP 规则而在本机解析过的域名：{RR_RESOLVED} 个里 16 个") == 1
assert rr.count(f"为了判断 IP 规则而在本机解析过的域名：{RR_RESOLVED} 个里 0 个") == 3
assert "stash-strict（没有官方内核，只有模拟器 + 真实的上游规则文件和直接订阅的上游国内域名清单）：290 条，全部符合人工期望" in rr
assert "release 分支 f7c0420" in rr and "rule-set 分支 be94d52" in rr
m = re.search(r"检查了 (\d+) 个字段 / 取值", read(f"{ev}/upstream-field-check.log"))
assert m and m.group(1) == "4589", "upstream-field-check.log 里的字段数"
ic = read(f"{ev}/icons-check.log")
assert "f250126f57228b0b32f3445b21078e382e6152e9" in ic and "合计 6,949,624 字节" in ic and "80 个地址逐个相同" in ic
assert ic.count("81 个策略组的图标都在图标仓库里，是 PNG，尺寸对") == 8 and "还没有上传" not in ic and "全部符合" in ic
assert "stash/stash.yaml：81 个策略组" in ic and "stash/stash-strict.yaml：81 个策略组" in ic
assert "1 个图在图标仓库里、清单没有收，没有比：Apple Push" in ic
cn = read(f"{ev}/cn-list-check.log")
assert "source/data/cn-domains.txt 与按固定快照重新生成的逐字节相同：后缀 6142 条、精确域名 12 条（快照 c1c2cf0d，2026-09-22）" in cn
assert "source/data/cn-domains-max.txt 与按固定快照重新生成的逐字节相同：后缀 111009 条、精确域名 268 条（快照 51d2e1dd，2026-09-21）" in cn
assert "source/data/LICENSE-domain-list-community.txt 与上游的 LICENSE 相同" in cn and "source/data/LICENSE-ios_rule_script.txt 与上游的 LICENSE 相同（GPL-2.0）" in cn
assert "--bm7" in cn.split("\n\n", 1)[0], "cn-list-check.log 的命令里要带 --bm7（核对大清单副本）"
ue = read(f"{ev}/upstream-evidence-check.log")
assert UE_NEEDLE in ue and "检查通过" in ue, ue[-800:]
assert CURSOR_NEEDLE in read(f"{ev}/cursor-迁入核对.md")
usnap = json.load(open(f"{ev}/upstream-snapshot.json", encoding="utf-8"))
cr = [x for x in usnap["client_restricted"] if x["service"] == "cn_common"]
assert len(cr) == 1 and cr[0]["clients"] == ["mihomo", "singbox", "stash"] and cr[0]["excluded"] == ["loon", "quantumultx"], cr
assert cr[0]["bm7_ads_shadowed_if_emitted"] == 954
assert "服务 `cn_common` 只写进 mihomo / singbox / stash：如果也写进 loon / quantumultx，本地规则会遮挡 blackmatrix7 AdvertisingLite 里 954 个条目" in read(f"{ev}/上游规则对照.md")

snap = json.load(open("tests/data/real_sets.json", encoding="utf-8"))
assert snap["generated"] == RUN_DAY and snap["source_version"] == "2026.10.13-2", (snap["generated"], snap["source_version"])
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
st = snap["sizes"]["stash"]
assert list(st) == ["https://raw.githubusercontent.com/blackmatrix7/ios_rule_script/master/rule/Clash/ChinaMax/ChinaMax_Domain_For_Clash.txt"], st
assert list(st.values())[0] == {"domain": 268, "ignored": {}, "ip": 0, "keyword": 0, "suffix": 111060}, st
assert snap["sizes"]["stash_geosite"] == {"category-ads-all": 911, "cn": 9303, "geolocation-!cn": 23905}
cons = snap["consistency"]
assert len(cons["mihomo"]["mismatch"]) == 0 and len(cons["singbox"]["mismatch"]) == 0 and len(cons["singbox112"]["mismatch"]) == 0
assert cons["mihomo"]["without_product_dns_rules"] == 136 and cons["mihomo"]["product_layer_checked"] == 136 and cons["mihomo"]["official_checked"] == 214
assert cons["singbox"]["without_product_dns_rules"] == 130
assert len(snap["hosts"]) == 266 and len(snap["ips"]) == 28
assert "逐条扫描" in snap["about"] and "全集" not in snap["about"] and "stash" in snap["about"]

cmp15 = read(f"{ev}/与上一版的对比.md")
assert cmp15.startswith("# 版本对比：r15 → r16\n"), cmp15[:40]
assert "| r15 | 632 | 0 | 632 | 0 |" in cmp15 and "| r16 | 632 | 0 | 632 | 0 |" in cmp15
assert "共 2254 个名字" in cmp15 and "### 手动组的归属变了（0 个）" in cmp15 and "成员变了（0 个）" in cmp15
assert cmp15.count("逐字节相同。") == 2, cmp15.count("逐字节相同。")
assert not re.search(r"^- 改动 `[^`]*`：\s*$", cmp15, re.M), "还有说不出改了什么的“改动”"
for needle in CMP_NEEDLES:
    assert needle in cmp15, needle
cmp7 = read(f"{ev}/与r7的对比.md")
assert cmp7.startswith("# 版本对比：r7 → r16\n"), cmp7[:40]
assert "| r7 | 585 | 47 | 541 | 91 |" in cmp7 and "| r16 | 632 | 0 | 632 | 0 |" in cmp7
assert "共 2254 个名字" in cmp7 and "### 手动组的归属变了（47 个）" in cmp7 and "成员变了（53 个）" in cmp7
cmpt = read(f"{W}/cmp16-time.txt").split("\n")
assert cmpt[0] > freeze and mtime(f"{ev}/与上一版的对比.md") <= cmpt[1] + "9", cmpt

# ---- 变异检查的说明（编号 → 发现它的测试，照变异日志）----
MUT_R16 = {"M123": "test_refuses_what_rfc1928_says_to_refuse", "M124": "test_refuses_what_rfc1928_says_to_refuse",
           "M125": "test_refuses_what_rfc1928_says_to_refuse", "M126": "test_records_names_and_addresses",
           "M127": "test_max_copy_change_date_follows_content", "M130": "test_one_placeholder_per_region_that_cannot_connect",
           "M133": "test_dns_block", "M134": "test_stash_uses_system_dns_for_lan_suffixes", "M135": "test_standard_rules_are_the_mihomo_rules",
           "M137": "test_pinned_paypal_node_keeps_its_placeholder", "M138": "test_build_refuses_a_broken_stash_config",
           "M139": "test_missing_placeholder", "M140": "test_wildcard_keys_are_quoted_like_the_docs"}
for name, test in MUT_R16.items():
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] {name} "))
    assert test in l and "输出含预期信息" in l, l[:400]
for i in list(range(71, N_MUT + 1)):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] M{i} "))
    if f"M{i}" not in res["not_seen"]:
        assert "输出含预期信息" in l, l[:200]
assert "DeprecationWarning" not in mut
partial_names = sorted(x for v in res["partial"].values() for x in v)
print("部分运行的：", res["partial"], "；未见预期信息：", res["not_seen"])
PARTIAL_EXPECTED = ⟦PARTIAL_EXPECTED⟧
assert partial_names == sorted(PARTIAL_EXPECTED), res["partial"]
MUT_R16_TEXT = ⟦MUT_R16_TEXT⟧
mut_cell = (f"{N_MUT} 类全部被发现，都是 r16 定稿（{freeze[:16]} UTC）以后在上面这个摘要、这个代码状态的代码上跑的（{window}）。"
            "“记录对应现在的配置”那两项——规则与 DNS 两段的摘要、拨号摘要——对改了规则、DNS 或出站的变异都会报："
            f"{N_MUT} 类里前一项报了 {len(fresh['with']['routing'])} 类、后一项报了 {len(fresh['with']['dial'])} 类；只靠这两项发现的一类都没有（r13 起）。"
            + MUT_R16_TEXT +
            "r15 加的 M119–M122 和更早的各类，发现它们的测试和 r15 时相同（M119 由路由用例，M120 由 `test_domain_trie_checks_patterns_like_mihomo`，"
            "M121 由 `test_max_copy_says_what_was_changed_and_when`，M122 由 `test_records_names_and_addresses`；M101–M118 见提交 `dc90da7` 里的这一页）。"
            "M45（回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，"
            "那一项把匹配放在带超时的子进程里，等满 5 分钟后失败并给出提示。⟦PARTIAL_TEXT_HERE⟧其余由对应的测试发现，每一类的失败项见日志")

# ---- 一次性核对：sing-box UDP 的定位（审核 r15 第三点），在定稿以后重跑 ----
p16 = read("handoff/notes/r15_review_probes.out")
assert mtime("handoff/notes/r15_review_probes.out") > freeze
pt = read(f"{W}/probe16-time.txt").split("\n")
assert pt[0].startswith("开始 ") and pt[1] == "exit 0" and pt[2].startswith("结束 "), pt
assert pt[0].split()[-2] == RUN_DAY and pt[0].split()[-1] > freeze[11:], pt
probe_window = f"（{pt[0].split()[-1][:5]}–{pt[2].split()[-1][:5]} UTC）"
v114, v112 = p16.split("\nsing-box 1.12.0（")
assert v114.startswith("sing-box 1.14.1（sing-box version 1.14.1）") and "sing-box version 1.12.0" in v112.split("\n")[0]


def block(text, title):
    i = text.index(f"  {title}\n")
    j = text.find("\n  ", i + 3)
    while j != -1 and text[j + 3] == " ":                                         # 子项缩进更深，跳过
        j = text.find("\n  ", j + 3)
    return text[i:j if j != -1 else len(text)]


SEL = "加 selector（final 是只含 SOCKS 出口的选择组）"
for title, dom in (("最简（没有路由规则，final 直接是 SOCKS 出口）", True), (SEL, False), ("加 sniff（路由第一条是 sniff 动作）", True),
                   ("sniff + selector", False), ("selector 换成 urltest（final 是只含 SOCKS 出口的自动测速组）", False)):
    b = block(v114, title)
    assert ("('domain', 'udp-probe.example')" in b) == dom and "('ip', '192.0.2.10')" in b and "不合规的报文：没有" in b, (title, b)
    assert ("unsupported address：0 行" in b) == dom, (title, b)
for title in ("加 resolve（路由第一条是 resolve 动作，交给本机 DNS 替身）", "resolve + selector（先解析成地址，再交给选择组）"):
    for v in (v114, v112):
        b = block(v, title)
        assert "[('ip', '127.0.1.1'), ('ip', '192.0.2.10')]" in b and "unsupported address：0 行" in b, (title, b)
for title in ("最简（没有路由规则，final 直接是 SOCKS 出口）", SEL, "加 sniff（路由第一条是 sniff 动作）", "sniff + selector"):
    b = block(v112, title)
    assert "('domain', 'udp-probe.example')" in b and "unsupported address：0 行" in b, (title, b)
b = block(v112, "selector 换成 urltest（final 是只含 SOCKS 出口的自动测速组）")
assert "[('ip', '192.0.2.10')]" in b and "unsupported address：0 行" in b, b                # 1.12.0 唯一的例外：域名那个包没发出，也没有报错
for proto in ("shadowsocks", "trojan", "vmess"):
    for v in (v114, v112):
        assert f"  {proto}：客户端握手 域名 ok、IPv4 ok；服务端日志里入站的 UDP 连接去：['192.0.2.10:443', 'udp-probe.example:443']；unsupported address 0 行" in v, (proto,)
for proto in ("shadowsocks", "trojan"):
    assert f"  {proto}（隔一个选择组）：客户端握手 域名 ok、IPv4 ok；服务端日志里入站的 UDP 连接去：['192.0.2.10:443']；unsupported address 1 行" in v114, proto
    assert f"  {proto}（隔一个选择组）：客户端握手 域名 ok、IPv4 ok；服务端日志里入站的 UDP 连接去：['192.0.2.10:443', 'udp-probe.example:443']；unsupported address 0 行" in v112, proto
assert "  vmess（隔一个选择组）：客户端握手 域名 ok、IPv4 ok；服务端日志里入站的 UDP 连接去：['192.0.2.10:443', 'udp-probe.example:443']；unsupported address 0 行" in v114
probe_cell = ("**1.14.1**：路由直接交给 SOCKS 出口时，域名、IPv4 两个目标都发出了；中间隔一个只含这个出口的选择组或自动测速组时，域名那个包被丢掉"
              "（日志 `packet upload closed: unsupported address`），IPv4 照常；路由第一条加 sniff 结果一样；先用 resolve 解析成地址再交给选择组，"
              "发出去的是地址、不丢。配对的服务端：Shadowsocks、Trojan 直接交给出口时服务端收到域名，隔一个选择组时域名那个包被丢、同样的报错；"
              "VMess 隔着选择组也收到了域名。**1.12.0**：各种组合下域名都发出了，只有“自动测速组 + SOCKS”这一种域名没发出、日志里也没有这条报错（原因没查）。"
              "和定稿之前那一次（写进 `docs/08` 第 11 轮的）结果相同。没有做的：虚拟网卡加假地址、1.14.3")

values = {"ICU_TIME": icu_time, "LONG_TIME": long_time, "MUT_CELL": mut_cell, "PROBE_CELL": probe_cell,
          "CMP_CELL": CMP_CELL, "R16_REAL_CELL": R16_REAL_CELL, "tests_n": N_TESTS, "mut_n": str(N_MUT),
          "freeze_utc": freeze[:16], "mut_window": window, "checks_window": checks_window, "probe_window": probe_window,
          "run_window": f"{RUN_DAY}（UTC）"}

# 产物大小、摘要与文档里写的一致
sizes = {rel: os.path.getsize(os.path.join("dist", rel)) for rel in man["outputs"]}
assert (sizes["loon/loon.conf"], sizes["quantumultx/quantumultx.conf"], sizes["mihomo/mihomo-profile.yaml"], sizes["mihomo/mihomo-core.yaml"],
        sizes["sing-box/sing-box-1.14.json"], sizes["sing-box/sing-box-1.12.json"], sizes["stash/stash.yaml"]) \
    == (241985, 404505, 280322, 280505, 79164, 79190, 251084), sizes
assert (sizes["loon/loon-strict.conf"], sizes["quantumultx/quantumultx-strict.conf"], sizes["stash/stash-strict.yaml"], sizes["loon/rules/cn-domains.list"],
        sizes["quantumultx/rules/cn-domains.list"], sizes["quantumultx/rules/cn-domains-max.list"],
        sizes["quantumultx/rules/domain-fallback.list"]) == (243317, 406482, 252016, 165629, 196326, 3521714, 629), sizes
doc05 = read("docs/05-验收记录.md")
for rel, v in man["outputs"].items():
    sha = v["sha256"] if isinstance(v, dict) else v
    assert f"`{sha[:8]}…`" in doc05, rel
assert digest in doc05 and state in doc05
# 和 r15 的 dist 比：哪些文件变了（r15 从 git 取到仓库以外，见 r16-as-used/README.md）
old = os.path.join(W, "r15", "dist")
changed, new = [], []
for rel in sorted(set(man["outputs"]) | {"manifest.json"}):
    a, b = os.path.join(old, rel), os.path.join("dist", rel)
    if not os.path.exists(a):
        new.append(rel)
    elif not filecmp.cmp(a, b, shallow=False):
        changed.append(rel)
assert new == ["stash/stash-strict.yaml", "stash/stash.yaml"], new
assert changed == ["loon/loon-strict.conf", "loon/loon.conf", "manifest.json", "mihomo/mihomo-core.yaml", "mihomo/mihomo-profile.yaml",
                   "quantumultx/quantumultx-strict.conf", "quantumultx/quantumultx.conf", "quantumultx/rules/cn-domains-max.list"], changed
for rel in ("loon/loon.conf", "loon/loon-strict.conf", "quantumultx/quantumultx.conf", "quantumultx/quantumultx-strict.conf",
            "mihomo/mihomo-core.yaml", "mihomo/mihomo-profile.yaml"):
    a, b = read(os.path.join(old, rel)), read(os.path.join("dist", rel))
    assert a.replace("2026.10.13-1", "2026.10.13-2") == b, rel                                   # 只有版本号变了
yaml = __import__("yaml")
pol = yaml.safe_load(read("dist/mihomo/mihomo-core.yaml"))["dns"]["nameserver-policy"]
assert len(pol) == 745 and sum(1 for v in pol.values() if v == ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"]) == 732, len(pol)
assert sum(1 for v in pol.values() if v == ["system"]) == 3 and sum(1 for v in pol.values() if v == ["https://223.5.5.5/dns-query", "https://1.12.12.12/dns-query"]) == 10
for rel in ("stash/stash.yaml", "stash/stash-strict.yaml"):
    c = yaml.safe_load(read(os.path.join("dist", rel)))
    assert len(c["proxies"]) == 7 and all(p["server"] == "127.0.0.1" and p["port"] == 1 for p in c["proxies"]), rel
    assert len(c["proxy-groups"]) == 81 and c["rules"][-1] == "MATCH,国外默认" and c["dns"]["follow-rule"] is False, rel
    assert ("rule-providers" in c) == rel.endswith("strict.yaml"), rel

for k, v in values.items():
    print(f"⟦{k}⟧ = {v[:200]}")
files = (["README.md", "README.zh-CN.md", "PROJECT_STATE.md", "00-审核说明.md", "handoff/README.md"]
         + sorted(os.path.join("docs", f) for f in os.listdir("docs") if f.endswith(".md")))
left = []
for p in files:
    s = read(p)
    s2 = re.sub(r"⟦([^⟧]+)⟧", lambda mm: values.get(mm.group(1), mm.group(0)), s)
    if s2 != s and not dry:
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(s2)
    if s2 != s:
        print("已替换：" if not dry else "会替换：", p, len(re.findall(r"⟦", s)))
    left += [(p, x) for x in re.findall(r"⟦[^⟧]*⟧", s2) if x != "⟦名字⟧"]
print("剩余占位符：", left)
if dry:
    sys.exit(0)
assert not left
for p, needles in DOC_NEEDLES_R16:
    s = read(p)
    for n in needles:
        assert n in s, (p, n)
# 旧的说法不应再作为现状出现（历史记录里的除外，逐个看过）
HIST = ["docs/00-需求原文.md", "docs/08-外部审核记录.md"]
for p in files:
    s = read(p)
    for k, allowed in STALE.items():
        if k in s and p not in allowed and p not in HIST:
            raise AssertionError(f"{p} 里还有旧的说法：{k}")
    # “全集”只能出现在说明旧名字的地方
    if p not in HIST:
        for mm in re.finditer("全集", s):
            ctx = s[max(0, mm.start() - 8):mm.start() + 12]
            assert re.search(r"叫(它)?“全集|“全集一致性”改名|“全集一致性”→|原“全集", ctx), (p, ctx)
print("核对通过")
