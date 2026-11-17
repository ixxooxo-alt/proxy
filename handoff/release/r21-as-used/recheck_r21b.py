"""r21b（2026-11-17）的复核：GPT 审 r21（PR #9）以后只改了文档。2026-10-31 出 r21 的那台机器已经回收，finalize.py 要读的工作文件
（~/proxy-work/ 下的定稿时间、变异汇总、两遍全部检查的时间、Python 3.12 / 3.11 的输出、运行环境核对）都不在了，finalize.py 没法整份重跑。
这里做能在仓库里做的那几项：
  1. 代码、产物、日志、一次性核对的输出相对 r21（c0e8707）没有变——finalize.py 10-31 核对过的就是这些文件；
  2. 代码状态哈希等于 r21 定稿时记下的值；manifest 的版本和统一源摘要不变；
  3. finalize.py 的文档核对部分：DOC_NEEDLES_R21、STALE（都从 finalize.py 读），加上这一轮的核对项和旧说法；没有占位符；
     docs/06 第 23 项在“2026-10-31 你定下的事项”里；docs/05 里有统一源摘要、代码状态和每个产物的摘要。
用法（在工程根目录）：python3 -B handoff/release/r21-as-used/recheck_r21b.py"""
import json, os, re, subprocess, sys

R21 = "c0e8707"
STATE = "eca139fa64d9b4ea4e2d286a358b4c1ca616d700e12eeb4c4631704068a7c32a"      # r21 定稿时（2026-10-31 16:57:23 UTC）
DIGEST = "eb13aba7dab0479cb1affea1242061a36645ae556b39f717168da3b832bb20d7"


