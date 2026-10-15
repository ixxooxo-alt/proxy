#!/usr/bin/env python3
"""一次性核对（2026-10-15，r18；不参与生成和测试，结果记在 docs/06 第 22 项、docs/08 第 13 轮）。

待决事项第 22 项（sing-box 1.14.1 隔着选择组 / 自动测速组转发 UDP、目标是域名时把包丢掉），你 2026-10-15 选了 ③：
取 1.14.3 的官方程序，用同一套最小核对和实际配置再跑一遍，再在 ① ② 里选。这里做两样，全部只在本机：
  1. 最小核对：handoff/notes/r15_review_probes.py 里的同一批最小配置（SOCKS 出口七种组合；Shadowsocks / Trojan / VMess
     连本机另一个同版本 sing-box 的入站，直接交给出口、隔一个选择组），换成 1.14.3 跑。
  2. 实际配置：这一版生成的 sing-box 1.14 版配置，按 tools/check_real_routes.py 的出站核对（singbox_outbound_probe：
     走代理的组换成测试出口——SOCKS 连本机的 SOCKS5 接收端，WireGuard 连本机一个没人监听的端口；三类 DNS 换成本机替身），
     三个场景（SOCKS 走 TCP、SOCKS 走 UDP、WireGuard 端点走 TCP）、两批主机（tests/cases.yaml 的 outbound_resolve、
     outbound_switched），1.14.1 和 1.14.3 各跑一遍，逐条对照“哪个 DNS 替身收到了查询”和“节点收到的目标”。
  3. 实际配置的全套核对：tools/check_real_routes.py 换成 1.14.3 当 1.14 版的内核跑一遍（不带 1.12、不写快照），完整输出存在
     handoff/notes/r18_singbox_1143_full.out，这里只列“不符合”的几行。人工期望（tests/cases.yaml）是按 1.14.1 的行为写的，
     所以“不符合”就是 1.14.3 和 1.14.1 不一样的地方。
内核只连本机端口，DNS 是本机替身，不联网。手机上的虚拟网卡（TUN）加假地址那条路这台机器开不了，没有核对；
真实节点、真实 DoH 也没有。所以这里的结果只说明“这两个版本的官方 Linux 程序在本机代理端口上的行为”，不等于 SFA 上的表现。

用法（仓库根目录）：source ~/proxy-vendor/env.sh && python3 handoff/notes/r18_singbox_1143_probes.py > handoff/notes/r18_singbox_1143_probes.out
要 SINGBOX1143_BIN（handoff/setup_env.sh 2026-10-15 起登记）、SINGBOX_BIN（1.14.1）、SRS_DIR。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools"), os.path.dirname(os.path.abspath(__file__))]

import build as builder  # noqa: E402
import check_real_routes as crr  # noqa: E402
import r15_review_probes as r15  # noqa: E402
import real_data as rd  # noqa: E402
from generator.model import build_plan, load  # noqa: E402

CONFIG = "sing-box/sing-box-1.14.json"


def version(binary: str) -> str:
    out = subprocess.run([binary, "version"], capture_output=True, text=True).stdout.splitlines()
    rev = next((ln.split(":", 1)[1].strip() for ln in out if ln.startswith("Revision:")), "?")
    return f"{out[0] if out else '?'}（Revision {rev[:12]}）"


FULL_OUT = os.path.join(ROOT, "handoff", "notes", "r18_singbox_1143_full.out")


def full_check(b1143: str) -> int:
    """tools/check_real_routes.py 换成 1.14.3 跑一遍，返回它的退出码；“不符合”的行打印出来。"""
    env = os.environ
    args = [sys.executable, os.path.join(ROOT, "tools", "check_real_routes.py"), "--mihomo", env["MIHOMO_BIN"], "--singbox", b1143,
            "--geodata-dir", env["GEODATA_DIR"], "--srs-dir", env["SRS_DIR"], "--bm7", env["BM7_SRC"]]
    for opt, name in (("--dlc", "DLC_SRC"), ("--geodata-origin", "GEODATA_ORIGIN"), ("--srs-origin", "SRS_ORIGIN"),
                      ("--bm7-origin", "BM7_ORIGIN")):
        if env.get(name):
            args += [opt, env[name]]
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600)
    with open(FULL_OUT, "w", encoding="utf-8") as f:
        f.write(r.stdout + (("\n--- stderr ---\n" + r.stderr) if r.stderr.strip() else "") + f"\n退出码：{r.returncode}\n")
    lines = r.stdout.splitlines()
    bad = [i for i, ln in enumerate(lines) if "[不符合]" in ln]
    print(f"退出码 {r.returncode}；最后一行“{lines[-1].strip() if lines else ''}”；"
          f"标着“不符合”的 {len(bad)} 段（完整输出：handoff/notes/r18_singbox_1143_full.out）")
    for i in bad:
        print("  " + lines[i].strip()[:300])
        j = i + 1
        while j < len(lines) and lines[j].startswith("      "):
            print("    " + lines[j].strip()[:300])
            j += 1
    return r.returncode


def real_config(binaries: dict, srs_dir: str) -> int:
    model = load(ROOT, include_local=False)
    files = builder.render_public(model, build_plan(model))
    text = files[CONFIG]
    print(f"配置：这一版生成的 {CONFIG}（统一源 {model.project['project']['source_version']}，SHA-256 {crr.sha256_text(text)}）")
    batches = (("outbound_resolve（走代理的组换成测试出口）", rd.outbound_cases(), False),
               ("outbound_switched（默认直连、可以切换的组也切到测试出口）", rd.outbound_switched_cases(), True))
    differ, failed = 0, 0
    for title, cases, switch in batches:
        hosts = [c["host"] for c in cases]
        print(f"\n  {title}：{len(hosts)} 个主机")
        for scen in (s for s in rd.OUTBOUND_SCENARIOS if s.startswith("singbox-")):
            _, outbound, transport = scen.split("-")
            got = {}
            for label, binary in binaries.items():
                recv = {}
                try:
                    dns = crr.singbox_outbound_probe(binary, srs_dir, text, hosts, outbound, transport, received=recv,
                                                     switch_default_direct=switch)
                    got[label] = (dns, recv)
                except Exception as e:                # noqa: BLE001  一次性核对：一项失败照样跑下一项
                    got[label] = None
                    print(f"    {scen} {label}：没有跑成（{type(e).__name__}: {e}）")
            if any(v is None for v in got.values()):
                failed += 1
                continue
            (old_label, (old_dns, old_recv)), (new_label, (new_dns, new_recv)) = list(got.items())
            rows = []
            for h in hosts:
                a = f"DNS {old_dns[h]}" + (f"，节点收到 {old_recv[h]}" if old_recv else "")
                b = f"DNS {new_dns[h]}" + (f"，节点收到 {new_recv[h]}" if new_recv else "")
                rows.append((h, a, b, a != b))
            n = sum(r[3] for r in rows)
            differ += bool(n)
            print(f"    {scen}：{'两个版本相同' if not n else f'{n} 个主机不同'}（左 {old_label}，右 {new_label}）")
            for h, a, b, d in rows:
                print(f"      {'≠' if d else ' '} {h}：{a}  |  {b}")
    print(f"\n实际配置的出站核对：六组（三个场景 × 两批主机）里两个版本结果不同的 {differ} 组，没有跑成的 {failed} 组")
    return differ + failed


def main() -> int:
    b1143, b1141, srs = os.environ.get("SINGBOX1143_BIN"), os.environ.get("SINGBOX_BIN"), os.environ.get("SRS_DIR")
    for name, path in (("SINGBOX1143_BIN", b1143), ("SINGBOX_BIN", b1141), ("SRS_DIR", srs)):
        if not path or not os.path.exists(path):
            print(f"没有找到 {name}（先 source ~/proxy-vendor/env.sh；1.14.3 由 handoff/setup_env.sh 2026-10-15 起登记）")
            return 2
    print(f"sing-box 1.14.3：{version(b1143)}")
    print(f"sing-box 1.14.1（对照）：{version(b1141)}")
    print("\n== 1. 最小核对（handoff/notes/r15_review_probes.py 的同一批配置），sing-box 1.14.3 ==")
    print(" SOCKS 出口 → 本机 SOCKS5 接收端：")
    r15.socks_variants(b1143)
    print(" 配对的服务端（同一版本；服务端只记日志、一律拒绝）：")
    r15.paired_variants(b1143, False)
    r15.paired_variants(b1143, True)
    print("\n== 2. 实际配置的出站核对：1.14.1 与 1.14.3 对照 ==")
    real_config({"1.14.1": b1141, "1.14.3": b1143}, srs)
    print("\n== 3. 实际配置的全套核对（tools/check_real_routes.py，1.14.3 当 1.14 版的内核；人工期望按 1.14.1 写） ==")
    full_check(b1143)
    return 0


if __name__ == "__main__":
    sys.exit(main())
