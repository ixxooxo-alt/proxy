#!/usr/bin/env bash
# r21：定稿以后、和变异检查同时跑的那一串（照 r20-as-used/chain20.sh 改的；时间文件三行：开始 / exit / 结束）。
# 一次性核对换成 r21 的：r20_full_private_same.py（完整版的私密产物和 r19 相同）这一版不成立了——Stash 完整版的选择组加了 interval——
# 换成 handoff/notes/r21_private_vs_r20.py（带本地补充和节点的私密产物相对 r20 只变了使用者定的那几个间隔）。
set -u
cd /home/user/proxy
source ~/proxy-vendor/env.sh
W=~/proxy-work
stamp() { date -u +"%Y-%m-%d %H:%M:%S"; }
# 4. 全部检查，第一遍
{ stamp; } > $W/checks21-time.txt
bash tools/run_checks.sh > $W/checks21.out 2>&1; rc=$?
echo "exit $rc" >> $W/checks21.out
stamp >> $W/checks21-time.txt
rm -rf $W/checks21-logs && mkdir -p $W/checks21-logs && cp docs/evidence/*.log $W/checks21-logs/
git checkout -- docs/evidence/*.log
# 5. 全部测试在 Python 3.12、3.11 上
{
  echo "开始 $(stamp)"; python3.12 --version
  python3.12 -B -m unittest discover -s tests > $W/py312-21.out 2>&1; echo "exit $?"
  echo "中间 $(stamp)"; python3.11 --version
  python3.11 -B -m unittest discover -s tests > $W/py311-21.out 2>&1; echo "exit $?"
  echo "结束 $(stamp)"
} > $W/py21-time.txt 2>&1
# 6. 运行环境核对
python3 -B handoff/release/r21-as-used/vendor_check.py > $W/vendor21-check.txt 2>&1
# 7. 一次性核对和版本对比
one() {  # one 时间文件 命令...
  local t="$1"; shift
  echo "开始 $(stamp)" > "$W/$t"
  "$@"; echo "exit $?" >> "$W/$t"
  echo "结束 $(stamp)" >> "$W/$t"
}
one icu21-time.txt bash -c 'python3 -B handoff/notes/r17_stash_filters_icu.py > handoff/notes/r17_stash_filters_icu.out 2>&1'
one probe21-time.txt bash -c 'python3 -B handoff/notes/r15_review_probes.py > handoff/notes/r15_review_probes.out 2>&1'
mkdir -p $W/pv21
one pv21-time.txt bash -c "python3 -B handoff/notes/r21_private_vs_r20.py $W/r20 /home/user/proxy $W/pv21 > handoff/notes/r21_private_vs_r20.out 2>&1"
one cmp21-time.txt bash -c 'python3 -B tools/compare_versions.py --old ~/proxy-work/r20 --old-label r20 --new-label r21 --write && python3 -B tools/compare_versions.py --old ~/proxy-work/r7 --old-label r7 --new-label r21 --write --out docs/evidence/与r7的对比.md'
echo "全部完成 $(stamp)" > $W/chain21-done.txt
