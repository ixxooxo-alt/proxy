#!/usr/bin/env bash
# r20：定稿以后、和变异检查同时跑的那一串（照 r19-as-used/README.md 的第 4–7 步；时间文件三行：开始 / exit / 结束）
set -u
cd /home/user/proxy
source ~/proxy-vendor/env.sh
W=~/proxy-work
stamp() { date -u +"%Y-%m-%d %H:%M:%S"; }
# 4. 全部检查，第一遍
{ stamp; } > $W/checks20-time.txt
bash tools/run_checks.sh > $W/checks20.out 2>&1; rc=$?
echo "exit $rc" >> $W/checks20.out
stamp >> $W/checks20-time.txt
rm -rf $W/checks20-logs && mkdir -p $W/checks20-logs && cp docs/evidence/*.log $W/checks20-logs/
git checkout -- docs/evidence/*.log
# 5. 全部测试在 Python 3.12、3.11 上
{
  echo "开始 $(stamp)"; python3.12 --version
  python3.12 -B -m unittest discover -s tests > $W/py312-20.out 2>&1; echo "exit $?"
  echo "中间 $(stamp)"; python3.11 --version
  python3.11 -B -m unittest discover -s tests > $W/py311-20.out 2>&1; echo "exit $?"
  echo "结束 $(stamp)"
} > $W/py20-time.txt 2>&1
# 6. 运行环境核对
python3 -B handoff/release/r20-as-used/vendor_check.py > $W/vendor20-check.txt 2>&1
# 7. 一次性核对和版本对比
one() {  # one 时间文件 命令...
  local t="$1"; shift
  echo "开始 $(stamp)" > "$W/$t"
  "$@"; echo "exit $?" >> "$W/$t"
  echo "结束 $(stamp)" >> "$W/$t"
}
one icu20-time.txt bash -c 'python3 -B handoff/notes/r17_stash_filters_icu.py > handoff/notes/r17_stash_filters_icu.out 2>&1'
one probe20-time.txt bash -c 'python3 -B handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out 2>&1'
mkdir -p $W/fp20
one fp20-time.txt bash -c "python3 -B handoff/notes/r20_full_private_same.py $W/r19 $W/r20-draft /home/user/proxy $W/fp20 > handoff/notes/r20_full_private_same.out 2>&1"
one cmp20-time.txt bash -c 'python3 -B tools/compare_versions.py --old ~/proxy-work/r19 --old-label r19 --new-label r20 --write && python3 -B tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r20 --write --out docs/evidence/与r7的对比.md'
echo "全部完成 $(stamp)" > $W/chain20-done.txt
