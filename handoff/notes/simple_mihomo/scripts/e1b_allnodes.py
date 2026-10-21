#!/usr/bin/env python3
"""E1b：“全部节点”的几种筛选写法，用 tests/node_names.yaml 的全部样本名（加几个占位节点名）在官方内核上比：
  A  只用“现有 filter 末尾那段”（提示行规则第 1、2 条）+ 排除占位节点
  B  七条宽筛选（六个地区的“手动”+“其他地区”）的并集 + 排除占位节点（一条正则）
  C  同 B，但用 mihomo 的反引号多条筛选（生成器禁止反引号；只作对照）
  D  紧凑写法：提示行规则第 1、2 条 + 第 3 条的否定（名字里有任何地区的词或国旗、其他国家的词、任何国旗，或者没有提示行常用词）
对照真值 = 七个宽筛选组（照抄 dist 的正则）成员的并集，再去掉占位节点。
节点都指向本机一个没人听的端口，不做健康检查。用法：python3 -I e1b_allnodes.py <运行目录> <base_port>"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402
import yaml  # noqa: E402

OUT, BASE = sys.argv[1], int(sys.argv[2])
os.makedirs(OUT, exist_ok=True)
API = BASE + 8
F = mh.filters()
INFO = mh.info_common()
PH = r"(?!.*·无可用节点$)"

sys.dont_write_bytecode = True
sys.path.insert(0, mh.REPO)
from generator import model as gm, regions as gr  # noqa: E402

m = gm.load(mh.REPO, include_local=False)
comp = gr._Composer(m.region_spec)
ids = m.region_spec.ids
oid = m.region_spec.other.id
mention = gr._alt([comp.txt(ids), comp.aflag(ids)])
weak = comp.weak()
not_cond3 = "(?:" + gr._pos(mention) + "|" + gr._pos(comp.txt([oid])) + "|" + gr._pos(comp.any_flag()) + "|" + gr._neg(weak) + ")"


def strip(rx):
    assert rx.startswith("(?i)^") and rx.endswith(".*$")
    return rx[5:-3]


LOOSE = {r: F["wide"][r] for r in mh.REGIONS}
LOOSE["其他地区"] = F["other"]
CAND = {
    "A": "(?i)^" + PH + INFO + ".*$",
    "B": "(?i)^" + PH + "(?:" + "|".join(strip(rx) for rx in LOOSE.values()) + ").*$",
    "C": "`".join(LOOSE.values()),
    "D": "(?i)^" + PH + INFO + not_cond3 + ".*$",
}
print("长度（字符）：", {k: len(v) for k, v in CAND.items()}, "；单条宽筛选：", {k: len(v) for k, v in LOOSE.items()})

samples = yaml.safe_load(open(os.path.join(mh.REPO, "tests", "node_names.yaml"), encoding="utf-8"))
names = []
for k, v in samples["expect"].items():
    names += v
names += [x["name"] for x in samples["manual_only"]]
names += [x["name"] for x in samples["known_limits"]] + [x["name"] for x in samples.get("known_auto_limits", [])]
names += [f"{r}·无可用节点" for r in mh.REGIONS + ["其他地区"]] + ["官网 example.com", "请更新订阅", "DIRECT"]
seen, uniq = set(), []
for n in names:
    if n not in seen:
        seen.add(n)
        uniq.append(n)
print("样本名：", len(uniq))
mh.write_yaml(os.path.join(OUT, "sub1.yaml"),
              {"proxies": [{"name": n, "type": "socks5", "server": "127.0.0.1", "port": 9, "udp": False} for n in uniq]})
groups = [{"name": f"宽-{k}", "type": "select", "include-all-providers": True, "filter": v, "empty-fallback": "REJECT"}
          for k, v in LOOSE.items()]
groups += [{"name": f"全部-{k}", "type": "select", "include-all-providers": True, "filter": v, "empty-fallback": "REJECT",
            **({"exclude-filter": "·无可用节点$"} if k == "C" else {})} for k, v in CAND.items()]
conf = {"allow-lan": False, "bind-address": "127.0.0.1", "external-controller": f"127.0.0.1:{API}", "mode": "rule",
        "log-level": "warning", "find-process-mode": "off", "profile": {"store-selected": False},
        "proxy-providers": {"订阅1": {"type": "file", "path": "./sub1.yaml", "health-check": {"enable": False}}},
        "proxy-groups": groups, "rules": ["MATCH,DIRECT"]}
cfg = os.path.join(OUT, "config.yaml")
mh.write_yaml(cfg, conf)
rc, out = mh.check(OUT, cfg)
print("mihomo -t：", rc, out.splitlines()[-1][:160])
mi = mh.Mihomo(OUT, cfg, API)
try:
    time.sleep(1.5)
    got = {g["name"]: mi.group(g["name"])["all"] for g in groups}
finally:
    mi.stop()
union = set()
for k in LOOSE:
    union |= set(got[f"宽-{k}"]) - {"REJECT"}
truth = {n for n in union if not n.endswith("·无可用节点")}
res = {"sample_count": len(uniq), "truth_count": len(truth), "lengths": {k: len(v) for k, v in CAND.items()}}
info_names = set(samples["expect"]["info"])
for k in CAND:
    s = set(got[f"全部-{k}"]) - {"REJECT"}
    res[k] = {"count": len(s), "extra_vs_truth": sorted(s - truth), "missing_vs_truth": sorted(truth - s),
              "info_names_let_in": sorted(s & info_names),
              "order_first10": got[f"全部-{k}"][:10]}
    print(f"{k}: 成员 {len(s)}；比真值多 {len(s - truth)}：{sorted(s - truth)[:12]}；少 {len(truth - s)}：{sorted(truth - s)[:8]}")
print("真值里有没有提示行样本：", sorted(truth & info_names))
print("真值里有没有 DIRECT：", "DIRECT" in truth)
json.dump(res, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)
with open(os.path.join(OUT, "candidates.json"), "w", encoding="utf-8") as f:
    json.dump(CAND, f, ensure_ascii=False, indent=1)
