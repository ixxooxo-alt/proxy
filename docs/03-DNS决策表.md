# DNS 决策表

总原则：走代理的连接把域名交给代理服务器远端解析，本机不需要知道真实 IP；本机只在“直连”“需要按 IP 判断归属”“解析代理节点自己的域名”三种情况下查询 DNS。

| 场景 | mihomo | sing-box | Loon | Quantumult X | 验证方法 |
|---|---|---|---|---|---|
| 国内服务解析 | `nameserver-policy` 把 GeoSite cn / private 交给 223.5.5.5、1.12.12.12 的 DoH；直连出站用 `direct-nameserver`（同一组 DoH）。r14 起，在它之前先把默认走代理的组的产品域名交给境外 DoH（和 sing-box 的“产品规则先于国内域名集合”对齐；见最后一节“出站时的解析”） | DNS 规则把 geosite-cn 交给 `dns-cn`（223.5.5.5 DoH，直连）；直连出站用 `default_domain_resolver: dns-cn`。产品规则里走代理组的域名先判断、不进这一条（见下面“sing-box：产品规则先于国内域名集合”） | `doh-server` 223.5.5.5 / 1.12.12.12。官方文档：同时配置时优先用加密 DNS，并发查询全部服务器、取最先返回的；加密 DNS 查询失败时默认回落到普通的 `dns-server`（这个行为可以在 App 的 DNS 服务器页面关掉） | `doh-server` 同上。配置里还写了两个国内 UDP 的 `server=`：官方示例说明，设了 DoH / DoQ 之后，系统 DNS 和没有绑定域名的普通 `server=` 都会被忽略，所以这两条只在去掉 DoH 时才起作用；DoH 查询失败时怎么办，官方示例没有写（❓） | 访问国内站点，查看返回的 IP 是否为国内节点；抓包确认没有发往境外 DNS |
| 境外服务解析与出口 | fake-ip：不在本机解析；需要按 IP 判断时，`nameserver`（1.1.1.1、8.8.8.8 DoH）按规则经代理发出（`respect-rules`） | fake-ip：产品规则里走代理组的域名和未分类域名的 A / AAAA 查询直接给假地址；其他类型的查询（HTTPS / SVCB 等）和“需要按 IP 判断”时的解析，用经“国外默认”发出的 `dns-foreign`（1.1.1.1 DoH） | 标准版（`loon.conf`）：命中域名规则的连接不在本机解析；没有命中任何域名规则的域名，要先用上一行的国内 DNS 解析，再按 IP 规则判断（见下方“已知取舍”第一条，结论是有条件的）。严格版（`loon-strict.conf`，2026-10-06）：这类域名不解析，直接走国外默认，见“Loon / Quantumult X：严格版”一节 | 同 Loon（`quantumultx.conf` / `quantumultx-strict.conf`） | mihomo / sing-box：抓包确认本机无明文 DNS 发往境外；Loon / QX：确认命中产品规则的域名不产生本机 DNS 查询 |
| 代理节点自身域名 | `proxy-server-nameserver` 用国内 DoH，直连查询，避免“要代理才能解析代理”的循环。节点的服务器如果是局域网里的名字（`gateway.lan`、不带点的主机名），由 `proxy-server-nameserver-policy` 交给 `system`（系统 DNS）——节点这条路不看 `nameserver-policy`，见最后一节“mihomo：三个解析器各管各的”（2026-10-05，审核 r10 的 R10-F01；要内核 v1.19.20 或更新） | `route.default_domain_resolver: dns-cn`（国内 DoH，直连）。节点的服务器如果是局域网里的名字（`gateway.lan`、不带点的主机名），这个节点另写 `domain_resolver: dns-local`（系统 DNS）——见下面“sing-box：拨号时的解析不看 DNS 规则”（2026-10-05） | 由 App 处理。官方文档的“节点”一页写了顺序：“节点服务器域名的解析顺序为：匹配到的 Host Map、节点的 server-dns、SSID DNS、全局 DNS。”（https://nsloon.app/docs/Node/ ，2026-10-06 查阅；`server-dns` 要 3.5.2 (996) 及以上）。按这句话，`[Host]` 里 `*.lan = server:system` 这几行对节点服务器也起作用：服务器是 `gateway.lan` 的节点由系统 DNS 解析，公网域名的节点由全局 DNS（国内 DoH）解析。没有在 App 里验证。**更正**：r11 的文档写的是“官方文档没有写这一点”，当时只查了“DNS”“DNS 映射”两页，漏看了“节点”这一页 | 由 App 处理。服务器是局域网名字的节点由谁解析，官方示例配置里没有写，也没有验证 | 断开所有代理组后重启客户端，节点仍能连上。有自建在局域网里的节点时：看它能不能连上 |
| 局域网、公司内网、本地名称 | `nameserver-policy` 第一条把 `+.lan/+.local/+.localdomain/+.home.arpa/+.localhost` 交给 `system`（系统 DNS：内核从系统读到的 DNS 服务器，通常是路由器 / 公司下发的，但不保证——2026-10-07 更正，见最后一节“`system` 指的是谁”）；`direct-nameserver-follow-policy: true` 让 DIRECT 连接的解析也走这条；`fake-ip-filter` 让它们拿真实地址；局域网段与这些后缀在规则第 2 阶段固定直连（2026-09-30 审核 F04 后补上，以前这些名字会被发给公共 DoH）。这一行管的是访问目标；节点自己的服务器地址见上一行 | DNS 规则把这些后缀交给 `dns-local`（系统 DNS）；局域网段固定直连。以域名形式到达直连出站的局域网名字，路由里先用一条 `resolve` 规则交给 `dns-local` 解析（2026-10-05，见“sing-box：拨号时的解析不看 DNS 规则”一节） | `[Host]` 里 `*.lan` 等交给 `server:system`；`real-ip` 不给假地址；`skip-proxy`、`bypass-tun` 排除私有网段 | `server=/*.lan/system` 等；`dns_exclusion_list`；`excluded_routes` | 访问 NAS / 打印机 / 路由器管理页；公司内网另在 `local.yaml` 加规则 |
| 系统联网检测 | Windows NCSI、Apple 强制门户等拿真实 IP 并固定直连 | 同左 | 同左（real-ip） | 同左（dns_exclusion_list） | Wi-Fi 图标不再误报“无网络”；酒店 / 机场 Wi-Fi 能弹出登录页 |
| 应用自带 DNS（HTTPDNS） | 未拦截：不等于广告，默认不启用（`adblock.yaml` 的 httpdns 为空） | 同左 | 同左；`hijack-dns` 接管发往 8.8.8.8 / 1.1.1.1 等的明文 53 端口查询 | 同左 | 对具体 App 实测：拦截后能否回退系统 DNS |
| 浏览器安全 DNS（DoH） | 浏览器自己加密查询，客户端看不到；fake-ip 失效时靠嗅探 SNI 恢复域名（sniffer） | `sniff` 动作恢复域名 | `sni-sniffing = true` | ❓ 依赖 App 自身行为 | 浏览器开 / 关安全 DNS 各访问一次，看是否命中同一策略 |
| 域名识别失败、直接 IP 连接 | 按 IP 规则：局域网 → Telegram 等专属段（不解析）→ 国内 IP → 国外默认 | 同左 | 同左 | 同左（专属段规则会触发解析，见限制） | 用 IP 直接访问一个国内、一个境外地址 |
| IPv6 | `dns.ipv6: false` 不返回 AAAA；内核 `ipv6: true` 仍处理 IPv6 字面地址连接。这是交付的配置：Clash Verge Rev 开虚拟网卡时会改写 `dns.ipv6`、补上 IPv6 假地址段（最后一节） | `strategy: ipv4_only`；TUN 同时有 IPv6 地址，IPv6 流量按规则处理 | `ip-mode = ipv4-only` | `no-ipv6`（官方：只让 AAAA 失败） | 关闭 AAAA ≠ 所有 IPv6 路径都受控：需在双栈网络下用 IPv6 字面地址测试是否仍经 TUN 与规则 |
| 缓存 | 内核缓存；`store-fake-ip` 保存映射 | `cache_file.store_fakeip` | 运行期 LRU，退出清空（官方） | App 内 | 重启客户端后已打开的连接是否正常 |

## 已知取舍

- **Loon / Quantumult X 上没有命中域名规则的域名**（2026-10-03 审核 F06：以前这里写“结果仍会走国外默认”，少了条件）。这两端没有引入第三方的“国内 / 国外域名大集合”（其中含宽泛关键词规则，违背收录要求），所以一个域名如果没有命中任何产品规则和广告规则，就要先在本机解析、再按 IP 规则判断。分开说：
  - **谁看得到查询**：解析用的是国内 DNS（223.5.5.5、1.12.12.12 的 DoH），所以国内 DNS 能看到这些域名。这是这两端的已知代价，不能说成“四端都不让国内 DNS 看到境外域名”。Loon 另有一条：加密 DNS 查询失败时默认回落到普通 DNS（`dns-server` 里的 223.5.5.5、119.29.29.29，明文 UDP），这个开关在 App 里；Quantumult X 的官方示例则说设了 DoH 后普通 `server=` 会被忽略，两端不能互相套用。
  - **最后走哪里**：取决于解析出来的 IP。不是国内 IP → 落到最后一条规则，走国外默认（连接交给代理时带的是域名，由代理服务器再解析一次）。**是国内 IP → 命中 `GEOIP,CN`，直连。** 境外网站在国内有 CDN 节点、域名解析被污染到国内地址、或者和国内服务共用基础设施时，都会走到这个分支。所以只能说“解析结果不是国内 IP 时走国外默认”，不能保证所有没分类的境外域名都走国外默认。本项目没有在你的网络上观测过实际的解析结果。
  - **对使用的实际影响**（2026-10-04 你问到的，归纳在这里）：只涉及这两端上规则里没有列到的域名，Google、YouTube、ChatGPT 这些有规则的不经过国内 DNS。① 国内 DNS 看得到你访问了哪些这类域名（只有域名，看不到内容）。② 解析出境外地址的照常走国外默认；国内 DNS 给的地址即使不对也不影响，因为代理服务器会自己再解析一次。③ 解析出国内地址的会直连：网站在国内有 CDN 的，通常没有问题；被污染成国内地址的，这个网站会打不开——遇到时把域名告诉我，按域名加一条规则。这种情况在你的网络上实际有多少，没有观测过。④ 每个新域名第一次访问多一次本机解析。
  - mihomo / sing-box 的同一类域名也按 IP 判断（国内 IP 直连是有意的设计），区别只在解析走的是经代理发出的境外 DoH，国内 DNS 看不到。
  - **2026-10-06 起另有严格版**：上面说的都是标准版。你问“国外 IP 的时候不泄露国内 DNS”以后，这两端各多生成了一份严格版，反过来做——先按域名认出国内网站，其余域名不在本机解析、直接走代理。标准版没有改，两份可以在 App 里随时切换。做法、依据、代价见“Loon / Quantumult X：严格版”一节。以前这里写的“可以做而没有做的：给这两端加一份境外域名集合”是另一种做法（列出境外域名），没有采用：境外域名列不全，没列到的仍然要先问国内 DNS。
