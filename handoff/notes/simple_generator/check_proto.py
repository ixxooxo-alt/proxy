"""核对原型（proto/out）：完整版与仓库 dist/ 逐字节相同；简易版与完整版除策略组以外相同；简易版的结构。只读仓库。
用法：python3 -B check_proto.py <仓库> <proto 目录>
"""
import json
import os
import re
import sys

REPO, P = sys.argv[1], sys.argv[2]
OUT = os.path.join(P, "out")
sys.path.insert(0, P)
sys.path.insert(0, os.path.join(P, "tests"))
sys.dont_write_bytecode = True
import yaml  # noqa: E402

import emulate  # noqa: E402  （副本里的 tests/emulate.py）
from generator import emit_singbox, emit_stash, nodes as nodeconv, verify  # noqa: E402
from generator.model import build_plan, load  # noqa: E402


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as f:
        return f.read()


# 1. 完整版：和仓库 dist/ 逐字节相同（manifest 除外：多了简易版的条目）
full = ["loon/loon.conf", "loon/loon-strict.conf", "quantumultx/quantumultx.conf", "quantumultx/quantumultx-strict.conf",
        "mihomo/mihomo-profile.yaml", "mihomo/mihomo-core.yaml", "sing-box/sing-box-1.14.json", "sing-box/sing-box-1.12.json",
        "stash/stash.yaml", "stash/stash-strict.yaml", "loon/rules/cn-domains.list", "quantumultx/rules/cn-domains.list",
        "quantumultx/rules/cn-domains-max.list", "quantumultx/rules/domain-fallback.list"]
same = [rel for rel in full if read(REPO + "/dist", rel) == read(OUT, rel)]
print(f"1. 完整版和自有规则文件与仓库 dist/ 逐字节相同：{len(same)}/{len(full)}；不同：{sorted(set(full) - set(same))}")
man = json.loads(read(OUT, "manifest.json"))
print("   manifest 登记的产物数：", len(man["outputs"]))

PAIRS = {"loon/loon-simple.conf": "loon/loon.conf", "loon/loon-simple-strict.conf": "loon/loon-strict.conf",
         "quantumultx/quantumultx-simple.conf": "quantumultx/quantumultx.conf",
         "quantumultx/quantumultx-simple-strict.conf": "quantumultx/quantumultx-strict.conf",
         "mihomo/mihomo-simple-profile.yaml": "mihomo/mihomo-profile.yaml", "mihomo/mihomo-simple-core.yaml": "mihomo/mihomo-core.yaml",
         "sing-box/sing-box-simple-1.14.json": "sing-box/sing-box-1.14.json", "sing-box/sing-box-simple-1.12.json": "sing-box/sing-box-1.12.json",
         "stash/stash-simple.yaml": "stash/stash.yaml", "stash/stash-simple-strict.yaml": "stash/stash-strict.yaml"}


