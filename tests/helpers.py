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

# 测试里说的“客户端”指一份产物。标准版六份；Loon / Quantumult X 另有严格版各一份（2026-10-06）。
CLIENT_FILES = {
    "mihomo-profile": "mihomo/mihomo-profile.yaml",
    "mihomo-core": "mihomo/mihomo-core.yaml",
    "singbox-1.14": "sing-box/sing-box-1.14.json",
    "singbox-1.12": "sing-box/sing-box-1.12.json",
    "loon": "loon/loon.conf",
    "quantumultx": "quantumultx/quantumultx.conf",
    "loon-strict": "loon/loon-strict.conf",
    "quantumultx-strict": "quantumultx/quantumultx-strict.conf",
}
STRICT_CLIENTS = ("loon-strict", "quantumultx-strict")
STANDARD_CLIENTS = tuple(c for c in CLIENT_FILES if c not in STRICT_CLIENTS)
STRICT_OF = {"loon": "loon-strict", "quantumultx": "quantumultx-strict"}        # 标准版 → 同一个 App 的严格版
LOON_CLIENTS = ("loon", "loon-strict")
QX_CLIENTS = ("quantumultx", "quantumultx-strict")


@functools.lru_cache(maxsize=1)
def model_and_plan():
    m = load(ROOT)
    return m, build_plan(m)


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
    """这份产物给哪一类客户端用：mihomo / singbox / loon / quantumultx（严格版和标准版是同一类）。"""
    for fam in ("singbox", "mihomo", "loon", "quantumultx"):
        if client.startswith(fam):
            return fam
    raise KeyError(client)


def is_strict(client: str) -> bool:
    return client in STRICT_CLIENTS


def expected(case: dict, client: str, default_key: str = "expect"):
    """一条用例在这个客户端上的期望：per_client[客户端名]（只有严格版会这样写）→ per_client[类名] → expect。"""
    pc = case.get("per_client") or {}
    if client in pc:
        return pc[client]
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
    return emulate.parse_qx(t)


def route(client: str, conn, fx, trace=None) -> str:
    """trace：给一个字典时，Loon / Quantumult X 的模拟器会记下“为了判断 IP 规则，有没有在本机解析这个域名”。"""
    conf = parsed(client)
    fam = family(client)
    if fam == "mihomo":
        return emulate.mihomo_route(conf, conn, fx)
    if fam == "singbox":
        return emulate.singbox_route(conf, conn, fx)
    if fam == "loon":
        return emulate.loon_route(conf, conn, fx, trace=trace)
    return emulate.qx_route(conf, conn, fx, trace=trace)


def load_yaml(name: str):
    with open(os.path.join(ROOT, "tests", name), encoding="utf-8") as f:
        return yaml.safe_load(f)