- **mihomo 上的整段 `.ms`**（2026-10-04，你的决定：不更正、跟随上游）：MetaCubeX 的国内域名集合里有整段后缀 `ms`，mihomo 的路由（`GEOSITE,cn`）和 DNS（`nameserver-policy` 的 `geosite:cn`）用的是同一个集合，所以没有被产品规则接住的 `.ms` 域名在 mihomo 上由国内 DNS 解析并直连。有规则的 `.ms` 域名（`aka.ms`、`1drv.ms` 等）按各自的组走，走代理时不在本机解析。sing-box 的集合里没有这一条。详见 `docs/06`“2026-10-04”一节。
- **Quantumult X 的专属 IP 段**：没有 no-resolve，域名连接走到 Telegram 段规则时会先解析；只影响没有命中任何域名规则的连接。
- **IPv6**：所有端的配置都选择“不返回 AAAA”（mihomo 这一条在 Clash Verge Rev 开虚拟网卡时会被 App 改掉，见最后一节）。这只阻止多数应用主动走 IPv6，不控制应用直接使用 IPv6 字面地址的情况；那部分流量在 TUN 模式下仍会按规则走（国内 IPv6 直连、其余走国外默认），在系统代理模式下可能绕过客户端。
- **局域网后缀的来源**：四端都从 `source/project.yaml` 的 `lan.domain_suffix` 生成（mihomo 的 `nameserver-policy` 和节点专用的 `proxy-server-nameserver-policy`、sing-box 的 `dns-local` DNS 规则、路由里的 `resolve` 规则和节点上的 `domain_resolver`、Loon 的 `[Host]`、QX 的 `server=/…/system`），改一处四端同步。公司自定义的内网域名（不在这些后缀下的）：把后缀加进 `lan.domain_suffix`，四端的解析和直连规则、两个内核对节点服务器的处理一起生效（`tests/test_dns_lan.py` 用一个虚构的后缀核对过 mihomo 和 sing-box）。只在 `local.yaml` 里加直连规则是不够的：`local.yaml` 现在改不了这份后缀列表，那样加的域名在 mihomo 下仍由国内 DoH 解析。要留意 `project.yaml` 是公开的统一源的一部分，加进去的后缀会出现在公开产物里；需要“只进私密产物”的写法时告诉我，现在没有。`.local` 的 mDNS 名字是否能解析取决于系统 DNS，未实测。
- **不带点的主机名作为访问目标**（`http://nas/`、`http://printer/`；r10 核对 sing-box 拨号解析时顺带看的，r11 查清了 mihomo 上 DNS 那一半。这部分规则 r10、r11 都没有动，以前的版本同样如此）：局域网的规则只认后缀（`.lan`、`.local` 等）和私有网段，不认“没有点的名字”。分两种情况：
  - 设备先查 DNS（TUN 模式下的常见情况）。mihomo 把这个查询交给了**国内的公共 DNS**，它不认识这个名字，解析失败。原因在上游数据：MetaCubeX 的 `private` 集合里有一条正则 `^[a-z]([a-z0-9-]{0,61}[a-z0-9])?$`，匹配“字母开头的单个标签”，这类名字于是落到 `nameserver-policy` 里 `geosite:cn,private → 国内 DoH` 那一条。官方 v1.19.31 实测，记成了固定用例（`tests/cases.yaml` 的 `mihomo_dns`，标了 `limit`）。sing-box 给的是假地址（r10 时的一次性核对）。
  - 名字原样到了内核（经 HTTP / SOCKS 代理端口）。官方 mihomo v1.19.31、sing-box v1.14.1 / v1.12.0 都没有规则命中，交给国外默认（r10 时的一次性核对，没有做成固定用例）。

  平常不容易遇到：系统多半会先补上路由器下发的搜索域（变成 `nas.lan`，按局域网处理），或者用 mDNS / NetBIOS 这类不经过 DNS 的方式找到设备，系统代理的例外名单通常也包含本地名字。遇到打不开时改用带后缀的名字或 IP。mihomo 上 DNS 那一半改起来只要一行（在 `nameserver-policy` 最前面加 `'*': [system]`），sing-box 要另写 DNS 规则，Loon 没有查到依据，Quantumult X 没有能表达“不带点”的规则类型；经代理端口的那一半还要各端另加路由规则。做不做、做到哪几端，列在 `docs/06` 待决事项第 14 项。**节点自己的服务器地址是另一回事**：不带点的节点服务器名字在 mihomo、sing-box 上都已经交给系统 DNS（最后两节）。

## sing-box：产品规则先于国内域名集合（2026-10-04）

起因是 2026-10-03 审核 F01 的 DNS 部分：sing-box 的 DNS 规则里，“国内域名集合 → 国内 DNS”排在假地址之前；而上游的国内域名集合会收一些本项目交给代理组的域名（`qwen.ai`、`apple.com.cn`、`music.apple.com`、`recaptcha.net`、`google.cn`、B 站港澳台用的几个接口主机……）。以前这些域名先被国内 DNS 解析成真实地址，连接再按域名规则交给代理组：路由没错，但国内 DNS 看得到查询，代理拿到的也是国内解析出来的地址。

现在 DNS 规则的顺序（`generator/emit_singbox.py` 的 `dns_layers`）：

| 顺序 | 匹配 | 去向 |
|---|---|---|
| 1 | 局域网后缀 | `dns-local`（系统 DNS） |
| 2 | 需要真实地址的域名（联网检测、NTP、运营商认证等） | `dns-cn` |
| 3 | 产品规则里“更具体”的那几层，和路由用同一条“更具体的规则优先”：走代理组的 → A / AAAA 给假地址，其他查询类型给 `dns-foreign`；被更具体的“国内直连”规则划出去的（目前只有 `delivery.mp.microsoft.com`）→ `dns-cn` | 见左 |
| 4 | 产品规则里走代理组的全部域名（内联规则集 `product-proxied`：656 个后缀、108 个精确主机，DNS 规则引用两次，只写一份） | A / AAAA → `dns-fakeip`；其他查询类型 → `dns-foreign` |
| 5 | 上游的国内域名集合 `geosite-cn` | `dns-cn` |
| 6 | 其余 A / AAAA | `dns-fakeip` |
| 最后 | 其余查询类型 | `dns-foreign` |

说明：

- “走代理组”包括默认直连的 Apple、Apple Music/TV、Apple Push（2026-10-06 加的）三个组：给假地址之后，组选直连时由直连出站用国内 DNS 解析（和以前一样），组切到某个地区时由代理解析——不会出现“组已经切到美国，地址还是国内 DNS 解析的”。
- 第 2 步有一处和这个设计不一致，2026-10-06 的逐条扫描查出来的：“需要真实地址的域名”整个名单都交给 `dns-cn`，而其中几个名字的路由并不是直连（`time.windows.com` 归 Microsoft 组，`pool.ntp.org` 落到国外默认）。见“走代理的域名不交给国内 DNS”一节和 `docs/06` 待决事项第 15 项。
- 归“国内直连”的产品规则（国内常用网站等）不用写进第 3、4 步：它们本来就由第 5、6 步处理，结果和以前一样。
- mihomo 不需要对应的改动：fake-ip 模式下，命中域名规则的连接不在本机解析，域名直接交给代理；`nameserver-policy` 里的国内集合只在需要解析时才用得到。这句话只管“fake-ip 生效、内核收到的是域名”这条路；浏览器自带的安全 DNS、被排除在 fake-ip 之外的名字、直接按 IP 发起的连接不在这句话的范围里（2026-10-04 审核 r9 时审核方指出的边界）。**2026-10-07 更正**（GPT 审核 r13 的 R13-F01）：这句只对“规则判断”和“TCP 经普通代理协议”成立。mihomo 转发 UDP 时，几乎所有代理协议都先在本机解析目标域名，WireGuard 这类出口连 TCP 也是，用的正是 `nameserver` / `nameserver-policy`——上游国内集合收了、规则又交给代理组的域名（`qwen.ai` 等）就被交给了国内 DNS。所以 mihomo 也需要这一层，r14 加了，见最后一节。
- 验证：22 条 DNS 去向用例（`tests/cases.yaml` 的 `singbox_dns`；2026-10-06 加了一条 Apple Push 的），官方内核 v1.14.1 与 v1.12.0 实际查询的结果、自制模拟器、人工期望三者一致；另对全部“期望走代理组”的主机逐个检查 A 查询得到假地址、HTTPS 查询交给 `dns-foreign`（`tests/test_real_data.py`）。自检：把第 3、4 步拿掉，官方内核把 `chat.qwen.ai`、`music.apple.com` 的 A 查询交给了 `dns-cn`。日志 `docs/evidence/real-route-check.log`。
- 没有验证的：配置变大（52 → 78 KB）之后 SFA 的导入与启动耗时；真实网络下的解析结果。

## sing-box：拨号时的解析不看 DNS 规则（2026-10-05）

起因是 2026-10-04 对 r9 的审核（F02）。sing-box 里有两条互不相干的解析路径：

