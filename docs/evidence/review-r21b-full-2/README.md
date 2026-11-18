# `ixxooxo-alt/proxy` 完整审核报告

- **审核对象**：分支 `claude/r12-gpt-review-handling-q4onlv`，提交 `b9a9f14598d300495859c6390559646e5c81254f`（与 `main` 上的 `a6671c1d` 即 r21b 相比，仅多 `63e66e4` 与 `b9a9f14` 两个纯文档/核对脚本提交，`dist/` 配置逐字节相同；工作区干净）
- **统一源版本**：`2026.10.31-1`；**生成器版本**：`1.12.1`；**简易版版本**：`2026.10.31-2`

---

## 一、总结论

1. **有没有确定的导入失败、分流错误、安全或泄漏？——有，共确认 9 项问题（其中安全或泄漏 1 项、导入失败 1 项共 3 类触发条件、分流错误 3 项、文档不符 3 项、测试与工具缺陷 1 项归入建议）：**
   - **安全或泄漏（1 项，影响 Loon 全部 4 份配置）**：Loon 的 `[General]` 把 `ip-mode` 写成了官方文档不存在的值 `ipv4-only`（Loon 官方枚举值为 **`v4-only`**），且未显式写 `ipv6-vif = off`。客户端忽略未知枚举值回退默认策略后，双栈网络下可能继续查询 `AAAA` 并建立 IPv6 连接，使“关闭 IPv6 / AAAA”失效。
   - **导入失败（1 项共 3 类节点写法，仅影响 `build.py --singbox-nodes` / `--singbox-sub-url` 生成的私密 SFA 配置）**：合法且能通过 `mihomo -t` 的常见 Clash 订阅节点——① VLESS Reality 的 `short-id:` 留空（YAML `null` 被写成 `"None"`）、② Hysteria2 的 `ports` 含单端口（如 `443,20000-30000`）或用 `/` 分隔、③ `socks5` / `http` / `hysteria2` / `tuic` / `anytls` 带 `smux: {enabled: true}`——经 `generator/nodes.py` 转换且未被 `generator/verify.py` 拦住，生成的 `dist/private/sing-box-*.json` 在官方 `sing-box check`（1.14.1 与 1.12.0）下**整份配置报错拒绝启动**。
   - **分流错误 / 节点凭据静默损坏（3 项）**：
     1. `generator/nodes.py` 直接用 `PyYAML`（YAML 1.1）解析 Clash 订阅，未加引号的前导 `0` 全 `0–7` 数字密码或 `short-id`（如 `01234567`、`0123`）会被当成**八进制整数**静默改写成十进制字符串（`"342391"`、`"83"`），`sing-box check` 不报错但节点握手必败；
     2. `Max`（HBO Max）服务漏掉了其核心客户端 API 域名 `discomax.com`（就在该项目登记的 `domain-list-community` `hbo` 快照第 7 行），当 `Max` 选的地区与 `国外默认` 不同时，同一 App 前后端出口跨国分裂；
     3. `source/regions.yaml` 香港单字规则 `(?<!香)港(?![日韩韓美])` 只排除了 `[日韩韓美]`，导致 `港台中转 01`、`港新中转 01`、`港坡专线 01`、`港德专线 01` 等非香港落地（甚至明确写着“中转”）的节点全部闯进 `香港·自动`、`香港·故障转移` 与简易版 `境外DNS`。
2. **这一版能不能照现在这样用？**
   - **`mihomo`（Clash Verge Rev / Clash Meta for Android）4 份配置**：**可以照现在这样直接用**。已通过官方 `mihomo v1.19.31` 语法检查、2290/2313 节点实际分组、290 项真实数据路由/DNS 探测及 222,353 个主机的全量扫描核对（仅若重度使用 HBO Max 且 `Max` 与 `国外默认` 选不同国家，建议补上 `discomax.com`）。
   - **`sing-box`（SFA）公开模板与私密生成配置**：路由与 DNS 架构设计扎实（官方 1.14.1 与 1.12.0 实测全部一致）；只要你的机场订阅没有触发上述 C2/C3 的节点写法（生成后跑一次 `sing-box check -c ...` 通过且无未加引号 `0` 开头纯数字密码），**可以正常使用**。
   - **`Quantumult X`（4 份）与 `Stash`（4 份）**：对照现行官方配置样例与 `stash.wiki` 官方文档逐项核对，未发现确定的导入失败或泄漏缺陷（受限于无 iOS/macOS 真机，严格版远程规则细节与简易版混写语法仍需按 `docs/09` 做首次真机确认）。
   - **`Loon`（4 份）**：在纯 IPv4 网络下可用（2026-10-20 使用者已在 iPhone 上成功导入 r19 的 `loon.conf`），但在有 IPv6 的移动蜂窝网或宽带下，**建议先把 `ip-mode = ipv4-only` 修正为 `ip-mode = v4-only`（并补 `ipv6-vif = off`）再日常使用**。
3. **安全与隐私**：公开仓库、历史记录与 25 个公开产物中**没有任何真实订阅链接、节点地址、密码或个人信息**；私密构建严格隔离在 `.gitignore` 覆盖的 `dist/private/` 与 `source/local.yaml`。

---

## 二、已确认的问题

### C1 `安全或泄漏` Loon 四份配置的 `ip-mode = ipv4-only` 写成了官方文档不存在的枚举值（官方为 `v4-only`），且未显式关闭 `ipv6-vif`

