#!/usr/bin/env python3
"""一次性核对（2026-10-15，r18；不参与生成和测试，结果记在 docs/08 第 13 轮）。

GPT 审核 r17 的 R17-F01：DNS 替身的 close_stubs 不等接收线程处理完就看 unparsed，可能先返回成功、随后才记下读不懂的查询。
审核报告附了一段“紧接着关闭”的最小脚本：起一个替身，发一个截断的查询，立刻 close_stubs，100 次里数
“关闭时就报错”和“关闭返回以后才记下”各几次。这里把那段脚本原样放在 PROBE 里（只把导入路径改成参数），
在这一版的代码上跑一遍；命令行再给几个目录（比如 git archive 取出来的 r17），也在那些代码上各跑一遍，对照着看。

次数随线程调度变化（审核方那边 r17 是 99 次关闭以后才记下），不是全套检查的漏报率——实际核对会先停内核、有等待。
确定性的回归测试在 tests/test_real_data.py（Socks5RecorderTool 里 2026-10-15 加的几项，用 Event 定先后）。

用法（仓库根目录）：python3 handoff/notes/r18_close_race_probe.py [别的代码根目录 …] > handoff/notes/r18_close_race_probe.out
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PROBE = r'''
import socket, sys
sys.path.insert(0, sys.argv[1])
import check_real_routes as c

packet = bytes.fromhex("1234010000010000000000000573686f7274")
late = 0
reported_n = 0
with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
    for _ in range(100):
        st = c.DnsStub("probe", {})
        st.start()
        u.sendto(packet, ("127.0.0.1", st.port))
        reported = False
        try:
            c.close_stubs([st])
        except RuntimeError:
            reported = True
        reported_n += reported
        st.join(0.015)
        late += not reported and packet.hex() in st.unparsed
        if st.is_alive():  # 仅为本探针清理仍阻塞的线程
            u.sendto(b"", ("127.0.0.1", st.port))
            st.join(0.2)
print(f"关闭时就报错 {reported_n} 次；关闭返回以后才记下 {late} 次；两样都没有 {100 - reported_n - late} 次")
'''


def describe(tree: str) -> str:
    r = subprocess.run(["git", "-C", tree, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    if r.returncode == 0 and os.path.realpath(tree) == ROOT:
        dirty = subprocess.run(["git", "-C", tree, "status", "--porcelain", "--", "tools"], capture_output=True, text=True).stdout
        return f"这一版的工作区（HEAD {r.stdout.strip()}{'，tools/ 有未提交的改动' if dirty.strip() else ''}）"
    return f"{tree}（不是这个仓库的工作区，例如 git archive 取出来的旧版）"


def main(argv) -> int:
    trees = [ROOT] + [os.path.abspath(x) for x in argv]
    for tree in trees:
        tools = os.path.join(tree, "tools")
        if not os.path.exists(os.path.join(tools, "check_real_routes.py")):
            print(f"{tree}：没有 tools/check_real_routes.py，跳过")
            continue
        started = time.time()
        r = subprocess.run([sys.executable, "-c", PROBE, tools], cwd=tree, capture_output=True, text=True, timeout=600)
        print(describe(tree))
        print("  " + (r.stdout.strip() or "没有输出") + f"（用时 {time.time() - started:.1f} 秒）")
        if r.returncode:
            print("  出错：" + r.stderr.strip()[-400:])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
