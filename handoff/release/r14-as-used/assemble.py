"""变异运行的日志汇总（r14 用的；照 r13-as-used/assemble.py 改的），写出 mut-result.json、mut-lines.txt 到日志目录。
用法（在工程根目录）：python3 handoff/release/r14-as-used/assemble.py <日志目录>
日志目录里要有 segments.json：[{"start": "mut-start-<段>.txt", "code_state": "code-state-<段>.txt", "logs": ["mut-A-<段>.log", "mut-B-<段>.log", "mut-C-<段>.log"]}, …]
（文件都是 handoff/release/run_mutations.sh 写的；r14 用 MUT_BATCHES=3 分了三批）。只有最后一段要求每份日志都有“合计”行（前面的段是被打断的）。
没跑完、有没被发现的、代码在运行期间（或各段之间）变过，都会直接报错。"""
import collections, datetime, json, os, re, subprocess, sys

D = os.path.abspath(sys.argv[1])
N = 117
segs = json.load(open(os.path.join(D, "segments.json"), encoding="utf-8"))
state = subprocess.run(["bash", "handoff/release/code_state.sh"], capture_output=True, text=True, check=True).stdout.strip()
for seg in segs:
    at_start = open(os.path.join(D, seg["code_state"]), encoding="utf-8").read().strip()
    assert state == at_start, ("代码在定稿之后变过", state, at_start)

num = lambda l: int(re.match(r"\[[^\]]+\] M(\d+) ", l).group(1))
utc = lambda t: datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
lines, seg_info = [], []
for i, seg in enumerate(segs):
    start = open(os.path.join(D, seg["start"]), encoding="utf-8").read().strip()
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", start), start
    got_seg = []
    for name in seg["logs"]:
        p = os.path.join(D, name)
        text = open(p, encoding="utf-8").read()
        got = [l for l in text.splitlines() if re.match(r"\[(发现|未发现|超时)\] M\d+ ", l)]
        other = [l for l in text.splitlines() if l.strip() and not l.startswith("[") and not l.startswith("合计")]
        assert not other, (p, other[:5])           # 例如弃用警告：r13 改掉了，日志里不应再有
        if i == len(segs) - 1:
            m = re.search(r"^合计 (\d+)/(\d+) 被发现", text, re.M)
            assert m and m.group(1) == m.group(2) == str(len(got)), f"{p} 还没跑完或有没被发现的"
        got_seg += got
    end = max(os.path.getmtime(os.path.join(D, name)) for name in seg["logs"])
    seg_info.append({"start": start, "end": utc(end), "ids": sorted(num(l) for l in got_seg)})
    lines += got_seg
lines.sort(key=num)
assert [num(l) for l in lines] == list(range(1, N + 1)), [num(l) for l in lines]
bad = [l for l in lines if not l.startswith("[发现]")]
assert not bad, bad
ran = collections.Counter(re.search(r"Ran (\d+) tests?", l).group(1) for l in lines)
full = max(ran, key=lambda k: int(k))
only = [l for l in lines if "只跑了" in l]
assert len(only) == 1 and num(only[0]) == 45, only
partial = {}
for l in lines:
    k = re.search(r"Ran (\d+) tests?", l).group(1)
    if k != full and "只跑了" not in l:
        partial.setdefault(k, []).append(f"M{num(l)}")
not_seen = [f"M{num(l)}" for l in lines if "未见预期信息" in l]
man = json.load(open("dist/manifest.json", encoding="utf-8"))
pyv = subprocess.run(["python3", "--version"], capture_output=True, text=True).stdout.strip()
import yaml
# 只靠“记录对应现在的配置”那两项（规则与 DNS 的摘要、拨号摘要）发现的有没有。r12 有两类（M91、M92），r13 补了静态断言以后应当没有
FRESH = {"routing": "test_recorded_official_runs_used_the_current_rules", "dial": "test_recorded_dial_runs_used_the_current_dial_config"}
with_it = {k: [] for k in FRESH}
solo = []
for l in lines:
    m = re.search(r"失败项 \[(.*?)\]", l)
    items = re.findall(r"'([^']+)'", m.group(1)) if m else []
    for k, t in FRESH.items():
        if any(t in x for x in items):
            with_it[k].append(f"M{num(l)}")
    if items and all(any(t in x for t in FRESH.values()) for x in items):
        solo.append(f"M{num(l)}")
result = {"segments": seg_info, "full": full, "partial": partial, "not_seen": not_seen, "n": N,
          "digest": man["source_sha256"], "python": pyv, "pyyaml": yaml.__version__, "state": state,
          "fresh": {"with": with_it, "solo": solo}}
with open(os.path.join(D, "mut-result.json"), "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=1)
with open(os.path.join(D, "mut-lines.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print(json.dumps(result, ensure_ascii=False, indent=1))
for k, v in partial.items():
    for name in v:
        l = next(x for x in lines if x.startswith(f"[发现] {name} "))
        print("部分运行：", l[:300])
for name in not_seen:
    l = next(x for x in lines if x.startswith(f"[发现] {name} "))
    print("未见预期信息：", l[:300])
for name in ["M91", "M92", "M99", "M100", "M101", "M102", "M103", "M104", "M105", "M108", "M109", "M110", "M116", "M117"]:
    l = next(x for x in lines if x.startswith(f"[发现] {name} "))
    print(l[:600])
