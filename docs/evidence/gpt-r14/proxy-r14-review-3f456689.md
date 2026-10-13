# r14 代理分流配置审核报告

审核提交：**3f456689579a7010a5c6aacd683f472e19dd6ca4**。分支：`claude/r12-gpt-review-handling-q4onlv`；统一源 `2026.10.07-2`；生成器 `1.7.0`。完成日期：2026-10-13。未修改仓库文件，未推送、未提 PR，未审 main。

## 结论与优先顺序

本轮没有确认新的、默认配置下的严重 DNS 泄漏或导入失败。R13-F01 的主要修复有效：在官方 mihomo v1.19.31 的本地探针中，`qwen.ai`、`download.microsoft.com` 经 SOCKS5 UDP、WireGuard TCP 均查询境外 DNS；删除新增产品域名层后，WireGuard 下两者重新查询国内 DNS，证实这层有实际作用。

需要改正两处说明：**第 21 项把当前配置的限制说成 mihomo 的普遍限制；阿里妈妈“其余子域按普通国内网站处理”的描述漏掉远程广告关键词。** 另列三项建议，不冒充运行故障。已知的 Apple/Bilibili 手动切代理后的 DNS 风险、严格版分类取舍、上游动态更新等不重复列为新问题。

“国内网站不能变慢”没有通过真实线路测速验收；以下只确认解析路径与规则行为。“没有查询记录”也不等于已经成功把域名送到代理服务器。

## R14-F01：第 21 项遗漏有条件可行的方案

**类别：文档不符；优先级：中。确认范围：源码 + 官方内核机制复测；实际网络速度未验证。**

