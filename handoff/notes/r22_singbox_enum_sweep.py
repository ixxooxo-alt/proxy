"""r22 的一次性核对（2026-11-18，不属于 tools/run_checks.sh）：全项目复核 F03 的同一类自查——转换器把订阅里的取值原样写给 sing-box 的字段，
sing-box 认哪些取值？

F03 是 packet-encoding 的 packet：mihomo 认，转换器原样写进去，sing-box 建出站时报错，整份配置启动不了（不只是丢一个节点）。
同样原样写过去、取值有限的字段还有：Shadowsocks 的加密方式（cipher → method）、VMess 的加密（cipher → security）、VLESS 的 flow、
TUIC 的 congestion-controller 和 udp-relay-mode、client-fingerprint（→ tls.utls.fingerprint）、smux 的 protocol（→ multiplex.protocol）。
这里拿官方 sing-box 1.14.1 和 1.12.0（tools/run_checks.sh 用的同两个程序）逐个取值跑 sing-box check（check 会建出站，取值不认就报错），
看哪些两个版本都认。候选取值是两边文档和常见订阅里出现过的写法，外加一个明显不存在的值作对照（必须被拒绝，证明这样能查出来）。
结果用来定 generator/nodes.py 里的白名单：两个版本都认的才转换，别的跳过并写进报告。
用法：python3 -B r22_singbox_enum_sweep.py <sing-box 1.14.1> <sing-box 1.12.0>"""
import json
import os
import re
import subprocess
import sys
import tempfile

UUID = "00000000-0000-4000-8000-000000000001"
KEY16 = "RVhBTVBMRS1LRVktMTIzNA=="                       # 16 字节（虚构）
KEY32 = "RVhBTVBMRS1LRVktMTIzNDU2Nzg5MDEyMzQ1Njc4OTA="   # 32 字节（虚构）


def ss(m):
    pw = KEY16 if m == "2022-blake3-aes-128-gcm" else KEY32 if m.startswith("2022-") else "example-password"
    return {"type": "shadowsocks", "server": "x.example.net", "server_port": 8388, "method": m, "password": pw}


def vmess(s):
    return {"type": "vmess", "server": "x.example.net", "server_port": 443, "uuid": UUID, "security": s}


def vless_flow(f):
    return {"type": "vless", "server": "x.example.net", "server_port": 443, "uuid": UUID, "flow": f,
            "tls": {"enabled": True, "server_name": "x.example.net"}}


def tuic(cc="bbr", mode="native"):
    return {"type": "tuic", "server": "x.example.net", "server_port": 443, "uuid": UUID, "password": "p",
            "congestion_control": cc, "udp_relay_mode": mode, "tls": {"enabled": True, "server_name": "x.example.net", "alpn": ["h3"]}}


def utls(fp):
    return {"type": "trojan", "server": "x.example.net", "server_port": 443, "password": "p",
            "tls": {"enabled": True, "server_name": "x.example.net", "utls": {"enabled": True, "fingerprint": fp}}}


def mux(p):
    return {"type": "vmess", "server": "x.example.net", "server_port": 443, "uuid": UUID, "security": "auto",
            "multiplex": {"enabled": True, "protocol": p}}


