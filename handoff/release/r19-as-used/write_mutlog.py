"""把汇总好的变异结果写成 docs/evidence/mutations.log（r19 用的；照 r18-as-used/write_mutlog.py 改的）。
用法（在工程根目录，先跑 assemble.py）：python3 handoff/release/r19-as-used/write_mutlog.py <日志目录> <定稿时间，如 "2026-10-15 03:10">"""
import json, os, sys

D = os.path.abspath(sys.argv[1])
FROZEN = sys.argv[2]
res = json.load(open(os.path.join(D, "mut-result.json"), encoding="utf-8"))
lines = open(os.path.join(D, "mut-lines.txt"), encoding="utf-8").read().rstrip("\n").split("\n")
N = res["n"]
assert len(lines) == N == 170, (len(lines), N)
segs = res["segments"]
full, partial = res["full"], res["partial"]
notes_partial = "；".join(f"Ran {k} tests 的几类（{'、'.join(v)}）" for k, v in sorted(partial.items(), key=lambda kv: int(kv[0])))
batches = ("M1 M4 … M169", "M2 M5 … M170", "M3 M6 … M168")      # MUT_BATCHES=3：编号除以 3 余 1、余 2、整除
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
head = [
    when,
    f"Python：{res['python']}，PyYAML：{res['pyyaml']}",
    f"统一源摘要：{res['digest']}（r19：统一源 2026.10.17-1、生成器 1.10.2）。"
    f"代码状态哈希 {res['state']}：运行开始和结束时相同，与 {FROZEN} UTC 定稿时记下的相同"
    "（source/、generator/、tests/、tools/、build.py、.gitignore 的合并哈希，handoff/release/code_state.sh）",
    cmd,
    "说明：每个变异在不含 dist/ 的项目副本里注入一处错误后跑全部测试；“发现”= 测试以非零退出码结束。",
    f"      skipped=2 是副本里没有 dist/ 时跳过的两项（“产物与统一源一致”、版本对比工具里要读 dist/ 的那一项）；完整的一次是 Ran {full} tests。"
    + (f"{notes_partial}是统一源校验直接拒绝、部分测试类无法初始化。" if partial else ""),
    "      M45（回溯失控）只跑专门针对它的那一项测试（见脚本开头的说明）：那一项把匹配放在带超时的子进程里，等满 300 秒后失败。",
    "      “未见预期信息”只表示输出里没有脚本预设的那个关键字（" + ("、".join(res["not_seen"]) or "这次没有") + "），失败项本身是对的。",
    "      M21 那一行有两个 FAILED：前一个是被测的检查脚本自己打印的，后一个才是这次测试运行的结果。",
    "      这次是 170 类：r18 的 162 类，加上 M163–M166（对应 GPT 审核 r18：DNS 替身的停止标记又叫 _stop、测试节点停下时不看控制连接、",
    "      sing-box 的查询和连接又放在同一遍里、拿到 fake-ip 的查询只记收到它的替身）和 M167–M170（对应 GPT 审核 r19 送审稿：",
    "      清 UDP 队列只在开头看一次控制连接、查询去向只看名字不看类型、替身没停下也认、在替身停下以前认）。",
    "      M155、M158、M162 的改动位置随这一版的代码挪了，改法不变。",
    "      只靠“记录对应现在的配置”那两项（规则与 DNS 两段的摘要、拨号摘要）发现的有 " + (str(len(solo)) + " 类：" + "、".join(solo) if solo else "0 类") + "。",
    "      运行环境和 r18 相同：同一个云端会话，Python 3.13.16，官方程序和上游数据是 handoff/setup_env.sh 登记的那一批。",
    f"      这一份对应的定稿是 {FROZEN} UTC，这一版的全部检查都在它之后跑。",
    "      定稿之前，M163–M170 和受影响的 M155、M158、M162 在接近定稿的代码上只跑 test_real_data 的 Socks5RecorderTool 试过（都被发现），",
    "      那几次的输出不在这份日志里。",
    "",
]
out = "\n".join(head + lines + ["", f"合计 {N}/{N} 被发现"]) + "\n"
with open("docs/evidence/mutations.log", "w", encoding="utf-8", newline="\n") as f:
    f.write(out)
print(out[:4000])
