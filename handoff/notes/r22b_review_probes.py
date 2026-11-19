#!/usr/bin/env python3
"""r22 送审稿的两份审核（2026-11-19，docs/08 第 24、25 轮）里，用官方程序核实、并据以修改转换器的几件事。一次性核对，不进 run_checks.sh。

1. 订阅里不带引号的值，mihomo v1.19.31 读成什么：把值写成节点名字（name 是文字字段，mihomo 读成什么就转成什么文字），
   启动 mihomo、从控制接口读回名字，和转换器的 go_plain_scalar 对照——整数应当一样，小数在 mihomo 里写成科学计数法
   （转换器遇到小数跳过节点），日期 mihomo 读不了（-t 报 time.Time，转换器同样跳过）。
2. 同一张表里同一个键写两次：mihomo -t 报 mapping key already defined（整份读不下去）。2026-11-19 交第二份送审稿前自查加：
   go-yaml 只在读进来的表上查——最外层重复报错；不认识的顶层键里重复、嵌套合并（被引用的表自己也合并、又盖掉继承来的键）都能过；
   mihomo 用 proxy-providers 读订阅时只认 proxies，订阅的 proxy-groups 里有重复照样读得出节点，proxies 里有重复则一个也读不出。
3. sing-box 1.14.1、1.12.0 的 check：不合格的 SS2022 密钥报 FATAL（整份启动不了）；TUIC 带 uTLS 能过 check（所以只能在转换时拦）。
4. 转换器对上面这些写法的处理（跳过 / 转换 / 提示）。

用法：python3 -B handoff/notes/r22b_review_probes.py <mihomo> <sing-box 1.14.1> <sing-box 1.12.0> <工作目录（新建）>
最后一行“全部符合”，退出码 0。"""
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from generator import nodes  # noqa: E402

SCALARS = ["0x_", "0b_", "0o_", "0_", "1_000", "0x_20", "1__0", "0x1_", "_1", "01234567", "0o17", "0089", "1_0.5", ".5",
           "123456789012345678901", "-9223372036854775809", "10000000000000000000", "0x1FFFFFFFFFFFFFFFFF",
           "0o7777777777777777777777777", "2026-02-30", "2026-01-02T03:04:05", "=", "1e400", "0b2", "08", "1:20"]
DATES = ["2026-1-2", "2026-1-2 3:4:5.5", "2026-01-02T03:04:05Z"]
K16 = "RVhBTVBMRS1LRVktMTIzNA=="
K32 = "RVhBTVBMRS1LRVktMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="
bad = []


def check(label, ok, detail=""):
    print(f"[{'符合' if ok else '不符合'}] {label}" + (f"：{detail}" if detail else ""))
    if not ok:
        bad.append(label)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def mihomo_names(mihomo, work, values):
    port = free_port()
    lines = ["mode: rule", "log-level: warning", f"external-controller: 127.0.0.1:{port}", "proxies:"]
    lines += [f"  - {{name: {v}, type: socks5, server: 127.0.0.1, port: {i}}}" for i, v in enumerate(values, 1)]
    lines += ["rules:", "  - MATCH,DIRECT"]
    cfg = os.path.join(work, "names.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    p = subprocess.Popen([mihomo, "-d", work, "-f", cfg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/proxies", timeout=1) as r:
                    data = json.load(r)["proxies"]
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise SystemExit("mihomo 的控制接口没有起来")
    finally:
        p.terminate()
        p.wait(timeout=10)
    # 节点按写进去的顺序编了端口 1、2、3……，用不到；名字按 type 过滤出来，再按写入顺序对回去
    got = [k for k, v in data.items() if str(v.get("type", "")).lower() == "socks5"]
    return got


def mihomo_provider_names(mihomo, work, provider_text):
    """把 provider_text 当成订阅，用 proxy-providers（type: file）交给 mihomo，从控制接口读回这个 provider 里的节点名；读不出来是空列表。"""
    port = free_port()
    with open(os.path.join(work, "sub.yaml"), "w", encoding="utf-8") as f:
        f.write(provider_text)
    lines = ["mode: rule", "log-level: warning", f"external-controller: 127.0.0.1:{port}",
             "proxy-providers:", "  sub:", "    type: file", "    path: ./sub.yaml", "    health-check: {enable: false}",
             "proxy-groups:", "  - {name: G, type: select, use: [sub]}", "rules:", "  - MATCH,DIRECT"]
    cfg = os.path.join(work, "provider.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    p = subprocess.Popen([mihomo, "-d", work, "-f", cfg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/providers/proxies", timeout=1) as r:
                    data = json.load(r)["providers"]
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise SystemExit("mihomo 的控制接口没有起来")
    finally:
        p.terminate()
        p.wait(timeout=10)
    return [x["name"] for x in (data.get("sub") or {}).get("proxies") or []]


