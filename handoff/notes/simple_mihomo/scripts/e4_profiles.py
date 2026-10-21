#!/usr/bin/env python3
"""E4：把仓库现有的两份 mihomo 配置（core / profile）按方案 ③ 只换 proxy-groups，官方内核 -t 检查；
看两份之间、简易版和完整版之间还差什么。用法：python3 -I e4_profiles.py <运行目录>"""
import difflib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh  # noqa: E402
import simple  # noqa: E402

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
ALLF = simple.all_nodes_filter_compact()
res = {}
texts = {}
for flavor in ("core", "profile"):
    conf = mh.dist(flavor)
    full_groups = conf["proxy-groups"]
    conf["proxy-groups"] = simple.simple_groups(conf, ALLF)
    home = os.path.join(OUT, flavor)
    os.makedirs(home, exist_ok=True)
    mh.copy_geodata(home)
    path = os.path.join(home, f"mihomo-{flavor}-simple.yaml")
    mh.write_yaml(path, conf)
    rc, out = mh.check(home, path)
    gs = conf["proxy-groups"]
    res[flavor] = {
        "check_rc": rc, "check_last": out.splitlines()[-1][:200],
        "groups_total": len(gs), "groups_hidden": sum(1 for g in gs if g.get("hidden")),
        "groups_visible": sum(1 for g in gs if not g.get("hidden")),
        "full_total": len(full_groups), "full_hidden": sum(1 for g in full_groups if g.get("hidden")),
        "no_icon": [g["name"] for g in gs if "icon" not in g],
        "size_bytes": os.path.getsize(path),
        "auto_groups_interval_lazy": sorted({(g.get("interval"), g.get("lazy")) for g in gs if g["type"] == "url-test"}),
        "provider_hc": conf["proxy-providers"]["订阅1"]["health-check"],
    }
    texts[flavor] = open(path, encoding="utf-8").read().splitlines()
    print(flavor, json.dumps(res[flavor], ensure_ascii=False))
diff = [ln for ln in difflib.unified_diff(texts["core"], texts["profile"], "core", "profile", n=0, lineterm="")]
res["core_vs_profile_diff"] = diff
print("core 与 profile 的差别：")
print("\n".join(diff))
# 完整版和简易版：除了 proxy-groups 还差什么
for flavor in ("core", "profile"):
    full = mh.dist(flavor)
    simp = mh.dist(flavor)
    simp["proxy-groups"] = simple.simple_groups(simp, ALLF)
    res[f"{flavor}_keys_differ"] = sorted(k for k in set(full) | set(simp) if full.get(k) != simp.get(k))
    print(flavor, "完整版与简易版不同的顶层段：", res[f"{flavor}_keys_differ"])
json.dump(res, open(os.path.join(OUT, "report.json"), "w"), ensure_ascii=False, indent=1)
