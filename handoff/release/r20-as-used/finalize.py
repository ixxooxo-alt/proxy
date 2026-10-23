"""把文档里的占位符 ⟦…⟧ 换成最终运行得到的数字，并核对文档里写的数字和日志、产物一致（r20 用的；照 r19-as-used/finalize.py 改的）。
r20 加了简易版（十份 -simple 配置；完整版不变），先审后跑：送审稿 4d3349d 只跑了快速检查，GPT 审完（PR #6）、按意见改完以后定稿一次。
完整版的配置和 r19 逐字节相同，所以 tests/data/real_sets.json 没有重新生成（下面核对它和 r19 的逐字节相同）。
变异检查跑完以后再跑一遍全部检查，交付的日志是这一遍的。全部测试另在 Python 3.12、3.11 上各跑一遍。
数字都从日志和产物里读。用法（在工程根目录）：python3 handoff/release/r20-as-used/finalize.py <变异日志目录> [--dry]"""
import datetime, filecmp, json, os, re, subprocess, sys

D = os.path.abspath(sys.argv[1])
dry = "--dry" in sys.argv
ev = "docs/evidence"
RUN_DAY = "2026-10-23"                                                            # 全部检查、一次性核对、变异检查都在这一天
DIGEST = "40317193e15ff2627a33a3ea6d1afe8b1daf51cde2909236d974f92b9e49761c"     # r20：生成器 1.11.1、统一源 2026.10.17-1、简易版 2026.10.23-1
N_TESTS, N_MUT, N_MIHOMO_DNS, N_FIELDS = "345", 202, "15", "8368"
ENV = "Python：Python 3.13.16，PyYAML：6.0.1"
R19 = "628ed8a"                                                                   # r19 正式版（main 现在的 85eaa7c 只多了文档和宣传动图）
W = os.path.expanduser("~/proxy-work")
R19_DIR = os.path.join(W, "r19")                                                  # 2026-10-21 从 main（85eaa7c）git archive 出来的；代码和产物与 628ed8a 相同
FULL = ["loon/loon.conf", "loon/loon-strict.conf", "quantumultx/quantumultx.conf", "quantumultx/quantumultx-strict.conf",
        "mihomo/mihomo-profile.yaml", "mihomo/mihomo-core.yaml", "sing-box/sing-box-1.14.json", "sing-box/sing-box-1.12.json",
        "stash/stash.yaml", "stash/stash-strict.yaml"]
RULE_FILES = ["loon/rules/cn-domains.list", "quantumultx/rules/cn-domains.list", "quantumultx/rules/cn-domains-max.list",
              "quantumultx/rules/domain-fallback.list"]
SIMPLE = ["loon/loon-simple.conf", "loon/loon-simple-strict.conf", "quantumultx/quantumultx-simple.conf",
          "quantumultx/quantumultx-simple-strict.conf", "mihomo/mihomo-simple-profile.yaml", "mihomo/mihomo-simple-core.yaml",
          "sing-box/sing-box-simple-1.14.json", "sing-box/sing-box-simple-1.12.json", "stash/stash-simple.yaml", "stash/stash-simple-strict.yaml"]

# ---- 这一版特有的说法（从日志里读到以后照抄；下面的断言核对它们确实在日志 / 报告里）----
UE_NEEDLE = "核对域名规则 856 条，社区来源 561 条；产品规则下的上游广告条目 48 条；更宽的广告条目 0 条"
CURSOR_NEEDLE = "Cursor 版共 533 条：同组 429，同组（只写进 mihomo / sing-box / Stash） 70，无专门规则 18，不同组 15，已替换 1。"
CMP_NEEDLES = ("大小：241,985 → 241,985 字节。", "大小：404,505 → 404,505 字节。", "大小：280,322 → 280,322 字节。", "大小：280,505 → 280,505 字节。",
               "大小：79,164 → 79,164 字节。", "大小：79,190 → 79,190 字节。", "大小：251,780 → 251,780 字节。",
               "大小：243,377 → 243,377 字节。", "大小：406,554 → 406,554 字节。", "大小：252,817 → 252,817 字节。",
               "## 六、严格版", "### `stash/stash-strict.yaml` 对照 `stash/stash.yaml`", "大小：标准版 251,780 字节，严格版 252,817 字节。",
               "## 七、简易版：r20 的简易版相对同一版的完整版", "### `stash/stash-simple.yaml` 对照 `stash/stash.yaml`",
               "### `sing-box/sing-box-simple-1.12.json` 对照 `sing-box/sing-box-1.12.json`",
               "- 改动 `OpenAI`：加上 `\"interval\": -1`", "- 新增：`F-ALL = NameRegex, FilterKey = \"<筛选：全部节点>\"`",
               "`loon/rules/cn-domains.list`：165,629 字节，规则 6,133 条（DOMAIN 12、DOMAIN-SUFFIX 6,121）。和 r19 的一模一样。",
               "`quantumultx/rules/cn-domains.list`：196,326 字节，规则 6,133 条（HOST 12、HOST-SUFFIX 6,121）。和 r19 的一模一样。",
               "`quantumultx/rules/cn-domains-max.list`：3,521,714 字节，规则 111,182 条（HOST 252、HOST-SUFFIX 110,930）。和 r19 的一模一样。",
               "`quantumultx/rules/domain-fallback.list`：629 字节，规则 1 条（HOST-KEYWORD 1）。和 r19 的一模一样。")
CMP_CELL = ("十份完整版配置都逐字节相同（大小不变）；新加十份简易版（`-simple`，报告第五节写明是这一版新增，第七节是它们对照同一版的完整版）；"
            "大清单副本、两份自有清单和域名兜底文件和 r19 的一模一样；`manifest.json` 多了十个简易版文件和 `simple_version`")