def mihomo_test(mihomo, work, text):
    cfg = os.path.join(work, "t.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(text)
    r = subprocess.run([mihomo, "-t", "-d", work, "-f", cfg], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def singbox_check(binary, work, outbound):
    cfg = os.path.join(work, "sb.json")
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump({"log": {"level": "error"}, "outbounds": [outbound, {"type": "direct", "tag": "direct"}]}, f)
    r = subprocess.run([binary, "check", "-c", cfg], capture_output=True, text=True)
    return r.returncode, re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout + r.stderr).strip())[:200]


def main(mihomo, sb114, sb112, work):
    os.makedirs(work)
    print(subprocess.run([mihomo, "-v"], capture_output=True, text=True).stdout.strip().splitlines()[0])
    for b in (sb114, sb112):
        print(subprocess.run([b, "version"], capture_output=True, text=True).stdout.strip().splitlines()[0])
    print("\n1. 不带引号的值（写成节点名字，从 mihomo 的控制接口读回）")
    names = set(mihomo_names(mihomo, work, SCALARS))
    for v in SCALARS:
        ours = nodes.go_plain_scalar(v)
        if isinstance(ours, float):
            hit = [n for n in names if "E" in n and abs(float(n) - ours) <= abs(ours) * 1e-15]
            check(f"{v!r}：mihomo 读成小数，转换器也读成小数（跳过节点）", bool(hit), f"mihomo {hit}，转换器 {ours!r}")
        else:
            want = str(ours)
            check(f"{v!r}：mihomo 读成 {want!r}，转换器也是", want in names, f"转换器 {ours!r}")
    for v in DATES:
        rc, out = mihomo_test(mihomo, work, f"mode: rule\nproxies:\n  - {{name: {v}, type: socks5, server: 127.0.0.1, port: 1}}\n"
                                            "rules:\n  - MATCH,DIRECT\n")
        ours = nodes.go_plain_scalar(v)
        check(f"{v!r}：mihomo 读成日期（-t 报错），转换器也读成日期（跳过节点）",
              rc != 0 and "time.Time" in out and not isinstance(ours, str), f"转换器 {ours!r}")
    print("\n2. 同一张表里同一个键写两次")
    rc, out = mihomo_test(mihomo, work, "mode: rule\nproxies:\n  - name: a\n    type: trojan\n    server: a.example\n    port: 443\n"
                                        "    password: p\n    skip-cert-verify: true\n    skip-cert-verify: false\nrules:\n  - MATCH,DIRECT\n")
    check("mihomo -t 整份报错（mapping key already defined）", rc != 0 and "already defined" in out)
    try:
        nodes.load_clash_proxies("proxies:\n  - name: a\n    password: p\n    password: q\n")
        check("转换器整份不转换", False, "没有报错")
    except ValueError as e:
        check("转换器整份不转换，只报键名和行号", "第 4 行的 password（第 3 行已经有了）" in str(e) and "q" not in str(e).split("。")[0][-3:])
    # 交第二份送审稿前自查（2026-11-19）：mihomo 在哪些地方查重复，转换器跟着在哪些地方查
    sock = "type: socks5, server: 127.0.0.1"
    for label, text, mihomo_ok in (
            ("最外层的键重复", f"mode: rule\nmode: global\nproxies:\n  - {{name: a, {sock}, port: 1}}\nrules:\n  - MATCH,DIRECT\n", False),
            ("不认识的顶层键里重复", f"mode: rule\nx: {{tls: true, tls: false}}\nproxies:\n  - {{name: a, {sock}, port: 1}}\n"
                              "rules:\n  - MATCH,DIRECT\n", True),
            ("嵌套合并（被引用的表自己也合并、又盖掉继承来的键）",
             f"mode: rule\nbase: &base {{{sock}, port: 1}}\nproxies:\n  - &a {{<<: *base, name: a, port: 2}}\nhk: {{<<: *a, name: b}}\n"
             "rules:\n  - MATCH,DIRECT\n", True)):
        rc, out = mihomo_test(mihomo, work, text)
        check(f"{label}：mihomo -t {'通过' if mihomo_ok else '报错'}", (rc == 0) == mihomo_ok and (mihomo_ok or "already defined" in out),
              out.strip().splitlines()[-1][-80:] if out.strip() else "")
        try:
            nodes.load_clash_proxies(text)
            ours = True
        except ValueError:
            ours = False
        check(f"{label}：转换器{'照常转换' if mihomo_ok else '整份不转换'}", ours == mihomo_ok)
    for label, text, want in (
            ("订阅的 proxy-groups 里有重复", f"proxies:\n  - {{name: a, {sock}, port: 1}}\nproxy-groups:\n  - {{name: g, name: h}}\n", ["a"]),
            ("订阅的 proxies 里有重复", f"proxies:\n  - {{name: a, {sock}, port: 1, port: 2}}\n", [])):
        got = mihomo_provider_names(mihomo, work, text)
        check(f"{label}：mihomo 用 proxy-providers 读出的节点是 {want}", got == want, f"读出 {got}")
        try:
            ours = [p["name"] for p in nodes.load_clash_proxies(text)]
        except ValueError:
            ours = []
        check(f"{label}：转换器读出的节点是 {want}", ours == want, f"读出 {ours}")
    print("\n3. sing-box check")
    for label, method, key, ok in (("aes-128 合格的 16 字节密钥", "2022-blake3-aes-128-gcm", K16, True),
                                   ("aes-128 不是 base64", "2022-blake3-aes-128-gcm", "NOT!BASE64", False),
                                   ("aes-256 只有 16 字节", "2022-blake3-aes-256-gcm", K16, False),
                                   ("chacha20 两段", "2022-blake3-chacha20-poly1305", f"{K32}:{K32}", False),
                                   ("aes-128 两段", "2022-blake3-aes-128-gcm", f"{K16}:{K16}", True)):
        ob = {"type": "shadowsocks", "tag": "s", "server": "a.example", "server_port": 443, "method": method, "password": key}
        for name, b in (("1.14.1", sb114), ("1.12.0", sb112)):
            rc, out = singbox_check(b, work, ob)
            check(f"SS2022 {label}：sing-box {name} check {'通过' if ok else '报错'}", (rc == 0) == ok, out)
        why = nodes.ss2022_key_problem(method, key)
        check(f"SS2022 {label}：转换器{'放行' if ok else '跳过'}", (why is None) == ok, why or "")
    tuic = {"type": "tuic", "tag": "t", "server": "a.example", "server_port": 443, "uuid": "00000000-0000-4000-8000-000000000001",
            "password": "p", "tls": {"enabled": True, "server_name": "a.example", "utls": {"enabled": True, "fingerprint": "chrome"}}}
    for name, b in (("1.14.1", sb114), ("1.12.0", sb112)):
        rc, out = singbox_check(b, work, tuic)
        check(f"TUIC 带 uTLS：sing-box {name} 的 check 能过（问题在拨号时，check 查不出来）", rc == 0, out)
    print("\n4. 转换器的处理")
    u = {"uuid": "00000000-0000-4000-8000-000000000001"}
    for label, d, expect in (
            ("TUIC 带指纹：不写 uTLS", {"type": "tuic", **u, "password": "p", "client-fingerprint": "chrome"},
             lambda o: o and "utls" not in o["tls"]),
            ("VMess auto 加 TLS：写明 aes-128-gcm", {"type": "vmess", **u, "cipher": "auto", "tls": True},
             lambda o: o and o["security"] == "aes-128-gcm"),
            ("VMess 大写 AES-128-GCM：转小写", {"type": "vmess", **u, "cipher": "AES-128-GCM"},
             lambda o: o and o["security"] == "aes-128-gcm"),
            ("VLESS flow xtls-rprx-vision-udp443：取前 16 个字符", {"type": "vless", **u, "tls": True, "flow": "xtls-rprx-vision-udp443"},
             lambda o: o and o["flow"] == "xtls-rprx-vision"),
            ("带引号的端口 0100：八进制 64", {"type": "trojan", "password": "p", "port": "0100"},
             lambda o: o and o["server_port"] == 64),
            ("port: true：跳过", {"type": "trojan", "password": "p", "port": True}, lambda o: o is None)):
        out, report, _ = nodes.convert([{"name": "n", "server": "a.example", "port": 443, **d}])
        o = out[0] if out else None
        check(label, bool(expect(o)), "；".join(report))
    print()
    print("全部符合" if not bad else f"有 {len(bad)} 项不符合：" + "、".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    sys.exit(main(*sys.argv[1:]))
