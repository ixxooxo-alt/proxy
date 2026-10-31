"""把汇总好的变异结果写成 docs/evidence/mutations.log（r21 用的；照 r20-as-used/write_mutlog.py 改的）。
用法（在工程根目录，先跑 assemble.py）：python3 handoff/release/r21-as-used/write_mutlog.py <日志目录> <定稿时间，如 "2026-10-31 16:59">"""
import json, os, sys

D = os.path.abspath(sys.argv[1])
FROZEN = sys.argv[2]
res = json.load(open(os.path.join(D, "mut-result.json"), encoding="utf-8"))
lines = open(os.path.join(D, "mut-lines.txt"), encoding="utf-8").read().rstrip("\n").split("\n")
N = res["n"]
assert len(lines) == N == 210, (len(lines), N)
segs = res["segments"]
full, partial = res["full"], res["partial"]
# 没跑满的原因（r20 起两种）：统一源校验直接拒绝的几类，和 M16（sing-box 生成时发现出站标签重名直接报错）。
# r20 是按测试项数分的（316、343）；r21 的测试项数变了，改成按编号认原因，项数照日志写
REASON = {**{x: "src" for x in ("M6", "M9", "M31", "M89", "M90")}, "M16": "tag"}
WHY = {"src": "是统一源校验直接拒绝、部分测试类无法初始化",
       "tag": "是节点名和组名相同又不改名，sing-box 生成时发现出站标签重名直接报错，简易版带节点的那个测试类（SingboxWithNodes，2 项）无法初始化；"
              "失败的另几项见那一行"}
groups = {}
for k, v in partial.items():
    for name in v:
        assert name in REASON, (k, name)
        groups.setdefault((int(k), REASON[name]), []).append(name)
notes_partial = "；".join(f"Ran {k} tests 的{'几类' if len(v) > 1 else '一类'}（{'、'.join(sorted(v, key=lambda x: int(x[1:])))}）{WHY[why]}"
                         for (k, why), v in sorted(groups.items()))
batches = ("M1 M4 … M208", "M2 M5 … M209", "M3 M6 … M210")      # MUT_BATCHES=3：编号除以 3 余 1、余 2、整除
if len(segs) == 1:
    when = f"运行时间（UTC）：{segs[0]['start']} 开始，三批并行，{segs[0]['end']} 结束。一次跑完，中间没有中断。"
    cmd = ("命令：MUT_BATCHES=3 bash handoff/release/run_mutations.sh，即 python3 tools/check_mutations.py " + "、".join(batches)
           + " 三条同时在后台运行")
else:
    parts = []
    for i, s in enumerate(segs, 1):
        parts.append(f"第 {i} 段 {s['start']} 开始、{s['end']} 结束，共 {len(s['ids'])} 类")
    when = ("运行时间（UTC）：分 " + str(len(segs)) + " 段，每段三批并行。" + "；".join(parts)
            + "。前面的段是被工作环境重新启动打断的（机器重启，后台进程随之停止），那时正在跑的那几类没有留下结果，在下一段里从头重跑；"
            "下一段开始前重新核对过代码状态和运行环境（Python、PyYAML、ICU 的版本，官方程序和上游数据的 SHA-256、上游源码的提交号），都没有变。")
    cmd = "命令：每一段都是 MUT_BATCHES=3 bash handoff/release/run_mutations.sh（三批同时跑），后面的段只带还没有结果的编号"
solo = res["fresh"]["solo"]
not_seen = res["not_seen"]
# 跑完以后按日志写的（2026-10-31）：这一类在定稿以后的这一次运行里记“未见预期信息”，原因逐个看过
NOT_SEEN_WHY = {"M182": "M182（sing-box 的 idle_timeout 照旧 30 分钟）预设由 test_foreign_dns_group 发现，可这一版 sing-box 简易版“境外DNS”的间隔改成了 600 秒，"
                        "按规则 idle_timeout 本来就是 30 分钟，这个变异在现在的配置上不改变产物，只有直接查换算的 test_duration_parser 失败；"
                        "关键字在 tools/check_mutations.py 里，改它就要重新定稿，留到下一版改代码时再改"}
