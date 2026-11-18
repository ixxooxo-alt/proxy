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

### F02 · 引号里的 false 会让转换器关闭证书校验

**类别：安全或泄漏 · 高；仅私密 sing-box 产物。**

位置：[generator/nodes.py:41](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/generator/nodes.py#L41)、[generator/nodes.py:55](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/generator/nodes.py#L55)、[README.zh-CN.md:66](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/README.zh-CN.md#L66)。YAML 布尔值 false 和字符串 "false" 不同；Python 对非空字符串取 bool 总为真。用启用 TLS 的合成 HTTP 输入核对：后者生成 `tls.insecure: true`，转换报告没有提示。普通布尔 false 不受影响。

依据：[mihomo v1.19.31 adapter/parser.go:15](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/parser.go#L15) 使用结构体解码；[mihomo v1.19.31 common/structure/structure.go:233](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/common/structure/structure.go#L233) 的布尔解码接受布尔值以及弱类型模式下的整数，不把字符串当成真。源端可拒绝的输入不能在转换后悄悄放宽验证。建议在读取布尔字段时先检查类型，无法无歧义映射就跳过并报告；一起检查 TLS 开关、UDP 和插件等直接用 Python 真值判断的位置。测试至少覆盖原生 false、原生 true 和引号里的 false。没有证据表明公开模板或现用订阅触发过。

### F03 · 合法的 packet 别名无法建立 sing-box 出站

**类别：导入失败（准确说是初始化失败）· 高；仅相关订阅。**

位置：[generator/nodes.py:274](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/generator/nodes.py#L274)、[generator/nodes.py:294](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/generator/nodes.py#L294)；写盘前 [generator/verify.py:240](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/generator/verify.py#L240) 查标签和组结构，不校验这个节点枚举。使用仓库自带的 VMess、VLESS 样例，只把 UDP 封装改成 mihomo 支持的 `packet`，完整生成返回 0；完整版/简易版、1.12/1.14 四份私密 JSON 都保留了 `packet_encoding: "packet"`。

依据：[mihomo v1.19.31 adapter/outbound/vmess.go:490](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/vmess.go#L490)、[mihomo v1.19.31 adapter/outbound/vless.go:474](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/vless.go#L474) 把 packet 和 packetaddr 当成同一模式；sing-box [VMess 1.14.1](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/vmess/outbound.go#L76)、[VLESS 1.14.1](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/vless/outbound.go#L78)、[VMess 1.12.0](https://github.com/SagerNet/sing-box/blob/v1.12.0/protocol/vmess/outbound.go#L70)、[VLESS 1.12.0](https://github.com/SagerNet/sing-box/blob/v1.12.0/protocol/vless/outbound.go#L65) 均不接受该别名，构造出站会返回 unknown packet encoding。生成结果已实测；目标内核结论来自固定版本源码，不是手机导入实测。

建议转换时按协议将 packet 归一成 packetaddr，其他值按两个内核的实际枚举处理；无法表达的明确跳过。在官方内核的带节点验收中加入这两个样例，不只断言 JSON 能解析。

### F04 · Copilot 网页实时连接没有跟随 Copilot 策略

**类别：分流错误 · 中；公开和私密规则源共用。**

位置：[source/services/ai.yaml:140](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/source/services/ai.yaml#L140) 的 github_copilot.rules；需求见 [docs/00-需求原文.md:155](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/docs/00-需求原文.md#L155)。GitHub [现行 Copilot 官方网络清单](https://docs.github.com/en/copilot/reference/copilot-allowlist-reference#specific-required-domains) 已列出七个特定的 Azure Web PubSub 主机，用于浏览器实时事件和状态更新，并明确不建议放行整个共享后缀。规则源没有为这批主机指定 Copilot。以其中的公开服务域名 `production-copilot-host.webpubsub.azure.com` 输入仓库路由模拟器，20/20 份配置在现有样本数据下都返回“国外默认”；已有的 Copilot suggestions 主机则 20/20 返回“Copilot”。

影响：用户给两个组选择不同出口时，连接不会遵守 Copilot 的选择；默认都选日本时可能看不出差别。真实客户端是否会断流没有实测，远程集合更新也可能改变兜底结果。建议只把官网列出的七个完整主机加到 Copilot，并用一个同后缀但不属于 Copilot 的对照名防止误收其他租户。

### F05 · 打包会把工程中的非默认私密文件收进去

**类别：安全或泄漏 · 高；发布链，有条件。**

位置：[handoff/release/pack.py:29](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/handoff/release/pack.py#L29)、[handoff/release/pack.py:55](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/handoff/release/pack.py#L55)、[build.py:202](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/build.py#L202)、[README.zh-CN.md:54](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/README.zh-CN.md#L54)。打包遍历工作目录，只排除字面上的 dist/private/ 和 source/local.yaml；它不按被审提交的文件清单收包。正常 CLI 的 --out 可以改输出目录，README 还允许从本地 YAML 读节点。若这两类文件留在工程内，一个未跟踪的输入文件或自选输出目录下的 private 都可能被打进要公开交付的 ZIP。

用无敏感数据的路径测试 wanted() 和 git check-ignore：默认 dist/private 下的配置被两者排除，export/private 下同名文件却被允许打包、Git 也不忽略；仓库根的普通节点输入 YAML 同样如此。README 第 68 行说可分享的范围还应明确为“只分享公开清单中的文件，不能整个复制含 private 子目录的 dist”。没有发现本次提交含真实订阅，也没有据此认定原 ZIP 泄漏。

建议正式发布从指定提交的对象或干净检出、按受控文件清单打包；没有 Git 时用明确的交付清单并拒绝额外文件。验收应覆盖非默认输出、仓库内未跟踪输入和多出的敏感目录；内容扫描不能替代文件边界。

### F06 · 验包遇到硬错误也会返回成功

**类别：建议 · 高优先级；影响发布验收可信度。**

位置：[handoff/release/verify_package.sh:32](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/handoff/release/verify_package.sh#L32) 至第 65 行。diff 不同只打印提示，build.py --check 和 unittest 的状态被 tail 管道遮住；最后返回的是目录统计命令的状态。用了一个只含无害 README 的不完整测试包：明确打印“包和工程不一样”，也找不到 build.py，但整个验包过程退出码仍是 0。

建议逐项保留 diff、构建检查和测试的真实退出码，没运行有效测试也应失败；禁止的私密文件应阻断交付。只供人工判断的扫描结果单列，正常“无匹配”不算命令故障。加一个好包与一个少文件的坏包作验收。原日志中人工看见的通过结果不因此作废，但不能把脚本退出 0 单独当作完整验收证据。

### F07 · 验包清理目录时可能删掉源工程

**类别：安全或泄漏（本地数据安全）· 高；特定目录布局。**

位置：[handoff/release/verify_package.sh:24](https://github.com/ixxooxo-alt/proxy/blob/b9a9f14598d300495859c6390559646e5c81254f/handoff/release/verify_package.sh#L24) 至第 29 行。脚本检查工作目录本身是否在源工程里，然后删除该工作目录下固定名为 proxy-rules 的子目录。前一项检查并不保证后一项目标与源工程互不相交。交付包解出来的顶层恰好叫 proxy-rules：若从这样的源工程运行脚本，把其父目录当作核对目录，则父目录通过检查，待删除目录正好等于源工程。

这是由路径运算即可确认的条件性错误；没有执行任何真实目录删除试验。建议在调用者指定的位置新建本轮专属临时目录，只清理由本轮自己创建的目录；同时按规范化路径拒绝清理目标等于或包含源工程。对路径判定函数做无删除的测试。
