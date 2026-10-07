#!/usr/bin/env bash
# 变异检查分几批（缺省两批：单数编号、双数编号）同时在后台跑，日志写到工作目录。
# r12 有 98 类，两批并行大约 80 分钟；一类一两分钟，M45 要等满 5 分钟。
# 2026-10-07（r14）：115 类，一类约 4 分钟（测试本身变慢了：一遍约 230 秒），两批要将近 4 小时；
# 机器有 4 个核时用 MUT_BATCHES=3 分三批（编号除以 3 的余数分组），约 2.5 小时，留一个核给 run_checks.sh。
#
# 用法：[MUT_BATCHES=2|3|4] bash handoff/release/run_mutations.sh [工作目录] [只跑这些编号…]
#   工作目录缺省 ~/proxy-work/mut（在仓库以外）。不带编号时跑全部。日志是 mut-A-…、mut-B-…（三批时还有 mut-C-…）。
# 开始前它会记下开始时间（UTC）和代码状态哈希。跑的过程中不要改 build.py、generator/、source/、tests/、tools/：
# 改了，这一轮结果就作废，要重新定稿、从头再跑。只改 docs/、README、PROJECT_STATE.md、00-审核说明.md 没有关系。
#
# 看进度：grep -c '^\[' 工作目录/mut-*.log     跑完的标志：每份日志最后一行是“合计 N/N 被发现”。
# 机器被回收时后台进程会消失、日志留着：把已经有结果的编号去掉，带上剩下的编号再运行一次（会另起一段日志），
# 汇总时把各段都列进 segments.json（见 handoff/release/README.md）。
# 要中止：pgrep -f '[c]heck_mutations\.py' | xargs -r kill
#   （不要用 pkill -f "check_mutations.py"：那条命令自己的命令行里也有这串字，会把自己所在的 shell 一起杀掉。）
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
OUT="$(realpath -m "${1:-$HOME/proxy-work/mut}")"
[ "$#" -gt 0 ] && shift
case "$OUT/" in "$REPO"/*) echo "工作目录不能在仓库里面：$OUT" >&2; exit 2 ;; esac
mkdir -p "$OUT"
cd "$REPO"

mapfile -t known < <(python3 -c '
import sys
sys.path.insert(0, "tools")
import check_mutations as m
print("\n".join(c[0].split()[0] for c in m.cases))')
if [ "$#" -gt 0 ]; then ids=("$@"); else ids=("${known[@]}"); fi
NB="${MUT_BATCHES:-2}"
case "$NB" in 2|3|4) ;; *) echo "MUT_BATCHES 只能是 2、3、4：$NB" >&2; exit 2 ;; esac
A=(); B=(); C=(); D=()
for id in "${ids[@]}"; do
  if ! printf '%s\n' "${known[@]}" | grep -qx -- "$id"; then
    echo "没有这个编号：$id（现在有 ${known[0]} … ${known[-1]}，共 ${#known[@]} 类）" >&2
    exit 2
  fi
  n="${id#M}"
  if [ "$NB" = 2 ]; then
    if (( n % 2 )); then A+=("$id"); else B+=("$id"); fi
  else
    case $(( n % NB )) in 1) A+=("$id") ;; 2) B+=("$id") ;; 0) if [ "$NB" = 3 ]; then C+=("$id"); else D+=("$id"); fi ;; 3) C+=("$id") ;; esac
  fi
done
python3 tools/check_mutations.py --check-edits >/dev/null || { echo "有变异的改动套不到当前代码上：先运行 python3 tools/check_mutations.py --check-edits 看是哪几个" >&2; exit 1; }

seg="$(date -u +%Y%m%dT%H%M%SZ)"
date -u +"%Y-%m-%d %H:%M:%S" > "$OUT/mut-start-$seg.txt"
bash handoff/release/code_state.sh > "$OUT/code-state-$seg.txt"
python3 -c 'import json; print(json.load(open("dist/manifest.json", encoding="utf-8"))["source_sha256"])' > "$OUT/digest-$seg.txt"
if [ "${#A[@]}" -gt 0 ]; then nohup python3 tools/check_mutations.py "${A[@]}" > "$OUT/mut-A-$seg.log" 2>&1 & fi
if [ "${#B[@]}" -gt 0 ]; then nohup python3 tools/check_mutations.py "${B[@]}" > "$OUT/mut-B-$seg.log" 2>&1 & fi
if [ "${#C[@]}" -gt 0 ]; then nohup python3 tools/check_mutations.py "${C[@]}" > "$OUT/mut-C-$seg.log" 2>&1 & fi
if [ "${#D[@]}" -gt 0 ]; then nohup python3 tools/check_mutations.py "${D[@]}" > "$OUT/mut-D-$seg.log" 2>&1 & fi
echo "已在后台启动（$NB 批）：A ${#A[@]} 类、B ${#B[@]} 类、C ${#C[@]} 类、D ${#D[@]} 类 → $OUT/mut-?-$seg.log"
echo "开始时间（UTC）$(cat "$OUT/mut-start-$seg.txt")；代码状态 $(cat "$OUT/code-state-$seg.txt")"