FIELDS = [
    ("Shadowsocks 加密方式（cipher → method）", ss,
     ["aes-128-gcm", "aes-192-gcm", "aes-256-gcm", "chacha20-ietf-poly1305", "xchacha20-ietf-poly1305",
      "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm", "2022-blake3-chacha20-poly1305", "none", "plain", "dummy",
      "aes-128-ctr", "aes-192-ctr", "aes-256-ctr", "aes-128-cfb", "aes-192-cfb", "aes-256-cfb", "rc4-md5", "rc4",
      "chacha20-ietf", "chacha20", "xchacha20", "aes-128-ccm", "aes-256-ccm", "aes-128-gcm-siv", "aes-256-gcm-siv",
      "chacha8-ietf-poly1305", "xchacha8-ietf-poly1305", "2022-blake3-chacha8-poly1305", "lea-128-gcm", "rabbit128-poly1305",
      "aegis-128l", "aegis-256", "aez-384", "deoxys-ii-256-128", "AES-128-GCM"]),
    ("VMess 加密（cipher → security）", vmess,
     ["auto", "none", "zero", "aes-128-gcm", "chacha20-poly1305", "aes-128-cfb", "aes-128-ctr", "legacy", "AUTO"]),
    ("VLESS flow", vless_flow,
     ["xtls-rprx-vision", "xtls-rprx-vision-udp443", "xtls-rprx-direct", "xtls-rprx-origin", "xtls-rprx-splice"]),
    ("TUIC congestion-controller（→ congestion_control）", lambda v: tuic(cc=v), ["cubic", "new_reno", "bbr", "newreno", "bbr_meta_v1"]),
    # udp_relay_mode：sing-box 建出站时不查取值（1.14.1、1.12.0 的 protocol/tuic/outbound.go：只认 quic，别的都按 native），
    # 对照值也会“认”，所以这一项查不出不认的值；列出来只为记下这一点（下面的“对照失败”是预期的）
    ("TUIC udp-relay-mode（→ udp_relay_mode）", lambda v: tuic(mode=v), ["native", "quic"]),
    ("client-fingerprint（→ tls.utls.fingerprint）", utls,
     ["chrome", "firefox", "edge", "safari", "360", "qq", "ios", "android", "random", "randomized", "chrome_psk",
      "chrome_psk_shuffle", "chrome_padding_psk_shuffle", "chrome_pq", "chrome_pq_psk", "chrome120", "firefox120", "safari16",
      "randomizednoalpn", "none"]),
    ("smux protocol（→ multiplex.protocol）", mux, ["smux", "yamux", "h2mux"]),
]
# 另查一项：Reality 不带 uTLS 时 sing-box 认不认（client-fingerprint 写 none 时 mihomo 不用 uTLS；转换时能不能照样去掉）
REALITY = {"type": "vless", "server": "x.example.net", "server_port": 443, "uuid": UUID, "flow": "xtls-rprx-vision",
           "tls": {"enabled": True, "server_name": "www.example.com",
                   "reality": {"enabled": True, "public_key": "AQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRobHB0eHyA", "short_id": "abcd"}}}
BOGUS = "not-a-real-value-xyz"


def check(binary, ob, tmp):
    p = os.path.join(tmp, "c.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"log": {"disabled": True}, "outbounds": [{"tag": "t", **ob}]}, f)
    r = subprocess.run([binary, "check", "-c", p], capture_output=True, text=True, timeout=60)
    msg = re.sub(r"\x1b\[[0-9;]*m", "", r.stdout + r.stderr).strip().splitlines()      # 去掉终端颜色
    return r.returncode == 0, (msg[-1] if msg else "")


def main():
    b114, b112 = sys.argv[1:3]
    for b in (b114, b112):
        print(subprocess.run([b, "version"], capture_output=True, text=True).stdout.splitlines()[0])
    tmp = tempfile.mkdtemp(prefix="enum-sweep-")
    bad = []
    try:
        for label, make, values in FIELDS:
            print(f"\n{label}")
            both = []
            for v in values + [BOGUS]:
                ok114, m114 = check(b114, make(v), tmp)
                ok112, m112 = check(b112, make(v), tmp)
                if ok114 and ok112:
                    both.append(v)
                why = "" if ok114 and ok112 else "；" + (m114 if not ok114 else m112)[-160:]
                print(f"  {v}: 1.14.1 {'认' if ok114 else '不认'}，1.12.0 {'认' if ok112 else '不认'}{why}")
                if v == BOGUS and (ok114 or ok112) and not label.startswith("TUIC udp-relay-mode"):
                    bad.append(f"{label}：明显不存在的值也被认了，这样查不出来")
            print(f"  两个版本都认：{both if BOGUS not in both else '（对照失败）'}")
        print("\nReality（不带 uTLS / 带 uTLS chrome）")
        for label, ob in (("不带 uTLS", REALITY),
                          ("带 uTLS chrome", {**REALITY, "tls": {**REALITY["tls"], "utls": {"enabled": True, "fingerprint": "chrome"}}})):
            r = [check(b, ob, tmp) for b in (b114, b112)]
            print(f"  {label}: 1.14.1 {'认' if r[0][0] else '不认'}，1.12.0 {'认' if r[1][0] else '不认'}"
                  + ("" if r[0][0] and r[1][0] else "；" + (r[0][1] if not r[0][0] else r[1][1])[-160:]))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    print("对照都被拒绝，结果可用" if not bad else "不符：" + "；".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
