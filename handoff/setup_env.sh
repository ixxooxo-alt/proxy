#!/usr/bin/env bash
# 搭检查环境：下载 mihomo / sing-box 的官方发布程序，按登记的提交号取回上游数据和源码，逐个核对 SHA-256，
# 最后写出一个 env.sh（tools/run_checks.sh 要用的环境变量都在里面）。
#
# 用法：bash handoff/setup_env.sh [目录]
#   目录：放下载内容的地方，缺省 ~/proxy-vendor（也可以用环境变量 PROXY_VENDOR 指定）。必须在仓库以外：
#         下载的程序、数据、第三方源码都不进仓库；也不要把自己写的脚本放进那个目录里运行。
# 可以重复运行：已经在、校验值对的就跳过。全新下载一两分钟，约 900 MB。只支持 Linux x86_64（云端会话的机器就是）。
#
# 这里登记的版本就是 r12（统一源 2026.10.06-1）的全部检查用的那一套，校验值和 r12 的日志里记的相同
# （docs/evidence/real-route-check.log 开头、docs/05-验收记录.md“官方程序检查”一行）。
# 上游的发布分支每天覆盖，登记的那个提交迟早取不到。取不到时脚本改取当天最新的，并在最后明确列出来：
# 那样数据就和 r12 记录的不同，核对结果里的数字会变，文档要按实际用的数据改（见 handoff/README.md 第 3 节）。
# 不要为了让数字对上去找别的来源的旧文件。
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
V="$(realpath -m "${1:-${PROXY_VENDOR:-$HOME/proxy-vendor}}")"
case "$V/" in
  "$REPO"/*) echo "放下载内容的目录不能在仓库里面：$V" >&2; exit 2 ;;
esac
if [ "$(uname -s)-$(uname -m)" != "Linux-x86_64" ]; then
  echo "这个脚本只登记了 Linux x86_64 的官方程序；这台机器是 $(uname -s)-$(uname -m)。" >&2
  echo "在别的系统上：照下面登记的版本号到各项目的 GitHub Releases 取对应的文件，核对发布页的 SHA-256，再手写 env.sh。" >&2
  exit 2
fi
mkdir -p "$V/bin" "$V/src" "$V/geodata" "$V/srs" "$V/cache"
TODAY="$(date -u +%F)"
DRIFT=()          # 没能按登记的提交取到、改用了最新的那几样

say() { printf '%s\n' "$*"; }
sha() { sha256sum "$1" | cut -d' ' -f1; }

# download 地址 目标文件 期望的SHA-256
download() {
  local url="$1" out="$2" want="$3"
  if [ -f "$out" ] && [ "$(sha "$out")" = "$want" ]; then say "  已有 $(basename "$out")"; return 0; fi
  say "  下载 $url"
  if ! curl -sS -L --fail --retry 3 --retry-delay 2 -o "$out.part" "$url"; then
    rm -f "$out.part"
    cat >&2 <<EOF
下载失败：$url
如果上面显示的是 403：这台机器的网络设置不允许访问这个地址。不要想办法绕过去，也不要换别的来源的文件，
把情况告诉使用者：云端环境的“网络访问”要是默认的 Trusted（要能访问 github.com 和 release-assets.githubusercontent.com）。
官方文档还提到，会话只能取“已经加进这次会话的仓库”的发布文件；这条在写这个脚本的环境里没有遇到，遇到了就照实说。
没有官方程序时，tools/check_official.py 和 tools/check_real_routes.py 这两项做不了，要在验收记录里写明，不能当作通过。
EOF
    return 1
  fi
  if [ "$(sha "$out.part")" != "$want" ]; then
    echo "下载到的文件校验值不对，没有采用：$url" >&2
    echo "  登记的 $want" >&2
    echo "  实际的 $(sha "$out.part")" >&2
    rm -f "$out.part"
    return 1
  fi
  mv "$out.part" "$out"
}

# check_file 文件 期望的SHA-256
check_file() {
  if [ "$(sha "$1")" != "$2" ]; then
    echo "校验值不对：$1（登记的 $2，实际的 $(sha "$1")）" >&2
    return 1
  fi
}

# fetch_commit 目录 仓库地址 提交号 [只检出这些目录…]
# 整个仓库按一个固定的提交取回（不带历史）；给了目录时只取这些目录里的文件。
fetch_commit() {
  local dir="$1" url="$2" commit="$3"
  shift 3
  if [ -d "$dir/.git" ] && [ "$(git -C "$dir" rev-parse HEAD 2>/dev/null)" = "$commit" ] \
     && [ -z "$(git -C "$dir" status --porcelain 2>/dev/null | head -n 1)" ]; then
    say "  已有 $(basename "$dir") @ ${commit:0:7}"
    return 0
  fi
  say "  取回 $url @ ${commit:0:7}"
  rm -rf "$dir"
  mkdir -p "$dir"
  git -C "$dir" init -q
  git -C "$dir" remote add origin "$url"
  if [ "$#" -gt 0 ]; then
    git -C "$dir" sparse-checkout set "$@"
    git -C "$dir" fetch -q --depth 1 --filter=blob:none origin "$commit"
  else
    git -C "$dir" fetch -q --depth 1 origin "$commit"
  fi
  git -C "$dir" -c advice.detachedHead=false checkout -q --detach FETCH_HEAD
  if [ "$(git -C "$dir" rev-parse HEAD)" != "$commit" ]; then
    echo "取回的提交不是登记的那个：$dir" >&2
    return 1
  fi
}

# fetch_files 名字 仓库地址 登记的提交号 取不到时改取的分支 目标目录 文件…
# 从一个提交里只取几个文件。结果记在全局变量 GOT_COMMIT、GOT_DATE、GOT_PINNED（yes / no）里。
fetch_files() {
  local name="$1" url="$2" commit="$3" branch="$4" outdir="$5"
  shift 5
  local repo="$V/cache/$name.git"
  if [ ! -d "$repo" ]; then
    git init -q --bare "$repo"
    git -C "$repo" remote add origin "$url"
  fi
  GOT_PINNED=yes
  say "  取回 $url @ ${commit:0:7} 里的 $# 个文件"
  if ! git -C "$repo" fetch -q --depth 1 --filter=blob:none origin "$commit" 2>/dev/null; then
    GOT_PINNED=no
    say "  ！登记的提交 ${commit:0:7} 取不到了，改取 $branch 分支现在的内容"
    git -C "$repo" fetch -q --depth 1 --filter=blob:none origin "$branch"
  fi
  GOT_COMMIT="$(git -C "$repo" rev-parse FETCH_HEAD)"
  GOT_DATE="$(git -C "$repo" log -1 --format=%cs FETCH_HEAD)"
  local f
  for f in "$@"; do
    git -C "$repo" cat-file blob "FETCH_HEAD:$f" > "$outdir/$f.part"
    mv "$outdir/$f.part" "$outdir/$f"
  done
  if [ "$GOT_PINNED" = no ]; then DRIFT+=("$name：登记的是 ${commit:0:7}，实际取到 ${GOT_COMMIT:0:7}（$GOT_DATE）"); fi
}

say "== 1. 这台机器 =="
say "  $(python3 --version 2>&1)；git $(git --version | cut -d' ' -f3)"
if ! python3 -c 'import yaml' 2>/dev/null; then
  say "  没有 PyYAML，现在安装（只装这一个包）"
  python3 -m pip install --quiet --user pyyaml 2>/dev/null \
    || python3 -m pip install --quiet --user --break-system-packages pyyaml
fi
say "  PyYAML $(python3 -c 'import yaml; print(yaml.__version__)')"
ICU="$(python3 -c 'import ctypes.util; print(ctypes.util.find_library("icui18n") or "")')"
if [ -n "$ICU" ]; then
  say "  ICU 库：$ICU"
else
  say "  ！没有找到 ICU 库（libicui18n）。tools/check_icu.py 会以退出码 2 跳过，那一项就等于没有检查。"
  say "    Ubuntu 上可以装：apt-get install -y libicu-dev。装不了就在验收记录里写明这一项没有做。"
fi
say "  r12 的日志是在 Python 3.11.17 / PyYAML 6.0.1 上跑出来的；这台机器不一样时结果应当相同，但文档里的运行环境要按实际的写。"

say "== 2. 官方发布程序（GitHub Releases；SHA-256 与发布页一致）=="
download "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.31/mihomo-linux-amd64-v1.19.31.gz" \
  "$V/bin/mihomo-linux-amd64-v1.19.31.gz" d5e74bbddbdfff49a1aef7775bf5911da59f0d7196ed509a0ac914b3653dd5f1
download "https://github.com/SagerNet/sing-box/releases/download/v1.14.1/sing-box-1.14.1-linux-amd64.tar.gz" \
  "$V/bin/sing-box-1.14.1-linux-amd64.tar.gz" 12cb2816b52febb356f6a885b740cc8758c3f30b8ae0ca8edba80f0d2d35343f
download "https://github.com/SagerNet/sing-box/releases/download/v1.12.0/sing-box-1.12.0-linux-amd64.tar.gz" \
  "$V/bin/sing-box-1.12.0-linux-amd64.tar.gz" f59b1253ae0143997cb46915af30d14a33431dcbd7e39edacfcde8d73050faaf
if [ ! -x "$V/bin/mihomo-linux-amd64-v1.19.31" ]; then
  gzip -dc "$V/bin/mihomo-linux-amd64-v1.19.31.gz" > "$V/bin/mihomo-linux-amd64-v1.19.31.part"
  chmod +x "$V/bin/mihomo-linux-amd64-v1.19.31.part"
  mv "$V/bin/mihomo-linux-amd64-v1.19.31.part" "$V/bin/mihomo-linux-amd64-v1.19.31"
fi
[ -x "$V/bin/sing-box-1.14.1-linux-amd64/sing-box" ] || tar -xzf "$V/bin/sing-box-1.14.1-linux-amd64.tar.gz" -C "$V/bin"
[ -x "$V/bin/sing-box-1.12.0-linux-amd64/sing-box" ] || tar -xzf "$V/bin/sing-box-1.12.0-linux-amd64.tar.gz" -C "$V/bin"
check_file "$V/bin/mihomo-linux-amd64-v1.19.31" 08787faafea19c1ab0f83fa5a1b22363b7d03ea78da18091a4c883aecaaa5979
check_file "$V/bin/sing-box-1.14.1-linux-amd64/sing-box" 9334a1c1fe97234911afaedd37226667ebdb3dab2abe383f2c4ae1387706dad9
check_file "$V/bin/sing-box-1.12.0-linux-amd64/sing-box" 84b23a2304a6c4efa41dc027a78b7226a94ef6c63566b56a5a2721bdfe473446
say "  mihomo v1.19.31、sing-box 1.14.1、sing-box 1.12.0：校验值都对"

say "== 3. 上游规则快照、上游源码、图标仓库（按登记的提交）=="
# 规则证据用的两个快照：提交号登记在 source/evidence.yaml，改这里之前先改那里
fetch_commit "$V/src/domain-list-community" https://github.com/v2fly/domain-list-community c1c2cf0d252871e8739747714df06e8d2671f72f
fetch_commit "$V/src/bm7" https://github.com/blackmatrix7/ios_rule_script 51d2e1dd8429a91be575157d6f8ed051c93559f8 \
  rule/Clash rule/Loon/AdvertisingLite rule/Loon/ChinaMax rule/QuantumultX/AdvertisingLite rule/QuantumultX/ChinaMax
# 字段名核对用的上游源码：mihomo v1.19.31、sing-box v1.14.1 两个标签对应的提交
fetch_commit "$V/src/mihomo" https://github.com/MetaCubeX/mihomo ab405bad5beeeac8b003bb01f60f134f6df54471
fetch_commit "$V/src/sing-box" https://github.com/SagerNet/sing-box 1ac1a339cb1223e9c70eae14c44411c75033c02d
# 使用者的图标仓库：只读。提交号登记在 source/icons.yaml 的 checked_commit
fetch_commit "$V/src/icon" https://github.com/ixxooxo-alt/icon f250126f57228b0b32f3445b21078e382e6152e9

say "== 4. mihomo 的地理数据（MetaCubeX/meta-rules-dat 的发布文件）=="
fetch_files meta-rules-dat https://github.com/MetaCubeX/meta-rules-dat f7c0420cdf589312aaf82cf51e061703d2621bca release "$V/geodata" \
  geosite.dat geoip.dat geoip.metadb country.mmdb GeoLite2-ASN.mmdb
if [ "$GOT_PINNED" = yes ]; then
  check_file "$V/geodata/geosite.dat" 79e7a395c57da61aeb3f68db01121c1a0730ab2bd1c8bbe4c0c327786e225134
  check_file "$V/geodata/geoip.dat" 391b522361c52804e486a98b53d97f3d9c1d3e4e4217bb34954774a0b456b9fd
  check_file "$V/geodata/geoip.metadb" 2f9c61b9f261f0a06c2391500d4056d1ab27e738260a5531704c8625234821e2
  check_file "$V/geodata/country.mmdb" b13f10cdb414b8db78a64c432d6cd511668415760ee0fb2d17ac9f42de5aba08
  check_file "$V/geodata/GeoLite2-ASN.mmdb" e16e2db7ed72adc4443e16d7e33a25120ca58bd8d0f2e902b49ac6c50c3f4815
  GEODATA_ORIGIN="MetaCubeX/meta-rules-dat 2026-10-05 的发布文件（release 分支 f7c0420），$TODAY 按提交号取回，SHA-256 与 2026-10-05 下载的相同"
else
  GEODATA_ORIGIN="MetaCubeX/meta-rules-dat $GOT_DATE 的发布文件（release 分支 ${GOT_COMMIT:0:7}），$TODAY 下载"
fi

say "== 5. sing-box 的规则集（SagerNet/sing-geosite、sing-geoip 的 rule-set 分支）=="
fetch_files sing-geosite https://github.com/SagerNet/sing-geosite be94d52ad035da5350a1e5f62515185725034d86 rule-set "$V/srs" \
  geosite-cn.srs 'geosite-geolocation-!cn.srs' geosite-category-ads-all.srs
SITE_PINNED="$GOT_PINNED"; SITE_COMMIT="$GOT_COMMIT"; SITE_DATE="$GOT_DATE"
fetch_files sing-geoip https://github.com/SagerNet/sing-geoip 7fe82a879ad2666526730c195b55a6d8d9147908 rule-set "$V/srs" \
  geoip-cn.srs
IP_PINNED="$GOT_PINNED"; IP_COMMIT="$GOT_COMMIT"; IP_DATE="$GOT_DATE"
if [ "$SITE_PINNED" = yes ]; then
  check_file "$V/srs/geosite-cn.srs" fc4cb8e6db7107783c93ed1c65f81708f07189bc8452667d6bbdf92401fd6a8c
  check_file "$V/srs/geosite-geolocation-!cn.srs" 30b1abf132e955f5770e1939132880fdd30120401907c06ee3b6606973e3d2d6
  check_file "$V/srs/geosite-category-ads-all.srs" a233c2e155fa8f984e8d3c48fd9c5ca9600e47889b91f6fe83e4ad5685ae5324
fi
if [ "$IP_PINNED" = yes ]; then
  check_file "$V/srs/geoip-cn.srs" ebee603fdf402314b44b9f653cdcf6d9cc9c41e84e2b3515e3123c5c920a93bc
fi
SRS_ORIGIN="SagerNet/sing-geosite rule-set 分支 ${SITE_COMMIT:0:7}（$SITE_DATE）、sing-geoip rule-set 分支 ${IP_COMMIT:0:7}（$IP_DATE），$TODAY 检出"

say "== 6. 写出 $V/env.sh =="
cat > "$V/env.sh" <<EOF
# 由 handoff/setup_env.sh 于 $TODAY 生成。用法：source 这个文件，然后在仓库根目录运行 bash tools/run_checks.sh
export MIHOMO_BIN="$V/bin/mihomo-linux-amd64-v1.19.31"
export SINGBOX_BIN="$V/bin/sing-box-1.14.1-linux-amd64/sing-box"
export SINGBOX112_BIN="$V/bin/sing-box-1.12.0-linux-amd64/sing-box"
export GEODATA_DIR="$V/geodata"
export SRS_DIR="$V/srs"
export BM7_SRC="$V/src/bm7"
export DLC_SRC="$V/src/domain-list-community"
export MIHOMO_SRC="$V/src/mihomo"
export SINGBOX_SRC="$V/src/sing-box"
export ICON_REPO="$V/src/icon"
export GEODATA_ORIGIN="$GEODATA_ORIGIN"
export SRS_ORIGIN="$SRS_ORIGIN"
export BM7_ORIGIN="blackmatrix7/ios_rule_script 固定快照 51d2e1d（2026-09-21）"
EOF
{
  echo "# $TODAY 取到的文件（handoff/setup_env.sh 生成）"
  (cd "$V" && sha256sum bin/mihomo-linux-amd64-v1.19.31 bin/sing-box-1.14.1-linux-amd64/sing-box bin/sing-box-1.12.0-linux-amd64/sing-box geodata/* srs/*)
  for d in domain-list-community bm7 mihomo sing-box icon; do echo "$(git -C "$V/src/$d" rev-parse HEAD)  src/$d"; done
} > "$V/SOURCES.txt"

say ""
if [ "${#DRIFT[@]}" -gt 0 ]; then
  say "注意：下面这些没能按登记的提交取到，用的是今天最新的。数据和 r12 记录的不同："
  printf '  - %s\n' "${DRIFT[@]}"
  say "这种情况下 tools/check_real_routes.py 的数字会和 r12 文档里的不一样，属于正常；做法见 handoff/README.md 第 3 节。"
else
  say "全部按登记的版本取到，校验值都对：和 r12 的检查用的是同一套程序和数据。"
fi
say "下一步（在仓库根目录）：source \"$V/env.sh\" && bash tools/run_checks.sh"
