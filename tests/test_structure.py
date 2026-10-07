"""产物结构：策略组、默认值、引用完整性、安全边界、版本差异、确定性。"""
import json
import os
import re
import unittest
from urllib.parse import urlparse

from helpers import CLIENT_FILES, LOON_CLIENTS, QX_CLIENTS, ROOT, build, family, load_yaml, model_and_plan, outputs, parsed, text
from generator import strict as strict_mod
from generator.util import valid_domain

CASES = load_yaml("cases.yaml")
REGIONS = ["香港", "日本", "韩国", "台湾", "新加坡", "美国"]
ALL_REGION_ENTRIES = REGIONS + ["其他地区"]
MODE_SUFFIX_FULL = ["手动优先", "手动", "自动", "故障转移", "负载均衡"]


def groups_of(client):
    """统一成 {组名: {"type":..., "members":[...], "raw":...}}"""
    c = parsed(client)
    out = {}
    if client.startswith("mihomo"):
        for g in c["proxy-groups"]:
            out[g["name"]] = {"type": g["type"], "members": g.get("proxies", []), "raw": g}
    elif client.startswith("singbox"):
        for o in c["outbounds"]:
            if o["type"] in ("selector", "urltest"):
                mem = list(o["outbounds"])
                if o["type"] == "selector" and "default" in o:
                    mem.remove(o["default"])
                    mem.insert(0, o["default"])
                out[o["tag"]] = {"type": o["type"], "members": mem, "raw": o}
    elif family(client) == "loon":
        for k, v in c["groups"].items():
            out[k] = {"type": v["type"], "members": v["members"], "raw": v}
    else:
        for k, v in c["policies"].items():
            mem = [{"direct": "DIRECT", "reject": "REJECT"}.get(x, x) for x in v["members"]]
            out[k] = {"type": v["type"], "members": mem, "raw": v}
    return out


BUILTINS = {"DIRECT", "REJECT"}


