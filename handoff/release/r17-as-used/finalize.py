"""把文档里的占位符 ⟦…⟧ 换成最终运行得到的数字，并核对文档里写的数字和日志、产物一致（r17 用的；照 r16-as-used/finalize.py 改的）。
r17 处理 GPT 对 r16 的审核；代码定稿两次（04:02 那一次之后跑版本对比，查出报告认不出 Stash 的新筛选，改了对比工具，04:20 重新定稿；
第一次定稿以后开始的变异检查和全部检查都停掉作废）。变异检查跑完以后再跑一遍全部检查，交付的日志是这一遍的。
数字都从日志和产物里读。用法（在工程根目录）：python3 handoff/release/r17-as-used/finalize.py <变异日志目录> [--dry]"""
import datetime, filecmp, json, os, re, subprocess, sys

D = os.path.abspath(sys.argv[1])
dry = "--dry" in sys.argv
ev = "docs/evidence"
RUN_DAY = "2026-10-14"                                                            # 全部检查、一次性核对、快照、变异检查都在这一天
DIGEST = "2405728aaec1c9b6a62032f1fc2ecb56e9fb234e37e14485b928f3030f29f58d"     # r17：生成器 1.10.0、统一源 2026.10.14-1
STATE = "0a3d47109f9de1c460f90eb3d13e74711cf0430f0d2cab43f876fb503f4db93d"
FREEZE = "2026-10-14 04:20:38"
FREEZE_A = "2026-10-14 04:02:52"                                                  # 第一次定稿（作废）
N_TESTS, N_MUT, N_MIHOMO_DNS = "305", 154, "15"
ENV = "Python：Python 3.13.16，PyYAML：6.0.1"
R16 = "a999d81"                                                                   # GPT 审的 r16
W = os.path.expanduser("~/proxy-work")

# ---- 这一版特有的说法（从日志里读到以后照抄；下面的断言核对它们确实在日志 / 报告里）----
RR_RESOLVED = "261"
RR_OUTBOUND = (                                                                  # 出站核对、节点收到的目标、组切换以后（照日志原文；和 r16 相同）
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
               "大小：251,084 → 251,780 字节。", "大小：252,016 → 252,712 字节。",
               "- 删除一行：`# 统一源版本 2026.10.13-2；目标：Loon 3.x（规则匹配顺序依据官方文档：本地 > 插件 > 订阅，域名规则先于 IP 规则，要求 3.0.3+）`",
               "- 新增一行：`# 统一源版本 2026.10.14-1；目标：Loon 3.x（规则匹配顺序依据官方文档：本地 > 插件 > 订阅，域名规则先于 IP 规则，要求 3.0.3+）`",
               "没有变化的分段：DNS（dns）（4 条）、规则（rules）（1009 条）、其余设置（4 条）。",
               "**策略组（proxy-groups）**：新增 0 条，删除 0 条，改动 26 条；两版都有的条目顺序不变。",
               "- 改动 8 条（`PayPal·美国固定`、`其他地区`、`香港·手动` 等，改法相同）：去掉 `\"filter\": \"<筛选：上一版 各自的地区>\"`；加上 `\"filter\": \"<筛选：Stash宽 各自的地区>\"`",
               "- 改动 18 条（`香港·自动`、`香港·故障转移`、`香港·负载均衡` 等，改法相同）：去掉 `\"filter\": \"<筛选：上一版严 各自的地区>\"`；加上 `\"filter\": \"<筛选：Stash严 各自的地区>\"`",
               "没有变化的分段：DNS（dns）（4 条）、规则（rules）（1010 条）、其余设置（5 条）。",
               "有差异的分段和 `stash/stash.yaml` 的一模一样（策略组（proxy-groups）），不重复列出。",
               "## 六、严格版", "### `stash/stash-strict.yaml` 对照 `stash/stash.yaml`", "大小：标准版 251,780 字节，严格版 252,712 字节。",
               "大小：标准版 241,985 字节，严格版 243,317 字节", "大小：标准版 404,505 字节，严格版 406,482 字节",
               "`loon/rules/cn-domains.list`：165,629 字节，规则 6,133 条（DOMAIN 12、DOMAIN-SUFFIX 6,121）。和 r16 的一模一样。",
               "`quantumultx/rules/cn-domains.list`：196,326 字节，规则 6,133 条（HOST 12、HOST-SUFFIX 6,121）。和 r16 的一模一样。",
               "`quantumultx/rules/cn-domains-max.list`：3,521,714 字节，规则 111,182 条（HOST 252、HOST-SUFFIX 110,930）。和 r16 的一模一样。",
               "`quantumultx/rules/domain-fallback.list`：629 字节，规则 1 条（HOST-KEYWORD 1）。和 r16 的一模一样。",
               "`<筛选：Stash宽 hk>` / `<筛选：Stash严 hk>`")
