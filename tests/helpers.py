import functools
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build  # noqa: E402
from generator import strict as strict_mod  # noqa: E402
from generator.model import build_plan, load  # noqa: E402
import emulate  # noqa: E402

# 测试里说的“客户端”指一份产物。标准版七份（2026-10-13 起含 Stash）；Loon / Quantumult X / Stash 另有严格版各一份
# （前两个 2026-10-06，Stash 2026-10-13）。
CLIENT_FILES = {
    "mihomo-profile": "mihomo/mihomo-profile.yaml",
    "mihomo-core": "mihomo/mihomo-core.yaml",
    "singbox-1.14": "sing-box/sing-box-1.14.json",
    "singbox-1.12": "sing-box/sing-box-1.12.json",
    "loon": "loon/loon.conf",
    "quantumultx": "quantumultx/quantumultx.conf",
    "loon-strict": "loon/loon-strict.conf",
    "quantumultx-strict": "quantumultx/quantumultx-strict.conf",
    # Stash（2026-10-13，r16）：标准版、严格版
    "stash": "stash/stash.yaml",
    "stash-strict": "stash/stash-strict.yaml",
}
# 简易版（2026-10-21，docs/10）：每一份完整版都有一份对应的简易版，客户端名在类名后面加 -simple。
# 规则和 DNS 与对应的完整版相同（mihomo、sing-box 的境外 DNS 和规则下载另走内部组），策略组不同。
# 下面这些集合都把简易版算进去：按规则判断的测试照样对简易版跑；只适用于完整版策略组的测试用 FULL_CLIENTS。
FULL_CLIENTS = tuple(CLIENT_FILES)
SIMPLE_FILES = {
    "mihomo-simple-profile": "mihomo/mihomo-simple-profile.yaml",
    "mihomo-simple-core": "mihomo/mihomo-simple-core.yaml",
    "singbox-simple-1.14": "sing-box/sing-box-simple-1.14.json",
    "singbox-simple-1.12": "sing-box/sing-box-simple-1.12.json",
    "loon-simple": "loon/loon-simple.conf",
    "quantumultx-simple": "quantumultx/quantumultx-simple.conf",
    "loon-simple-strict": "loon/loon-simple-strict.conf",
    "quantumultx-simple-strict": "quantumultx/quantumultx-simple-strict.conf",
    "stash-simple": "stash/stash-simple.yaml",
    "stash-simple-strict": "stash/stash-simple-strict.yaml",
}
CLIENT_FILES.update(SIMPLE_FILES)
SIMPLE_CLIENTS = tuple(SIMPLE_FILES)
FULL_OF = {c: c.replace("-simple", "", 1) for c in SIMPLE_CLIENTS}      # 简易版 → 对应的完整版
SIMPLE_OF = {v: k for k, v in FULL_OF.items()}                         # 完整版 → 对应的简易版
STRICT_CLIENTS = ("loon-strict", "quantumultx-strict", "stash-strict",
                  "loon-simple-strict", "quantumultx-simple-strict", "stash-simple-strict")
STANDARD_CLIENTS = tuple(c for c in CLIENT_FILES if c not in STRICT_CLIENTS)
STRICT_OF = {"loon": "loon-strict", "quantumultx": "quantumultx-strict", "stash": "stash-strict",   # 标准版 → 同一个 App 的严格版
             "loon-simple": "loon-simple-strict", "quantumultx-simple": "quantumultx-simple-strict",
             "stash-simple": "stash-simple-strict"}
LOON_CLIENTS = ("loon", "loon-strict", "loon-simple", "loon-simple-strict")
QX_CLIENTS = ("quantumultx", "quantumultx-strict", "quantumultx-simple", "quantumultx-simple-strict")
STASH_CLIENTS = ("stash", "stash-strict", "stash-simple", "stash-simple-strict")
# Loon / Quantumult X 的严格版：按这两端的文件格式（[Rule] / [Remote Rule]、filter_local / filter_remote）写的检查只管它们
LQ_STRICT_OF = {"loon": "loon-strict", "quantumultx": "quantumultx-strict",
                "loon-simple": "loon-simple-strict", "quantumultx-simple": "quantumultx-simple-strict"}


@functools.lru_cache(maxsize=1)
def model_and_plan():
    m = load(ROOT)
    return m, build_plan(m)


def simple_spec():
    """写盘前检查（generator/verify.py）核对简易版要用的名字。"""
    from generator import verify
    return verify.simple_spec(model_and_plan()[0])


@functools.lru_cache(maxsize=1)
def outputs():
    m, p = model_and_plan()
    files = build.render_public(m, p)
    # 严格版引用的自有远程规则文件：内容就是这次生成的产物，登记给模拟器，按真实内容判断
    base = m.strict["publish_base"]
    emulate.register_own_lists(base, {base + rel: files[rel] for rel in strict_mod.OWN_FILES})
    return files


def text(client: str) -> str:
    return outputs()[CLIENT_FILES[client]]


def family(client: str) -> str:
    """这份产物给哪一类客户端用：mihomo / singbox / loon / quantumultx / stash（严格版和标准版是同一类）。"""
    for fam in ("singbox", "mihomo", "loon", "quantumultx", "stash"):
        if client.startswith(fam):
            return fam
    raise KeyError(client)


def is_strict(client: str) -> bool:
    return client in STRICT_CLIENTS


def is_simple(client: str) -> bool:
    return client in FULL_OF


def full_of(client: str) -> str:
    """简易版 → 对应的完整版（loon-simple-strict → loon-strict）；完整版原样返回。"""
    return FULL_OF.get(client, client)


def expected(case: dict, client: str, default_key: str = "expect"):
    """一条用例在这个客户端上的期望：per_client[客户端名]（只有严格版会这样写）→ per_client[类名] → expect。
    简易版按对应的完整版查（loon-simple-strict 用 per_client 里 loon-strict 的那一项）：分流规则两版相同；
    只对简易版成立的期望写成 per_client[简易版的客户端名]。"""
    pc = case.get("per_client") or {}
    if client in pc:
        return pc[client]
    if full_of(client) in pc:
        return pc[full_of(client)]
    return pc.get(family(client), case[default_key])


@functools.lru_cache(maxsize=None)
def parsed(client: str):
    t = text(client)
    fam = family(client)
    if fam == "mihomo":
        return emulate.parse_mihomo(t)
    if fam == "singbox":
        return emulate.parse_singbox(t)
    if fam == "loon":
        return emulate.parse_loon(t)
    if fam == "stash":
        return emulate.parse_stash(t)
    return emulate.parse_qx(t)


def route(client: str, conn, fx, trace=None) -> str:
    """trace：给一个字典时，Loon / Quantumult X / Stash 的模拟器会记下“为了判断 IP 规则，有没有在本机解析这个域名”。"""
    conf = parsed(client)
    fam = family(client)
    if fam == "mihomo":
        return emulate.mihomo_route(conf, conn, fx)
    if fam == "singbox":
        return emulate.singbox_route(conf, conn, fx)
    if fam == "loon":
        return emulate.loon_route(conf, conn, fx, trace=trace)
    if fam == "stash":
        return emulate.stash_route(conf, conn, fx, trace=trace)
    return emulate.qx_route(conf, conn, fx, trace=trace)


def load_yaml(name: str):
    with open(os.path.join(ROOT, "tests", name), encoding="utf-8") as f:
        return yaml.safe_load(f)