H8 = "docs/08-外部审核记录.md"
DOC_NEEDLES_R20 = (
    ("README.md", ["tests-345%20passing", "345 automated tests", "202 deliberately injected bugs", "This README describes r20", "2026.10.23-1",
                   "**Simple version (new in r20).**", "Seventeen rounds of external input", "This is r20.", "r19 answered two external reviews",
                   "632 hand-labelled", "270 targets", "561 community-sourced", "available since 2026-10-19"]),
    ("README.zh-CN.md", ["tests-345%20passing", "345 项自动测试；故意改坏代码 202 处", "自动测试 345 项全部通过", "这份说明对应 r20", "**简易版（r20 新增）**",
                         "外部意见一共 17 轮", "这一版的检查是 2026-10-23（UTC）", "r12–r20 各版改了什么", "632 个人工写期望", "270 个目标", "561 条社区来源规则"]),
    ("PROJECT_STATE.md", ["更新：2026-10-23　**r20：新加简易版**", "T33 简易版", "T34 第 17 轮", "已验证（345 项；变异检查：202 类全部被发现）",
                          "需要再跑一次 345 项", "确认 345 项通过", "| 请审核方审 r20 |"]),
    ("00-审核说明.md", ["## 本轮（r20：简易版，统一源 2026.10.17-1）改了什么", "测试 317 → 345 项", "变异检查 170 → 202 类", "公开产物 15 → 25 个",
                        "R20-F01", "R20-F02", "## 本轮请重点看", "注入 202 类错误"]),
    ("docs/05-验收记录.md", ["345 项全部通过", "逐一注入 202 类错误", "| 简易版版本 | 2026.10.23-1", "生成 25 个公开产物", "2290 个假节点", "“国外默认”2,259 项",
                             "“境外DNS”425 个节点", "860 个 120 / 400 个字符的怪名字 × 14 条正则", "270 个目标", "mihomo 15 条", "8,254 字节",
                             "`tests/test_simple.py`，28 项", "`tests/test_real_data.py`，63 项", "`tests/test_strict.py`，34 项", "`tests/test_stash.py`，29 项",
                             "`tests/test_regions.py`，66 项", "`tests/test_compare_versions.py`，14 项", "239 个路由用例 × 20 份配置",
                             "222,353 个里走代理组的 0 个", "官方内核核对了其中 214 个", "6,949,624 字节", "111,182 条", "111,328 条", "自有拦截 98",
                             "202 类全部被发现", "与上一版（r19）对比", "**运行环境：与 r19 相同**", "| 简易版：完整版的私密产物仍和 r19 相同",
                             "| 简易版：境外 DNS 经内部组“境外DNS”出去", "| 简易版送审稿的快速检查", "Python 3.12.3：345 项通过", "Python 3.11.17：345 项通过",
                             "全部 8368 个字段 / 取值", "82 个组名"]),
    ("docs/10-简易版框架.md", ["状态（2026-10-23）：**r20 正式版**", "生成器版本 1.11.1，简易版版本 2026.10.23-1", "251,780 → 172,060；252,817 → 173,111",
                              "## 八、送审稿（`4d3349d`）跑了什么，审完改了什么", "### 6.4 1 小时检查的后果（2026-10-23 按 GPT 审核 R20-F03、R20-F04 改写）",
                              "**每个组都写 `interval: -1`**", "## 十二、请审核方重点看的（r20 正式版）"]),
    ("docs/06-已知限制与待决事项.md", ["| 23 | 简易版：内部组“境外DNS”的检查间隔", "## 2026-10-21：简易版的已知限制（2026-10-23 按 GPT 对送审稿的审核改过）",
                                      "## 2026-10-23（r20）：处理 GPT 对简易版送审稿的审核时顺带查出来的", "**Stash 完整版的选择组也按默认每 600 秒测速**",
                                      "**“境外DNS”可能一个节点都没有**", "**DNS 泄露的说法和完整版相同**"]),
    ("docs/03-DNS决策表.md", ["## 简易版：境外 DNS 和规则下载走内部组“境外DNS”（2026-10-21；2026-10-23 按 GPT 对送审稿的审核改过）",
                             "（2026-10-23 更正，GPT 审核 R20-F05", "**实测的范围**（2026-10-23，GPT 审核的建议 S01）", "| mihomo | 224,087 个"]),
    (H8, ["## 第 17 轮：2026-10-23，GPT 审核简易版送审稿（r20 送审稿，审核 PR #6）", "docs/evidence/gpt-r20-draft/", "R20-F01", "R20-F05", "S01（建议）",
          "## 第 16 轮：2026-10-17，GPT 审核 r19 正式版", "## 第 15 轮：2026-10-17，GPT 审核 r19 送审稿"]),
    ("docs/09-真机验收操作清单.md", ["对应统一源 2026.10.17-1 生成的配置（r20；简易版 2026.10.23-1）", "## 1d. 简易版", "| 7b. Stash：测速"]),
    ("docs/01-导入、更新、诊断与回滚.md", ["这一版（r20）是 `2026.10.17-1`", "## 简易版（2026-10-21 新增，送审稿）：导入哪个文件", "简易版不定时测速"]),
    ("docs/07-需求对照.md", ["### 2026-10-23（GPT 审核简易版送审稿之后，r20）", "R20-F02：新的保留名"]),
    ("docs/00-需求原文.md", ["## 补充（2026-10-23，GPT 审完简易版送审稿；对话中给出，照录）", "> 审核完成，报告已提交到 PR #6"]),
    ("handoff/README.md", ["## 17. r20：简易版", "r20-as-used", "r20_full_private_same.py"]),
)
# 旧的说法不应再作为现状出现（历史记录里的除外：docs/00 只追加，docs/08 是逐轮的记录）
STALE = {k: [] for k in (
    # r19 时的现状
    "tests-317", "317 automated", "自动测试 317 项", "317 项全部通过", "确认 317 项通过", "注入 170 类", "已验证（317 项", "（317 项；",
    "这份说明对应 `2026.10.17-1`（r19", "This README describes source version **2026.10.17-1** (r19", "Fifteen rounds of external input",
    "外部意见一共 15 轮", "**运行环境：与 r18 相同**", "与上一版（r18）对比", "r19 定稿（2026-10-17 08:39:15 UTC）之后",
    # 送审稿时的现状
    "注入 196 类", "r20 是 196 类", "（送审稿）的已知限制", "送审中，`main` 上还没有", "in review, not on `main` yet", "这一页的数字仍是 r19 的",
    "## 2026-10-21：这一次请审“简易版”的送审稿", "**已经写好，这是送审稿**", "完整版和简易版共用同一批转换好的节点",
    # GPT 审核 r20 送审稿指出说过头的（R20-F03–F05）
    "没在用时约 2 小时", "最长约 1 小时（没在用时约 2 小时）", "mihomo 上用不着改", "不受间隔影响", "两份都不会交给国内 DNS",
    "Clash、SFA 两种都不会把走代理的域名交给国内 DNS（`d", "SFA 开着时每 5 分钟把这个组的节点测一遍",
    # 更早的（r19 的 finalize 里列过的，仍不应出现）
    "tests-311", "311 automated", "自动测试 311 项", "注入 162 类", "This is r18.", "None of r12–r19", "r12–r19 交付时都没有推", "`main` 现在还是 r11",
    "① ② 仍等你定", "waiting for the owner's decision", "<筛选：未知的正则>\"",
    "unusable until the repository's `main` branch carries this version's rule files")}