| | 什么时候用 | 交给哪个 DNS 服务器 |
|---|---|---|
| 普通 DNS 查询 | 设备上的程序查域名（TUN 接管了 53 端口的查询） | 按 `dns.rules` 逐条匹配：局域网后缀 → `dns-local`，国内域名 → `dns-cn`，其余给假地址…… |
| 拨号时的解析 | 内核自己要连一个“域名形式”的地址：代理节点的 `server`，或者直连出站收到的目标仍是域名 | 出站自己的 `domain_resolver`；没有写就用 `route.default_domain_resolver`。**不经过 `dns.rules`** |

依据是 sing-box v1.14.1 的源码：`common/dialer/dialer.go` 的 `NewWithOptions` 在出站没有指定解析器时，把 `route.default_domain_resolver` 对应的服务器填进查询选项；`dns/router.go` 的 `Lookup` 在查询选项里已经带了服务器时直接向它查询，不走按域名分流的那段规则。官方文档：`https://sing-box.sagernet.org/configuration/shared/dial/` 的 `domain_resolver`、`https://sing-box.sagernet.org/configuration/route/` 的 `default_domain_resolver`。

r9 及以前，`default_domain_resolver` 是 `dns-cn`（国内 DoH），所有出站都没有单独指定。后果有两个，都只在特定条件下出现：

- 节点的 `server` 写的是只有路由器 / 公司 DNS 认识的名字（`gateway.lan`、`proxy.home.arpa`、不带点的 `homeproxy`）时，这个名字被拿去问公共的国内 DNS：解析不到，节点不可用，内部名字也泄露给了公共 DNS。
- 直连出站收到的目标是域名、又是局域网名字时，同样去问 `dns-cn`。公开模板只有 TUN 入站，平常访问 NAS 不走这条路：普通 DNS 查询先经 `dns-local` 得到局域网 IP，连接是按 IP 直连的。自己加了 HTTP / SOCKS 入站、让程序把域名原样交给内核时才会遇到（核对时用的就是这种入站）。审核方也是这样界定范围的：不把它说成只有 TUN 的成品上的普遍故障。

这一版的改法（只动这两处，别的解析策略不变）：

| 改动 | 写在哪 | 效果 |
|---|---|---|
| 节点的 `server` 是局域网里的名字时，给这个节点写 `domain_resolver: dns-local` | `generator/emit_singbox.py` 转换节点时；只出现在带节点的私密配置里 | 这个节点的服务器名字由系统 DNS 解析 |
| 路由规则里，在“局域网后缀 → 直连”之前加一条 `{"domain_suffix": [局域网后缀], "action": "resolve", "server": "dns-local"}` | 公开模板和私密配置都有；排在嗅探、DNS 劫持之后 | 目标是局域网名字的连接，先用系统 DNS 解析成地址，再直连 |

“局域网里的名字”指：不带点的主机名（公共 DNS 不可能认识），或者在 `lan.domain_suffix`（`lan`、`local`、`localdomain`、`home.arpa`、`localhost`）之下的名字。IP 地址不算；`lan.example.com` 这种只是名字里有 lan 的公网域名不算。

没有改的：`route.default_domain_resolver` 仍是 `dns-cn`。公网域名的节点、直连的公网域名继续由国内 DNS 解析——这是本来的设计（节点域名要在代理起来之前就能解析，直连的国内网站要拿到国内的地址）。把默认解析器整个换成系统 DNS 会把这两件事一起改掉。

验证（事实）：

- 官方 sing-box v1.14.1（1.14 版配置）和 v1.12.0（兼容版配置）各实际拨号一遍，7 个用例，结果与人工写的期望一致（`tests/cases.yaml` 的 `singbox_dial`；日志 `docs/evidence/real-route-check.log`）：节点 `gateway.lan`、`proxy.home.arpa`、`homeproxy` → `dns-local`；节点 `node.example.com`、`lan.example.com` → `dns-cn`；直连目标 `nas.lan` → `dns-local`；直连目标 `www.baidu.com` → `dns-cn`。
- 这一项保留了真实的拨号过程：节点是本机一个没人监听的端口上的 SOCKS 出站，直连出站保持直连；三个 DNS 服务器换成本机的替身，不管问什么都答 127.0.0.1（所以拨号不会离开本机），看的是“这个名字被拿去问了哪一个替身”。以前的路由 / DNS 核对把直连换成了拒绝，正好绕开了拨号——审核方指出的就是这一点。
- 自检：把这两处修正拿掉再跑，`gateway.lan`、`proxy.home.arpa`、`homeproxy`、`nas.lan` 都被拿去问了 `dns-cn`——问题确实存在，修正确实起作用。
- 写盘前的结构检查另加三项：`resolve` 规则、出站的 `domain_resolver`、`route.default_domain_resolver` 指向的 DNS 服务器必须存在。

没有验证的：

- 真实网络、真实节点、TUN 接管下的表现；SFA 里 `local` 类型的 DNS 服务器在 VPN 接管以后实际向谁查询（取决于 SFA 的实现，没有核对）。
- sing-box 1.13；SFA 内置的内核版本。
- 公司自定义的内网域名（不在上面那几个后缀之下）：它们作为节点服务器或直连目标时仍由 `dns-cn` 解析。需要时把后缀加进 `source/project.yaml` 的 `lan.domain_suffix`（四端一起生效，见上面“局域网后缀的来源”）。

## mihomo：三个解析器各管各的（2026-10-05）

起因是 2026-10-05 对 r10 的审核（R10-F01），和上一节 sing-box 的问题是同一类。mihomo 内核里，按“谁要解析这个名字”分成几条路，各有各的服务器和例外策略（下表；第四行是 2026-10-07 补的，它和第一行用的是同一个解析器）：

| 谁要解析 | 用哪些服务器 | 例外策略写在哪 | 局域网里的名字，这一版交给谁 |
|---|---|---|---|
| 设备上的程序发来的 DNS 查询（TUN 接管的查询） | `nameserver` | `nameserver-policy` | 局域网后缀 → `system`（策略的第一条） |
| 直连出口连接域名形式的目标 | `direct-nameserver` | 开了 `direct-nameserver-follow-policy` 时先看 `nameserver-policy` | 同上 |
| 节点连接自己的服务器（订阅里每个节点的 `server`） | `proxy-server-nameserver` | `proxy-server-nameserver-policy`。**不看 `nameserver-policy`** | 局域网后缀、不带点的名字 → `system`（这一版加的） |
| 代理出口为连接解析目标：转发 UDP 时几乎所有协议都这样，WireGuard 这类出口连 TCP 也是（GPT 审核 r13 的 R13-F01） | `nameserver`（默认的解析器） | `nameserver-policy` | 同第一行；r14 起，走代理组的产品域名交给境外 DNS（最后一节） |

依据：mihomo v1.19.31 的源码 `dns/resolver.go`（`NewResolver`：节点用的解析器 `ProxyResolver`，服务器取自 `ProxyServer`、策略取自 `ProxyServerPolicy`；直连用的 `DirectResolver` 在 `DirectFollowPolicy` 为真时共用主解析器的策略）、`config/config.go` 的 `parseDNS`；官方说明 https://wiki.metacubex.one/en/config/dns/ 的 `proxy-server-nameserver-policy` 一节（大意：格式与 `nameserver-policy` 相同，只用于节点域名的解析，`proxy-server-nameserver` 不为空时才生效）。

r10 及以前，只在 `nameserver-policy` 里写了“局域网后缀 → `system`”，又开了 `direct-nameserver-follow-policy`：前两条路是对的，第三条路没有写例外。后果只在特定条件下出现：节点的 `server` 写的是只有路由器 / 公司 DNS 认识的名字（`gateway.lan`、`proxy.home.arpa`，自己搭在家里或公司内网的代理）时，这个名字被拿去问国内的公共 DoH——解析不到，节点不可用，内部名字也发给了公共 DNS。服务器是公网域名或 IP 的节点不受影响。

这一版的改法，只在 dns 段加一个字段（`generator/emit_mihomo.py` 的 `node_server_dns_policy`）：

```yaml
dns:
  proxy-server-nameserver: ['https://223.5.5.5/dns-query', 'https://1.12.12.12/dns-query']   # 没有动
  proxy-server-nameserver-policy:
    +.lan,+.local,+.localdomain,+.home.arpa,+.localhost: [system]
    '*': [system]
```

- 第一条由 `lan.domain_suffix` 生成，是审核方建议的写法。`+.lan` 同时匹配 `lan` 本身和它下面的任意多级。
- 第二条是不带点的主机名（`homeproxy`）。审核方的建议里没有这一条，并提醒“不带点的节点名应按实际需求另行明确”。这里明确为：交给系统 DNS。理由有两条：公共 DNS 不可能认识一个不带点的名字；sing-box 那边从 r10 起就是这样判断的（上一节），同一个节点在两个内核上的处理应该相同。依据：mihomo 官方对通配符的说明（“`*` 只匹配 localhost 等没有 `.` 的主机名”，https://wiki.metacubex.one/handbook/syntax/）、源码 `component/trie/domain.go`，以及下面官方内核的实际结果。它只写在节点这条策略里，**不影响访问目标**（“已知取舍”里“不带点的主机名作为访问目标”那一条没有变）。
- `proxy-server-nameserver` 没有清空，也不能清空：`respect-rules` 和这条策略都要求它不为空，否则内核拒绝加载。两种情况各用官方内核试过，报错记在 `docs/evidence/official-check.log`；生成器写盘前也会检查这两条（`generator/verify.py`）。
- 公网域名的节点照旧由国内 DNS 解析，这是本来的设计。

验证（事实）：

- 官方 mihomo v1.19.31 实际跑了一遍，结果与人工写的期望一致（用例在 `tests/cases.yaml` 的 `mihomo_dial`、`mihomo_dns`；日志 `docs/evidence/real-route-check.log`）：
  - 节点 `gateway.lan`、`proxy.home.arpa`、`homeproxy` → 系统 DNS；节点 `node.example.com`、`lan.example.com` → 国内 DNS。
  - 直连目标 `nas.lan` → 系统 DNS；直连目标 `www.baidu.com` → 国内 DNS。
  - 设备查询 `printer.lan`、`nas.home.arpa` → 系统 DNS；`www.taobao.com` → 直接给假地址，不向上游查询；不带点的 `printer` → 国内 DNS（已知限制的现状，见“已知取舍”）。
