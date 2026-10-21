"""简易版能不能共用完整版的官方内核记录：规则段 + DNS 段的摘要、拨号核对用的部分是否相同。只读。"""
import json, os, sys
P = sys.argv[1]
sys.path.insert(0, P); sys.path.insert(0, os.path.join(P, "tools")); sys.dont_write_bytecode = True
import real_data as rd
from generator import emit_singbox, nodes as nodeconv
from generator.model import build_plan, load
def read(rel):
    with open(os.path.join(P, "out", rel), encoding="utf-8") as f:
        return f.read()
for s, f in (("mihomo/mihomo-simple-core.yaml", "mihomo/mihomo-core.yaml"), ("mihomo/mihomo-simple-profile.yaml", "mihomo/mihomo-profile.yaml"),
             ("sing-box/sing-box-simple-1.14.json", "sing-box/sing-box-1.14.json"), ("sing-box/sing-box-simple-1.12.json", "sing-box/sing-box-1.12.json")):
    same = rd.routing_digest(f, read(s)) == rd.routing_digest(f, read(f))
    print(f"routing_digest {s} == {f}：{same}")
print("mihomo_dial_base 简易 core == 完整 core：", rd.mihomo_dial_base(read("mihomo/mihomo-simple-core.yaml")) == rd.mihomo_dial_base(read("mihomo/mihomo-core.yaml")))
m = load(P, include_local=False); plan = build_plan(m)
import yaml
cases = yaml.safe_load(open(os.path.join(P, "tests", "cases.yaml"), encoding="utf-8"))["singbox_dial"]
proxies = rd.dial_proxies(cases, 1)
conv, report, renamed = nodeconv.convert(proxies, emit_singbox.reserved_tags(m))
for v in ("1.14", "1.12"):
    a = json.loads(emit_singbox.build(m, plan, v, nodes=conv, renamed=renamed))
    b = json.loads(emit_singbox.build(m, plan, v, nodes=conv, renamed=renamed, layout="simple"))
    print(f"sing-box {v} dial_digest 简易 == 完整：", rd.dial_digest("singbox", a) == rd.dial_digest("singbox", b))
snap = rd.load_snapshot()
print("快照里 mihomo 记录的 routing_sha256 == 简易 core 的：", snap["official"]["mihomo"]["routing_sha256"] == rd.routing_digest("mihomo/mihomo-core.yaml", read("mihomo/mihomo-simple-core.yaml")))
