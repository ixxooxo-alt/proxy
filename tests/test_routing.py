"""路由行为：用独立写出的期望（cases.yaml）检查四个客户端的真实产物。"""
import unittest

from helpers import CLIENT_FILES, emulate, family, load_yaml, model_and_plan, route

CASES = load_yaml("cases.yaml")
FIX = load_yaml("fixtures.yaml")


def expected_for(case, client):
    exp = case.get("per_client", {}).get(family(client), case["expect"])
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
            for r in plan.product:
                if r.kind not in ("domain", "suffix"):
                    continue
                probes = [r.value] if r.kind == "domain" else [r.value, "probe-x1." + r.value]
                for h in probes:
                    want = most_specific(plan.product, h).target
                    got = route(client, emulate.Conn(host=h), fx)
                    if family(client) == "singbox" and want == "广告拦截":
                        want = "REJECT"
                    if got != want:
                        failures.append(f"[{client}] {h}: 期望 {want}，实际 {got}")
        self.assertFalse(failures, "\n" + "\n".join(failures[:40]))

    def test_service_ip_rules_do_not_trigger_resolution(self):
        """服务专属 IP 规则只匹配直接 IP 连接：域名连接解析到 Telegram 段也不应被它截走（no-resolve 语义）。"""
        fx = emulate.Fixtures({"dns": {"somewhere.example": "149.154.167.51"}, "geoip": {"cn": []},
                               "geosite": {}, "ad_list": []})
        for client in ("mihomo-profile", "mihomo-core", "singbox-1.14", "singbox-1.12", "loon"):
            got = route(client, emulate.Conn(host="somewhere.example"), fx)
            self.assertEqual(got, "国外默认", client)
        # Quantumult X 的 ip-cidr 没有 no-resolve 参数：域名连接走到 IP 规则时会解析并命中（已知差异，见 docs）
        self.assertEqual(route("quantumultx", emulate.Conn(host="somewhere.example"), fx), "Telegram")


if __name__ == "__main__":
    unittest.main()
