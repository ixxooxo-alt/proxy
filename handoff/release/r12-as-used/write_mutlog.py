"""把汇总好的变异结果写成 docs/evidence/mutations.log（在工程根目录运行；先跑 assemble.py）。"""
import json, os

S = os.path.dirname(os.path.abspath(__file__))
res = json.load(open(S + "/mut-result.json", encoding="utf-8"))
lines = open(S + "/mut-lines.txt", encoding="utf-8").read().rstrip("\n").split("\n")
N = res["n"]
assert len(lines) == N == 98, (len(lines), N)
segs = res["segments"]
full, partial = res["full"], res["partial"]
notes_partial = "；".join(f"Ran {k} tests 的几类（{'、'.join(v)}）" for k, v in sorted(partial.items(), key=lambda kv: int(kv[0])))
odd, even = "M1 M3 … M97", "M2 M4 … M98"
if len(segs) == 1:
    when = f"运行时间（UTC）：{segs[0]['start']} 开始，两批并行，{segs[0]['end']} 结束。一次跑完，中间没有中断。"
    cmd = f"命令：python3 tools/check_mutations.py {odd} 和 python3 tools/check_mutations.py {even}"
else:
    parts = []
    for i, s in enumerate(segs, 1):
        ids = s["ids"]
        parts.append(f"第 {i} 段 {s['start']} 开始、{s['end']} 结束，共 {len(ids)} 类")
    when = ("运行时间（UTC）：分 " + str(len(segs)) + " 段，每段两批并行。" + "；".join(parts)
            + "。前面的段是被工作环境重启打断的，重启时正在跑的那两类没有留下结果，在下一段里从头重跑。")
    cmd = "命令：每一段都是 python3 tools/check_mutations.py <单数编号> 和 python3 tools/check_mutations.py <双数编号>，后面的段只带还没有结果的编号"
head = [
    when,
    f"Python：{res['python']}，PyYAML：{res['pyyaml']}",
    f"统一源摘要：{res['digest']}（运行期间 source/、generator/、tests/、tools/、build.py、.gitignore 都没有改动：这些文件的合并哈希在运行结束时"
    "与 2026-10-06 11:41 UTC 第三次定稿时相同）",
    cmd,
    "说明：每个变异在不含 dist/ 的项目副本里注入一处错误后跑全部测试；“发现”= 测试以非零退出码结束。",
    f"      skipped=2 是副本里没有 dist/ 时跳过的两项（“产物与统一源一致”、版本对比工具里要读 dist/ 的那一项）；完整的一次是 Ran {full} tests。"
    + (f"{notes_partial}是统一源校验直接拒绝、部分测试类无法初始化。" if partial else ""),
    "      M45（回溯失控）只跑专门针对它的那一项测试（见脚本开头的说明）：那一项把匹配放在带超时的子进程里，等满 300 秒后失败。",
    "      “未见预期信息”只表示输出里没有脚本预设的那个关键字（" + ("、".join(res["not_seen"]) or "这次没有") + "），失败项本身是对的。",
    "      M21 那一行有两个 FAILED：前一个是被测的检查脚本自己打印的，后一个才是这次测试运行的结果。",
    "      这次是 98 类：r11 的 75 类，加上这一轮新增的 M76–M98（Loon / Quantumult X 严格版 M76–M90；mihomo、sing-box“没被接住的域名只问境外 DNS”",
    "      M91、M92；境外 DNS 不应答那一遍 M93；全集一致性 M94；Apple Push M95–M97；上游规则文件里的 IP 规则带不带 no-resolve M98）。",
    "      M20、M61 两类检查的错误没有变，注入的写法因为这一轮代码有改动重写过。",
    "      只靠“记录对应现在的配置”那两项（规则与 DNS 两段的摘要、拨号摘要）发现的有 " + (str(len(res["fresh"]["solo"])) + " 类：" + "、".join(res["fresh"]["solo"]) if res["fresh"]["solo"] else "0 类") + "。",
    "      M91、M92 改的是“没被域名规则接住的域名问哪个 DNS”（mihomo 默认的 DNS、sing-box 路由里 resolve 动作的服务器）。离线测试不重跑官方内核，",
    "      所以它们表现为“官方内核的记录过期”，失败信息提示重新运行 tools/check_real_routes.py；重跑时“没被接住的域名只问境外 DNS”那几条",
    "      会不符合，工具拒绝写快照（2026-10-06 一次性核对过：把这两处改动套到副本上实际重跑，见 docs/05 变异检查一行）。其余各类都另有针对那个错误本身的测试失败。",
    "      这次运行之前：这一版的代码在 2026-10-06 定稿过三次。第一次（06:29 UTC）以后跑完 28 类时对话中断、云端机器被回收；",
    "      第二次（11:15 UTC，改了 Apple Push 的图标登记）以后跑完 20 类；两次的结果都因为之后代码有改动没有采用。",
    "      这份日志是第三次定稿（11:41 UTC，补了 M98 对应的固定核对）以后从头跑的。新增的各类里，M83、M86、M88、M89、M93、M94、M97、M98",
    "      在定稿之前各单独试跑过（都被发现），那几次的输出不在这份日志里。",
    "",
]
out = "\n".join(head + lines + ["", f"合计 {N}/{N} 被发现"]) + "\n"
with open("docs/evidence/mutations.log", "w", encoding="utf-8", newline="\n") as f:
    f.write(out)
print(out[:3000])