CMP_CELL = ("Loon、Quantumult X、mihomo 的六份配置只有文件头注释里的统一源版本号变了（各分段的条目完全相同，大小不变），策略组、规则、DNS 都没有变；"
            "sing-box 的两份逐字节相同；Stash 的两份只有策略组的 `filter` 变了（26 个带筛选的组：同一条正则，开头多一段排除内置策略名），"
            "规则、DNS 和其余设置没有变；大清单副本、两份自有清单和域名兜底文件和 r16 的一模一样")
R17_REAL_CELL = ("路由 270 个目标（和 r16 相同）在 mihomo v1.19.31、sing-box v1.14.1 与 v1.12.0 上都与人工期望一致；DNS 去向、连接时的解析、境外 DNS 不应答、"
                 "出站时的解析（含节点收到的目标）、默认直连的组切到代理以后，结果和 r16 逐条相同——改严以后的 SOCKS5 接收端、DNS 替身一次都没有报"
                 "“不合规”“读不懂的查询”；逐条扫描两个内核走代理组的仍是 0 个。Stash 只有模拟器：两份各 290 条全部符合期望；为了判断 IP 规则在本机解析过的域名，"
                 "标准版 261 个里 16 个、严格版 0 个（`docs/evidence/real-route-check.log`）。")
