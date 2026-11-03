# r20 简易版送审稿审核（2026-10-22）

对象：`ixxooxo-alt/proxy`，`claude/r12-gpt-review-handling-q4onlv`，固定提交 `4d3349d8492decae66eef328d0652f7c0ebd4ff1`。没有审核或修改 main。

## 结论

确认 5 项问题，详见各文件；不是 5 个导入失败。主要是一个后台测速设定遗漏、一个完整版生成兼容性例外，以及三处说明超出了依据。

| 编号 | 类别 / 优先级 | 问题 |
|---|---|---|
| [R20-F01](R20-F01.md) | 文档不符、配置未实现约定 / P2 | Stash 手选组仍默认每 600 秒测速 |
| [R20-F02](R20-F02.md) | 完整版兼容性、文档不符 / P2 | 新保留名称改变了带节点的完整版 |
| [R20-F03](R20-F03.md) | 文档不符 / P2 | mihomo 几秒恢复的结论遗漏触发条件 |
| [R20-F04](R20-F04.md) | 文档不符 / P2 | SFA 闲置约两小时的推断不适用于当前参数 |
| [R20-F05](R20-F05.md) | 安全或泄漏说明不符 / P2 | 新增 DNS 总结抹掉了已知例外 |

P2 表示正式交付前应处理；未确认新的普遍导入失败或新的分流泄漏。

## 本轮实际核对

- Python 3.12.14 / PyYAML 6.0.3：`python3 -m unittest discover -s tests -v`，342 项，238.334 秒，OK。
- `python3 build.py --check`：通过。
- 对 r19 `628ed8a` 的 10 份公开配置和 4 个规则文件逐一比较字节：全部一致。这个结论不覆盖带实际节点的私密生成结果，见 F02。
- 检查了生成器、构建入口、测试登记、写盘前检查和 E6/E7 脚本、记录；核对了指定版本 mihomo、sing-box 源码和官方示例。
- 没有重跑变异检查、全套检查，也没有改写 `docs/evidence/`。不能将本轮 342 项 Python 测试说成手机实测。
- 本环境尝试启动官方 sing-box 1.14.1 的补充闲置探针，被环境的 netlink 权限限制阻止：`create netlink socket: operation not permitted`。F04 是源码核实，未冒充本轮运行结果。没有把环境限制报成项目错误。

## 其余重点的判断

1. **Loon**：[官方 example.conf](https://github.com/Loon0x00/LoonExampleConfig/blob/master/example.conf) 有策略组、节点、订阅混放，也说明 Remote Filter 可加入组；没有恰好等同本项目“组 + Filter”的完整例子。文档目前将组合用法及首次选中标为推断，合理，仍须真机验收。
2. **Quantumult X**：[固定示例 af6fb59](https://github.com/crossutility/Quantumult-X/blob/af6fb59/sample.conf#L102-L113) 分别示范显式成员和正则成员，没有证明混用无效，也没有充分证明其合并顺序。现有“未知”表述适当，不把它报成确定语法错误。
3. **Stash**：[当前官方策略组页](https://stash.wiki/proxy-protocols/proxy-groups) 支持 select 嵌套、include-all、filter，并明确空组视作 DIRECT。尚不足以确认显式成员与批量成员的精确合并顺序、filter 对显式成员的作用。占位节点首次被选中和空订阅风险已列为真机事项，不重复作为新错误。当前页有 hidden；不需要隐藏组的简易版不使用它，不构成问题。
4. **mihomo**：[groupbase.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outboundgroup/groupbase.go)、[parser.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outboundgroup/parser.go)、[dns_dialer.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/tunnel/dns_dialer.go) 支持显式成员的 Compatible provider 不过普通 filter、反引号拆多条筛选，以及 DNS 指定出站名称；不存在的出站名可能作为网卡名解释，因此写盘前校验有必要。未发现这几处确定写法错误。
5. **compose_any**：阅读合成逻辑及“宽七条并集”对照测试；测试包含词表样例、随机组合、本地补充与 assign。此次未找到反例。但有限样例测试不应单独称为任意字符串的数学证明；Python 通过也不能替代各 App 的正则执行和成员合并验收。
6. **测试登记与写盘前检查**：10 份简易版都在 CLIENT_FILES；期望复用通过 full_of 保留严格版区别；未知配置文件名会报错。未发现本轮新增文件整体被静默跳过。具体仍有 F01 这类“测试没有表达该约定”的遗漏。
7. **E6/E7 的证据边界（建议 S01）**：E6/E7 将实际 DoH 换成 TCP DNS，将测速 HTTPS 换为 HTTP；E7 还删除 http_clients/default_http_client，把远程规则集改成本地（`e7_singbox_simple_dist.py:68–79`）。所以它证明的是改造实验台里的 DNS 出站及故障行为；不能算真实 DoH、TLS、长连接及 sing-box 远程规则下载的完整运行验收。建议在 docs/10:149、196 附近列全这些改动，将“官方内核记录对简易版同样成立”改为“静态路由/查询规则一致，旧运行记录可作参考；新增出站路径仅完成下述局部实验”。不要求这次先审后跑阶段补跑全套。
8. **DNS 地区不同的代价**：可能影响本机先解析、再把 IP 交给节点的连接，作为 CDN 风险的推断合理。具体 CDN 地址还取决于递归服务商、缓存、ECS 等，不能理解为必然按出口国家返回地址；当前已注明未实测，建议继续保留限定。
9. docs/05 和 docs/evidence 保留 r19、快速检查另存 handoff 的安排已清楚说明，不能因为尚未跑正式变异检查而判这份送审稿失败。

本 PR 仅提交审核材料，未修改生成器、配置、规则、需求原文或既有证据。所有复现均只用虚构输入，不含真实订阅和凭据。
