# DNS 决策表

总原则：走代理的连接把域名交给代理服务器远端解析，本机不需要知道真实 IP；本机只在“直连”“需要按 IP 判断归属”“解析代理节点自己的域名”三种情况下查询 DNS。

| 场景 | mihomo | sing-box | Loon | Quantumult X | 验证方法 |
|---|---|---|---|---|---|
| 国内服务解析 | `nameserver-policy` 把 GeoSite cn / private 交给 223.5.5.5、1.12.12.12 的 DoH；直连出站用 `direct-nameserver`（同一组 DoH） | DNS 规则把 geosite-cn 交给 `dns-cn`（223.5.5.5 DoH，直连）；直连出站用 `default_domain_resolver: dns-cn`。产品规则里走代理组的域名先判断、不进这一条（见下面“sing-box：产品规则先于国内域名集合”） | `doh-server` 223.5.5.5 / 1.12.12.12。官方文档：同时配置时优先用加密 DNS，并发查询全部服务器、取最先返回的；加密 DNS 查询失败时默认回落到普通的 `dns-server`（这个行为可以在 App 的 DNS 服务器页面关掉） | `doh-server` 同上。配置里还写了两个国内 UDP 的 `server=`：官方示例说明，设了 DoH / DoQ 之后，系统 DNS 和没有绑定域名的普通 `server=` 都会被忽略，所以这两条只在去掉 DoH 时才起作用；DoH 查询失败时怎么办，官方示例没有写（❓） | 访问国内站点，查看返回的 IP 是否为国内节点；抓包确认没有发往境外 DNS |
| 境外服务解析与出口 | fake-ip：不在本机解析；需要按 IP 判断时，`nameserver`（1.1.1.1、8.8.8.8 DoH）按规则经代理发出（`respect-rules`） | fake-ip：产品规则里走代理组的域名和未分类域名的 A / AAAA 查询直接给假地址；其他类型的查询（HTTPS / SVCB 等）和“需要按 IP 判断”时的解析，用经“国外默认”发出的 `dns-foreign`（1.1.1.1 DoH） | 命中域名规则的连接不在本机解析；没有命中任何域名规则的域名，要先用上一行的国内 DNS 解析，再按 IP 规则判断（见下方“已知取舍”第一条，结论是有条件的） | 同 Loon | mihomo / sing-box：抓包确认本机无明文 DNS 发往境外；Loon / QX：确认命中产品规则的域名不产生本机 DNS 查询 |
| 代理节点自身域名 | `proxy-server-nameserver` 用国内 DoH，直连查询，避免“要代理才能解析代理”的循环。节点的服务器如果是局域网里的名字（`gateway.lan`、不带点的主机名），由 `proxy-server-nameserver-policy` 交给 `system`（系统 DNS）——节点这条路不看 `nameserver-policy`，见最后一节“mihomo：三个解析器各管各的”（2026-10-05，审核 r10 的 R10-F01；要内核 v1.19.20 或更新） | `route.default_domain_resolver: dns-cn`（国内 DoH，直连）。节点的服务器如果是局域网里的名字（`gateway.lan`、不带点的主机名），这个节点另写 `domain_resolver: dns-local`（系统 DNS）——见下面“sing-box：拨号时的解析不看 DNS 规则”（2026-10-05） | 由 App 处理。服务器是局域网名字的节点由谁解析，官方文档的“DNS”“DNS 映射”两页没有写（2026-10-06 查的），也没有验证 | 由 App 处理。同样的问题，官方示例配置里没有写，也没有验证 | 断开所有代理组后重启客户端，节点仍能连上。有自建在局域网里的节点时：看它能不能连上 |
| 局域网、公司内网、本地名称 | `nameserver-policy` 第一条把 `+.lan/+.local/+.localdomain/+.home.arpa/+.localhost` 交给 `system`（系统 DNS，即路由器 / 公司 DNS）；`direct-nameserver-follow-policy: true` 让 DIRECT 连接的解析也走这条；`fake-ip-filter` 让它们拿真实地址；局域网段与这些后缀在规则第 2 阶段固定直连（2026-09-30 审核 F04 后补上，以前这些名字会被发给公共 DoH）。这一行管的是访问目标；节点自己的服务器地址见上一行 | DNS 规则把这些后缀交给 `dns-local`（系统 DNS）；局域网段固定直连。以域名形式到达直连出站的局域网名字，路由里先用一条 `resolve` 规则交给 `dns-local` 解析（2026-10-05，见“sing-box：拨号时的解析不看 DNS 规则”一节） | `[Host]` 里 `*.lan` 等交给 `server:system`；`real-ip` 不给假地址；`skip-proxy`、`bypass-tun` 排除私有网段 | `server=/*.lan/system` 等；`dns_exclusion_list`；`excluded_routes` | 访问 NAS / 打印机 / 路由器管理页；公司内网另在 `local.yaml` 加规则 |
| 系统联网检测 | Windows NCSI、Apple 强制门户等拿真实 IP 并固定直连 | 同左 | 同左（real-ip） | 同左（dns_exclusion_list） | Wi-Fi 图标不再误报“无网络”；酒店 / 机场 Wi-Fi 能弹出登录页 |
| 应用自带 DNS（HTTPDNS） | 未拦截：不等于广告，默认不启用（`adblock.yaml` 的 httpdns 为空） | 同左 | 同左；`hijack-dns` 接管发往 8.8.8.8 / 1.1.1.1 等的明文 53 端口查询 | 同左 | 对具体 App 实测：拦截后能否回退系统 DNS |
| 浏览器安全 DNS（DoH） | 浏览器自己加密查询，客户端看不到；fake-ip 失效时靠嗅探 SNI 恢复域名（sniffer） | `sniff` 动作恢复域名 | `sni-sniffing = true` | ❓ 依赖 App 自身行为 | 浏览器开 / 关安全 DNS 各访问一次，看是否命中同一策略 |
| 域名识别失败、直接 IP 连接 | 按 IP 规则：局域网 → Telegram 等专属段（不解析）→ 国内 IP → 国外默认 | 同左 | 同左 | 同左（专属段规则会触发解析，见限制） | 用 IP 直接访问一个国内、一个境外地址 |
| IPv6 | `dns.ipv6: false` 不返回 AAAA；内核 `ipv6: true` 仍处理 IPv6 字面地址连接 | `strategy: ipv4_only`；TUN 同时有 IPv6 地址，IPv6 流量按规则处理 | `ip-mode = ipv4-only` | `no-ipv6`（官方：只让 AAAA 失败） | 关闭 AAAA ≠ 所有 IPv6 路径都受控：需在双栈网络下用 IPv6 字面地址测试是否仍经 TUN 与规则 |
| 缓存 | 内核缓存；`store-fake-ip` 保存映射 | `cache_file.store_fakeip` | 运行期 LRU，退出清空（官方） | App 内 | 重启客户端后已打开的连接是否正常 |