- 做法和 sing-box 那一项相同：保留真实的拨号过程，只把 DNS 换成本机替身。生成的配置里规则、DNS 段的结构原样；DNS 段里出现的每个服务器按它属于哪一类，换成那一类的替身——`system` 换成“系统 DNS”的替身，国内的 DoH 和明文地址换成“国内”替身，境外 DoH 换成“境外”替身；替身不管问什么都答 127.0.0.1。节点是本机一个没人监听的端口上的 SOCKS 节点，所以每次拨号都落在本机被拒绝，不会有连接离开这台机器。看的是“这个名字被拿去问了哪一类替身”。
- 自检三遍，每遍从 DNS 段里去掉一样东西再跑同一批用例：去掉 `proxy-server-nameserver-policy`，只有三个局域网节点变回国内 DNS（这就是 r10 的情况，与审核方的复现一致）；去掉 `direct-nameserver-follow-policy`，只有直连目标 `nas.lan` 变回国内 DNS；去掉 `nameserver-policy` 里局域网后缀那一条，设备查询的两个局域网名字和直连目标 `nas.lan` 变回国内 DNS，三个局域网节点不变。三处设置各管各的——只写其中一处，另外的路仍然会去问公共 DNS。
- 两个内核的判断一致：测试核对了 mihomo 策略里的通配符和 sing-box 的 `is_lan_name` 对同一批名字的归类相同，两份拨号用例是同一批名字（`tests/test_dns_lan.py`）。
- 一次性核对（脚本不在交付包里）：
  - **更早的内核**：`proxy-server-nameserver-policy` 是 mihomo v1.19.20 加的。拿官方 v1.19.19（文件的 SHA-256 与发布页一致）试这一版的配置：`-t` 通过，这个字段被忽略，三个局域网节点仍去问国内 DNS，其余结果相同。也就是说，内核比 v1.19.20 旧时这处修正不起作用，效果和 r10 一样，不会更糟。
  - **订阅地址在局域网里**（`proxy-providers` 的下载走 `proxy: DIRECT`）：`sub.lan` → 系统 DNS，走的是直连出口那条路；不带点的 `subhost` → 国内 DNS，属于“访问目标”那条限制。
  - v1.19.31 对 dns 段里它不认识的字段不报错、也不警告。

没有验证的：

- **`system` 在真实系统上向谁查询**。核对时把它换成了替身。2026-10-07 把三个系统的源码都读了（GPT 审核 r12 提醒“`system` 不保证就是你家的路由器”），结论在最后一节“`system` 指的是谁”：通常是路由器 / 公司下发的 DNS；配置里写的 `system` 从系统读不到 DNS 时，这次解析失败、不会改问别的服务器（r13 这里写的是“用内置的 114.114.114.114 和 8.8.8.8”，读错了源码，GPT 审核 r13 的 R13-F02）；macOS 上开着 Clash Verge Rev 的虚拟网卡时，按源码推断是 114.114.114.114，这时局域网里的节点解析不到。都没有在真实系统上验证。`nameserver-policy` 里的 `system` 从 r6 起就在用，是同一个东西。
- 真实网络、真实节点、TUN 接管下的表现。
- **客户端有没有把配置文件里的 dns 段原样交给内核**。Clash Verge Rev 有“DNS 覆写”开关；2026-10-06 读了它的源码，行为比 r11 写的清楚了，见最后一节“客户端这一侧”。Clash Meta for Android 有没有类似的设置没有核对。两个客户端内置的内核版本也没有核对。
- Loon / Quantumult X：服务器是局域网名字的节点由谁解析。Loon 官方文档的“节点”一页写了顺序（Host Map 排第一，见开头表格“代理节点自身域名”一行的更正），按它 `[Host]` 的那几行管得到节点服务器，没有在 App 里验证；Quantumult X 的官方示例配置里没有写，不知道。
- 公司自定义的内网后缀：见上面“局域网后缀的来源”。

## Loon / Quantumult X：严格版（2026-10-06）

起因是 2026-10-06 你问的：“国外 IP 的时候不泄露国内 DNS”，能不能在配置里做到。

**标准版为什么做不到**（上面“已知取舍”第一条）：这两端的配置里填的是国内 DNS。一个域名没有命中任何域名规则时，App 要先在本机把它解析出来，再按 IP 规则判断它是不是国内的。所以最后从代理出去的连接，域名也被国内 DNS 看到了。两个 App 的官方文档里都没有“让 DNS 查询经代理发出”的选项（Loon 的“DNS”“General”两页、Quantumult X 的 sample.conf，2026-10-06 查阅）；把默认 DNS 换成境外的公共 DNS 是另一回事——查询仍然从本机直接发出，而且会连国内网站一起改掉，你担心的“国内网站解析变慢”正是那种做法的后果，所以没有采用。

**严格版的做法**：这两端各多生成一份配置（`dist/loon/loon-strict.conf`、`dist/quantumultx/quantumultx-strict.conf`），标准版原样保留，两份可以在 App 里切换。严格版把判断顺序反过来：

| 连接的目标 | 严格版怎么处理 | 谁解析这个域名 |
|---|---|---|
| 有产品规则的域名（ChatGPT、YouTube、Apple……） | 和标准版一样，按规则走各自的组 | 走代理的由代理那一端解析；组选直连时由本机用国内 DNS 解析 |
| 广告集合里的域名 | 和标准版一样，拦截 | 不解析 |
| 国内域名清单里的域名 | 国内直连 | 本机用国内 DNS 解析——和标准版一样，国内网站的解析没有变 |
| “要真实地址的名单”里的名字（NTP、运营商号码认证等 8 条，`source/project.yaml` 的 `dns.real_ip`） | 固定直连 | 本机用国内 DNS 解析（它们本来就不给假地址） |
| **其余全部域名** | **不在本机解析，直接交给“国外默认”** | 代理那一端。国内 DNS 看不到这个域名 |
| 原本就是 IP 的连接 | 和标准版一样按 IP 规则：局域网直连、Telegram 等专属段、国内 IP 直连、其余走国外默认 | 不涉及 |

两端的写法不同，各有各的依据：

**Loon**（`generator/emit_loon.py`，`strict=True`）

- `[Rule]` 里 28 条按 IP 判断的规则全部带 `no-resolve`，包括最后一条 `GEOIP,CN,国内直连,no-resolve`（标准版只有这一条不带，它就是靠解析来认国内网站的）。依据：官方文档“IP 规则”一页写着加了 `no-resolve` 以后“规则只匹配目标地址已经是 IP 的请求，不会为域名执行 DNS 查询”；“规则”一页“匹配优先级”的原话是“目标地址为域名时，先匹配域名规则。域名规则未命中时，再解析 DNS 并匹配 IP 规则。其他规则按配置顺序匹配，越靠前优先级越高。”和“规则来源优先级为：本地规则 > 插件规则 > 订阅规则”（https://nsloon.app/docs/Rule/ ，2026-10-06 查阅）。
- `GEOIP` 能不能加 `no-resolve`：官方“逻辑规则”一页的例子里有 `OR,((DOMAIN-SUFFIX,example.com),(DEST-PORT,443),(GEOIP,CN,no-resolve)),DIRECT`（https://nsloon.app/docs/Rule/logic_rule/ ）。**单独一行的 `GEOIP,CN,策略,no-resolve` 没有官方例子**，这是推断，要在真机上看（`docs/09`）。它不被接受时最坏的两种结果：这一行被忽略（按 IP 访问的国内地址改走代理，影响很小），或者 `no-resolve` 被忽略（没被接住的域名又在本机解析，严格版悄悄退回标准版的行为）——后一种只有按 `docs/09` 的步骤才看得出来。
- `[Remote Rule]`：广告集合两条 → blackmatrix7 的 `ChinaMax_Domain.list`（上游直接订阅，交给国内直连）→ 本项目的自有清单 `loon/rules/cn-domains.list`。先后的依据是上面那句“按配置顺序匹配，越靠前优先级越高”；官方没有专门说多条订阅规则之间怎么排，这是按那句话的理解，要在真机上看（`docs/09`：清单里的域名下的广告主机仍然被拦）。
- **订阅的上游文件里也有按 IP 判断的规则**：广告集合的第一个文件有 187 条 IP 段。“全部 IP 规则都不为域名解析”要连它们一起算——本地规则带不带 `no-resolve` 由生成器保证、写盘前检查；上游文件的内容本项目管不到。按固定快照读，这 187 条全部带 `no-resolve`（订阅规则文件里这样写有官方例子：Loon 官方示例仓库的 `Rule/ExampleRule.lsr` 里就是 `IP-CIDR,91.108.4.0/22,no-resolve`）；另外两个文件没有 IP 规则。`tools/check_real_routes.py` 每次核对时都数一遍、记进快照，有不带的就报不符合，测试核对记录是 0（审核方提醒“要检查全部有效规则，包括远程订阅”以后加的）。上游哪天把 `no-resolve` 去掉了，Loon 严格版里没被接住的域名会为那几条规则在本机解析——带着新数据重跑这个工具能发现，手机上看不出来。你自己在 App 里另加的规则、插件也一样：里面有不带 `no-resolve` 的 IP 规则，严格版就不严了。

**Quantumult X**（`generator/emit_qx.py`，`strict=True`）

- Quantumult X 没有 `no-resolve`。官方 sample.conf 给的办法是加一条接住全部域名的规则，原文：“You can add below host-keyword rule to skip the DNS query for all the non-matched hosts. Pure IP requests won't be matched by the host related rules.”，示例行是 `;host-keyword, ., proxy`，位置在 `ip-cidr` / `geoip` / `ip-asn` 几行之后、`final` 之前。由此可知域名类规则先于 IP 类规则判断，原本就是 IP 的连接不受这条规则影响——所以**IP 规则一条都不用拿掉**。（我在对话里一度说“只能拿掉全部按 IP 判断的规则”，是错的，GPT 指出来以后核对属实。）
- 这条“域名兜底”没有照官方示例写进本地规则，而是做成一个远程规则文件（`quantumultx/rules/domain-fallback.list`，里面只有 `HOST-KEYWORD,.,proxy` 一条），在 `[filter_remote]` 里排最后，用 `force-policy=国外默认` 指定去向。原因：本地规则优先于全部远程规则，兜底写在本地会把远程的广告集合和国内域名清单全部挡在后面。官方仓库有一条用户报告说的就是这件事（crossutility/Quantumult-X 的 issue #251，报告时未关闭）；报告里的临时办法是给远程资源加 `inserted-resource=true`，sample.conf 里出现过这个参数但没有解释，本项目没有用。
- `[filter_remote]` 的顺序：广告集合 → 自有清单 `quantumultx/rules/cn-domains.list`（国内直连）→ 域名兜底（国外默认）。
- **没有官方依据、靠推断的两点**：远程资源之间按书写顺序；远程资源里的域名规则先于本地的 IP 规则。都要在真机上看。
- 兜底是远程资源，**它没有加载成功时严格版悄悄退回标准版的行为**，App 不会提示（模拟器里验证过这一点，`tests/test_strict.py`）。所以验收步骤里第一件事是看这三个资源有没有加载出来。
- 不带点的主机名（`http://nas/`）不含“.”，兜底接不住，仍然按标准版的办法处理。

