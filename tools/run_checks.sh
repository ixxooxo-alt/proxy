#!/usr/bin/env bash
# 生成 + 测试 + （可选）上游源码字段核对 + （可选）规则上游快照核对，并把完整日志写到 docs/evidence/。
# 可选：MIHOMO_SRC=/path/to/mihomo  SINGBOX_SRC=/path/to/sing-box \
#       DLC_SRC=/path/to/domain-list-community  BM7_SRC=/path/to/ios_rule_script  bash tools/run_checks.sh
# DLC_SRC / BM7_SRC 必须检出到 source/evidence.yaml 里登记的 snapshot 提交，否则核对会失败。
set -u
cd "$(dirname "$0")/.."
mkdir -p docs/evidence
python3 build.py || exit $?
digest=$(python3 -c 'import json;print(json.load(open("dist/manifest.json"))["source_sha256"])')
{
  date -u +"运行时间（UTC）：%Y-%m-%d %H:%M:%S"
  echo "Python：$(python3 --version 2>&1)，PyYAML：$(python3 -c 'import yaml;print(yaml.__version__)')"
  echo "统一源摘要：$digest"
  echo "命令：python3 -m unittest discover -s tests -v"
  echo
  python3 -m unittest discover -s tests -v 2>&1
  echo "退出码：$?"
} > docs/evidence/tests.log
tail -n 3 docs/evidence/tests.log
if [ -n "${MIHOMO_SRC:-}" ] || [ -n "${SINGBOX_SRC:-}" ]; then
  args=()
  [ -n "${MIHOMO_SRC:-}" ] && args+=(--mihomo-src "$MIHOMO_SRC")
  [ -n "${SINGBOX_SRC:-}" ] && args+=(--singbox-src "$SINGBOX_SRC")
  {
    date -u +"运行时间（UTC）：%Y-%m-%d %H:%M:%S"
    [ -n "${MIHOMO_SRC:-}" ] && echo "mihomo 源码：$(git -C "$MIHOMO_SRC" describe --tags 2>/dev/null)（提交 $(git -C "$MIHOMO_SRC" rev-parse --short HEAD 2>/dev/null)）"
    [ -n "${SINGBOX_SRC:-}" ] && echo "sing-box 源码：$(git -C "$SINGBOX_SRC" describe --tags 2>/dev/null)（提交 $(git -C "$SINGBOX_SRC" rev-parse --short HEAD 2>/dev/null)）"
    echo "统一源摘要：$digest"
    echo "命令：python3 tools/verify_with_upstream_source.py ${args[*]}"
    echo
    python3 tools/verify_with_upstream_source.py "${args[@]}" 2>&1
    echo "退出码：$?"
  } > docs/evidence/upstream-field-check.log
  tail -n 3 docs/evidence/upstream-field-check.log
fi
if [ -n "${DLC_SRC:-}" ] && [ -n "${BM7_SRC:-}" ]; then
  {
    date -u +"运行时间（UTC）：%Y-%m-%d %H:%M:%S"
    echo "统一源摘要：$digest"
    echo "命令：python3 tools/check_upstream_evidence.py --dlc <DLC_SRC> --bm7 <BM7_SRC>"
    echo
    python3 tools/check_upstream_evidence.py --dlc "$DLC_SRC" --bm7 "$BM7_SRC" 2>&1
    echo "退出码：$?"
  } > docs/evidence/upstream-evidence-check.log
  tail -n 2 docs/evidence/upstream-evidence-check.log
fi
