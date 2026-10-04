# DNS 决策表

总原则：走代理的连接把域名交给代理服务器远端解析，本机不需要知道真实 IP；本机只在“直连”“需要按 IP 判断归属”“解析代理节点自己的域名”三种情况下查询 DNS。

| 场景 | mihomo | sing-box | Loon | Quantumult X | 验证方法 |
|---|---|---|---|---|---|
| 国内服务解析 | `nameserver-policy` 把 GeoSite cn / private 交给 223.5.5.5、1.12.12.12 的 DoH；直连出站用 `direct-nameserver`（同一组 DoH） | DNS 规则把 geosite-cn 交给 `dns-cn`（223.5.5.5 DoH，直连）；直连出站用 `default_domain_resolver: dns-cn` | `doh-server` 223.5.5.5 / 1.12.12.12，官方说明加密 DNS 优先、并发查询取最快，失败回落 `dns-server` | `doh-server` 同上，另有 `server=` 两个国内 UDP | 访问国内站点，查看返回的 IP 是否为国内节点；抓包确认没有发往境外 DNS |
| 境外服务解析与出口 | fake-ip：不在本机解析；需要按 IP 判断时，`nameserver`（1.1.1.1、8.8.8.8 DoH）按规则经代理发出（`respect-rules`） | fake-ip；未分类域名需要按 IP 判断时，用经“国外默认”发出的 `dns-foreign`（1.1.1.1 DoH） | 未命中域名规则的境外域名会用国内 DNS 解析后再判断（见下方限制） | 同 Loon | mihomo / sing-box：抓包确认本机无明文 DNS 发往境外；Loon / QX：确认命中产品规则的域名不产生本机 DNS 查询 |
| 代理节点自身域名 | `proxy-server-nameserver` 用国内 DoH，直连查询，避免“要代理才能解析代理”的循环 | `route.default_domain_resolver: dns-cn` | 由 App 处理 | 由 App 处理 | 断开所有代理组后重启客户端，节点仍能连上 |
| 局域网、公司内网、本地名称 | `fake-ip-filter` 让 `.lan/.local/.localdomain/.home.arpa` 等拿真实地址；局域网段与这些后缀在规则第 2 阶段固定直连 | 这些后缀交给 `local`（系统 DNS）；局域网段固定直连 | `[Host]` 里 `*.lan` 等交给 `server:system`；`real-ip` 不给假地址；`skip-proxy`、`bypass-tun` 排除私有网段 | `server=/*.lan/system` 等；`dns_exclusion_list`；`excluded_routes` | 访问 NAS / 打印机 / 路由器管理页；公司内网另在 `local.yaml` 加规则 |
| 系统联网检测 | Windows NCSI、Apple 强制门户等拿真实 IP 并固定直连 | 同左 | 同左（real-ip） | 同左（dns_exclusion_list） | Wi-Fi 图标不再误报“无网络”；酒店 / 机场 Wi-Fi 能弹出登录页 |
| 应用自带 DNS（HTTPDNS） | 未拦截：不等于广告，默认不启用（`adblock.yaml` 的 httpdns 为空） | 同左 | 同左；`hijack-dns` 接管发往 8.8.8.8 / 1.1.1.1 等的明文 53 端口查询 | 同左 | 对具体 App 实测：拦截后能否回退系统 DNS |
| 浏览器安全 DNS（DoH） | 浏览器自己加密查询，客户端看不到；fake-ip 失效时靠嗅探 SNI 恢复域名（sniffer） | `sniff` 动作恢复域名 | `sni-sniffing = true` | ❓ 依赖 App 自身行为 | 浏览器开 / 关安全 DNS 各访问一次，看是否命中同一策略 |
| 域名识别失败、直接 IP 连接 | 按 IP 规则：局域网 → Telegram 等专属段（不解析）→ 国内 IP → 国外默认 | 同左 | 同左 | 同左（专属段规则会触发解析，见限制） | 用 IP 直接访问一个国内、一个境外地址 |
| IPv6 | `dns.ipv6: false` 不返回 AAAA；内核 `ipv6: true` 仍处理 IPv6 字面地址连接 | `strategy: ipv4_only`；TUN 同时有 IPv6 地址，IPv6 流量按规则处理 | `ip-mode = ipv4-only` | `no-ipv6`（官方：只让 AAAA 失败） | 关闭 AAAA ≠ 所有 IPv6 路径都受控：需在双栈网络下用 IPv6 字面地址测试是否仍经 TUN 与规则 |
| 缓存 | 内核缓存；`store-fake-ip` 保存映射 | `cache_file.store_fakeip` | 运行期 LRU，退出清空（官方） | App 内 | 重启客户端后已打开的连接是否正常 |

## 已知取舍

- **Loon / Quantumult X 的境外域名解析**：这两端没有引入第三方“国内 / 国外域名大集合”（其中含宽泛关键词规则，违背收录要求），所以没有命中产品规则的境外域名会先经国内 DNS 解析再按 GEOIP 判断——结果仍会走国外默认，但国内 DNS 能看到这些域名。可以在 App 里自行加国外域名集合缓解。
- **Quantumult X 的专属 IP 段**：没有 no-resolve，域名连接走到 Telegram 段规则时会先解析；只影响没有命中任何域名规则的连接。
- **IPv6**：所有端都选择“不返回 AAAA”。这只阻止多数应用主动走 IPv6，不控制应用直接使用 IPv6 字面地址的情况；那部分流量在 TUN 模式下仍会按规则走（国内 IPv6 直连、其余走国外默认），在系统代理模式下可能绕过客户端。