assert set(not_seen) <= set(NOT_SEEN_WHY), not_seen
head = [
    when,
    f"Python：{res['python']}，PyYAML：{res['pyyaml']}",
    f"统一源摘要：{res['digest']}（r21：统一源 2026.10.31-1、生成器 1.12.1、简易版 2026.10.31-2）。"
    f"代码状态哈希 {res['state']}：运行开始和结束时相同，与 {FROZEN} UTC 定稿时记下的相同"
    "（source/、generator/、tests/、tools/、build.py、.gitignore 的合并哈希，handoff/release/code_state.sh）",
    cmd,
    "说明：每个变异在不含 dist/ 的项目副本里注入一处错误后跑全部测试；“发现”= 测试以非零退出码结束。",
    f"      skipped=2 是副本里没有 dist/ 时跳过的两项（“产物与统一源一致”、版本对比工具里要读 dist/ 的那一项）；完整的一次是 Ran {full} tests。"
    + (f"{notes_partial}。" if partial else ""),
    "      M45（回溯失控）只跑专门针对它的那一项测试（见脚本开头的说明）：那一项把匹配放在带超时的子进程里，等满 300 秒后失败。",
    ("      “未见预期信息”只表示输出里没有脚本预设的那个关键字（" + "、".join(not_seen) + "），失败项本身是对的："
     + "；".join(NOT_SEEN_WHY[x] for x in not_seen) + "。") if not_seen else
    "      每一类的输出都含脚本预设的那个关键字（r20 记“未见预期信息”的 M3、M177，这一版把关键字改对了：M3 的那句说明 2026-10-07 起就不在了，"
    "M177 预设的测试那时也查不出它，这一版补了，见下）。",
    "      M21 那一行有两个 FAILED：前一个是被测的检查脚本自己打印的，后一个才是这次测试运行的结果。",
    "      这次是 210 类：r20 的 202 类，加上 M203–M209（2026-10-31，使用者定的测速间隔：Stash 完整版的选择组又不写 interval、写盘前检查不核对它、",
    "      自动类组也关掉定时测速、写盘前检查不核对自动类组、sing-box 简易版的“境外DNS”仍用 1 小时、写盘前检查不核对它、规则源不校验 Stash 组上的间隔）",
    "      和 M210（对应 GPT 审核 r21 送审稿的建议：规则源又接受 Stash 完整版选择组的正数间隔）；M201 跟着改写成“Stash 简易版的组不写 interval”",
    "      （r20 是“不关定时测速”，2026-10-31 起定的是每小时测一次）。M3、M177 只改了预设的关键字；M177 同时补了它预设的那项测试",
    "      （test_simple 的 SameAsFullOutsideGroups.test_mihomo 以前只查“别处没有不同”，少了 GEO 数据那条规则、少了 #境外DNS 也不报）。",
    "      只靠“记录对应现在的配置”那两项（规则与 DNS 两段的摘要、拨号摘要）发现的有 " + (str(len(solo)) + " 类：" + "、".join(solo) if solo else "0 类") + "。",
    "      运行环境和 r20 相同：同一个云端会话，Python 3.13.16，官方程序和上游数据是 handoff/setup_env.sh 登记的那一批。",
    f"      这一份对应的定稿是 {FROZEN} UTC，这一版的全部检查都在它之后跑。",
    "      定稿之前，M203–M209 在 r21 送审稿的代码上（2026-10-31 08:33 起），M3、M176、M177 在接近定稿的代码上，各跑过一遍全部测试（都被发现）；",
    "      M210 第一次试跑没被发现（预设的生成流程测试分不出是规则源还是写盘前检查拒绝的，docs/08 第 19 轮的补记），补了 test_select_interval_in_the_source_must_be_negative",
    "      以后再试跑一遍。那几次的输出不在这份日志里。",
    "",
]
out = "\n".join(head + lines + ["", f"合计 {N}/{N} 被发现"]) + "\n"
with open("docs/evidence/mutations.log", "w", encoding="utf-8", newline="\n") as f:
    f.write(out)
print(out[:4000])