H8 = "docs/08-外部审核记录.md"
DOC_NEEDLES_R17 = (
    ("README.md", ["tests-305%20passing", "305 automated tests", "2026.10.14-1", "This is r17", "632 hand-labelled", "12–16 KB",
                   "43 service groups", "81 policy groups", "270 targets", "stash-strict.yaml", "15 on mihomo", "561 community-sourced",
                   "Twelve rounds of external input", "unsupported address", "item 22 of `docs/06`", "One rule source. Five clients.",
                   "tests were run on Linux (Python 3.13) in a cloud session on 2026-10-14 (UTC)", "DIRECT, REJECT and REJECT-DROP",
                   "four cases in `docs/09`", "None of r12–r17 was pushed"]),
    ("README.zh-CN.md", ["自动测试 305 项", "2026.10.14-1", "（r17：处理 GPT 对 r16 的审核", "632 个人工写期望", "2290 个假节点",
                         "每条 12–16 KB", "81 个策略组", "270 个目标", "mihomo 15 条", "r14 起两个内核都是 0 个", "Python 3.13.16",
                         "561 条社区来源规则", "外部意见一共 12 轮", "这一版的检查是 2026-10-14（UTC）在云端会话里跑的", "sing-box 17,701 个代表主机",
                         "`docs/06` 第 22 项", "`dist/stash/stash.yaml`", "r12–r17 做完时都没有立刻推到"]),
    ("PROJECT_STATE.md", ["r17：统一源 2026.10.14-1", "生成器 1.10.0", "T30 第 12 轮", "第 22 项", "确认 305 项通过", "需要再跑一次 305 项",
                          "r13–r17 在 `claude/r12-gpt-review-handling-q4onlv` 分支", "`2026.10.14-1` 是 r17"]),
    ("00-审核说明.md", ["## 本轮（r17，统一源 2026.10.14-1）改了什么", "294 → 305 项", "141 → 154 类", "公开产物仍是 15 个",
                        "**这一轮检查的时间**：2026-10-14（UTC）", "代码 2026-10-14 04:20 UTC 定稿", "R16-F01", "R16-F02", "R16-F03", "## 本轮请重点看",
                        "“2026-10-13（r16）”“2026-10-14（r17）”六节"]),
    ("docs/05-验收记录.md", ["305 项全部通过", "逐一注入 154 类错误", "2026.10.14-1（r17", "Python 3.13.16，PyYAML 6.0.1", "2290 个假节点",
                             "860 个 120 / 400 个字符", "270 个目标", "**04:02 第一次定稿**", "第二次定稿**", "mihomo 15 条", "`tests/test_real_data.py`，51 项",
                             "`tests/test_strict.py`，34 项", "`tests/test_stash.py`，29 项", "`tests/test_regions.py`，66 项", "`tests/test_compare_versions.py`，14 项",
                             "222,353 个里走代理组的 0 个", "官方内核核对了其中 214 个", "81 个策略组", "6,949,624 字节", "111,182 条", "111,328 条",
                             "自有拦截 98", "154 类全部被发现", "与上一版（r16）对比", "GPT 审核 r15 建议的 sing-box UDP 定位", "Stash 是 16 个",
                             "| Stash iOS | Stash iPadOS | Stash macOS |", "Stash 带前缀的筛选在 ICU 上", "人工维护的日期加一份内容快照"]),
    ("docs/02-语法依据与能力矩阵.md", ["270 个目标", "81 个策略组", "6,949,624 字节", "`cn-domains-max.list`", "**1.14.1 没有发出**", "`tests/test_regions.py` 66 项",
                                     "v1.19.20", "## Loon / Quantumult X 严格版用到的写法（2026-10-06）", "ExampleRule.lsr", "## Stash（2026-10-13，r16）", "2290 个节点名",
                                     "44 项内容（42 个页面", "r17 起每条节点筛选的开头排除 DIRECT、REJECT、REJECT-DROP"]),
    ("docs/03-DNS决策表.md", ["| mihomo | 224,087 个", "| sing-box（两个版本相同） | 19,548 个代表主机", "290 条用例和排除项", "现在 732 条", "111,047 条",
                             "6,133 条", "653 个后缀", "1.14.1 没有发出这个包", "## 出站时的解析：代理出口会不会再解析目标（2026-10-07，r14）",
                             "**节点收到的到底是什么**", "`system` 指的是谁", "187 条 IP 段", "49 个顶级域", "110,712 条",
                             "## Stash（2026-10-13，r16；2026-10-14 r17 改写了不用 `follow-rule` 的理由）", "定位到了“组”这一层",
                             "都没有验证过**——不是“做不到”", "**可以试的写法（GPT 审核 r16 提的，待实测，这一版没有做）**"]),
    ("docs/06-已知限制与待决事项.md", ["## 2026-10-14（r17）：处理 GPT 对 r16 的审核", "## 2026-10-13（r16）：Stash 的配置，和处理 GPT 对 r15 的审核",
                                      "| 22 | sing-box 1.14.1", "自有拦截另有 98 条", "| 21 | 默认直连、可以切到代理的组", "## 2026-10-13 你定下的事项",
                                      "| ① 维持现状 | **配置不变**", "## 2026-10-07 你定下的事项", "870 条服务规则", "105,317 条", "632 个带期望的节点名",
                                      "**r17 起每条节点筛选的开头都排除 DIRECT、REJECT、REJECT-DROP 这几个名字**", "不能把占位节点当成已经验证的安全保证",
                                      "那只是可能退回以后的表现，没有验证"]),
    (H8, ["## 第 12 轮：2026-10-14，GPT 审核 r16", "294 → 305 项", "141 → 154 类", "docs/evidence/gpt-r16/", "r15_review_probes.out", "## 第 11 轮", "270 个目标",
          "r17_stash_filters_icu.out", "| 6 | 第一次定稿（04:02）以后跑版本对比"]),
    ("docs/09-真机验收操作清单.md", ["对应统一源 2026.10.14-1", "81 个策略组", "111,182 条", "unsupported address", "## 1b. 严格版", "## 1c. Stash",
                                     "afpapi.alimama.com", "courier-push-apple.com.akadns.net", "251,780 字节", "252,712 字节", "分四种情况",
                                     "r12–r17 交付时都没有推 `main`"]),
    ("docs/01-导入、更新、诊断与回滚.md", ["2026.10.14-1", "81 个策略组", "--bm7", "DNS 覆写", "v1.19.20", "f250126", "2001:2::", "stash.yaml",
                                          "**r12–r17 交付时都没有推到 `main`**"]),
    ("docs/07-需求对照.md", ["### 2026-10-12 至 10-13", "R14-F02", "cd63eba", "### 2026-10-13（GPT 审核 r15 之后，r16）", "632 个人工写期望的节点名",
                             "### 2026-10-14（GPT 审核 r16 之后，r17）", "2026-10-14 更正"]),
    ("docs/00-需求原文.md", ["## 补充（2026-10-12 至 10-13", "改吧 改完连 stash 一起写最好再让他审核终版",
                             "## 补充（2026-10-14，r16 交付以后，GPT 审完 r16；对话中给出，照录）", "> r16 仍有 3 处需要处理，尚不能认定为真机验收通过的终版。"]),
    ("handoff/README.md", ["## 14. r17 的补充", "r13–r17", "第 10–14 节", "**定稿了两次**"]),
)
# 旧的说法不应再作为现状出现（历史记录里的除外：docs/00 只追加，docs/08 是逐轮的记录）
STALE = {k: [] for k in (
    "tests-294", "294 automated", "自动测试 294 项", "294 项全部通过", "确认 294 项通过", "注入 141 类", "这份说明对应 `2026.10.13-2`",
    "source version **2026.10.13-2**", "对应统一源 2026.10.13-2", "This is r16.", "Eleven rounds of external input", "外部意见一共 11 轮",
    "r12–r16 都没有推到", "r12–r16 交付时都没有推", "r12–r16 做完时", "None of r12–r16", "标准版 251,084 字节，严格版 252,016 字节）",
    "`tests/test_stash.py`，23 项", "`tests/test_real_data.py`，47 项", "`tests/test_compare_versions.py`，13 项", "网页、视频照常，",
    "国内网站最快，", "“国内网站不能变慢”首先受影响", "原话在 `docs/00` 最后", "`docs/00` 最后一节 |",
    "如果每个组里都是全部 7 个占位节点", "filter` 管不管 `proxies` 里直接写的节点（不管的话", "<筛选：未知的正则>\"")}
STALE.update({"44 页": ["docs/02-语法依据与能力矩阵.md", "docs/06-已知限制与待决事项.md", "docs/07-需求对照.md", "00-审核说明.md", "docs/05-验收记录.md"],
              "原话见 `docs/00` 最后": ["handoff/README.md", "00-审核说明.md"],             # 这两处是在说这种写法本身
              "141 类全部被发现": [H8], "r16：统一源 2026.10.13-2": [H8], "2247 个名字": [H8, "docs/02-语法依据与能力矩阵.md"]})
