"""严格版（Loon / Quantumult X 各多生成一份配置）用到的数据与自有远程规则文件。

严格版要解决的事（2026-10-06）：这两端的标准版里，没有命中任何域名规则的域名要先在本机解析（两端填的是国内 DNS），
再按 IP 判断走哪里——出口是代理的连接，域名也被国内 DNS 看到了。严格版改成：
  先按域名认出国内网站（国内域名清单）→ 国内直连；其余域名不在本机解析，直接交给“国外默认”；
  原本就是 IP 的连接照旧按 IP 规则判断（局域网、服务专属 IP、国内 IP）。
两端各自的写法见 emit_loon.py / emit_qx.py；设定在 source/strict.yaml。

自有远程规则文件（生成在 dist/ 下，随仓库发布，配置里按 strict.publish_base 引用）：
  loon/rules/cn-domains.list            国内域名清单，Loon 的规则文件写法（类型,值）
  quantumultx/rules/cn-domains.list     同一份清单，Quantumult X 的写法（类型,值,策略）
  quantumultx/rules/domain-fallback.list  Quantumult X 的域名兜底：一条 HOST-KEYWORD,.（官方 sample.conf 给的写法，
                                          注释原文：“skip the DNS query for all the non-matched hosts”）
清单数据在 source/data/cn-domains.txt，由 tools/update_cn_list.py 从 domain-list-community 的固定快照生成。
"""
from __future__ import annotations

import os
from typing import List, Tuple

CN_DATA_REL = "source/data/cn-domains.txt"
LOON_CN_REL = "loon/rules/cn-domains.list"
QX_CN_REL = "quantumultx/rules/cn-domains.list"
QX_FALLBACK_REL = "quantumultx/rules/domain-fallback.list"
OWN_FILES = (LOON_CN_REL, QX_CN_REL, QX_FALLBACK_REL)
# Quantumult X 的远程规则文件里每行要带一个策略名；配置里用 force-policy 指定了真正的策略，官方 sample.conf 写明
# 这时文件里的策略会被忽略。这里写内置策略：万一 force-policy 没有生效，国内清单仍是直连、兜底仍是走代理而不是本机解析。
QX_INLINE_DIRECT = "direct"
QX_INLINE_PROXY = "proxy"
FALLBACK_KEYWORD = "."          # 含“.”的主机名都命中；不带点的主机名（http://nas/）不命中，见 docs/06


def parse_cn_domains(text: str) -> Tuple[List[str], List[str]]:
    """数据文件 → (后缀列表, 精确域名列表)，保持文件里的顺序。"""
    suffix, full = [], []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("."):
            suffix.append(line[1:])
        else:
            full.append(line)
    return suffix, full


def load_cn_domains(root: str) -> Tuple[List[str], List[str]]:
    with open(os.path.join(root, *CN_DATA_REL.split("/")), encoding="utf-8") as f:
        return parse_cn_domains(f.read())


HEADER_KEPT = ("# 来源：", "# 授权：", "# 展开后", "# 去重后", "# 写法不合规")


def data_header(root: str) -> List[str]:
    """数据文件头部讲来源、快照、授权、条数的几行，原样带进生成的规则文件（讲数据文件自身写法的那一行不带）。"""
    out = []
    with open(os.path.join(root, *CN_DATA_REL.split("/")), encoding="utf-8") as f:
        for raw in f:
            if not raw.startswith("#"):
                break
            if raw.startswith(HEADER_KEPT):
                out.append(raw.rstrip("\n"))
    return out


def own_url(m, rel: str) -> str:
    return m.strict["publish_base"] + rel


def cn_entries(m, plan, family: str) -> Tuple[List[str], List[str], int]:
    """这一端的自有清单里实际写出的条目：(后缀, 精确域名, 去掉了几条)。
    去掉的是已经被这一端【本地规则】覆盖的条目（例如清单里的 qwen.ai：本地规则把它交给国外默认）。两端都是本地规则优先于
    远程规则，这些条目本来就不会生效；去掉以后，“清单里有、本地规则另有安排”的域名走哪里，不再依赖两类规则谁先谁后
    （Quantumult X 的规则先后没有完整的官方说明）。"""
    local = [r for r in plan.lan + plan.real_ip_direct + plan.exceptions + plan.ads_local + plan.product_for(family)
             if r.kind in ("domain", "suffix")]
    by_suffix = {r.value for r in local if r.kind == "suffix"}
    by_exact = {r.value for r in local if r.kind == "domain"}

    def covered(value: str, exact: bool) -> bool:
        parts = value.split(".")
        if any(".".join(parts[i:]) in by_suffix for i in range(len(parts))):
            return True
        return exact and value in by_exact

    suffix, full = m.cn_domains
    kept_s = [x for x in suffix if not covered(x, False)]
    kept_f = [x for x in full if not covered(x, True)]
    return kept_s, kept_f, len(suffix) + len(full) - len(kept_s) - len(kept_f)


def _cn_header(m, dropped: int, kept: int) -> List[str]:
    return m.cn_data_header + [
        f"# 生成时另去掉 {dropped} 条已被配置里的本地规则覆盖的条目（本地规则优先于远程规则，它们本来也不会生效），这个文件里共 {kept} 条。"]


def loon_cn_list(m, plan) -> str:
    suffix, full, dropped = cn_entries(m, plan, "loon")
    L = ["# Loon 严格版用的国内域名清单（订阅规则；策略由配置里的 policy= 指定）。由统一源生成，请勿手工修改。"]
    L += _cn_header(m, dropped, len(suffix) + len(full))
    L += [f"DOMAIN-SUFFIX,{s}" for s in suffix]
    L += [f"DOMAIN,{d}" for d in full]
    return "\n".join(L) + "\n"


def qx_cn_list(m, plan) -> str:
    suffix, full, dropped = cn_entries(m, plan, "quantumultx")
    L = ["# Quantumult X 严格版用的国内域名清单（策略由配置里的 force-policy= 指定，行内的策略名会被忽略）。由统一源生成，请勿手工修改。"]
    L += _cn_header(m, dropped, len(suffix) + len(full))
    L += [f"HOST-SUFFIX,{s},{QX_INLINE_DIRECT}" for s in suffix]
    L += [f"HOST,{d},{QX_INLINE_DIRECT}" for d in full]
    return "\n".join(L) + "\n"


def qx_fallback_list(m, plan=None) -> str:
    return "\n".join([
        "# Quantumult X 严格版的域名兜底。由统一源生成，请勿手工修改。",
        "# 只有一条规则：主机名里含“.”就命中。它排在全部远程规则的最后，没有被前面任何域名规则接住的域名都落到这里，",
        "# 交给配置里 force-policy= 指定的策略（国外默认），不再为了判断 IP 规则而在本机解析。",
        "# 写法出自官方 sample.conf：“You can add below host-keyword rule to skip the DNS query for all the non-matched hosts.",
        "# Pure IP requests won't be matched by the host related rules.”——原本就是 IP 的连接不受它影响。",
        f"HOST-KEYWORD,{FALLBACK_KEYWORD},{QX_INLINE_PROXY}",
    ]) + "\n"
