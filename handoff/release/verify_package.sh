#!/usr/bin/env bash
# 解包核对交付包：① 和提交逐个文件相同，没有私密产物、缓存、临时文件；② 解出来的副本里 build.py --check 和全部测试通过；
# ③ 凭据、私人信息、本机路径扫描没有命中。任何一项不通过，最后退出码 1；全部通过才是 0、最后一行是“核对通过”。
#
# 用法：bash handoff/release/verify_package.sh <zip> [工作目录] [--without-handoff] [--rev 提交] [--skip-tests]
#   工作目录缺省 ~/proxy-work/unzip-check（必须在仓库以外）。每次在它下面新建一个本轮专属的子目录（run-随机名），只解到这里
#   --without-handoff：包里不含 CLAUDE.md 和 handoff/ 时加上（和 pack.py 的同名选项配套）
#   --rev：包应当对应的提交，缺省 HEAD（pack.py 从提交打包，先提交再打包再核对）
#   --skip-tests：不跑全部测试，只给 selftest_package.sh 用（坏包不用等五分钟的测试也看得出来）；正式核对不要加，加了最后也不会说“核对通过”
#
# 2026-11-18 起（全项目复核 F06、F07）：
#   - 每一项都看真实的退出码。以前包和工程不一样只打印一句提示、build.py --check 和测试的退出码被 tail 遮住，坏包也返回 0；
#   - 包里有私密产物、local.yaml、缓存、临时文件，扫描有命中，都算不通过（以前只是列出来）；没跑出测试（0 项）也算不通过；
#   - 不删任何不是本轮自己建的目录。以前每次先删“工作目录/proxy-rules”，工作目录恰好是工程的上一级、工程又叫 proxy-rules 时，
#     删的就是工程本身。现在只在全部通过以后删本轮的子目录，删之前还要 package_check.py may-remove 确认它和仓库不相交；
#     没通过时留着给你看。
#
# 另外：使用者本人的邮箱、账号编号这类字样不要写进仓库里的任何文件（仓库是公开的），所以这里只扫通用的写法。
# 你知道具体要防哪些字样时，用环境变量临时带进来再扫一遍，例如：
#   PRIVATE_PATTERN='某个邮箱前缀|某个账号编号' bash handoff/release/verify_package.sh <zip>
# 扫描有命中时逐条看：是真的泄露就改掉重打包，不要只改这个脚本让它不报。
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd -P)"
HERE="$REPO/handoff/release"
USAGE="用法：verify_package.sh <zip> [工作目录] [--without-handoff] [--rev 提交] [--skip-tests]"
Z="${1:?$USAGE}"
[ -f "$Z" ] || { echo "没有这个文件：$Z" >&2; exit 2; }
Z="$(cd "$(dirname "$Z")" && pwd -P)/$(basename "$Z")"
W="$HOME/proxy-work/unzip-check"
SKIP_HANDOFF=no
SKIP_TESTS=no
REV=HEAD
shift
while [ $# -gt 0 ]; do
  case "$1" in
    --without-handoff) SKIP_HANDOFF=yes ;;
    --skip-tests) SKIP_TESTS=yes ;;
    --rev) REV="${2:?$USAGE}"; shift ;;
    --*) echo "不认识的选项：$1" >&2; exit 2 ;;
    *) W="$1" ;;
  esac
  shift
