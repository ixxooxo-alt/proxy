#!/usr/bin/env bash
# r21：变异检查跑完以后自动接着做的两步（照 r20-as-used/after20.sh 改的）。用法：nohup bash handoff/release/r21-as-used/after21.sh <段名> <定稿时间> &
# 段名是 run_mutations.sh 写的 mut-start-<段名>.txt 里的那一段（如 20261031T170000Z），定稿时间如 "2026-10-31 16:59"。
# 等三批变异日志都写出“合计”行；有一批没正常结束、或者有没被发现的，就停下不接着跑。日志在 ~/proxy-work/after21.log。
set -u
cd /home/user/proxy
source ~/proxy-vendor/env.sh
W=~/proxy-work
D=$W/mut21
SEG="${1:?段名}"
FROZEN="${2:?定稿时间}"
L="$D/mut-A-$SEG.log $D/mut-B-$SEG.log $D/mut-C-$SEG.log"
stamp() { date -u +"%Y-%m-%d %H:%M:%S"; }
until [ "$(grep -l '^合计 ' $L 2>/dev/null | wc -l)" = 3 ] || ! pgrep -f '[c]heck_mutations\.py' >/dev/null; do sleep 60; done
echo "变异检查结束（或进程不在了）$(stamp)"
ok=yes
for f in $L; do
  n=$(grep -c '^\[' "$f"); last=$(tail -1 "$f")
  echo "$(basename "$f")：$n 类；最后一行：$last"
  [ "$last" = "合计 $n/$n 被发现" ] || ok=no
done
[ "$ok" = yes ] || { echo "有一批没有正常结束，或者有没被发现的：不接着跑"; exit 1; }
# 5. 汇总变异日志
cat > "$D/segments.json" <<EOF
[{"start": "mut-start-$SEG.txt", "code_state": "code-state-$SEG.txt", "logs": ["mut-A-$SEG.log", "mut-B-$SEG.log", "mut-C-$SEG.log"]}]
EOF
python3 -B handoff/release/r21-as-used/assemble.py "$D" || { echo "assemble.py 失败"; exit 1; }
python3 -B handoff/release/r21-as-used/write_mutlog.py "$D" "$FROZEN" || { echo "write_mutlog.py 失败"; exit 1; }
echo "mutations.log 已写好 $(stamp)"
# 6. 全部检查，第二遍（交付的日志是这一遍的）。第一遍（chain21.sh）还没跑完时先等它
until [ -e "$W/chain21-done.txt" ]; do sleep 60; done
stamp > "$W/checks21b-time.txt"
bash tools/run_checks.sh > "$W/checks21b.out" 2>&1; rc=$?
echo "exit $rc" >> "$W/checks21b.out"
stamp >> "$W/checks21b-time.txt"
echo "第二遍全部检查结束 $(stamp)，退出码 $rc"
echo "全部完成 $(stamp)" > "$W/after21-done.txt"
