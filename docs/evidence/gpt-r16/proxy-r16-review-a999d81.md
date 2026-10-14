# proxy r16 独立审核报告

审核对象：`ixxooxo-alt/proxy`，分支 `claude/r12-gpt-review-handling-q4onlv`，提交 **a999d81db2bb25e1269008991e5638f29e83de4b**。统一源 2026.10.13-2，生成器 1.9.0。增量基线：r15 的 dc90da785b654f7ab318354da23f392502303e52。审核日期：2026-10-14（UTC+8）。

先读了本提交的 `00-审核说明.md`、`docs/08` 第 11 轮，再核对生成器、两份 Stash 产物、相关测试、DNS 说明、待决事项和日志。本报告不审核 main，不重写配置；审核 PR 仅新增本报告，不修改已有项目文件或合并分支。

## 结论

**没有确认到 Stash 的导入失败，也没有在 Stash 真机上确认实际直连泄漏；但当前证据不足以把 r16 认定为已完成真机验收的终版。**

本轮确认三处需要处理的内容：

| 编号 | 类别与优先级 | 确认到的事实 | 影响边界 |
|---|---|---|---|
| R16-F01 | 安全或泄漏：条件风险，中 | Stash“其他地区”的节点筛选接受 DIRECT、REJECT、REJECT-DROP，结构检查仍通过 | 空 provider 的 DIRECT 是否在 App 中进入该组、最终被选中，尚未运行验证；不能据此宣布已经泄漏 |
| R16-F02 | 文档不符／测试工具，中低 | SOCKS 记录器对未知 TCP ATYP、截断地址和不支持的命令，仍有未记入 invalid 的拒绝 | 不推翻现有正常报文结果；影响未来异常路径的证据可信度 |
| R16-F03 | 文档不符，低 | Stash DNS 说明把可能的性能影响写得过于确定，并将目标版本已支持的功能列进不采用的理由 | 两份配置的取舍可以保留；需要收窄理由与性能承诺 |

通过的部分：`build.py --check`；**294 项单元测试，0 failure、0 error、0 skipped**；代码状态哈希与定稿记录一致；旧四客户端配置的增量说明一致；Stash 文档包的 44 项内容与当前官网一致。

Stash 正则引擎、空订阅时的最终故障行为、默认选项与真机 DNS 仍未确认。sing-box 1.14.3 的源码已有与 UDP 现象直接相关的修改，但本轮不能宣称运行验证通过。

## 已确认问题

### R16-F01：其他地区的筛选未排除内置策略名

**位置：**

- `dist/stash/stash.yaml:309–312`，“其他地区”，`include-all: true` 与 `filter`。
- `dist/stash/stash-strict.yaml:311–314`，同一组。
- `generator/emit_stash.py:87–93`，`filter_regex` 原样返回地区筛选。
- `generator/verify.py:147–157`，只确认筛选选中一个占位节点，没有检查内置策略名。
- `docs/06-已知限制与待决事项.md:277–278`，空地区与空订阅的说明。

**独立核对：** 用 PyYAML 读取本提交的两份真实产物，对其实际 filter 执行 Python 正则匹配。只有“其他地区”会接受 `DIRECT`、`REJECT`、`REJECT-DROP`；其余六地区及 PayPal 筛选拒绝这些名字。两份配置的 `verify.check_stash` 均返回空问题列表。

**为什么需要改：** 官方说明空远程代理集会以 DIRECT 替代。当前“其他地区”用排除已知地区的方式接收未识别名称，因此这个替代策略在名称层面没有被挡住。放一个失败节点只能保证组不为空，不能保证组内没有可直连的成员。“国外默认”和多个业务组可以选择“其他地区”，所以这是实际存在的防护缺口。

**已确认与推断必须分开：**

- 已确认：产物正则接受这些名字；检查器未发现；官方明确记录空 provider 的 DIRECT 替代。
- 未确认：替代发生在组筛选之前还是之后；是否纳入 include-all；缓存和当前选择是否会导致 DIRECT 被使用。
- 因而本条不是“真机已经泄漏”的报告，也不是六个地区自动组必然直连的报告。