def sections(text):
    out, cur = {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        mm = re.match(r"^\[(.+)\]$", line)
        if mm:
            cur = mm.group(1)
            out.setdefault(cur, [])
        elif cur is not None:
            out[cur].append(line)
    return out


GROUP_SECTIONS = {"Proxy Group", "Remote Filter", "policy"}
print("2. 简易版与完整版：除策略组以外是否相同")
for s_rel, f_rel in PAIRS.items():
    a, b = read(OUT, s_rel), read(OUT, f_rel)
    if s_rel.endswith(".conf"):
        sa, sb = sections(a), sections(b)
        diff = [k for k in set(sa) | set(sb) if k not in GROUP_SECTIONS and sa.get(k) != sb.get(k)]
    elif s_rel.endswith(".yaml"):
        ya, yb = yaml.safe_load(a), yaml.safe_load(b)
        diff = [k for k in set(ya) | set(yb) if k != "proxy-groups" and ya.get(k) != yb.get(k)]
    else:
        ja, jb = json.loads(a), json.loads(b)
        diff = [k for k in set(ja) | set(jb) if k != "outbounds" and ja.get(k) != jb.get(k)]
        oa = [o for o in ja["outbounds"] if o["type"] not in ("selector", "urltest")]
        ob = [o for o in jb["outbounds"] if o["type"] not in ("selector", "urltest")]
        if oa != ob:
            diff.append("非组出站")
    # 注释行（版本号、说明）不比
    print(f"   {s_rel}：{'相同' if not diff else '不同 ' + str(diff)}")

m = load(P, include_local=False)
plan = build_plan(m)
regions = [r["name"] for r in m.regions]
print("3. 简易版结构")
for rel in ("mihomo/mihomo-simple-core.yaml", "stash/stash-simple.yaml"):
    c = yaml.safe_load(read(OUT, rel))
    g = {x["name"]: x for x in c["proxy-groups"]}
    bad = [n for n in g if re.search("·(手动|手动优先|故障转移|负载均衡)$", n)]
    print(f"   {rel}：{len(g)} 个组；不该有的组 {bad}；hidden 的 {[n for n, x in g.items() if x.get('hidden')]}")
    print(f"     日本 = proxies {g['日本'].get('proxies')}，筛选是宽的 jp：{g['日本']['filter'].endswith(m.node_regexes()['jp'][5:])}，"
          f"include-all(-providers) {g['日本'].get('include-all', g['日本'].get('include-all-providers'))}")
    print(f"     国外默认 = proxies {g['国外默认'].get('proxies')}；筛选 {len(g['国外默认']['filter'].encode())} 字节")
    if rel.startswith("stash"):
        rx = re.compile(g["国外默认"]["filter"])
        ph = list(emit_stash.placeholders(m).values())
        print("     Stash 国外默认的筛选选中的占位节点：", [x for x in ph if rx.search(x)], "；选中内置名：",
              [x for x in ("DIRECT", "REJECT", "REJECT-DROP", "direct") if rx.search(x)])
for rel in ("loon/loon-simple.conf", "quantumultx/quantumultx-simple.conf"):
    t = read(OUT, rel)
    sec = sections(t)
    key = "Proxy Group" if rel.startswith("loon") else "policy"
    lines = sec[key]
    jp = [ln for ln in lines if ln.startswith(("日本 =", "static=日本,"))][0]
    fd = [ln for ln in lines if ln.startswith(("国外默认 =", "static=国外默认,"))][0]
    print(f"   {rel}：{len(lines)} 个组；[Remote Filter] {len(sec.get('Remote Filter', []))} 条")
    print("     日本：", re.sub(r"(server-tag-regex=)[^,]*", r"\1<宽 jp>", jp)[:120])
    print("     国外默认：", re.sub(r"(server-tag-regex=)[^,]*", r"\1<全部节点>", fd)[:160])
    print("     结构检查：", verify.check_loon(t) if rel.startswith("loon") else verify.check_qx(t))
for rel in ("sing-box/sing-box-simple-1.14.json",):
    c = json.loads(read(OUT, rel))
    ob = {o["tag"]: o for o in c["outbounds"]}
    sel = [o for o in c["outbounds"] if o["type"] in ("selector", "urltest")]
    print(f"   {rel}（模板，没有节点）：{len(sel)} 个组；日本 = {ob['日本']['outbounds']} 默认 {ob['日本'].get('default')}；"
          f"国外默认 = {ob['国外默认']['outbounds']} 默认 {ob['国外默认'].get('default')}；日本·自动 = {ob['日本·自动']['outbounds']}")

# 4. sing-box 带样例节点
with open(os.path.join(P, "tests", "node_samples.yaml"), encoding="utf-8") as f:
    samples = yaml.safe_load(f)["proxies"]
conv, report, renamed = nodeconv.convert(samples, emit_singbox.reserved_tags(m))
for variant in ("1.14", "1.12"):
    t = emit_singbox.build(m, plan, variant, conv, renamed, layout="simple")
    os.makedirs(os.path.join(P, "out-private"), exist_ok=True)
    with open(os.path.join(P, "out-private", f"sing-box-simple-{variant}.json"), "w", encoding="utf-8") as f:
        f.write(t)
    c = json.loads(t)
    ob = {o["tag"]: o for o in c["outbounds"]}
    print(f"4. 样例节点 sing-box 简易版 {variant}：结构检查 {verify.check_singbox(t)}")
print("   日本 =", ob["日本"]["outbounds"], "默认", ob["日本"].get("default"))
print("   国外默认 =", ob["国外默认"]["outbounds"], "默认", ob["国外默认"].get("default"))
print("   提示行“剩余流量：100GB”进了哪些组：", [k for k, o in ob.items() if "剩余流量：100GB" in (o.get("outbounds") or [])])

# 5. 路由：模拟器在简易版和完整版上逐个用例相同（样本数据）
FIX = yaml.safe_load(read(P, "tests/fixtures.yaml"))
CASES = yaml.safe_load(read(P, "tests/cases.yaml"))
base = m.strict["publish_base"]
files = {rel: read(OUT, rel) for rel in ["loon/rules/cn-domains.list", "quantumultx/rules/cn-domains.list",
                                          "quantumultx/rules/cn-domains-max.list", "quantumultx/rules/domain-fallback.list"]}
emulate.register_own_lists(base, {base + rel: t for rel, t in files.items()})
fx = emulate.Fixtures(FIX)
parse = {"loon": (emulate.parse_loon, emulate.loon_route), "quantumultx": (emulate.parse_qx, emulate.qx_route),
         "mihomo": (emulate.parse_mihomo, emulate.mihomo_route), "sing-box": (emulate.parse_singbox, emulate.singbox_route),
         "stash": (emulate.parse_stash, emulate.stash_route)}
bad = 0
for s_rel, f_rel in PAIRS.items():
    fam = s_rel.split("/")[0]
    pr, rt = parse[fam]
    cs, cf = pr(read(OUT, s_rel)), pr(read(OUT, f_rel))
    for case in CASES["cases"]:
        conn = emulate.Conn(host=case.get("host"), ip=case.get("ip"))
        if rt(cs, conn, fx) != rt(cf, conn, fx):
            bad += 1
print(f"5. 模拟器：{len(PAIRS)} 对 × {len(CASES['cases'])} 个用例，简易版与完整版结果不同的：{bad}")

# 6. 写盘前的结构检查：简易版的 Loon / QX / Stash 现在会被检查（仓库里的 verify 会按完整文件名跳过它们）
own = verify.own_files(m, {rel: read(OUT, rel) for rel in man["outputs"]})
probs = verify.check_outputs({rel: read(OUT, rel) for rel in PAIRS}, own)
print("6. 原型 verify 对十份简易版：", probs or "没有问题")
