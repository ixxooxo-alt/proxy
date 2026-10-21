"""原型（只读分析用，不改仓库）：拼一条“全部节点（去掉提示行）”的筛选正则，量大小，并和“宽的那套取并集”逐个对比。
运行：PYTHONDONTWRITEBYTECODE=1 python3 -B 本文件 /home/user/proxy
"""
import json
import os
import re
import sys

ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
sys.dont_write_bytecode = True

import yaml  # noqa: E402

from generator import regions as R  # noqa: E402
from generator.model import load  # noqa: E402
from generator import emit_stash  # noqa: E402


def compose_all_nodes(spec):
    c = R._Composer(spec)
    info = c.info_common()
    weak = c.weak()
    ids, oid = spec.ids, spec.other.id
    body = info
    if weak is not None:
        sign = R._alt([c.txt(ids + [oid]), c.any_flag()])
        body += "(?:" + R._pos(sign) + "|" + R._neg(weak) + ")"
    # 和 wrap() 同样处理 local.yaml 的 assign：指定了地区（含其他地区）的照收，指定 none 的不收
    names = sorted(spec.assign)
    core = body + ".*$"
    if not names:
        return "(?i)^" + core
    excl = "(?!(?:" + "|".join(R.lit(n) for n in names) + ")$)"
    keep = [n for n in names if spec.assign[n] != R.NONE]
    if keep:
        return "(?i)^(?:(?:" + "|".join(R.lit(n) for n in keep) + ")$|" + excl + core + ")"
    return "(?i)^" + excl + core


m = load(ROOT, include_local=False)
spec = m.region_spec
loose = {k: re.compile(v) for k, v in m.node_regexes().items()}
strict = {k: re.compile(v) for k, v in m.node_regexes_strict().items()}
all_rx_text = compose_all_nodes(spec)
R.check_composed(all_rx_text)
all_rx = re.compile(all_rx_text)
print("全部节点正则：", len(all_rx_text.encode("utf-8")), "字节；含禁止字符：",
      [b for b in R.FORBIDDEN_IN_REGEX if b in all_rx_text])
print("宽的各条字节数：", {k: len(v.encode()) for k, v in m.node_regexes().items()})

# 样本：tests/node_names.yaml + CLDR / 时区城市名
with open(os.path.join(ROOT, "tests", "node_names.yaml"), encoding="utf-8") as f:
    nn = yaml.safe_load(f)
names = [n for lst in nn["expect"].values() for n in lst]
names += [x["name"] for key in ("manual_only", "known_limits", "known_auto_limits") for x in nn.get(key, [])]
names += list(nn.get("info", []) or [])
with open(os.path.join(ROOT, "tests", "data", "cldr_tz_names.json"), encoding="utf-8") as f:
    ref = json.load(f)
for c_ in ref["regions"]:
    fl = R.flag(c_["code"])
    names += [f'{fl} {c_["zh_hans"]} 01', f'{c_["zh_hans"]} 01', f'{c_["zh_hant"]} 01', f'{c_["en"]} 01', f'{c_["code"]}-01']
names += [z["city"] + " 01" for z in ref["tz_cities"]]
names = list(dict.fromkeys(names))
cl = R.Classifier(spec)
diff = []
for n in names:
    union = any(r.search(n) for r in loose.values())
    one = bool(all_rx.search(n))
    info = cl.is_info(n) is not None
    if union != one or one == info:
        diff.append((n, union, one, info))
print("样本", len(names), "个；全部节点正则与“宽的并集”/逐步判断不一致：", len(diff), diff[:10])
print("node_names.yaml 里 expect 键：", list(nn["expect"].keys()), "；其他键：", [k for k in nn if k != "expect"])

# 成员组名能不能被筛选选中（Stash 的筛选会不会也作用在写明的成员上，文档没写）
regions_ = [r["name"] for r in m.regions]
auto_names = [r + "·自动" for r in regions_]
print("各地区“X·自动”被本地区宽的筛选选中：",
      {r["name"]: bool(loose[r["id"]].search(r["name"] + "·自动")) for r in m.regions})
print("各地区“X·自动”被本地区宽的筛选（Stash 前缀版）选中：",
      {r["name"]: bool(re.search(emit_stash.exclude_builtins(m.node_regexes()[r["id"]]), r["name"] + "·自动")) for r in m.regions})
members_fd = ["日本", "香港", "韩国", "台湾", "新加坡", "美国", "其他地区"]
print("国外默认的七个成员被全部节点正则选中：", {x: bool(all_rx.search(x)) for x in members_fd})
ph = emit_stash.placeholders(m)
print("占位节点被全部节点正则选中：", {v: bool(all_rx.search(v)) for v in ph.values()})
groups = [g.name for g in m.groups]
print("业务组名里被全部节点正则选中的个数：", sum(1 for g in groups if all_rx.search(g)), "/", len(groups))
print("业务组名里被“其他地区”筛选选中的个数（现行标准版，若 include-all 也收策略组就会混进去）：",
      sum(1 for g in groups if loose["other"].search(g)), "/", len(groups))
for b in ("DIRECT", "REJECT", "REJECT-DROP", "direct"):
    print("内置名", b, "被全部节点正则选中：", bool(all_rx.search(b)))

# 提示行的样本：info 一节
info_samples = [n for n in names if cl.is_info(n)]
print("样本里的提示行", len(info_samples), "个，例如：", info_samples[:8])
