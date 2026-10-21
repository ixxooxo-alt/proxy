"""全部节点正则在 ICU 上：和 Python 逐个名字比，再和手写期望（不是提示行就该收）比；顺带量长名字。只读。"""
import os, re, sys, time
P = sys.argv[1]
sys.path.insert(0, P); sys.path.insert(0, os.path.join(P, "tools")); sys.dont_write_bytecode = True
from check_icu import ICURegex, _load_icu, sample_names, overlay_regexes, overlay_sample, stress_names  # noqa
from generator import regions
from generator.model import load
from generator.emit_stash import exclude_builtins
lib, suf, where = _load_icu()
if lib is None:
    sys.exit("没有 ICU：" + where)
m = load(P, include_local=False)
names, expect = sample_names()
rx = m.node_regex_any()
icu, py = ICURegex(lib, suf, rx), re.compile(rx)
t = time.perf_counter()
diff = [n for n in names if icu.search(n) != bool(py.search(n))]
dt = (time.perf_counter() - t) / len(names) * 1e6
wrong = [n for n, g in expect.items() if icu.search(n) != bool(g)]
print(f"ICU {where}：全部节点正则 {len(rx.encode())} 字节 × {len(names)} 个名字：ICU 与 Python 不一致 {len(diff)}；与手写期望不符 {len(wrong)}；平均 {dt:.0f} 微秒 / 次")
# 长名字（回溯失控）：拿 check_icu 的长名字生成器
worst = 0.0
for length in (200, 600):
    for n in stress_names(m.region_spec, length)[:300]:
        t = time.perf_counter(); a = icu.search(n); b = bool(py.search(n)); d = time.perf_counter() - t
        worst = max(worst, d)
        assert a == b, n
print(f"长名字（200 / 600 字符各 300 个）：ICU 与 Python 一致，单次最长 {worst*1000:.1f} 毫秒")