位置：[docs/06-已知限制与待决事项.md，第 13 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/docs/06-%E5%B7%B2%E7%9F%A5%E9%99%90%E5%88%B6%E4%B8%8E%E5%BE%85%E5%86%B3%E4%BA%8B%E9%A1%B9.md#L13)（第 21 项整行），[docs/03-DNS决策表.md，第 336 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/docs/03-DNS%E5%86%B3%E7%AD%96%E8%A1%A8.md#L336)；相关实现 [generator/emit_mihomo.py，第 37-95 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/generator/emit_mihomo.py#L37-L95)、DNS 段中的 `direct-nameserver` 与 `direct-nameserver-follow-policy`。

文档对“保留国内公共 DoH 为 direct-nameserver，单独关闭 follow-policy”的判断是对的：直连解析不再执行局域网 policy，内部域名可能失败。但不能据此得出“mihomo 不能实现直连与代理分开解析”的一般结论。

mihomo 已有两个独立的目标解析入口：DIRECT 使用 DirectHostResolver；普通代理 UDP、WireGuard 的默认本地目标解析使用 DefaultResolver。关闭 follow-policy 后，前者并非必须指向不认识局域网名字的公共 DNS。

**有条件的方案：**

1. 保留 fake-IP，使这些 Apple/Bilibili 业务域名在连接选择出口之前不取得国内真实地址。
2. 将这些可切换业务域名也加入境外 nameserver-policy，保留更具体的固定直连例外和局域网例外。
3. `direct-nameserver-follow-policy: false`。
4. `direct-nameserver` 指向一台既能解析本地名字、又将公网国内域名交给国内 DNS 的路由器或独立分流 DNS。只有确认设备的系统 DNS 就满足该条件，才可写 `[system]`；更可靠的是明确配置已验证的解析器地址。

这样，直连在 DirectHostResolver 中解析，代理 UDP/WireGuard 在 DefaultResolver 中解析；并不是 nameserver-policy 读取了策略组的当前选择。

本次以回环 DNS 替身模拟上述路由器，保留生成配置的规则，使用 v1.19.31 实测 TCP：

| 目标 | 业务组选 DIRECT | Apple/Bilibili 组选 WireGuard |
|---|---|---|
| www.apple.com.cn | 路由器替身 | 境外 DNS 替身 |
| api.bilibili.com | 路由器替身 | 境外 DNS 替身 |
| www.qq.com | 路由器替身 | 路由器替身 |
| router.lan | 路由器替身 | 路由器替身 |
| qwen.ai | 境外 DNS 替身 | 境外 DNS 替身 |

这些测试证明解析入口可以分离，并未测试一台真实路由器能否解析你的全部内部名字。测试中 system 被替换成回环服务器，没有修改系统 DNS，没有启用 TUN。连接目标由替身答成 127.0.0.1；未进行真实站点下载测速。

**必须保留的边界：**路由器转发到谁、缓存、ECS/CDN 选择和响应时间都影响速度。不能承诺任何路由器都与现有国内 DoH 一样快，也不能把国内公共 DNS 和路由器并列为竞争上游来保证内部名字正常。设备发出的 TXT/HTTPS 等非 fake-IP 查询仍按静态 policy 判断，不随业务组改变；上述方案主要解决连接阶段的目标解析。系统 DNS 若回指 mihomo 或被劫持形成循环，还须先消除循环。节点自己指定远程 DNS 的情况另行核对。

**建议怎么改：**将第 21 项改成“当前直连 DNS 保持国内公共 DoH 时，不能仅通过关闭 follow-policy 兼顾 LAN；可增加需验证局域网 DNS 的第三方案”。默认配置不宜直接替换；先在用户常用网络测内部名字和国内站点首包/下载速度。没有这些环境条件时，现有两种取舍仍成立。

依据：

- [mihomo v1.19.31 dns/resolver.go，第 617–627 行](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/dns/resolver.go#L617-L627)：DirectResolver 有独立 main/cache，只有开启开关才共用 policy。
- [v1.19.31 adapter/outbound/direct.go，第 24–60 行](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/direct.go#L24-L60)：DIRECT 的 TCP、UDP 解析入口。
- [v1.19.31 adapter/outbound/base.go，第 178–186 行](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/base.go#L178-L186)、[wireguard.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/wireguard.go)：代理出口的解析入口。
- [官方 DNS 配置文档](https://wiki.metacubex.one/config/dns/)本身有 `direct-nameserver: [system]` 配合关闭 follow-policy 的示例。
- 本次核查的最新稳定发布为 **v1.19.32（2026-09-30）**；[该版本 resolver.go 第 617–627 行](https://github.com/MetaCubeX/mihomo/blob/v1.19.32/dns/resolver.go#L617-L627)仍是同一机制。未发现新增的按业务组动态切换 DNS 策略接口；没有把源码检查当成该版本完整运行验收。

## R14-F02：阿里妈妈的剩余子域说明不准确

**类别：文档不符，兼有四端拦截范围不一致；优先级：低。确认范围：固定上游规则 + 本地规则检查；mihomo 实测，Loon/QX 为规则语义核对，非手机实测。**

位置：[source/adblock.yaml，第 112-145 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/source/adblock.yaml#L112-L145)、[docs/06-已知限制与待决事项.md，第 26 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/docs/06-%E5%B7%B2%E7%9F%A5%E9%99%90%E5%88%B6%E4%B8%8E%E5%BE%85%E5%86%B3%E4%BA%8B%E9%A1%B9.md#L26)，以及对应的需求落实说明。当前只迁入根域精确规则和 10 条后缀规则；文档说其他子域按普通国内网站处理。

固定上游快照还存在：

```text
HOST-KEYWORD,afpapi.alimama.com,AdvertisingLite
```

它不在上述 11 条本地规则中，也没有被本地放行规则覆盖。Loon/QX 仍订阅包含该关键词的远程广告规则，所以 `afpapi.alimama.com` 仍命中广告拦截；后面新增国内清单不会覆盖先命中的广告规则。本次用固定快照重放两端规则也得到广告拦截。mihomo 的同批 geodata + r14 配置则没有将此主机判为广告（本次替身返回境外 IP，因此最终 MATCH → 国外默认；这个结果不代表该主机真实 IP 在国外）。

这里不是重复报告早已登记的“上游关键词可能误杀”，而是指出 **r14 新写的阿里妈妈收窄结果没有包含这个具体例外**。不能据此宣称这次对所有剩余子域都放行，或者四端广告范围完全一致。

**建议怎么改：**若用户的意思是把上游标出的阿里妈妈广告主机统一拦截，将 `afpapi.alimama.com` 作为边界明确的精确域名或经确认的后缀加入统一源，并补四端用例；不要直接复制宽泛关键词。若只打算拦目前这 11 条，则需要对该域名明确放行，并说明与上游的差异。两种做法选其一后再更新计数和文档。

依据：[blackmatrix7 固定提交 51d2e1dd… 的 QuantumultX/AdvertisingLite.list，第 37730 行](https://github.com/blackmatrix7/ios_rule_script/blob/51d2e1dd8429a91be575157d6f8ed051c93559f8/rule/QuantumultX/AdvertisingLite/AdvertisingLite.list#L37730)。[Loon 对应文件](https://github.com/blackmatrix7/ios_rule_script/blob/51d2e1dd8429a91be575157d6f8ed051c93559f8/rule/Loon/AdvertisingLite/AdvertisingLite.list)也保留该关键词；它们是项目已选定的规则维护者来源，不是据第三方博客推测业务性质。

## 本轮六项重点的审核结果

### 1. nameserver-policy 分层、顺序与客户端改写

对当前合法规则，[generator/emit_mihomo.py，第 42-95 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/generator/emit_mihomo.py#L42-L95) 的覆盖关系处理未发现错误。默认代理产品优先于 geosite:cn；更具体的 `delivery.mp.microsoft.com` 仍交国内 DNS；八条固定直连名字和 LAN 名字优先。相邻普通域名形成同一棵树，geosite 匹配器将普通域名段分开，这与 [v1.19.31 resolver.go 的 makePolicy](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/dns/resolver.go#L568-L594)相符。默认直连组不纳入境外层是当前 follow-policy=true 下有意保留的取舍，不另报为新增缺陷。

YAML 锚点/别名通过此前同提交的官方内核加载检查。界面层的源码证据：

- Clash Verge Rev v2.5.7，提交 `ea509b82363a40c3c32e951d7ce9d66d66da411f`：[enhance/field.rs](https://github.com/clash-verge-rev/clash-verge-rev/blob/ea509b82363a40c3c32e951d7ce9d66d66da411f/src-tauri/src/enhance/field.rs) 的 use_sort 处理顶层字段，并未递归排序 DNS policy；配置使用 serde_yaml_ng Mapping。未发现这批别名必然损坏的依据，但没有运行 Windows/macOS GUI。
- CMFA v2.11.34，提交 `513b67fc35c68af1b0e7377681f95b33c074ecf7`：[load.go 第 32–58 行](https://github.com/MetaCubeX/ClashMetaForAndroid/blob/513b67fc35c68af1b0e7377681f95b33c074ecf7/core/src/main/golang/native/config/load.go#L32-L58) 直接调用 mihomo 配置解析；该标签内核子模块指向 `ab405bad…`，与 v1.19.31 一致。用户 DNS override 仍会改变结果；这属于已登记边界，不能由模板保证。

### 2. 出站解析探针：主要修复有效，阴性结果证据不足

SOCKS5 UDP 和 WireGuard TCP 的阳性 DNS 记录能覆盖 R13-F01；删除产品层的对照试验也有效。以下是**建议 S01**，不是新发现的实际泄漏：

位置：[tools/check_real_routes.py，第 817-912 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/tools/check_real_routes.py#L817-L912)、[tools/check_real_routes.py，第 915-986 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/tools/check_real_routes.py#L915-L986)；[docs/03-DNS决策表.md，第 310-325 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/docs/03-DNS%E5%86%B3%E7%AD%96%E8%A1%A8.md#L310-L325)。

当前上游代理是未监听端口，只统计哪台 DNS 收到查询。`none` 仅能说明观察窗口内没查询；不能证明 SOCKS 请求或 UDP 数据已带着域名成功转交代理。连接被提前拒绝、目标未被处理，也可能得到 none。本次直连 UDP 就出现 `route ip+net: netlinkrib: operation not permitted`，随后没有 DNS 查询；这是运行环境限制，不能解释成“不解析”。现有人工期望会使这些直连用例失败，不能说整个工具对这种情况静默通过。

建议增加一个真实可握手的本机 SOCKS5 接收端，断言 TCP 请求/UDP 报文中的目标地址类型和域名；每个用例记录“进入出口”“发生 DNS”“收到出站请求”三个结果，遇到权限错误单列 blocked。增加去掉 DNS 产品层后 **UDP** 也回到国内 DNS 的对照，补一次策略组实际切换的用例。相关协议地址格式依据 [RFC 1928 第 4、7 节](https://www.rfc-editor.org/rfc/rfc1928)。

`dialer-proxy` 和节点 `ip-version` 没有完整运行覆盖。源码上 ip-version 控制地址族偏好，并不单独选择国内 DNS；链式出口又涉及下一跳服务器域名，不能将“目标域名”和“代理节点域名”混为一类。未取得相反证据，不报成配置错误；以后增加链式出口阳性测试即可。

### 3. DomainTrie 模拟

[tools/dns_route_consistency.py，第 145-224 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/tools/dns_route_consistency.py#L145-L224) 在当前产物用到的精确名、`+.`、单独 `*`、geosite 分段上符合内核逻辑。单独 `*` 匹配单标签名字，不是所有带点域名的全局兜底。

**建议 S02：不要把它称为全部输入下的完全等价实现。** Python insert 会 strip 外围空白，`+.` 分支直接插入；内核 [v1.19.31 component/trie/domain.go 第 27–118 行](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/component/trie/domain.go#L27-L118)对空白、空标签、尾点等有严格验证。Python search 还会去掉末尾所有点。当前生成值合法，没有据此确认实际错分；可补无效输入测试或在注释中限定输入范围，防止后续扩展时误信模拟结果。

### 4. 用户决定的落实

| 决定 | 审核结果 |
|---|---|
| 国内直连固定 DIRECT | source/groups.yaml 第 81 行及四端生成逻辑一致，没有保留可切国外入口 |
| 八条 NTP/认证相关规则固定直连 | generator/model.py 第 719–725 行生成 real_ip_direct，排在广告和产品规则前；它们因此绕过广告是用户决定带来的预期行为，包括已登记的认证误拦例外 |
| Bilibili 港澳台默认直连 | source/groups.yaml 第 43–46 行落实；可手动切换，DNS 的已知代价不算漏改 |
| 友盟收窄 | 本地拦截 18 个 @ads 子域，再由友盟+ 后缀放行其余 umeng.com/umengcloud.com；在选定快照内未确认新增应拦而被漏放的同域子项；域外 umeng 关键词影响已有文档登记 |
| 阿里妈妈收窄 | 本地 11 条落实，但剩余域名说明见 F02 |
| Apple AI 去三条宽规则 | source/services/bigtech.yaml 第 5–35 行已去掉，gspe1-ssl.ls.apple.com 保留；Apple 官方列出的 guzzoni、smoot、apple-relay.cloudflare.com、apple-relay.fastly-edge.com、cp4.cloudflare.com、apple-relay.apple.com 仍有覆盖 |
| Netflix·解锁入口取消 | 分组与生成结果落实；不再作为 Netflix 的默认成员 |
| mihomo dotless/private → system | 已落实；system 的环境含义仍需按文档确认，不等同于保证路由器解析 |
| QX 严格版大清单 | 按固定源复制，生成时只删除被本地规则完整覆盖的条目，没有把只覆盖一个子域误当成覆盖整条父后缀 |

Apple 覆盖依据：[Apple 企业网络官方端点清单的 Apple Intelligence, Siri, and Search 一节](https://support.apple.com/en-us/101555)。这是官方已列端点的覆盖核对，不是 Apple Intelligence 全功能真机验证，也不恢复已由用户决定删除的宽泛域。

大清单在此前同提交的检查中，与登记快照逐字节重建一致；源 111,277 条、生成后 111,182 条，删除 95 条。`generator/strict.py` 第 89–109 行的覆盖检查区分精确名与后缀，判断方向正确。十一万条/约 3.5 MB 在 QX 上的加载、内存与匹配性能没有官方上限依据或手机实测，保持“未验证”，不凭大小判定导入失败。

**建议 S03（许可说明，低优先级）：** `source/data/cn-domains-max.txt` 头部及生成头部已写明上游、提交和 GPL-2.0，且附许可全文；建议在 [generator/strict.py，第 128-135 行](https://github.com/ixxooxo-alt/proxy/blob/3f456689579a7010a5c6aacd683f472e19dd6ca4/generator/strict.py#L128-L135) 生成头部再加入本项目实际修改日期、转换内容和可点击许可地址。上游快照日期不是本项目修改日期。依据为随附 GPL-2.0 第 2(a) 条及 [GNU 官方许可文本](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)。此处仅核对随附声明，不据此判断整个混合仓库必须如何重新许可。

### 5. Loon、Quantumult X 的代理 UDP 解析

**Quantumult X 有官方一般性说明，但没有本次可用的逐协议 UDP 实测。** 官方 [sample.conf，提交 af6fb594…，第 52–60 行](https://github.com/crossutility/Quantumult-X/blob/af6fb594233ec4a3ec6d4ccb3601e9c36b75ea2d/sample.conf#L52-L60)说明本地 DNS 结果用于规则判断和直连，走代理服务器时不使用该结果；第 14 行说明假地址映射的远端解析效果。正文没有把这一描述限定为 TCP，因此支持“通常交给代理解析”的文档推断。但它没有单独列出各 UDP 协议、UoT、dns_exclusion_list 的行为矩阵，不能据此保证所有 UDP 路径都无本地解析。建议文档写成“有官方一般说明；UDP 各协议尚未实测”，而非笼统说完全没有任何官方材料。

**Loon：仍未找到足以确认代理 UDP 目标解析位置的官方文字或本次可靠实测。** [官方 DNS 页](https://nsloon.app/docs/DNS/)里的 UDP/DoQ 是 DNS 查询的传输方式，不能拿来证明被代理应用 UDP 的目标域名在哪里解析。保持未确认；不借用 mihomo 的行为来推断 Loon。

验收应选命中明确代理域名规则的测试主机，同时观察本机 DNS 接收端和可控代理的实际目标字段，并分别试 SS/SOCKS/Trojan、UDP/UoT、域名/假地址入口。只跑 DNS 泄漏网站不能覆盖这些组合。

### 6. 严格版推断、system 和验收措辞

Loon 单独 GEOIP+no-resolve、远程订阅顺序，以及 QX 远程资源之间/远程域名规则相对本地 IP 规则的优先级，仍缺独立真机验证；r14 将它们标为推断是恰当的。不能用按同样推断写成的模拟器去反证 App 必然如此。

可更新一个小证据等级：docs/02 第 105 行将 QX `update-interval` 与 `opt-parser` 一并归为远程过滤资源上的社区写法；当前官方 [sample.conf 第 115–124 行](https://github.com/crossutility/Quantumult-X/blob/af6fb594233ec4a3ec6d4ccb3601e9c36b75ea2d/sample.conf#L115-L124)把自动更新间隔描述为所有远程资源的通用设置。因此 update-interval 可以单独注明一般官方依据；opt-parser 和排序推断不要顺带升级为事实。这是文档建议，不影响生成结果。

关于 system：r13 审核指出的固定公共 DNS 兜底说法已更正；读取系统 DNS 不保证得到家用路由器，Mac 的系统解析行为也不能从 Linux 的替身测试外推。r14 已标出的这些限制无需再算缺陷。

## 验证记录与没有做的部分

- 已核对本地 HEAD 精确等于指定提交；`python3 build.py --check` 通过，仓库工作区保持干净。
- 单元测试：2026-10-13 重跑 259 项，全部通过（0 errors、0 failures、0 skipped）；另单跑 DNS/LAN 13 项通过。。
- 10 月 12 日同一审核会话、同一提交的官方检查已完成：mihomo v1.19.31 两份配置、sing-box v1.14.1/v1.12.0 对应配置与样例节点检查通过；mihomo 2283 个公开样例和 2306 个含本地补充样例的分组与期望一致。临时日志随后被环境清理，10 月 13 日没有把它伪装成重新跑出的日志。
- 10 月 13 日重新下载官方 mihomo v1.19.31。可执行文件 SHA-256：`08787faafea19c1ab0f83fa5a1b22363b7d03ea78da18091a4c883aecaaa5979`。geosite/geoip 使用项目登记的 MetaCubeX 提交 `f7c0420cdf589312aaf82cf51e061703d2621bca`。
- 重跑 8 个域名 × SOCKS5 TCP、SOCKS5 UDP、WireGuard TCP，及去产品层对照、F01 条件方案和 F02 实际路由。直连 UDP 四例被环境 netlink 权限阻断，不能报告整组通过；代理 UDP 的四例有明确境外 DNS 查询记录。
- 没有取得此前完整 real-route-check 的最终结果，不把那次启动视为通过；本报告不宣称重新完成全部 269 目标扫描、118 类变异检查或四端真机验收。
- 没有真实订阅、节点凭据、真实 WireGuard 隧道和实际国内站点速度测试；没有运行 iOS Loon/QX 或 Windows/macOS/Android 客户端界面。

### 当前保留的关键结果

```json
[
  {
    "test": "baseline",
    "outbound": "socks5",
    "transport": "tcp",
    "dns": {
      "qwen.ai": "none",
      "download.microsoft.com": "none",
      "chatgpt.com": "none",
      "never-listed-site.org": "foreign",
      "www.qq.com": "domestic",
      "www.apple.com": "domestic",
      "tlu.dl.delivery.mp.microsoft.com": "domestic",
      "time.windows.com": "domestic"
    }
  },
  {
    "test": "baseline",
    "outbound": "socks5",
    "transport": "udp",
    "dns": {
      "qwen.ai": "foreign",
      "download.microsoft.com": "foreign",
      "chatgpt.com": "foreign",
      "never-listed-site.org": "foreign",
      "www.qq.com": "none",
      "www.apple.com": "none",
      "tlu.dl.delivery.mp.microsoft.com": "none",
      "time.windows.com": "none"
    }
  },
  {
    "test": "baseline",
    "outbound": "wireguard",
    "transport": "tcp",
    "dns": {
      "qwen.ai": "foreign",
      "download.microsoft.com": "foreign",
      "chatgpt.com": "foreign",
      "never-listed-site.org": "foreign",
      "www.qq.com": "domestic",
      "www.apple.com": "domestic",
      "tlu.dl.delivery.mp.microsoft.com": "domestic",
      "time.windows.com": "domestic"
    }
  },
  {
    "test": "router-direct",
    "selected": "DIRECT",
    "dns": {
      "www.apple.com.cn": "system",
      "api.bilibili.com": "system",
      "www.qq.com": "system",
      "router.lan": "system",
      "qwen.ai": "foreign"
    }
  },
  {
    "test": "router-direct",
    "selected": "proxy",
    "dns": {
      "www.apple.com.cn": "foreign",
      "api.bilibili.com": "foreign",
      "www.qq.com": "system",
      "router.lan": "system",
      "qwen.ai": "foreign"
    }
  },
  {
    "test": "alimama-mihomo",
    "routes": {
      "afpapi.alimama.com": [
        "Match",
        "国外默认"
      ],
      "www.alimama.com": [
        "Match",
        "国外默认"
      ],
      "afpapi.alimama.com.example.net": [
        "Match",
        "国外默认"
      ]
    }
  }
]
```

删除新增产品层后，WireGuard 解析：`qwen.ai → domestic`、`download.microsoft.com → domestic`、`chatgpt.com → foreign`。

### 可复现方法

以下脚本依赖固定提交的工具模块，只将 DNS 和代理端替换成回环测试端；不修改 dist，不开 TUN。`system` 列表示模拟的路由器，不代表审核环境真实的系统 DNS。把脚本里的绝对目录改为自己的检出目录、审核输出目录即可。

```python
import pathlib,sys,json,inspect,yaml
P=pathlib.Path('/workspace/scratch/ce4c6bd3b3ae');R=P/'proxy-r14-review';O=P/'r14-audit'
sys.path[:0]=[str(R),str(R/'tools')]
import check_real_routes as c
from generator.model import load
m=load(str(R),include_local=False);text=(R/'dist/mihomo/mihomo-core.yaml').read_text();base=yaml.safe_load(text)
src=inspect.getsource(c.mihomo_outbound_probe).replace('        shutil.rmtree(home, ignore_errors=True)','        shutil.copyfile(logp, str(AUDIT_LOG)); shutil.rmtree(home, ignore_errors=True)')
exec(src,c.__dict__)
binary=str(O/'vendor/mihomo');geodata=str(O/'geodata');rows=[]
# Re-run all mihomo outbound cases exactly, preserving kernel logs.
hosts=[x['host'] for x in c.rd.outbound_cases()]
for out,tr in [('socks5','tcp'),('socks5','udp'),('wireguard','tcp')]:
 c.AUDIT_LOG=O/f'core-baseline-{out}-{tr}.log'
 r=c.mihomo_outbound_probe(binary,geodata,m,text,hosts,out,tr)
 rows.append(dict(test='baseline',outbound=out,transport=tr,dns=r));print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
# Conditional item21 alternative: system is replaced by a loopback LAN-router DNS stub.
hosts=['www.apple.com.cn','api.bilibili.com','www.qq.com','router.lan','qwen.ai']
for selected in ['DIRECT','proxy']:
 conf=yaml.safe_load(text);d=conf['dns'];d['direct-nameserver-follow-policy']=False;d['direct-nameserver']=['system']
 pol={}
 for k,v in d['nameserver-policy'].items():
  if k=='geosite:private':
   for h in hosts[:2]:pol[h]=list(m.dns['foreign_doh'])
  pol[k]=v
 d['nameserver-policy']=pol
 if selected=='proxy':
  for g in conf['proxy-groups']:
   if g['name'] in ['Apple','Apple Music/TV','Apple Push','Bilibili 港澳台']:g['proxies']=['国外默认']
 c.AUDIT_LOG=O/f'core-item21-{selected}.log'
 r=c.mihomo_outbound_probe(binary,geodata,m,yaml.safe_dump(conf,allow_unicode=True,sort_keys=False),hosts,'wireguard','tcp')
 rows.append(dict(test='router-direct',selected=selected,dns=r));print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
# Alimama actual routing with exact geodata.
hosts=['afpapi.alimama.com','www.alimama.com','afpapi.alimama.com.example.net']
r=c.mihomo_probe(binary,geodata,text,hosts,{})
rows.append(dict(test='alimama-mihomo',routes=r));print(json.dumps(rows[-1],ensure_ascii=False),flush=True)
(O/'key-results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
```
