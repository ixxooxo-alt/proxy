"""从仓库现有的 mihomo 配置（dist/mihomo/mihomo-{core,profile}.yaml，已展开锚点）按方案 ③ 换掉 proxy-groups。
其余段落（dns、rules、sniffer、proxy-providers……）原样保留。只在内存里改，写到调用者给的目录。"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402

REGIONS = mh.REGIONS


def all_nodes_filter_compact():
    """“全部节点”的紧凑写法（E1b 的 D）：提示行规则第 1、2 条 + 第 3 条的否定 + 排除占位节点。"""
    sys.dont_write_bytecode = True
    if mh.REPO not in sys.path:
        sys.path.insert(0, mh.REPO)
    from generator import model as gm, regions as gr  # noqa: E402
    m = gm.load(mh.REPO, include_local=False)
    comp = gr._Composer(m.region_spec)
    ids, oid = m.region_spec.ids, m.region_spec.other.id
    mention = gr._alt([comp.txt(ids), comp.aflag(ids)])
    not_cond3 = ("(?:" + gr._pos(mention) + "|" + gr._pos(comp.txt([oid])) + "|" + gr._pos(comp.any_flag()) + "|"
                 + gr._neg(comp.weak()) + ")")
    return "(?i)^(?!.*·无可用节点$)" + comp.info_common() + not_cond3 + ".*$"


def simple_groups(conf, all_filter, all_name="全部节点"):
    old = {g["name"]: g for g in conf["proxy-groups"]}
    out = []
    for g in conf["proxy-groups"]:
        n = g["name"]
        if n in REGIONS:
            wide = old[f"{n}·手动"]["filter"]
            d = {"name": n, "type": "select", "proxies": [f"{n}·自动"], "include-all-providers": True,
                 "filter": wide, "empty-fallback": "REJECT"}
            if "icon" in g:
                d["icon"] = g["icon"]
            out.append(d)
        elif n == "其他地区":
            out.append(copy.deepcopy(g))
            out.append({"name": all_name, "type": "select", "include-all-providers": True, "filter": all_filter,
                        "empty-fallback": "REJECT"})
        elif any(n == f"{r}·{s}" for r in REGIONS for s in ("手动优先", "手动", "故障转移", "负载均衡")):
            continue
        else:
            d = copy.deepcopy(g)
            if n == "国外默认":
                d["proxies"] = REGIONS[1:2] + REGIONS[:1] + REGIONS[2:] + ["其他地区", all_name]
            out.append(d)
    return out