STALE.update({"和完整版一样看不到": ["docs/03-DNS决策表.md"],                       # docs/03 那一处是在说以前的写法
              "会走代理（能打开，会慢）": ["00-审核说明.md"], "境外域名都不在本机解析": ["docs/03-DNS决策表.md", "00-审核说明.md"],
              "`main` 仍是 r11": ["handoff/README.md"], "`main` 还是 r11": ["docs/07-需求对照.md"],
              "原话见 `docs/00` 最后": ["handoff/README.md", "00-审核说明.md"], "44 页": ["docs/02-语法依据与能力矩阵.md",
              "docs/06-已知限制与待决事项.md", "docs/07-需求对照.md", "00-审核说明.md", "docs/05-验收记录.md"],
              # 这两处是更正说明里引的旧话（“原来这里写的……说满了”“以前这里写的……是照搬旧实验”），逐个看过
              "两份都不会交给国内 DNS": ["docs/07-需求对照.md"], "没在用时约 2 小时": ["docs/10-简易版框架.md"]})


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def mtime(p):
    return datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def times(name):
    """一次性核对记下的时间文件：第一行“开始 <日期> <时间>”，第二行“exit 0”，第三行“结束 <日期> <时间>”。返回 (开始, 结束)。"""
    t = read(f"{W}/{name}").split("\n")
    assert t[0].startswith("开始 ") and t[1] == "exit 0" and t[2].startswith("结束 "), (name, t)
    a, b = t[0].split(" ", 1)[1], t[2].split(" ", 1)[1]
    assert a[:10] == RUN_DAY and a > freeze, (name, a, freeze)
    return a, b


def window(a, b):
    return f"（{a[11:16]}–{b[11:16]} UTC）" if a[11:16] != b[11:16] else f"（{a[11:16]} UTC）"


man = json.load(open("dist/manifest.json", encoding="utf-8"))
digest = man["source_sha256"]
assert man["source_version"] == "2026.10.17-1" and man["generator_version"] == "1.11.1" and man["simple_version"] == "2026.10.23-1", man
assert digest == DIGEST, digest
assert sorted(man["outputs"]) == sorted(FULL + RULE_FILES + SIMPLE), sorted(man["outputs"])
freeze = read(f"{W}/freeze20-time.txt").strip()                                   # 定稿时记下的时间（UTC）
state = subprocess.run(["bash", "handoff/release/code_state.sh"], capture_output=True, text=True, check=True).stdout.strip()
assert state == read(f"{W}/freeze20-state.txt").strip(), "代码在定稿之后变过"
assert freeze[:10] == RUN_DAY, freeze

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
assert all(s["start"][:10] >= RUN_DAY for s in segs), segs
assert all(s["start"] > freeze for s in segs), (segs, freeze)
assert sum(len(x["ids"]) for x in segs) == N_MUT
mut_end = segs[-1]["end"]
end_day = "" if mut_end[:10] == RUN_DAY else f"{mut_end[:10]} "
if len(segs) == 1:
    mwin = f"三批并行，{segs[0]['start'][11:16]}–{end_day}{segs[0]['end'][11:16]} UTC，一次跑完，中间没有中断"
else:
    mwin = ("三批并行，分 " + str(len(segs)) + " 段：" + "；".join(f"{x['start'][5:16]}–{x['end'][5:16]} UTC 跑完 {len(x['ids'])} 类" for x in segs)
            + "；前面的段停在工作环境停掉的时候，各段之间代码没有改动，后一段开始前重新核对过代码状态和运行环境")
fresh = res["fresh"]
assert fresh["solo"] == [], fresh

# ---- 全部检查（变异检查跑完以后的那一遍）----
LOGS = ("tests.log", "icu-check.log", "official-check.log", "real-route-check.log", "upstream-field-check.log",
        "upstream-evidence-check.log", "cursor-report-check.log", "icons-check.log", "cn-list-check.log")
