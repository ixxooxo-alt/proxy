# r21b 全项目复核 · b9a9f14

**结论：公开模板可有条件继续使用；没有发现 20 份公开配置普遍无法导入，也没有确认新的默认配置 DNS 泄漏。发现了确定的业务分流遗漏，以及带特定订阅生成的 sing-box 配置会失去 TLS 保护或不能启动的问题。打包与验包也有需要先修的错误。** 公共配置能继续用，不等于可以原样信任所有私密配置或从日常工作目录直接交付 ZIP。优先修 F01–F03、F05–F07；使用网页 Copilot 的同时处理 F04。

对象为会话分支上的 [b9a9f14](https://github.com/ixxooxo-alt/proxy/commit/b9a9f14598d300495859c6390559646e5c81254f)。和已发布 a6671c1 的 dist 完全一致。精确地说，两次后续提交除了 Markdown，还给一次性的 recheck_r21b.py 增加了一项旧文案检查；生成器、规则和产物没变。这里审的是最终树，不是只审那两次提交。以下是报告，不含配置改动。

## 覆盖与证据强度

| 范围 | 本次核对及其边界 |
|---|---|
| 需求与历次决定 | 以 00-审核说明、docs/00、07 为准，结合 docs/08 历轮处理和 docs/06 现行决定。业务默认/独立 AI/共享云、广告例外、严格版、手选版及三个测速间隔分别对照源、产物和测试。docs/07 第 14、23、29 行的“已实现”有具体反例（F01–F05）；“已实现·未实测”不能解读成手机通过。 |
| 五端产物与导入 | 公开 20 份配置、4 个自有规则文件和 1 份 manifest；24 个清单哈希逐个按原始字节重算。检查 build、五个 emit、groups、strict、verify、tests/helpers 的变体登记，并用全套测试解析各版。对照 [Loon 规则](https://nsloon.app/docs/Rule/)、[QX 官方样例](https://github.com/crossutility/Quantumult-X/blob/master/sample.conf)、[Stash 策略组](https://stash.wiki/proxy-protocols/proxy-groups)、[mihomo 代理集](https://wiki.metacubex.one/config/proxy-providers/) 和 [sing-box URLTest](https://sing-box.sagernet.org/configuration/outbound/urltest/)。QX 写明成员与正则混写、Loon 简易版组与筛选混放、Stash 首选与订阅失败的行为仍不能由语法检查代替真机。 |
| 规则、归属与先后 | 五个服务文件共 91 个服务、870 条规则，模型给出产品 850、服务 IP 14，其余系统 6。全套测试包含针对每个适用产品精确域名/后缀及代表子域、在各端与“更具体优先”的期望比较（tests/test_routing.py）。这验证生成顺序，不能用规则自身证明登记的归属正确。独立抽查 [OpenAI 官方网络清单](https://help.openai.com/en/articles/9247338)、[GitHub Copilot 官方清单](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference) 等；20 份的模拟结果中 OpenAI API、Gemini 和已有的 Copilot 专属主机归属正确，F04 是反例。561 条社区规则是固定快照核对，不是 870 条今天逐域联网实测。 |
| DNS 与两项目标 | 对照 docs/03、06、生成器和 real-route-check.log，区分设备 DNS、为匹配规则而解析、直连/代理出站再解析、节点自身解析；查看 LAN、IPv6、假地址和缓存的边界。默认直连组被手选到国外、App 自带 DNS、标准版遇未分类域名、严格版漏收国内站点，不能从已有记录推得“永不外泄”或“国内不变慢”。严格版约束的是为判断规则而解析，并不禁止所有本机解析。未做当前运营商的延迟对照或设备抓包。就已给目标，保留可选严格版比宣称存在一个两全默认值更合适。 |
| 组、故障与地区 | 每份完整版 Stash：57 个 select 为 -1，12 fallback、6 url-test、6 load-balance 为 300 且 lazy；每份简易版 51 个 select 为 3600。两份简易 sing-box 的“境外DNS”均为 600s/30m；mihomo 简易版保持一小时。sing-box 完整版默认不等同于其他端的手动优先。ICU 对公开 2290 名、本地补充 2313 名的结果与 Python 一致；七组宽筛选并集和“全部节点”一致。名称不能证明出口；Stash 的正则引擎、父组如何测子组、订阅首次失败的实际出口仍无真机证据。 |
| 测试与交付 | 本次 Python 3.12.14：build.py --check 通过；349 项 unittest 通过（307.904 秒）；code_state.sh 与冻结值一致；recheck_r21b.py 通过（119 项文档检查，116 条旧说法）。重跑 Cursor 533 条对照、ICU、r20→本版私密样例对比（24 文件；manifest 整份豁免）。210 类变异改动均能套用；本次对 M182、M210 各跑其专属断言，看见预期的测试失败。检查归档日志 M1–M210 各一次；快照 290 用例、270 不同目标，DNS 查询 22 / 15、拨号各 12；未重跑整套变异。 |
| 隐私 | 检查该提交跟踪文件、公开产物 provider 和忽略边界；常见私钥头、令牌、代理 URI、常见个人邮箱模式未命中；受检查的公开订阅为占位。此为对最终树的检查，不是对所有 Git 历史或任意个人信息的保证。下述生成/归档测试用仓库样例或无敏感数据的临时文件。 |
| 未做 | 未在五端 App 或真实线路上导入、测速或验证故障恢复。docs/05 的 2026-10-20/21 是使用者在 r19 Loon 上的记录。本机没有指定的官方二进制和配套地理数据；官方发行文件下载超时，未重跑 check_official 或 check_real_routes。官方内核和其他 Python 版本的成功是已有日志/记录，不当作本次实测。审核基于 Git 对象，未核验用户所指原 ZIP 的字节。 |

代码状态：`eca139fa64d9b4ea4e2d286a358b4c1ca616d700e12eeb4c4631704068a7c32a`。此前已登记的 M182 关键字、变异只看返回值、单一样例跳过 manifest 等，不重复列为新错误。

## 确认的问题

### F01 · Trojan 转换可能去掉原有 TLS

**类别：安全或泄漏 · 高；仅私密 sing-box 产物。**

位置：[generator/nodes.py:308](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/generator/nodes.py#L308) 调用 [generator/nodes.py:39](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/generator/nodes.py#L39)。Trojan 的缺省值虽是开启，但订阅里额外写的布尔 `tls: false` 会覆盖它。用合成输入调用转换器，输出中 TLS 为 null，跳过/警告记录为空。对普通 TCP Trojan，[mihomo v1.19.31 adapter/outbound/trojan.go:44](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/trojan.go#L44) 的选项没有这个 TLS 开关，[mihomo v1.19.31 adapter/outbound/trojan.go:150](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/trojan.go#L150) 的普通 TCP 路径会建立 TLS。目标内核在 [sing-box v1.14.1 protocol/trojan/outbound.go:55](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/trojan/outbound.go#L55) 只在 TLS 配置存在时建立 TLS 拨号器，第 139 行以下在没有拨号器时走普通连接；[1.12.0 对应分支](https://github.com/SagerNet/sing-box/blob/v1.12.0/protocol/trojan/outbound.go#L127) 也是条件握手。

结论限于转换结果及源码路径：这使源格式不会关闭的 TLS 在目标格式里消失，正规服务端还可能直接拒绝连接。没有抓取真实流量或用户数据。建议按协议固定 Trojan 的 TLS 语义；收到矛盾字段时宁可跳过该节点并报原因。加一项普通 TCP Trojan 的回归测试，同时保留 HTTP / VMess 真能选择 TLS 开关的区别。
