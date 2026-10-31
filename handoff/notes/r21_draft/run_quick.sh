#!/usr/bin/env bash
# r21 送审稿（2026-10-31：三个测速间隔）的快速检查。不是 tools/run_checks.sh：不写 docs/evidence/（那是定稿以后出版时写的），
# 输出写到这个目录的 logs/；本机的临时目录、仓库目录在日志里换成 <tmp>、<repo>。
# 用法：source ~/proxy-vendor/env.sh 以后，在仓库根目录运行
#   bash handoff/notes/r21_draft/run_quick.sh <r20 的工程目录>
# 自动测试在 Python 3.13、3.12、3.11 上各跑一遍（并行）；其余各步和 run_checks.sh 里同名的步骤用同样的命令。
set -u
cd "$(dirname "$0")/../../.."
REPO=$(pwd)
OUT=handoff/notes/r21_draft/logs
OLD=${1:?要给 r20 的工程目录}
mkdir -p "$OUT"
failed=()
# 文档以外的部分和提交是否相同（文档不影响检查结果；送审稿是先跑检查、再把结果写进文档）
if [ -z "$(git status --porcelain -- build.py generator source dist tests tools)" ]; then
  CODE_STATE="（build.py、generator、source、dist、tests、tools）与提交相同"
else
  CODE_STATE="（build.py、generator、source、dist、tests、tools）有未提交的改动"
fi

scrub() {  # 把本机路径换成占位，免得日志里带上这台机器的目录
  sed -e "s#$REPO#<repo>#g" -e "s#$OLD#<r20>#g" -e 's#\(\.\./\)*\.\./tmp/[A-Za-z0-9_.-]*#<tmp>#g' -e 's#/tmp/[A-Za-z0-9_.-]*#<tmp>#g'
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
step compare-r20 python3 tools/compare_versions.py --old "$OLD" --old-label r20 --new-label r21 \
  --write --out handoff/notes/r21_draft/与r20的对比.md
step mutations-check-edits python3 tools/check_mutations.py --check-edits

echo
if [ "${#failed[@]}" -gt 0 ]; then
  echo "以下步骤失败：${failed[*]}"
  exit 1
fi
echo "快速检查全部通过。"