## 已知取舍

- **Loon / Quantumult X 上没有命中域名规则的域名**（2026-10-03 审核 F06：以前这里写“结果仍会走国外默认”，少了条件）。这两端没有引入第三方的“国内 / 国外域名大集合”（其中含宽泛关键词规则，违背收录要求），所以一个域名如果没有命中任何产品规则和广告规则，就要先在本机解析、再按 IP 规则判断。分开说：
  - **谁看得到查询**：解析用的是国内 DNS（223.5.5.5、1.12.12.12 的 DoH），所以国内 DNS 能看到这些域名。这是这两端的已知代价，不能说成“四端都不让国内 DNS 看到境外域名”。Loon 另有一条：加密 DNS 查询失败时默认回落到普通 DNS（`dns-server` 里的 223.5.5.5、119.29.29.29，明文 UDP），这个开关在 App 里；Quantumult X 的官方示例则说设了 DoH 后普通 `server=` 会被忽略，两端不能互相套用。
  - **最后走哪里**：取决于解析出来的 IP。不是国内 IP → 落到最后一条规则，走国外默认（连接交给代理时带的是域名，由代理服务器再解析一次）。**是国内 IP → 命中 `GEOIP,CN`，直连。** 境外网站在国内有 CDN 节点、域名解析被污染到国内地址、或者和国内服务共用基础设施时，都会走到这个分支。所以只能说“解析结果不是国内 IP 时走国外默认”，不能保证所有没分类的境外域名都走国外默认。本项目没有在你的网络上观测过实际的解析结果。
  - **对使用的实际影响**（2026-10-04 你问到的，归纳在这里）：只涉及这两端上规则里没有列到的域名，Google、YouTube、ChatGPT 这些有规则的不经过国内 DNS。① 国内 DNS 看得到你访问了哪些这类域名（只有域名，看不到内容）。② 解析出境外地址的照常走国外默认；国内 DNS 给的地址即使不对也不影响，因为代理服务器会自己再解析一次。③ 解析出国内地址的会直连：网站在国内有 CDN 的，通常没有问题；被污染成国内地址的，这个网站会打不开——遇到时把域名告诉我，按域名加一条规则。这种情况在你的网络上实际有多少，没有观测过。④ 每个新域名第一次访问多一次本机解析。
  - mihomo / sing-box 的同一类域名也按 IP 判断（国内 IP 直连是有意的设计），区别只在解析走的是经代理发出的境外 DoH，国内 DNS 看不到。
  - 可以做而没有做的：给这两端也加一份经过审查的“境外域名”精确 / 后缀集合，让这些域名不经本机解析就走代理。审核方的建议是先把上游集合里的宽泛关键词过滤掉再用，并在实施前确认节点域名的解析、规则下载不会形成“要代理才能解析代理”的启动循环，评估国内 CDN 的延迟变化。这涉及取舍，留给用户决定，见 `docs/06`。
