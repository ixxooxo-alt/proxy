#!/usr/bin/env python3
"""把 e2_timing.py 的 driver.jsonl 汇总成几项数字。用法：python3 -I summarize.py <运行目录>..."""
import json
import os
import sys


def checks(evs, node=None):
    """源站收到的健康检查（HEAD /generate_204），按时间聚成“一次检查”（相隔 2 秒以内算同一次）。"""
    ts = sorted(e["t"] for e in evs if e["ev"] == "lab_probe" and (node is None or e.get("node") == node))
    out = []
    for t in ts:
        if not out or t - out[-1][-1] > 2.0:
            out.append([t])
        else:
            out[-1].append(t)
    return [round(c[0], 1) for c in out]


def summarize(d):
    evs = [json.loads(x) for x in open(os.path.join(d, "driver.jsonl"), encoding="utf-8")]
    p = json.load(open(os.path.join(d, "params.json")))
    fail = next((e["t"] for e in evs if e["ev"] == "fail"), None)
    s = {"run": os.path.basename(d), "params": p, "t_fail": fail}
    s["checks_at"] = checks(evs)
    nows = [e for e in evs if e["ev"] == "now"]
    s["now_changes"] = [(e["t"], e["auto"], e["jp"]) for e in nows]
    sw = next((e for e in nows if fail is not None and e["t"] >= fail and e["auto"] != "日本 01"), None)
    s["auto_left_n1_after_s"] = round(sw["t"] - fail, 1) if sw else None
    s["auto_now_after"] = sw["auto"] if sw else None
    reqs = [e for e in evs if e["ev"] == "req"]
    after = sorted([e for e in reqs if fail is not None and e["t"] - e["secs"] >= fail - 0.01], key=lambda e: e["t"] - e["secs"])
    bad, first_ok = [], None
    for e in after:
        if e["res"].startswith("node=") and e["res"] != "node=n1":
            first_ok = e
            break
        bad.append(e)
    s["reqs_after_fail_until_first_ok"] = len(bad)
    s["bad_results"] = sorted({e["res"] for e in bad})
    s["first_ok_other"] = ({"start_after_s": round(first_ok["t"] - first_ok["secs"] - fail, 1),
                            "done_after_s": round(first_ok["t"] - fail, 1), "res": first_ok["res"],
                            "secs": first_ok["secs"]} if first_ok else None)
    still_n1 = [e for e in after if e["res"] == "node=n1"]
    s["ok_via_n1_after_fail"] = len(still_n1)
    if p.get("traffic") == "idle":
        on = next((e["t"] for e in evs if e["ev"] == "traffic_on"), None)
        s["traffic_on_at"] = on
        s["checks_during_idle"] = [c for c in s["checks_at"] if fail - p["idle_before"] < c < (on or 1e9)]
        s["first_reqs_after_on"] = [(round(e["t"] - e["secs"] - on, 1), e["res"], e["secs"]) for e in after if on and e["t"] - e["secs"] >= on][:6]
    s["last_req"] = reqs[-1]["res"] if reqs else None
    return s


if __name__ == "__main__":
    for d in sys.argv[1:]:
        s = summarize(d)
        json.dump(s, open(os.path.join(d, "summary.json"), "w"), ensure_ascii=False, indent=1)
        print(json.dumps(s, ensure_ascii=False))