done
W="$(realpath -m "$W")"
case "$W/" in "$REPO"/*) echo "工作目录不能在仓库里面：$W" >&2; exit 2 ;; esac
mkdir -p "$W" || exit 2
RUN="$(mktemp -d "$W/run-XXXXXX")" || exit 2
echo "本轮目录：$RUN"
FAILED=()
fail() { FAILED+=("$1"); echo "!!! 不通过：$1"; }

echo "== 解包，和提交逐个文件比（$REV）"
HO=(); [ "$SKIP_HANDOFF" = yes ] && HO=(--without-handoff)
if ! python3 -I "$HERE/package_check.py" unpack "$Z" "$RUN/pkg" "$REPO" "$REV" "${HO[@]}"; then
  fail "包的内容（见上面）"
fi
P="$RUN/pkg/proxy-rules"
if [ ! -f "$P/build.py" ]; then
  fail "包里没有 build.py，下面的生成检查和测试没法跑"
else
  echo "== build.py --check"
  (cd "$P" && python3 -B build.py --check) > "$RUN/check.out" 2>&1
  rc=$?
  tail -3 "$RUN/check.out"
  [ $rc -eq 0 ] || fail "build.py --check（退出码 $rc）"
  if [ "$SKIP_TESTS" = yes ]; then
    echo "== 测试：按 --skip-tests 没有跑"
  else
    echo "== 测试（约五分钟）"
    (cd "$P" && python3 -B -m unittest discover -s tests) > "$RUN/tests.out" 2>&1
    rc=$?
    tail -3 "$RUN/tests.out"
    ran="$(grep -oE '^Ran [0-9]+ tests?' "$RUN/tests.out" | tail -1 | grep -oE '[0-9]+')"
    if [ $rc -ne 0 ]; then fail "测试（退出码 $rc）"
    elif [ -z "$ran" ] || [ "$ran" -eq 0 ]; then fail "测试：一项也没有跑"
    elif ! tail -1 "$RUN/tests.out" | grep -qE '^OK( \(.*\))?$'; then fail "测试：最后一行不是 OK"
    fi
  fi
fi

echo "== 凭据与私人信息扫描（包内全部文件；有输出 = 有命中 = 不通过）"
if [ -d "$RUN/pkg/proxy-rules" ]; then
cd "$RUN/pkg" || exit 2
# 这几个文件里的匹配写法、断言文字本身就含有被扫的字样，不扫它们自己
SELF=(--exclude=verify_package.sh --exclude=finalize.py --exclude=selftest_package.py)
scan() {   # scan <说明> <排除的正则（空 = 不排除）> <grep 的参数…>：grep 的输出去掉排除的行就是命中；没有命中时 grep 退出码 1 是正常的，2 是命令出错
  local label="$1" exclude="$2"; shift 2
  local raw rc out
  raw="$(grep "$@" 2>&1)"; rc=$?
  if [ $rc -ge 2 ]; then echo "$raw" | head -3; fail "扫描命令出错：$label"; return; fi
  out="$raw"
  [ -n "$exclude" ] && [ -n "$out" ] && out="$(printf '%s\n' "$out" | grep -v -E "$exclude")"
  if [ -n "$out" ]; then echo "$out" | head -10; fail "扫描有命中：$label"; fi
}
echo "含占位订阅的文件数（只应是样例和说明）：$(grep -rIl -E 'REPLACE-ME\.invalid' proxy-rules | wc -l)"
scan "代理链接" 'tests/' -rIn "${SELF[@]}" -E '(ss|ssr|vmess|vless|trojan|hysteria2?|tuic)://[A-Za-z0-9+/=_-]{12,}' proxy-rules
scan "令牌、密码" 'tests/|SECRET123' -rIn "${SELF[@]}" -E '(token|secret|passwd|password)[=:][ ]*[A-Za-z0-9+/_-]{12,}' proxy-rules \
  --include='*.conf' --include='*.yaml' --include='*.json' --include='*.md'
scan "私钥、证书" '' -rIn "${SELF[@]}" -E 'BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY|BEGIN CERTIFICATE' proxy-rules
scan "GitHub / API 令牌" '' -rIn "${SELF[@]}" -E 'gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9]{20,}' proxy-rules
scan "常见个人邮箱" '' -rIn "${SELF[@]}" -E '[A-Za-z0-9._%+-]+@(gmail|outlook|hotmail|qq|163|126|icloud|proton|protonmail|foxmail|yahoo)\.[a-z.]+' proxy-rules
scan "会话链接、noreply 邮箱" '' -rIn "${SELF[@]}" -i -E 'users\.noreply\.github\.com|session_01[A-Za-z0-9]{6,}|claude\.ai/(code/session_|chat/)' proxy-rules
# docs/00 里有两行提到另一个对话的模型所在机器上的 /mnt/user-data/outputs/（使用者 2026-10-12 截图里写的，不是本机目录，也不是私人信息）。
# docs/00 只追加、不改写，2026-10-13 逐行看过，只按这两行开头的文字放过；别处出现照样报出来
scan "本机工作路径" '^proxy-rules/docs/00-需求原文\.md:[0-9]+:(19:46 前后（附了一张手机截图：另一个对话里的模型说它把 Stash 的配置样例存到了它那边的 `/mnt/user-data/outputs/stash-config-example\.yaml`）：$|- \*\*共享目录\*\*：那个对话的“共享目录”在它自己的机器上，我这边同名的 `/mnt/user-data/outputs/` 是空的，读不到。)' \
  -rIn "${SELF[@]}" -E '/root/\.claude|/tmp/claude|scratchpad|replay-git|/mnt/user-data' proxy-rules
if [ -n "${PRIVATE_PATTERN:-}" ]; then
  echo "-- 另外按 PRIVATE_PATTERN 扫（字样本身不显示，只列文件）"
  scan "PRIVATE_PATTERN" '' -rIl -i -E "$PRIVATE_PATTERN" proxy-rules
fi
echo "== 日志里出现的本机目录（只供人工看：只应是放官方程序和上游数据的那个目录；这一项不判通过与否）"
grep -rIhoE '(/home/[A-Za-z0-9._-]+|/root|/opt|/workspace|/tmp)/[A-Za-z0-9._/-]+' proxy-rules/docs/evidence 2>/dev/null \
  | sed -E 's#^((/home/[^/]+|/root|/opt|/workspace|/tmp)/[^/]+).*#\1#' | sort | uniq -c
else
  fail "包没有解开，扫描没法做"
fi

echo
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "核对没有通过（${#FAILED[@]} 项）：$(IFS='；'; echo "${FAILED[*]}")"
  echo "解出来的文件留在 $RUN，看完自己删"
  exit 1
fi
cd "$W" || exit 2
if python3 -I "$HERE/package_check.py" may-remove "$REPO" "$RUN" > /dev/null; then rm -rf "$RUN"; else echo "本轮目录和仓库相交，没有删：$RUN"; fi
if [ "$SKIP_TESTS" = yes ]; then
  echo "除了没跑的测试，其余各项都通过（--skip-tests 只给自测用，不能当作核对通过）"
  exit 0
fi
echo "核对通过"