- **mihomo 上的整段 `.ms`**（2026-10-04，你的决定：不更正、跟随上游）：MetaCubeX 的国内域名集合里有整段后缀 `ms`，mihomo 的路由（`GEOSITE,cn`）和 DNS（`nameserver-policy` 的 `geosite:cn`）用的是同一个集合，所以没有被产品规则接住的 `.ms` 域名在 mihomo 上由国内 DNS 解析并直连。有规则的 `.ms` 域名（`aka.ms`、`1drv.ms` 等）按各自的组走，走代理时不在本机解析。sing-box 的集合里没有这一条。详见 `docs/06`“2026-10-04”一节。
- **Quantumult X 的专属 IP 段**：没有 no-resolve，域名连接走到 Telegram 段规则时会先解析；只影响没有命中任何域名规则的连接。
- **IPv6**：所有端都选择“不返回 AAAA”。这只阻止多数应用主动走 IPv6，不控制应用直接使用 IPv6 字面地址的情况；那部分流量在 TUN 模式下仍会按规则走（国内 IPv6 直连、其余走国外默认），在系统代理模式下可能绕过客户端。
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
| 4 | 产品规则里走代理组的全部域名（内联规则集 `product-proxied`：655 个后缀、108 个精确主机，DNS 规则引用两次，只写一份） | A / AAAA → `dns-fakeip`；其他查询类型 → `dns-foreign` |
| 5 | 上游的国内域名集合 `geosite-cn` | `dns-cn` |
| 6 | 其余 A / AAAA | `dns-fakeip` |
| 最后 | 其余查询类型 | `dns-foreign` |

说明：

- “走代理组”包括默认直连的 Apple、Apple Music/TV 两个组：给假地址之后，组选直连时由直连出站用国内 DNS 解析（和以前一样），组切到某个地区时由代理解析——不会出现“组已经切到美国，地址还是国内 DNS 解析的”。
- 归“国内直连”的产品规则（国内常用网站等）不用写进第 3、4 步：它们本来就由第 5、6 步处理，结果和以前一样。
- mihomo 不需要对应的改动：fake-ip 模式下，命中域名规则的连接不在本机解析，域名直接交给代理；`nameserver-policy` 里的国内集合只在需要解析时才用得到。这句话只管“fake-ip 生效、内核收到的是域名”这条路；浏览器自带的安全 DNS、被排除在 fake-ip 之外的名字、直接按 IP 发起的连接不在这句话的范围里（2026-10-04 审核 r9 时审核方指出的边界）。
- 验证：21 条 DNS 去向用例（`tests/cases.yaml` 的 `singbox_dns`），官方内核 v1.14.1 与 v1.12.0 实际查询的结果、自制模拟器、人工期望三者一致；另对全部“期望走代理组”的主机逐个检查 A 查询得到假地址、HTTPS 查询交给 `dns-foreign`（`tests/test_real_data.py`）。自检：把第 3、4 步拿掉，官方内核把 `chat.qwen.ai`、`music.apple.com` 的 A 查询交给了 `dns-cn`。日志 `docs/evidence/real-route-check.log`。
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

起因是 2026-10-05 对 r10 的审核（R10-F01），和上一节 sing-box 的问题是同一类。mihomo 内核里，按“谁要解析这个名字”分成三条路，各有各的服务器和例外策略：

| 谁要解析 | 用哪些服务器 | 例外策略写在哪 | 局域网里的名字，这一版交给谁 |
|---|---|---|---|
| 设备上的程序发来的 DNS 查询（TUN 接管的查询） | `nameserver` | `nameserver-policy` | 局域网后缀 → `system`（策略的第一条） |
| 直连出口连接域名形式的目标 | `direct-nameserver` | 开了 `direct-nameserver-follow-policy` 时先看 `nameserver-policy` | 同上 |
| 节点连接自己的服务器（订阅里每个节点的 `server`） | `proxy-server-nameserver` | `proxy-server-nameserver-policy`。**不看 `nameserver-policy`** | 局域网后缀、不带点的名字 → `system`（这一版加的） |

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

- **`system` 在真实系统上向谁查询**。核对时把它换成了替身。源码（`dns/system*.go`）里，Linux / macOS 读 `/etc/resolv.conf`，Windows 另有实现，Clash Meta for Android 的构建又是一套（没有看）；TUN 接管了 53 端口时它会不会绕回内核自己，没有实测。`nameserver-policy` 里的 `system` 从 r6 起就在用，是同一个东西。
- 真实网络、真实节点、TUN 接管下的表现。
- **客户端有没有把配置文件里的 dns 段原样交给内核**。Clash Verge Rev 有“DNS 覆写”开关，近几个版本它的行为有变动（`docs/06`“2026-10-05 审核（GPT r10）”一节）；Clash Meta for Android 有没有类似的设置没有核对。两个客户端内置的内核版本也没有核对。
- Loon / Quantumult X：服务器是局域网名字的节点由谁解析，`[Host]` / `server=/…/system` 那几行管不管得到节点服务器，都不知道——2026-10-06 查了 Loon 官方文档的“DNS”“DNS 映射”两页和 Quantumult X 的官方示例配置，都没有写这一点。
- 公司自定义的内网后缀：见上面“局域网后缀的来源”。