**国内域名清单用的是什么数据**

| | 来源 | 规模 | 谁用 |
|---|---|---|---|
| 自有清单 | domain-list-community 的 `cn` 列表（`tld-cn` 加 `geolocation-cn`），按固定快照 `c1c2cf0d`（2026-09-22）展开，MIT 授权。sing-box 用的 `geosite-cn` 也源自它。由 `tools/update_cn_list.py` 生成到 `source/data/cn-domains.txt`，再转成两端各自的写法放在 `dist/…/rules/` | 后缀 6,142 条、精确域名 12 条，含整段 `.cn` 等 49 个顶级域；写进规则文件的是 6,132 条（另 22 条已被本地规则覆盖，例如 `qwen.ai` 本地规则让它走国外默认，清单里就不再写它） | Loon、Quantumult X |
| blackmatrix7 `ChinaMax_Domain.list` | 上游文件，配置里直接订阅它的地址（内容跟着上游变）。mihomo 用的 `geosite:cn` 就是从它来的：MetaCubeX 的数据仓库说明里写着“`geosite:cn` 源替换为 ios_rule_script/ChinaMax_Domain”（https://github.com/MetaCubeX/meta-rules-dat ，2026-10-06 查阅）；拿固定快照和 2026-10-05 的 `geosite.dat` 逐条比，`geosite:cn` 的 111,224 条里有 110,712 条在这份清单里同值出现，其余的差别里包括 `geosite:cn` 的 52 条整段顶级域（一次性核对，2026-10-06） | 按固定快照 `51d2e1d` 读：111,277 条，只有域名和后缀两类，**不含整段顶级域** | 只有 Loon |

- 为什么要自己生成一份：Loon 那份上游大清单不含整段 `.cn`；Quantumult X 没有可以直接订阅的成品——blackmatrix7 给它的只有 `ChinaMax.list`，里面混着 13 条关键词规则（`baidu`、`aliyun`、`stripe` 等，含这些字样的域名都会被当成国内）和 65 条 UA 规则。
- 所以**两端认得的国内网站不一样多**：只在大清单里的域名，Loon 严格版直连，Quantumult X 严格版走代理。差多少（2026-10-07 按两份严格版完整的域名规则顺序逐条算——本地规则在前，远程规则按书写顺序，两端都是广告集合排在国内清单之前；按固定快照 `51d2e1d`；脚本和输出在 `handoff/notes/r13_strict_routes.*`）：大清单的 111,277 条里，**Loon 严格版直连、Quantumult X 严格版交给国外默认的 105,317 条（94.6%）**；两端都由国内清单直连的 5,715 条；两端都先被拦掉的 152 条（远程广告集合 149 条、本地广告规则 3 条）；两端按本地规则交给同一个组的 93 条（Microsoft 54 条、国内直连 13 条、Google 10 条等）。后缀条目改用一个子域来算，是 105,380 条（94.7%）。**更正**：r13 这里写的是“105,446 条（94.8%）在 Loon 严格版直连、在 Quantumult X 严格版走代理”。那个数只扣掉了 Quantumult X 自有清单和本地规则接得住的条目，没有扣两端都排在前面的远程广告集合，不是两端实际分流不同的条目数（GPT 审核 r13 的 R13-F03；它找到 20 条反例，按完整顺序算是 152 条两端都拦截）。这些都是**条目数**，不能换算成实际访问里有多少比例会走代理。r13 时的分析仍然有效：`.cn` 结尾的自有清单全部接得住；随手挑的 30 个常见大站（百度、淘宝、京东、B 站、支付宝、招商银行等）也都接得住——这 30 个不是严格统计，接不住的大多是小网站、公司官网（`handoff/notes/qx_strict_coverage.*`）。要让 Quantumult X 也用上大清单，得在你的仓库里放一份转换过的副本，而 blackmatrix7 的仓库是 GPL-2.0，这件事没有替你决定，列在 `docs/06` 待决事项第 19 项。
- 清单和兜底文件放在你自己的仓库里，严格版按 `https://raw.githubusercontent.com/ixxooxo-alt/proxy/main/dist/…` 引用。**仓库的 `main` 更新到这一版之前，这三个地址打不开，严格版用不了**；以后文件改名、仓库改成私有，引用它们的规则也会失效。

**代价和它改变的东西**（都记成了用例，`tests/cases.yaml`）

- 清单里没有的国内网站走代理：能打开，会慢，有的网站会因为是境外 IP 而显示不同的内容。标准版里它们解析出国内 IP 就直连。这是严格版换来“不让国内 DNS 看到”的代价，没有办法两头都要。遇到常用的网站被这样处理，把域名告诉我，加进清单或者加一条规则。
- 反过来，清单里有、但解析到境外 CDN 的国内网站：标准版走代理，严格版直连（和 mihomo / sing-box 一致）。
- “要真实地址的名单”固定直连：`time.apple.com`、`time.windows.com` 在标准版里跟着 Apple、Microsoft 组；`pool.ntp.org` 在标准版里落到国外默认。
- `id6.me`、`log.cmpassport.com`（运营商号码认证）：上游的广告集合收了它们，标准版里被拦；严格版里固定直连的本地规则排在远程广告集合之前，不拦（`docs/06` 待决事项第 18 项）。
- 国内 DNS 仍然看得到的：国内域名清单里的域名、组选直连时的域名（Apple 等默认直连的组）、代理节点自己的服务器域名、局域网以外的“要真实地址的名单”。这些都是直连所必需的解析。
- 没被接住的域名由代理那一端解析：用的是你的节点所在位置的 DNS，这一点由机场决定，配置管不到。

**验证到什么程度**

事实（都不是真机）：

- 两份严格版和标准版相比，策略组、节点订阅、DNS、其余设置逐行相同；本地规则只多出“要真实地址的名单”8 条，Loon 另把 `GEOIP,CN` 加上 `no-resolve`；远程规则只在后面多出上面说的几条（`tests/test_strict.py`，`docs/evidence/与上一版的对比.md` 第六节）。
- 自制模拟器按官方文档描述的顺序判断：280 条用例和排除项，在样本数据和真实上游数据下，两份严格版的结果都符合人工写的期望；251 个域名里没有一个需要“为了判断 IP 规则而在本机解析”（标准版是 44 个）。严格版和标准版去向不同的主机，只有用例里写明的那几类。
- 写盘前的结构检查会拦住：Loon 严格版有 IP 规则没带 `no-resolve`、国内清单排在广告集合前面或者没有、Quantumult X 的兜底不是最后一条 / 交给了别的组 / 用了 `inserted-resource`、引用的自有文件没有生成、兜底文件里不是那一条规则。
- 自有清单与按固定快照重新生成的逐字节相同（`docs/evidence/cn-list-check.log`）。

没有验证的（全部要靠真机，步骤在 `docs/09` 的“严格版”一节）：

- 两个 App 是否接受这些写法、规则先后是否如上面所说、没被接住的域名是否真的不产生本机 DNS 查询。
- 六千条 / 十一万条的远程规则在手机上的加载时间和内存占用。Loon 官方文档“订阅规则”一页说它“支持数十万条规则”，并给了一组数字（iPhone 15 Pro、Loon 3.2.0 (712)：20 万条 `DOMAIN` / `DOMAIN-SUFFIX` 规则的查询在 1 毫秒以内），说的是匹配速度，不是加载时间和内存；Quantumult X 没有查到类似的说明。
- 上游大清单的格式（每行一个域名，“.”开头表示含子域）在 Loon 官方文档里没有写，和广告集合的第二个文件是同一种情况（`docs/06` 待决事项第 11 项）。
- **严格版只保证“为了判断规则，不在本机解析”**（GPT 审核 r12 第 3 点：这是验证的边界，不是已经复现的漏洞）。下面这些路径不在这个保证里，也都没有验证：
  - 手机上的程序自己发出的 DNS 查询，尤其 A / AAAA 以外的类型，比如 HTTPS（类型 65；较新的 iOS 访问网站时会连同 A / AAAA 一起查它，这是我的一般了解，没有在这两个 App 里核对过）。两个 App 对这类查询是直接回空应答，还是转给 `[dns]` 里的国内 DNS，官方文档没有写。会转的话，没被接住的域名的这一部分查询国内 DNS 仍然看得到。mihomo 上的同一个问题见下面“逐条扫描”一节的第二类和待决事项第 16 项。
  - 浏览器自己的安全 DNS（DoH）；程序缓存了地址以后直接按 IP 连接（那样走的是 IP 规则）；你自己在 App 里另加的规则、插件；系统在隧道之外发出的流量。
  `docs/09` 第 1b 节第 3、4 步能看出其中一部分。

## 走代理的域名不交给国内 DNS：三项固定核对与逐条扫描（2026-10-06；2026-10-07 修订）

这一节说的是 mihomo（Clash Verge Rev / Clash Meta for Android）和 sing-box（SFA）。r12 加的是检查：把“国外的连接，名字不要让国内 DNS 看到”这句话拆成能用官方内核实际跑的几项。r14（2026-10-07）加了第 ④ 项“出站时的解析”，并按它查出来的问题改了 mihomo 的 `nameserver-policy`（最后一节）。做法沿用拨号核对的办法（`tools/check_real_routes.py`）：内核是官方发布的程序（mihomo v1.19.31，sing-box v1.14.1 和 v1.12.0），系统 / 国内 / 境外三类 DNS 各换成一个本机替身，看“这个名字被哪个替身收到过”。

