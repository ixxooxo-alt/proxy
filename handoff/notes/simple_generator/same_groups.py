"""简易版里和完整版同名的组（业务组 42 个、PayPal·美国固定、其他地区、X·自动）写法是否和完整版逐字相同。只读。"""
import json, os, re, sys
OUT = sys.argv[1]
def read(rel):
    with open(os.path.join(OUT, rel), encoding="utf-8") as f:
        return f.read()
def ini_groups(text, sec):
    out, cur = {}, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        m = re.match(r"^\[(.+)\]$", line)
        if m:
            cur = m.group(1); continue
        if cur == sec:
            name = line.split(" = ", 1)[0] if sec == "Proxy Group" else line.split("=", 1)[1].split(",", 1)[0].strip()
            out[name] = line
    return out
import yaml
pairs = [("loon/loon-simple.conf", "loon/loon.conf", "Proxy Group"), ("quantumultx/quantumultx-simple.conf", "quantumultx/quantumultx.conf", "policy"),
         ("mihomo/mihomo-simple-core.yaml", "mihomo/mihomo-core.yaml", None), ("stash/stash-simple.yaml", "stash/stash.yaml", None),
         ("sing-box/sing-box-simple-1.14.json", "sing-box/sing-box-1.14.json", None)]
for s, f, sec in pairs:
    if sec:
        a, b = ini_groups(read(s), sec), ini_groups(read(f), sec)
    elif s.endswith(".yaml"):
        a = {g["name"]: g for g in yaml.safe_load(read(s))["proxy-groups"]}
        b = {g["name"]: g for g in yaml.safe_load(read(f))["proxy-groups"]}
    else:
        a = {o["tag"]: o for o in json.loads(read(s))["outbounds"] if o["type"] in ("selector", "urltest")}
        b = {o["tag"]: o for o in json.loads(read(f))["outbounds"] if o["type"] in ("selector", "urltest")}
    common = [n for n in a if n in b]
    diff = [n for n in common if a[n] != b[n]]
    print(f"{s}：同名的组 {len(common)} 个，写法不同的 {diff}；只在简易版里的 {[n for n in a if n not in b]}")
