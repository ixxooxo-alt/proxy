#!/usr/bin/env bash
# 生成 + 测试 + Cursor 对照报告迁入核对 + ICU 正则核对（有 ICU 时）+ （可选）官方程序检查 + （可选）真实数据路由核对
# + （可选）上游源码字段核对 + （可选）图标核对 + （可选）规则上游快照核对 + （可选）严格版国内域名清单核对。
# 每一步的完整日志写到 docs/evidence/。任何一步失败，脚本最后以非零退出码结束
# （2026-09-30 审核 F08：以前只把退出码写进日志，脚本本身总是返回 0）。
#
# 可选环境变量：
#   MIHOMO_BIN / SINGBOX_BIN [/ SINGBOX112_BIN / GEODATA_DIR]   官方程序与 mihomo 地理数据（tools/check_official.py）
#   MIHOMO_SRC / SINGBOX_SRC     上游源码检出目录（tools/verify_with_upstream_source.py）
#   DLC_SRC / BM7_SRC            规则上游快照检出目录，必须是 source/evidence.yaml 登记的提交（tools/check_upstream_evidence.py）。
#                                给了 DLC_SRC 时另外核对严格版的国内域名清单（source/data/cn-domains.txt）确实是按这个快照生成的、
#                                没有手改过（tools/update_cn_list.py --check；给了 BM7_SRC 时连同上游大清单的副本）
#   ICON_REPO                    图标仓库（source/icons.yaml 里登记的那个）的检出目录：核对配置里写的每个图标在仓库里都有（tools/check_icons.py）
#   SRS_DIR                      sing-box 远程规则集的 .srs 文件所在目录。与 MIHOMO_BIN / SINGBOX_BIN / GEODATA_DIR / BM7_SRC
#                                都给了时，用官方内核和这些真实数据核对路由与 DNS 去向（tools/check_real_routes.py）；
#                                GEODATA_ORIGIN / SRS_ORIGIN / BM7_ORIGIN 可以写上数据文件的来历，会记进日志
set -u
cd "$(dirname "$0")/.."
mkdir -p docs/evidence
failed=()
digest="（生成失败，未计算）"
env_line="Python：$(python3 --version 2>&1)，PyYAML：$(python3 -c 'import yaml;print(yaml.__version__)' 2>&1)"

# run_step 名称 日志文件 命令...：完整输出写进日志，保留命令的真实退出码
run_step() {
  local name="$1" log="$2"
  shift 2
  (
    date -u +"运行时间（UTC）：%Y-%m-%d %H:%M:%S"
    echo "$env_line"
    echo "统一源摘要：$digest"
    echo "命令：$*"
    echo
    "$@" 2>&1
    rc=$?
    echo "退出码：$rc"
    exit $rc
  ) > "$log"
  local rc=$?
  tail -n 2 "$log"
  if [ "$rc" -ne 0 ]; then
    failed+=("$name（退出码 $rc，日志 $log）")
  fi
}

if python3 build.py; then
  digest=$(python3 -c 'import json;print(json.load(open("dist/manifest.json"))["source_sha256"])')
else
  failed+=("生成（build.py）")
fi

run_step "自动测试" docs/evidence/tests.log python3 -m unittest discover -s tests -v

if [ -f "docs/evidence/cursor-对照明细.csv" ]; then
  run_step "Cursor 对照报告核对" docs/evidence/cursor-report-check.log python3 tools/check_cursor_report.py --write
fi

# 节点筛选正则在 ICU 上的结果（推断 Loon / Quantumult X 用的是苹果系统自带的正则，底层是 ICU）。
# 退出码 2 = 这台机器没有 ICU，算跳过，不算失败
if [ -f tools/check_icu.py ]; then
  before=${#failed[@]}
  run_step "ICU 正则核对" docs/evidence/icu-check.log python3 tools/check_icu.py --public --verbose
  if [ "${#failed[@]}" -gt "$before" ] && grep -q "^退出码：2$" docs/evidence/icu-check.log; then
    unset "failed[$before]"
    failed=("${failed[@]}")
    echo "（没有可用的 ICU 库，已跳过）"
  fi
fi

if [ -n "${MIHOMO_BIN:-}" ] && [ -n "${SINGBOX_BIN:-}" ]; then
  args=(--mihomo "$MIHOMO_BIN" --singbox "$SINGBOX_BIN")
  [ -n "${SINGBOX112_BIN:-}" ] && args+=(--singbox-112 "$SINGBOX112_BIN")
  [ -n "${GEODATA_DIR:-}" ] && args+=(--geodata-dir "$GEODATA_DIR")
  run_step "官方程序检查" docs/evidence/official-check.log python3 tools/check_official.py "${args[@]}"
fi

if [ -n "${MIHOMO_BIN:-}" ] && [ -n "${SINGBOX_BIN:-}" ] && [ -n "${GEODATA_DIR:-}" ] && [ -n "${SRS_DIR:-}" ] && [ -n "${BM7_SRC:-}" ]; then
  args=(--mihomo "$MIHOMO_BIN" --singbox "$SINGBOX_BIN" --geodata-dir "$GEODATA_DIR" --srs-dir "$SRS_DIR" --bm7 "$BM7_SRC")
  [ -n "${SINGBOX112_BIN:-}" ] && args+=(--singbox-112 "$SINGBOX112_BIN")
  [ -n "${DLC_SRC:-}" ] && args+=(--dlc "$DLC_SRC")
  [ -n "${GEODATA_ORIGIN:-}" ] && args+=(--geodata-origin "$GEODATA_ORIGIN")
  [ -n "${SRS_ORIGIN:-}" ] && args+=(--srs-origin "$SRS_ORIGIN")
  [ -n "${BM7_ORIGIN:-}" ] && args+=(--bm7-origin "$BM7_ORIGIN")
  run_step "真实数据路由核对" docs/evidence/real-route-check.log python3 tools/check_real_routes.py "${args[@]}"
fi

if [ -n "${MIHOMO_SRC:-}" ] || [ -n "${SINGBOX_SRC:-}" ]; then
  args=()
  [ -n "${MIHOMO_SRC:-}" ] && args+=(--mihomo-src "$MIHOMO_SRC")
  [ -n "${SINGBOX_SRC:-}" ] && args+=(--singbox-src "$SINGBOX_SRC")
  run_step "字段名对照上游源码" docs/evidence/upstream-field-check.log python3 tools/verify_with_upstream_source.py "${args[@]}"
fi

if [ -n "${ICON_REPO:-}" ]; then
  run_step "图标核对" docs/evidence/icons-check.log python3 tools/check_icons.py --icon-repo "$ICON_REPO"
fi

if [ -n "${DLC_SRC:-}" ] && [ -n "${BM7_SRC:-}" ]; then
  run_step "规则证据对照上游快照" docs/evidence/upstream-evidence-check.log \
    python3 tools/check_upstream_evidence.py --dlc "$DLC_SRC" --bm7 "$BM7_SRC"
fi

if [ -n "${DLC_SRC:-}" ]; then
  # 给了 BM7_SRC 时一并核对 Quantumult X 严格版用的上游大清单副本（2026-10-07 起）
  args=(--dlc "$DLC_SRC")
  [ -n "${BM7_SRC:-}" ] && args+=(--bm7 "$BM7_SRC")
  run_step "严格版国内域名清单核对" docs/evidence/cn-list-check.log python3 tools/update_cn_list.py "${args[@]}" --check
fi

echo
if [ "${#failed[@]}" -gt 0 ]; then
  echo "以下步骤失败："
  printf '  - %s\n' "${failed[@]}"
  exit 1
fi
echo "全部检查通过。"