- **文件与位置**：
  - [emit_loon.py](<审核方本机的工程目录>/generator/emit_loon.py#L77)
  - [loon.conf](<审核方本机的工程目录>/dist/loon/loon.conf#L8)、[loon-strict.conf](<审核方本机的工程目录>/dist/loon/loon-strict.conf#L11)、[loon-simple.conf](<审核方本机的工程目录>/dist/loon/loon-simple.conf#L10)、[loon-simple-strict.conf](<审核方本机的工程目录>/dist/loon/loon-simple-strict.conf#L13)
  - [03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L16)
- **为什么错**：
  - `emit_loon.py:77` 输出 `"ip-mode = " + ("dual" if dns["ipv6_answers"] else "ipv4-only")`。
  - 但 Loon 官方文档在所有涉及 `ip-mode` 的页面均明确规定合法枚举值只有 5 个：**`v4-only`**、`dual`、`prefer-v4`、`prefer-v6`、`v6-only`，不存在 `ipv4-only`（疑似与 Quantumult X 的 `ipv6 = false` 或其他客户端命名混淆）。
  - 同时，Loon 的 TUN 虚拟网卡是否启用 IPv6 由独立的 `ipv6-vif` 参数（`off` / `auto` / `always`）控制，配置中未写出 `ipv6-vif = off`。
  - 使用者 2026-10-20 在 iPhone 上导入 r19 的 `loon.conf` 未报错，说明 Loon 对不认识的 `ip-mode` 枚举值不会整份拒绝导入，而是忽略并回退内部默认行为；在双栈移动网络或宽带下，若回退为 `dual`，Loon 仍会并发查询 `AAAA` 并发起 IPv6 连接，违背 `source/dns.yaml`（`ipv6_answers: false`）和 `docs/03` 第 16 行声称的关闭 IPv6/AAAA 设计。
- **依据**：
  - Loon 官方文档《通用配置 - IP 模式》：`https://nsloon.app/docs/General/#ip-mode`（明确列出 `v4-only`：“仅使用 IPv4，不查询 AAAA，并拒绝 IPv6 连接”）及 `#ipv6-vif`（`ipv6-vif = off`：“关闭 IPv6 VIF”）。
  - Loon 官方文档《DNS 映射》：`https://nsloon.app/docs/DNS/hostmap`（`example.com = ip-mode:v4-only`，明确写明“`ip-mode` 支持 `v4-only`、`dual`、`prefer-v4`、`prefer-v6` 和 `v6-only`”）。
  - Loon 官方文档《单节点配置》：`https://nsloon.app/docs/Node/`（同样列出该 5 个枚举值）。
- **建议怎么改**：
  - 将 [emit_loon.py](<审核方本机的工程目录>/generator/emit_loon.py#L77) 中的 `"ipv4-only"` 改为 `"v4-only"`，并在 `not dns["ipv6_answers"]` 时紧接输出一行 `"ipv6-vif = off"`；
  - 在 [verify.py](<审核方本机的工程目录>/generator/verify.py) 的 `check_loon` 中增加 `ip-mode` 合法值集合校验（`{"v4-only", "dual", "prefer-v4", "prefer-v6", "v6-only"}`），并同步更新 [03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L16) 及测试断言。

---

### C2 `导入失败` `generator/nodes.py` 将 3 类合法 Clash 订阅节点转成令 `sing-box` 整份配置崩溃的坏字段，且 `generator/verify.py` 未拦截

- **文件与位置**：
  - [nodes.py](<审核方本机的工程目录>/generator/nodes.py#L61-L66)（VLESS Reality `short-id` / `public-key`）
  - [nodes.py](<审核方本机的工程目录>/generator/nodes.py#L320-L326)（Hysteria2 `ports` / `hop-interval`）
  - [nodes.py](<审核方本机的工程目录>/generator/nodes.py#L177-L189)（`_dial` 中的 `smux` → `multiplex`）
  - [verify.py](<审核方本机的工程目录>/generator/verify.py#L254-L314)（`check_singbox` 未检查节点出站上述结构）
- **为什么错**（以下 3 类均已用官方 `mihomo v1.19.31 -t` 验证退出码 `0`、`build.py --singbox-nodes` 退出码 `0`，随后官方 `sing-box 1.14.1` 与 `1.12.0` 的 `check` 直接 `FATAL` 退出码 `1`）：
  1. **VLESS Reality 的 `short-id` 留空（YAML `null`）被写成字符串 `"None"`**（与第 1 轮审核 F12 同一类问题）：
     机场 Clash 订阅极常见 `reality-opts: {public-key: xxx, short-id: }`（无 shortId 时留空）。YAML 解析后 `reality.get("short-id", "")` 返回 `None`（因为键存在且值为 `None`，默认值 `""` 不生效），第 65 行 `str(reality.get("short-id", ""))` 把它写成 `"short_id": "None"`；同时 `reality["public-key"]` 也未走 `_req`（缺键抛 `KeyError` 被外层笼统捕获，值为 `None` 则写出 JSON `null`）。`sing-box check` 整份配置报错退出：
     `FATAL[0000] initialize outbound[...]: decode short_id: encoding/hex: invalid byte: U+004E 'N'`。
  2. **Hysteria2 端口跳跃 `ports` 含单端口或 `/` 分隔符**：
     mihomo 的 Hysteria2 实现同时支持 `,` 和 `/` 分隔，且支持单端口与端口段混写（如 `ports: 443,20000-30000` 或 `ports: 20000-30000/40000-50000`）。而 `nodes.py:322` 仅做 `[x.strip().replace("-", ":") for x in str(ports).split(",")]`，生成 `["443", "20000:30000"]` 或 `["20000:30000/40000:50000"]`。sing-box 强制要求 `server_ports` 每项必须带 `:`（单端口须写 `"443:443"`），`sing-box check` 直接报错：
     `FATAL[0000] initialize outbound[...]: bad port range: 443`。
     （附：mihomo 还支持区间写法 `hop-interval: "30-60"`，当前第 325 行 `int(hop)` 会抛 `ValueError`。）
  3. **不支持多路复用的协议被写出 `"multiplex"` 字段**（与第 1 轮审核 F01 的 `NETWORK_FIELD` 同一类问题）：
     `_dial` 对所有协议统一转换 `smux`。当订阅在 `socks5`、`http`、`hysteria2`、`tuic`、`anytls` 节点上附带 `smux: {enabled: true}` 时（mihomo 不报错），`nodes.py` 写出 `"multiplex": {...}`，但 sing-box 仅在 `shadowsocks`、`vmess`、`vless`、`trojan` 四种出站结构体中定义了 `Multiplex`，`sing-box check` 直接在 JSON 解码阶段报错退出：
     `FATAL[0000] decode config ... outbounds[...].multiplex: json: unknown field "multiplex"`。
- **依据**：
  - `MetaCubeX/mihomo` (`ab405ba`, v1.19.31)：`adapter/outbound/hysteria2.go:243-265`（`utils.NewUnsignedRanges[uint16]` 支持 `,`/`/` 与单端口）、`adapter/outbound/vless.go`、`adapter/outbound/socks5.go`。
  - `SagerNet/sing-box` (`1ac1a33`, v1.14.1)：`option/vless.go`、`option/hysteria2.go`、`outbound/hysteria2.go`、`option/socks.go`、`option/http.go`、`option/anytls.go`、`option/tuic.go`，以及官方二进制 `sing-box check` 实测结果。
- **建议怎么改**：
  - **Reality**：用 `_req(reality, set(), "public-key")` 校验公钥非空；`sid = reality.get("short-id")`，若 `sid is None` 转 `""`，否则转字符串并校验十六进制格式（`^[0-9a-fA-F]{0,16}$` 且长度为偶数，不合法抛 `Unsupported`）。
  - **Hysteria2**：用 `re.split(r"[,/]", str(ports))` 拆分，逐段匹配 `^(\d+)(?:-(\d+))?$`，校验端口号在 `1..65535` 且起始 ≤ 结束，单端口 `p` 输出 `f"{p}:{p}"`，范围输出 `f"{a}:{b}"`，不合法抛 `Unsupported`；`hop-interval` 非纯整数时抛清晰的 `Unsupported`（或对 1.14 映射 `hop_interval_max`）。
  - **Multiplex**：仿照第 35 行 `NETWORK_FIELD` 定义 `MULTIPLEX_FIELD = {"shadowsocks", "vmess", "vless", "trojan"}`，其他协议遇到 `smux.enabled` 为真时抛 `Unsupported`（跳过该节点并记入转换报告，而不是写进 JSON 把整份配置炸崩）。
  - 在 `verify.py:check_singbox` 中补上这三项结构约束。

---

### C3 `分流错误` `generator/nodes.py` 使用 `PyYAML`（YAML 1.1）解析 Clash 订阅，未加引号的前导 `0` 密码或 `short-id` 被静默当成八进制改写

- **文件与位置**：
  - [nodes.py](<审核方本机的工程目录>/generator/nodes.py#L416-L421)（`load_clash_proxies` 直接调用 `yaml.safe_load(text)`）
  - [nodes.py](<审核方本机的工程目录>/generator/nodes.py#L31)（`_req` 中 `str(v)`）、[nodes.py](<审核方本机的工程目录>/generator/nodes.py#L65)、[nodes.py](<审核方本机的工程目录>/generator/nodes.py#L319)、[nodes.py](<审核方本机的工程目录>/generator/nodes.py#L392)
- **为什么错**：
  - mihomo 使用 Go 的 `go.yaml.in/yaml/v3`（遵循 YAML 1.2，且直接按结构体目标类型解码到 Go `string`，未加引号的 `password: 01234567`、`short-id: 0123`、`password: 001234` 均原样保留前导零）。
  - 而 Python 的 `PyYAML` 实现的是 **YAML 1.1**：
    - 未加引号的 `0[0-7]+`（如 `01234567`、`0123`）被按 **八进制整数** 解析成 `int`（`342391`、`83`），随后 `str(v)` 写成 `"342391"`、`"83"`；
    - 含 `8`/`9` 的前导零纯数字（如 `001289`）在 YAML 1.1 中虽不按八进制算，若是 `0`（如 `short-id: 00`）则变成 `"0"` 丢失位数；
    - 未加引号的 YAML 1.1 布尔词（如 `short-id: on` / `off`、`username: no`）会被解析成 `bool`，变成 `"True"` / `"False"`。
  - 实测含 `password: 01234567` 和 `short-id: 0123` 的订阅转换后，`build.py` 与官方 `sing-box check` 退出码均为 `0`（完全无警告），但生成的 `sing-box-*.json` 里凭据已被篡改，导致该节点静默握手失败。
- **依据**：
  - `MetaCubeX/mihomo` `go.mod`（`go.yaml.in/yaml/v3 v3.0.5`）与 `PyYAML` `yaml.resolver.Resolver` 的 YAML 1.1 `tag:yaml.org,2002:int`（`^[-+]?0[0-7_]+$` 八进制规则）及 `tag:yaml.org,2002:bool` 规则。
- **建议怎么改**：
  - 在 `nodes.py` 中自定义继承自 `yaml.SafeLoader` 的 Loader：移除 YAML 1.1 的 `0[0-7]+` 八进制整数隐式解析（以及仅保留 `true`/`false` 布尔解析，对齐 YAML 1.2 Core Schema），并对字符串凭据键（`password`、`auth`、`obfs-password`、`uuid`、`short-id`、`public-key`、`username`、`sni`、`servername`）在构造映射时直接保留 `ScalarNode.value` 原始字面量（当 `node.tag != 'tag:yaml.org,2002:null'` 且非空时）。

---

### C4 `分流错误` `Max`（HBO Max）漏掉核心客户端后端域名 `discomax.com`，跨国选区时前后端出口分裂

- **文件与位置**：
  - [streaming.yaml](<审核方本机的工程目录>/source/services/streaming.yaml#L68-L78)（`id: max`）
- **为什么错**：
  - `max` 目前仅收录 `max.com`、`hbomax.com`、`hbomaxcdn.com`、`hbo.com`、`hbogo.com` 5 条后缀，漏掉了 Warner Bros. Discovery 为 Max / HBO Max 客户端提供鉴权、目录、账户配置与播放调度的核心 API 域名 **`discomax.com`**（如 `default.any-any.prd.api.discomax.com`、`*.beam.discomax.com`）。
  - `discomax.com` 就在 `max` 自己声明的 `upstream: {dlc: [hbo]}` 固定快照里，且在 `geosite:geolocation-!cn` 中、不在 `geosite:cn` 中。
  - 后果：当用户将 `Max` 策略组选为 `美国`（或香港/台湾/新加坡），而 `国外默认` 保持默认的 `日本` 时，`max.com` 走 `Max`（美国），客户端核心 API `*.discomax.com` 却掉进 `GEOSITE,geolocation-!cn` / `FINAL` 走 `国外默认`（日本），同一会话出口横跨两国，触发地区不匹配报错或无法播放。
- **依据**：
  - 本项目固定快照 `v2fly/domain-list-community`（`c1c2cf0d252871e8739747714df06e8d2671f72f`，见 [evidence.yaml](<审核方本机的工程目录>/source/evidence.yaml)）中 `data/hbo` 第 7 行：`discomax.com`（另可参考同文件第 68 行封面图 CDN `hbomax-images.warnermediacdn.com`）。
- **建议怎么改**：
  - 在 [streaming.yaml](<审核方本机的工程目录>/source/services/streaming.yaml#L73-L77) 的 `max.rules` 中增加 `- {suffix: discomax.com, ev: dlc}`（可一并评估补入 `- {domain: hbomax-images.warnermediacdn.com, ev: dlc}`），重新运行 `build.py`。

---

### C5 `分流错误` `source/regions.yaml` 香港单字 `港` 正则只排除 `[日韩韓美]`，`港台中转`/`港新中转`/`港坡专线`/`港德专线` 等节点误入 `香港·自动` 与 `境外DNS`

- **文件与位置**：
  - [regions.yaml](<审核方本机的工程目录>/source/regions.yaml#L95-L100)（`'(?<!香)港(?![日韩韓美])'`）
  - [regions.yaml](<审核方本机的工程目录>/source/regions.yaml#L132) 与 [regions.yaml](<审核方本机的工程目录>/source/regions.yaml#L146)
- **为什么错**：
  - 我们注意到了第 132 行（`# 不收“港台”：它也常指港台解锁，仍按香港算`）和第 146 行（`# 不收“港新”：“香港新增”“香港新界”太常见，仍按香港算`）的取舍说明，但这里的实现与理由存在两处确切漏洞：
    1. **中转节点漏进香港自动组与 `境外DNS`**：第 97–98 行专门记过 2026-10-05 修过的 bug——`港日中转 01` 里因为“港”后面排除了“日”，所以只进日本的手动组、不进任何自动组；但因为第 100 行只写了 `(?![日韩韓美])`，对于完全同构的 **`港台中转 01`、`港新中转 01`**，“港”与“中转”之间隔了“台”/“新”，中转前瞻断言不触发，实测 `tools/check_node_names.py` 把它们直接判为**明确香港落地**（连“请看一眼”提示都没有），送进了 `香港·自动`、`香港·故障转移`、`香港·负载均衡` 以及简易版的 `境外DNS`！
    2. **其他“港+落地”简称全部误进香港自动组，且第 146 行对 `香港新增`/`香港新界` 的顾虑在 `(?<!香)` 下并不成立**：
       - 在 `香港新增 01`、`香港新界 01` 中，“港”前面紧挨着“香”（且“香港”本身已是 `hk` 的国名级词），只要写成 `(?<!香)港新(?![界增闻聞])`（或收无歧义的 `港坡`），`香港新增` 和 `香港新界` 根本不会被匹配到新加坡；
       - 即使按当前取舍不把 `港台`、`港新` 归入台湾/新加坡自动组，像 **`港坡专线 01`、`港德专线 01`、`港英专线 01`、`港欧专线 01`** 这类常见“香港入口→第三国落地”的专线名，实测也全部进了 **`香港·自动` 和 `境外DNS`**（导致用户选香港自动时流量实际从新加坡/德国出去）。
- **依据**：
  - [regions.yaml](<审核方本机的工程目录>/source/regions.yaml#L95-L100) 自身中转排除设计说明，以及本机实跑 `python tools/check_node_names.py - --all --public` 输出：
    - `港日中转 01` → `日本（只进手动组）`
    - `港台中转 01` → **`香港`（进自动组）**
    - `港新中转 01` → **`香港`（进自动组）**
    - `港坡专线 01` / `港德专线 01` → **`香港`（进自动组）**
- **建议怎么改**：
  - 在 `sg.country.words` 补入无歧义的 `港坡`（如希望支持 `港新专线` 也可加带前后断言的 `(?<!香)港新(?![界增闻聞])`）；
  - 将 `hk.patterns` 第 100 行的排除集从 `(?![日韩韓美])` 扩充覆盖常见落地简称字（如 `'(?<!香)港(?![日韩韓美台臺新坡澳德英法欧歐加俄印土])'`；若仍希望纯 `港台` 在手动组里可见，可只让 `港[台臺新]` 进入宽筛选而不进严筛选自动组），并在 `tests/node_names.yaml` 增加 `港台中转 01`、`港新中转 01`、`港坡专线 01` 回归用例。

---

### C6 `文档不符` 多份核心文档现状段落仍写“从未在任何真机导入/实测”，与 `docs/05` 自身及 `docs/10` 的 2026-10-20 Loon 真机记录自相矛盾

- **文件与位置**：
  - [05-验收记录.md](<审核方本机的工程目录>/docs/05-验收记录.md#L151)（“Loon、Quantumult X：没有命令行工具，也没有设备，未导入”）、[#L157-L158](<审核方本机的工程目录>/docs/05-验收记录.md#L157-L158)、[#L173](<审核方本机的工程目录>/docs/05-验收记录.md#L173) —— 与**同一份文件** [#L186-L206](<审核方本机的工程目录>/docs/05-验收记录.md#L186-L206)、[#L229-L259](<审核方本机的工程目录>/docs/05-验收记录.md#L229-L259) 直接矛盾
  - [README.zh-CN.md](<审核方本机的工程目录>/README.zh-CN.md#L9)（徽章 `真机验证-还没做`）、[#L16](<审核方本机的工程目录>/README.zh-CN.md#L16)、[#L144](<审核方本机的工程目录>/README.zh-CN.md#L144)（“Loon 和 Quantumult X……**没有**在任何真机上导入或实测”）
  - [README.md](<审核方本机的工程目录>/README.md#L16)、[#L135](<审核方本机的工程目录>/README.md#L135)
  - [02-语法依据与能力矩阵.md](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L15)、[#L63](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L63)、[#L138](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L138)、[#L271](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L271)
  - [07-需求对照.md](<审核方本机的工程目录>/docs/07-需求对照.md#L24)（“有表格，未填写（没有设备）”）
- **为什么错**：
  - 使用者已于 2026-10-20 在 iPhone 的 Loon 上实际导入了 r19 的 `loon.conf`（与 r21 的 `loon.conf` 除文件头版本号外逐字节相同），验证了 81 个策略组与 12–16 KB 正则导入不报错不卡顿、“香港·手动优先”显示两个子组、两条远程广告规则加载成功、DNS 记录中无 Claude/OpenAI 等，并记录在 `docs/05:186-259`、`docs/10:85` 和 `PROJECT_STATE.md:72`。上述概览处仍保留 r19 之前的“从未导入任何真机 / 表格未填写”。
- **依据**：
  - [05-验收记录.md](<审核方本机的工程目录>/docs/05-验收记录.md#L186-L259)、[10-简易版框架.md](<审核方本机的工程目录>/docs/10-简易版框架.md#L85)、[00-需求原文.md](<审核方本机的工程目录>/docs/00-需求原文.md#L696-L735)。
- **建议怎么改**：
  - 将上述位置统一改为准确口径：“Loon 完整版（r19，配置本体与 r21 相同）已于 2026-10-20 在 iPhone 上完成初步导入与基础检查；严格版、全部简易版及其他四个客户端尚未在真机实测”。

---

### C7 `文档不符` Loon 最低目标版本声明为 `3.0.3+`，但生成的配置实际使用了 `3.2.5 (789)+` 才引入的参数，且仍输出官方标为已弃用的 `switch-node-after-failure-times`

- **文件与位置**：
  - [project.yaml](<审核方本机的工程目录>/source/project.yaml#L20)（`targets.loon.core`）
  - [emit_loon.py](<审核方本机的工程目录>/generator/emit_loon.py#L2)、[#L56](<审核方本机的工程目录>/generator/emit_loon.py#L56)、[#L89](<审核方本机的工程目录>/generator/emit_loon.py#L89)
  - [manifest.json](<审核方本机的工程目录>/dist/manifest.json#L69)、[02-语法依据与能力矩阵.md](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L15)
- **为什么错**：
  - 配置头与文档声明目标为 `Loon 3.x（域名规则先于 IP 规则自 3.0.3 起，故要求 3.0.3+）`，但 `[General]` 中实际输出的：
    - `domain-reject-mode = DNS`、`udp-fallback-mode = REJECT` 要求 **Loon 3.2.0 (702)+**；
    - `ip-mode` 要求 **Loon 3.2.3 (754)+**；
    - `hijack-dns` 要求 **Loon 3.2.5 (789)+**。
  - 此外，`emit_loon.py:89` 输出了 `switch-node-after-failure-times = 3`，而 Loon 官方文档《通用配置 - 已弃用参数》明确标注：“以下参数仅用于识别旧配置，新配置不应继续使用：`switch-node-after-failure-times` | Loon 现已自动检测节点可用性”。
- **依据**：
  - Loon 官方文档《通用配置》：`https://nsloon.app/docs/General/`（`#domain-reject-mode`、`#udp-fallback-mode`、`#ip-mode`、`#hijack-dns` 及 `#已弃用参数`）。
- **建议怎么改**：
  - 将 `targets.loon.core` 与 `docs/02` 的最低版本要求更新为 `Loon 3.2.5 (789)+`（保留“域名规则先于 IP 规则自 3.0.3 起”的说明），并在下一版更新代码时移除已弃用的 `switch-node-after-failure-times`（或注释说明新版本已忽略）。

---

### C8 `文档不符` `docs/01`、`docs/02`、`docs/05`、`docs/07` 及 `emit_loon.py` / `emit_qx.py` 注释残留多处旧版本（r12 / r13 / r16）说法与旧数量

- **文件与位置**：
  1. [01-导入、更新、诊断与回滚.md](<审核方本机的工程目录>/docs/01-导入、更新、诊断与回滚.md#L22-L30)：GitHub `raw` 下载地址列表仍写着 `# 下面是 r12 才有的：main 更新到 r12 以后才取得到`，且只列了 6 个链接——漏掉了 Stash 两份完整版（`stash.yaml`、`stash-strict.yaml`）以及 `main` 已发布的全部 10 份 `-simple` 简易版地址；同文件 [#L93](<审核方本机的工程目录>/docs/01-导入、更新、诊断与回滚.md#L93) 策略组图标只提三端 81 个组（漏了 Stash 与简易版 51/52 个组）；[#L228](<审核方本机的工程目录>/docs/01-导入、更新、诊断与回滚.md#L228) “回滚”一节仍写 `r12 和这一版 r13（都是 2026.10.06-1）`。
  2. [02-语法依据与能力矩阵.md](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L132) 与 [#L138](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L138)、[05-验收记录.md](<审核方本机的工程目录>/docs/05-验收记录.md#L158)：策略组图标仍写“三个客户端的六份产物”，实际带图标的公开配置已是 **4 个客户端共 16 份产物**（与 `docs/evidence/icons-check.log` 一致）。
  3. [02-语法依据与能力矩阵.md](<审核方本机的工程目录>/docs/02-语法依据与能力矩阵.md#L267)：仍写 `r7 → r16`、`r15 → r16`，实际两份对比文件已是 `r7 → r21`、`r20 → r21`。
  4. [07-需求对照.md](<审核方本机的工程目录>/docs/07-需求对照.md#L70-L71) 与 [05-验收记录.md](<审核方本机的工程目录>/docs/05-验收记录.md#L96)：`docs/07` 仍写“八份配置（r12 起是八份，含两份严格版）”/“八份配置 × 17 条规则”，`docs/05` 写“十份配置里 17 条”，而 `tests/test_apple_ai.py` 实际遍历 `CLIENT_FILES` 检查的是 **20 份配置**。
  5. [emit_loon.py](<审核方本机的工程目录>/generator/emit_loon.py#L7-L12) 与 [emit_qx.py](<审核方本机的工程目录>/generator/emit_qx.py#L9-L16)：模块顶部 docstring 第 3 点仍说严格版比标准版在 `real-ip` / `force-http-engine-hosts` 里“补上固定直连”，实际上自 r14（待决事项第 15 项）起两版都无条件写出 `plan.real_ip_direct`（`tests/test_strict.py:85` 专门断言两版此处相同）。
- **为什么错**：后续迭代新增 Stash（r16）和简易版（r20）并更新 `main`（r21b）时，这些段落未被 `handoff/release/r21-as-used/recheck_r21b.py` 的 `STALE` 词表覆盖。
- **依据**：上述文件行号与现行 [test_icons.py](<审核方本机的工程目录>/tests/test_icons.py#L35-L38)、[test_apple_ai.py](<审核方本机的工程目录>/tests/test_apple_ai.py)、[test_strict.py](<审核方本机的工程目录>/tests/test_strict.py#L85) 对照。
- **建议怎么改**：补齐 `docs/01` 的 18 个可直接导入链接（含 Stash 与简易版），修正 `docs/01`、`docs/02`、`docs/05`、`docs/07` 及两处模块注释中的旧版号和份数，并将典型旧词加入定稿核对脚本。

---

### C9 `建议`（测试与工具跨平台缺陷）Windows 下 `Socks5Recorder._serve` 触发 TCP `RST` 致 `unittest` 必败 1 项（连带使 `check_mutations.py` 基线恒非零），且 `run_checks.sh` / `code_state.sh` / `recheck_r21b.py` 存在跨平台兼容问题

- **文件与位置**：
  - [check_real_routes.py](<审核方本机的工程目录>/tools/check_real_routes.py#L1003-L1016) 与 [#L1034](<审核方本机的工程目录>/tools/check_real_routes.py#L1034)（`Socks5Recorder._serve`）
  - [test_real_data.py](<审核方本机的工程目录>/tests/test_real_data.py#L948-L971)（`test_records_every_request_it_refuses`）
  - [run_checks.sh](<审核方本机的工程目录>/tools/run_checks.sh#L22)、[#L46](<审核方本机的工程目录>/tools/run_checks.sh#L46)、[#L52](<审核方本机的工程目录>/tools/run_checks.sh#L52)
  - [code_state.sh](<审核方本机的工程目录>/handoff/release/code_state.sh#L9-L10)
  - [recheck_r21b.py](<审核方本机的工程目录>/handoff/release/r21-as-used/recheck_r21b.py#L72)、[#L80-L85](<审核方本机的工程目录>/handoff/release/r21-as-used/recheck_r21b.py#L80-L85)
- **为什么错**：
  1. **`Socks5Recorder._serve` 未排空接收缓冲区即 `close()` 发 TCP `RST`**：
     `test_records_every_request_it_refuses` 第 970 行发送 10 字节 `b"\x05\x02\x00\x01" + bytes(6)` 后 `sleep(0.15)` 再 `recv(64)`。服务端 `_serve` 第 1003 行只 `need(3)` 读走前 3 字节，内核接收缓冲区还剩 **7 字节未读**时就 `sendall(b"\x05\x07...")` 并执行 `finally: c.close()`。按 RFC 1122 §4.2.2.13，接收缓冲区有未读数据时 `close()` 会直接发 TCP **`RST`**；Windows Winsock 收到 `RST` 立即丢弃客户端尚未读取的应答并抛 `ConnectionResetError`（10054），被 `talk()` 第 963 行 `except OSError: pass` 吞掉后返回 `b""`，在 Windows Python 3.12 上**必现 `AssertionError: b'' != b'\x05\x07'`**。
     **连锁影响**：因为 `tools/check_mutations.py` 只看退出码非 0 即判 `[发现]`（`docs/08` 第 20 轮已记），在基线本身就有 1 项失败的环境上跑 `check_mutations.py`，任何空操作变异都会被假阳性判成 `[发现]`。
  2. **Windows + Git Bash 下其他 3 处脚本兼容性**：
     - `tools/run_checks.sh` 硬编码 `python3`，在 Windows 虚拟环境（只有 `python.exe`）下会落入系统 `WindowsApps\python3.exe` 商店占位符（退出码 49），导致 `RunChecksExitCode` 两项测试在有 `bash` 时必败；
     - `handoff/release/code_state.sh:10` 的 `xargs sha256sum | sha256sum` 在 MSYS2 Git Bash 下因 `sha256sum` 默认二进制模式输出 `<hash> *<file>`（带 `*` 而非空格），算出的哈希变成 `be2b3b0b...`（将 ` *` 归一化为两个空格后即为 `eca139fa...`）；
     - `recheck_r21b.py:72` 用 `os.path.join("docs", f)` 在 Windows 下生成 `docs\00-需求原文.md`，与第 80 行 `HIST = ["docs/00-需求原文.md", ...]` 斜杠不一致，误报 26 条“旧说法”。
- **依据**：
  - 本机实跑 `python -m unittest discover -s tests -v` 失败堆栈、`bash handoff/release/code_state.sh` 输出及 RFC 1122 §4.2.2.13。
- **建议怎么改**：
  - `Socks5Recorder._serve` 在发完拒绝应答返回前，先 `c.shutdown(socket.SHUT_WR)` 再用短超时读空对端已发字节后 `c.close()`；`check_mutations.py` 开跑前先做一次基线通过性预检；
  - `run_checks.sh` 用 `PYTHON="${PYTHON:-python3}"`（`test_run_checks.py` 传入 `env["PYTHON"] = sys.executable`）；`code_state.sh` 加 `sed 's/ \*/  /'`；`recheck_r21b.py` 用 `f"docs/{f}"`。

---

## 三、推测的问题、取舍评估与改进建议（非确定错误）

### S1 `建议` 把 `广告拦截` 组手动切到 `DIRECT` 时的跨层副作用提示（`docs/01`）

- **位置**：[groups.yaml](<审核方本机的工程目录>/source/groups.yaml#L25-L29)、[01-导入、更新、诊断与回滚.md](<审核方本机的工程目录>/docs/01-导入、更新、诊断与回滚.md#L230)
- **说明**：`广告拦截` 默认是 `REJECT`，此时完全无泄漏、无慢速。但 `docs/01:230` 推荐遇到误拦时“把 `广告拦截` 组切到 `DIRECT`”。经代码核对，`plan.ads_local` 中有 **26 条规则**落在代理产品根域之下（如 `ads.youtube.com`、`adservice.google.com`、`analytics.tiktok.com`、`graph.whatsapp.com`、`an.facebook.com`、`adeventtracker.spotify.com`）。一旦切到 `DIRECT`：
  - 在中国大陆网络下，这些境外域名从本机直连大多会连接超时、反而拖慢应用；
  - 在 `sing-box` 上直连出口默认走 `dns-cn`，会把这些境外广告/统计域名交给国内 DNS 解析；在 `mihomo` 上 `direct-nameserver-follow-policy: true` 会命中父域（如 `+.google.com` → `*dns-foreign`）用境外 DNS 解析后再本机直连。
- **建议**：无需改动分流结构，只需在 `docs/01:230` 补一句提示：把 `广告拦截` 切为 `DIRECT` 仅用于临时排查**国内应用**误拦；排查境外应用异常时请暂时关闭远程广告规则或在 `local.yaml` 加例外，不要长期停在 `DIRECT`。

### S2 `建议` 官网现行文档核实结果同步（供更新文档时参考）

作者此前因云端环境无法访问 `stash.wiki`（返回 403），将若干字段标为“审核方转述 / 未核对”。本次直接访问现行官网核实如下：
1. **Stash `hidden: true` 与版本号**（`https://stash.wiki/proxy-protocols/proxy-groups`、`https://stash.wiki/release-notes/ios`）：
   - 官方文档《策略组 - 隐藏策略组》已正式记录 `hidden: true`，可将 `docs/10` 中“官方快照里没写”更新为官方文档已收录；
   - Stash iOS App Store 最新正式版目前仍为 `3.4.0`（2026-06-23），因此项目在 `emit_stash.py` 中不使用 `iOS 3.6+ / macOS 4.3+` 专属字段（`proxy-server-nameserver`、`ipv6: false` 等）的决定完全正确。
2. **Loon 3.5.2 (996)+ 订阅级 `server-dns`**（`https://nsloon.app/docs/Node/subscription`）：
   - 现行官方文档在 `[Remote Proxy]` 已新增 `server-dns` 参数用于固定解析节点服务器域名（避免切换 Wi-Fi 时受系统 DNS 影响）。当前 Loon 全局 DNS 已设为国内 DoH/明文，现状无误；后续如上调目标版本可考虑选配。

---

## 四、十个审核维度与本轮重点项逐项核对小结

| 维度 | 核对结论 |
| --- | --- |
| **1. 需求符合度**（`docs/00` vs `docs/07`） | `docs/00` 历次原始需求与 2026-09-29 至 2026-10-31 的全部决定（含第 1–23 项待决事项、完整版/简易版/严格版并存、三个新测速间隔）在代码与产物中**均已真实落地**。`docs/07` 标“已实现”的条目无夸大功能，仅有 C6/C8 指出的真机记录状态与配置份数文字未同步。 |
| **2. 能否导入与语法依据**（25 份公开 + 私密） | `mihomo` 4 份、`sing-box` 4 份公开模板 + 6 份带节点配置通过官方内核实检；`Quantumult X` 4 份对照官方 v1.5.5 (build 914) `sample.conf` 核对无误；`Stash` 4 份对照现行 `stash.wiki` 全部页面核对无误（含 YAML 锚点、`domain-text`、`benchmark-url`、`interval: -1` / `3600`、排除内置策略名的筛选正则）。发现 **Loon `ip-mode = ipv4-only` 写错（C1）** 和 **私密 `sing-box` 转换 3 类节点崩溃（C2）**。 |
| **3. 规则归属与先后** | 856 条服务规则与 48 条自有拦截规则逐条复核：`Apple AI` 在 `Apple` 前、`Google AI` / `YouTube` 在 `Google` 前、`Copilot` 在 `GitHub` 前、`OneDrive` / `Teams` 在 `Microsoft` 前、`Prime Video` 的 `atv-ps.amazon.com` 在 `Amazon` 前、`Hulu` 的 `hulu.playback.edge.bamgrid.com` 在 `Disney+` 前、`adblock` 例外与具体产品域优先级均正确；Loon 域名先于 IP、QX/mihomo/Stash/sing-box 按行顺序与 `no-resolve` 的差异处理正确。仅发现 **`Max` 漏掉 `discomax.com`（C4）**。 |
| **4. DNS 与泄漏** | 国内直连走国内 DoH/明文（223.5.5.5 / 119.29.29.29）、境外连接走远端解析或境外加密 DNS（1.1.1.1 / 8.8.8.8 经代理解析）、节点自身域名走国内 DNS（无回环死锁）、LAN 后缀走 `system`、`real-ip` / `fake-ip-filter` 名单一致。290 项真实探测与 222,353 域名全量核对 `0` 处代理域名落入国内 DNS。`docs/03` 与 `docs/06` 所列客户端口子（第 21 项未命中域名首包前嗅探/GEOIP 解析、Stash 无 `follow-rule` 时的 `nameserver-policy` 覆盖边界、SFA 首次无 `.srs` 缓存时的启动依赖等）完整、准确，未说过头。Loon 需修 C1 的 `v4-only`。 |
| **5. 故障行为与 r21 三个测速间隔** | ① 完整版“手动优先（`fallback` 嵌 `手动` + `自动`）”在五端均实现；空地区组有 `empty-fallback`（mihomo）、`REJECT` 占位节点（Stash）或空筛选保护，**不会悄悄退回 `DIRECT`**（代码与 `check_official.py` 已验证）。② **r21 三个测速间隔逐项核对无误**：Stash 完整版 57 个 `select` 组为 `interval: -1`（自动类 24 个组仍为 `interval: 300` + `lazy: true`；关于 `fallback` 嵌 `select` 时父组是否仍测子组已在 `docs/09` 第 1c 节第 16 步诚实标为待真机确认，且 Stash 文档说明同节点延迟跨组共享，不会破坏 `X·手动优先` 的故障切换）；Stash 简易版 51 个组为 `interval: 3600`；SFA 简易版 `境外DNS` 为 `interval: "600s"`、`idle_timeout: "30m"`，mihomo 简易版订阅健康检查保持 `3600`；`docs/10` 第 4.4 / 6.3 / 6.4 节、`docs/06`、`docs/03`、`docs/09` 按定时器活跃/休眠两态改写准确，没有说过头。 |
| **6. 节点按名称分地区** | 宽/严两套正则在 Python `re`、Windows 系统 `icu.dll`（ICU 引擎）与 `mihomo` Go `regexp2` 三套引擎上对 2290/2313 个节点名与 860 个 120/400 字超长名结果 **100% 一致**；Stash 筛选开头排除 `DIRECT|REJECT|REJECT-DROP|PASS|COMPATIBLE` 处理正确。发现 **`港台中转`/`港新中转`/`港坡专线` 等漏进香港自动组（C5）**。 |
| **7. 生成器与写盘前检查** | `model.py`、`verify.py` 对规则冲突、死规则、URL 安全性、端口/CIDR 合法性、Stash/SFA 三个新测速间隔（含 `model.py` 强制完整版 `stash_select_interval_s < 0` 与 `verify.check_stash` / `check_simple`）管得很严；需补齐 C1（Loon `ip-mode`）和 C2/C3（`nodes.py` 节点转换与 `verify.check_singbox`）的写盘前拦截。另外审查了 `r20_full_private_same.py` 与 `r21_private_vs_r20.py` 的核对逻辑：对当前 r20→r21 的变更足够充分，下一版按 `docs/08` 第 20 轮记下的补上 `manifest.json` 对比即可。 |
| **8. 测试与检查工具** | 349 项单测与 210 类变异设计覆盖面极广（M203–M210 已覆盖 r21 三个间隔；M182 因 `600s` 下 `max(3*600, 1800) == 1800` 不改变产物、由 `test_duration_parser` 捕获，解释属实）。需修 C9 中 Windows 下 `Socks5Recorder` 的 TCP `RST` 必败及脚本跨平台问题。 |
| **9. 文档与证据** | `docs/evidence/` 全部日志的 SHA-256、条数、运行时间与代码状态哈希 `eca139fa…` 对得上；事实、源码推断、未验证在正文主体区分清晰。需修 C6、C7、C8 的残留旧表述与 Loon 版本号说明。 |
| **10. 安全与隐私** | 全仓代码、`dist/` 25 个公开产物、`docs/`、`handoff/`、`tests/` 及 Git 历史均只含 `https://REPLACE-ME.invalid/...`、`example.com` 等测试占位符，无任何订阅链接、真实节点或凭据；`dist/private/` 与 `source/local.yaml` 均在 `.gitignore` 中并有单测守护。 |

---

## 五、验证边界

### 1. 本次实际运行并核对结果的命令

在 Windows（Python `3.12.13`、`PyYAML 6.0.3`）隔离虚拟环境中对提交 `b9a9f14598d300495859c6390559646e5c81254f` 实际运行了以下检查：

1. `python build.py --check` → **通过（退出码 0）**：`产物与统一源一致（含 manifest.json）。`
2. `bash handoff/release/code_state.sh` → 复现了 MSYS2 `sha256sum` 二进制模式 `*` 前缀差异；归一化 ` *` → `  ` 后输出 **`eca139fa64d9b4ea4e2d286a358b4c1ca616d700e12eeb4c4631704068a7c32a`**，与 `docs/05` 定稿记录完全一致。
3. `python -B handoff/release/r21-as-used/recheck_r21b.py` → 复现了 Windows 反斜杠路径问题（见 C9）；归一化路径斜杠与 `code_state` 后输出 **`相对 r21（c0e8707）只改了文档；代码状态 eca139fa… 与定稿时相同；文档核对 119 项、旧说法 116 条都对。核对通过`**。
4. `python -B -m unittest discover -s tests -v`（349 项，耗时 515 秒）→ **343 项通过，1 项失败（`test_records_every_request_it_refuses`，见 C9），5 项按平台条件跳过**（3 项依赖 Linux `/proc/net/udp`，2 项在 PowerShell 默认无 `bash` 时跳过、加入 Git Bash 后复现 `python3` 退出码 49）。
5. `python -B tools/check_icu.py --public --verbose`（调用系统 `icu.dll`）→ **通过（退出码 0）**：13+1 条正则 × 2290/2313 节点名 + 860 个超长名与 Python 100% 一致。
6. `python -B tools/check_cursor_report.py` → **通过（退出码 0）**。
7. `python -B tools/check_icons.py --icon-repo <ixxooxo-alt/icon@f250126>` → **通过（退出码 0）**：82 个组名、81 张 PNG 全部核对通过。
8. `python -B tools/update_cn_list.py --dlc <dlc@c1c2cf0d> --bm7 <bm7@51d2e1dd> --check` → **通过（退出码 0）**。
9. `python -B tools/check_upstream_evidence.py --dlc <dlc@c1c2cf0d> --bm7 <bm7@51d2e1dd>` → **通过（退出码 0）**：856 条规则、561 条社区来源及 48 条产品下上游广告规则全部核对一致。
10. `python -B tools/verify_with_upstream_source.py --mihomo-src <mihomo@ab405ba> --singbox-src <sing-box@1ac1a33>` → **通过（退出码 0）**：8,368 处字段与枚举值对照 Go 源码结构体标签全部通过。
11. `python -B tools/check_official.py`（使用官方发布页校验过 SHA-256 的 `mihomo v1.19.31`、`sing-box v1.14.1`、`sing-box v1.12.0` 及 `meta-rules-dat@f7c0420`）→ **通过（退出码 0）**：4 份 `mihomo -t`、10 份 `sing-box check`、3 项反向自检及 3 轮 `mihomo` 实际启动节点分组全部通过。
12. `python -B tools/check_real_routes.py`（同上官方二进制 + `meta-rules-dat@f7c0420`、`sing-geosite@be94d52`、`sing-geoip@7fe82a8`、`bm7@51d2e1d`、`dlc@c1c2cf0`，耗时约 17 分钟）→ **通过（退出码 0，`全部一致`）**：290 项探测（270 个目标）、DNS/连接/静默境外 DNS/出站解析核对，以及 222,353 个主机的全量扫描（`0` 处代理域名落入国内 DNS）。
13. `python -B tools/check_mutations.py --check-edits` → **通过（退出码 0，210/210 个变异均可干净套用）**，并抽跑单类变异（如 `M6`）验证流程，同时用官方 `mihomo` 与 `sing-box` 二进制实证复现了 C2 与 C3 的全部测试用例。

### 2. 本次阅读与对照的范围

- **仓库内文件**：完整阅读了 `00-审核说明.md`、两份 `README`、`PROJECT_STATE.md`、`CLAUDE.md`、`docs/00`–`docs/10` 全部 11 份文档、`handoff/` 脚本、`build.py`、`generator/` 全部 13 个模块、`source/` 全部 YAML（含 `services/*.yaml` 全量规则）、`tests/` 全部测试文件、`tools/` 全部检查脚本、`dist/manifest.json` 及五端代表产物、`docs/evidence/` 日志。
- **外部权威资料**：实时拉取并核对了 Loon 官方文档（`nsloon.app/docs/`）、Quantumult X 官方样例配置（`crossutility/Quantumult-X` `sample.conf` build 914）、Stash 官方文档（`stash.wiki`），以及固定提交的 `mihomo`（`v1.19.31`）与 `sing-box`（`v1.14.1`）Go 源码。

### 3. 本次未做的事项

1. **没有真机环境**：未在 iPhone / iPad / Mac / Android 真机上实际导入运行 Loon、Quantumult X、Stash、SFA、Clash Verge Rev / CMFA（故 Loon 严格版单行 `GEOIP,CN,国内直连,no-resolve`、Loon/QX 简易版“组名 + 筛选正则”混写、Stash `fallback` 嵌 `interval: -1` 的 `select` 子组时的测速细节等客户端闭源运行时行为，仍以真机按 `docs/09` 验收为准）。
2. **未跑全量 210 类变异测试**：仅执行了 `--check-edits` 全量补丁可套用性检查及代表性变异实跑，未耗时 5–6 小时跑完全部 210 类。
3. **未提交 GitHub PR**：因当前审核机器未登录 GitHub 凭据，未推送分支或创建 PR，仓库本地副本保持未修改状态。