def run(*cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


# 1. 只改了文档：代码、产物、日志、一次性核对的输出都和 r21 相同（新加的审核报告存档除外）
FROZEN = ["build.py", "generator", "source", "tests", "tools", ".gitignore", "dist", "handoff/notes"]
r = run("git", "diff", "--name-only", R21, "--", *FROZEN)
assert r.returncode == 0 and r.stdout.strip() == "", ("相对 r21 变了：", r.stdout)
r = run("git", "status", "--porcelain", "--", *FROZEN)
assert r.stdout.strip() == "", ("工作区里有没提交的改动：", r.stdout)
ev = run("git", "diff", "--name-only", R21, "--", "docs/evidence").stdout.split()
ev += [l[3:] for l in run("git", "status", "--porcelain", "--untracked-files=all", "--", "docs/evidence").stdout.splitlines()]
assert all(p.startswith("docs/evidence/gpt-r21/") for p in ev), ("docs/evidence 里除了新存档的审核报告还有改动：", ev)

# 2. 代码状态、版本、摘要
state = run("bash", "handoff/release/code_state.sh").stdout.strip()
assert state == STATE, state
man = json.load(open("dist/manifest.json", encoding="utf-8"))
assert (man["source_version"], man["generator_version"], man["simple_version"], man["source_sha256"]) == ("2026.10.31-1", "1.12.1", "2026.10.31-2", DIGEST), man

# 3. 文档核对（核对项和旧说法从 finalize.py 读）
src = read("handoff/release/r21-as-used/finalize.py")
ns = {}
exec(src[src.index("H8 = "):src.index("def read(p):")], ns)
DOC_NEEDLES, STALE = list(ns["DOC_NEEDLES_R21"]), dict(ns["STALE"])
H8 = ns["H8"]
DOC_NEEDLES_R21B = (
    ("README.md", ["Twenty rounds of external input", "r21b (2026-11-17) changes documentation only",
                   "on 2026-11-17 the owner approved r21 and `main` was fast-forwarded to r21b", "`main` carries r21b"]),
    ("README.zh-CN.md", ["外部意见一共 20 轮", "第 20 轮是 r21 正式版", "r21b（2026-11-17）只改了文档", "2026-11-17 你说可以，`main` 从 r19 更新到了这一版"]),
    ("PROJECT_STATE.md", ["**r21b：发布到 `main`**", "T38 第 20 轮", "| 把 r21 推到 `main` | 已完成 |"]),
    ("00-审核说明.md", ["**交付以后（r21b，2026-11-17）**", "`main` 是 2026-11-17 发布的 r21b"]),
    ("docs/05-验收记录.md", ["- **交付以后**（2026-11-17）：GPT 审核 r21（审核 PR #9", "`manifest.json` 整份没有比", "recheck_r21b.py"]),
    ("docs/10-简易版框架.md", ["2026-11-17 按 GPT 审核 R21-F04 改", "2026-11-17 GPT 审了 r21（`docs/08` 第 20 轮）"]),
    ("docs/06-已知限制与待决事项.md", ["2026-11-17 补注：这一行是你选之前的原文", "**2026-11-17 你看过 GPT 对 r21 的审核以后说“没有问题了 更新吧”"]),
    (H8, ["## 第 20 轮：2026-11-17，GPT 审核 r21 正式版（审核 PR #9）", "docs/evidence/gpt-r21/", "R21-F04"]),
    ("docs/07-需求对照.md", ["### 2026-11-17（r21 交付以后，r21b）"]),
    ("docs/00-需求原文.md", ["## 补充（2026-11-17，GPT 审完 r21 正式版", "没有问题了 更新吧"]),
    ("docs/01-导入、更新、诊断与回滚.md", ["**2026-11-17 你说可以以后，`main` 更新到了 r21b**"]),
    ("docs/09-真机验收操作清单.md", ["2026-11-17 起 `main` 上有简易版"]),
    ("handoff/README.md", ["10. **交付以后（r21b，2026-11-17）**", "11. **发布**：2026-11-17", "| `main` | r21b"]),
)
# 发布以前、r21 时的现状，现在不应再出现（docs/00、docs/08 是逐轮的记录，除外）
for k in ("Nineteen rounds of external input", "外部意见一共 19 轮", "（`main` 上还没有）", "not on `main` yet", "`main` still carries r19", "`main` 上现在是 r19",
          "`main` 更新到这一版以前取不到", "only after `main` moves to this version", "它还在审，`main` 上还没有", "r20 也等你说可以再更新 `main`",
          "`main` 是 2026-10-19 发布的 r19；r20、r21 在这个分支上", "2026-10-19 起 `main` 是 r19（使用者看过", "| `main` | r19，统一源",
          "| 请审核方审 r21 | 等你转给 GPT |", "`main` 更新以前，导入地址里还取不到简易版", "`main` 更新以后才取得到。", "1. r21 交给你了"):
    STALE[k] = []
STALE["同样的道理放大六倍"] = ["docs/10-简易版框架.md"]                     # docs/10 那一处是更正说明里引的旧话
files = (["README.md", "README.zh-CN.md", "PROJECT_STATE.md", "00-审核说明.md", "handoff/README.md"]
         + sorted(os.path.join("docs", f) for f in os.listdir("docs") if f.endswith(".md")))
problems = []
left = [(p, x) for p in files for x in re.findall(r"⟦[^⟧]*⟧", read(p)) if x != "⟦名字⟧"]
if left:
    problems.append(("占位符", left))
for p, needles in DOC_NEEDLES + list(DOC_NEEDLES_R21B):
    s = read(p)
    problems += [("缺少", p, n) for n in needles if n not in s]
HIST = ["docs/00-需求原文.md", "docs/08-外部审核记录.md"]
for p in files:
    s = read(p)
    for k, allowed in STALE.items():
        if k in s and p not in allowed and p not in HIST:
            problems.append(("旧说法", p, k))
d06 = read("docs/06-已知限制与待决事项.md")
pending = d06[d06.index("## 需要你决定的事项"):d06.index("## 2026-10-31 你定下的事项")]
decided = d06[d06.index("## 2026-10-31 你定下的事项"):d06.index("## 2026-10-15 你定下的事项")]
if "\n| 23 |" in pending or "\n| 23 |" not in decided or "\n\n| 23 |" in decided:
    problems.append(("第 23 项的位置",))
doc05 = read("docs/05-验收记录.md")
sha = {rel: (v["sha256"] if isinstance(v, dict) else v) for rel, v in man["outputs"].items()}
problems += [("docs/05 没有摘要", rel) for rel in man["outputs"] if f"`{sha[rel][:8]}…`" not in doc05]
if DIGEST not in doc05 or STATE not in doc05:
    problems.append(("docs/05 没有统一源摘要或代码状态",))
for x in problems:
    print("  ", x)
if problems:
    sys.exit(1)
print(f"相对 r21（{R21}）只改了文档；代码状态 {STATE[:8]}… 与定稿时相同；文档核对 {sum(len(n) for _, n in DOC_NEEDLES) + sum(len(n) for _, n in DOC_NEEDLES_R21B)} 项、"
      f"旧说法 {len(STALE)} 条都对。核对通过")