**建议：** 只在 Stash 的节点筛选入口显式排除官方内置 DIRECT、REJECT、REJECT-DROP 的完整名称。给生成检查与结构检查增加对应断言；不要删除业务组中用户可以主动选择的 DIRECT。重新生成 dist，保留占位节点。之后分别验证无缓存首次下载失败、已有缓存更新失败、部分订阅失败、全部 provider 返回空列表。若 App 在 filter 之后额外注入 DIRECT，正则排除仍不够，必须再按实际行为处理。

依据：[Stash 远程代理集](https://stash.wiki/proxy-protocols/proxy-providers)、[策略组](https://stash.wiki/proxy-protocols/proxy-groups)、[规则类型中的内置拒绝策略](https://stash.wiki/rules/rule-types)。项目来源：[本提交的 Stash 生成器](https://github.com/ixxooxo-alt/proxy/blob/a999d81db2bb25e1269008991e5638f29e83de4b/generator/emit_stash.py#L87)。

### R16-F02：记录器仍会静默丢掉部分 TCP 协议错误

**位置：** `tools/check_real_routes.py:885–903`，`Socks5Recorder._serve`；`_socks_addr:811–823`。相关概括在 `docs/08` 第 11 轮 R15-F01 的“被拒绝的都记进 invalid”，以及 `docs/07` 的 R15-F01 完成记录。

解析地址发生在主请求错误检查之前。未知地址类型抛出 ValueError，截断地址抛出 ConnectionError，统一 catch 后直接返回。合法地址配不支持的 CMD 虽回复 07，也没有记录拒绝原因。

本轮直接向记录器发送协议字节，不启动代理内核：

| 请求 | 回复 | 新增 invalid |
|---|---|---|
| 无认证握手后发送 `05 01 00 09`（未知 ATYP） | 连接关闭，空回复 | 0 |
| IPv4 请求只发一字节地址后关闭写端 | 连接关闭，空回复 | 0 |
| CMD=2（本记录器不支持 BIND），地址完整 | `05 07 00 01 00000000 0000` | 0 |

**为什么需要改：** 记录器没有把异常请求记成正常目标，这一点比 r15 正确。但“invalid 为空”仍不能说明它没有收到畸形请求。以后内核把目标写坏，这种异常可能与“根本没发出”一样只体现为 `-`，固定核对无法依靠 invalid 区分。

**建议：** 校验主请求头后再解析地址；对未知 ATYP 记录原因并按适用范围回复 08；对握手或请求尚未完整时的 EOF 记录“截断请求”；不支持的命令单独记为拒绝。正常 CONNECT 的结束、正常 UDP 控制连接关闭不要当成畸形请求。无需把记录器扩成完整代理服务。

依据：[RFC 1928 第 4、5、6 节](https://www.rfc-editor.org/rfc/rfc1928)，ATYP 的合法范围和 REP=08。项目位置：[请求解析与异常处理](https://github.com/ixxooxo-alt/proxy/blob/a999d81db2bb25e1269008991e5638f29e83de4b/tools/check_real_routes.py#L872)。

**严重程度边界：** 测试工具的异常路径与说明问题，不是生产代理漏洞；本轮原有 RFC 负向测试均通过，不因此否定 r16 已存档正常路径的输出。

### R16-F03：Stash DNS 取舍的性能与版本论证应收窄

**位置：**

- `docs/03-DNS决策表.md:247–255`，尤其理由 1、2、5 及“国内网站最快”。
- `docs/06-已知限制与待决事项.md:280`。
- `generator/emit_stash.py:17–19` 的对应说明。

**问题：**

1. 官网说 DNS 经代理可能影响 CDN 和延迟，没有证明本配置一开 follow-rule 就会使国内网站先变慢。若 cn policy 仍选国内 DNS 且这些 DNS 的连接直连，国内查询与境外查询的路径可以不同。Stash 网络引擎处理仍可能增加开销，但增幅没有测量。
2. 旧版本也有官网列出的避环条件：代理服务器使用 IP，或者 DNS 服务器使用 IP。不能将“独立 proxy-server-nameserver 要 3.6”写成旧版本没有任何可用办法。项目 docs/03 第 2 条已提到 IP 条件，而 docs/06 的概括遗漏了它。
3. geosite policy 与多服务器值已经在本次指定的 iOS 3.4.0 / macOS 4.2.0 支持。“它需要这两个版本”是兼容性条件，对本次目标本身不是不支持的理由。
4. “国内网站最快”没有性能对照；国内 DNS 通常有利于国内 CDN，但不是速度保证。

**建议：** 保留标准／严格两份，将理由改成未验证的资源、CDN、启动与维护成本；把性能表述改为“优先使用国内解析，有利于保留国内 CDN 路径，实际速度需测”。明确目标版本已支持 geosite policy。不要仅为修文档而自动改 DNS 配置。

依据：[Stash DNS](https://stash.wiki/features/dns-server)、[iOS 3.4.0 发布记录](https://stash.wiki/release-notes/ios)、[macOS 4.2.0 发布记录](https://stash.wiki/release-notes/macos)。

## Stash 写法逐项核对

本轮读取并比较了官网当前的原始“Copy page”内容。下表的“有依据”表示文档支持这种配置写法，**不表示 App 导入或实际执行已通过**。

| 当前写法 | 官方依据 | 判断 |
|---|---|---|
| mode: rule、log-level: warning | [配置样例](https://stash.wiki/configuration/example-config) | 有依据 |
| nameserver 的两条 HTTPS DNS，默认直出 | [DNS](https://stash.wiki/features/dns-server) | 有依据；IP 形式避免 DNS 服务名的 bootstrap 查询；未测试真实服务性能 |
| follow-rule: false | 同上 | 有依据；关闭是默认行为 |
| nameserver-policy 的 `'+.lan': system` 等标量值 | 同上及配置样例 | 有依据；使用系统 DNS 不等同保证系统实际指向路由器 |
| fake-ip-filter 的精确域名与 +. 后缀 | 配置样例、[主机名映射](https://stash.wiki/features/hosts) | 有依据；具体 DNS 流量未抓取 |
| HTTP 类型占位节点、server、port、benchmark-* | [协议类型](https://stash.wiki/proxy-protocols/proxy-types) | 字段有依据；localhost:1 是预期失败目标，未证明每台设备都没有监听服务 |
| proxy-providers 的 url、interval | [远程代理集](https://stash.wiki/proxy-protocols/proxy-providers) | 有依据；未写 path 不能从文档推出完全没有 App 缓存 |
| provider 上的 benchmark-url、benchmark-timeout | [iOS 2.6.5 发布记录](https://stash.wiki/release-notes/ios)、macOS 发布记录 | 有依据；timeout 为秒，本项目转换正确 |
| select、url-test、fallback、load-balance、嵌套组 | [策略组](https://stash.wiki/proxy-protocols/proxy-groups) | 有依据；组成员健康状态与回切仍需实测 |
| include-all: true + filter | 同上，官方香港组示例 | 有依据；正则引擎未确认；内置策略名缺口见 F01 |
| interval、lazy、consistent-hashing | 同上 | 有依据；consistent-hashing 本身不保证任何故障下出口 IP 永不改变 |
| icon 图片 URL | [策略组图标](https://stash.wiki/configuration/proxy-group-icon) | 有依据；未验证图片下载、显示 |
| DOMAIN／DOMAIN-SUFFIX／DOMAIN-KEYWORD、IP-CIDR／IP-CIDR6、GEOIP、GEOSITE、MATCH | [规则类型](https://stash.wiki/rules/rule-types) | 当前用到的类型有依据；规则顺序与 mihomo 标准版相同 |
| GEOIP,CN,国内直连,no-resolve | 同上 | 明确支持；严格版其余 IP 规则也带 no-resolve |
| rule-providers 的 behavior: domain-text、url、interval；RULE-SET | [配置样例](https://stash.wiki/configuration/example-config)、[规则集合](https://stash.wiki/rules/rule-set) | 有依据；domain + format: text 也有文档依据，但无需因此换写法 |
| YAML 锚点／别名、单引号 | 配置样例声明使用 YAML；[YAML 规范](https://yaml.org/spec/1.2.2/) | 语法合法，PyYAML 解析通过；Stash 解析器执行未验证 |

没有发现误用了 proxy-server-nameserver、加密 default-nameserver、inline rule-provider、GEOIP,UNKNOWN 等文档标为较新版本的能力。两份产物也没有复制 mihomo 的 respect-rules、direct-nameserver、empty-fallback、hidden。

### 下载的“44 页”与官网

实际构成是：**42 个页面 Markdown + llms.txt + 提取的配置 YAML = 44 项内容**，另有 FAILED.txt 与 MANIFEST.txt；不是 44 个独立网页。

- 包内 MANIFEST 登记 45 个文件，45 个 SHA-256 与大小全部匹配；MANIFEST 自身不在该清单里，ZIP 总计 46 个文件。
- 去掉代下载者添加的四行来源／时间前缀，与当前官网提供给“Copy page”的源文本比较：42 个页面与 llms.txt 全部逐字节一致。
- 配置 YAML 与官网配置样例中的 YAML 块逐字节一致。
- **44/44 一致，0 差异，0 失败。**

这证明本轮比较时包内内容与当前官方内容一致；不是官网曾经每个历史时刻都不变的证明。两页发行记录中的目标版本能力也核对过。

## DNS 设计是否能满足两个目标

**判断：保留标准版／严格版有合理理由；但不能把任何一份宣传成全场景同时保证“国内 DNS 看不到所有境外名字、国内网站绝不变慢”。**

标准版的国内 DoH、fake-IP、域名规则优先、最后 GEOIP,CN 解析，与文档支持的路径一致。它已经写明未分类域名可能被国内 DNS 看到；这是原有取舍，不重复报成新增漏洞。

严格版给 GEOIP,CN 加 no-resolve，能在模拟的规则判断阶段避免为未分类域名本机解析；ChinaMax 只补两个 GEOSITE 都未接住的名字，现有顺序有依据。清单未收录的国内网站会走国外默认。官方 TCP 表述有“通常尽可能”的限定，不足以证明所有代理类型、非 A/AAAA 查询、App 自带 DNS 都遵守同一结论。

**目标版本可支持的进一步写法，属于待实测设计：**

在 iOS 3.4.0 / macOS 4.2.0，可用 follow-rule、IP 形式的境外 DNS、geosite:cn 的国内 policy、局域网 system policy；为 DNS 服务地址明确指定出站，避免 DNS 服务连接又依赖域名分类。若已有至少一个可用的 IP 地址代理或可用缓存节点，可降低首次连接和节点域名解析的循环风险。对尚需国内节点域名解析的情况，可维护精确节点名 policy，但它会增加维护与隐私边界，不能隐去这个成本。

这套路径可以让已分类国内查询继续使用国内 DNS，把需要在本机解析的境外查询送往境外 DNS；它**不能保证**未分类的国内域名也始终最快。Stash 没有本项目在 mihomo 中使用的独立 direct-nameserver 分工，尚未证明“路由最终直连才改用国内 DNS”的通用实现。没有可用节点时还必须处理订阅和 GEOSITE 的启动；本版有占位节点，不能假定外网默认组会自动安全地变成直连。

还应限定两点：订阅节点可以带 udp-nameserver，不能把默认 1.0.0.1 当成所有真实订阅都强制使用的值；设备的 TXT／HTTPS 等非地址查询和非域名承载协议，继续按未验证记录。当前选择两份配置可以保留，不要求本轮改成 follow-rule。

## 占位节点、排序与正则

### 占位节点够不够

生成检查和本轮正则匹配支持：每个节点筛选恰好选中本地区的一个占位节点；固定 PayPal 筛选也保留美国占位节点。它能避免正常筛选后完全空组的风险。

但“一个失败节点存在”不足以证明故障全过程都拒绝外发：F01 的内置策略名、App 对全部节点失败的处理、UDP 不支持的 HTTP 占位出口，以及正则编译失败时的行为都需要实际观察。不得把它写成已通过的安全保证。

官方说明组内默认按配置顺序排序，也允许按延迟排序；没有说明 include-all 合并静态节点、多个 provider 和替代 DIRECT 的完整顺序。docs/06 对 PayPal 可能默认选占位节点的提醒应保留。

### filter 是否处理 proxies

这里应区分配置顶层 proxies 与组内 proxies。本版占位节点都在顶层 proxies；**所有带 filter 的组，其组内都没有显式 proxies 成员**。官方 include-all + filter 示例涵盖顶层代理和 provider，所以当前设计并非完全没有文档依据。

不能拿别的 Clash 内核对组内显式成员的处理，推断本版每组必然多出六个占位节点。App 的真实筛选、排序和 fallback 注入仍需验收，尤其不能跳过 F01 的“其他地区”。

### 正则引擎

本轮没有找到 Stash 官方对 filter 引擎的确认。不能根据 Apple 平台推定 ICU，也不能根据 Clash 兼容性推定 RE2 或 regexp2。

Python／ICU 的结果一致，只证明这些被测引擎接受本项目表达式，不能证明 Stash 接受。负向前瞻、定长负向后顾和较长表达式仍须在目标版本导入并检查实际成员。当前没有依据报告“Stash 不支持，所以必然导入失败”；也没有依据将其标为真机兼容通过。

## R15 修复和建议的复核

- **R15-F01 的主要修复正确。** 方法协商、请求 VER/RSV、UDP RSV/FRAG、关联源地址、控制 TCP 关闭后的 UDP socket 结束已落实；本轮完整测试包含对应负向用例并通过。剩余缺口见 F02。
- **R15-F02 正确修复。** `singbox_outbound_probe:1140–1150` 不再无条件声称 TCP/UDP 都把域名原样交给节点；现在以接收记录、版本和路由为准。
- **transport 过滤正确。** `received_by_node:963–975` 按 tcp/udp 过滤，并保留 domain+ip 的合并。
- **第 21 项方案③的补充正确。** system 需要独立可用的最终解析器，替身不能证明真实系统无间接环路；fake-IP 不使所有查询类型自动跟随组选择。没有改动使用者已选的维持现状。
- **域名尾点更正正确。** 我上一轮关于“内核只去掉一个根点”的表述有误。实际 [mihomo v1.19.31 dns/util.go:324–330](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/dns/util.go#L324) 使用 strings.TrimRight，去掉全部末尾点。r16 的查询入口模拟与直接 trie Search 的区分，以及 ASCII 范围限定，处理正确。
- **GPL 文件自身的修改日期已补。** 内容未变化时不变更日期／产物的做法合理。当前哈希测试能发现未同步更新哈希的内容改动；如果以后仅更新哈希常量而不改日期，测试并不能独立发现。应把它称为人工维护的日期与内容快照，不夸大成自动证明日期一定更新。这是后续建议，不否定本版日期。
- ResourceWarning 的文件关闭修复正确，本轮测试日志无此警告。

## sing-box UDP 定位与待决事项第 22 项

### 探针能证明什么

`handoff/notes/r15_review_probes.py` 的域名／IPv4、直接出口／selector、sniff、resolve 对照设计有价值。SOCKS 使用同一个已改进的记录器；SS/Trojan/VMess 使用同版本本地配对服务端，出口拒绝外发。输出与 docs/08 第 11 轮的主要描述一致：

| 存档场景 | 1.14.1 | 1.12.0 |
|---|---|---|
| SOCKS 直接出口：域名／IPv4 | 两者收到 | 两者收到 |
| SOCKS 经 selector：域名／IPv4 | 仅 IPv4 收到，出现 unsupported address | 两者收到 |
| sniff + selector | 同上 | 两者收到 |
| resolve + selector | 解析后的 IP 收到 | 解析后的 IP 收到 |
| SOCKS 经 urltest | 仅 IPv4 收到，出现 unsupported address | 仅 IPv4 收到，无此错误 |
| SS／Trojan 经 selector | 域名未到服务端，IPv4 到达 | 两者到达 |
| VMess 经 selector | 两者到达 | 两者到达 |

1.12.0 的 urltest 例外在 docs/08 中有记录，不能概括为该版本所有组组合均正常。未测试的协议、真实服务器、下行回复和 TUN 不可由这张表推定通过。

这表是**审核仓库存档**，不是本轮重新完成的内核运行。

### 源码补充：与现象直接对应的接口丢失路径

本轮读取官方源码，定位链条如下：

1. [sing-box v1.14.1 selector.go:155–161](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/group/selector.go#L155)／urltest 的 ListenPacket 返回 interrupt 包装。
2. [common/interrupt/conn.go:49–75](https://github.com/SagerNet/sing-box/blob/v1.14.1/common/interrupt/conn.go#L49) 的 PacketConn 只嵌入 net.PacketConn，丢失底层带域名地址的 ReadPacket/WritePacket 接口。
3. [sing v0.9.4 bufio/conn.go:15–22、107–109](https://github.com/SagerNet/sing/blob/v0.9.4/common/bufio/conn.go#L15) 将其包装为 ExtendedPacketConn；WritePacket 将 Socksaddr 转为 net.UDPAddr。[metadata/addr.go:89–97](https://github.com/SagerNet/sing/blob/v0.9.4/common/metadata/addr.go#L89) 的该转换不承载 Fqdn。
4. SOCKS 的 WriteTo 再从这个地址构造目标；[metadata/serializer.go:50–63](https://github.com/SagerNet/sing/blob/v0.9.4/common/metadata/serializer.go#L50) 对空地址 family 返回 unsupported address。直接使用完整 PacketConn 接口时不会走这次域名到普通 UDPAddr 的降级。

这是比“组那一层”更具体的**源码分析**，与存档对照吻合；本轮没有获取真实执行调用栈。

[1.14.3 common/interrupt/conn.go](https://github.com/SagerNet/sing-box/blob/v1.14.3/common/interrupt/conn.go) 已改为嵌入 N.NetPacketConn，通过 bufio.NewPacketConn 保留扩展接口。**新版确有直接相关的源码修补**；不能仅因发布说明写 fixes and improvements 就认定全场景已修复，也不能继续把它描述成只有完全没有依据的猜测。

### 本轮运行限制

官方 1.14.1 压缩包与程序 SHA-256 均匹配仓库登记值。1.14.3 压缩包 SHA-256 为 `e2bdf179c15a3652955dc44867e33ca0965c9c9b91b34267dcc5a5d639a5feee`，与官方 release asset digest 相同。

- 1.14.1 最小 mixed → direct 启动失败：create netlink socket: operation not permitted。
- 1.14.3 最小配置在本环境退出码 -11，无输出，进程在转发验证前退出。
- 没有把这两种启动失败算成 UDP 不通，也没有把它们当作升级无效的证据。1.14.3 的实际修复效果仍待可运行环境验证。

### 第 22 项的处理顺序和成本

**建议先按现有③确认 SFA 内核，并在可运行环境重跑同一最小探针及实际配置；这有明确源码依据。** 暂不自动改 DNS。

①维持现状是有代价的接受：网页常能改走 TCP，但不能保证所有浏览器、语音、游戏或纯 UDP 应用都有有效回退。“网页、视频照常”应收窄为可能回退后的表现。

②“先 resolve，再交给组”有存档支持，但目前只验证了本机 UDP DNS 替身；没有验证实际 dns-foreign 经国外默认访问 DoH 的整条路径。实施前必须说清以下条件：

- 解析动作放在匹配到最终代理路由之前；若只是全局顶置 network=udp 的境外 resolve，会影响局域网、国内直连、拒绝流量和直接 IP 连接，不能称为只影响代理 UDP。
- 当前业务组可以切到 DIRECT，单靠业务组名字不能判断用户当前实际选中的出口；方案需要定义这些可切换组的行为。
- dns-foreign 的 DoH 本身依赖可用代理。应防止 DNS 劫持路径再触发同一 resolve、循环或故障时回落国内。
- 新增解析往返、缓存命中、失败时阻塞、A/AAAA 选择以及 CDN 出口匹配都是成本，不能只写 CDN 一项。
- 要核对上行目标、返回报文的地址还原、UDP 会话，以及 TUN fake-IP 的行为；“节点收到地址”尚不是双向应用已通。

其他可列入成本说明的局部规避：只拒绝受影响代理路径上的 UDP/443，让支持回退的应用使用 TCP；或在必要场景绕过组直接路由到实际节点。前者不能修语音游戏，后者损失动态选组、故障切换；若考虑旧内核，也必须确认 App 与兼容配置、功能和维护代价。它们不应替代先验证新版的步骤。

## 事实／推断／未验证及数字核对

`docs/05` 的总体分层合理：官方 Linux 核对、自制模拟器、源码推断、真机未验证没有合并成同一种证据。具体需要收窄的是 F03 的速度语言，以及 Stash TCP／DNS 的泛化；F01 的空组防护必须增加上述条件。docs/05 的 290 条 Stash 结果位于模拟器范围，并非官方内核结果，这一点记录正确。

| 核对项 | 本轮结论 |
|---|---|
| 统一源与生成器 | 2026.10.13-2／1.9.0，与 manifest 和日志一致 |
| source_sha256 | cd8f4cc874b1f4b462d0349531e0ffd4c1edb90ed4d2a61709cc5ae671dda4cf，一致 |
| 定稿代码状态哈希 | c613987e17944ae25087a0e8bece3ded4215204f0eb3631b55256f2b04a6a1a9，本轮重算一致 |
| 产物数量 | manifest 登记 14 个被哈希的文件，加 manifest 自身共 15 个；不是数字矛盾 |
| 全部登记产物 SHA-256 | 逐个重算，全部一致 |
| 自动测试 | 存档 294 项；本轮 294 项，全部通过，无跳过 |
| 变异日志 | 141 条、141 个不同编号，M1–M141 无缺号；未重跑整批变异 |
| r15 → r16 旧产物 | Loon／QX／mihomo 六份仅版本注释变化；sing-box 两份逐字节相同，已独立比较 |
| 路由数字 | 日志明确是 290 条用例／排除项、270 个不同目标；Stash 模拟两份各 290 条，不能把两种计数混用 |
| 规则判断阶段本机解析 | 日志与文档一致：261 个主机中，Loon／QX 标准 43、Stash 标准 16；三种严格版为 0 |
| 逐条 DNS／路由扫描 | 文档与存档两内核代表主机为 0 的结果一致；不是所有实际网络名字的全称证明 |
| Stash 严格版清单 | 快照记录 111,328 条、268 精确域名／111,060 后缀；实际运行订阅会随上游更新 |
| .ms | Stash 严格版跟随上游的差异已经记录；未要求撤销使用者接受的取舍 |
| 字段扫描 | 日志 4,589 个字段／取值，与 docs/05 一致；仅针对 mihomo／sing-box，不包括 Stash |

没有发现本轮上述主要数字被日志否定。存档“141/141 被发现”不是本轮亲自重跑 141 类的声明。源码 dialer-proxy、节点 ip-version、系统 DNS、Loon/QX 严格版四处假设、Stash 实际数据及资源占用，继续保留未验证边界，不升格。

## 本轮实际执行和交付范围

实际执行：固定提交克隆及增量比较、生成一致性检查、294 项测试、代码哈希和产物哈希核对、44 项官网源文比对、Stash 保留策略名匹配、SOCKS 异常请求探针、官方版本源码比较、官方 sing-box 最小启动尝试。

没有执行：Stash／Loon／QX 导入、真实订阅、手机／Mac DNS 抓包、完整官方路由批次、完整变异批次、TUN、真实应用连通性与性能。没有更改 main、审核目标分支、已有日志或需求原文。审核 PR 只放这份报告，不包含未验证的生产配置修补。

下一步应先处理 F01 的名称防护与 F02 的异常记录，再完成 Stash 正则、空订阅、默认选择和 DNS 验收；sing-box 按第 22 项先确认实际版本并验证源码相关修补。F03 修说明即可，不需要因此重写整个项目。