starts, ends = {}, {}
for name in LOGS:
    t = read(f"{ev}/{name}")
    head = t.split("\n\n", 1)[0]
    assert f"统一源摘要：{digest}" in head, name
    assert ENV in head, (name, head[:200])
    assert re.search(r"^退出码：0$", t, re.M), name
    assert "scratchpad" not in t and "/tmp/claude" not in t and "/root/.claude" not in t, name
    starts[name] = re.search(r"运行时间（UTC）：(\S+ \S+)", head).group(1)
    ends[name] = mtime(f"{ev}/{name}")
assert min(starts.values()) > mut_end, (min(starts.values()), mut_end)
CHECK_DAY = min(starts.values())[:10]
checks_window = (f"{CHECK_DAY} " if CHECK_DAY != RUN_DAY else "") + f"{min(starts.values())[11:16]}–{max(ends.values())[11:16]} UTC"
ct = read(f"{W}/checks20b-time.txt").split("\n")
assert ct[0] > mut_end and ct[0] <= min(starts.values()) and ct[1] >= max(ends.values()), ct
assert read(f"{W}/checks20b.out").rstrip().endswith("全部检查通过。\nexit 0"), "run_checks.sh 没有以“全部检查通过。”结束"
c1 = read(f"{W}/checks20-time.txt").split("\n")                                   # 定稿以后、和变异检查同时跑的第一遍
assert c1[0] > freeze and read(f"{W}/checks20.out").rstrip().endswith("全部检查通过。\nexit 0"), c1
checks1_window = f"{c1[0][11:16]}–{c1[1][11:16]} UTC"
first = f"{W}/checks20-logs"                                                       # 第一遍的日志（第二遍开始前复制出来的）

tests = read(f"{ev}/tests.log")
m = re.search(r"^Ran (\d+) tests in [\d.]+s\n\nOK\b(.*)$", tests, re.M)
assert m, "tests.log 里没有 OK"
assert "skipped" not in m.group(2), "有跳过的测试：" + m.group(2)
assert m.group(1) == N_TESTS, m.group(1)
assert not re.search(r"\w+Warning: ", tests), re.findall(r".*\w+Warning: .*", tests)[:3]
assert tests.count("ResourceWarning") == 1 and "那一处 ResourceWarning，同一类写法" in tests
NEW_R20 = ("test_every_full_output_has_a_simple_one", "test_routing_digest_equals_the_full_one_apart_from_the_dns_path", "test_foreign_dns_group",
           "test_samples", "test_random_names_and_local_overlay", "test_layout_breakage_is_caught", "test_internal_group_name_must_be_new",
           # 审核以后加的
           "test_reserved_tags_per_layout", "test_full_version_keeps_r19_names", "test_report_says_when_the_foreign_dns_group_is_empty",
           "test_stash_groups_do_not_benchmark")
for t in ("test_refuses_what_rfc1928_says_to_refuse", "test_threads_do_not_shadow_thread_internals", "test_dns_attribution_uses_the_real_stubs_after_they_stop",
          "test_code_closes_the_files_it_opens", "test_build_refuses_a_broken_stash_config") + NEW_R20:
    assert re.search(rf"^{t} \(test_\w+\.\w+\.{t}\)", tests, re.M), t
per_file = {}
for mod, _cls, _name in set(re.findall(r"\((test_\w+)\.(\w+)\.(\w+)\)", tests)):
    per_file[mod] = per_file.get(mod, 0) + 1
assert sum(per_file.values()) == int(N_TESTS), per_file
assert (per_file["test_real_data"], per_file["test_strict"], per_file["test_dns_lan"], per_file["test_compare_versions"],
        per_file["test_local_and_private"], per_file["test_icons"], per_file["test_source"], per_file["test_stash"], per_file["test_regions"],
        per_file["test_simple"]) == (63, 34, 15, 14, 9, 9, 18, 29, 66, 28), per_file

ICU_RX = r"ICU 平均每次匹配：宽 (\d+) 微秒、严 (\d+) 微秒.*?Loon (\d+) 毫秒，Quantumult X（26 个策略各一条）(\d+) 毫秒"
icu = read(f"{ev}/icu-check.log")
assert "13 条（宽 7 条、严 6 条）× 2290 个节点名（其中 632 个有手写的期望）" in icu
assert "× 2313 个节点名" in icu
for needle in ("简易版：全部节点那一条（8254 字节）× 2290 个节点名，ICU 与 Python 完全一致，也等于宽的七条取并集",
               "带本地补充样例：全部节点那一条（8593 字节）× 2313 个节点名，ICU 与 Python 完全一致，也等于宽的七条取并集",
               "带本地补充样例：期望不进任何组的 2 个名字，全部节点那一条一个都没选"):
    assert needle in icu, needle
m = re.search(ICU_RX, icu)
m1 = re.search(ICU_RX, read(f"{first}/icu-check.log"))
assert m and m1, "icu-check.log 里没有耗时行"
icu_time = (f"这次运行 ICU 平均每次匹配：宽的 {m.group(1)} 微秒、严的 {m.group(2)} 微秒（含调用开销）；按 300 个节点估算 Loon 约 {m.group(3)} 毫秒、"
            f"Quantumult X 约 {m.group(4)} 毫秒（每次运行有出入：同一个云端会话里，定稿以后和变异检查同时跑的第一遍是 {m1.group(1)} / {m1.group(2)} 微秒、"
            f"{m1.group(3)} / {m1.group(4)} 毫秒，r19 是 38 / 67 毫秒，r18 是 51 / 94 毫秒，r17 是 60 / 107 毫秒，r16 是 41 / 73 毫秒——中间工作环境重启过，不一定是同一台机器；"
            f"r12 是 29 / 51 毫秒（另一台机器），r10 时几次运行是 36–38 / 63–66 毫秒；手机会慢几倍。这是完整版的估算，简易版每个地区只有一条筛选）")
