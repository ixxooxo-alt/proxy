import functools
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import build  # noqa: E402
from generator.model import build_plan, load  # noqa: E402
import emulate  # noqa: E402

CLIENT_FILES = {
    "mihomo-profile": "mihomo/mihomo-profile.yaml",
    "mihomo-core": "mihomo/mihomo-core.yaml",
    "singbox-1.14": "sing-box/sing-box-1.14.json",
    "singbox-1.12": "sing-box/sing-box-1.12.json",
    "loon": "loon/loon.conf",
    "quantumultx": "quantumultx/quantumultx.conf",
}


@functools.lru_cache(maxsize=1)
def model_and_plan():
    m = load(ROOT)
    return m, build_plan(m)


@functools.lru_cache(maxsize=1)
def outputs():
    m, p = model_and_plan()
    return build.render_public(m, p)


def text(client: str) -> str:
    return outputs()[CLIENT_FILES[client]]


@functools.lru_cache(maxsize=None)
def parsed(client: str):
    t = text(client)
    if client.startswith("mihomo"):
        return emulate.parse_mihomo(t)
    if client.startswith("singbox"):
        return emulate.parse_singbox(t)
    if client == "loon":
        return emulate.parse_loon(t)
    return emulate.parse_qx(t)


def route(client: str, conn, fx) -> str:
    conf = parsed(client)
    if client.startswith("mihomo"):
        return emulate.mihomo_route(conf, conn, fx)
    if client.startswith("singbox"):
        return emulate.singbox_route(conf, conn, fx)
    if client == "loon":
        return emulate.loon_route(conf, conn, fx)
    return emulate.qx_route(conf, conn, fx)


def load_yaml(name: str):
    with open(os.path.join(ROOT, "tests", name), encoding="utf-8") as f:
        return yaml.safe_load(f)


def family(client: str) -> str:
    return "singbox" if client.startswith("singbox") else ("mihomo" if client.startswith("mihomo") else client)
