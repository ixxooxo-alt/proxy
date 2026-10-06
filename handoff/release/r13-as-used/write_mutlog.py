"""把汇总好的变异结果写成 docs/evidence/mutations.log（r13 用的；照 r12-as-used/write_mutlog.py 改的）。
用法（在工程根目录，先跑 assemble.py）：python3 handoff/release/r13-as-used/write_mutlog.py <日志目录> <定稿时间，如 "2026-10-06 17:40">"""
import json, os, sys

D = os.path.abspath(sys.argv[1])
FROZEN = sys.argv[2]
res = json.load(open(os.path.join(D, "mut-result.json"), encoding="utf-8"))
lines = open(os.path.join(D, "mut-lines.txt"), encoding="utf-8").read().rstrip("\n").split("\n")
N = res["n"]
assert len(lines) == N == 100, (len(lines), N)
segs = res["segments"]
full, partial = res["full"], res["partial"]
notes_partial = "；".join(f"Ran {k} tests 的几类（{'、'.join(v)}）" for k, v in sorted(partial.items(), key=lambda kv: int(kv[0])))
odd, even = "M1 M3 … M99", "M2 M4 … M100"
if len(segs) == 1:
    when = f"运行时间（UTC）：{segs[0]['start']} 开始，两批并行，{segs[0]['end']} 结束。一次跑完，中间没有中断。"
    cmd = f"命令：python3 tools/check_mutations.py {odd} 和 python3 tools/check_mutations.py {even}（handoff/release/run_mutations.sh）"
else:
    parts = []
    for i, s in enumerate(segs, 1):
        parts.append(f"第 {i} 段 {s['start']} 开始、{s['end']} 结束，共 {len(s['ids'])} 类")
    when = ("运行时间（UTC）：分 " + str(len(segs)) + " 段，每段两批并行。" + "；".join(parts)
            + "。前面的段是被工作环境重启打断的，重启时正在跑的那两类没有留下结果，在下一段里从头重跑。")
    cmd = "命令：每一段都是 python3 tools/check_mutations.py <单数编号> 和 python3 tools/check_mutations.py <双数编号>，后面的段只带还没有结果的编号"
solo = res["fresh"]["solo"]
head = [
    when,
    f"Python：{res['python']}，PyYAML：{res['pyyaml']}",
    f"统一源摘要：{res['digest']}（与 r12 相同：这一版没有改 source/、generator/、build.py）。"
    f"代码状态哈希 {res['state']}：运行开始和结束时相同，与 {FROZEN} UTC 定稿时记下的相同"
    "（source/、generator/、tests/、tools/、build.py、.gitignore 的合并哈希，handoff/release/code_state.sh）",
    cmd,
    "说明：每个变异在不含 dist/ 的项目副本里注入一处错误后跑全部测试；“发现”= 测试以非零退出码结束。",
    f"      skipped=2 是副本里没有 dist/ 时跳过的两项（“产物与统一源一致”、版本对比工具里要读 dist/ 的那一项）；完整的一次是 Ran {full} tests。"
    + (f"{notes_partial}是统一源校验直接拒绝、部分测试类无法初始化。" if partial else ""),
    "      M45（回溯失控）只跑专门针对它的那一项测试（见脚本开头的说明）：那一项把匹配放在带超时的子进程里，等满 300 秒后失败。",
    "      “未见预期信息”只表示输出里没有脚本预设的那个关键字（" + ("、".join(res["not_seen"]) or "这次没有") + "），失败项本身是对的。",
    "      M21 那一行有两个 FAILED：前一个是被测的检查脚本自己打印的，后一个才是这次测试运行的结果。",
    "      这次是 100 类：r12 的 98 类，加上这一轮新增的 M99（sing-box 的境外 DNS 不再经“国外默认”发出）、M100（核对工具又只读 A 记录、",
    "      按“没有 A 记录”判空应答）。M94 只改了名字里的“全集一致性”→“逐条扫描”，注入的错误没有变；M3、M8、M12、M27 和 drop_loon_domain_list",
    "      把 re.sub 的 count 改成关键字写法（Python 3.13 对位置参数报弃用警告），注入的错误没有变。",
    "      只靠“记录对应现在的配置”那两项（规则与 DNS 两段的摘要、拨号摘要）发现的有 " + (str(len(solo)) + " 类：" + "、".join(solo) if solo else "0 类") + "。",
    "      r12 时有 2 类（M91、M92）只靠这两项发现；这一轮补了静态断言（tests/test_dns_lan.py 的 test_mihomo_unmatched_names_ask_only_the_foreign_doh、",
    "      test_singbox_unmatched_names_ask_only_dns_foreign），它们现在由这两项直接发现，M99 也是。",
    f"      运行环境和 r12 不同：这一轮是新的云端会话，Python 3.13.16（r12 是 3.11.17），官方程序和上游数据按 handoff/setup_env.sh 登记的版本和校验值重新取回。",
    f"      代码只定稿过一次（{FROZEN} UTC）。定稿之前，M91、M92、M99、M100 在接近定稿的代码上各单独试跑过（都被发现；M100 当时“未见预期信息”，",
    "      之后给那两处断言加了说明文字），那几次的输出不在这份日志里。",
    "",
]
out = "\n".join(head + lines + ["", f"合计 {N}/{N} 被发现"]) + "\n"
with open("docs/evidence/mutations.log", "w", encoding="utf-8", newline="\n") as f:
    f.write(out)
print(out[:4000])