**四项固定核对**（用例在 `tests/cases.yaml` 的 `mihomo_dial`、`singbox_dial`、`mihomo_dns`、`singbox_dns`、`outbound_resolve`，期望是人工写的；结果在 `docs/evidence/real-route-check.log`）

| 核对 | mihomo | sing-box（两个版本结果相同） |
|---|---|---|
| ① 有规则、走代理组的域名（`www.youtube.com`、`gemini.google.com`、`chat.qwen.ai`），内核处理这个连接的全过程 | 三类替身都没有收到关于它的查询 | 同左 |
| ② 没有被任何域名规则接住的域名（虚构的 `never-listed-site.org`、泄露测试网站那一类的 `r1.test.dnsleaktest.com`） | 只有境外 DNS 的替身收到（为了判断最后的 `GEOIP,CN` 要解析一次） | 只有 `dns-foreign` 的替身收到（路由里的 `resolve` 动作） |
| 对照：国内直连的公网域名（`www.baidu.com`） | 国内 DNS 的替身收到 | `dns-cn` 的替身收到 |
| 设备发来的 DNS 查询 | 走代理的域名和哪个集合里都没有的域名：A 查询直接给假地址，AAAA、HTTPS 查询直接回空应答，都不向上游查询；TXT 这类其他类型交给境外 DNS——r14 起 `qwen.ai` 的 TXT 也是（r13 时交给国内 DNS）；`tlu.dl.delivery.mp.microsoft.com` 的 TXT 交给国内 DNS（Microsoft 下面更具体的国内直连规则）。AAAA 那条用例（`google.cn`）是 2026-10-07 加的；这一行说的都是交付的原始配置，Clash Verge Rev 开虚拟网卡时 AAAA 可能变成假的 IPv6 地址（最后一节） | A 查询给假地址；其他类型交给 `dns-foreign`（以前就有的 22 条用例） |
| ③ 境外 DNS 不应答：把境外替身改成只收不答，每个连接保持 14 秒不断开（mihomo 的 DNS 超时是 5 秒，sing-box 是 10 秒），同一批连接和查询重跑一遍 | 收到查询的替身与正常那一遍完全相同：连接 6 条、查询 13 条，其中 5 条只有境外替身收到 | 同左：连接 6 条、查询 22 条，其中 6 条只有境外替身收到 |
| ④ 出站时的解析（r14 加）：走代理的组换成真的出口（连本机一个没人监听的端口），分别发 TCP 连接和 UDP 包，看出口自己会不会再解析目标域名、交给谁（8 个主机） | TCP 经 SOCKS5：走代理的域名都没有被解析；转发 UDP、经 WireGuard 时在本机解析——走代理的域名只问境外 DNS（r13 时 `qwen.ai`、`download.microsoft.com` 问的是国内 DNS），直连的（`www.qq.com`、Apple、微软更新下载）问国内 DNS。自检：把产品域名那一层去掉，WireGuard 下这两个变回国内 DNS | SOCKS 的 TCP、UDP：域名原样交给节点，没有解析；WireGuard 端点按 DNS 规则解析，走代理的域名问 `dns-foreign`；`time.windows.com` 问 `dns-cn`（待决事项第 15 项） |

第 ③ 项能说明的只有这些：**在这次“境外替身只收不答”的测试里**，14 秒的观察时间内，内核没有转去问国内 DNS 或系统 DNS，那个连接只是失败。别的失败方式——连接被重置、TLS 证书出错、HTTP 报错、返回 SERVFAIL——没有试；替身是 UDP 的，真实配置里是 DoH；真实节点、真实 DoH 的全链路、App 改写过的配置也都没有验证。所以它不能说成“境外 DNS 不管怎么连不上都不会回落”。支持同一方向、但不是实测的两点：配置里没有给境外查询安排国内的 `fallback`（`tests/test_dns_lan.py` 有静态断言）；mihomo v1.19.31 的解析器在没有 `fallback` 时直接返回主服务器的结果或错误（源码 `dns/resolver.go` 的 `ipExchange`）。（2026-10-07 按 GPT 审核 r12 第 5 点收窄：r12 这里写的是“境外 DNS 连不上时”，说宽了。）

**逐条扫描**（`tools/dns_route_consistency.py`；r12 叫它“全集一致性”，2026-10-07 按 GPT 审核 r12 第 4 点改名，因为它不是“全部域名”的证明）

上面的用例只有十几个名字。另外把“名字会交给国内 DNS”的集合整个拿出来，逐条取代表主机（条目本身；后缀条目再取它的一个子域），看路由有没有把它交给代理组；再反过来把配置里每条域名规则的值也查一遍。判断用自制模拟器加读进来的真实集合；走代理组的每个主机和按固定间隔抽出来的 200 个主机，再交给官方内核实际跑，核对模拟器没有算错。

| | 扫了多少 | 名字会交给国内 DNS 的 | 其中路由是国内直连 / 直连 / 拦截 | 归默认直连、可切换的组（Apple） | 走代理组 |
|---|---|---|---|---|---|
| sing-box（两个版本相同） | 19,531 个代表主机（`geosite-cn` 的 9,303 条，加规则的值） | 17,679 | 17,673 | 1 | **5** |
| mihomo（r14） | 224,266 个（`geosite:cn` 的 111,224 条、`private` 的 131 条，加规则的值） | 222,593 | 222,361 | 10 | **222** |

官方内核核对：sing-box 每个版本 206 个主机（路由结果、A 与 HTTPS 查询的去向都与模拟器相同）；mihomo 432 个主机（路由结果与模拟器相同，TXT 查询都由国内 DNS 的替身收到；r13 时是 574 个，少的就是下面第二类）。自检：把 sing-box DNS 规则里“走代理组的产品域名”那一层拿掉再扫，走代理组的从 5 个变成 152 个；r14 起 mihomo 也做同样的自检——把 `nameserver-policy` 里产品域名那一层拿掉再扫，走代理组的从 222 个变成 364 个，多出来的 142 个交给官方内核查 TXT，现在都只由境外 DNS 的替身收到。这项核对看得见它要防的错误。

表里的数都是**代表主机**的个数：只对这份快照（2026-10-05 的上游数据）和“条目本身加一个子域”这种取法成立，不是互联网上实际受影响的主机有多少。它也不是“全部合法域名、全部规则组合”的证明：正则和关键词覆盖的范围、比代表主机更深的子域、手动切换过的策略组、客户端改写过的配置、真实的解析结果都不在里面（下面“没有覆盖的”）。

（r13 时 mihomo 这一行是 222,733 / 222,359 / 10 / **364**：r14 在 `nameserver-policy` 里加了产品域名那一层，下表第二类的 142 个没有了；`delivery.mp.microsoft.com` 和它的一个子域从“境外 DNS”变成“国内 DNS、直连”，所以第二、三列各多 2 个。）

“走代理组”的那些就是“名字交给国内 DNS、连接却从代理出去”的情况。下面是现状的如实记录；第二类 r14 改了，另外两类没有改：

| 类别 | 哪一端 | 是什么 | 实际影响 | 待决事项 |
|---|---|---|---|---|
| “要真实地址的名单”里路由不直连的名字 | sing-box 的 5 个代表主机：`time.windows.com`（Microsoft 组）、`pool.ntp.org` 和它的子域（国外默认）、`icitymobile.mobi` 和它的子域（没有域名规则，按解析到的 IP 决定）。`time.apple.com` 归 Apple 组，默认直连，组切到代理时也属于这一类 | DNS 规则的第二条把这份名单整个交给 `dns-cn`，名单里的名字不一定直连 | 国内 DNS 看得到这几个名字的查询；它们是对时和运营商认证用的，不是你访问的网站。标准版的 Loon / Quantumult X 同理（名单里的名字先在本机解析）；严格版把它们固定直连了 | 第 15 项 |
| 上游的国内域名集合收了、路由靠产品规则交给代理组的域名（**r14 已改，这一类没有了**） | r13 时 mihomo 的 142 个代表主机：`qwen.ai`、`google.cn`、`aka.ms` 等几个 `.ms` 域名、`bilibili.tv`、`download.microsoft.com` 这一批微软下载主机、B 站港澳台用的几个接口主机等 | r13 的 `nameserver-policy` 里只有“国内域名集合 → 国内 DNS”，没有 sing-box 那样“走代理组的产品域名先判断”的一层 | r12、r13 写的是“按交付的原始配置，只影响地址以外的查询类型（TXT、SRV），连接本身不解析，影响面很窄”——**说错了**（GPT 审核 r13 的 R13-F01）：设备查 A 得到假地址、AAAA / HTTPS 是空应答这一半是对的（2026-10-07 一次性核对过，GPT 也独立复测过）；但 mihomo 转发 UDP（例如浏览器的 QUIC）时、经 WireGuard 这类出口时，会在本机用这份策略解析目标域名，这些名字就交给了国内 DNS（官方内核实测，`handoff/notes/r13_review_probes.r13.out`）。r14 按你的决定在 `nameserver-policy` 里加了“走代理组的产品域名 → 境外 DNS”一层（最后一节），这一类没有了 | 第 16 项（已改，r14） |
| 上游 `private` 集合里的名字 | mihomo 的 222 个代表主机：反向解析域（`10.in-addr.arpa` 这类，190 个）、保留后缀（`test`、`invalid`、`internal`、`example`）、路由器登录域名（`tplinkwifi.net`、`router.asus.com` 等） | `nameserver-policy` 的那一条写的是 `geosite:cn,private`，`fake-ip-filter` 又让它们拿真实地址；路由上只有局域网后缀固定直连 | 这些名字本来就该由路由器回答，交给国内的公共 DNS 多半解析不到或者解析错。和“不带点的名字”是同一个原因 | 第 14 项 |

另有一条不在扫描范围里、但性质相同的已知限制：四个客户端的“国内直连”都是可以切换的组（直连 / 国外默认，默认直连）。把它切到“国外默认”以后，sing-box 仍然先按 DNS 规则把国内域名集合里的域名交给 `dns-cn` 解析，再把连接交给代理（`docs/06` 待决事项第 17 项）；mihomo 和 Loon / Quantumult X 上，被域名规则接住的部分不在本机解析。

