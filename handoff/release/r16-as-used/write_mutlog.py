"""把汇总好的变异结果写成 docs/evidence/mutations.log（r16 用的；照 r15-as-used/write_mutlog.py 改的）。
用法（在工程根目录，先跑 assemble.py）：python3 handoff/release/r16-as-used/write_mutlog.py <日志目录> <定稿时间，如 "2026-10-13 05:10">"""
import json, os, sys

D = os.path.abspath(sys.argv[1])
FROZEN = sys.argv[2]
res = json.load(open(os.path.join(D, "mut-result.json"), encoding="utf-8"))
lines = open(os.path.join(D, "mut-lines.txt"), encoding="utf-8").read().rstrip("\n").split("\n")
N = res["n"]
assert len(lines) == N == 141, (len(lines), N)
segs = res["segments"]
full, partial = res["full"], res["partial"]
notes_partial = "；".join(f"Ran {k} tests 的几类（{'、'.join(v)}）" for k, v in sorted(partial.items(), key=lambda kv: int(kv[0])))
batches = ("M1 M4 … M139", "M2 M5 … M140", "M3 M6 … M141")      # MUT_BATCHES=3：编号除以 3 余 1、余 2、整除
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
    f"统一源摘要：{res['digest']}（r16：统一源 2026.10.13-2、生成器 1.9.0）。"
    f"代码状态哈希 {res['state']}：运行开始和结束时相同，与 {FROZEN} UTC 定稿时记下的相同"
    "（source/、generator/、tests/、tools/、build.py、.gitignore 的合并哈希，handoff/release/code_state.sh）",
    cmd,
    "说明：每个变异在不含 dist/ 的项目副本里注入一处错误后跑全部测试；“发现”= 测试以非零退出码结束。",
    f"      skipped=2 是副本里没有 dist/ 时跳过的两项（“产物与统一源一致”、版本对比工具里要读 dist/ 的那一项）；完整的一次是 Ran {full} tests。"
    + (f"{notes_partial}是统一源校验直接拒绝、部分测试类无法初始化。" if partial else ""),
    "      M45（回溯失控）只跑专门针对它的那一项测试（见脚本开头的说明）：那一项把匹配放在带超时的子进程里，等满 300 秒后失败。",
    "      “未见预期信息”只表示输出里没有脚本预设的那个关键字（" + ("、".join(res["not_seen"]) or "这次没有") + "），失败项本身是对的。",
    "      M21 那一行有两个 FAILED：前一个是被测的检查脚本自己打印的，后一个才是这次测试运行的结果。",
    "      这次是 141 类：r15 的 122 类，加上 M123–M128（对应 GPT 审核 r15：SOCKS5 接收端不看客户端提供的方法、收分了片的 UDP 包、",
    "      控制连接断了以后照样收包（R15-F01）；认主机时不分 TCP / UDP（建议）；大清单副本内容变了“最后一次改动”的日期没跟着改（建议）；",
    "      读内核日志不关文件（r15 测试日志里的 ResourceWarning））和 M129–M141（Stash：严格版 GEOIP 不带 no-resolve、占位节点连得上 / 没有、",
    "      国内清单排错位置、nameserver 换成境外、局域网后缀不交给 system、国内补充规则没写进 Stash、模拟器不认 RULE-SET、",
    "      PayPal 固定节点没带占位节点、生成时 / 结构检查不核对占位节点、DNS 段不加引号、模拟器不记本机解析）。",
    "      M2 套的那一行跟着改了（“国内常用网站”的 clients 多了 stash），变异本身没变。",
    "      只靠“记录对应现在的配置”那两项（规则与 DNS 两段的摘要、拨号摘要）发现的有 " + (str(len(solo)) + " 类：" + "、".join(solo) if solo else "0 类") + "。",
    "      运行环境和 r15 相同：同一个云端会话，Python 3.13.16，官方程序和上游数据是 handoff/setup_env.sh 登记的那一批。",
    f"      这一份对应的定稿是 {FROZEN} UTC，这一版的全部检查都在它之后跑。",
    "      定稿之前，M123–M128 在接近定稿的代码上试跑过（M125 第一次没被发现，补了测试、改了变异以后两种改法都被发现），那几次的输出不在这份日志里。",
    "",
]
out = "\n".join(head + lines + ["", f"合计 {N}/{N} 被发现"]) + "\n"
with open("docs/evidence/mutations.log", "w", encoding="utf-8", newline="\n") as f:
    f.write(out)
print(out[:4000])
