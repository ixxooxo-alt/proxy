"""连接记录分析工具（tools/check_connections.py）：解析 mihomo 的日志 / 连接快照，并对照统一源分类。"""
import json
import os
import sys
import tempfile
import unittest

from helpers import ROOT, emulate, load_yaml, model_and_plan, route

sys.path.insert(0, os.path.join(ROOT, "tools"))
import check_connections as cc  # noqa: E402

LOG_LINES = [
    # /logs 接口的 JSON 行（mihomo v1.19.31 tunnel.go 的写法：match 规则(内容) using 组[节点]）
    {"type": "info", "payload": "[TCP] 127.0.0.1:50001 --> chatgpt.com:443 match DomainSuffix(chatgpt.com) using OpenAI[🇯🇵 日本 01 [IEPL]]"},
    {"type": "info", "payload": "[TCP] 127.0.0.1:50002 --> robinfrontend-pa.googleapis.com:443 match DomainSuffix(googleapis.com) using Google[日本 01]"},
    {"type": "info", "payload": "[TCP] 127.0.0.1:50003 --> api.newservice.example:443 match Match using 国外默认[日本 01]"},
    {"type": "info", "payload": "[TCP] 127.0.0.1:50004 --> tracker.example:443 match GeoSite(category-ads-all) using 广告拦截[REJECT]"},
    {"type": "info", "payload": "[TCP] 127.0.0.1:50005 --> hulu.playback.edge.bamgrid.com:443 match GeoSite(category-ads-all) using 广告拦截[REJECT]"},
    {"type": "info", "payload": "[TCP] 127.0.0.1:50006 --> www.gov.cn:443 match GeoSite(cn) using 国内直连[DIRECT]"},
    {"type": "info", "payload": "[UDP] 127.0.0.1:50007 --> 91.108.56.100:443 match IPCIDR(91.108.56.0/22) using Telegram[日本 01]"},
    {"type": "info", "payload": "[TCP] 127.0.0.1:50008 --> nas.lan:5000 match DomainSuffix(lan) using DIRECT"},
    {"type": "info", "payload": "[TCP] 127.0.0.1:50009 --> api.newservice.example:443 match Match using 国外默认[日本 02]"},
    {"type": "warning", "payload": "[TCP] dial 国外默认 (match Match/) 127.0.0.1:50010 --> x.example:443 error: timeout"},
]
# 从 Clash Verge Rev“日志”页面复制的文本（前面带时间和级别）
TEXT_LINES = [
    "2026-09-25 20:00:01 INFO [TCP] 127.0.0.1:50123 --> api.anthropic.com:443 match DomainSuffix(anthropic.com) using Claude[日本 02]",
    "这一行不是连接日志",
]
CONNECTIONS = {"downloadTotal": 1, "uploadTotal": 1, "memory": 0, "connections": [{
    "id": "x", "upload": 1, "download": 1, "start": "2026-09-25T12:00:00Z", "rule": "DomainSuffix", "rulePayload": "netflix.com",
    "metadata": {"network": "tcp", "type": "Tun", "host": "www.netflix.com", "process": "chrome.exe",
                 "destinationIP": "198.18.0.9", "destinationPort": "443"},
    # chains：第一项是节点，最后一项是规则指向的组
    "chains": ["美国 03", "美国·手动", "美国·手动优先", "美国", "Netflix·解锁入口", "Netflix"],
}]}


