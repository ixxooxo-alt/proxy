"""把 events.jsonl 整理成相对时间线。用法：python3 -I summarize.py <run目录> [--probes]"""
import json
import sys

run = sys.argv[1]
show_probes = "--probes" in sys.argv
ev = [json.loads(x) for x in open(run + "/events.jsonl")]
t0 = next(e["t0"] for e in ev if e.get("kind") == "start")
ev.sort(key=lambda e: e["t"])
last_req = None
streak = []


def flush():
    global streak
    if streak:
        a, b = streak[0], streak[-1]
        desc = f"{'OK via ' + str(a.get('node')) if a['ok'] else 'FAIL'}"
        print(f"  {a['t'] - t0:7.1f}–{b['t'] - t0:7.1f}s  req x{len(streak)}  {desc}"
              + ("" if a["ok"] else f"  (e.g. {a.get('err') or a.get('head')!r} dur={a['dur']})"))
    streak = []


for e in ev:
    k = e.get("kind")
    rel = e["t"] - t0
    if k == "req":
        key = (e["ok"], e.get("node"))
        if streak and (streak[-1]["ok"], streak[-1].get("node")) != key:
            flush()
        streak.append(e)
        continue
    if k in ("stream_start", "stream_gap", "stream_end", "groupdelay_result", "stream_open"):
        flush()
        print(f"  {rel:7.1f}s  {k} " + json.dumps({x: y for x, y in e.items() if x not in ('t', 'kind')}))
        continue
    if k in ("now", "action", "set", "select_result") or (show_probes and k == "probe") or k in ("socks_hang",):
        flush()
        if k == "probe":
            print(f"  {rel:7.1f}s  probe via {e['node']}")
        elif k == "now":
            print(f"  {rel:7.1f}s  NOW {e['group']} = {e['now']}")
        elif k == "action":
            print(f"  {rel:7.1f}s  ACTION {e['action']}")
        elif k == "set":
            print(f"  {rel:7.1f}s  lab: {e['node']} {e['old']} -> {e['state']}")
        elif k == "socks_hang":
            pass
        else:
            print(f"  {rel:7.1f}s  {k} {e.get('resp', '')!r}")
flush()