LONG_RX = r"^长名字（120、400 个字符两档，共 (\d+) 个）× (\d+) 条正则，(ICU|Python)：(.*?)；最慢的一次 ([\d.]+) 毫秒"
long_lines = re.findall(LONG_RX, icu, re.M)
long_first = re.findall(LONG_RX, read(f"{first}/icu-check.log"), re.M)
assert len(long_lines) == 2 and all(x[0] == "860" and x[1] == "14" and "全部按时结束，分组与逐步判断完全一致" in x[3] for x in long_lines), long_lines
assert len(long_first) == 2
long_time = ("最慢的一次：" + "、".join(f"{eng} {float(ms):.1f} 毫秒" for _, _, eng, _, ms in long_lines)
             + "（每次运行有出入：定稿以后和变异检查同时跑的第一遍是 " + "、".join(f"{eng} {float(ms):.1f}" for _, _, eng, _, ms in long_first)
             + " 毫秒，r19 是 ICU 22.9、Python 4.8 毫秒（13 条），r18 是 ICU 23.9、Python 9.5 毫秒，r17 是 ICU 40.3、Python 8.3 毫秒）")

off = read(f"{ev}/official-check.log")
assert "节点 2290 个（手写期望：手动组 632 个、自动类组 632 个）" in off and "只进手动组的 72 个" in off
assert "节点 2313 个（手写期望：手动组 24 个、自动类组 24 个）" in off
assert "节点 2290 个；香港 117、日本 109、韩国 30、台湾 42、新加坡 29、美国 187、其他地区 1755；国外默认 2259 项（写明的 7 个 + 节点 2252 个）；境外DNS 425 个" in off
assert "[符合] 简易版：mihomo 实际分组（地区组用宽的、国外默认是七个地区加全部节点、境外DNS 是严的并集）与手写期望、Python 结果一致" in off
assert off.count("[符合] mihomo -t ") == 4 and off.count("[符合] sing-box check ") == 10, (off.count("[符合] mihomo -t "), off.count("[符合] sing-box check "))
assert off.count("预期失败") == 3 and "[不符" not in off and "全部符合预期" in off
assert "if “respect-rules” is turned on, “proxy-server-nameserver” cannot be empty" in off
assert "disallow empty `proxy-server-nameserver` when `proxy-server-nameserver-policy` is set" in off

rr = read(f"{ev}/real-route-check.log")
# 完整版的配置、上游数据、内核都和 r19 相同：日志除了开头的运行时间和统一源摘要，应当和 r19 那一份逐字相同
rr19 = subprocess.run(["git", "show", f"{R19}:{ev}/real-route-check.log"], capture_output=True, text=True, check=True).stdout
body = lambda t: [x for x in t.split("\n") if not x.startswith(("运行时间（UTC）：", "统一源摘要："))]
assert body(rr) == body(rr19), "real-route-check.log 和 r19 的不同（除了运行时间、统一源摘要）"
assert f"用例与排除项共 290 条，不同的目标 270 个；DNS 去向用例 sing-box 22 条、mihomo {N_MIHOMO_DNS} 条，拨号解析用例 sing-box 12 条、mihomo 12 条" in rr
assert rr.count("[符合] 路由 270 条") == 3 and "[不符合]" not in rr and "\n全部一致\n" in rr
assert "名字会交给国内 DNS 的 222353 个：路由是国内直连 / 直连 / 拦截的 222339 个；归默认直连、可以切换的组的 14 个；走代理组的 0 个" in rr
assert "[符合] 官方内核核对 214 个主机（走代理组的和默认直连组的全部，另抽 200 个）" in rr
m = re.search(r"检查了 (\d+) 个字段 / 取值", read(f"{ev}/upstream-field-check.log"))
assert m and m.group(1) == N_FIELDS, "upstream-field-check.log 里的字段数"
ic = read(f"{ev}/icons-check.log")
assert "f250126f57228b0b32f3445b21078e382e6152e9" in ic and "合计 6,949,624 字节" in ic and "80 个地址逐个相同" in ic
assert ic.count("81 个策略组的图标都在图标仓库里，是 PNG，尺寸对") == 8 and ic.count("51 个策略组的图标都在图标仓库里，是 PNG，尺寸对") == 6
assert ic.count("52 个策略组的图标都在图标仓库里，是 PNG，尺寸对") == 2 and "各端同一个策略组用的是同一个地址（82 个组名）" in ic
assert "用到的图片 81 张" in ic and "还没有上传" not in ic and "全部符合" in ic and "1 个图在图标仓库里、清单没有收，没有比：Apple Push" in ic
cn = read(f"{ev}/cn-list-check.log")
assert "source/data/cn-domains.txt 与按固定快照重新生成的逐字节相同：后缀 6142 条、精确域名 12 条（快照 c1c2cf0d，2026-09-22）" in cn
assert "source/data/cn-domains-max.txt 与按固定快照重新生成的逐字节相同：后缀 111009 条、精确域名 268 条（快照 51d2e1dd，2026-09-21）" in cn
assert "--bm7" in cn.split("\n\n", 1)[0]
ue = read(f"{ev}/upstream-evidence-check.log")
assert UE_NEEDLE in ue and "检查通过" in ue, ue[-800:]
assert CURSOR_NEEDLE in read(f"{ev}/cursor-迁入核对.md")