# 第 22 项等你定：不能写成已经定了
STALE.update({k: ["docs/00-需求原文.md"] for k in ("第 22 项已定", "第 22 项你选了")})


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def mtime(p):
    return datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


man = json.load(open("dist/manifest.json", encoding="utf-8"))
digest = man["source_sha256"]
assert man["source_version"] == "2026.10.14-1" and man["generator_version"] == "1.10.0", man
assert digest == DIGEST, digest
freeze = read(f"{W}/freeze17-time.txt").strip()                                   # 第二次定稿时记下的时间（UTC）
state = subprocess.run(["bash", "handoff/release/code_state.sh"], capture_output=True, text=True, check=True).stdout.strip()
assert state == read(f"{W}/freeze17-state.txt").strip(), "代码在定稿之后变过"
assert freeze == FREEZE and state == STATE, (freeze, state)
assert read(f"{W}/freeze17a-time.txt").strip() == FREEZE_A and read(f"{W}/freeze17a-state.txt").strip() != STATE

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
assert all(s["start"][:10] == RUN_DAY and s["end"][:10] == RUN_DAY for s in segs), segs
assert all(s["start"] > freeze for s in segs), (segs, freeze)
assert sum(len(x["ids"]) for x in segs) == N_MUT
mut_end = segs[-1]["end"]
if len(segs) == 1:
    window = f"三批并行，{segs[0]['start'][11:16]}–{segs[0]['end'][11:16]} UTC，一次跑完，中间没有中断"
else:
    window = ("三批并行，分 " + str(len(segs)) + " 段：" + "；".join(f"{x['start'][11:16]}–{x['end'][11:16]} UTC 跑完 {len(x['ids'])} 类" for x in segs)
              + "；前面的段停在工作环境停掉的时候，各段之间代码没有改动，后一段开始前重新核对过代码状态和运行环境")
fresh = res["fresh"]
assert fresh["solo"] == [], fresh
mut_a = [l for name in sorted(os.listdir(f"{W}/mut17a")) if name.startswith("mut-") and name.endswith(".log")
         for l in read(f"{W}/mut17a/{name}").splitlines() if l.startswith("[")]
assert len(mut_a) == 7 and all(l.startswith("[发现]") for l in mut_a), mut_a          # 第一次定稿以后、停掉之前跑完的 7 类

# ---- 全部检查（变异检查跑完以后的那一遍）----
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
checks_window = f"{min(starts.values())[11:16]}–{max(ends.values())[11:16]} UTC"
ct = read(f"{W}/checks17b-time.txt").split("\n")
assert ct[0] > mut_end and ct[0] <= min(starts.values()) and ct[1] >= max(ends.values()), ct
assert read(f"{W}/checks17b.out").rstrip().endswith("全部检查通过。\nexit 0"), "run_checks.sh 没有以“全部检查通过。”结束"
c1 = read(f"{W}/checks17-time.txt").split("\n")                                   # 第二次定稿以后、和变异检查同时跑的第一遍
assert c1[0] > freeze and read(f"{W}/checks17.out").rstrip().endswith("全部检查通过。\nexit 0"), c1
checks1_window = f"{c1[0][11:16]}–{c1[1][11:16]} UTC"
first = f"{W}/checks17-logs"                                                       # 第一遍的日志（第二遍开始前复制出来的）

tests = read(f"{ev}/tests.log")
m = re.search(r"^Ran (\d+) tests in [\d.]+s\n\nOK\b(.*)$", tests, re.M)
assert m, "tests.log 里没有 OK"
assert "skipped" not in m.group(2), "有跳过的测试：" + m.group(2)
assert m.group(1) == N_TESTS, m.group(1)
# 真正的警告是“…: ResourceWarning: unclosed …”这样的行；r17 新加的那项测试的说明文字里提到了 ResourceWarning 这个词（unittest -v 会把说明的第一行印出来），不算
assert not re.search(r"\w+Warning: ", tests), re.findall(r".*\w+Warning: .*", tests)[:3]
assert tests.count("ResourceWarning") == 1 and "那一处 ResourceWarning，同一类写法" in tests
NEW_R17 = ("test_no_filter_picks_a_builtin_policy", "test_without_the_prefix_other_regions_would_pick_direct",
           "test_prefix_changes_nothing_for_node_names", "test_prefix_only_goes_after_the_documented_head",
           "test_filter_that_picks_a_builtin_policy", "test_build_refuses_a_filter_that_picks_a_builtin_policy",
           "test_records_every_request_it_refuses", "test_dns_stub_keeps_queries_it_cannot_read",
           "test_every_dns_stub_is_closed_through_close_stubs", "test_code_closes_the_files_it_opens",
           "test_stash_filters_get_their_own_label")
