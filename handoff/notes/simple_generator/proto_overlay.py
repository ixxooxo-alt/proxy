"""原型续：带本地补充（tests/local_overlay_sample.yaml）的词表上，全部节点正则 = 宽的并集；随机名字也比。只读。"""
import os, random, re, sys
ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True
import yaml
from generator import regions as R
from proto_all_nodes import compose_all_nodes  # noqa: E402  (会先跑一遍公开词表的输出)

with open(os.path.join(ROOT, "source", "regions.yaml"), encoding="utf-8") as f:
    data = yaml.safe_load(f)
with open(os.path.join(ROOT, "tests", "local_overlay_sample.yaml"), encoding="utf-8") as f:
    overlay = yaml.safe_load(f)
for label, local in (("公开词表", None), ("带本地补充", overlay["node_names"])):
    spec, errors = R.parse(yaml.safe_load(yaml.safe_dump(data)), local)
    assert not errors, errors
    loose, _ = R.compose_all(spec)
    loose = {k: re.compile(v) for k, v in loose.items()}
    allrx = compose_all_nodes(spec)
    R.check_composed(allrx)
    allc = re.compile(allrx)
    names = [e["name"] for e in overlay["expect"]] + list(spec.assign)
    rnd = random.Random(20261021)
    words = [x for w in spec.regions + [spec.other] for x in w.words + w.latin + [R.flag(c) for c in w.flags]]
    info = spec.info_words + spec.info_colon + spec.info_latin + spec.info_always[:2]
    tags = ["01", "|", "-", " ", "：", ":", "Premium", "流量", "到期", "官网", "x1.5", "[IPLC]"]
    for _ in range(20000):
        parts = [rnd.choice(words if rnd.random() < 0.4 else info if rnd.random() < 0.3 else tags) for _ in range(rnd.randint(1, 5))]
        names.append(rnd.choice(["", " ", "-"]).join(parts).strip() or "x")
    bad = [n for n in names if bool(allc.search(n)) != any(r.search(n) for r in loose.values())]
    print(label, "：", len(allrx.encode()), "字节；", len(names), "个名字里不一致", len(bad), bad[:5])
    if local:
        print("  指定 none 的“测试 节点”被选中：", bool(allc.search("测试 节点")), "；指定 other 的“日本 99”被选中：", bool(allc.search("日本 99")))
