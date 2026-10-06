#!/usr/bin/env bash
# 解包核对交付包：① 与工程逐文件相同；② 解出来的副本里 build.py --check 和全部测试通过；③ 凭据、私人信息、本机路径扫描。
#
# 用法：bash handoff/release/verify_package.sh <zip> [工作目录] [--without-handoff]
#   工作目录缺省 ~/proxy-work/unzip-check（在仓库以外；每次清空重来）
#   --without-handoff：包里不含 CLAUDE.md 和 handoff/ 时加上（和 pack.py 的同名选项配套）
# 另外：使用者本人的邮箱、账号编号这类字样不要写进仓库里的任何文件（仓库是公开的），所以这里只扫通用的写法。
# 你知道具体要防哪些字样时，用环境变量临时带进来再扫一遍，例如：
#   PRIVATE_PATTERN='某个邮箱前缀|某个账号编号' bash handoff/release/verify_package.sh <zip>
# 最后几项扫描“没有输出 = 没有命中”。有命中时逐条看：是真的泄露就改掉重打包，不要只改这个脚本让它不报。
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
Z="${1:?用法：verify_package.sh <zip> [工作目录] [--without-handoff]}"
Z="$(cd "$(dirname "$Z")" && pwd)/$(basename "$Z")"
W="$HOME/proxy-work/unzip-check"
SKIP_HANDOFF=no
shift
for arg in "$@"; do
  case "$arg" in
    --without-handoff) SKIP_HANDOFF=yes ;;
    *) W="$arg" ;;
  esac
done
W="$(realpath -m "$W")"
case "$W/" in "$REPO"/*) echo "工作目录不能在仓库里面：$W" >&2; exit 2 ;; esac
mkdir -p "$W" || exit 2
rm -rf "$W/proxy-rules"
cd "$W" || exit 2
python3 -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); print('zip 自检：', z.testzip()); z.extractall('.')" "$Z" || exit 2
echo "文件数：$(find proxy-rules -type f | wc -l)"
echo "== 不该在包里的东西（没有输出 = 没有）"
find proxy-rules -name '__pycache__' -o -name '*.pyc' -o -path '*/dist/private*' -o -name 'local.yaml' -o -name '.git' | head

echo "== 与工程对比（不比 .git、__pycache__、dist/private、source/local.yaml）"
EX=(-x .git -x __pycache__ -x private -x local.yaml)
[ "$SKIP_HANDOFF" = yes ] && EX+=(-x CLAUDE.md -x handoff)
if diff -rq proxy-rules "$REPO" "${EX[@]}"; then echo "逐文件相同"; else echo "!!! 包和工程不一样（上面列出的）"; fi

cd "$W/proxy-rules" || exit 2
echo "== build.py --check"; python3 build.py --check | tail -1
echo "== 测试"; python3 -m unittest discover -s tests 2>&1 | tail -3

echo "== 凭据与私人信息扫描（包内全部文件）"
cd "$W" || exit 2
# 这两个文件里的匹配写法、断言文字本身就含有被扫的字样，不扫它们自己
SELF=(--exclude=verify_package.sh --exclude=finalize.py)
grep -rIl -E 'REPLACE-ME\.invalid' proxy-rules | wc -l | xargs echo "含占位订阅的文件数（只应是样例和说明）："
grep -rIn "${SELF[@]}" -E '(ss|ssr|vmess|vless|trojan|hysteria2?|tuic)://[A-Za-z0-9+/=_-]{12,}' proxy-rules | grep -v 'tests/' | head -5
grep -rIn "${SELF[@]}" -E '(token|secret|passwd|password)[=:][ ]*[A-Za-z0-9+/_-]{12,}' proxy-rules --include='*.conf' --include='*.yaml' --include='*.json' --include='*.md' | grep -v -E 'tests/|SECRET123' | head -5
grep -rIn "${SELF[@]}" -E 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|BEGIN CERTIFICATE' proxy-rules | head -5
grep -rIn "${SELF[@]}" -E 'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}' proxy-rules | head -5
grep -rIn "${SELF[@]}" -E '[A-Za-z0-9._%+-]+@(gmail|outlook|hotmail|qq|163|126|icloud|proton|protonmail|foxmail|yahoo)\.[a-z.]+' proxy-rules | head -5
grep -rIn "${SELF[@]}" -i -E 'users\.noreply\.github\.com|session_01[A-Za-z0-9]{6,}|claude\.ai/(code/session_|chat/)' proxy-rules | head -5
grep -rIn "${SELF[@]}" -E '/root/\.claude|/tmp/claude|scratchpad|replay-git|/mnt/user-data' proxy-rules | head -10
if [ -n "${PRIVATE_PATTERN:-}" ]; then
  echo "-- 另外按 PRIVATE_PATTERN 扫（字样本身不显示）"
  grep -rIl -i -E "$PRIVATE_PATTERN" proxy-rules | head -10
fi
echo "（上面几项没有输出 = 没有命中）"
echo "== 日志里出现的本机目录（只应是放官方程序和上游数据的那个目录）"
grep -rIhoE '(/home/[A-Za-z0-9._-]+|/root|/opt|/workspace|/tmp)/[A-Za-z0-9._/-]+' proxy-rules/docs/evidence 2>/dev/null \
  | sed -E 's#^((/home/[^/]+|/root|/opt|/workspace|/tmp)/[^/]+).*#\1#' | sort | uniq -c