for t in ("test_refuses_what_rfc1928_says_to_refuse", "test_records_names_and_addresses", "test_blocked_environment_is_an_error_not_a_result",
          "test_groups_are_the_mihomo_groups", "test_stash", "test_each_filter_group_picks_exactly_its_own_placeholder",
          "test_build_refuses_a_broken_stash_config", "test_max_copy_change_date_follows_content") + NEW_R17:
    # 测试带说明文字时，unittest -v 把“... ok”写在说明的那一行，不在名字那一行；整体是 OK（上面已经断言），这里只核对它们确实跑了
    assert re.search(rf"^{t} \(test_\w+\.\w+\.{t}\)", tests, re.M), t
per_file = {}
for mod, _cls, _name in set(re.findall(r"\((test_\w+)\.(\w+)\.(\w+)\)", tests)):
    per_file[mod] = per_file.get(mod, 0) + 1
assert sum(per_file.values()) == int(N_TESTS), per_file
assert (per_file["test_real_data"], per_file["test_strict"], per_file["test_dns_lan"], per_file["test_compare_versions"],
        per_file["test_local_and_private"], per_file["test_icons"], per_file["test_source"], per_file["test_stash"], per_file["test_regions"]) \
    == (51, 34, 15, 14, 9, 9, 18, 29, 66), per_file

ICU_RX = r"ICU 平均每次匹配：宽 (\d+) 微秒、严 (\d+) 微秒.*?Loon (\d+) 毫秒，Quantumult X（26 个策略各一条）(\d+) 毫秒"
icu = read(f"{ev}/icu-check.log")
assert "13 条（宽 7 条、严 6 条）× 2290 个节点名（其中 632 个有手写的期望）" in icu
assert "× 2313 个节点名" in icu
m = re.search(ICU_RX, icu)
m1 = re.search(ICU_RX, read(f"{first}/icu-check.log"))
assert m and m1, "icu-check.log 里没有耗时行"
icu_time = (f"这次运行 ICU 平均每次匹配：宽的 {m.group(1)} 微秒、严的 {m.group(2)} 微秒（含调用开销）；按 300 个节点估算 Loon 约 {m.group(3)} 毫秒、"
            f"Quantumult X 约 {m.group(4)} 毫秒（每次运行有出入：同一个云端会话里，定稿以后和变异检查同时跑的第一遍是 {m1.group(1)} / {m1.group(2)} 微秒、"
            f"{m1.group(3)} / {m1.group(4)} 毫秒，r16 是 41 / 73 毫秒，r15 是 42 / 75 毫秒，r14 是 52 / 91 毫秒——中间工作环境重启过，不一定是同一台机器；"
            f"r12 是 29 / 51 毫秒（另一台机器），r10 时几次运行是 36–38 / 63–66 毫秒；手机会慢几倍）")
LONG_RX = r"^长名字（120、400 个字符两档，共 (\d+) 个）.*?，(ICU|Python)：(.*?)；最慢的一次 ([\d.]+) 毫秒"
long_lines = re.findall(LONG_RX, icu, re.M)
long_first = re.findall(LONG_RX, read(f"{first}/icu-check.log"), re.M)
assert len(long_lines) == 2 and all(x[0] == "860" and "全部按时结束，分组与逐步判断完全一致" in x[2] for x in long_lines), long_lines
assert len(long_first) == 2
long_time = ("最慢的一次：" + "、".join(f"{eng} {float(ms):.1f} 毫秒" for _, eng, _, ms in long_lines)
             + "（每次运行有出入：定稿以后和变异检查同时跑的第一遍是 " + "、".join(f"{eng} {float(ms):.1f}" for _, eng, _, ms in long_first)
             + " 毫秒，r16 是 ICU 19.6、Python 7.5 毫秒）")

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
assert "operation not permitted" not in rr and "不合规" not in rr and "读不懂的查询" not in rr
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

snap = json.load(open("tests/data/real_sets.json", encoding="utf-8"))
assert snap["generated"] == RUN_DAY and snap["source_version"] == "2026.10.14-1", (snap["generated"], snap["source_version"])
mh = snap["official"]["mihomo"]
assert mh["dial"]["node gateway.lan"] == "system" and mh["dns"]["printer A"] == "system" and len(mh["dial_sha256"]) == 64
assert mh["dns"]["tplinkwifi.net A"] == "system" and mh["dns"]["time.windows.com A"] == "domestic"
assert mh["dns"]["qwen.ai TXT"] == "foreign" and mh["dns"]["tlu.dl.delivery.mp.microsoft.com TXT"] == "domestic"
assert mh["outbound"]["mihomo-wireguard-tcp"]["qwen.ai"] == "foreign" and mh["outbound_without_product_layer"]["qwen.ai"] == "domestic"
assert mh["outbound_received"]["mihomo-socks5-tcp"]["qwen.ai"] == "domain" and mh["outbound_received"]["mihomo-socks5-udp"]["qwen.ai"] == "ip"
assert mh["outbound_switched"]["mihomo-wireguard-tcp"] == {"api.bilibili.com": "domestic", "www.apple.com": "foreign", "www.apple.com.cn": "domestic", "www.qq.com": "domestic"}
sb, sb12 = snap["official"]["singbox"], snap["official"]["singbox112"]
assert sb["outbound_received"]["singbox-socks-udp"]["qwen.ai"] == "-" and sb12["outbound_received"]["singbox-socks-udp"]["qwen.ai"] == "domain"
# 和 r16 的快照比：只有日期、版本号和 mihomo 配置的摘要（注释里的版本号）变了
old_snap = json.load(open(os.path.join(W, "r16", "tests", "data", "real_sets.json"), encoding="utf-8"))
for k in ("generated", "source_version"):
    old_snap.pop(k), snap.pop(k)