# ---- 快照：没有重新生成，和 r19 的逐字节相同 ----
snap_now = read("tests/data/real_sets.json")
snap19 = subprocess.run(["git", "show", f"{R19}:tests/data/real_sets.json"], capture_output=True, text=True, check=True).stdout
assert snap_now == snap19, "tests/data/real_sets.json 和 r19 的不同"
assert json.loads(snap_now)["generated"] == "2026-10-17"

cmp_ = read(f"{ev}/与上一版的对比.md")
assert cmp_.startswith("# 版本对比：r19 → r20\n"), cmp_[:40]
assert "| r19 | 632 | 0 | 632 | 0 |" in cmp_ and "| r20 | 632 | 0 | 632 | 0 |" in cmp_
assert "共 2254 个名字" in cmp_ and "### 手动组的归属变了（0 个）" in cmp_ and "成员变了（0 个）" in cmp_
assert cmp_.count("逐字节相同。") == 10, cmp_.count("逐字节相同。")
assert cmp_.count("r19 没有这个文件，是这一版新增的简易版") == 10
assert "未知的正则>\"" not in cmp_ and "<筛选：未知的正则>" not in cmp_
assert not re.search(r"^- 改动 `[^`]*`：\s*$", cmp_, re.M), "还有说不出改了什么的“改动”"
for needle in CMP_NEEDLES:
    assert needle in cmp_, needle
cmp7 = read(f"{ev}/与r7的对比.md")
assert cmp7.startswith("# 版本对比：r7 → r20\n"), cmp7[:40]
assert "| r7 | 585 | 47 | 541 | 91 |" in cmp7 and "| r20 | 632 | 0 | 632 | 0 |" in cmp7
assert "共 2254 个名字" in cmp7 and "### 手动组的归属变了（47 个）" in cmp7 and "成员变了（53 个）" in cmp7
cmpt = read(f"{W}/cmp20-time.txt").split("\n")
assert cmpt[0].startswith("开始 ") and cmpt[1] == "exit 0", cmpt
cmp_start = cmpt[0].split(" ", 1)[1]
assert cmp_start > freeze and mtime(f"{ev}/与上一版的对比.md") <= cmpt[2].split(" ", 1)[1] + "9", cmpt

# ---- 变异检查的说明（编号 → 发现它的测试，照变异日志）----
MUT_TESTS = {"M195": "test_reserved_tags_per_layout", "M197": "test_full_version_keeps_r19_names", "M198": "test_full_version_keeps_r19_names",
             "M199": "test_full_version_keeps_r19_names", "M200": "test_report_says_when_the_foreign_dns_group_is_empty",
             "M201": "test_stash_groups_do_not_benchmark", "M202": "test_layout_breakage_is_caught",
             # r19 的几类，发现它们的测试照旧
             "M163": "test_threads_do_not_shadow_thread_internals", "M167": "test_recorder_stop_ignores_udp_packets_after_the_control_connection_closes_mid_drain",
             "M168": "test_dns_attribution_uses_the_real_stubs_after_they_stop", "M170": "test_every_dns_stub_is_closed_through_close_stubs"}
for name, test in MUT_TESTS.items():
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] {name} "))
    assert test in l, l[:400]
for i in list(range(71, N_MUT + 1)):
    l = next(x for x in mut.splitlines() if x.startswith(f"[发现] M{i} "))
    if f"M{i}" not in res["not_seen"]:
        assert "输出含预期信息" in l, l[:200]
assert "DeprecationWarning" not in mut
partial_names = sorted(x for v in res["partial"].values() for x in v)
print("部分运行的：", res["partial"], "；未见预期信息：", res["not_seen"])
# 跑完以后按日志确认（README 第 7 步）：M6、M9、M31、M89、M90 是统一源校验直接拒绝；M16 是 r20 起 sing-box 生成时发现出站标签重名直接报错，
# 简易版带节点的测试类（SingboxWithNodes）无法初始化（2026-10-23 在临时副本上复现过）
PARTIAL_EXPECTED = sorted(os.environ.get("PARTIAL_EXPECTED", "M6 M9 M16 M31 M89 M90").split())
assert res["partial"] == {"316": ["M6", "M9", "M31", "M89", "M90"], "343": ["M16"]}, res["partial"]
assert sorted(res["not_seen"]) == ["M177", "M3"], res["not_seen"]
assert partial_names == PARTIAL_EXPECTED, res["partial"]
MUT_R20_TEXT = ("这一版新加的 32 类：M171–M196 是简易版的（2026-10-21），每一类由 `tests/test_simple.py` 或把简易版算进去的原有测试发现；"
                "M197–M202 对应 GPT 审核送审稿的 R20-F01、R20-F02：M197（完整版的节点又避开简易版的组名）、M198（简易版沿用完整版转换好的节点）、"
                "M199（转换报告不写简易版不同的地方）由 `test_full_version_keeps_r19_names` 发现，M200（“境外DNS”没有节点时报告不提）由 "
                "`test_report_says_when_the_foreign_dns_group_is_empty` 发现，M201（Stash 简易版的组不关定时测速）由 `test_stash_groups_do_not_benchmark` "
                "和写盘前检查发现，M202（写盘前检查不核对它）由 `test_layout_breakage_is_caught` 发现；M195 跟着 R20-F02 改写成“简易版的节点只避开完整版的组名”，"
                "由 `test_reserved_tags_per_layout` 发现。M177（mihomo 简易版不把 GEO 数据的下载交给“境外DNS”）预设的关键字写成了 `test_mihomo`"
                "（送审稿时这批只核对过改动能套上），实际由写盘前检查和 `test_routing_digest_equals_the_full_one_apart_from_the_dns_path` 发现，"
                "所以日志里记“未见预期信息”；关键字留到下一版改代码时再改（改它就要重新定稿）。"
                "M16（节点与组同名不再改名）这一版起还会让 sing-box 生成时直接报出站标签重名，简易版带节点的测试类无法初始化，所以只跑了 343 项。")
