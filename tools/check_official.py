#!/usr/bin/env python3
"""用官方程序检查生成的配置（mihomo -t、sing-box check），包括带样例节点的 sing-box 私密配置。

公开模板里没有节点，所以只检查模板发现不了节点转换的问题（审核 F01 / F02）；这里另用 tests/node_samples.yaml
里的虚构节点生成一份 sing-box 配置交给官方程序检查。另做一次自检：故意写坏一个出站，确认检查确实会失败。
mihomo 也有两条自检：把 proxy-server-nameserver 清空（分别只留 respect-rules、只留节点的解析策略），内核必须拒绝加载。

节点按名称分地区（2026-10-02）：`mihomo -t` 只检查配置能不能解析，看不出筛选正则把节点分到了哪里。所以另外
启动一次 mihomo：把公开配置里的订阅换成一个本地文件订阅（type: file），里面是一批名字来自 tests/ 的假节点
（服务器都是 127.0.0.1，不联网，关闭健康检查）；策略组部分原样不动（include-all-providers + filter，YAML 别名也保留）。
这样走的就是真实订阅的那条路径：内核从订阅里取节点，再用每个组的 filter 筛（源码 adapter/outboundgroup/groupbase.go
的 GetProxies）。然后从它的本机控制接口读出每个地区组实际收进了哪些节点，和手写的期望、Python 的结果逐个对比。
每个地区有两条筛选（2026-10-04，审核 F04）：“手动”组和 PayPal 的美国固定入口用宽的，“自动 / 故障转移 / 负载均衡”
用严的（只收名字只指向这个地区的节点）。两条都比：手动组对宽的那套期望，另外三个模式组对严的那套期望。
这次启动不开 TUN、不设系统代理、不监听代理端口，控制接口只监听 127.0.0.1 的一个临时端口，结束后立即退出。
同样的检查再做一遍“带本地补充”的配置：在临时目录里给统一源配上 tests/local_overlay_sample.yaml 那份虚构的
node_names（补充词、指定节点），生成私密版的 mihomo 配置交给内核分组（不读、不写你的 source/local.yaml）。

用法：
  python3 tools/check_official.py --mihomo <mihomo 可执行文件> --singbox <sing-box 1.14 可执行文件> \\
      [--singbox-112 <sing-box 1.12 可执行文件>] [--geodata-dir <目录>]
官方程序请从各项目的 GitHub Releases 下载，并与发布页列出的 SHA-256 核对。
mihomo -t 需要 GeoSite / GeoIP 数据：给了 --geodata-dir（放 MetaCubeX/meta-rules-dat 发布的 geosite.dat、geoip.dat、
geoip.metadb、country.mmdb、GeoLite2-ASN.mmdb）就复制进临时检查目录；不给则由 mihomo 按配置里的 geox-url 自行下载。
全程只用临时目录，不读取、不改动正在使用的代理配置。
退出码：任一检查不符合预期时为 1。
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from generator import emit_mihomo, emit_singbox, nodes as nodeconv  # noqa: E402
from generator.model import build_plan, load  # noqa: E402
from generator.util import safe_stdout  # noqa: E402

import build as builder  # noqa: E402
# 同目录：手写样本 + CLDR / 时区库的名字；本地补充样例；两者各自“严的那套”的期望
from check_icu import overlay_expect_auto, overlay_sample, sample_expect_auto, sample_names  # noqa: E402

AUTO_MODES = ("自动", "故障转移", "负载均衡")


def run(cmd, cwd=None, timeout=300):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, (r.stdout + r.stderr).strip()


def version(binary, args):
    code, out = run([binary] + args, timeout=60)
    return out.splitlines()[0] if out else f"（退出码 {code}）"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def overlay_model(tmp: str):
    """在临时目录里复制一份统一源，配上虚构的本地补充（tests/local_overlay_sample.yaml），返回 (模型, 规则计划)。"""
    root = os.path.join(tmp, "overlay-root")
    shutil.copytree(os.path.join(ROOT, "source"), os.path.join(root, "source"),
                    ignore=shutil.ignore_patterns("local.yaml"))
    with open(os.path.join(root, "source", "local.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"node_names": overlay_sample()[0]}, f, allow_unicode=True, sort_keys=False)
    m = load(root, include_local=True)
    return m, build_plan(m)


def mihomo_grouping(mihomo: str, home: str, profile_text: str, model, names: list, expect: dict, expect_auto: dict) -> list:
    """用官方内核实际分一次组。返回问题列表（空 = 与期望和 Python 的结果完全一致）。
    names：假节点的名字；expect：{名字: 期望进哪些地区的手动组}；expect_auto：{名字: 期望进哪个地区的自动类组}
    （都只比其中列出的名字）。"""
    port = _free_port()
    with open(os.path.join(home, "fake-nodes.yaml"), "w", encoding="utf-8") as f:
        yaml.safe_dump({"proxies": [{"name": n, "type": "ss", "server": "127.0.0.1", "port": 1,
                                     "cipher": "aes-128-gcm", "password": "x"} for n in names]},
                       f, allow_unicode=True, sort_keys=False, width=100000)
    # 订阅换成本地文件（健康检查关掉，地址与各组相同，所以不会发起任何测速）；其余只做最小的文本替换，
    # 策略组里的 include-all-providers、filter 和 YAML 锚点 / 别名原样交给 mihomo 自己解析
    provider = ("proxy-providers:\n  假节点:\n    type: file\n    path: ./fake-nodes.yaml\n"
                "    health-check:\n      enable: false\n      url: " + model.hc["url_https"] + "\n\n")
    text, n1 = re.subn(r"(?ms)^proxy-providers:\n.*?(?=^proxy-groups:)", lambda _m: provider, profile_text)
    text = text.replace("geo-auto-update: true", "geo-auto-update: false")
    if n1 != 1 or "include-all-providers: true" not in text:
        return ["没能把公开配置改写成带假节点的测试配置（生成器的输出格式变了？）"]
    text = f"external-controller: 127.0.0.1:{port}\n" + text
    path = os.path.join(home, "grouping.yaml")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    proc = subprocess.Popen([mihomo, "-d", home, "-f", path], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        got = None
        for _ in range(120):
            time.sleep(0.5)
            if proc.poll() is not None:
                break
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/providers/proxies", timeout=3) as r:
                    # 控制接口先于订阅就绪：这时 providers 可能还是 null
                    loaded = len(((json.load(r).get("providers") or {}).get("假节点") or {}).get("proxies") or [])
                if loaded < len(set(names)):
                    continue                    # 订阅文件还没读完
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/proxies", timeout=10) as r:
                    got = json.load(r)["proxies"]
                    break
            except OSError:
                continue
        if got is None:
            out = proc.stdout.read().decode("utf-8", "replace") if proc.poll() is not None else "（60 秒内控制接口没有响应）"
            return ["mihomo 没有启动成功：" + out[-600:]]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    def members_of(group):
        return set(got[group].get("all") or []) - {"REJECT", "COMPATIBLE"}

    def differs(group, have, rx):
        py = {n for n in names if re.search(rx, n)}
        if have != py:
            only_m, only_p = sorted(have - py)[:5], sorted(py - have)[:5]
            problems.append(f"{group}：mihomo 与 Python 不一致（只在 mihomo：{only_m}；只在 Python：{only_p}）")

    rxs, strict = model.node_regexes(), model.node_regexes_strict()
    region_group = {r["id"]: r["name"] + "·手动" for r in model.regions}
    region_group[model.other_region["id"]] = model.other_region["name"]
    problems = []
    # 宽的那套：各地区的手动组 + 其他地区
    members = {}
    for gid, group in region_group.items():
        if group not in got:
            problems.append(f"mihomo 里没有组 {group}")
            continue
        members[gid] = members_of(group)
        differs(group, members[gid], rxs[gid])
    for n, want in expect.items():
        have = sorted(g for g, mem in members.items() if n in mem)
        if have != want:
            problems.append(f"{n!r}：期望进 {want} 的手动组，mihomo 分到 {have}")
    # 严的那套：自动 / 故障转移 / 负载均衡。三个组引用同一条正则（YAML 别名），成员必须相同；
    # 并且只能是同一地区手动组的一部分
    auto = {}
    for r in model.regions:
        gid = r["id"]
        per_mode = {}
        for mode in AUTO_MODES:
            group = f"{r['name']}·{mode}"
            if group not in got:
                problems.append(f"mihomo 里没有组 {group}")
                continue
            per_mode[mode] = members_of(group)
            differs(group, per_mode[mode], strict[gid])
        if len({frozenset(v) for v in per_mode.values()}) > 1:
            problems.append(f"{r['name']} 的自动 / 故障转移 / 负载均衡三个组成员不相同")
        auto[gid] = per_mode.get(AUTO_MODES[0], set())
        if not auto[gid] <= members.get(gid, set()):
            problems.append(f"{r['name']}·自动 里有不在 {r['name']}·手动 里的节点：{sorted(auto[gid] - members.get(gid, set()))[:5]}")
    for n, want in expect_auto.items():
        have = sorted(g for g, mem in auto.items() if n in mem)
        if have != want:
            problems.append(f"{n!r}：期望进 {want} 的自动类组，mihomo 分到 {have}")
    twice = sorted(n for n in names if sum(1 for mem in auto.values() if n in mem) > 1)
    if twice:
        problems.append(f"有节点同时进了两个地区的自动类组：{twice[:5]}")
    # PayPal 的美国固定入口由人来选，用宽的那条
    fixed = model.special_entries["paypal_fixed"]
    if fixed["name"] in got:
        differs(fixed["name"], members_of(fixed["name"]), rxs[fixed["region"]])
    else:
        problems.append(f"mihomo 里没有组 {fixed['name']}")
    manual_only = sum(1 for n in names if any(n in members[g] and n not in auto[g] for g in auto if g in members))
    print(f"  节点 {len(names)} 个（手写期望：手动组 {len(expect)} 个、自动类组 {len(expect_auto)} 个）；手动组（括号里是其中进自动类组的）："
          + "、".join(f"{region_group[g]} {len(m)}" + (f"（{len(auto[g])}）" if g in auto else "") for g, m in members.items())
          + f"；只进手动组的 {manual_only} 个")
    return problems


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mihomo", required=True)
    ap.add_argument("--singbox", required=True, help="sing-box 1.14.x")
    ap.add_argument("--singbox-112", help="sing-box 1.12.x（检查兼容版）")
    ap.add_argument("--geodata-dir", help="mihomo 用的 GeoSite / GeoIP 文件所在目录")
    a = ap.parse_args(argv)
    safe_stdout()

    m = load(ROOT, include_local=False)
    plan = build_plan(m)
    files = builder.render_public(m, plan)
    with open(os.path.join(ROOT, "tests", "node_samples.yaml"), encoding="utf-8") as f:
        samples = yaml.safe_load(f)["proxies"]
    converted, report, renamed = nodeconv.convert(samples, emit_singbox.reserved_tags(m))
    private = {v: emit_singbox.build(m, plan, v, converted, renamed) for v in ("1.14", "1.12")}

    print(f"mihomo：{version(a.mihomo, ['-v'])}")
    print(f"sing-box：{version(a.singbox, ['version'])}")
    if a.singbox_112:
        print(f"sing-box（兼容版检查）：{version(a.singbox_112, ['version'])}")
    print(f"样例节点 {len(samples)} 个：转换 {len(converted)} 个（改名 {len(renamed)} 个），跳过 {len(samples) - len(converted)} 个")
    for line in report:
        print("  " + line)
    print()

    failures = []
    tmp = tempfile.mkdtemp(prefix="official-check-")
    try:
        def check(label, cmd, expect_ok=True, cwd=None):
            code, out = run(cmd, cwd=cwd)
            ok = (code == 0) == expect_ok
            print(f"[{'符合' if ok else '不符合'}] {label}：退出码 {code}" + ("" if expect_ok else "（预期失败）"))
            if out and (not ok or not expect_ok):
                print("    " + "\n    ".join(out.splitlines()[-4:]))
            if not ok:
                failures.append(label)

        # mihomo：两份公开产物；-d 指向隔离目录，GeoSite / GeoIP 下载到这里
        home = os.path.join(tmp, "mihomo-home")
        os.makedirs(home)
        if a.geodata_dir:
            import hashlib
            geo_files = {"geosite.dat": "GeoSite.dat", "geoip.dat": "GeoIP.dat", "geoip.metadb": "geoip.metadb",
                         "country.mmdb": "Country.mmdb", "GeoLite2-ASN.mmdb": "GeoLite2-ASN.mmdb"}
            for src, dst in geo_files.items():
                sp = os.path.join(a.geodata_dir, src)
                if os.path.exists(sp):
                    shutil.copy(sp, os.path.join(home, dst))
                    with open(sp, "rb") as f:
                        print(f"地理数据 {src}：SHA-256 {hashlib.sha256(f.read()).hexdigest()}")
        for rel in ("mihomo/mihomo-core.yaml", "mihomo/mihomo-profile.yaml"):
            p = os.path.join(tmp, os.path.basename(rel))
            with open(p, "w", encoding="utf-8") as f:
                f.write(files[rel])
            check(f"mihomo -t {rel}", [a.mihomo, "-t", "-d", home, "-f", p])
        # 自检（2026-10-05 审核 r10）：mihomo 对 proxy-server-nameserver（解析节点服务器地址的 DNS）有两个要求——
        # 打开 respect-rules 时、写了 proxy-server-nameserver-policy 时，它都不能为空。生成器的写盘前检查
        # （generator/verify.py 的 check_mihomo）照这两条拦；这里各单独触发一条，确认官方内核确实拒绝加载。
        for label, edit in (
                ("清空 proxy-server-nameserver，只留 respect-rules（节点的解析策略已去掉）",
                 lambda d: (d.__setitem__("proxy-server-nameserver", []), d.pop("proxy-server-nameserver-policy"))),
                ("清空 proxy-server-nameserver，只留节点的解析策略（respect-rules 已关闭）",
                 lambda d: (d.__setitem__("proxy-server-nameserver", []), d.__setitem__("respect-rules", False)))):
            conf = yaml.safe_load(files["mihomo/mihomo-core.yaml"])
            edit(conf["dns"])
            p = os.path.join(tmp, "broken-dns.yaml")
            with open(p, "w", encoding="utf-8") as f:
                yaml.safe_dump(conf, f, allow_unicode=True, sort_keys=False, width=100000)
            check(f"自检：mihomo -t，{label}", [a.mihomo, "-t", "-d", home, "-f", p], expect_ok=False)

        # sing-box：公开模板 + 带样例节点的私密配置
        jobs = [(a.singbox, "sing-box-1.14.json", files["sing-box/sing-box-1.14.json"]),
                (a.singbox, "sing-box-1.12.json（在 1.14 上）", files["sing-box/sing-box-1.12.json"]),
                (a.singbox, "样例节点 sing-box-1.14.json", private["1.14"])]
        if a.singbox_112:
            jobs += [(a.singbox_112, "sing-box-1.12.json（在 1.12 上）", files["sing-box/sing-box-1.12.json"]),
                     (a.singbox_112, "样例节点 sing-box-1.12.json（在 1.12 上）", private["1.12"])]
        for i, (binary, label, text) in enumerate(jobs):
            p = os.path.join(tmp, f"sb{i}.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            check(f"sing-box check {label}", [binary, "check", "-c", p])

        # 自检：给一个 HTTP 出站加上它没有的 network 字段（F01 的原样错误），检查必须失败
        conf = json.loads(private["1.14"])
        for o in conf["outbounds"]:
            if o.get("type") == "http":
                o["network"] = "tcp"
                break
        p = os.path.join(tmp, "broken.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(conf, f, ensure_ascii=False)
        check("自检：HTTP 出站带 network 字段", [a.singbox, "check", "-c", p], expect_ok=False)

        # 节点按名称分地区：用官方内核实际分一次组
        print("mihomo 实际分组（假节点，不联网）：")
        names, expect = sample_names()
        probs = mihomo_grouping(a.mihomo, home, files["mihomo/mihomo-profile.yaml"], m, names, expect, sample_expect_auto())
        label = "mihomo 实际分组（手动组用宽的、自动类组用严的）与手写期望、Python 结果一致"
        print(f"[{'符合' if not probs else '不符合'}] {label}")
        for x in probs[:20]:
            print("    " + x)
        if probs:
            failures.append(label)

        # 同样的检查，换成带本地补充（补充词、指定节点）的私密版配置
        print("mihomo 实际分组：带本地补充样例（tests/local_overlay_sample.yaml）的配置：")
        om, oplan = overlay_model(tmp)
        o_expect = overlay_sample()[1]
        o_names = list(dict.fromkeys(list(o_expect) + names))
        probs = mihomo_grouping(a.mihomo, home, emit_mihomo.build(om, oplan, "profile"), om, o_names, o_expect,
                                overlay_expect_auto())
        label = "带本地补充的配置：mihomo 实际分组（宽、严两套）与手写期望、Python 结果一致"
        print(f"[{'符合' if not probs else '不符合'}] {label}")
        for x in probs[:20]:
            print("    " + x)
        if probs:
            failures.append(label)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    print("全部符合预期" if not failures else f"{len(failures)} 项不符合预期：" + "、".join(failures))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