old_snap["official"]["mihomo"].pop("config_sha256"), snap["official"]["mihomo"].pop("config_sha256")
assert old_snap == snap, "快照除了日期、版本号和 mihomo 配置的摘要以外还有别的变了"

cmp16 = read(f"{ev}/与上一版的对比.md")
assert cmp16.startswith("# 版本对比：r16 → r17\n"), cmp16[:40]
assert "| r16 | 632 | 0 | 632 | 0 |" in cmp16 and "| r17 | 632 | 0 | 632 | 0 |" in cmp16
assert "共 2254 个名字" in cmp16 and "### 手动组的归属变了（0 个）" in cmp16 and "成员变了（0 个）" in cmp16
assert cmp16.count("逐字节相同。") == 2, cmp16.count("逐字节相同。")
assert "未知的正则>\"" not in cmp16
assert not re.search(r"^- 改动 `[^`]*`：\s*$", cmp16, re.M), "还有说不出改了什么的“改动”"
for needle in CMP_NEEDLES:
    assert needle in cmp16, needle
cmp7 = read(f"{ev}/与r7的对比.md")
assert cmp7.startswith("# 版本对比：r7 → r17\n"), cmp7[:40]
assert "| r7 | 585 | 47 | 541 | 91 |" in cmp7 and "| r17 | 632 | 0 | 632 | 0 |" in cmp7
assert "共 2254 个名字" in cmp7 and "### 手动组的归属变了（47 个）" in cmp7 and "成员变了（53 个）" in cmp7
cmpt = read(f"{W}/cmp17-time.txt").split("\n")
assert cmpt[0] > freeze and mtime(f"{ev}/与上一版的对比.md") <= cmpt[1] + "9", cmpt

# ---- 变异检查的说明（编号 → 发现它的测试，照变异日志）----
MUT_TESTS = {"M123": "test_refuses_what_rfc1928_says_to_refuse", "M124": "test_refuses_what_rfc1928_says_to_refuse",
             "M125": "test_refuses_what_rfc1928_says_to_refuse", "M126": "test_records_names_and_addresses",
             "M127": "test_max_copy_change_date_follows_content", "M130": "test_one_placeholder_per_region_that_cannot_connect",
             "M133": "test_dns_block", "M134": "test_stash_uses_system_dns_for_lan_suffixes", "M135": "test_standard_rules_are_the_mihomo_rules",
             "M137": "test_pinned_paypal_node_keeps_its_placeholder", "M138": "test_build_refuses_a_broken_stash_config",
             "M139": "test_missing_placeholder", "M140": "test_wildcard_keys_are_quoted_like_the_docs",
             "M128": "test_blocked_environment_is_an_error_not_a_result", "M136": "test_strict_list_catches_what_both_geosite_sets_miss",
             "M141": "test_no_domain_is_resolved_locally_for_rule_matching", "M132": "test_strict_list_before_geolocation",
             "M131": "test_missing_placeholder", "M129": "test_strict_configs_never_resolve_for_rule_matching",
             "M111": "test_max_copy_is_the_upstream_list_minus_locally_covered_entries", "M121": "test_max_copy_says_what_was_changed_and_when",
             # r17
             "M143": "test_build_refuses_a_filter_that_picks_a_builtin_policy", "M144": "test_filter_that_picks_a_builtin_policy",
             "M145": "test_prefix_changes_nothing_for_node_names", "M146": "test_records_every_request_it_refuses",
             "M147": "test_records_every_request_it_refuses", "M148": "test_records_every_request_it_refuses",
             "M149": "test_records_every_request_it_refuses", "M150": "test_dns_stub_keeps_queries_it_cannot_read",
             "M151": "test_dns_stub_keeps_queries_it_cannot_read", "M152": "test_every_dns_stub_is_closed_through_close_stubs",
             "M153": "test_code_closes_the_files_it_opens", "M154": "test_stash_filters_get_their_own_label"}
for name, test in MUT_TESTS.items():
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] {name} "))
    assert test in l and "输出含预期信息" in l, l[:400]
l142 = next(x for x in mut.splitlines() if x.startswith("[发现] M142 "))
assert "输出含预期信息" in l142, l142[:400]                                         # 预期信息是“内置策略”（生成时的报错）
for i in list(range(71, N_MUT + 1)):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] M{i} "))
    if f"M{i}" not in res["not_seen"]:
        assert "输出含预期信息" in l, l[:200]