mut_cell = (f"{N_MUT} 类全部被发现，都是 r20 定稿（{freeze[:16]} UTC）以后在上面这个摘要、这个代码状态的代码上跑的（{mwin}）。"
            "“记录对应现在的配置”那两项——规则与 DNS 两段的摘要、拨号摘要——对改了规则、DNS 或出站的变异都会报："
            f"{N_MUT} 类里前一项报了 {len(fresh['with']['routing'])} 类、后一项报了 {len(fresh['with']['dial'])} 类；只靠这两项发现的一类都没有（r13 起）。"
            + MUT_R20_TEXT +
            "r19 和更早的各类，发现它们的测试和 r19 时相同（M99、M139 跟着简易版的代码改了注入的位置；M101–M122 见提交 `dc90da7`、"
            "M123–M141 见提交 `a999d81`、M142–M154 见提交 `88a1e38`、M155–M162 见提交 `ead8ca8`、M163–M170 见提交 `628ed8a` 里的这一页）。"
            "M45（回溯失控）只跑专门针对它的那一项测试：这种错误会让别的用到正则的测试卡住而不是报错，"
            "那一项把匹配放在带超时的子进程里，等满 5 分钟后失败并给出提示。"
            "“恢复关键词 siri”“azure.com 放回 Microsoft”“用回肯定前瞻”、国内域名清单数据文件被改坏的两类（M89、M90）"
            "由统一源校验直接拒绝（生成器不肯生成，测试大面积报错）；严格版的结构被改坏的几类（M76–M78、M80–M82）、Stash 的几类（M129、M131、M132）"
            "和“清空 `proxy-server-nameserver`”被写盘前的检查拦住，生成流程的那批测试因此失败，同时另有对应的测试失败；"
            "“图标登记里漏了 Apple Push”在生成时直接报错；其余由对应的测试发现，每一类的失败项见日志")

# ---- 运行环境核对（定稿以后）----
vc = read(f"{W}/vendor20-check.txt")
m = re.search(r"^文件 (\d+) 个都对；源码目录 (\d+) 个，提交号都对、没有改动；Stash 文档包 (\d+) 个文件都对$", vc, re.M)
assert m and m.group(1) == "13" and m.group(2) == "5" and m.group(3) == "45", vc[-500:]
vendor_hm = re.search(r"^时间 \S+ (\d\d:\d\d)", vc, re.M).group(1)
VENDOR_CELL = f"{m.group(1)} 个文件的 SHA-256、{m.group(2)} 个源码目录的提交号都对"

# ---- 一次性核对：sing-box UDP 的定位（审核 r15 第三点），每版定稿以后重跑 ----
p15 = read("handoff/notes/r15_review_probes.out")
assert mtime("handoff/notes/r15_review_probes.out") > freeze
pa, pb = times("probe20-time.txt")
assert p15.count("不合规的报文：没有") == 14 and "不合规的报文：[" not in p15 and "没有跑成" not in p15
norm = lambda t: re.sub(r"\[\d+ \d+ms\]", "[…]", t)
p15_19 = subprocess.run(["git", "show", f"{R19}:handoff/notes/r15_review_probes.out"], capture_output=True, text=True, check=True).stdout
assert norm(p15) == norm(p15_19), "r15 定位核对的结果和 r19 那一次不同"

# ---- 一次性核对：Stash 带前缀的筛选在 ICU 上（完整版的筛选没变，重跑一遍）----
q = read("handoff/notes/r17_stash_filters_icu.out")
assert mtime("handoff/notes/r17_stash_filters_icu.out") > freeze
qa, qb = times("icu20-time.txt")
q19 = subprocess.run(["git", "show", f"{R19}:handoff/notes/r17_stash_filters_icu.out"], capture_output=True, text=True, check=True).stdout
assert q == q19, "Stash 筛选的 ICU 核对和 r19 那一次不是逐字相同"
assert q.rstrip().endswith("全部符合") and q.count("[符合]") == 26

# ---- 一次性核对：完整版的私密产物和 r19 相同（R20-F02 的同类自查）----
fp = read("handoff/notes/r20_full_private_same.out")
assert mtime("handoff/notes/r20_full_private_same.out") > freeze
fa, fb = times("fp20-time.txt")
assert fp.count("build.py 退出码 0") == 3 and "scratchpad" not in fp and "/tmp/claude" not in fp
now_part = fp[fp.index("当前和 r19 比"):]
draft_part = fp[fp.index("送审稿和 r19 比"):fp.index("当前和 r19 比")]
assert "  11 个相同、1 个不同" in now_part and "  不同  sing-box-节点转换报告.txt" in now_part, now_part[:600]
assert "  9 个相同、3 个不同" in draft_part and "  不同  sing-box-1.14.json" in draft_part and "['境外DNS（节点）']" in draft_part
assert "完整版 sing-box 里那个虚构节点的标签：['境外DNS']" in now_part
assert "境外DNS：完整版里叫 境外DNS，简易版里叫 境外DNS（节点）（各自避开本版的组名）" in fp

# ---- 全部测试在 Python 3.12、3.11 上（定稿以后跑的，日志在仓库以外）----
pt = read(f"{W}/py20-time.txt").split("\n")
assert pt[0].startswith("开始 ") and pt[1] == "Python 3.12.3" and pt[2] == "exit 0" and pt[3].startswith("中间 ") \
    and pt[4] == "Python 3.11.17" and pt[5] == "exit 0" and pt[6].startswith("结束 "), pt