**这些核对没有覆盖的**

- 真实的虚拟网卡路径。核对用的是本机的代理端口和临时的 DNS 端口，不是 TUN；系统在 TUN 之外自己发出的 DNS 查询（见下一节）内核看不到，这里也看不到。
- 境外 DNS 的那条连接本身从哪里出去。配置里境外 DNS 是 1.1.1.1 / 8.8.8.8 的 DoH，mihomo 开了 `respect-rules`、sing-box 写了 `detour: 国外默认`；固定核对里它们被换成了本机替身。2026-10-06 做过一次性的核对（不在交付包里）：mihomo 用回真实的 DoH 地址时，日志里是 `[TCP] mihomo --> 1.1.1.1:443 match Match using 国外默认`，即这条连接按规则交给了国外默认。
- 代表主机只有“条目本身和它的一个子域”，正则条目（sing-box 8 条、mihomo 1 条）取不出代表主机，没有扫。
- 境外 DNS 除了“只收不答”以外的失败方式（见第 ③ 项下面那段）。
- 客户端改写过的配置：上面的结果都是交付的原始配置跑出来的；Clash Verge Rev 开虚拟网卡时会改 dns 段，“DNS 覆写”、扩展配置也能改（最后一节）。
- 解析结果是假定的（没列出的主机按境外 IP 算），只影响“没被域名规则接住、靠 IP 决定去向”的那几个主机。

## 客户端这一侧：哪些设置会让上面的设计不成立（2026-10-06；2026-10-07 补充）

配置文件只管得到“内核收到的流量和查询”。下面这些在 App 或系统里，配置文件管不到；每个客户端要手动确认的清单在 `docs/01`“每个客户端要手动确认的开关”，这里记依据。除了写明“官方文档”的，都是读源码得到的，**没有在 App 里验证**。

- **要用虚拟网卡（TUN）模式。** 只开系统代理时，不认系统代理的程序自己去问系统 DNS，内核看不到。系统代理和虚拟网卡同时开没有问题，两条路进的是同一个内核、同一份 dns 段。
- **Clash Verge Rev 的“DNS 覆写”**（读的是 v2.5.7 标签和 2026-10-05 的 dev 分支 `30f05a7`，`src-tauri/src/enhance/mod.rs` 的 `merge_dns_config`；更新日志 v2.5.4、v2.5.5、v2.5.7）：
  - v2.5.4 起，覆写只盖掉界面里**填了值的字段**，没填的保留配置文件里的（按字段整个替换，不是往里合并：界面里填了 `nameserver-policy`，配置文件里的那一整张表就被换掉；布尔值填“关”不算填了值）；订阅自带 DNS 设置时打开覆写要先确认，订阅更新以后覆写自动关闭；v2.5.5 起按订阅分别记忆；v2.5.7 修了“确认开启的覆写重启后被自动关闭”。界面上的原话是“如果你不清楚这里的设置请不要修改，并保持 DNS 覆写关闭”。
  - **更正**：r11 的文档只说它“近几个版本行为有变动”，依据是问题单；现在按源码写清楚了。结论不变——保持关闭。
- **Clash Verge Rev 开虚拟网卡时会改写 `dns.ipv6`**（`src-tauri/src/enhance/tun.rs` 的 `use_tun`）：fake-ip 模式下，它把 `dns.ipv6` 设成和顶层的 `ipv6` 一样；顶层的 `ipv6` 又会被 App 自己保存的设置盖掉（`merge_default_config`，App 的模板默认是 `true`）。也就是说，本项目写的 `dns.ipv6: false`（不返回 AAAA）在这个客户端开着虚拟网卡时，实际跟着 App 设置里的 IPv6 开关走。这是 App 自己的那一步；在它之后，你自己加的“扩展配置 / 扩展脚本”还可以再改这个值，“DNS 覆写”开着并且管着这一项时又以它为准（v2.5.7 源码里有一项测试专门区分这两种情况，审核方指出的）——所以最后是什么，要看 App 里的运行时配置，不能只按这里推。想保持“不返回 AAAA”，把 App 里的 IPv6 开关关掉。
  - **IPv6 开关开着时还多一样**（GPT 审核 r12 第 4 点指出，2026-10-07 核对源码属实）：配置里没有 `fake-ip-range6` 时，`use_tun` 会补上 `2001:2::0/64`（v2.5.7 `tun.rs` 第 46–48 行；开着“DNS 覆写”时 `enhance/mod.rs` 的 `ensure_fake_ip_range6` 也会补）。mihomo v1.19.31 只在顶层 `ipv6` 开着、而且本机有公网 IPv6 地址时才用这一段（`config/config.go` 的 `parseIPV6`），用了以后，走 fake-ip 的名字的 AAAA 查询拿到的是这一段里的假地址，不再是空应答。拿官方内核照这个改法试过（一次性核对，`handoff/notes/r12_review_probes.*`）：当作机器有公网 IPv6 时，r13 时归为待决事项第 16 项的那 142 个主机的 AAAA 都拿到了 `2001:2::` 开头的假地址，HTTPS 仍是空应答，三类 DNS 替身都没有收到查询；没有公网 IPv6 时仍是空应答。它改变的是“设备拿到什么地址”，不是“查询交给谁”。本项目文档里“AAAA 为空”的说法都只指交付的原始配置。
  - macOS 上它还会在开虚拟网卡时把系统 DNS 改成 114.114.114.114（官方常见问题页写的是 223.6.6.6，以源码为准），这是为了让系统的 DNS 查询能被虚拟网卡接到。做法是 `networksetup -setdnsservers`，改的是默认路由所在网卡对应的那个网络服务（v2.5.7 `scripts/set_dns.sh`）。它的一个连带后果见下面“`system` 指的是谁”。
- **Clash Verge Rev 的“严格路由”在 App 里开，开完看一眼运行时配置**（2026-10-07 按 GPT 审核 r12 第 6 点改了说法）：v2.5.4 的更新日志写着“优化 TUN 配置优先级：界面设置优先”。v2.5.7 的源码里，App 自己保存的设置中 `tun` 下**有**的那几项（`constants.rs` 的 `GUI_KEYS`，含 `strict-route`）会盖到配置文件的 `tun` 段上，之后的扩展配置、扩展脚本也改不动它们（`enhance/mod.rs` 的 `merge_default_config`、`gui_tun_keys`、`enforce_tun`）。全新安装时 App 的设置按模板生成，模板里有 `strict-route: false`（`config/clash.rs` 的 `template`），所以常见的情况下，配置文件里写的 `tun.strict-route: true` 会被盖成 false——本项目没有写它。**r12 这里写的是“写在配置文件里不起作用，只能在 App 里开”，说得太绝对**：App 只在保存的设置里完全没有 `tun` 这一段时才补模板（`IClashTemp::new`），保存过 `tun`、却不含 `strict-route` 的时候，配置文件里写的值不会被盖掉。准确的做法是：在 App 的界面里开，再在运行时配置里看 `tun.strict-route` 是不是 `true`。它的作用，mihomo 官方文档的说法是在 Windows 上“添加防火墙规则以阻止 Windows 的普通多宿主 DNS 解析行为造成的 DNS 泄露”——Windows 会同时向各个网卡的 DNS 发查询，不开的话物理网卡那一路会绕过虚拟网卡。副作用：内核示例配置的注释说打开以后别的设备访问不到这台电脑；官方文档说它“可能会使某些应用程序（如 VirtualBox）在某些情况下无法正常工作”。读了内核用的 sing-tun 的 Windows 实现：先读的是 MetaCubeX/sing-tun 2026-10-02 的代码 `f870488`；2026-10-07 又读了 mihomo v1.19.31 的 `go.mod` 钉的 v0.4.24（GPT 审核 r12 引的也是这一版），两者的 `tun_windows.go` 只差一处——`f870488` 在拦掉 IPv6 之前多放行三种 IPv6 邻居发现报文——所以下面的描述对 v0.4.24 同样成立：它拦的是本机向外发起的、目标端口 53 的连接（放行内核自己的进程和虚拟网卡上的连接），虚拟网卡没有 IPv6 地址时另外拦掉全部 IPv6 出站；另外它把虚拟网卡的 DNS 设成虚拟网卡上的地址。它管的是“发往 53 端口的查询走不走虚拟网卡”，不是“所有 DNS 都被接管”：程序自己用 DoH（443 端口）或者别的端口的加密 DNS，不在它的范围里。macOS 的实现里没有用到这个选项。
- **`system` 指的是谁**（2026-10-07；GPT 审核 r12 第 11 点提醒“`system` 不保证就是你家的路由器”。下面是读 mihomo v1.19.31 源码的结论，没有在真实系统上验证）。本项目把局域网后缀（`nas.lan` 这类访问目标，和服务器是局域网名字的节点）交给 `system`，意思是“问系统设置里的 DNS”。内核从哪里读：Windows 是“已连接、有网关”的网卡上设置的 DNS（`dns/system_windows.go`）；macOS / Linux 是 `/etc/resolv.conf` 里的 `nameserver`（`dns/system_posix.go`）；Clash Meta for Android 是 App 交给内核的地址（`dns/patch_android.go` 的 `UpdateSystemDNS`；App 那一边传的是什么没有看，推断是当前网络的 DNS）。虚拟网卡自己的 DNS 地址会被排除。**一个都读不到时，这次解析失败**，不会改问别的服务器。**更正**：r13 这里写的是“一个都读不到时，内核用内置的 114.114.114.114 和 8.8.8.8（`dns/system.go`）”，读错了（GPT 审核 r13 的 R13-F02）：那两个地址只属于内核启动时另建的一个全局解析器（`dns/system.go` 第 68–74 行，`resolver.SystemResolver`）；配置里写的 `system` 是另外新建的（`dns/util.go` 第 127–128 行、`dns/system.go` 第 62–66 行），不带这个兜底（第 32–41 行只在兜底列表不为空时才用）。全局那个只在没有可用的解析器时才用（`component/resolver/resolver.go`），本项目的配置开着 DNS，用不到。Clash Meta for Android 版里系统 DNS 由 App 告诉内核（`dns/patch_android.go`），没有时同样没有兜底。这些是读源码的结论，没有实测。所以 `system` 通常就是路由器 / 公司下发的 DNS，但不保证；以前开头的表写成“即路由器 / 公司 DNS”，说满了。已知会不是路由器的两种情况：
  - **macOS 上开着 Clash Verge Rev 的虚拟网卡**：App 把系统 DNS 改成了 114.114.114.114（上面一条），`/etc/resolv.conf` 跟着变（这一步是 macOS 的行为，我按常识推断），内核的 `system` 于是去问 114.114.114.114——路由器才认识的 `nas.lan`、局域网里的节点 `gateway.lan` 都解析不到，这些名字也被发给了这个公共 DNS。推断，没有在 Mac 上验证；验收步骤在 `docs/09` 第 1 节“局域网”一行。
  - **Windows 上照 `docs/01` 开关表里的那句话，不开严格路由、把网卡的 DNS 改成公网地址**：`system` 就是那个公网地址，结果同上。
  这两种情况配置文件改不了（配置里不知道你家路由器的地址）。可以考虑的办法都没有试过：用 IP 地址访问局域网里的设备；mihomo 有“向某个网卡的 DHCP 要 DNS”的写法（`dhcp://网卡名`，`config/config.go`），也许能写进你自己电脑的私密配置——GPT 审核 r13 确认这是官方文档列出的写法（https://wiki.metacubex.one/config/dns/type/ ），可以作为真机验证的候选，但网卡名、DHCP 下发的内容、运行权限都要实际试过，不能直接改成通用的默认值。知道公司内网 DNS 的地址时，也可以只给局域网后缀写明那个地址。用到了再定。