assert "DeprecationWarning" not in mut
partial_names = sorted(x for v in res["partial"].values() for x in v)
print("部分运行的：", res["partial"], "；未见预期信息：", res["not_seen"])
PARTIAL_EXPECTED = sorted(os.environ.get("PARTIAL_EXPECTED", "M6 M9 M31 M89 M90").split())     # 跑完以后按日志确认，写进 README
assert partial_names == PARTIAL_EXPECTED, res["partial"]
MUT_R17_TEXT = ("处理 GPT 审核 r16 新加的八类：M142（Stash 的筛选又不排除内置策略的名字）被生成时的核对拦住（生成器报“会选中内置策略”，用到生成结果的测试因此报错）；"
                "M143（生成时不核对）由 `tests/test_stash.py` 的 `test_build_refuses_a_filter_that_picks_a_builtin_policy` 发现；"
                "M144（结构检查不核对）由 `test_filter_that_picks_a_builtin_policy` 发现；M145（排除得太宽）由 `test_prefix_changes_nothing_for_node_names` 发现；"
                "M146–M149（SOCKS5 接收端又漏记地址类型不认识、只发了一部分、不支持的命令，或者把空连接记成不合规）都由 `tests/test_real_data.py` 的 "
                "`test_records_every_request_it_refuses` 发现。自查的五类：M150、M151（DNS 替身又丢掉读不懂的查询、关的时候不报错）由 "
                "`test_dns_stub_keeps_queries_it_cannot_read` 发现；M152（有一处不经 `close_stubs`）由 `test_every_dns_stub_is_closed_through_close_stubs` 发现；"
                "M153（报错分支读日志不关文件）由 `test_code_closes_the_files_it_opens` 发现；M154（版本对比报告认不出 Stash 带前缀的筛选）由 "
                "`tests/test_compare_versions.py` 的 `test_stash_filters_get_their_own_label` 发现。")
mut_cell = (f"{N_MUT} 类全部被发现，都是 r17 第二次定稿（{freeze[:16]} UTC）以后在上面这个摘要、这个代码状态的代码上跑的（{window}）。"
            "第一次定稿（04:02）以后开始的那一轮停掉作废，不算在这里（停之前跑完的 7 类也都被发现）。"
            "“记录对应现在的配置”那两项——规则与 DNS 两段的摘要、拨号摘要——对改了规则、DNS 或出站的变异都会报："
            f"{N_MUT} 类里前一项报了 {len(fresh['with']['routing'])} 类、后一项报了 {len(fresh['with']['dial'])} 类；只靠这两项发现的一类都没有（r13 起）。"
            + MUT_R17_TEXT +
            "r16 加的 M123–M141 和更早的各类，发现它们的测试和 r16 时相同（M128 另被新加的 `test_code_closes_the_files_it_opens` 发现；"
            "M101–M122 见提交 `dc90da7`、M123–M141 见提交 `a999d81` 里的这一页）。"
            "M45（回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，"
            "那一项把匹配放在带超时的子进程里，等满 5 分钟后失败并给出提示。"
            "“恢复关键词 siri”“azure.com 放回 Microsoft”“用回肯定前瞻”、国内域名清单数据文件被改坏的两类（M89、M90）"
            "由统一源校验直接拒绝（生成器不肯生成，测试大面积报错）；严格版的结构被改坏的几类（M76–M78、M80–M82）、Stash 的几类（M129、M131、M132）"
            "和“清空 `proxy-server-nameserver`”被写盘前的检查拦住，生成流程的那批测试因此失败，同时另有对应的测试失败；"
            "“图标登记里漏了 Apple Push”在生成时直接报错；其余由对应的测试发现，每一类的失败项见日志")

# ---- 一次性核对：sing-box UDP 的定位（审核 r15 第三点），第二次定稿以后用改严以后的接收端重跑 ----
p17 = read("handoff/notes/r15_review_probes.out")
assert mtime("handoff/notes/r15_review_probes.out") > freeze
pt = read(f"{W}/probe17-time.txt").split("\n")
assert pt[0].startswith("开始 ") and pt[1] == "exit 0" and pt[2].startswith("结束 "), pt
assert pt[0].split()[-2] == RUN_DAY and pt[0].split()[-1] > freeze[11:], pt
probe_window = f"（{pt[0].split()[-1][:5]}–{pt[2].split()[-1][:5]} UTC）"
assert p17.count("不合规的报文：没有") == 14 and "不合规的报文：[" not in p17
v114, v112 = p17.split("\nsing-box 1.12.0（")
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
b = block(v112, "selector 换成 urltest（final 是只含 SOCKS 出口的自动测速组）")
assert "[('ip', '192.0.2.10')]" in b and "unsupported address：0 行" in b, b
for proto in ("shadowsocks", "trojan"):
    assert f"  {proto}（隔一个选择组）：客户端握手 域名 ok、IPv4 ok；服务端日志里入站的 UDP 连接去：['192.0.2.10:443']；unsupported address 1 行" in v114, proto
assert "  vmess（隔一个选择组）：客户端握手 域名 ok、IPv4 ok；服务端日志里入站的 UDP 连接去：['192.0.2.10:443', 'udp-probe.example:443']；unsupported address 0 行" in v114