pa12, pm, pb11 = pt[0].split(" ", 1)[1], pt[3].split(" ", 1)[1], pt[6].split(" ", 1)[1]
assert pa12[:10] == RUN_DAY and pa12 > freeze, (pa12, freeze)
for name in ("py312-20.out", "py311-20.out"):
    t = read(f"{W}/{name}")
    m = re.search(r"^Ran (\d+) tests in [\d.]+s\n\nOK\b(.*)$", t, re.M)
    assert m and m.group(1) == N_TESTS and "skipped" not in m.group(2), (name, t[-300:])
    assert not re.search(r"\w+Warning: ", t), name
PY_OTHER = (f"Python 3.12.3：{N_TESTS} 项通过（{pa12[11:16]}–{pm[11:16]} UTC）；Python 3.11.17：{N_TESTS} 项通过（{pm[11:16]}–{pb11[11:16]} UTC）；"
            "都没有跳过、没有警告")

ONEOFF_TIMES = (f"sing-box UDP 的定位重跑{window(pa, pb)}、Stash 带前缀的筛选在 ICU 上{window(qa, qb)}、完整版的私密产物和 r19 比{window(fa, fb)}"
                "（r18 那两项——R17-F01 的复现脚本、第 22 项 ③ 的 sing-box 1.14.3——这一版没有重跑）")

values = {"ICU_TIME": icu_time, "LONG_TIME": long_time, "MUT_CELL": mut_cell, "CMP_CELL": CMP_CELL, "N_TESTS": N_TESTS, "N_FIELDS": N_FIELDS,
          "freeze_utc": freeze[:16], "freeze_full": freeze, "freeze_hm": freeze[11:16], "mut_window": mwin, "mut_start_hm": segs[0]["start"][11:16],
          "checks_window": checks_window, "checks1_window": checks1_window, "cmp_hm": cmp_start[11:16], "state": state, "digest": digest,
          "vendor_hm": vendor_hm, "VENDOR_CELL": VENDOR_CELL, "ONEOFF_TIMES": ONEOFF_TIMES,
          "P15_WINDOW": window(pa, pb), "ICU17_WINDOW": window(qa, qb), "FP_WINDOW": window(fa, fb), "PY_OTHER": PY_OTHER}

# 产物大小、摘要与文档里写的一致
sizes = {rel: os.path.getsize(os.path.join("dist", rel)) for rel in man["outputs"]}
assert [sizes[x] for x in FULL] == [241985, 243377, 404505, 406554, 280322, 280505, 79164, 79190, 251780, 252817], sizes
assert [sizes[x] for x in RULE_FILES] == [165629, 196326, 3521714, 629], sizes
assert [sizes[x] for x in SIMPLE] == [160794, 162200, 171603, 173666, 275241, 275421, 76536, 76553, 172060, 173111], [sizes[x] for x in SIMPLE]
sha = {rel: (v["sha256"] if isinstance(v, dict) else v) for rel, v in man["outputs"].items()}
short = lambda rel: f"`{sha[rel][:8]}…`"
tag = lambda rel: rel.split("/")[-1].rsplit(".", 1)[0]
values["OUT_DIGESTS"] = ("完整版的标准版七份：" + "、".join(f"{tag(r)} {short(r)}" for r in FULL if "strict" not in r)
                         + "；完整版的严格版三份：" + "、".join(f"{tag(r)} {short(r)}" for r in FULL if "strict" in r)
                         + "；简易版十份：" + "、".join(f"{tag(r)} {short(r)}" for r in SIMPLE)
                         + "；Loon / Quantumult X 严格版引用的四个规则文件：" + "、".join(f"`{r}` {short(r)}" for r in RULE_FILES))
# 和 r19 的 dist 比：只有 manifest.json 变了，十份简易版是新的
old = os.path.join(R19_DIR, "dist")
changed, new = [], []
for rel in sorted(set(man["outputs"]) | {"manifest.json"}):
    a, b = os.path.join(old, rel), os.path.join("dist", rel)
    if not os.path.exists(a):
        new.append(rel)
    elif not filecmp.cmp(a, b, shallow=False):
        changed.append(rel)
assert new == sorted(SIMPLE), new
assert changed == ["manifest.json"], changed

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
for p, needles in DOC_NEEDLES_R20:
    s = read(p)
    for n in needles:
        assert n in s, (p, n)
assert state in read("docs/05-验收记录.md")
d06 = read("docs/06-已知限制与待决事项.md")
pending = d06[d06.index("## 需要你决定的事项"):d06.index("## 2026-10-15 你定下的事项")]
assert "\n| 23 |" in pending, "第 23 项不在“需要你决定的事项”的表里（或者和表断开了）"
assert "\n\n| 23 |" not in pending, "第 23 项和上面的表断开了"
doc05 = read("docs/05-验收记录.md")
for rel in man["outputs"]:
    assert short(rel) in doc05, rel
assert digest in doc05
# 旧的说法不应再作为现状出现（历史记录里的除外，逐个看过）
HIST = ["docs/00-需求原文.md", "docs/08-外部审核记录.md"]
for p in files:
    s = read(p)
    for k, allowed in STALE.items():
        if k in s and p not in allowed and p not in HIST:
            raise AssertionError(f"{p} 里还有旧的说法：{k}")
    if p not in HIST:
        for mm in re.finditer("全集", s):
            ctx = s[max(0, mm.start() - 8):mm.start() + 12]
            assert re.search(r"叫(它)?“全集|“全集一致性”改名|“全集一致性”→|原“全集", ctx), (p, ctx)
print("核对通过")