class Structure(unittest.TestCase):
    def test_parse(self):
        for client in CLIENT_FILES:
            self.assertTrue(parsed(client), client)

    def test_business_groups_present(self):
        m, _ = model_and_plan()
        for client in CLIENT_FILES:
            gs = groups_of(client)
            for g in m.groups:
                if client.startswith("singbox") and g.name == "广告拦截":
                    continue      # sing-box 用规则动作 reject
                self.assertIn(g.name, gs, f"{client} 缺少 {g.name}")

    def test_defaults(self):
        for client in CLIENT_FILES:
            gs = groups_of(client)
            for name, want in CASES["defaults"].items():
                if client.startswith("singbox") and name == "广告拦截":
                    continue
                self.assertEqual(gs[name]["members"][0], want, f"{client} {name} 默认值")

    def test_region_entries(self):
        for client in CLIENT_FILES:
            gs = groups_of(client)
            for r in REGIONS:
                mem = gs[r]["members"]
                if client.startswith("singbox"):
                    self.assertEqual(mem, [f"{r}·自动", f"{r}·手动"], client)
                else:
                    self.assertEqual(mem, [f"{r}·{s}" for s in MODE_SUFFIX_FULL], client)
                for x in mem:
                    self.assertIn(x, gs, f"{client} {x}")
            fd = gs["国外默认"]["members"]
            self.assertEqual(sorted(fd), sorted(ALL_REGION_ENTRIES), client)
            self.assertEqual(fd[0], "日本")

    def test_no_silent_direct_in_node_groups(self):
        for client in CLIENT_FILES:
            gs = groups_of(client)
            for name, g in gs.items():
                is_node_group = name in ALL_REGION_ENTRIES or "·" in name
                if is_node_group:
                    self.assertFalse(set(g["members"]) & BUILTINS, f"{client} {name} 含 DIRECT/REJECT")
        for client in ("mihomo-profile", "mihomo-core"):
            for g in parsed(client)["proxy-groups"]:
                if g.get("include-all-providers"):
                    self.assertEqual(g.get("empty-fallback"), "REJECT", g["name"])

    def test_manual_first_semantics(self):
        """手动优先·自动兜底 = 故障转移组，成员依次为 手动、自动（同地区）。
        Loon 额外在末尾附带同地区节点筛选：官方示例称 fallback 只支持节点，嵌套组可能被忽略，
        附带节点可保证那种情况下该组不为空，且仍只含同地区节点。附带的是严的那条（F-XX-AUTO）：
        这条退路是客户端自己选节点，说不清落地的节点不能进。"""
        codes = {"香港": "HK", "日本": "JP", "韩国": "KR", "台湾": "TW", "新加坡": "SG", "美国": "US"}
        for client in ("mihomo-profile",) + LOON_CLIENTS + QX_CLIENTS:
            gs = groups_of(client)
            for r in REGIONS:
                g = gs[f"{r}·手动优先"]
                self.assertIn(g["type"], ("fallback", "available"), client)
                want = [f"{r}·手动", f"{r}·自动"] + ([f"F-{codes[r]}-AUTO"] if family(client) == "loon" else [])
                self.assertEqual(g["members"], want, client)
                if family(client) == "loon":
                    self.assertEqual(gs[f"{r}·自动"]["members"], [f"F-{codes[r]}-AUTO"], "附带的节点筛选必须与本地区的自动组一致")
                    self.assertEqual(gs[f"{r}·手动"]["members"], [f"F-{codes[r]}"])

    def test_review_followups(self):
        """外部审核后的修正：Loon 不写无用的局域网共享端口；sing-box 不返回 AAAA 时不配 IPv6 假地址段。"""
        for client in LOON_CLIENTS:
            self.assertNotIn("wifi-access-", text(client).replace("allow-wifi-access", ""), client)
        for client in ("singbox-1.14", "singbox-1.12"):
            fake = [s for s in parsed(client)["dns"]["servers"] if s["type"] == "fakeip"][0]
            self.assertEqual(parsed(client)["dns"]["strategy"], "ipv4_only")
            self.assertNotIn("inet6_range", fake)

    def test_paypal(self):
        for client in CLIENT_FILES:
            gs = groups_of(client)
            p = gs["PayPal"]["members"]
            self.assertEqual(p[0], "PayPal·美国固定")
            self.assertNotIn("国外默认", p)
            self.assertIn("DIRECT", p)
            fixed = gs["PayPal·美国固定"]["members"]
            self.assertNotIn("美国", fixed, client)
            self.assertNotIn("国外默认", fixed, client)
        g = [x for x in parsed("mihomo-profile")["proxy-groups"] if x["name"] == "PayPal·美国固定"][0]
        self.assertTrue(g.get("include-all-providers"))
        self.assertIn("filter", g)

    def test_final_is_foreign_default(self):
        self.assertEqual(parsed("mihomo-profile")["rules"][-1], "MATCH,国外默认")
        self.assertEqual(parsed("singbox-1.14")["route"]["final"], "国外默认")
        for client in LOON_CLIENTS + QX_CLIENTS:
            self.assertEqual(parsed(client)["final"], "国外默认", client)

    def test_references_resolve(self):
        for client in CLIENT_FILES:
            gs = groups_of(client)
            known = set(gs) | BUILTINS
            if client.startswith("singbox"):
                known |= {o["tag"] for o in parsed(client)["outbounds"]}
            for name, g in gs.items():
                for mem in g["members"]:
                    if family(client) == "loon" and mem.startswith("F-"):
                        self.assertIn(mem, parsed(client)["filters"])
                        continue
                    self.assertIn(mem, known, f"{client} 组 {name} 引用了不存在的 {mem}")
            # 规则目标
            if client.startswith("mihomo"):
                targets = {r.split(",")[2] if not r.startswith("MATCH") else r.split(",")[1] for r in parsed(client)["rules"]}
            elif client.startswith("singbox"):
                targets = {r["outbound"] for r in parsed(client)["route"]["rules"] if "outbound" in r}
            elif family(client) == "loon":
                c = parsed(client)
                targets = {p[2] for p in c["local"]} | {r["policy"] for r in c["remote"]} | {c["final"]}
            else:
                c = parsed(client)
                targets = {({"direct": "DIRECT", "reject": "REJECT"}.get(p[2], p[2])) for p in c["local"]}
                targets |= {r["policy"] for r in c["remote"]} | {c["final"]}
            for t in targets:
                self.assertIn(t, known, f"{client} 规则目标 {t} 不存在")

    def test_no_group_cycles(self):
        for client in CLIENT_FILES:
            gs = groups_of(client)

            def visit(n, stack):
                self.assertNotIn(n, stack, f"{client} 组循环引用 {stack + [n]}")
                for mem in gs.get(n, {}).get("members", []):
                    if mem in gs:
                        visit(mem, stack + [n])
            for n in gs:
                visit(n, [])

    def test_no_secrets_in_public_outputs(self):
        allowed_hosts = {
            "REPLACE-ME.invalid", "www.gstatic.com", "connectivitycheck.platform.hicloud.com",
            "testingcf.jsdelivr.net", "raw.githubusercontent.com", "223.5.5.5", "1.12.12.12",
            "1.1.1.1", "8.8.8.8",
        }
        # raw.githubusercontent.com 下只允许这几个仓库：上游规则库、用户自己的图标仓库、用户自己放配置的仓库（严格版的自有规则文件）
        allowed_repos = ("/blackmatrix7/ios_rule_script/", "/ixxooxo-alt/icon/", "/ixxooxo-alt/proxy/",
                         "/SagerNet/sing-geosite/", "/SagerNet/sing-geoip/")
        for rel, t in outputs().items():
            for u in re.findall(r"https?://[^\s,\"']+", t):
                host = urlparse(u).hostname or ""
                self.assertIn(host if host != "replace-me.invalid" else "REPLACE-ME.invalid", allowed_hosts,
                              f"{rel} 出现未登记的外部地址 {u}")
                if host == "raw.githubusercontent.com":
                    self.assertTrue(urlparse(u).path.startswith(allowed_repos), f"{rel} 引用了没有登记的仓库 {u}")
            scan = t
            if rel in strict_mod.OWN_FILES:
                # 自有规则文件：每行规则只有“类型,域名[,策略]”。域名本身可能带这些字样（上游大清单里有 passwordkeyboard.com），
                # 所以规则行改为核对写法（第二段必须是合法域名，域名兜底那一条是“.”），只扫注释行
                for ln in t.splitlines():
                    if ln and not ln.startswith("#"):
                        parts = ln.split(",")
                        self.assertIn(len(parts), (2, 3), f"{rel}：{ln}")
                        self.assertTrue(valid_domain(parts[1]) or parts[1] == strict_mod.FALLBACK_KEYWORD, f"{rel}：{ln}")
                scan = "\n".join(ln for ln in t.splitlines() if ln.startswith("#"))
            for bad in ("password", "uuid", "ca-p12", "ca-passphrase", "token="):
                self.assertNotIn(bad, scan.lower(), f"{rel} 含敏感字段 {bad}")
        for client in CLIENT_FILES:
            if client.startswith(("mihomo", "loon", "quantumultx")):
                self.assertIn("REPLACE-ME.invalid", text(client))

    def test_mihomo_flavors_and_control_plane(self):
        core = parsed("mihomo-core")
        prof = parsed("mihomo-profile")
        self.assertTrue(core["external-controller"].startswith("127.0.0.1:"))
        self.assertFalse(core["allow-lan"])
        self.assertEqual(core["bind-address"], "127.0.0.1")
        for k in ("tun", "external-controller", "mixed-port", "allow-lan"):
            self.assertNotIn(k, prof, f"托管版不应包含 {k}")
        self.assertTrue(prof["profile"]["store-selected"])
        dns = prof["dns"]
        self.assertTrue(dns["respect-rules"])
        self.assertIn("proxy-server-nameserver", dns)
        self.assertFalse(dns["ipv6"])

    def test_singbox_integrity_and_versions(self):
        for client in ("singbox-1.14", "singbox-1.12"):
            c = parsed(client)
            tags = [o["tag"] for o in c["outbounds"]]
            self.assertEqual(len(tags), len(set(tags)), "出站 tag 重复")
            rs_tags = {r["tag"] for r in c["route"]["rule_set"]}
            for r in c["route"]["rules"] + c["dns"]["rules"]:
                if "rule_set" in r:
                    self.assertIn(r["rule_set"], rs_tags)
            dns_tags = {s["tag"] for s in c["dns"]["servers"]}
            for r in c["dns"]["rules"]:
                self.assertIn(r["server"], dns_tags)
            self.assertIn(c["dns"]["final"], dns_tags)
            self.assertIn(c["route"]["default_domain_resolver"], dns_tags)
            for s in c["dns"]["servers"]:
                if "detour" in s:
                    self.assertIn(s["detour"], tags)
            if client == "singbox-1.14":
                self.assertIn("http_clients", c)
                self.assertEqual(c["route"]["default_http_client"], c["http_clients"][0]["tag"])
                self.assertFalse(any("download_detour" in r for r in c["route"]["rule_set"]))
            else:
                self.assertNotIn("http_clients", c)
                self.assertTrue(all(r.get("download_detour") == "国外默认" for r in c["route"]["rule_set"]
                                    if r["type"] == "remote"))
            # 内联规则集只有一个（DNS 上“走代理组的产品域名”），不带下载相关的字段；其余都是远程的二进制规则集
            inline = [r for r in c["route"]["rule_set"] if r["type"] == "inline"]
            self.assertEqual([r["tag"] for r in inline], ["product-proxied"])
            self.assertEqual(set(inline[0]), {"type", "tag", "rules"})
            self.assertTrue(all(r["type"] in ("remote", "inline") for r in c["route"]["rule_set"]))
            # DNS 规则的先后：局域网 → 要真实地址的名单 → 产品规则 → 国内域名集合 → 假地址
            order = [("rule_set" in r and r["rule_set"]) or ("lan" in r.get("domain_suffix", []) and "lan")
                     or ("query_type" in r and len(r) == 2 and "fakeip-all") or "list" for r in c["dns"]["rules"]]
            self.assertEqual(order[0], "lan")
            self.assertLess(max(i for i, x in enumerate(order) if x == "product-proxied"), order.index("geosite-cn"))
            self.assertEqual(order[-2:], ["geosite-cn", "fakeip-all"])
            self.assertEqual(order.count("product-proxied"), 2, "A / AAAA 给假地址一条，其余类型交给经代理的 DNS 一条")
            # 旧版字段不应出现（1.12 起新 DNS 服务器格式；1.13 移除入站 sniff 等旧字段；geosite/geoip 数据库已弃用）
            for s in c["dns"]["servers"]:
                self.assertIn("type", s)
                self.assertNotIn("address", s)
                self.assertNotIn("address_resolver", s)
            for ib in c["inbounds"]:
                for legacy in ("sniff", "sniff_override_destination", "domain_strategy", "inet4_address"):
                    self.assertNotIn(legacy, ib)
            for r in c["route"]["rules"]:
                self.assertNotIn("geosite", r)
                self.assertNotIn("geoip", r)
            self.assertNotIn("geosite", c["route"])
            self.assertNotIn("geoip", c["route"])

    def test_dns_and_routing_read_the_same_domestic_set(self):
        """“哪些域名算国内”在 DNS 和路由两边用的是同一份数据，运行时不会出现一边已经更新、另一边还是旧的
        （2026-10-06，GPT 评审 r12 方案时提的“运行时快照一致”）。
        sing-box：DNS 规则和路由规则引用同一个规则集标签 geosite-cn，这个标签只定义一次（一个地址、一份下载）。
        mihomo：路由的 GEOSITE,cn 和 nameserver-policy 的 geosite:cn 都读同一个 geosite.dat（geox-url 里只有一个 geosite 地址）。
        Loon / Quantumult X 的标准版没有国内域名集合；严格版只在路由一边用清单，DNS 一边没有按域名分流的设置。"""
        for client in ("singbox-1.14", "singbox-1.12"):
            c = parsed(client)
            dns_cn = [r["rule_set"] for r in c["dns"]["rules"] if r.get("server") == "dns-cn" and "rule_set" in r]
            route_cn = [r["rule_set"] for r in c["route"]["rules"] if r.get("outbound") == "国内直连" and "rule_set" in r]
            self.assertEqual(dns_cn, ["geosite-cn"], client)
            self.assertIn("geosite-cn", route_cn, client)
            defs = [x for x in c["route"]["rule_set"] if x["tag"] == "geosite-cn"]
            self.assertEqual(len(defs), 1, client)
            self.assertEqual(defs[0]["type"], "remote")
        for client in ("mihomo-profile", "mihomo-core"):
            c = parsed(client)
            self.assertIn("GEOSITE,cn,国内直连", c["rules"], client)
            policy = [k for k in c["dns"]["nameserver-policy"] if k.startswith("geosite:")]
            # 2026-10-07 起 private 单独一条交给系统 DNS（待决事项第 14 项方案二），国内 DNS 那一条只剩 cn
            self.assertEqual(policy, ["geosite:private", "geosite:cn"], client)
            self.assertEqual(c["dns"]["nameserver-policy"]["geosite:private"], ["system"], client)
        self.assertEqual(sorted(parsed("mihomo-core")["geox-url"]), ["asn", "geoip", "geosite", "mmdb"])

    def test_line_formats(self):
        for loon, qx in zip(LOON_CLIENTS, QX_CLIENTS):
            found = 0
            for rx in re.findall(r'FilterKey = "([^"\n]+)"', text(loon)):
                re.compile(rx)
                found += 1
            for line in text(qx).splitlines():
                if "server-tag-regex=" in line:
                    rest = line.split("server-tag-regex=", 1)[1]
                    rx = rest.split(", ", 1)[0]
                    re.compile(rx)
                    self.assertTrue(rx.endswith("$"), f"QX 正则被逗号截断：{rx}")
                    found += 1
            self.assertGreater(found, 30, loon)

    def test_node_name_screening(self):
        m, _ = model_and_plan()
        loon_filters = parsed("loon")["filters"]
        label = {"hk": "F-HK", "jp": "F-JP", "kr": "F-KR", "tw": "F-TW", "sg": "F-SG", "us": "F-US", "other": "F-OTHER"}
        compiled = {k: re.compile(loon_filters[v]) for k, v in label.items()}
        for name, want in CASES["node_names"].items():
            hits = sorted(k for k, rx in compiled.items() if rx.search(name))
            if want == "info":
                self.assertEqual(hits, [], f"提示行 {name} 不应进入任何地区")
            else:
                self.assertEqual(hits, [want], f"{name} 期望 {want}，实际 {hits}")

    def test_deterministic(self):
        m, p = model_and_plan()
        a = build.render_public(m, p)
        b = build.render_public(m, p)
        self.assertEqual(a, b)

    def test_dist_matches_source(self):
        dist = os.path.join(ROOT, "dist")
        if not os.path.isdir(dist):
            self.skipTest("尚未生成 dist/")
        for rel, t in outputs().items():
            if rel == "manifest.json":
                continue
            with open(os.path.join(dist, rel), encoding="utf-8") as f:
                self.assertEqual(f.read(), t, f"dist/{rel} 与统一源不一致，请运行 python3 build.py")


if __name__ == "__main__":
    unittest.main()
