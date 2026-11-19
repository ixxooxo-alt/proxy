#!/usr/bin/env bash
# r22 第二份送审稿（2026-11-19：第一份送审稿的两份审核，docs/08 第 24、25 轮）的快速检查。照 handoff/notes/r22_draft/run_quick.sh 改：
# 私密产物改成和第一份送审稿比（handoff/notes/r22b_private_vs_r22draft.py），另加官方程序核对（handoff/notes/r22b_review_probes.py）；
# 打包验包自测去掉 PYTHONUNBUFFERED 跑（这个云端环境设了它，会把“测试打印的字排在汇总后面”这种情况藏起来，GPT 审核 R22-F02）。
# 不是 tools/run_checks.sh：不写 docs/evidence/，输出写到这个目录的 logs/；本机的临时目录、仓库目录在日志里换成 <tmp>、<repo>。
# 用法：source ~/proxy-vendor/env.sh 以后，在仓库根目录运行
#   bash handoff/notes/r22_draft2/run_quick.sh <r21b 的工程目录> <第一份送审稿 f60ee42 的工程目录>
# 自动测试在 Python 3.13、3.12、3.11 上各跑一遍（并行）；其余各步和 run_checks.sh 里同名的步骤用同样的命令。
set -u
cd "$(dirname "$0")/../../.."
REPO=$(pwd)
OUT=handoff/notes/r22_draft2/logs
OLD=${1:?要给 r21b 的工程目录}
DRAFT1=${2:?要给第一份送审稿的工程目录}
mkdir -p "$OUT"
failed=()
# 文档以外的部分和提交是否相同（文档不影响检查结果；送审稿是先跑检查、再把结果写进文档）
if [ -z "$(git status --porcelain -- build.py generator source dist tests tools)" ]; then
  CODE_STATE="（build.py、generator、source、dist、tests、tools）与提交相同"
else
  CODE_STATE="（build.py、generator、source、dist、tests、tools）有未提交的改动"
fi

scrub() {  # 把本机路径换成占位，免得日志里带上这台机器的目录
  sed -e "s#$REPO#<repo>#g" -e "s#$OLD#<r21b>#g" -e "s#$DRAFT1#<draft1>#g" -e "s#$HOME/proxy-work#<work>#g" -e 's#\(\.\./\)*\.\./tmp/[A-Za-z0-9_.-]*#<tmp>#g' -e 's#/tmp/[A-Za-z0-9_.-]*#<tmp>#g'
}

step() {  # step 名字 命令...：输出写进 logs/名字.log，保留真实退出码
  local name="$1"
  shift
  (
    date -u +"运行时间（UTC）：%Y-%m-%d %H:%M:%S"
    echo "Python：$(python3 --version 2>&1)，PyYAML：$(python3 -c 'import yaml;print(yaml.__version__)' 2>&1)"
    echo "提交：$(git rev-parse --short HEAD)；代码和产物$CODE_STATE"
    echo "命令：$*"
    echo
    "$@" 2>&1
    echo "退出码：$?"
  ) | scrub > "$OUT/$name.log"
  tail -n 1 "$OUT/$name.log"
  grep -q "^退出码：0$" "$OUT/$name.log" || failed+=("$name")
}

step build-check python3 build.py --check

for v in 3.13 3.12 3.11; do
  (
    date -u +"运行时间（UTC）：%Y-%m-%d %H:%M:%S"
    echo "Python：$(python$v --version 2>&1)，PyYAML：$(python$v -c 'import yaml;print(yaml.__version__)' 2>&1)"
    echo "提交：$(git rev-parse --short HEAD)；代码和产物$CODE_STATE"
    echo "命令：python$v -B -m unittest discover -s tests -v"
    echo
    python$v -B -m unittest discover -s tests -v 2>&1
    echo "退出码：$?"
  ) | scrub > "$OUT/tests-py$v.log" &
done
wait
for v in 3.13 3.12 3.11; do
  tail -n 4 "$OUT/tests-py$v.log" | head -n 3
  grep -q "^退出码：0$" "$OUT/tests-py$v.log" || failed+=("tests-py$v")
done

step official-check python3 tools/check_official.py --mihomo "$MIHOMO_BIN" --singbox "$SINGBOX_BIN" \
  --singbox-112 "$SINGBOX112_BIN" --geodata-dir "$GEODATA_DIR"
step icu-check python3 tools/check_icu.py --public --verbose
step upstream-field-check python3 tools/verify_with_upstream_source.py --mihomo-src "$MIHOMO_SRC" --singbox-src "$SINGBOX_SRC"
step icons-check python3 tools/check_icons.py --icon-repo "$ICON_REPO"
step compare-r21b python3 tools/compare_versions.py --old "$OLD" --old-label r21b --new-label r22 \
  --write --out handoff/notes/r22_draft2/与r21b的对比.md
step mutations-check-edits python3 tools/check_mutations.py --check-edits
# 全项目复核 F05–F07：打包、验包脚本的自测（好包、坏包、删除前的路径判断）；要求 HEAD 是要审的提交
step selftest-package env -u PYTHONUNBUFFERED python3 -B handoff/release/selftest_package.py
# 相对第一份送审稿的私密产物（带本地补充、虚构订阅和节点）：只差这一轮有意改的地方
rm -rf "$HOME/proxy-work/r22b-private-cmp"
step private-vs-draft1 python3 -B handoff/notes/r22b_private_vs_r22draft.py "$DRAFT1" "$REPO" "$HOME/proxy-work/r22b-private-cmp"
# 两份审核里拿官方程序核实的几件事（订阅读法、重复键、SS2022 密钥、QUIC 上的 uTLS）
rm -rf "$HOME/proxy-work/r22b-probes"
step review-probes python3 -B handoff/notes/r22b_review_probes.py "$MIHOMO_BIN" "$SINGBOX_BIN" "$SINGBOX112_BIN" "$HOME/proxy-work/r22b-probes"
# F03 的同一类：sing-box 认哪些取值（官方程序逐个 check）
step singbox-enum-sweep python3 -B handoff/notes/r22_singbox_enum_sweep.py "$SINGBOX_BIN" "$SINGBOX112_BIN"

echo
if [ "${#failed[@]}" -gt 0 ]; then
  echo "以下步骤失败：${failed[*]}"
  exit 1
fi
echo "快速检查全部通过。"
