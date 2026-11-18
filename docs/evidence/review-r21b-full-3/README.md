# `ixxooxo-alt/proxy` 全量工程审核报告（`b9a9f14` / r21b）

- **审核对象**：公开仓库 `https://github.com/ixxooxo-alt/proxy` 分支 `claude/r12-gpt-review-handling-q4onlv`，提交 `b9a9f14598d300495859c6390559646e5c81254f`（统一源 `2026.10.31-1`、生成器 `1.12.1`、简易版 `2026.10.31-2`；与 `main` 上的 `a6671c1db4f1a7c26df4fba1925648c97143d34d` 配置与产物完全一致，仅多 `63e66e4`、`b9a9f14` 两个纯文档提交）。
- **交付方式说明**：当前审核环境未登录 GitHub 凭据（`gh` 未授权），无法推送分支或创建 PR，按 [00-审核说明.md](<审核方本机的工程目录>/00-审核说明.md)“开不了 PR 就写报告”直接交付完整报告；本地检出库保持干净，未改动 `dist/`、`docs/evidence/`、[00-需求原文.md](<审核方本机的工程目录>/docs/00-需求原文.md) 或任何远端分支。

---

## 一、总体结论

1. **有没有确定的导入失败**：**没有**。25 个公开产物（完整版 10 份、简易版 10 份、严格版引用的 4 个规则文件及 [manifest.json](<审核方本机的工程目录>/dist/manifest.json)）语法与结构均符合对应客户端文档或官方内核校验：官方 `mihomo v1.19.31 -t`（4 份配置）、官方 `sing-box 1.14.1` 与 `1.12.0 check`（4 份模板 + 带样例节点的私密转换共 10 项）、上游结构体标签核对（8,368 个字段/取值）全部通过。
2. **有没有确定的分流错误、DNS 路径偏差或泄漏**：**确认 6 项问题**（前 20 轮审核均未覆盖），其中影响配置行为或规则完整性的有 4 项，影响测试与核对工具有 2 项：
   - **[F01｜分流错误 / 文档不符]**：`mihomo` 全部 4 份配置里，系统联网检测域名 `msftconnecttest.com`、`msftncsi.com`、`captive.apple.com` 的设备侧 DNS 查询（TUN 接管 53 端口）未写进 `nameserver-policy`，经官方 `mihomo v1.19.31` 实测落入**境外 DoH（经代理）**而非国内 DoH；在酒店/机场强制门户（Captive Portal）认证前或默认代理节点不可用时会导致系统联网检测解析失败，且与 `sing-box`（走 `dns-cn`）及 [03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L11-L12) 的描述不符（不造成境外域名向国内 DNS 泄漏）。
   - **[F02｜分流错误]**：Cursor 官方登录文档已将新登录域名更新为 `accounts.spacexsi.com`（`*.spacexsi.com`），并写明旧页回退在 11 月 30 日停用后登录必须使用 `accounts.spacexsi.com`；统一源仍只收录早期的 `spacex.ai`，导致 `accounts.spacexsi.com` 未进 `Grok` 组而落入 `国外默认`（且在 Loon / Quantumult X 标准版上会先触发本机国内 DNS 解析）。
   - **[F03｜分流错误 / 安全或泄漏]**：用户若照 [local.example.yaml](<审核方本机的工程目录>/source/local.example.yaml#L20-L25) 在 `local.yaml` 中写 `group: DIRECT` 的 `extra_services` 域名规则，且该域名落在某个走代理的产品后缀之下（如 `internal.microsoft.com`、`cn-mirror.github.com`），生成器不会在 `mihomo` 的 `nameserver-policy` 或 `sing-box` 的 `dns.rules` 中生成直连豁免层；经官方内核实测，`mihomo` 连 `DIRECT` 直连拨号都会去问境外 DoH。公开产物不受此条影响。
   - **[F04｜安全或泄漏 / 文档不符]**：`sing-box` 未设 `dns.reverse_mapping: true`。按 `sing-box v1.14.1` 源码推导，TUN 模式下 `dns.real_ip` 里不带 SNI/Host 的纯 UDP 流量（如 NTP `time.windows.com`、`time.apple.com`、`*.pool.ntp.org`）先由国内 DoH（`dns-cn`）拿到真实非国内 IP，后续 UDP 包进入 TUN 时因无反向映射且 `sniff.NTP` 提不出域名，命中不了第 2b 阶段域名直连规则，最终仍走 `国外默认`（即“国内 DNS 解析 + 代理出口”），使文档中第 15 项“四端标准版都固定直连，这一类没有了”在 `sing-box` TUN 路径上说过了头。
   - **[F05｜建议 / 文档不符]**（测试与变异工具缺陷）：[check_real_routes.py](<审核方本机的工程目录>/tools/check_real_routes.py#L1003-L1034) 的 `Socks5Recorder._serve` 拒绝不支持的命令时未读完请求剩余字节即 `close()`，触发 TCP `RST`，导致 Windows 上运行 `python -m unittest discover -s tests` 必现 1 项失败（`test_records_every_request_it_refuses`），进而使 `check_mutations.py` 在 Windows 上因基线退出码非 0 把跑全量测试的变异一律误判为 `[发现]`。
   - **[F06｜建议]**（核对与复核工具跨平台缺陷）：[real_data.py](<审核方本机的工程目录>/tools/real_data.py#L309) 用 `os.sep + "Clash" + os.sep` 识别格式，Windows 下若传入正斜杠路径会静默把 11 万余条 `+.后缀` 误读为字面精确域名而不报错；[recheck_r21b.py](<审核方本机的工程目录>/handoff/release/r21-as-used/recheck_r21b.py#L72-L85)、[finalize.py](<审核方本机的工程目录>/handoff/release/r21-as-used/finalize.py#L472-L507) 与 [code_state.sh](<审核方本机的工程目录>/handoff/release/code_state.sh#L1-L10) 在 Windows 上也有路径分隔符与 `sha256sum` 二进制星号差异。
3. **这一版能不能照现在这样用**：**可以照现在这样使用**（替换订阅占位符并按 [01-导入、更新、诊断与回滚.md](<审核方本机的工程目录>/docs/01-导入、更新、诊断与回滚.md) 与 [09-真机验收操作清单.md](<审核方本机的工程目录>/docs/09-真机验收操作清单.md) 确认客户端开关后即可日常使用）。两条最高优先级目标（国内常用网站不变慢；常规走代理的网站域名不交给国内 DNS）在当前公开配置中均成立；确认的几项问题边界清晰（强制门户/断代理时的 `mihomo` 联网检测解析、Cursor 新登录域名 `spacexsi.com`、`local.yaml` 特定写法、`sing-box` TUN 下 NTP 包去向），建议在下一版按“一个问题一个提交”修补。

---

## 二、已确认的问题（Confirmed Issues）

### F01：`mihomo` 的 `nameserver-policy` 漏掉 `connectivity_check` 三条 `real_ip` 域名，设备侧查询落入境外 DoH

- **严重程度**：`分流错误` / `文档不符`
- **位置**：
  - [emit_mihomo.py](<审核方本机的工程目录>/generator/emit_mihomo.py#L337-L338)（及 [model.py](<审核方本机的工程目录>/generator/model.py#L780-L791)）
  - 产物：[mihomo-profile.yaml](<审核方本机的工程目录>/dist/mihomo/mihomo-profile.yaml#L30-L49)、`dist/mihomo/mihomo-core.yaml`、`dist/mihomo/mihomo-simple-profile.yaml`、`dist/mihomo/mihomo-simple-core.yaml`
  - 文档：[03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L11-L12)、第 167 行、第 347 行
- **为什么错**：
  1. [project.yaml](<审核方本机的工程目录>/source/project.yaml#L108-L124) 的 `dns.real_ip` 共 15 条：4 条局域网后缀 + **3 条系统联网检测域名**（`msftconnecttest.com`、`msftncsi.com`、`captive.apple.com`）+ 8 条对时与运营商认证域名。
  2. 在 `sing-box` 生成器（[emit_singbox.py](<审核方本机的工程目录>/generator/emit_singbox.py#L301-L303)）中，直接从 `dns["real_ip"]` 排除 `lan_sfx` 生成第 2 条 DNS 规则，因此**全部 11 条非局域网 `real_ip` 域名都交给 `dns-cn`**（[sing-box-1.14.json](<审核方本机的工程目录>/dist/sing-box/sing-box-1.14.json#L41-L56)）。
  3. 但在 `mihomo` 生成器（[emit_mihomo.py](<审核方本机的工程目录>/generator/emit_mihomo.py#L337-L338)）中，遍历的是 `plan.real_ip_direct`；而 `build_plan()`（[model.py](<审核方本机的工程目录>/generator/model.py#L780-L791)）为了避免**路由规则**与 `plan.lan`（含 [misc.yaml](<审核方本机的工程目录>/source/services/misc.yaml#L91-L101) 的 `connectivity_check`）重复，把已在 `lan_keys` 里的 `msftconnecttest.com`、`msftncsi.com`、`captive.apple.com` 剔除了。
  4. 结果：`mihomo` 的 `fake-ip-filter` 里有 `+.msftconnecttest.com`、`+.msftncsi.com`、`captive.apple.com`（不给假地址、要求立即解析真实 IP），但 `nameserver-policy` 里没有这三条；而 MetaCubeX 的 `geosite.dat` 中这三者都在 `geolocation-!cn`、不在 `cn` 或 `private`，于是 TUN 接管的系统联网检测 DNS 查询一路穿透 `nameserver-policy`，落到 `dns.nameserver`（**经代理发出的境外 DoH `1.1.1.1` / `8.8.8.8`**）。
  5. **实际后果**：① 在酒店/机场/校园网强制门户（未登录前外网与代理节点不通）或默认代理组（完整版 `日本` / 简易版 `境外DNS`）无可用节点时，Windows NCSI（`www.msftconnecttest.com`、`dns.msftncsi.com`）与 Apple 强制门户（`captive.apple.com`）在 DNS 阶段即超时失败，无法反映本地物理网络状态或弹出门户登录页，违背 [misc.yaml](<审核方本机的工程目录>/source/services/misc.yaml#L90)“反映本地网络，固定直连”及 [03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L11) 的验收预期；② 代理正常时，境外 DoH 按日本/美国出口返回境外边缘 IP，`mihomo` 记录映射后又按 `DIRECT` 从国内直连该境外 IP。
- **依据**：
  - 官方 `mihomo v1.19.31` 实测（复用 `check_real_routes.mihomo_dial_probe` 替身框架）：设备查询 `captive.apple.com A -> foreign`、`www.msftconnecttest.com A -> foreign`、`dns.msftncsi.com A -> foreign`（同批对照 `time.apple.com A -> domestic`、`time.windows.com A -> domestic`；同机 `sing-box v1.14.1` 实测上述三条均为 `dns-cn`）。
  - `mihomo v1.19.31` 源码 `dns/middleware.go:155-157, 199-219`（命中 `fake-ip-filter` 跳过 FakeIP 后交给默认 `resolver.ExchangeContext`，按 `nameserver-policy` -> `nameserver` 查询）。
- **建议怎么改**：
  - 在 [emit_mihomo.py](<审核方本机的工程目录>/generator/emit_mihomo.py#L337-L338) 中改为与 `emit_singbox.py` 同一口径，从 `dns["real_ip"]` 排除 `lan["domain_suffix"]` 写入 `domestic_layer`（共 11 条）；同步把 [03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L12) 中“8 条”更正为非局域网的 11 条（路由第 2b 阶段补齐其余 8 条），并在 [cases.yaml](<审核方本机的工程目录>/tests/cases.yaml#L386) 的 `mihomo_dns` 增加 `captive.apple.com` 与 `www.msftconnecttest.com` 用例。

---

### F02：Cursor 官方登录域名已变更为 `accounts.spacexsi.com`（`*.spacexsi.com`），统一源缺失该后缀

- **严重程度**：`分流错误`
- **位置**：
  - [ai.yaml](<审核方本机的工程目录>/source/services/ai.yaml#L60-L73)（`id: cursor`，`group: Grok`）
  - [evidence.yaml](<审核方本机的工程目录>/source/evidence.yaml#L32-L36)（`cursor-signin`）
- **为什么错**：
  - 统一源按 2026-09-30 查阅结果收录了 `{suffix: spacex.ai, ev: cursor-signin}`，未收录 `spacexsi.com`。
  - 本次实时核对同一官方页面，Cursor 已将新登录入口改为 `accounts.spacexsi.com`（建议整段放行 `*.spacexsi.com`），并明确写明旧页 `authenticator.cursor.sh` 的临时回退在 **11 月 30 日退役后，登录必须走 `accounts.spacexsi.com`**。
  - 当前 `accounts.spacexsi.com` 在全部客户端上均不命中 `Grok` 组而落入 `国外默认`：当用户将 `Grok` 组切到特定地区（如美国）而 `国外默认` 在日本时，登录链路与编辑器会话会跨国分裂；在 Loon / Quantumult X 标准版上，`accounts.spacexsi.com` 因未命中任何域名规则，还会先触发本机国内 DNS 解析（国内 DNS 可见，且若被污染成国内 IP 会命中 `GEOIP,CN` 直连导致登录失败）。
- **依据**：
  - Cursor 官方文档 `https://cursor.com/help/troubleshooting/sign-in-domains`（实时抓取原文：*“Cursor sign-in is moving to `accounts.spacexsi.com` (replacing `authenticator.cursor.sh` as the sign-in page). ... Once it is retired on November 30, sign-in requires `accounts.spacexsi.com`.”*，放行清单首条为 `*.spacexsi.com`）。
  - 同次复核另外两份登记的官方清单也发现新增专属主机（可作为同批补充建议）：
    1. Cursor 企业网络文档 `https://cursor.com/docs/enterprise/network-configuration` 新增桌面端专属存储主机 `agent-stores.s3.us-east-1.amazonaws.com`、`agent-stores.s3.amazonaws.com`（同步 skills 与 agent 文件）及 `cursor.blob.core.windows.net`（Windows Remote SSH 服务端下载），与已收录的 `anysphere-binaries.s3.us-east-1.amazonaws.com` 性质完全相同。
    2. GitHub Copilot 官方放行清单 `https://docs.github.com/en/copilot/reference/allowlist-reference` 新增实时事件流 WebSocket 专属主机 `production-copilot-host.webpubsub.azure.com` 及 `production-copilot-host-{centralus,centralus-02,eastasia,austriaeast,westus,westus3}.webpubsub.azure.com`（因 `azure.com` 按共享云根域禁收，这些主机当前落入 `国外默认` 而非 `Copilot`）。
- **建议怎么改**：
  - 在 [ai.yaml](<审核方本机的工程目录>/source/services/ai.yaml#L72) 的 `cursor` 服务下补 `{suffix: spacexsi.com, ev: cursor-signin}`（保留 `spacex.ai` 以兼容过渡期），更新 [evidence.yaml](<审核方本机的工程目录>/source/evidence.yaml#L32-L36) 的查阅日期与说明，并在 [cases.yaml](<审核方本机的工程目录>/tests/cases.yaml#L146) 补 `accounts.spacexsi.com -> Grok`；按同一收录原则评估补入上述 3 个 Cursor 专属存储主机与 7 个 Copilot WebSocket 主机。

---

### F03：`local.yaml` 中 `group: DIRECT` 的 `extra_services` 域名规则未参与 `mihomo` 与 `sing-box` 的产品 DNS 分层

- **严重程度**：`分流错误` / `安全或泄漏`（仅影响使用 `local.yaml` 生成的私密配置 `dist/private/`，不影响 25 个公开产物）
- **位置**：
  - [model.py](<审核方本机的工程目录>/generator/model.py#L491-L500)、[model.py](<审核方本机的工程目录>/generator/model.py#L780-L794)
  - [emit_mihomo.py](<审核方本机的工程目录>/generator/emit_mihomo.py#L66-L96)、第 340–341 行
  - [emit_singbox.py](<审核方本机的工程目录>/generator/emit_singbox.py#L109-L130)
  - 示例：[local.example.yaml](<审核方本机的工程目录>/source/local.example.yaml#L20-L25)
- **为什么错**：
  1. [local.example.yaml](<审核方本机的工程目录>/source/local.example.yaml#L20-L25) 示范用户用 `group: DIRECT` 编写本地直连规则。[model.py](<审核方本机的工程目录>/generator/model.py#L495) 将 `s["group"] == "DIRECT"` 的规则设为 `stage = "lan"`，并在 `build_plan()` 中放入 `plan.lan` 而非 `plan.product`。
  2. 但 `emit_mihomo.product_dns_policy`（[emit_mihomo.py](<审核方本机的工程目录>/generator/emit_mihomo.py#L67)）和 `emit_singbox.dns_layers`（[emit_singbox.py](<审核方本机的工程目录>/generator/emit_singbox.py#L109)）都只取 `plan.exceptions + plan.product_for(...)`，完全没看 `plan.lan`。
  3. 一旦用户在 `local.yaml` 里把某个走代理的产品根域下的子域设为 `group: DIRECT`（例如企业自用子域 `internal.microsoft.com`、镜像子域 `cn-mirror.github.com`），路由第 2 阶段虽然将连接判给 `DIRECT`，但 DNS 侧仍只看到外层的 `+.microsoft.com: *dns-foreign` / `product-proxied`：
     - 在 `mihomo` 上，由于开了 `direct-nameserver-follow-policy: true`，**连 `DIRECT` 出站拨号都会去问境外 DoH**（同时把企业子域名发给经代理的境外公共 DNS，且拿到境外 CDN 地址后直连）；
     - 在 `sing-box` 上，A 查询拿到 `dns-fakeip`（而非像 `delivery.mp.microsoft.com` 那样给 `dns-cn`），HTTPS/SVCB 等非地址查询则发往 `dns-foreign`。
  4. 此外，若用户在 `local.yaml` 中添加非 `DIRECT` 规则且域名恰好与 `dns.real_ip` 同值（如 `domain: time.windows.com`），`model._validate` 不会拦截，直到 [emit_mihomo.py](<审核方本机的工程目录>/generator/emit_mihomo.py#L340-L341) 抛出未包装的 `ValueError`（而 `emit_singbox` 甚至不报错）。
- **依据**：
  - 官方内核实测：构造含 `{suffix: internal.microsoft.com, group: DIRECT}` 的模型交给官方 `mihomo v1.19.31` 与 `sing-box v1.14.1`，实测得到 `mihomo` 的 `direct app.internal.microsoft.com -> foreign`、`b.internal.microsoft.com TXT -> foreign`，`sing-box` 的 `app.internal.microsoft.com HTTPS -> dns-foreign`（路由为 `DIRECT`）。
- **建议怎么改**：
  - 在 `product_dns_policy`（[emit_mihomo.py](<审核方本机的工程目录>/generator/emit_mihomo.py#L66-L67)）把 `"DIRECT"` 加入直连目标集合，并将 `s.group == "DIRECT"` 的服务域名规则（排除已在 `lan.domain_suffix` 与 `dns.real_ip` 中的项）一并纳入 `rules` 参与覆盖深度计算；在 `dns_layers`（[emit_singbox.py](<审核方本机的工程目录>/generator/emit_singbox.py#L109-L110)）同样将这类规则与 `DOMESTIC_GROUP` 一同视作直连层。同时在 `model._validate` 中校验服务规则与 `dns.real_ip` / `lan.domain_suffix` 冲突并报 `SourceError`。

---

### F04：`sing-box` 未开启 `dns.reverse_mapping`，TUN 下 `real_ip` 中的无 SNI 纯 UDP 流量（如 NTP）仍会“国内 DNS 解析 + 代理出口”

- **严重程度**：`安全或泄漏` / `文档不符`
- **位置**：
  - [emit_singbox.py](<审核方本机的工程目录>/generator/emit_singbox.py#L334-L341)
  - 产物：[sing-box-1.14.json](<审核方本机的工程目录>/dist/sing-box/sing-box-1.14.json#L6-L110)（及 `1.12`、`simple-1.14`、`simple-1.12`）
  - 文档与注释：[model.py](<审核方本机的工程目录>/generator/model.py#L741-L743)、[03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L12)（及第 56、299 行）、[06-已知限制与待决事项.md](<审核方本机的工程目录>/docs/06-已知限制与待决事项.md#L62)（第 15 项）
- **为什么错**：
  1. `sing-box` 配置唯一的入站是 `tun-in`。对 `dns.real_ip` 里的对时域名（`time.windows.com`、`time.apple.com`、`*.pool.ntp.org`），设备先发 DNS A 查询，命中 `dns.rules[1]` 由国内 DoH（`dns-cn`）解析并返回**真实公网 IP**（非 FakeIP，通常是非国内 IP，如 `20.189.79.72`、`17.253.84.123`）。
  2. 随后操作系统向 `<真实IP>:123` 发送二进制 NTP UDP 报文进入 `tun-in`。在 `sing-box v1.14.1` 的 `prepareMatchMetadata` 中：
     - 目标不是 FakeIP，`FakeIP().Store().Contains(...)` 为假；
     - 接着调用 `r.dns.LookupReverseMapping(addr)`，但因 `dns.reverse_mapping` 未配置（默认 `false`），`r.dnsReverseMapping` 为 `nil`，永远返回 `("", false)`；
     - 第 1 条路由规则 `{"action": "sniff"}` 对 UDP 调用 `sniff.NTP`，它只标记 `metadata.Protocol = "ntp"`，无法从二进制 NTP 报文中提取任何域名；
     - 结果 `metadata.Domain` 为空，第 2b 阶段的域名规则（`domain: ["time.apple.com", "time.windows.com", ...], outbound: "DIRECT"`）**根本不会命中**；非国内 IP 又不命中 `geoip-cn`，最终落入 `route.final: "国外默认"` 经代理发出。
  3. 对比 `mihomo`：`mihomo v1.19.31` 在 `enhanced-mode: fake-ip` 下默认同时启用 4096 条 `mapping` 缓存（`dns/enhancer.go:178-189`、`dns/middleware.go:99-146`），即使命中 `fake-ip-filter` 返回真实 IP，也会把 `真实IP -> 域名` 写入 `mapping`，因此 `mihomo` 在 TUN 下仍能还原 `time.windows.com` 并命中 `DIRECT`。
  4. 本项目的 `dns_route_consistency.py` 与 `check_real_routes.py`（`outbound_resolve`）之所以没发现，是因为测试走的是本机 SOCKS5 代理入站、直接传域名 `ATYP=0x03`，跳过了 TUN 的“DNS 拿真实 IP → 纯 IP UDP 包”两步链路。因此文档中称第 15 项改完后“四端标准版都固定直连，这一类（国内 DNS 解析 + 代理出口）没有了”，对 `sing-box` 的 TUN 纯 UDP 非国内地址不成立。
- **依据**：
  - 官方 `sing-box v1.14.1`（提交 `1ac1a339cb12`）源码：`option/dns.go:18-24`（`ReverseMapping bool json:"reverse_mapping,omitempty"`）、`dns/router.go:116-118, 1385-1391`（仅在 `options.ReverseMapping` 为真时初始化 `dnsReverseMapping`）、`route/route.go:32-40, 353-372, 564-584`（非 FakeIP 仅靠 `LookupReverseMapping` 或 `sniff` 恢复域名，而 NTP 报文不含域名）。
- **建议怎么改**：
  - 方案 A（改配置）：在 [emit_singbox.py](<审核方本机的工程目录>/generator/emit_singbox.py#L334-L338) 的 `dns` 对象中评估开启 `"reverse_mapping": True`（`1.12` 与 `1.14` 的 `RawDNSOptions` 均支持该字段；需留意 CDN 多域名共用同一真实 IP 时反向映射按最近一次查询覆盖的已知特性），或对 `protocol: ntp` 视需求处理。
  - 方案 B（只改说明）：若维持配置不变，把 [03-DNS决策表.md](<审核方本机的工程目录>/docs/03-DNS决策表.md#L56)（及第 299 行）与 [06-已知限制与待决事项.md](<审核方本机的工程目录>/docs/06-已知限制与待决事项.md#L62) 第 15 项限定为“带域名入站或能嗅探出 Host/SNI 的连接固定直连；`sing-box` TUN 模式下不带 SNI 的 NTP 等纯 IP UDP 报文若解析到非国内 IP，因未开 `reverse_mapping` 仍会走 `国外默认`”。

---

### F05：`Socks5Recorder._serve` 提前 `close()` 触发 TCP `RST`，导致 Windows 下单元测试失败并污染变异检查判定

- **严重程度**：`建议` / `文档不符`（测试与验证工具问题，不影响 `dist/` 产物）
- **位置**：
  - [check_real_routes.py](<审核方本机的工程目录>/tools/check_real_routes.py#L1003-L1034)（`Socks5Recorder._serve`）
  - [test_real_data.py](<审核方本机的工程目录>/tests/test_real_data.py#L948-L970)（`Socks5RecorderTool.test_records_every_request_it_refuses`）
  - 关联影响：[check_mutations.py](<审核方本机的工程目录>/tools/check_mutations.py#L52)、[00-审核说明.md](<审核方本机的工程目录>/00-审核说明.md#L107)
- **为什么错**：
  1. 在 [test_real_data.py](<审核方本机的工程目录>/tests/test_real_data.py#L970) 中，`talk(b"\x05\x01\x00", b"\x05\x02\x00\x01" + bytes(6), half_close=False)` 发送 10 字节的 SOCKS5 `BIND` 请求（`cmd=0x02`），并在 `s.recv(64)` 之前 `time.sleep(0.15)`。
  2. 服务端 `_serve` 在第 1003 行只调用 `ver, cmd, rsv = need(3)` 读走前 3 字节（接收缓冲区中仍残留 7 字节未读数据 `\x01` + 6 个 `\x00`；第 1004 行 `ver != 5 or rsv != 0` 分支同理），发送 `05 07 ...` 错误应答后直接 `return`，进入第 1034 行 `finally: c.close()`。
  3. 按 TCP 规范（RFC 1122 §4.2.2.13、RFC 9293 §3.6.1），套接字接收缓冲区尚有应用层未读数据时执行 `close()`，内核协议栈会发送异常中断的 **TCP `RST`** 而非正常的 `FIN`。在 Windows Winsock 上，客户端在 `0.15s` 等待期间收到 `RST` 会立即丢弃未读缓冲并让首次 `s.recv(64)` 抛出 `ConnectionResetError [WinError 10054]`；`talk()` 在第 963–964 行 `except OSError: pass` 吞掉异常返回 `b""`，导致第 970 行断言 `AssertionError: b'' != b'\x05\x07'` 稳定失败（全套测试结果为 `Ran 349 tests: FAILED (failures=1, skipped=3)`）。
  4. **连带影响**：[check_mutations.py](<审核方本机的工程目录>/tools/check_mutations.py#L52) 目前仅以 `r.returncode != 0` 判定 `[发现]`（`docs/08` 第 20 轮已记留待下版收紧）。在 Windows 上由于基线本身就有这 1 项失败，任何跑全套测试的变异都会自动满足 `returncode != 0` 而被误判为 `[发现]`。
- **依据**：
  - 本次在 Windows + Python 3.14.5 上运行全量测试与单独复现 `python -m unittest discover -s tests -p test_real_data.py -k test_records_every_request_it_refuses` 稳定复现；抓取底层异常确认为 `ConnectionResetError: [WinError 10054]`。
  - RFC 1122 §4.2.2.13 / RFC 9293 §3.6.1（有未读接收数据时关闭连接发送 `RST`）。
- **建议怎么改**：
  - 在 [check_real_routes.py](<审核方本机的工程目录>/tools/check_real_routes.py#L1034) `finally:` 关闭连接前，先 `c.shutdown(socket.SHUT_WR)` 并设短超时（如 `0.1s`）排空客户端已发出的剩余请求字节后再 `c.close()`，保证正常发 `FIN`。同时在文档中注明有 3 项 `/proc/net/udp` 相关测试在非 Linux 系统上会 `skip`（Linux 上为 349 项无跳过通过）。

---

### F06：`tools/real_data.py` 与发布复核脚本的路径分隔符 / `sha256sum` 跨平台缺陷

- **严重程度**：`建议`（影响核对工具与复核脚本的跨平台可靠性，其中第 1 点可导致静默误判）
- **位置**：
  - [real_data.py](<审核方本机的工程目录>/tools/real_data.py#L308-L311)（`read_remote`）
  - [recheck_r21b.py](<审核方本机的工程目录>/handoff/release/r21-as-used/recheck_r21b.py#L36)（及第 71–85 行）、[finalize.py](<审核方本机的工程目录>/handoff/release/r21-as-used/finalize.py#L471-L472)（及第 502–507 行）
  - [code_state.sh](<审核方本机的工程目录>/handoff/release/code_state.sh#L1-L10) 及仓库根目录（缺少 `.gitattributes`）
- **为什么错**：
  1. **`read_remote` 静默误读风险**：[real_data.py](<审核方本机的工程目录>/tools/real_data.py#L309) 写的是 `if path.endswith(".txt") and os.sep + "Clash" + os.sep in path:`。在 Windows 上 `os.sep` 是 `\`，若传入正斜杠路径（例如 Git Bash 路径或 `C:/.../rule/Clash/ChinaMax/ChinaMax_Domain_For_Clash.txt`），条件不成立，会**不报任何错误**而退回 `read_rule_list(path)`。而 `read_rule_list` 把不含逗号且不以 `.` 开头的行一律当作精确域名，导致 `ChinaMax_Domain_For_Clash.txt` 里 11 万余条 `+.cn`、`+.baidu.com` 全部被静默塞进 `domains.full`（变成字面主机名 `"+.cn"`），`domains.suffix` 变成空集！
  2. **`recheck_r21b.py` 与 `finalize.py` 路径分隔符不一致**：第 72 行 `os.path.join("docs", f)` 在 Windows 下生成 `docs\03-DNS决策表.md`，而 `HIST` 与 `STALE` 的豁免列表写死为正斜杠 `"docs/..."`，导致 `p not in allowed and p not in HIST` 全部失灵，误报 26 条旧说法错误。
  3. **`code_state.sh` 与换行符**：仓库无 `.gitattributes`（Windows 默认 `core.autocrlf=true` 检出会变成 CRLF）；即便设为 LF，Git for Windows 自带的 MSYS2 `sha256sum` 默认以二进制模式输出 `<hash> *<file>`（中间是 ` *` 而非 Linux 的两个空格 `  `），导致第二级管道 `| sha256sum` 算出的摘要变成 `cd7527c8...` 而非 `eca139fa...`。
- **依据**：
  - 本次在 Windows 上实测验证：`rd.read_remote(".../rule/Clash/ChinaMax/ChinaMax_Domain_For_Clash.txt")`（正斜杠）得到 `full={'+.cn', '+.baidu.com', ...}`、`suffix=set()`、`why('www.baidu.com')=None`；将路径统一为 `/` 并按文本模式计算 `code_state` 后，`recheck_r21b.py` 的全部 101 行核对逻辑零误差通过。
- **建议怎么改**：
  - `real_data.py:309` 改为 `"/Clash/" in path.replace("\\", "/")`；`recheck_r21b.py` 与 `finalize.py` 改为 `"docs/" + f`；`code_state.sh` 改为 `xargs sha256sum --text`（或用几行 Python 固定按 LF/字节流拼装）并补充 `.gitattributes`（`* text=auto eol=lf`）。

---

## 三、推导观察与改进建议（Inferred / Low-Risk Suggestions）

以下各项不构成当前公开产物的分流错误或导入失败，供后续迭代参考：

1. **`[建议]` 节点名“解锁说明”带圆括号前置时会吞掉后面的落地地区**（[regions.py](<审核方本机的工程目录>/generator/regions.py#L64-L68)、第 495 行）：
   - 现状：`_CLAUSE_REST` 为避免“解锁：美国(Netflix)/日本(Abema)”在右括号处提前结束，令遇到左括号 `(` 时整个跳过分支失效，即从 `解锁` 一直屏蔽到名字末尾。
   - 推导反例（已用 `Classifier` 与正则交叉验证）：当机场把带圆括号的解锁标签写在地区**前面**时，如 `"解锁(Netflix) | 日本 01"` 或 `"[解锁(US)] 日本 01"`，后面的 `日本` 也会被一并屏蔽，导致前者只进 `jp` 手动组（`auto=[]`），后者变成 `groups=['jp', 'us'], auto=[]`（而方括号写法 `"【解锁美国】日本 01"` 能正常进 `jp` 自动组）。
   - 建议：把这类“前置 `解锁(...) | 地区`”记入 [node_names.yaml](<审核方本机的工程目录>/tests/node_names.yaml#L695) 的 `known_limits`（保持正则简单、无回溯风险），或在 `_CLAUSE_REST` 中仅允许跳过单层不含竖线的圆括号片段 `(?:\([^|｜丨()（）]*\)|[^|｜丨(（\[【)）\]】])*`（若改正则须重跑 `check_icu.py` 长名字压测防回溯失控）。
2. **`[建议]` 两项标为“未能重新抓取，需复核”的官方证据已核实一致，可更新状态**（[evidence.yaml](<审核方本机的工程目录>/source/evidence.yaml#L98-L106)）：
   - 本次实时抓取了 `https://core.telegram.org/resources/cidr.txt`（共 14 条：9 条 IPv4 + 5 条 IPv6），与 [social.yaml](<审核方本机的工程目录>/source/services/social.yaml) 中 `telegram` 收录的 14 条 CIDR 逐条完全一致；`https://ai.google.dev/` 官方文档的 Gemini API 端点仍为 `generativelanguage.googleapis.com`。下次更新统一源时可将 `telegram-cidr` 与 `gemini-api` 从 `official_unverified` 更新为 `official` 并记下查阅日期。
3. **`[建议]` `mihomo_outbound_probe` 若未来扩展到简易版需兼容 `#境外DNS` 后缀**（[check_real_routes.py](<审核方本机的工程目录>/tools/check_real_routes.py#L1237-L1246)）：
   - 当前 `check_real_routes.py` 只对 `mihomo-core.yaml` 跑出站探针，工作正常；若后续把 `mihomo-simple-core.yaml` 也纳入出站探针，`stand_in` 查 `kind_of` 时会因地址末尾带 `#境外DNS` 抛 `RuntimeError`，届时可像 `mihomo_dial_probe` 一样先剥离 `#组名` 或映射该键。

---

## 四、十个审核维度的逐项核查结论

| 维度 | 核查结论 |
|---|---|
| **1. 需求符合度** | 对照 [00-需求原文.md](<审核方本机的工程目录>/docs/00-需求原文.md) 全部初始需求与历次补充决定（Cursor+Grok 合并、Apple AI 收窄、Apple Push 独立默认直连、Netflix 取消特殊入口、Bilibili 港澳台默认直连、国内直连固定 `DIRECT`、Loon/QX/Stash 严格版、简易版及 2026-10-31 定的三个测速间隔），策略组拓扑、成员顺序、首次默认出口、PayPal 不跟随国外默认均落实到位。[07-需求对照.md](<审核方本机的工程目录>/docs/07-需求对照.md) 将真机未验项如实标为“已实现·未实测”，唯一说过头的边界见 **F01** 与 **F04**。 |
| **2. 能不能导入** | 25 个公开产物全部逐类核对：官方 `mihomo v1.19.31 -t` 四份全过；`sing-box 1.14.1`（`http_clients` + `default_http_client`）与 `1.12.0`（`download_detour`）四份模板加节点转换共 10 次 `check` 全过；8,368 个结构体字段/枚举全部匹配上游源码；Loon、Quantumult X、Stash 的完整版、简易版、严格版写法均有官方文档依据（Loon 单独一行 `GEOIP,CN,国内直连,no-resolve`、QX 远程规则顺序及 Stash 正则引擎已如实在 `docs/02`、`docs/03`、`docs/09` 标明为待真机确认项）。 |
| **3. 规则归属和先后** | 856 条服务域名规则、98 条自有广告/跟踪拦截、10 条误杀例外经 `order_rules()` 拓扑排序，更具体规则严格排在宽泛规则之前（如 `Apple AI` / `Apple Music/TV` / `Apple Push` 在 `Apple` 前，`Google AI` / `YouTube` 在 `Google` 前，`Copilot` / `delivery.mp.microsoft.com` 在 `Microsoft` 前，`Hulu US` 在 `Disney+` 前），剩余集合不抢独立服务流量；Loon / QX 本地规则优先于远程集合的差异已通过前置 48 条产品根域下广告规则与误杀例外妥善处理。需要补充的是 **F02**（Cursor 新登录域名 `spacexsi.com` 等官方新增端点）。 |
| **4. DNS 与泄漏** | 默认策略下，mihomo 与 sing-box 对走代理组的产品域名及未命中域名均走经代理的境外 DoH / FakeIP，国内域名走国内 DoH，节点服务器与访问目标的局域网名字均走系统/本地 DNS；Loon / QX / Stash 标准版与严格版的取舍、客户端侧口子（TUN 必开、Clash Verge Rev 的 DNS 覆写与 `dns.ipv6` / `strict-route` 改写、macOS 下 `system` 变成 `114.114.114.114`、第 21 项默认直连组手切代理后的限制）在 `docs/03`、`docs/06` 中交代清晰准确。新发现的三处缺口见 **F01**、**F03**、**F04**。 |
| **5. 故障行为与测速间隔** | 完整版“手动优先（fallback）+ 同地区自动兜底、不跨国”在各端实现正确；某地区无节点时 mihomo（`empty-fallback` 默认 `COMPATIBLE` 不会变 `DIRECT`，且无节点不可连）、sing-box（注入 `127.0.0.1:9` 占位节点）、Stash（每个地区注入 `127.0.0.1:1` 占位节点并在筛选开头排除 `DIRECT/REJECT/REJECT-DROP`）、Loon / QX 均不会悄悄退回直连。r21 三个新间隔（Stash 完整版 57 个选择组 `-1`、自动类组 `300` + `lazy: true`；Stash 简易版 51 个组 `3600`；sing-box 简易版“境外DNS” `600s` / `30m`；mihomo 简易版 `3600`）产物数值、源码状态机说明（含 R21-F01 与 R21-F04 修正后的定时器边界）及 Stash 嵌套组待真机确认的边界均准确。 |
| **6. 节点按名称分地区** | [regions.yaml](<审核方本机的工程目录>/source/regions.yaml) 与 `compose` / `compose_strict` / `compose_any` 逻辑严密：不使用肯定前瞻与特殊分隔符，兼顾 Python、ICU（Windows `icu.dll` 实测 2,290 / 2,313 个节点名及 860 个 120/400 字符长名字零差异、最慢毫秒级无回溯失控）与 mihomo `regexp2`（官方内核实测 2,290 / 2,313 个假节点分组与 Python 完全一致）。前置圆括号解锁写法的边界见第三节建议 1。 |
| **7. 生成器与写盘前检查** | [build.py](<审核方本机的工程目录>/build.py) 采用临时文件 + 校验通过后原子替换并在异常时回滚；[verify.py](<审核方本机的工程目录>/generator/verify.py) 覆盖了占位符泄漏、空组、悬挂引用、严格版 `no-resolve`、Stash 负数/正数间隔、mihomo `#组名` 存在性及 sing-box `interval <= idle_timeout` 等关键防线。需补齐 `local.yaml` 的两处校验与分层见 **F03**。 |
| **8. 测试与检查工具** | 349 项测试覆盖面扎实，模拟器与官方内核快照双轨互校；发现的 Windows 跨平台 `RST` 竞态及 `real_data.py` 路径分隔符静默误读见 **F05**、**F06**。 |
| **9. 文档与证据** | [manifest.json](<审核方本机的工程目录>/dist/manifest.json) 源摘要 `eb13aba7…`、代码状态 `eca139fa…`、25 个产物的字节数与短哈希、测试数 349、变异数 210、字段数 8,368、路由目标 270、社区规则 561、自有拦截 98、图标 81 张（6,949,624 字节）等数字与 `docs/evidence/*.log` 完全吻合；事实、源码推断与未验证项区分清晰，未见残留的旧版现状表述。 |
| **10. 安全与隐私** | 全仓 604 个跟踪文件及全部 Git 历史提交扫描通过：无真实订阅链接、无真实节点凭据/密钥/Token/个人敏感信息；公开产物仅含 `https://REPLACE-ME.invalid/请替换为你的订阅链接` 占位符及公开规则/图标地址；[.gitignore](<审核方本机的工程目录>/.gitignore) 正确隔离 `dist/private/` 与 `source/local.yaml`，`mihomo-core.yaml` 控制面仅绑定 `127.0.0.1:9090` 且 `allow-lan: false`。 |

---

## 五、验证边界说明（What Was Run vs. Not Run）

1. **实际运行的检查（Windows Server / Python 3.14.5，PyYAML 6.0.3）**：
   - `python build.py --check`：**通过**（退出码 0，25 个公开产物与统一源一致）。
   - `python -m unittest discover -s tests -v`：运行全部 **349 项**（527.2 秒），345 项通过、3 项因非 Linux 无 `/proc/net/udp` 正常跳过、**1 项失败**（即 **F05** 定位的 `test_records_every_request_it_refuses`）。
   - 代码状态哈希与 `recheck_r21b.py`：复算 LF 口径代码状态哈希为 `eca139fa64d9b4ea4e2d286a358b4c1ca616d700e12eeb4c4631704068a7c32a`（与 `docs/05` 一致）；归一化 Windows 路径分隔符后 `recheck_r21b.py` 全部文档核对项与旧说法检查通过（原始脚本差异见 **F06**）。
   - `python tools/check_icu.py --public --verbose`：**通过**（退出码 0，调用系统 `icu.dll` 核对 14 条正则 × 2,290 / 2,313 个节点名及 860 个长名字）。
   - `python tools/check_cursor_report.py`、`python tools/check_node_names.py --clash tests/node_samples.yaml`、`python tools/check_mutations.py --check-edits`（210/210 可套用）及单类变异 `M6`：**通过**。
   - **官方内核与固定快照检查**：按 GitHub Release 官方摘要下载 Windows `amd64` 版 `mihomo v1.19.31`、`sing-box 1.14.1`、`sing-box 1.12.0` 及 `setup_env.sh` 登记的同 SHA-256 地理数据与规则集，实跑通过：
     - `tools/check_official.py`：**全部符合预期**（退出码 0，含 4 份 mihomo `-t`、10 次 sing-box `check`、3 项负向自检及 2,290 / 2,313 假节点实际分组）；
     - 针对 **F01**、**F03** 的官方 `mihomo v1.19.31` 与 `sing-box v1.14.1` 真实 DNS / 拨号替身探针：**实测复现**；
     - `tools/verify_with_upstream_source.py`（对照 `mihomo ab405bad` 与 `sing-box 1ac1a339` 源码）：**8,368 个字段/取值全部通过**；
     - `tools/check_icons.py`（对照 `ixxooxo-alt/icon f250126f`）：**全部符合**；
     - `tools/check_upstream_evidence.py`（对照 `dlc c1c2cf0d` 与 `bm7 51d2e1dd` 数据文件）：**856 条域名规则、561 条社区来源规则、48 条产品下广告规则核对全部符合**。
   - **官方文档实时核对**：实时抓取核对了 `core.telegram.org/resources/cidr.txt`、`cursor.com/help/troubleshooting/sign-in-domains`、`cursor.com/docs/enterprise/network-configuration`、`code.claude.com/docs/en/network-config`、`code.claude.com/docs/en/desktop`、`docs.github.com/en/copilot/reference/allowlist-reference`、`support.apple.com/en-us/101555`。
2. **未做的项（明确边界）**：
   - **无真机 / 客户端 GUI 实测**：未在 iPhone / iPad / Mac / Android 真机上导入运行 Loon、Quantumult X、Stash、Clash Verge Rev、Clash Meta for Android、SFA（Stash 嵌套 `select` `interval: -1` 对父 `fallback` 的影响、Loon 单行 `GEOIP,CN,国内直连,no-resolve`、QX 远程兜底加载顺序仍需按 `docs/09` 真机验收）。
   - **未重跑全套 210 类变异（约 5–6 小时）与完整 `tools/check_real_routes.py` 全量扫描**：已核对归档 `mutations.log`、`real-route-check.log` 及 `tests/data/real_sets.json` 摘要一致性，并对关键路径用官方内核做了定向实测。
   - **未核对离线附件 `.zip` 包字节哈希**：本次直接检出 GitHub 仓库 `b9a9f14598d300495859c6390559646e5c81254f` 审核，会话中未附带 `.zip` 原件，故不对压缩包文件本身的 SHA-256 作声明。
