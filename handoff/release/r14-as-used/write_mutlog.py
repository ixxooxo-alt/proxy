"""把汇总好的变异结果写成 docs/evidence/mutations.log（r14 用的；照 r13-as-used/write_mutlog.py 改的）。
用法（在工程根目录，先跑 assemble.py）：python3 handoff/release/r14-as-used/write_mutlog.py <日志目录> <定稿时间，如 "2026-10-07 06:50">"""
import json, os, sys

D = os.path.abspath(sys.argv[1])
FROZEN = sys.argv[2]
res = json.load(open(os.path.join(D, "mut-result.json"), encoding="utf-8"))
lines = open(os.path.join(D, "mut-lines.txt"), encoding="utf-8").read().rstrip("\n").split("\n")
N = res["n"]
assert len(lines) == N == 117, (len(lines), N)
segs = res["segments"]
full, partial = res["full"], res["partial"]
notes_partial = "；".join(f"Ran {k} tests 的几类（{'、'.join(v)}）" for k, v in sorted(partial.items(), key=lambda kv: int(kv[0])))
batches = ("M1 M4 … M115", "M2 M5 … M116", "M3 M6 … M117")      # MUT_BATCHES=3：编号除以 3 余 1、余 2、整除
if len(segs) == 1:
    when = f"运行时间（UTC）：{segs[0]['start']} 开始，三批并行，{segs[0]['end']} 结束。一次跑完，中间没有中断。"
    cmd = ("命令：MUT_BATCHES=3 bash handoff/release/run_mutations.sh，即 python3 tools/check_mutations.py " + "、".join(batches)
           + " 三条同时在后台运行")
else:
    parts = []
    for i, s in enumerate(segs, 1):
        parts.append(f"第 {i} 段 {s['start']} 开始、{s['end']} 结束，共 {len(s['ids'])} 类")
    when = ("运行时间（UTC）：分 " + str(len(segs)) + " 段，每段三批并行。" + "；".join(parts)
            + "。前面的段是被工作环境重启打断的，重启时正在跑的那几类没有留下结果，在下一段里从头重跑。")
    cmd = "命令：每一段都是 MUT_BATCHES=3 bash handoff/release/run_mutations.sh（三批同时跑），后面的段只带还没有结果的编号"
solo = res["fresh"]["solo"]
head = [
    when,
    f"Python：{res['python']}，PyYAML：{res['pyyaml']}",
    f"统一源摘要：{res['digest']}（r14：统一源 2026.10.07-2、生成器 1.7.0）。"
    f"代码状态哈希 {res['state']}：运行开始和结束时相同，与 {FROZEN} UTC 定稿时记下的相同"
    "（source/、generator/、tests/、tools/、build.py、.gitignore 的合并哈希，handoff/release/code_state.sh）",
    cmd,
    "说明：每个变异在不含 dist/ 的项目副本里注入一处错误后跑全部测试；“发现”= 测试以非零退出码结束。",
    f"      skipped=2 是副本里没有 dist/ 时跳过的两项（“产物与统一源一致”、版本对比工具里要读 dist/ 的那一项）；完整的一次是 Ran {full} tests。"
    + (f"{notes_partial}是统一源校验直接拒绝、部分测试类无法初始化。" if partial else ""),
    "      M45（回溯失控）只跑专门针对它的那一项测试（见脚本开头的说明）：那一项把匹配放在带超时的子进程里，等满 300 秒后失败。",
    "      “未见预期信息”只表示输出里没有脚本预设的那个关键字（" + ("、".join(res["not_seen"]) or "这次没有") + "），失败项本身是对的。",
    "      M21 那一行有两个 FAILED：前一个是被测的检查脚本自己打印的，后一个才是这次测试运行的结果。",
    "      这次是 117 类：r13 的 100 类，加上 M101–M104（对应 GPT 审核 r13：核对工具又只在名字的第一个字节看压缩指针；mihomo 的",
    "      nameserver-policy 又没有走代理组的产品域名那一层；那一层把默认直连的组也交给境外 DNS；核对工具查 nameserver-policy 时按",
    "      “第一条命中”而不是 mihomo 的域名树）、M105–M115（对应使用者 2026-10-07 定下的待决事项：要真实地址的名单在 sing-box、mihomo",
    "      上不固定直连或 DNS 没写明交给国内；不带点的名字、private 集合又交给国内的公共 DNS；Quantumult X 严格版没有订阅大清单的副本、",
    "      副本的数据文件被手改；友盟的直连规则、上游标了 @ads 的子域；Bilibili 港澳台的默认出口；Apple AI 又收了 ls.apple.com）、",
    "      M116、M117（出版本时核对生成的文件查出的两处缺陷：版本对比报告里只换了先后的条目又不写改了什么；docs/04 里大清单副本那一行",
    "      又按自有清单的数据算条数）。M11、M84、M85、M91、M94、M102 的改法跟着新代码换了写法或改了说明",
    "      （注入的错误没有变）。",
    "      只靠“记录对应现在的配置”那两项（规则与 DNS 两段的摘要、拨号摘要）发现的有 " + (str(len(solo)) + " 类：" + "、".join(solo) if solo else "0 类") + "。",
    f"      运行环境和 r13 相同：同一个云端会话，Python 3.13.16，官方程序和上游数据是 handoff/setup_env.sh 登记的那一批。",
    f"      这一份对应的定稿是 {FROZEN} UTC，这一版的全部检查都在它之后跑。之前还定稿过两次，结果都没有用：02:05 那次是只做了审核那一半的",
    "      生成器 1.6.0，变异检查跑到一半被使用者叫停（他要先把待决事项一次定完，那一版没有交付）；06:20 那次是 1.7.0，变异检查开始",
    "      一两分钟后我在版本对比报告里发现 M116 那一处缺陷，停下、改了 tools/compare_versions.py 和测试，再定稿。",
    "      定稿之前，M105–M116 和改过写法的 M11、M84、M85、M94、M102 在接近定稿的代码上各单独试跑过（都被发现，都见到预期信息），",
    "      那几次的输出不在这份日志里。",
    "",
]
out = "\n".join(head + lines + ["", f"合计 {N}/{N} 被发现"]) + "\n"
with open("docs/evidence/mutations.log", "w", encoding="utf-8", newline="\n") as f:
    f.write(out)
print(out[:4000])