# ---- 一次性核对：Stash 带前缀的筛选在 ICU 上 ----
q = read("handoff/notes/r17_stash_filters_icu.out")
assert mtime("handoff/notes/r17_stash_filters_icu.out") > freeze
qt = read(f"{W}/icu17-time.txt").split("\n")
assert qt[1] == "exit 0" and qt[0].split()[-1] > freeze[11:], qt
assert q.rstrip().endswith("全部符合") and "ICU 库：libicui18n.so.74" in q and "名字：2305 个" in q
assert q.count("[符合]") == 26 and "[不符合]" not in q and q.count("ICU 与 Python 不同的 0 个") == 26
assert q.count("ICU 上加不加前缀结果不同的 9 个（DIRECT、direct、Direct、REJECT、reject、Reject、REJECT-DROP、reject-drop、Reject-Drop）") == 2
assert q.count("ICU 上加不加前缀结果不同的 0 个（无）") == 24 and q.count("加前缀后选中内置策略名 0 个") == 26

values = {"ICU_TIME": icu_time, "LONG_TIME": long_time, "MUT_CELL": mut_cell, "CMP_CELL": CMP_CELL, "R17_REAL_CELL": R17_REAL_CELL,
          "freeze_utc": freeze[:16], "freeze_full": freeze, "freeze_hm": freeze[11:16], "mut_window": window, "mut_start_hm": segs[0]["start"][11:16],
          "checks_window": checks_window, "checks1_window": checks1_window, "probe_window": probe_window, "cmp_hm": cmpt[0][11:16], "state": state}

# 产物大小、摘要与文档里写的一致
sizes = {rel: os.path.getsize(os.path.join("dist", rel)) for rel in man["outputs"]}
assert (sizes["loon/loon.conf"], sizes["quantumultx/quantumultx.conf"], sizes["mihomo/mihomo-profile.yaml"], sizes["mihomo/mihomo-core.yaml"],
        sizes["sing-box/sing-box-1.14.json"], sizes["sing-box/sing-box-1.12.json"], sizes["stash/stash.yaml"]) \
    == (241985, 404505, 280322, 280505, 79164, 79190, 251780), sizes
assert (sizes["loon/loon-strict.conf"], sizes["quantumultx/quantumultx-strict.conf"], sizes["stash/stash-strict.yaml"], sizes["loon/rules/cn-domains.list"],
        sizes["quantumultx/rules/cn-domains.list"], sizes["quantumultx/rules/cn-domains-max.list"],
        sizes["quantumultx/rules/domain-fallback.list"]) == (243317, 406482, 252712, 165629, 196326, 3521714, 629), sizes
doc05 = read("docs/05-验收记录.md")
for rel, v in man["outputs"].items():
    sha = v["sha256"] if isinstance(v, dict) else v
    assert f"`{sha[:8]}…`" in doc05, rel
assert digest in doc05
# 和 r16 的 dist 比：哪些文件变了（r16 从 git 取到仓库以外，见 r17-as-used/README.md）
old = os.path.join(W, "r16", "dist")
changed, new = [], []
for rel in sorted(set(man["outputs"]) | {"manifest.json"}):
    a, b = os.path.join(old, rel), os.path.join("dist", rel)
    if not os.path.exists(a):
        new.append(rel)
    elif not filecmp.cmp(a, b, shallow=False):
        changed.append(rel)
assert new == [], new
assert changed == ["loon/loon-strict.conf", "loon/loon.conf", "manifest.json", "mihomo/mihomo-core.yaml", "mihomo/mihomo-profile.yaml",
                   "quantumultx/quantumultx-strict.conf", "quantumultx/quantumultx.conf", "stash/stash-strict.yaml", "stash/stash.yaml"], changed
for rel in ("loon/loon.conf", "loon/loon-strict.conf", "quantumultx/quantumultx.conf", "quantumultx/quantumultx-strict.conf",
            "mihomo/mihomo-core.yaml", "mihomo/mihomo-profile.yaml"):
    a, b = read(os.path.join(old, rel)), read(os.path.join("dist", rel))
    assert a.replace("2026.10.13-2", "2026.10.14-1") == b, rel                                   # 只有版本号变了
yaml = __import__("yaml")
sys.path.insert(0, os.getcwd())
from generator.emit_stash import exclude_builtins  # noqa: E402
for rel in ("stash/stash.yaml", "stash/stash-strict.yaml"):
    a, b = yaml.safe_load(read(os.path.join(old, rel))), yaml.safe_load(read(os.path.join("dist", rel)))
    for g in a["proxy-groups"]:
        if "filter" in g:
            g["filter"] = exclude_builtins(g["filter"])
    assert a == b, rel                                                                             # 只有筛选多了前缀（另有注释）
    assert len(b["proxies"]) == 7 and len(b["proxy-groups"]) == 81 and b["rules"][-1] == "MATCH,国外默认" and b["dns"]["follow-rule"] is False, rel

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
for p, needles in DOC_NEEDLES_R17:
    s = read(p)
    for n in needles:
        assert n in s, (p, n)
assert STATE in read("docs/05-验收记录.md")
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