def _write(tmp, name, text):
    p = os.path.join(tmp, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


class ConnectionLogTool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.files = [
            _write(cls.tmp, "netflix.jsonl", "\n".join(json.dumps(x, ensure_ascii=False) for x in LOG_LINES) + "\n"),
            _write(cls.tmp, "verge.txt", "\n".join(TEXT_LINES) + "\n"),
            _write(cls.tmp, "connections.json", json.dumps(CONNECTIONS, ensure_ascii=False)),
        ]
        cls.m, cls.plan = model_and_plan()
        cls.records = cc.read_records(cls.files)
        cls.result = cc.analyze(cls.records, cls.m, cls.plan, "netflix")

    def cat(self, host):
        for k, items in self.result["by_cat"].items():
            for x in items:
                if x["host"] == host:
                    return k
        return None

    def test_parsing(self):
        hosts = [r.host for r in self.records]
        self.assertEqual(len(self.records), 11)          # 9 条匹配日志 + 1 行复制文本 + 1 个连接快照；错误日志与杂行被忽略
        self.assertIn("91.108.56.100", hosts)
        first = self.records[0]
        self.assertEqual((first.rule, first.payload, first.group, first.node),
                         ("DomainSuffix", "chatgpt.com", "OpenAI", "🇯🇵 日本 01 [IEPL]"))
        conn = [r for r in self.records if r.host == "www.netflix.com"][0]
        self.assertEqual((conn.group, conn.node, conn.process), ("Netflix", "美国 03", "chrome.exe"))
        lan = [r for r in self.records if r.host == "nas.lan"][0]
        self.assertEqual((lan.group, lan.node), ("DIRECT", "DIRECT"))

    def test_classification(self):
        self.assertEqual(self.cat("chatgpt.com"), "ok")
        self.assertEqual(self.cat("api.anthropic.com"), "ok")
        self.assertEqual(self.cat("www.netflix.com"), "ok")
        self.assertEqual(self.cat("91.108.56.100"), "ok")
        self.assertEqual(self.cat("nas.lan"), "ok")
        self.assertEqual(self.cat("robinfrontend-pa.googleapis.com"), "mismatch")      # 统一源应进 Google AI
        self.assertEqual(self.cat("api.newservice.example"), "fallback_foreign")
        self.assertEqual(self.cat("tracker.example"), "ads_upstream")
        self.assertEqual(self.cat("hulu.playback.edge.bamgrid.com"), "ads_over_product")
        self.assertEqual(self.cat("www.gov.cn"), "fallback_cn")          # 国内常用网站清单（cn_common）以外的国内主机
        merged = [x for x in self.result["by_cat"]["fallback_foreign"] if x["host"] == "api.newservice.example"][0]
        self.assertEqual(merged["count"], 2)
        self.assertEqual(merged["nodes"], {"日本 01", "日本 02"})

    def test_report_and_exit_code(self):
        report = cc.render(self.result, self.m, self.files)
        self.assertIn("与统一源不一致", report)
        self.assertIn("Netflix（本次测试对象）", report)
        self.assertNotIn("127.0.0.1", report)             # 报告不含来源地址
        out = os.path.join(self.tmp, "report.md")
        self.assertEqual(cc.main(["--service", "netflix", "--out", out] + self.files), 1)   # 有不一致 → 1
        ok_file = _write(self.tmp, "ok.jsonl", json.dumps(LOG_LINES[0], ensure_ascii=False) + "\n")
        self.assertEqual(cc.main(["--out", out, ok_file]), 0)

    def test_expectation_agrees_with_generated_mihomo_config(self):
        """用模拟器按生成的 mihomo 配置路由 cases.yaml 的全部主机，把结果当作日志喂给工具：
        凡是统一源有专门规则的主机，工具都应判定为“符合统一源”。"""
        fx = emulate.Fixtures(load_yaml("fixtures.yaml"), ads_on=True)
        exp = cc.Expectation(self.plan)
        bad = []
        for case in load_yaml("cases.yaml")["cases"]:
            host = case.get("host") or case.get("ip")
            got = route("mihomo-profile", emulate.Conn(host=case.get("host"), ip=case.get("ip")), fx)
            e = exp.target(host)
            if e is None:
                continue
            if got == "广告拦截" and e != "广告拦截":
                # 只有上游广告集合会把产品规则里的主机拦掉（自有拦截条目会让统一源的预期本身就是“广告拦截”）
                rec, want = cc.Record(host, "GeoSite", "category-ads-all", got, "REJECT"), "ads_over_product"
            else:
                rec, want = cc.Record(host, "DomainSuffix", "x", got, "节点"), "ok"
            if cc.classify(rec, e) != want:
                bad.append(f"{host}: 统一源 {e}，配置 {got}")
        self.assertFalse(bad, "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
