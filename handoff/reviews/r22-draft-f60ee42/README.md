# r22 送审稿审核 · f60ee42

**结论：先修再定稿。** 没有发现 20 份公开配置普遍不能导入，没有观察到使用者的订阅、凭据或设备流量已经泄漏。但已确认三类会影响交付的事：一条不合规的 SS2022 输入可以使整份私密 SFA 配置无法启动；固定直连在域名别名或特定本地补充下不能保证原定去向；一个逐文件正确、测试全过的包会被正式验包命令判失败。反过来，验包脚本也会在文件未通过比对时运行包里的代码。

**对象**：会话分支上的 `f60ee428e4bfc5472b1450f6bfbcc553322e83f4`，对照 `b9a9f14`。未把 `main` 或审核对象之后的提交算进来。范围包括 `166f5e4` **之后**的实现改动：`be463a1` 修改了打包脚本以保留 `.gitattributes`。以下“实跑”指本次运行；“源码确认”指固定版本在所述输入下的代码路径，不等于在手机或公网观察到了后果。下文例子只用公开服务、地名、保留域名和标量。

## 已确认的问题

### R22-F01　包与提交不同，验包仍执行包里的程序

**严重程度：安全或泄漏，高；发布工具。**

**位置与依据：**[handoff/release/verify_package.sh:52–76](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/verify_package.sh#L52-L76)、[handoff/release/selftest_package.py:99–119](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/selftest_package.py#L99-L119)。内容比对失败只在 `FAILED` 数组里记一笔；只要解开的目录有 `build.py`，就继续运行它，正常模式还发现并运行包里的测试。自测甚至要求不符提交的测试实际执行。最终退出 1 是对的，但此时已经执行过未经核对的代码。

**建议：**路径、文件集合或内容比对失败后，保留诊断并立即返回非零；后续可只用可信工具做静态扫描。测试“构建失败 / 测试失败”的场景应当来自与指定临时提交**相符**的夹具，另断言比对失败时执行阶段从未开始。本条是控制流程审阅，没有运行不可信程序，也没有证据表明交付包被动过。

### R22-F02　完全正确的包被正式验包命令判失败

**严重程度：建议，高；阻断发布验收。**

**实跑：**从审核提交新打的包有 650 个文件，逐个文件及生成检查均通过；解包副本的 unittest 跑了 369 项、无跳过、结果 `OK`。不带 `--skip-tests` 的验包命令却退出 **1**，唯一失败理由为“测试：最后一行不是 OK”。

**位置与依据：**[handoff/release/verify_package.sh:69–77](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/verify_package.sh#L69-L77) 合并标准输出与错误输出，并把整个文件的最后一行当 unittest 的结果。Python 的 [TextTestRunner](https://docs.python.org/3.12/library/unittest.html#unittest.TextTestRunner) 默认把汇总写到标准错误；本次汇总之后还有测试自身缓冲的标准输出。[handoff/release/selftest_package.py:80–87](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/selftest_package.py#L80-L87) 对正确包使用 `--skip-tests`，所以“24 项自测通过”和这次失败不矛盾。

**建议：**让一个可信的测试运行器以 `result.testsRun > 0`、`result.wasSuccessful()` 和进程退出码作判据；日志留作诊断。给正确包加一项不带跳过开关的验收，覆盖测试本身会打印文字的情况。

### R22-F03　ZIP 的同名成员未纳入逐项核对

**严重程度：安全或泄漏；交付包内容核验。**

**位置与依据：**[handoff/release/package_check.py:37–63](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/handoff/release/package_check.py#L37-L63)。先取得成员文件名，解包后再按名字 `z.read(n)`，并建成以文件名为键的字典。同名成员因此合成一条；集合、数量、内容和解包后的扫描都不能证明 ZIP 的每一个物理成员都与提交一致。标准库[明确区分按名称与按 ZipInfo 读取](https://docs.python.org/3/library/zipfile.html#zipfile.ZipFile.open)。这是验包判据的问题；没有证据表明本次正确包含重复项。

**建议：**解包前对每个 `ZipInfo` 检查并规范化成员路径，重复目标以及文件与目录冲突立即拒绝；按唯一条目比对，再解包。回归测试用两条同名、无敏感内容的成员即可。

### R22-F04　SFA 的真实地址反查在 DNS 别名下认不回原名

**严重程度：分流错误 / 安全或泄漏；公开与私密 SFA，后果有条件。**

**位置：**[generator/emit_singbox.py:307–343](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/emit_singbox.py#L307-L343)、[tests/test_build_pipeline.py:322–325](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/tests/test_build_pipeline.py#L322-L325)；`docs/03-DNS决策表.md:56`、`docs/06-已知限制与待决事项.md:62、376`。反查开关应保留，但“真实地址名单固定直连”的承诺仍有缺口，不只同 IP 的后一次查询才会造成它。

**源码确认：**[sing-box 1.14.1](https://github.com/SagerNet/sing-box/blob/v1.14.1/dns/router.go#L1122-L1132) 和 [1.12.0](https://github.com/SagerNet/sing-box/blob/v1.12.0/dns/router.go#L317-L325) 都把 **A/AAAA 记录自己的名字**写入映射，并按其 TTL 保存；不是把原始问题的名字写入。即便只查过一次，若应答是「原名 → CNAME → 另一个名字的 A」，[TUN 路由](https://github.com/SagerNet/sing-box/blob/v1.14.1/route/route.go#L564-L583)认回来的也可能是另一个名字。原名走国内 DNS、实际连接却按另一条规则走的条件就成立。SIDN Labs 的[时间服务测量](https://www.sidnlabs.nl/downloads/4ZYbgAM6xtydn2DCkwMctt/8e9a3d7793e620ae2096bd24ba173399/BigTime_Characterizing_Large_Time_Service_Providers_tech_report_20251201.pdf)记录了 Windows 和 Apple 时间服务的别名；本次配置模拟中，`time.apple.com` 是 DIRECT，而 `time.g.aaplimg.com` 属于可切换的 Apple 组。`twc.trafficmanager.net` 不在固定直连名单，给定境外地址的仓库夹具判为国外默认。没有在用户网络测 DNS 应答或 NTP 包，没有证据称这台手机已经走错。

**建议：**文档将承诺限定为“反查命中且记下的名字命中固定规则”。为仍需固定的服务验证其专用别名，只为有证据的确切名字补规则；不要整段收共享 DNS/CDN 后缀。验收增加带一跳 CNAME 的回答和随后无域名的 UDP，观察所选出站。现有测试只查开关为 `true`。

### R22-F05　仅一个客户端应当直连的本地规则在其他端也生效

**严重程度：分流错误 / 安全或泄漏；特定私密配置。**

**位置与依据：**[generator/model.py:491–500](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/model.py#L491-L500) 接受本地服务的 `clients`，[generator/model.py:793–807](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/model.py#L793-L807) 却把所有固定 DIRECT 规则都放进不区分客户端的 `plan.lan`。[generator/emit_mihomo.py:67–72](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/emit_mihomo.py#L67-L72)、[generator/emit_singbox.py:109–114](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/emit_singbox.py#L109-L114)又把这些规则送入 DNS 分层；路由也直接使用 `plan.lan`（上述两文件第 254、266 行）。

**实跑：**只为 Loon 添加一条 GitHub 子域的 DIRECT 规则。模型中 `emitted_to(..., "mihomo")` 为假；实际生成的 mihomo 和 sing-box 却均匹配 DIRECT，mihomo 的 DNS 策略和 sing-box 的 HTTPS 查询都指向国内 DNS。去掉这条本地规则，原目标是 GitHub。公开源目前没有限定客户端的 DIRECT 服务，不把它报成默认泄漏。

**建议：**为固定直连阶段加与 `product_for(family)` 一样的按端筛选；每端的路由、DNS 和预期计算共用筛选结果。测试既断言指定端包含，也断言另外四端没有这条覆盖。

### R22-F06　固定直连父规则与更具体的代理规则仍会造成路由、DNS 分歧

**严重程度：分流错误；特定本地补充。**

**位置与依据：**[generator/model.py:650–661](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/model.py#L650-L661) 仅比“类型和值都相等”；[generator/emit_mihomo.py:75–99](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/emit_mihomo.py#L75-L99)、[generator/emit_singbox.py:112–133](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/emit_singbox.py#L112-L133) 的 DNS 按域名具体程度排。路由却先匹配固定 DIRECT 或真实地址名单，再匹配产品；[mihomo 的 DNS 域名树](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/dns/resolver.go#L568-L599)会使用更具体的匹配。

**实跑：**① 加一条固定 DIRECT 的保留域名后缀，再把它的一个确切子域给国外默认：两个端的连接都 DIRECT，mihomo 的该名 DNS 走境外，sing-box 的 A 给假地址、HTTPS 走境外。② 在既有 `pool.ntp.org` 下加一条给国外默认的确切子域：路由仍 DIRECT；mihomo 选境外 DNS，sing-box 因真实地址规则在前选国内 DNS。两种输入均通过规则源校验。现有测试只覆盖“窄直连盖过宽代理”和同值冲突。

**建议：**按客户端检查：如果一条必须直连的规则完全覆盖了较后、不同目标的产品规则，就在读规则源时报清哪两条矛盾；保留“宽代理下划出窄直连”的合法用法。加入上述两个方向的用例。

### R22-F07　一个无效的 SS2022 条目仍可使整份 SFA 配置启动失败

**严重程度：导入失败，高；仅带该输入生成的私密 SFA。**

**位置：**[generator/nodes.py:374–378](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L374-L378)、[generator/verify.py:280–295](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/verify.py#L280-L295)、[tests/test_nodes.py:350–359](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/tests/test_nodes.py#L350-L359)。加密方法在白名单、认证字段非空就放行；新增正例还把不符合 SS2022 格式的单字符输入列作成功。**本次实跑：**生成返回 0，四份私密 SFA JSON 都保留该出站，写盘前检查均为 0 个问题。

**源码确认：**[1.14.1 的出站构造器](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/shadowsocks/outbound.go#L42-L48)和 [1.12.0](https://github.com/SagerNet/sing-box/blob/v1.12.0/protocol/shadowsocks/outbound.go#L40-L46) 都会传播方法构造失败；两个版本使用的[同一依赖](https://github.com/SagerNet/sing-shadowsocks2/blob/v0.2.1/shadowaead_2022/method.go#L54-L96)校验 Base64、每段解码长度（按方法为 16 或 32 字节），还区分链式密钥适用的方法。失败发生在建出站，不用连上服务就足以使整个配置不能启动。不是说这条畸形输入本应在 mihomo 工作；问题是该条目把旁边正常的也拖下水。

**建议：**按三种 2022 方法在转换时校验，单条不合规就跳过并报字段名/原因，不回显内容；写盘前使用同一判据。现有正例换成合规的合成数据，并加“一条错、一条对，其余配置仍能启动”的测试。

### R22-F08　把 sing-box 的取值白名单直接用在原始订阅上，会误跳过可等价转换的条目

**严重程度：分流错误；私密 SFA 的可用节点少于预期。**

**位置：**[generator/nodes.py:99–104](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L99-L104)、同文件第 128–133、418、436–438 行；`handoff/notes/r22_singbox_enum_sweep.py:53–73` 直接测试目标 JSON，没有测试源写法能否先转换。

**实跑与依据：**三种写法均被转换器跳过：① VMess 的大写 `AES-128-GCM`：[mihomo 先转小写](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/vmess.go#L475-L486)，小写已在两版 sing-box 的白名单；② VLESS 的 `xtls-rprx-vision-udp443`：[该版 mihomo 取前 16 字节作为实际 flow](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/vless.go#L462-L472)，得到两版都支持的 `xtls-rprx-vision`；③ 不加引号的数字指纹 `360`：[mihomo 把整数转十进制文字](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/common/structure/structure.go#L212-L224)，其[指纹表](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/component/tls/utls.go#L78-L87)包含它；本项目给同一值加引号便能转换。这里的对照仅针对指定的 mihomo 版本与 SFA 目标，不推广到其他客户端。

**建议：**先按每个源字段已经证实的含义归一化，再校验输出白名单；不要任意放宽所有字符串。把三种输入分别和规范写法生成的有效字段做对照。

### R22-F09　VMess 外面有 TLS 时，两个内核对内部的 auto 不作同一种处理

**严重程度：安全或泄漏；协议参数被改变，并非外层 TLS 被关闭。**

**位置：**[generator/nodes.py:414–432](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L414-L432) 直接把 VMess 的 `cipher: auto` 作为 `security: auto`，另行照抄 TLS，报告不提示这两项的组合。**源码确认：**[mihomo 1.19.31](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/vmess.go#L475-L486)把 `auto` 原样交给[其 VMess 客户端](https://github.com/MetaCubeX/sing-vmess/blob/v0.2.5/client.go#L42-L54)，[按处理器架构选择 AES-GCM 或 ChaCha20](https://github.com/MetaCubeX/sing-vmess/blob/v0.2.5/protocol.go#L137-L142)。而 [sing-box 1.14.1](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/vmess/outbound.go#L95-L104) 和 [1.12.0](https://github.com/SagerNet/sing-box/blob/v1.12.0/protocol/vmess/outbound.go#L89-L98) 只要已建 TLS 配置就把内部 `auto` 改作 `zero`。所以“枚举值两端都认”不能保证保留内层加密。外层 TLS 仍在，没有观察到公网明文或凭据泄漏。

**建议：**对明确写了 `auto` 且开启 TLS 的源条目，按可核实的目标架构输出等效的显式内部算法；目标架构未知时不要静默降为 `zero`，应跳过并说明。测试分开检查有无 TLS 的实际含义。

### R22-F10　在 TUIC、Hysteria2 上也写入 TCP 使用的 uTLS 指纹

**严重程度：分流错误；特定私密出站建好后无法正常拨号。**

**位置与实跑：**[generator/nodes.py:128–146](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L128-L146)、同文件第 169–178、490、516 行。用仓库合成样例，只给 TUIC 和 Hysteria2 增加相同的常规浏览器指纹；两者都被保留、都生成 `tls.utls.enabled: true`，均没有提示。取值试验用的是 **Trojan**（`handoff/notes/r22_singbox_enum_sweep.py:41–43`），不覆盖 QUIC 拨号。

**源码确认：**mihomo 的 [TUIC](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/tuic.go#L34-L71) 和 [Hysteria2](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/hysteria2.go#L39-L72) 选项没有 `client-fingerprint`。sing-box 却会[真正启用 uTLS](https://github.com/SagerNet/sing-box/blob/v1.14.1/common/tls/client.go#L100-L108)。例如 TUIC [使用 QUIC 拨号](https://github.com/SagerNet/sing-quic/blob/v0.7.0/tuic/client.go#L165-L171)，Hysteria2 [创建 QUIC Transport](https://github.com/SagerNet/sing-quic/blob/v0.7.0/hysteria2/client.go#L288-L297)，都需要其[标准 TLS 配置](https://github.com/SagerNet/sing-quic/blob/v0.7.0/quic.go#L166-L208)；[1.14.1 的 uTLS 实现明确对这个调用返回错误](https://github.com/SagerNet/sing-box/blob/v1.14.1/common/tls/utls_client.go#L77-L83)。[1.12.0 的相应接口](https://github.com/SagerNet/sing-box/blob/v1.12.0/common/tls/utls_client.go#L49-L56)与[该版 QUIC 依赖](https://github.com/SagerNet/sing-quic/blob/v0.5.0-beta.3/quic.go#L34-L69)有同样限制。这是普通客户端模式的源码结论，没有向真实节点拨号。

**建议：**这两种源协议保留正常 TLS，并按 mihomo 实际行为忽略该浏览器指纹且报告；不要连合法的证书校验字段一起去掉。测试“组合”，而非只测试指纹字符串。

### R22-F11　五个旧浏览器指纹能通过 check，却被换成通用 Chrome

**严重程度：文档不符 / 建议；私密出站握手参数。**

**位置与实跑：**[generator/nodes.py:94–96](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L94-L96)、同文件第 128–146 行；`docs/06-已知限制与待决事项.md:364–369`。以 `chrome_psk` 为例，生成器照写、没有提示。**源码确认：**[mihomo 的表](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/component/tls/utls.go#L89-L100)分别选择历史 ClientHello；[sing-box 1.14.1](https://github.com/SagerNet/sing-box/blob/v1.14.1/common/tls/utls_client.go#L371-L376) 和 [1.12.0](https://github.com/SagerNet/sing-box/blob/v1.12.0/common/tls/utls_client.go#L243-L248) 把 `chrome_psk`、`chrome_psk_shuffle`、`chrome_padding_psk_shuffle`、`chrome_pq`、`chrome_pq_psk` 全部落到 `HelloChrome_Auto`。`check` 成功只证明认这个名字。没有断言所有这类服务都会拒绝连接。

**建议：**把“能启动”与“保留指定指纹”分成两列。按本项目不静默改关键参数的约定，这五个没有等价写法的显式选择应在转换时单独报告并跳过；测试它们有别于普通 `chrome`。

### R22-F12　订阅解析器在部分普通标量上仍与 go-yaml v3 不同，甚至中止整份解析

**严重程度：导入失败 / 文档不符；私密配置生成阶段。**

**位置：**[generator/nodes.py:562–601](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L562-L601)；`docs/06-已知限制与待决事项.md:369` 说“订阅按 mihomo 的读法解析”。原报告关于 `0123` 的指责**不成立**：两边都得到 83。其他标量尚未对齐。

**实跑对照：**未加引号的日期形状文字 `2026-02-30` 和不构成整数的 `0x_` 在本项目都令整次 `load_clash_proxies` 抛 `ValueError`，还没进入逐条跳过逻辑。go-yaml v3.0.5 [解析日期失败后继续尝试，若仍不匹配则保留原串](https://github.com/yaml/go-yaml/blob/v3.0.5/resolve.go#L180-L209)，亦见[返回文字和日期校验](https://github.com/yaml/go-yaml/blob/v3.0.5/resolve.go#L260-L265)。此外，超过 uint64 的十进制整数在 Python 仍为整数，Go 会继续尝试浮点；`1_0.5` 在本项目为字符串，Go 去下划线后识别为浮点。用作文字字段时，这会绕过项目对浮点值的拒绝，写出与 mihomo 不同的内容。

**建议：**按固定版本的整数范围、去下划线、日期与数值尝试顺序决定类型；隐式解析不成功时保留原文。保留对不能安全转换的真实浮点值的单条提示。用固定 Go 版本产生的类型和值做小型对照表，覆盖整份订阅有好有坏时的结果。

### R22-F13　普通 YAML 映射有重复键时，转换器悄悄采用最后一项

**严重程度：安全或泄漏；有歧义的私密输入。**

**位置：**[generator/nodes.py:562–575](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L562-L575)、同文件第 596–602 行：`SubscriptionLoader` 继承 PyYAML 的映射构造，没有显式重复键检查。用两个同名的无敏感标记读入，结果只剩最后一个，没有错误。mihomo 的 [provider 用 YAML 解码接收订阅](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/provider/provider.go#L377-L393)，[固定版本的 go-yaml](https://github.com/yaml/go-yaml/blob/v3.0.5/decode.go#L767-L782)会拒绝映射中重复出现的同一显式键。若冲突的是证书校验等字段，两端的差别就不只是提示。没有使用真实订阅，没有证据表明已有资料泄漏。

**建议：**在 `SubscriptionLoader` 的映射构造阶段拒绝显式重复键，只报键名和行号，不输出值；区分合法的 YAML 合并继承与同一映射内的显式重复。为普通键、嵌套键和合法继承各加一个测试。

### R22-F14　带引号的端口被当成十进制，有时连的不是订阅指定的端口

**严重程度：分流错误；私密 SFA 出站。**

**位置与实跑：**[generator/nodes.py:363–374](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/nodes.py#L363-L374) 直接使用 Python `int(value)`。对带引号的标量 `"0100"`，转换器写出十进制 100；`"0x01bb"` 则被跳过。以 VMess 为例，[mihomo 的端口字段是 int](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/vmess.go#L53-L61)，[弱类型解码按 Go 的基数 0 读字符串](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/common/structure/structure.go#L131-L155)，这两个值分别是十进制 64、443。反过来，例如字符串 `"08"` 是 Python 接受、Go 按该路径不接受的写法。此处讨论的是**引号中的端口字符串**，和 C3 所说未加引号的 `0123` 是不同层。

**建议：**端口从源字段的实际类型入手，字符串走与 Go 等价的基数和语法，再做 1–65535 的范围校验；不要把布尔值当数字 1。测试要断言最终输出的端口，不只检查能生成。

### R22-F15　“港英、港德”在完整香港地名内部也能命中

**严重程度：分流错误；公开词表，实际影响取决于订阅命名。**

**位置：**[source/regions.yaml:197–201](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/source/regions.yaml#L197-L201) 把这些简称当作不受上下文限制的外国词；[generator/regions.py:976–984](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/generator/regions.py#L976-L984) 遇到这类词，优先归“其他地区”。单字“港”的负向判断不能约束这几个独立的词。

**实跑：**使用两个公开街道名组成的虚构标签“香港英皇道”“香港德輔道西”。`b9a9f14` 的分类器、宽正则、严正则均识别为香港；`f60ee42` 的分类器和宽正则均只给“其他地区”，严正则也不再进香港。可对照[香港地政总署公布的街道名称](https://www.landsd.gov.hk/doc/en/street-name/Gazetted_Street_Name.pdf)。两个正则引擎得出同一结果，并不能证明这个地区判断正确。没有估计这类名字在真实订阅里的比例。

**建议：**对“港英、港德”等**简称本身**加左侧上下文限制，使其不在完整“香港”词尾内部命中；同时用本轮已经正确的独立简称、以及完整香港地名做成双向测试。不需要扩大成一律排除“港加、港澳”等字串。

### R22-F16　变异检查仍可能把别的测试失败记在预设测试头上

**严重程度：建议；影响验收证据，非 43 条历史记录全错。**

**位置：**[tools/check_mutations.py:53–76](https://github.com/ixxooxo-alt/proxy/blob/f60ee428e4bfc5472b1450f6bfbcc553322e83f4/tools/check_mutations.py#L53-L76) 已认真检查正常结束、FAILED 汇总和非空失败列表，但判“符合预期”用的是 `expect_in_output in out`，不是在那个失败项或其断言中核对。**实跑 / 代码对照：**M82（同文件第 331–332 行）的预期词“国外默认”在本次**零失败**的常规测试输出中就已出现；M185（第 632–635 行）只检查 `test_generated_outputs_pass`，`tests/test_strict.py:447` 与 `tests/test_simple.py:561` 各有一个同名方法，`tests/test_stash.py:30` 还有一个更长的同前缀方法。只要别的地方确有一项失败，当前两个条件就可能拼出“发现”。基线全绿不能消除这个歧义。

**建议：**逐个变异登记允许失败的完整 `模块.类.方法`，与解析出的失败列表精确相交；若还需断言文字，只在该项的失败详情里找。加一条反向测试：其他测试失败、通过的测试恰好打印预期词，应判未发现。不要把这一工具缺口倒推成某条归档的变异一定没有被测试发现。