- **mihomo 官方文档写明的两条限制**（TUN 一页，https://wiki.metacubex.one/config/inbound/tun/ ，2026-10-06 查阅）：“在 MacOS/Windows 无法自动劫持发往局域网的 dns 请求”——系统 DNS 填的是路由器地址时，查询不进内核；“在 Android 如开启私人dns 则无法自动劫持 dns 请求”——系统设置里的“私人 DNS”要选“关闭”（“自动”这一档算不算开启，文档没有说）。
- **浏览器自己的“安全 DNS”**：浏览器直接用 DoH 查询，内核看不到这个查询，只能靠嗅探恢复域名（开头表格“浏览器安全 DNS”一行）。查询去了哪家由浏览器的设置决定。
- **Loon**：加密 DNS 查询失败时默认回落到明文的普通 DNS，这个行为只能在 App 的 DNS 服务器页面里关（官方文档“DNS”一页），配置文件里没有对应的字段。
- **Quantumult X**：sample.conf 说设了 DoH / DoQ 以后，系统 DNS 和没有绑定域名的普通 `server=` 都会被忽略；但 `dns_exclusion_list` 里的域名“may or may not follow the settings in [dns] section”。另有一个 `no-system` 参数，本项目没有加：它会不会连配置里明确交给系统 DNS 的局域网名字（`server=/*.lan/system` 等）一起关掉，官方没有写，只有真机能试（`docs/06` 待决事项第 20 项）。
- **DNS 泄露测试网站只是必要检查，不是证明**：它只看得到“那一刻、那一个随机子域名”的查询从哪家 DNS 发出来。看不到别的域名，看不到系统在虚拟网卡之外发的查询，也分不清是规则管住了还是碰巧。测出国内 DNS 说明有问题；没测出来不说明没有问题。

## 出站时的解析：代理出口会不会再解析目标（2026-10-07，r14）

起因是 GPT 审核 r13 的 R13-F01：mihomo 的 WireGuard 出口连接一个还是域名的目标时，用默认的解析器在本机解析它——默认解析器按 `nameserver` / `nameserver-policy` 选服务器，所以 `qwen.ai` 这类“上游国内域名集合收了、规则又交给代理组”的域名被交给了国内 DNS。r12、r13 的文档说“连接本身不解析”，只看了规则判断那一段：固定核对里走代理的组都换成了拒绝出口，拒绝出口不拨号，看不到出口自己的这一步。

**范围比审核报告说的大**（核实时读源码、再用官方内核实测出来的）：

- mihomo v1.19.31 的 `adapter/outbound/base.go` 有一个 `ResolveUDP`：目标还没解析时，用默认解析器在本机解析。socks5、shadowsocks、shadowsocksr、trojan、vmess、vless、hysteria、hysteria2、tuic、snell、anytls、mieru 等出口转发 UDP 前都先调用它（各自的 `ListenPacketContext`）。也就是说，**经普通的代理节点转发 UDP 也一样**——浏览器访问支持 HTTP/3 的网站时用的 QUIC 就是 UDP。WireGuard、OpenVPN、Masque 这类按 IP 转发的出口，连 TCP 也要在本机解析（`wireguard.go` 的 `DialContext`）。只有少数出口能配“远程解析”（WireGuard 的 `remote-dns-resolve` + `dns`，节点上的设置，订阅里的节点一般不带）。
- 官方内核实测（一次性核对 `handoff/notes/r13_review_probes.r13.out`，r13 的配置）：走代理的组换成 SOCKS5、Shadowsocks、Trojan 或 WireGuard 出口（都连本机空端口），`qwen.ai` 走 TCP 经 SOCKS5、Shadowsocks 时没有被解析；走 UDP（SOCKS5、Shadowsocks 试了目标写域名和目标是假地址两种，Trojan 试了目标写域名）、经 WireGuard（TCP、UDP）时，它的 A、AAAA 查询都由国内 DNS 的替身收到。`chatgpt.com` 这类普通境外域名本来就问境外 DNS，不受影响。
- sing-box 1.14.1、1.12.0 实测：SOCKS、Shadowsocks 出口把域名原样交给节点（TCP、UDP 都是），不解析；WireGuard 端点按 DNS 规则解析（`protocol/wireguard/endpoint.go`），DNS 规则里有“走代理组的产品域名先判断”一层，`qwen.ai` 交给 `dns-foreign`。只有待决事项第 15 项那几个名字（`time.windows.com` 等，DNS 规则写明交给 `dns-cn`、路由却走代理组）经 WireGuard 端点时交给 `dns-cn`。
- Loon、Quantumult X：没有能运行的内核，转发 UDP 时会不会在本机解析目标，官方文档没有写，不知道。

**r14 的改动**（待决事项第 16 项，你 2026-10-07 选了“改”；生成器 1.6.0，统一源 2026.10.07-1）：mihomo 的 `nameserver-policy` 在“局域网后缀 → `system`”之后、`geosite:cn,private` 之前，加一条一条的产品域名：

- 交给默认走代理的组的（国外默认、Google、Microsoft……）→ 境外 DoH，和 `nameserver` 是同一份（配置里写成 YAML 的锚点 `&dns-foreign`，每条用 `*dns-foreign` 引用）；现在 739 条。
- 交给默认直连的组的（国内直连、Apple、Apple Music/TV、Apple Push）不放进去：mihomo 的直连连接也按这份策略解析（`direct-nameserver-follow-policy`），放进去的话，Apple 默认直连时会拿境外 DNS 的结果、可能连到远的服务器。例外是被更宽的“走代理”规则包住的直连规则，要写明交给国内 DNS，否则会被外面那一条盖住——现在只有一条：Microsoft 下面的 `delivery.mp.microsoft.com`（Windows 更新的下载）。sing-box 那边把 Apple 那几个组也算作“走代理”的一类，是因为它的直连出站另由国内 DNS 解析（`default_domain_resolver`），和 mihomo 不同。
- 为什么一条一条地写、写在 `geosite:` 前面：mihomo 把相邻的普通域名写法合成一棵域名树，树里越具体的越优先、不看先后（v1.19.31 `dns/resolver.go` 的 `makePolicy`、`component/trie/domain.go`），和路由规则“更具体的优先”一致；`geosite:` 的条目各自单独、按书写顺序，所以这一层要在 `geosite:cn,private` 之前。核对工具的逐条扫描以前按“第一条命中”模拟，r14 改成按域名树算（`tools/dns_route_consistency.py` 的 `DomainTrie`）。

**代价**：这些组你手动切成直连时（例如把 Microsoft 切成 DIRECT 下载更新），它们的名字也由境外 DNS 解析，可能连到离你远的服务器、变慢——sing-box 现在就是这样（DNS 在连接之前就判断完了，见 `docs/06` 待决事项第 17 项那一类）。默认状态下不影响国内网站。

**核对**（都在 `tools/check_real_routes.py`，结果在 `docs/evidence/real-route-check.log`、快照的 `outbound`）：

- 第 ④ 项“出站时的解析”：8 个主机（`tests/cases.yaml` 的 `outbound_resolve`）× mihomo 三种出口（SOCKS5 走 TCP、走 UDP，WireGuard 走 TCP）、sing-box 两种（SOCKS 走 UDP，WireGuard 端点走 TCP），两个 sing-box 版本各跑一遍，结果都与人工期望一致。自检：把 mihomo 的产品域名那一层去掉，WireGuard 下 `qwen.ai`、`download.microsoft.com` 变回国内 DNS，别的不变。
- 逐条扫描的自检：去掉那一层再扫，mihomo 走代理组的从 222 个变成 364 个；多出来的 142 个交给官方内核查 TXT，现在都只由境外 DNS 的替身收到。
- 静态断言（`tests/test_dns_lan.py`）：每条产品规则的值和它的一个子域，路由交给默认走代理的组的，`nameserver-policy` 必须交给境外 DNS；交给默认直连的组的，不能交给境外 DNS（变异 M102、M103）。

**仍然没有覆盖的**

- 默认直连的组你手动切到代理以后（例如把 Apple 切到某个地区），它们的名字仍按 `geosite:cn` 交给国内 DNS——转发 UDP、经 WireGuard 时同样会被国内 DNS 看到。和 sing-box 的待决事项第 17 项是同一类：DNS 不会跟着组的选择变。
- 上游 `private` 集合里的名字（待决事项第 14 项）、sing-box 的“要真实地址的名单”（第 15 项）不受这次改动影响。
- 核对用的是本机的代理端口，不是 TUN；真实节点、真实网络没有试。Loon、Quantumult X 的情况不知道（上面）。
