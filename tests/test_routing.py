"""路由行为：用独立写出的期望（cases.yaml）检查各个客户端的真实产物（标准版六份，加 Loon / Quantumult X 的严格版两份）。"""
import csv
import os
import unittest

from helpers import CLIENT_FILES, ROOT, emulate, expected, family, load_yaml, model_and_plan, parsed, route

CASES = load_yaml("cases.yaml")
FIX = load_yaml("fixtures.yaml")


def expected_for(case, client):
    exp = expected(case, client)
    if family(client) == "singbox" and exp == "广告拦截":
        return "REJECT"        # sing-box 以规则动作 reject 实现广告拦截
    return exp


def conn_of(case):
    return emulate.Conn(host=case.get("host"), ip=case.get("ip"))


class RoutingCases(unittest.TestCase):
    def test_all_cases_all_clients(self):
        fx = emulate.Fixtures(FIX, ads_on=True)
        failures = []
        for client in CLIENT_FILES:
            for case in CASES["cases"]:
                got = route(client, conn_of(case), fx)
                exp = expected_for(case, client)
                if got != exp:
                    failures.append(f"[{client}] {case.get('host') or case.get('ip')}: 期望 {exp}，实际 {got}"
                                    + (f"（{case['why']}）" if case.get("why") else ""))
        self.assertFalse(failures, "\n" + "\n".join(failures))

    def test_ad_exceptions_same_exit_with_and_without_ads(self):
        m, plan = model_and_plan()
        exc_values = {r.value for r in plan.exceptions}
        on = emulate.Fixtures(FIX, ads_on=True)
        off = emulate.Fixtures(FIX, ads_on=False, exception_values=exc_values)
        failures = []
        for client in CLIENT_FILES:
            for host in CASES["exception_consistency"]:
                a = route(client, emulate.Conn(host=host), on)
                b = route(client, emulate.Conn(host=host), off)
                if a != b:
                    failures.append(f"[{client}] {host}: 开广告规则 {a} / 关广告规则 {b}")
        self.assertFalse(failures, "\n" + "\n".join(failures))
        # 禁止所有例外统一 DIRECT
        self.assertTrue(any(r.target != "DIRECT" for r in plan.exceptions))

    def test_every_product_rule_wins_for_its_own_hosts(self):
        """对每条产品规则取代表主机（精确域名本身；后缀本身与一个子域），
        在各端首个命中的目标必须等于该规则按“更具体优先”语义的归属——检查生成顺序没有让宽泛规则遮挡例外。"""
        from generator.model import most_specific
        m, plan = model_and_plan()
        fx = emulate.Fixtures({"dns": {}, "geoip": {"cn": []}, "geosite": {}, "ad_list": []}, ads_on=True)
        failures = []
        for client in CLIENT_FILES:
            emitted = plan.product_for(family(client))          # 部分服务只生成到某些客户端（例如国内常用网站不写进 Loon / QX）
            for r in emitted:
                if r.kind not in ("domain", "suffix"):
                    continue
                probes = [r.value] if r.kind == "domain" else [r.value, "probe-x1." + r.value]
                for h in probes:
                    want = most_specific(emitted, h).target
                    got = route(client, emulate.Conn(host=h), fx)
                    if family(client) == "singbox" and want == "广告拦截":
                        want = "REJECT"
                    if got != want:
                        failures.append(f"[{client}] {h}: 期望 {want}，实际 {got}")
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))

    # 需求补充（2026-09-29）：Apple AI 照搬 Cursor 版 18 条，关键词 siri 换成最后三条具体主机名；
    # 2026-10-07 用户定了待决事项第 8 项（方案二）：放宽“不增不减”，拿掉 ls.apple.com、apps.mzstatic.com、gateway.icloud.com 三条宽规则
    APPLE_AI_EXPECTED = [
        ("domain", "guzzoni.apple.com"), ("domain", "mask-api.fe.apple-dns.net"), ("domain", "mask-api.icloud.com"),
        ("domain", "mask-t.apple-dns.net"), ("domain", "mask.apple-dns.net"),
        ("suffix", "apple-relay.apple.com"), ("suffix", "apple-relay.cloudflare.com"), ("suffix", "apple-relay.fastly-edge.com"),
        ("suffix", "apple-relay.mask.apple-dns.net"), ("suffix", "cp4.cloudflare.com"),
        ("suffix", "gspe1-ssl.ls.apple.com"),
        ("suffix", "mask-h2.icloud.com"), ("suffix", "mask.icloud.com"), ("suffix", "smoot.apple.com"),
        ("suffix", "siri.apple.com"), ("suffix", "siri.com"), ("suffix", "applesiri.cn"),
    ]
    NARROWED = {("suffix", "ls.apple.com"), ("suffix", "apps.mzstatic.com"), ("suffix", "gateway.icloud.com")}
    # 普通苹果地址仍归 Apple；后三个是 2026-10-07 拿掉的三条宽规则管过的主机，现在回到 Apple（默认直连）
    ORDINARY_APPLE = ["apple.com", "www.apple.com", "icloud.com", "www.icloud.com", "p00-ckdatabase.icloud.com",
                      "time.apple-dns.net", "is1-ssl.mzstatic.com", "gs-loc.apple.com", "apps.apple.com", "itunes.apple.com",
                      "gsp-ssl.ls.apple.com", "apps.mzstatic.com", "gateway.icloud.com"]

    SIRI_REPLACEMENTS = {("suffix", "siri.apple.com"), ("suffix", "siri.com"), ("suffix", "applesiri.cn")}

    def test_apple_ai_matches_cursor_baseline(self):
        """与对照报告明细（docs/evidence/cursor-对照明细.csv）里 Cursor 版的 18 条相比，只有两处差别：关键词 siri 换成三条后缀；
        2026-10-07 按用户的决定拿掉三条宽规则（待决事项第 8 项）。"""
        kind = {"完整域名": "domain", "域名后缀": "suffix", "关键词": "keyword"}
        with open(os.path.join(ROOT, "docs", "evidence", "cursor-对照明细.csv"), encoding="utf-8") as f:
            base = {(kind[r["规则类型"]], r["规则值"]) for r in csv.DictReader(f)
                    if r["分流"] == "Apple AI" and r["本仓库有"] == "是"}
        self.assertEqual(len(base), 18)
        self.assertLessEqual(self.NARROWED, base)
        self.assertEqual(base - {("keyword", "siri")} - self.NARROWED, set(self.APPLE_AI_EXPECTED) - self.SIRI_REPLACEMENTS)
        self.assertEqual(len(self.APPLE_AI_EXPECTED), 17 - len(self.NARROWED) + len(self.SIRI_REPLACEMENTS))

    def test_apple_ai_before_apple(self):
        """Apple AI 的全部地址在四端都先命中 Apple AI；普通苹果地址仍命中 Apple；不再有关键词规则误伤 siriusxm.com。"""
        m, plan = model_and_plan()
        rules = [(r.kind, r.value) for s in m.services if s.id == "apple_ai" for r in s.rules]
        self.assertEqual(rules, self.APPLE_AI_EXPECTED, "Apple AI 规则必须与上面的清单一致（需求给定的 18 条，按用户的决定去掉三条宽规则）")
        self.assertFalse([r for s in m.services for r in s.rules if r.kind == "keyword"], "不应再有关键词规则")
        fx = emulate.Fixtures({"dns": {}, "geoip": {"cn": []}, "geosite": {}, "ad_list": []}, ads_on=True)
        failures = []
        for client in CLIENT_FILES:
            for kind, value in self.APPLE_AI_EXPECTED:
                for h in ([value] if kind == "domain" else [value, "probe-x1." + value]):
                    got = route(client, emulate.Conn(host=h), fx)
                    if got != "Apple AI":
                        failures.append(f"[{client}] {h}: 期望 Apple AI，实际 {got}")
            for h in self.ORDINARY_APPLE:
                got = route(client, emulate.Conn(host=h), fx)
                if got != "Apple":
                    failures.append(f"[{client}] {h}: 期望 Apple，实际 {got}")
            got = route(client, emulate.Conn(host="www.siriusxm.com"), fx)
            if got != "国外默认":
                failures.append(f"[{client}] www.siriusxm.com: 期望 国外默认，实际 {got}")
            # 书写位置：Apple AI 的每一条都写在 Apple 组的第一条（含 apple.com、apple-dns.net）之前
            targets = self._domain_rule_targets(client)
            ai = [i for i, t in enumerate(targets) if t == "Apple AI"]
            ap = [i for i, t in enumerate(targets) if t == "Apple"]
            if not ai or not ap or max(ai) > min(ap):
                failures.append(f"[{client}] 书写顺序：Apple AI 位置 {ai[:1]}…{ai[-1:]}，Apple 位置 {ap[:1]}…{ap[-1:]}")
        self.assertFalse(failures, "\n" + "\n".join(failures))
        apple = next(s for s in m.services if s.group == "Apple")
        self.assertIn(("suffix", "apple-dns.net"), [(r.kind, r.value) for r in apple.rules], "apple-dns.net 保留在 Apple 组")

    @staticmethod
    def _domain_rule_targets(client):
        """按书写顺序列出各端域名类规则的目标组（sing-box 一条规则对象可能含多个域名，按对象计）。"""
        conf = parsed(client)
        if client.startswith("mihomo"):
            return [ln.split(",")[2].strip() for ln in conf["rules"]
                    if ln.split(",")[0] in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD")]
        if client.startswith("singbox"):
            return [r.get("outbound") for r in conf["route"]["rules"]
                    if any(k in r for k in ("domain", "domain_suffix", "domain_keyword"))]
        types = (("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD") if family(client) == "loon"
                 else ("host", "host-suffix", "host-keyword"))
        return [p[2] for p in conf["local"] if p[0] in types]

    def test_service_ip_rules_do_not_trigger_resolution(self):
        """服务专属 IP 规则只匹配直接 IP 连接：域名连接解析到 Telegram 段也不应被它截走（no-resolve 语义）。"""
        fx = emulate.Fixtures({"dns": {"somewhere.example": "149.154.167.51"}, "geoip": {"cn": []},
                               "geosite": {}, "ad_list": []})
        for client in ("mihomo-profile", "mihomo-core", "singbox-1.14", "singbox-1.12", "loon", "loon-strict"):
            got = route(client, emulate.Conn(host="somewhere.example"), fx)
            self.assertEqual(got, "国外默认", client)
        # Quantumult X 的 ip-cidr 没有 no-resolve 参数：标准版里域名连接走到 IP 规则时会解析并命中（已知差异，见 docs）
        self.assertEqual(route("quantumultx", emulate.Conn(host="somewhere.example"), fx), "Telegram")
        # 严格版：域名兜底先于 IP 类规则接住它，不解析，也就不会被服务专属 IP 段截走
        trace = {}
        self.assertEqual(route("quantumultx-strict", emulate.Conn(host="somewhere.example"), fx, trace=trace), "国外默认")
        self.assertFalse(trace.get("resolved"))
        # 原本就是 IP 的连接，各端（含两份严格版）仍按服务专属 IP 规则走
        for client in CLIENT_FILES:
            self.assertEqual(route(client, emulate.Conn(ip="149.154.167.51"), fx), "Telegram", client)


if __name__ == "__main__":
    unittest.main()
