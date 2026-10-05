# 分流对照报告

本仓库分支 `cursor/scaffold-proxy-routing-4265`，HEAD `f647ecba9fe8007d2b2e07cad97c2ded67fdc333`（`f647ecb`，Record a full Mihomo and sing-box rule-hit audit）。
另一版是附件 zip 里的 `proxy-rules/`，统一源版本 `2026.09.23-2`（`source/project.yaml`），zip 内没有 git SHA。
本报告只读对照，没有改本分支的任何文件。

## 怎么比的

本仓库以 `rules/manifest.yaml` 的 emit 包为准：发出的规则 533 条（含 Telegram 14 条官方 CIDR）。`steam` 包 `emit: false` 且列表里没有域名行。Disney+、Max、Prime Video、Hulu US、Hulu Japan 的列表文件只有说明，客户端规则是 0。
四端产物核对：Mihomo、Loon、Quantumult X、sing-box 的规则体都与这 533 条的类型、值和顺序一致。Mihomo 最后是 `MATCH,国外默认`，Loon 是 `FINAL,国外默认`，Quantumult X 是 `final, 国外默认`，sing-box 用 `route.final=国外默认`。四端是同一份规则源的语法映射，不是另一套名单。导入和实机仍是未验证。
另一版以 `source/services/*.yaml`、`source/adblock.yaml`、`source/project.yaml` 的局域网段为准，经它自己的 `build_plan` 展开：产品规则 532、服务 IP 14、自有广告 31、误杀例外 9、局域网/联网检测 24，再加 3 条 GEOSITE 和 1 条 GEOIP。`dist/mihomo/mihomo-core.yaml` 规则 615 条，与上述计划加兜底一致，最后是 `MATCH,国外默认`。Loon 与 QX 的本地规则是 612 条（不把 GEOSITE 写进本地规则，广告另挂 blackmatrix7 AdvertisingLite 远程列表）。sing-box 1.14 把多条域名合成少量规则，并用 rule-set 引用 geosite/geoip，所以条数不能和 mihomo 对齐着看。
「两边都有」指同一分流里规则类型和规则值都相同。一边用后缀、一边用被该后缀盖住的精确主机，仍算两条差异，并在理由里说明覆盖关系。
判断只用三种：该收、不该收、不确定。一致表示两边都有、不必取舍。查得到官方页或当日抓到的上游文件就写来源；只在社区列表里出现、本次没有官方表的，标不确定，不把上游出现当成该收。
证据日期：Cursor、Claude、GitHub Copilot、Google supported_domains、v2fly `data/openai`、`data/anthropic`、`data/cursor`、`data/github`、`data/paypal` 为 2026-09-29 抓取。本仓库各包 AUDIT 的访问日是 2026-09-15 至 2026-09-19。另一版证据登记日是 2026-09-23，dlc 快照 `c1c2cf0d252871e8739747714df06e8d2671f72f`。

明细表：`分流对照明细.csv`，共 1021 行。判断计数：该收 687、不确定 177、一致 125、不该收 32。

## 分组结构

两边的可见业务组几乎同一张清单：AI 六组、流媒体（含 Abema、DMM、日本影音、Bilibili 港澳台、Bahamut）、社交、Apple / Apple Music/TV、Google、Microsoft、GitHub、开发下载、远程控制、PayPal、广告拦截、国内直连、国外默认。

| 项目 | 本仓库 | 另一版 |
|---|---|---|
| 七地区 | HK / JP / KR / TW / SG / US / OTHER，组名 `PROXY-XX` | 香港、日本、韩国、台湾、新加坡、美国、其他地区 |
| 同地区自动 | 六个明确地区各有 `PROXY-XX·自动`（url-test）。选择组默认仍是第一片占位叶子，不是「手动优先·自动兜底」。OTHER 纯手动 | 六个明确地区各有手动优先、手动、自动、故障转移、负载均衡。默认入口是「手动优先」：手选失败后同地区自动，不跨国 |
| 国外默认 | 业务组，默认日本，成员是地区入口。无域名行。兜底 MATCH/FINAL/`route.final` 指向它，不指向 DIRECT | 同名组，默认日本，成员是七个地区入口，注释写明全组不可用时不自动跨国。另外用 `GEOSITE,geolocation-!cn` 先把「境外域名」送进这组，再 MATCH |
| Apple AI | 有独立组，默认美国。18 条规则排在广告之后、任何 Apple 通用规则之前 | 没有这个组。多数相关主机被 Apple 组（默认 DIRECT）的 `apple.com` / `icloud.com` / `apple-dns.net` / `mzstatic.com` 吞掉 |
| OpenAI / Claude / Cursor / Google AI / Copilot / 其他 AI | 默认日本。组内选项不含 DIRECT | 默认日本。标准选项含国外默认、七地区和 DIRECT |
| YouTube 等跟随国外默认的组 | `default_follow: 国外默认` | `default: 国外默认` |
| PayPal | 默认 `PayPal·美国固定`，占位节点，可再选地区和 DIRECT，不跟随国外默认 | 同样默认 `PayPal·美国固定`。固定节点名为空时退化为美国组里手选。选项没有国外默认，有 DIRECT |
| Netflix | 默认 `Netflix·解锁入口`（占位节点）。解锁未验证 | 同样默认解锁入口。`verified_node_regex` 为空，注释写明未验证，入口退化为地区选择 |
| Hulu US / Hulu Japan / Bahamut / Bilibili 港澳台 | 默认美国 / 日本 / 台湾 / 台湾（另有香港成员） | 相同 |
| Apple / Apple Music/TV | 默认 DIRECT | 默认 DIRECT |
| 远程控制 | 有组，无规则，默认跟随国外默认 | 有组，默认日本（不跟随国外默认），唯一规则是 `cursorvm.com` |
| 开发下载 | 有组，无规则。Steam 不整包映射，且不发出 | 有组，34 条语言和镜像仓库。没有 Steam 组 |
| 广告拦截 | 默认 REJECT，可改 DIRECT。只有 41 条显式后缀 | 默认 REJECT。自有广告 + 远程集合 |
| 国内直连 | 默认 DIRECT。72 条显式后缀，无 GEOIP | 默认 DIRECT。少量显式条 + `GEOSITE,cn` + `GEOIP,CN` |
| 规则是否直绑地区出口 | 否，规则绑业务组 | 否，规则绑业务组 |

另一版多出来的「手动优先·自动兜底」是它的地区入口模式，不是本仓库已经实现的行为。本仓库文档写明：多叶子加 url-test 不等于运行时故障切换，不得宣称单一入口自动兜底已成立。两边都没有把健康检查结果写成已在实机验证。

本仓库有、另一版没有的分流：Apple AI；共享基础设施（另一版把这些根域拆进 Google/Microsoft 或留给兜底）。
两边都有组、但只有另一版有域名的分流：Disney+、Max、Prime Video、Hulu US、Hulu Japan、Abema、DMM、日本影音、Bilibili 港澳台、其他流媒体、Apple Music/TV、开发下载、远程控制，以及系统联网检测和局域网（本仓库未发路由）。
两边都没有独立组的：Steam（本仓库审计包不发出；另一版没有 Steam）。

## 规则顺序

本仓库 `emit_order`：广告拦截 → Apple AI → OpenAI → Claude → Cursor → Google AI → Copilot → 其他 AI → PayPal → Netflix → YouTube → Hulu US → Hulu Japan → Disney+ → Max → Prime Video → Telegram → Discord → GitHub → WhatsApp → LINE → X → Meta 社交 → Reddit → LinkedIn → Twitch → TikTok → Spotify → Bahamut → Apple → Google → Microsoft → 共享基础设施 → 国内直连 → `MATCH,国外默认`。
要点：广告在产品前；Apple AI 在 Apple 前；Google AI 和 YouTube 在 Google 前；Copilot、GitHub 在 Microsoft 前；其他 AI 在 X 前；WhatsApp 在 Meta 社交前；共享根在产品精确主机之后、国内直连之前。没有局域网段，没有 GEOSITE，没有 GEOIP。

另一版 mihomo 顺序：局域网与联网检测 DIRECT → 广告误杀例外 → 自有广告/跟踪 → `GEOSITE,category-ads-all` → 产品规则（精确域名先于更宽的后缀，跨组覆盖时更具体的在前）→ `GEOSITE,cn` → `GEOSITE,geolocation-!cn` → 服务专属 IP（Telegram CIDR，no-resolve）→ `GEOIP,CN` → `MATCH,国外默认`。
Loon/QX 没有等价的「先写的域名一定先匹配」：远程广告列表排在本地产品规则之后，所以只有写进 local_ads 的产品子域广告能在 Loon/QX 上先被拦截。另一版在 `adblock.yaml` 里写了这个限制。

## DNS

| 项目 | 本仓库 `out/mihomo` | 另一版 `dist/mihomo` |
|---|---|---|
| 模式 | `redir-host`，不用 fake-ip | `fake-ip`，范围 `198.18.0.1/16`，过滤局域网和联网检测 |
| IPv6 DNS | `ipv6: true`（会查 AAAA，未验证） | `ipv6: false`（不返回 AAAA） |
| 国外解析 | UDP `8.8.8.8#国外默认`，`respect-rules: true`。不发 DoH | DoH `1.1.1.1` / `8.8.8.8`，`respect-rules: true` |
| 国内解析 | `direct-nameserver: system`。不用 geosite:cn。Bilibili 国际站 `+.bilibili.tv` 单独走国外默认 | `nameserver-policy` 把 `geosite:cn,private` 交给 `223.5.5.5` / `1.12.12.12` 的 DoH |
| 节点域名 | `proxy-server-nameserver` 为 `223.5.5.5` 与 `8.8.8.8` | 国内 DoH 直连查 |
| Loon / QX | 国外代理解析标了 unsupported，不能当成四端等价 | Loon `ip-mode=ipv4-only`，国内 DoH，`hijack-dns` 接管 8.8.8.8/1.1.1.1 的 53 端口；QX 同样国内 DoH，并有 dns 排除列表 |
| sing-box | 本仓库按 1.14 类型化 DNS，国外 UDP 经国外默认，不用 fake-ip | 另一版 fake-ip + 国内 DoH + 国外 DoH 经国外默认，`strategy` 为只要 IPv4 |

两边都不把系统联网检测、节点健康检查和「打开网页看出口 IP」当成同一种直连。本仓库健康检查结构在 `policy/health_check.yaml`，状态是 structure_only。另一版探测 URL 是 `https://www.gstatic.com/generate_204`（移动端用 HTTP），间隔 300 秒，lazy，连续失败 3 次。

## 逐分流

下面每条都给了判断。CSV 里是同一批行。

### OpenAI

本仓库 6 条，另一版 9 条。两边都有 6，仅本仓库 0，仅另一版 3。

两边默认都是日本。本仓库 6 条全部来自 OpenAI 帮助中心 9247338 的第一方允许表（2026-09-15）。另一版在这 6 条之外多了 3 条。两边都故意不收 Stripe、Sentry、Intercom、SendGrid、WorkOS、Cloudflare 验证页。本仓库也不收语音 IP 段。当日 v2fly `data/openai` 还有 `chatgpt.site`、`crixet.com`，两边都没写，本次没有官方表，不建议盲并。

两边都有：

- `完整域名` `cdn.openaimerge.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `chatgpt.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `oaistatic.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `oaistatsig.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `oaiusercontent.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `openai.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `chat.com` — 该收。OpenAI 持有并跳转到 ChatGPT 的第一方域名，不是通用聊天词；官方防火墙文 9247338 的最小集没写它，但应归 OpenAI 而不是国外默认。
- `域名后缀` `chatgpt.livekit.cloud` — 该收。ChatGPT 语音在 LiveKit 上的专属主机；不要连带收 host.livekit.cloud / turn.livekit.cloud（全客户共用）。
- `域名后缀` `sora.com` — 不该收。Sora 网页/App 已于 2026-04-26 停服，API 于 2026-09-24 停服；导出页是 sora.chatgpt.com，已被 chatgpt.com 后缀覆盖。

### Claude

本仓库 6 条，另一版 7 条。两边都有 5，仅本仓库 1，仅另一版 2。

两边默认日本。2026-09-29 的 CLI 网络表覆盖 api.anthropic.com、claude.ai、claude.com、platform.claude.com、downloads.claude.ai、bridge/frame.claudeusercontent.com。Desktop 页另外列出 claude.app 与 *.claudemcpcontent.com。共享的 GCS、npm、GitHub、字体和 JS CDN 两边都不收进 Claude。

两边都有：

- `域名后缀` `anthropic.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `claude.ai` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `claude.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `claudemcpcontent.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `claudeusercontent.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `claude.app` — 该收。当日 Desktop 网络要求仍列出 claude.app 与 *.claude.app；CLI 表未列，但 Desktop 流量需要。另一版缺这条。

只有另一版有：

- `域名后缀` `clau.de` — 不确定。只出现在上游 anthropic 列表，2026-09-29 的 CLI 与 Desktop 允许表都没有这条短链。
- `域名后缀` `claudemcpclient.com` — 不确定。上游 anthropic 列表有，官方 Desktop 页只写了 *.claudemcpcontent.com，没有 claudemcpclient.com。

### Cursor

本仓库 5 条，另一版 5 条。两边都有 3，仅本仓库 2，仅另一版 2。

两边默认日本。2026-09-29 官方推荐模式仍是 *.cursor.sh、*.cursor-cdn.com、*.cursorapi.com、*.cursorvm.com 和嵌套 *.*.cursorvm.com。颗粒列表含 downloads.cursor.com 与 anysphere-binaries 的那一台 S3。文档还写：9 月 30 日起登录使用 `accounts.spacex.ai`、`accounts.x.ai`（`authenticator.cursor.sh` 保留到 10 月 30 日）。这两个精确主机两边都没有，建议补上，不要收成 spacex.ai / x.ai 整段（x.ai 已在其他 AI）。

两边都有：

- `域名后缀` `cursor-cdn.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `cursor.sh` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `cursorapi.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `完整域名` `downloads.cursor.com` — 该收。官方颗粒列表写明该主机用于客户端更新；推荐模式没有 *.cursor.com，不应改成整段后缀。另一版用 cursor.com 后缀盖住了它。
- `域名后缀` `cursorvm.com` — 不该收。同一条后缀该留，但不应放在 Cursor 组。官方写明 *.cursorvm.com 与 *.*.cursorvm.com 是 Grok Bot 托管计算机，应归远程控制，避免和编辑器开关绑在一起。

只有另一版有：

- `完整域名` `anysphere-binaries.s3.us-east-1.amazonaws.com` — 该收。官方颗粒列表写明该存储桶用于更新和扩展下载。只收这一台精确主机，不要收 amazonaws.com。本仓库把它排除后，会落到共享基础设施的 amazonaws.com，出口仍是国外默认，但不会跟着 Cursor 组切换。
- `域名后缀` `cursor.com` — 不该收。官方推荐模式是 *.cursor.sh、*.cursor-cdn.com、*.cursorapi.com、*.cursorvm.com，颗粒列表只有 downloads.cursor.com，没有 *.cursor.com。整段后缀会吞掉未列出的子域。

### Google AI

本仓库 7 条，另一版 43 条。两边都有 5，仅本仓库 2，仅另一版 38。

两边默认日本。本仓库 7 条是文档化端点，googleapis 只用精确主机。另一版 43 条，多从上游 google-deepmind 展开。5 条完全一致；gemini.google.com 与 aistudio.google.com 本仓库是后缀、另一版是精确主机。

两边都有：

- `完整域名` `cloudaicompanion.googleapis.com` — 一致。两边同类型、同值、同一分流。
- `完整域名` `cloudcode-pa.googleapis.com` — 一致。两边同类型、同值、同一分流。
- `完整域名` `generativelanguage.googleapis.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `antigravity.google` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `notebook.google.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `aistudio.google.com` — 该收。本仓库按 Workspace / Gemini API / Code Assist / Antigravity 文档收的最小集，后缀或精确主机都没有放宽到 googleapis.com。另一版缺 gemini.google.com 与 aistudio.google.com 的后缀（只写了精确主机）。
- `域名后缀` `gemini.google.com` — 该收。本仓库按 Workspace / Gemini API / Code Assist / Antigravity 文档收的最小集，后缀或精确主机都没有放宽到 googleapis.com。另一版缺 gemini.google.com 与 aistudio.google.com 的后缀（只写了精确主机）。

只有另一版有：

- `完整域名` `aistudio.google.com` — 不该收。本仓库已有同名域名后缀，精确主机是其子集合，再写一条不增加命中。
- `完整域名` `alkalicore-pa.clients6.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `alkalimakersuite-pa.clients6.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `antigravity-pa.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `antigravity.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `bard.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `daily-cloudcode-pa.googleapis.com` — 不该收。另一版自己注明 2026-09-23 复核时不在 Gemini Code Assist 官方清单内。
- `完整域名` `gemini.google.com` — 不该收。本仓库已有同名域名后缀，精确主机是其子集合，再写一条不增加命中。
- `完整域名` `makersuite.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `notebooklm-pa.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `notebooklm.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `notebooklm.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `完整域名` `webchannel-alkalimakersuite-pa.clients6.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `ai.google.dev` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `ai.studio` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `aicode.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `aida.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `aisandbox-pa.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `antigravity-unleash.goog` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `deepmind.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `deepmind.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `flow.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `flow.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `geller-pa.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `gemini.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `gemini.gstatic.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `generativeai.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `jules.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `jules.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `labs.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `labs.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `notebook.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `notebooklm.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `opal.google` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `opal.google.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `proactivebackend-pa.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `robinfrontend-pa.googleapis.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。
- `域名后缀` `stitch.withgoogle.com` — 不确定。上游把这些主机归在 Generative Language / AI Studio / Labs / DeepMind 段，本次没有在 Gemini API、Workspace 或 Code Assist 官方允许表里逐条复核到。不建议整段并入，也不建议当成已证伪删掉。

### Copilot

本仓库 9 条，另一版 11 条。两边都有 7，仅本仓库 2，仅另一版 4。

两边默认日本，GitHub Copilot 与 Microsoft Copilot 同一个组。GitHub 允许表（2026-09-29）仍包含 *.githubcopilot.com、copilot-proxy、origin-tracker、copilot-telemetry、copilot-reports.github.com。collector.github.com 与 default.exp-tas.com 在允许表里，但本仓库把前者交给 github.com 后缀，后者不收（实验平台，VS Code 共用）。不要收整段 github.com 或 bing.com 进 Copilot。

两边都有：

- `完整域名` `copilot-proxy.githubusercontent.com` — 一致。两边同类型、同值、同一分流。
- `完整域名` `copilot-reports.github.com` — 一致。两边同类型、同值、同一分流。
- `完整域名` `copilot-telemetry.githubusercontent.com` — 一致。两边同类型、同值、同一分流。
- `完整域名` `origin-tracker.githubusercontent.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `copilot.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `copilot.microsoft.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `githubcopilot.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `完整域名` `copilot.cloud.microsoft` — 该收。Microsoft Learn 把 copilot.cloud.microsoft 写成入口主机。精确域名不会吞掉整个 cloud.microsoft（那条在 Microsoft 组）。另一版写成后缀，能多盖子域。
- `域名后缀` `copilot.ai` — 不确定。本仓库 2026-09-15 审计把它记为个人档入口；本次检索的 M365 网络要求主文强调的是 copilot.cloud.microsoft，没有再次看到 copilot.ai。

只有另一版有：

- `完整域名` `copilot-workspace.githubnext.com` — 不确定。只在上游 github-copilot 列表，不在 2026-09-29 抓到的 GitHub Copilot allowlist 正文里。存储桶位于共享云，即使以后收也只能精确主机。
- `完整域名` `copilotprodattachments.blob.core.windows.net` — 不确定。只在上游 github-copilot 列表，不在 2026-09-29 抓到的 GitHub Copilot allowlist 正文里。存储桶位于共享云，即使以后收也只能精确主机。
- `完整域名` `sydney.bing.com` — 不确定。历史对话后端，另一版标明是维护者知识，上游只把 bing.com 整体归 Bing。不要为了它收整段 bing.com。
- `域名后缀` `copilot.cloud.microsoft` — 该收。比精确主机更盖子域，又比 *.cloud.microsoft 窄，能把 Copilot 从 Microsoft 组拆开。官方点名的是这台主机及其所属通配，不是 bing.com。

### 其他 AI

本仓库 4 条，另一版 23 条。两边都有 4，仅本仓库 0，仅另一版 19。

两边默认日本，已含 grok.com、x.ai、perplexity.ai、poe.com。国内模型不在这组。x.com 上的 Grok 无法按域名拆开，两边都把它留在 X。另一版多了十几个其他厂商。

两边都有：

- `域名后缀` `grok.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `perplexity.ai` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `poe.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `x.ai` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `ppl-ai-file-upload.s3.amazonaws.com` — 不该收。共享 S3 / Cloudinary 上的桶。精确主机仍是别人的云，本仓库约定这种依赖不进产品组，交给国外默认。
- `完整域名` `pplx-res.cloudinary.com` — 不该收。共享 S3 / Cloudinary 上的桶。精确主机仍是别人的云，本仓库约定这种依赖不进产品组，交给国外默认。
- `域名后缀` `character.ai` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `elevenlabs.com` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `elevenlabs.io` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `grokipedia.com` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `groq.com` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `hf.co` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `hf.space` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `huggingface.co` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `meta.ai` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `midjourney.com` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `mistral.ai` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `openrouter.ai` — 该收。境外 AI 产品自己的品牌域名，应进其他 AI（默认日本），不要进国内直连，也不要和已独立的 OpenAI/Claude/Cursor 混。
- `域名后缀` `perplexity.com` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `poecdn.net` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `pplx.ai` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `suno.ai` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。
- `域名后缀` `suno.com` — 不确定。上游或维护者有记录，但没有本次打开的官方防火墙表。pplx.ai 被本仓库审计明确排除过；character.ai / Suno 另一版标的是维护者知识。

### Apple AI

本仓库 18 条，另一版 0 条。两边都有 0，仅本仓库 18，仅另一版 0。

本仓库 18 条，默认美国，类型直方图 5 个完整域名、12 个后缀、1 个关键词 siri。另一版 0 条，且没有这个组。这是两边最大的结构差：Apple Intelligence / 私有中继的主机在另一版里多数直连。

两边都有：

- （无）

只有本仓库有：

- `完整域名` `guzzoni.apple.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `完整域名` `mask-api.fe.apple-dns.net` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `完整域名` `mask-api.icloud.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `完整域名` `mask-t.apple-dns.net` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `完整域名` `mask.apple-dns.net` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `关键词` `siri` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 关键词 siri 很宽，但基线冻结，不得改窄。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `apple-relay.apple.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `apple-relay.cloudflare.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有任何规则能盖住这几条中继主机。
- `域名后缀` `apple-relay.fastly-edge.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有任何规则能盖住这几条中继主机。
- `域名后缀` `apple-relay.mask.apple-dns.net` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `apps.mzstatic.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版 mzstatic.com 整段归默认 DIRECT 的 Apple 组，会把这条吞成直连。
- `域名后缀` `cp4.cloudflare.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有任何规则能盖住这几条中继主机。
- `域名后缀` `gateway.icloud.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `gspe1-ssl.ls.apple.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `ls.apple.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `mask-h2.icloud.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `mask.icloud.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。
- `域名后缀` `smoot.apple.com` — 该收。冻结的 18 条必须原样保留，匹配类型不能改。 另一版没有 Apple AI 组，多数主机会被 apple.com / icloud.com / apple-dns.net 的 Apple 组（默认 DIRECT）吞掉。

只有另一版有：

- （无）

### YouTube

本仓库 12 条，另一版 13 条。两边都有 2，仅本仓库 10，仅另一版 11。

本仓库 12 条全是完整域名，来自 Workspace 的 YouTube 限制主机表，所以只命中写出来的那几台，不命中任意子域。另一版用后缀。两边都有的只有两个 googleapis 精确主机。

两边都有：

- `完整域名` `youtube.googleapis.com` — 一致。两边同类型、同值、同一分流。
- `完整域名` `youtubei.googleapis.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `完整域名` `m.youtube.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `restrict.youtube.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `restrictmoderate.youtube.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `s.ytimg.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `www.youtube-nocookie.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `www.youtube.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `www.youtubeeducation.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `youtu.be` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `youtube.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。
- `完整域名` `youtubeeducation.com` — 该收。本仓库按官方 YouTube 限制主机收的精确域名，没有放宽成后缀，所以 music.youtube.com 这类子域目前盖不住。另一版的 youtube.com 后缀能盖住其中多条，但精确条在后缀落地前应保留。

只有另一版有：

- `完整域名` `s.youtube.com` — 该收。播放统计主机。放在广告拦截之前，避免远程广告集合把它 REJECT 掉后观看记录异常。本仓库目前没有这条，也没有 category-ads-all。
- `完整域名` `yt3.ggpht.com` — 该收。频道头像/横幅的精确主机。整段 ggpht.com / googleusercontent.com 仍应留在共享基础设施，不要为了头像把根域改挂到 YouTube。
- `完整域名` `yt3.googleusercontent.com` — 该收。频道头像/横幅的精确主机。整段 ggpht.com / googleusercontent.com 仍应留在共享基础设施，不要为了头像把根域改挂到 YouTube。
- `域名后缀` `googlevideo.com` — 该收。YouTube 第一方站点、短链、嵌入、图片和视频流域名。本仓库只有少量精确主机，子域会漏到国外默认。googlevideo.com 不要拿去归 Google 通用组。
- `域名后缀` `youtu.be` — 该收。YouTube 第一方站点、短链、嵌入、图片和视频流域名。本仓库只有少量精确主机，子域会漏到国外默认。googlevideo.com 不要拿去归 Google 通用组。
- `域名后缀` `youtube-nocookie.com` — 该收。YouTube 第一方站点、短链、嵌入、图片和视频流域名。本仓库只有少量精确主机，子域会漏到国外默认。googlevideo.com 不要拿去归 Google 通用组。
- `域名后缀` `youtube.com` — 该收。YouTube 第一方站点、短链、嵌入、图片和视频流域名。本仓库只有少量精确主机，子域会漏到国外默认。googlevideo.com 不要拿去归 Google 通用组。
- `域名后缀` `youtubeembeddedplayer.googleapis.com` — 该收。嵌入播放器接口在 googleapis.com 下面，必须写得比共享根更具体，并排在共享基础设施之前。
- `域名后缀` `youtubekids.com` — 该收。YouTube 第一方站点、短链、嵌入、图片和视频流域名。本仓库只有少量精确主机，子域会漏到国外默认。googlevideo.com 不要拿去归 Google 通用组。
- `域名后缀` `yt.be` — 不确定。上游有这条短域，本次没有在 Google 官方 YouTube 主机表里看到。
- `域名后缀` `ytimg.com` — 该收。YouTube 第一方站点、短链、嵌入、图片和视频流域名。本仓库只有少量精确主机，子域会漏到国外默认。googlevideo.com 不要拿去归 Google 通用组。

### Netflix

本仓库 7 条，另一版 20 条。两边都有 7，仅本仓库 0，仅另一版 13。

默认都是解锁入口，解锁都未验证。Open Connect 投递域 7 条两边一致。另一版多了测速站、netflix.net 和 11 个 DNS 探测域。两边都没收 Netflix IP 段。

两边都有：

- `域名后缀` `netflix.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `nflxext.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `nflximg.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `nflximg.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `nflxsearch.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `nflxso.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `nflxvideo.net` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `fast.com` — 该收。Netflix 的测速站，和正片域名分开。放进 Netflix 组会跟着解锁入口走，这是合理的。
- `域名后缀` `netflix.net` — 不确定。不在 2026-09-16 抓到的 Open Connect mobiledeliverydomains.txt 里，本仓库因此不收；上游列表有。
- `域名后缀` `netflixdnstest0.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest1.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest10.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest2.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest3.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest4.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest5.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest6.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest7.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest8.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。
- `域名后缀` `netflixdnstest9.com` — 不确定。上游列出 0–10 共 11 个客户端 DNS 探测域，不是 Open Connect 投递域。是否必须跟解锁入口走，没有官方文件证明。

### Disney+

本仓库 0 条，另一版 6 条。两边都有 0，仅本仓库 0，仅另一版 6。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `bamgrid.com` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `disney-plus.net` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `disneyplus.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `disneystreaming.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `dssott.com` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `registerdisney.go.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。 这条比 amazon.com / bamgrid.com / go.com 更具体，必须排在更宽的规则前面。

### Max

本仓库 0 条，另一版 5 条。两边都有 0，仅本仓库 0，仅另一版 5。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `hbo.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `hbogo.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `hbomax.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `hbomaxcdn.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `max.com` — 不确定。服务曾用 max.com，但这个后缀极宽，且 2025 年后品牌回到 HBO Max。本次没有打开官方主机表确认它仍独占。

### Prime Video

本仓库 0 条，另一版 18 条。两边都有 0，仅本仓库 0，仅另一版 18。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `atv-ps.amazon.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。 这条比 amazon.com / bamgrid.com / go.com 更具体，必须排在更宽的规则前面。
- `完整域名` `avodmp4s3ww-a.akamaihd.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `d1v5ir2lpwr8os.cloudfront.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `d22qjgkvxw22r6.cloudfront.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `d25xi40x97liuc.cloudfront.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `d27xxe7juh1us6.cloudfront.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `dmqdd6hw24ucf.cloudfront.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `msh.amazon.co.uk` — 不确定。上游或 blackmatrix7 快照里有，看起来像 Prime 播放或设备服务，但本次没有 Amazon 官方主机表。a2z.com 是亚马逊基础设施域，收成后缀要谨慎。
- `域名后缀` `aiv-cdn.net` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `aiv-delivery.net` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `amazonvideo.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `atv-ps-eu.amazon.co.uk` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。 这条比 amazon.com / bamgrid.com / go.com 更具体，必须排在更宽的规则前面。
- `域名后缀` `atv-ps-eu.amazon.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。 这条比 amazon.com / bamgrid.com / go.com 更具体，必须排在更宽的规则前面。
- `域名后缀` `atv-ps-fe.amazon.co.jp` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。 这条比 amazon.com / bamgrid.com / go.com 更具体，必须排在更宽的规则前面。
- `域名后缀` `atv-ps-fe.amazon.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。 这条比 amazon.com / bamgrid.com / go.com 更具体，必须排在更宽的规则前面。
- `域名后缀` `primevideo.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `prod.service.minerva.devices.a2z.com` — 不确定。上游或 blackmatrix7 快照里有，看起来像 Prime 播放或设备服务，但本次没有 Amazon 官方主机表。a2z.com 是亚马逊基础设施域，收成后缀要谨慎。
- `域名后缀` `pv-cdn.net` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。

### Hulu US

本仓库 0 条，另一版 4 条。两边都有 0，仅本仓库 0，仅另一版 4。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `hulu.playback.edge.bamgrid.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。 这条比 amazon.com / bamgrid.com / go.com 更具体，必须排在更宽的规则前面。
- `域名后缀` `hulu.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `huluim.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `hulustream.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。

### Hulu Japan

本仓库 0 条，另一版 5 条。两边都有 0，仅本仓库 0，仅另一版 5。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `happyon.jp` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `hjholdings.jp` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `hulu.jp` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `prod.hjholdings.tv` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `streaks.jp` — 不确定。另一版写明 STREAKS 可能被其他日本服务共用，只是因为同走日本出口才归进 Hulu Japan。

### Abema

本仓库 0 条，另一版 9 条。两边都有 0，仅本仓库 0，仅另一版 9。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `abematv.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `ds-linear-abematv.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `ds-vod-abematv.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `linear-abematv.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `vod-abematv.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `abema-tv.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `abema.io` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `abema.tv` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `hayabusa.io` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。

### DMM

本仓库 0 条，另一版 4 条。两边都有 0，仅本仓库 0，仅另一版 4。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `dmm-extension.com` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `dmm.co.jp` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `dmm.com` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `dmmapis.com` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。

### 日本影音

本仓库 0 条，另一版 20 条。两边都有 0，仅本仓库 0，仅另一版 20。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `dmc.nico` — 不确定。niconico 家族域名，上游有，本次没有逐条打开官网。
- `域名后缀` `fod.fujitv.co.jp` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。
- `域名后缀` `lemino.docomo.ne.jp` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。
- `域名后缀` `nico.ms` — 该收。日区影音产品自己的站点或短链，应进日本影音（默认日本），本仓库这组没有域名。
- `域名后缀` `nicochannel.jp` — 不确定。niconico 家族域名，上游有，本次没有逐条打开官网。
- `域名后缀` `nicodic.jp` — 不确定。niconico 家族域名，上游有，本次没有逐条打开官网。
- `域名后缀` `nicomanga.jp` — 不确定。niconico 家族域名，上游有，本次没有逐条打开官网。
- `域名后缀` `niconico.com` — 该收。日区影音产品自己的站点或短链，应进日本影音（默认日本），本仓库这组没有域名。
- `域名后缀` `nicoseiga.jp` — 不确定。niconico 家族域名，上游有，本次没有逐条打开官网。
- `域名后缀` `nicovideo.jp` — 该收。日区影音产品自己的站点或短链，应进日本影音（默认日本），本仓库这组没有域名。
- `域名后缀` `nimg.jp` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。
- `域名后缀` `nxtv.jp` — 该收。日区影音产品自己的站点或短链，应进日本影音（默认日本），本仓库这组没有域名。
- `域名后缀` `radiko-cf.com` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。
- `域名后缀` `radiko.jp` — 该收。日区影音产品自己的站点或短链，应进日本影音（默认日本），本仓库这组没有域名。
- `域名后缀` `simg.jp` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。
- `域名后缀` `smartstream.ne.jp` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。
- `域名后缀` `telasa.jp` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。
- `域名后缀` `tver.jp` — 该收。日区影音产品自己的站点或短链，应进日本影音（默认日本），本仓库这组没有域名。
- `域名后缀` `unext.jp` — 该收。日区影音产品自己的站点或短链，应进日本影音（默认日本），本仓库这组没有域名。
- `域名后缀` `wowow.co.jp` — 不确定。维护者知识，或图片/播放子域没有在本次打开的官方页上核对。

### Spotify

本仓库 2 条，另一版 10 条。两边都有 2，仅本仓库 0，仅另一版 8。

两边都有：

- `域名后缀` `spoti.fi` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `spotify.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `audio-ak-spotify-com.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `audio4-ak-spotify-com.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `heads-ak-spotify-com.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `heads4-ak-spotify-com.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `pscdn.co` — 不确定。社区把它们当 Spotify CDN，本仓库审计明确不收整段，怕不是 Spotify 独占。
- `域名后缀` `scdn.co` — 不确定。社区把它们当 Spotify CDN，本仓库审计明确不收整段，怕不是 Spotify 独占。
- `域名后缀` `spotifycdn.com` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `spotifycdn.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。

### TikTok

本仓库 3 条，另一版 38 条。两边都有 3，仅本仓库 0，仅另一版 35。

两边都有：

- `域名后缀` `tiktok.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `tiktokcdn.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `tiktokv.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `lf16-effectcdn.byteeffecttos-g.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `完整域名` `p16-tiktokcdn-com.akamaized.net` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `bytedapm.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `bytegecko-i18n.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `byteglb.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `byteintlapi.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `byteoversea.com` — 不该收。字节海外共用根，不是 TikTok 独占。本仓库审计明确不收，收了会把其他字节海外产品卷进 TikTok 组。
- `域名后缀` `byteoversea.net` — 不该收。字节海外共用根，不是 TikTok 独占。本仓库审计明确不收，收了会把其他字节海外产品卷进 TikTok 组。
- `域名后缀` `ibytedtos.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `ibyteimg.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `ipstatp.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `isnssdk.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `muscdn.com` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `musical.ly` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `sgpstatp.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `tik-tokapi.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `tiktok-minis.com` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktok-row.net` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokcdn-eu.com` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokcdn-us.com` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokd.net` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokd.org` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokeu-cdn.com` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokglobalshopv.com` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokminis.us` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokrow-cdn.com` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokv.eu` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokv.us` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokw.eu` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `tiktokw.us` — 该收。国际版 TikTok 或已并入 TikTok 的 musical.ly 域名。不要收 douyin.com（本仓库国内直连已有）。
- `域名后缀` `ttcdn-us.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `ttlivecdn.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `ttoverseaus.net` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `ttwebview.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。
- `域名后缀` `ttwstatic.com` — 不确定。字节海外监控、统计或 CDN 根，上游有，但是否只服务 TikTok 没有官方表。

### Twitch

本仓库 3 条，另一版 6 条。两边都有 3，仅本仓库 0，仅另一版 3。

两边都有：

- `域名后缀` `jtvnw.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `twitch.tv` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `twitchcdn.net` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `ext-twitch.tv` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `ttvnw.net` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。
- `域名后缀` `twitchsvc.net` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。

### Bilibili 港澳台

本仓库 0 条，另一版 4 条。两边都有 0，仅本仓库 0，仅另一版 4。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `api.bilibili.com` — 不该收。和大陆客户端共用主机。排在 bilibili.com 国内直连前面会把大陆 API 送去台湾。另一版自己也写了「与大陆使用共用主机」。
- `完整域名` `app.bilibili.com` — 不该收。和大陆客户端共用主机。排在 bilibili.com 国内直连前面会把大陆 API 送去台湾。另一版自己也写了「与大陆使用共用主机」。
- `完整域名` `bangumi.bilibili.com` — 不该收。和大陆客户端共用主机。排在 bilibili.com 国内直连前面会把大陆 API 送去台湾。另一版自己也写了「与大陆使用共用主机」。
- `完整域名` `upos-hz-mirrorakam.akamaized.net` — 不确定。上游标 @!cn 的 Akamai 镜像，是否只服务港澳台没有官方文件。

### Bahamut

本仓库 1 条，另一版 5 条。两边都有 1，仅本仓库 0，仅另一版 4。

两边都有：

- `域名后缀` `gamer.com.tw` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `bahamut.akamaized.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `gamer-cds.cdn.hinet.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `完整域名` `gamer2-cds.cdn.hinet.net` — 不确定。共享 CDN 上的叶子或上游有、官方主机表本次没核对的播放域名。可以以后按精确主机收，不要收 cloudfront.net / akamaihd.net 整段。
- `域名后缀` `bahamut.com.tw` — 该收。产品自己的站点或播放域，本仓库对应包是空的（没有官方主机快照就不发明域名）。

### 其他流媒体

本仓库 0 条，另一版 53 条。两边都有 0，仅本仓库 0，仅另一版 53。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `api.viu.now.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `完整域名` `d1k2us671qcoau.cloudfront.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `d2anahhhmp1ffz.cloudfront.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `dfp6rglgjqszk.cloudfront.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdfreemobile-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdfreepc-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdfreetv-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdfreevcpc-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdofifreemobile-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdofifreepc-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdofifreetv-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `ntdofifreevcpc-tgc.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `完整域名` `theater-kktv.cdn.hinet.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `域名后缀` `bilibili.tv` — 该收。哔哩哔哩国际站，不是大陆 bilibili.com。本仓库 DNS 已把 bilibili.tv 当作港澳台解析覆盖，但流量包仍是空的。应归 Bilibili 港澳台，不要丢在其他流媒体。
- `域名后缀` `biliintl.com` — 该收。哔哩哔哩国际站，不是大陆 bilibili.com。本仓库 DNS 已把 bilibili.tv 当作港澳台解析覆盖，但流量包仍是空的。应归 Bilibili 港澳台，不要丢在其他流媒体。
- `域名后缀` `bstarstatic.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `catchplay.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `crunchyroll.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `dazn-api.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `dazn.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `dazndn.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `daznfeeds.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `daznplayer.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `daznservices.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `deezer.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `dzcdn.net` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `iq.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `kktv.com.tw` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `kktv.me` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `litv.tv` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `litvfreepc.akamaized.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `域名后缀` `mytvsuper.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `ofiii.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `p-cdn.us` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `pandora.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `paramountplus.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `peacocktv.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `pluto.tv` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `plutotv.net` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `sndcdn.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `soundcloud.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `tidal.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `tra-ww000-cp.akamaized.net` — 不确定。共享 CDN 上的叶子，上游有，本次没有官方主机表。
- `域名后缀` `tubi.io` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `tubi.tv` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `tubi.video` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `tubitv.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `viki.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `vimeo.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `vimeocdn.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `viu.com` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `viu.tv` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。
- `域名后缀` `wetv.vip` — 该收。独立流媒体自己的品牌域名。本仓库「其他流媒体」组存在但没有规则，这些会掉进国外默认，开关不起作用。

### Telegram

本仓库 16 条，另一版 23 条。两边都有 16，仅本仓库 0，仅另一版 7。

两边都有：

- `域名后缀` `t.me` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `telegram.org` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `149.154.160.0/20` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `185.76.151.0/24` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `91.105.192.0/23` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `91.108.12.0/22` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `91.108.16.0/22` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `91.108.20.0/22` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `91.108.4.0/22` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `91.108.56.0/22` — 一致。两边同类型、同值、同一分流。
- `IPv4 段` `91.108.8.0/22` — 一致。两边同类型、同值、同一分流。
- `IPv6 段` `2001:67c:4e8::/48` — 一致。两边同类型、同值、同一分流。
- `IPv6 段` `2001:b28:f23c::/48` — 一致。两边同类型、同值、同一分流。
- `IPv6 段` `2001:b28:f23d::/48` — 一致。两边同类型、同值、同一分流。
- `IPv6 段` `2001:b28:f23f::/48` — 一致。两边同类型、同值、同一分流。
- `IPv6 段` `2a0a:f280::/32` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `cdn-telegram.org` — 不确定。上游有。 本次没有在 core.telegram.org 的现行说明里逐条核对。
- `域名后缀` `fragment.com` — 不确定。更接近 TON/Fragment，不一定是聊天流量。 本次没有在 core.telegram.org 的现行说明里逐条核对。
- `域名后缀` `tdesktop.com` — 该收。Telegram 图床与桌面端站点，第一方，本仓库最小集只有 telegram.org 和 t.me。
- `域名后缀` `telegra.ph` — 该收。Telegram 图床与桌面端站点，第一方，本仓库最小集只有 telegram.org 和 t.me。
- `域名后缀` `telegram-cdn.org` — 不确定。上游有。 本次没有在 core.telegram.org 的现行说明里逐条核对。
- `域名后缀` `telegram.me` — 不确定。本仓库 2026-09-16 对照 FAQ 时正文没有 telegram.me。 本次没有在 core.telegram.org 的现行说明里逐条核对。
- `域名后缀` `telesco.pe` — 不确定。上游有。 本次没有在 core.telegram.org 的现行说明里逐条核对。

### X

本仓库 4 条，另一版 8 条。两边都有 4，仅本仓库 0，仅另一版 4。

两边都有：

- `域名后缀` `t.co` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `twimg.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `twitter.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `x.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `periscope.tv` — 不该收。本仓库审计把 Periscope / pscp 标为已停产品，不再收。
- `域名后缀` `pscp.tv` — 不该收。本仓库审计把 Periscope / pscp 标为已停产品，不再收。
- `域名后缀` `tweetdeck.com` — 不确定。旧 TweetDeck / Twitter 短域，上游有，本次没有官方主机表证明仍在用。
- `域名后缀` `twttr.com` — 不确定。旧 TweetDeck / Twitter 短域，上游有，本次没有官方主机表证明仍在用。

### Meta 社交

本仓库 9 条，另一版 16 条。两边都有 8，仅本仓库 1，仅另一版 8。

两边都有：

- `域名后缀` `cdninstagram.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `facebook.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `fb.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `fb.me` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `instagram.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `messenger.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `threads.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `threads.net` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `instagr.am` — 该收。Instagram 短链，另一版没有。

只有另一版有：

- `域名后缀` `facebook.net` — 该收。Meta 社交的 SDK、图片 CDN 或短链。fbcdn.net 本仓库审计曾不收，功能上会掉进国外默认，但域名本身是 Meta 的。不要收成广告。
- `域名后缀` `fbcdn.net` — 该收。Meta 社交的 SDK、图片 CDN 或短链。fbcdn.net 本仓库审计曾不收，功能上会掉进国外默认，但域名本身是 Meta 的。不要收成广告。
- `域名后缀` `fbsbx.com` — 该收。Meta 社交的 SDK、图片 CDN 或短链。fbcdn.net 本仓库审计曾不收，功能上会掉进国外默认，但域名本身是 Meta 的。不要收成广告。
- `域名后缀` `ig.me` — 该收。Meta 社交的 SDK、图片 CDN 或短链。fbcdn.net 本仓库审计曾不收，功能上会掉进国外默认，但域名本身是 Meta 的。不要收成广告。
- `域名后缀` `m.me` — 该收。Meta 社交的 SDK、图片 CDN 或短链。fbcdn.net 本仓库审计曾不收，功能上会掉进国外默认，但域名本身是 Meta 的。不要收成广告。
- `域名后缀` `meta.com` — 不确定。公司站或 Quest/Oculus，不一定该跟 Facebook/Instagram 同一个开关。
- `域名后缀` `oculus.com` — 不确定。公司站或 Quest/Oculus，不一定该跟 Facebook/Instagram 同一个开关。
- `域名后缀` `oculuscdn.com` — 不确定。公司站或 Quest/Oculus，不一定该跟 Facebook/Instagram 同一个开关。

### WhatsApp

本仓库 3 条，另一版 3 条。两边都有 3，仅本仓库 0，仅另一版 0。

两边都有：

- `域名后缀` `wa.me` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `whatsapp.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `whatsapp.net` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- （无）

### LINE

本仓库 4 条，另一版 7 条。两边都有 4，仅本仓库 0，仅另一版 3。

两边都有：

- `域名后缀` `line-apps.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `line-cdn.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `line-scdn.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `line.me` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `line.naver.jp` — 该收。LINE 短链、历史域名或公司域名。本仓库只收了 line.me 和三套 CDN。
- `域名后缀` `lin.ee` — 该收。LINE 短链、历史域名或公司域名。本仓库只收了 line.me 和三套 CDN。
- `域名后缀` `linecorp.com` — 该收。LINE 短链、历史域名或公司域名。本仓库只收了 line.me 和三套 CDN。

### Discord

本仓库 4 条，另一版 9 条。两边都有 3，仅本仓库 1，仅另一版 6。

两边都有：

- `域名后缀` `discord.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `discord.gg` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `discordapp.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `media.discordapp.net` — 该收。官方 Activities CSP 写了 media.discordapp.net。另一版用更宽的 discordapp.net 后缀盖住它。

只有另一版有：

- `域名后缀` `dis.gd` — 不确定。上游 Discord 列表里的短链或状态页，本次没有在开发者文档里逐条看到。
- `域名后缀` `discord.co` — 不确定。上游 Discord 列表里的短链或状态页，本次没有在开发者文档里逐条看到。
- `域名后缀` `discord.dev` — 不确定。上游 Discord 列表里的短链或状态页，本次没有在开发者文档里逐条看到。
- `域名后缀` `discord.media` — 不确定。上游 Discord 列表里的短链或状态页，本次没有在开发者文档里逐条看到。
- `域名后缀` `discordapp.net` — 该收。比本仓库的 media.discordapp.net 更宽，能盖住媒体子域，仍然是 Discord 品牌域。
- `域名后缀` `discordstatus.com` — 不确定。上游 Discord 列表里的短链或状态页，本次没有在开发者文档里逐条看到。

### Reddit

本仓库 5 条，另一版 5 条。两边都有 4，仅本仓库 1，仅另一版 1。

两边都有：

- `域名后缀` `redd.it` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `reddit.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `redditmedia.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `redditstatic.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `redditinc.com` — 该收。Reddit 公司域名，本仓库有，另一版没有。

只有另一版有：

- `域名后缀` `redditmail.com` — 不确定。可能是邮件域名，也可能是跟踪。上游有，本次没核对。

### LinkedIn

本仓库 3 条，另一版 3 条。两边都有 3，仅本仓库 0，仅另一版 0。

两边都有：

- `域名后缀` `licdn.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `linkedin.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `lnkd.in` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- （无）

### Apple

本仓库 10 条，另一版 16 条。两边都有 4，仅本仓库 6，仅另一版 12。

两边都有：

- `域名后缀` `apple.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `cdn-apple.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `icloud-content.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `mzstatic.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `完整域名` `metrics.icloud.com` — 该收。iCloud 探测/设置类精确主机，来自企业网络主机交叉。另一版用 icloud.com 后缀盖住它们，但那条后缀默认 DIRECT，且会在没有 Apple AI 前置时吞掉智能相关主机。
- `完整域名` `pong.icloud.com` — 该收。iCloud 探测/设置类精确主机，来自企业网络主机交叉。另一版用 icloud.com 后缀盖住它们，但那条后缀默认 DIRECT，且会在没有 Apple AI 前置时吞掉智能相关主机。
- `完整域名` `probe.icloud.com` — 该收。iCloud 探测/设置类精确主机，来自企业网络主机交叉。另一版用 icloud.com 后缀盖住它们，但那条后缀默认 DIRECT，且会在没有 Apple AI 前置时吞掉智能相关主机。
- `完整域名` `setup.icloud.com` — 该收。iCloud 探测/设置类精确主机，来自企业网络主机交叉。另一版用 icloud.com 后缀盖住它们，但那条后缀默认 DIRECT，且会在没有 Apple AI 前置时吞掉智能相关主机。
- `完整域名` `statici.icloud.com` — 该收。iCloud 探测/设置类精确主机，来自企业网络主机交叉。另一版用 icloud.com 后缀盖住它们，但那条后缀默认 DIRECT，且会在没有 Apple AI 前置时吞掉智能相关主机。
- `完整域名` `ws-ee-maidsvc.icloud.com` — 该收。iCloud 探测/设置类精确主机，来自企业网络主机交叉。另一版用 icloud.com 后缀盖住它们，但那条后缀默认 DIRECT，且会在没有 Apple AI 前置时吞掉智能相关主机。

只有另一版有：

- `域名后缀` `aaplimg.com` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。
- `域名后缀` `apple-cloudkit.com` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。
- `域名后缀` `apple-dns.net` — 不该收。会匹配 mask.apple-dns.net 等 Apple AI 主机。另一版没有 Apple AI 组，这些流量会进默认 DIRECT 的 Apple 组。本仓库不应在 Apple AI 18 条之前加入这条后缀。
- `域名后缀` `apple-mapkit.com` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。
- `域名后缀` `apple.co` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。
- `域名后缀` `apple.com.cn` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。 Apple 组默认 DIRECT，中国站效果接近直连。
- `域名后缀` `apple.news` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。
- `域名后缀` `appstore.com` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。
- `域名后缀` `icloud.com` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。 必须排在 Apple AI 18 条之后。
- `域名后缀` `icloud.com.cn` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。 Apple 组默认 DIRECT，中国站效果接近直连。
- `域名后缀` `itunes.com` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。
- `域名后缀` `me.com` — 该收。Apple 第一方服务域。本仓库 Apple 包只有 apple.com、cdn-apple.com、icloud-content.com、mzstatic.com 和 6 条 iCloud 精确主机。

### Apple Music/TV

本仓库 0 条，另一版 11 条。两边都有 0，仅本仓库 0，仅另一版 11。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `aod-ssl.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `aod.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `audio-ssl.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `hls-amt.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `hls-svod.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `hls.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `np-edge.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `play-edge.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `完整域名` `uts-api.itunes.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `域名后缀` `music.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。
- `域名后缀` `tv.apple.com` — 该收。Apple Music / TV 的站点或itunes 流媒体主机，用来单独选区。两边这组默认都是 DIRECT。必须写在 apple.com 后缀之前，否则会被 Apple 通用组先吃掉。本仓库有组无规则。

### Google

本仓库 187 条，另一版 26 条。两边都有 7，仅本仓库 180，仅另一版 19。

两边都有：

- `域名后缀` `google.co.jp` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `google.co.kr` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `google.co.uk` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `google.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `google.com.hk` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `google.com.sg` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `google.com.tw` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `google.ad` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ae` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.al` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.am` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.as` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.at` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.az` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ba` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.be` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.bf` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.bg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.bi` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.bj` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.bs` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.bt` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.by` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ca` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cat` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cd` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cf` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ch` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ci` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cl` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cn` — 不确定。它在 Google 官方 supported_domains 的 187 条里，域名该不该存在没有疑问；但中国站放进默认走国外代理的 Google 组，是否合适取决于可用性，本次没有实测。
- `域名后缀` `google.co.ao` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.bw` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.ck` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.cr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.id` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.il` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.in` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.ke` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.ls` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.ma` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.mz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.nz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.th` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.tz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.ug` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.uz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.ve` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.vi` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.za` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.zm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.co.zw` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.af` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ag` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ar` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.au` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.bd` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.bh` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.bn` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.bo` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.br` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.bz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.co` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.cu` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.cy` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.do` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ec` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.eg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.et` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.fj` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.gh` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.gi` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.gt` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.jm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.kh` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.kw` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.lb` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ly` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.mm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.mt` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.mx` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.my` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.na` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ng` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ni` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.np` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.om` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.pa` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.pe` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.pg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ph` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.pk` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.pr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.py` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.qa` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.sa` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.sb` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.sl` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.sv` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.tj` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.tr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.ua` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.uy` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.vc` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.com.vn` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cv` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.cz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.de` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.dj` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.dk` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.dm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.dz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ee` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.es` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.fi` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.fm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.fr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ga` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ge` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.gg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.gl` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.gm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.gr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.gy` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.hn` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.hr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ht` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.hu` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ie` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.im` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.iq` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.is` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.it` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.je` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.jo` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.kg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ki` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.kz` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.la` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.li` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.lk` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.lt` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.lu` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.lv` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.md` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.me` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.mg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.mk` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ml` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.mn` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.mu` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.mv` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.mw` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ne` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.nl` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.no` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.nr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.nu` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.pl` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.pn` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ps` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.pt` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ro` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.rs` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ru` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.rw` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.sc` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.se` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.sh` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.si` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.sk` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.sm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.sn` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.so` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.sr` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.st` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.td` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.tg` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.tl` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.tm` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.tn` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.to` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.tt` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.vu` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。
- `域名后缀` `google.ws` — 该收。与 Google 官方 supported_domains 完全一致的搜索国家域（2026-09-29 抓取 187 条，一条不差）。另一版只显式写了 7 个常用后缀，其余靠 GEOSITE。

只有另一版有：

- `域名后缀` `android.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `blogger.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `blogspot.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `chrome.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `chromium.org` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `g.co` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `ggpht.com` — 不该收。这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。
- `域名后缀` `gmail.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `goo.gl` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `google.dev` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `googleapis.com` — 不该收。这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。
- `域名后缀` `googlemail.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `googlesource.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `googleusercontent.com` — 不该收。这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。
- `域名后缀` `gstatic.com` — 不该收。这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。
- `域名后缀` `gvt1.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `gvt2.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。
- `域名后缀` `recaptcha.net` — 不该收。另一版写明上游只有 recaptcha.net 与 www.recaptcha.net 两个精确主机，收成后缀是放宽。
- `域名后缀` `withgoogle.com` — 该收。Google 第一方产品域，不是搜索国家域。本仓库 187 条全是 google.* 国家后缀，这些会掉进 MATCH/国外默认，Google 组开关管不到。

### Microsoft

本仓库 68 条，另一版 30 条。两边都有 12，仅本仓库 56，仅另一版 18。

两边都有：

- `域名后缀` `cloud.microsoft` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `microsoft.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `microsoftonline-p.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `microsoftonline.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `msauth.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `msftauth.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `office.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `office.net` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `office365.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `outlook.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `sharepoint.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `skype.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `完整域名` `account.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `adl.windows.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `admin.onedrive.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `aka.ms` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `apis.live.net` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `auth.gfx.ms` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `autologon.microsoftazuread-sso.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `c.bing.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `c.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `clientconfig.microsoftonline-p.net` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `g.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `join.secure.skypeassets.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `login.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `mem.gfx.ms` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `office.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `officespeech.platform.bing.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `oneclient.sfx.ms` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `partnerservices.getmicrosoftkey.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `signup.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `storage.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `sway.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `www.bing.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `www.microsoft365.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `www.onedrive.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `完整域名` `www.sway.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `aadrm.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `acompli.net` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `activity.windows.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `appex-rf.msn.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `appex.bing.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `assets-yammer.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `hip.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `lync.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `microsoftusercontent.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `msauthimages.net` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `msftauthimages.net` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `msftidentity.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `msidentity.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `msocdn.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `mx.microsoft` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `o365weve.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `officeapps.live.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `onenote.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `onmicrosoft.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `outlookmobile.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `phonefactor.net` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `portal.cloudappsecurity.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `powerapps.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `powerautomate.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `sharepointonline.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `static.microsoft` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `svc.ms` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `usercontent.microsoft` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `wns.windows.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `yammer.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。
- `域名后缀` `yammerusercontent.com` — 该收。M365 worldwide endpoints 与社区列表交叉后的 HIGH 集。精确主机没有放宽成 live.com / bing.com。另一版缺这些时，一部分会被它的更宽后缀盖住，一部分会漏。

只有另一版有：

- `域名后缀` `1drv.com` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `1drv.ms` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `aka.ms` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `azure.com` — 不该收。azure.com 本仓库在共享基础设施；bing.com 整段会吞掉搜索，Copilot 只能靠更具体的 sydney.bing.com 抢先。官方 Copilot 文档要求的是 M365 与 copilot.cloud.microsoft，不是整段 Bing。
- `域名后缀` `bing.com` — 不该收。azure.com 本仓库在共享基础设施；bing.com 整段会吞掉搜索，Copilot 只能靠更具体的 sydney.bing.com 抢先。官方 Copilot 文档要求的是 M365 与 copilot.cloud.microsoft，不是整段 Bing。
- `域名后缀` `bing.net` — 不该收。azure.com 本仓库在共享基础设施；bing.com 整段会吞掉搜索，Copilot 只能靠更具体的 sydney.bing.com 抢先。官方 Copilot 文档要求的是 M365 与 copilot.cloud.microsoft，不是整段 Bing。
- `域名后缀` `gfx.ms` — 不该收。过宽。本仓库已有 login.live.com、oneclient.sfx.ms 等 endpoints 精确主机，整段 live.com / *.ms 短域会卷进未审计子域。
- `域名后缀` `live.com` — 不该收。过宽。本仓库已有 login.live.com、oneclient.sfx.ms 等 endpoints 精确主机，整段 live.com / *.ms 短域会卷进未审计子域。
- `域名后缀` `live.net` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `microsoft365.com` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `msn.com` — 不确定。微软消费/门户域名，上游有。本仓库 Microsoft 组以 M365 端点为主，要不要把 Xbox 和 MSN 放进同一个开关，没有产品决定。
- `域名后缀` `onedrive.com` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `sfx.ms` — 不该收。过宽。本仓库已有 login.live.com、oneclient.sfx.ms 等 endpoints 精确主机，整段 live.com / *.ms 短域会卷进未审计子域。
- `域名后缀` `visualstudio.com` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `vsassets.io` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `windows.com` — 该收。微软第一方产品域（OneDrive、短链、Visual Studio、Windows）。本仓库有的只是其中部分精确主机。aka.ms 本仓库是精确域名，后缀更能盖住子域。
- `域名后缀` `xbox.com` — 不确定。微软消费/门户域名，上游有。本仓库 Microsoft 组以 M365 端点为主，要不要把 Xbox 和 MSN 放进同一个开关，没有产品决定。
- `域名后缀` `xboxlive.com` — 不确定。微软消费/门户域名，上游有。本仓库 Microsoft 组以 M365 端点为主，要不要把 Xbox 和 MSN 放进同一个开关，没有产品决定。

### GitHub

本仓库 6 条，另一版 9 条。两边都有 5，仅本仓库 1，仅另一版 4。

两边都有：

- `域名后缀` `ghcr.io` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `github.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `github.dev` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `githubassets.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `githubusercontent.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `github.io` — 该收。GitHub /meta 的 domains.website 包含 *.github.io。另一版没写，GitHub Pages 会掉进国外默认。

只有另一版有：

- `域名后缀` `collector.github.com` — 不该收。GitHub 官方 Copilot 允许表有这台遥测主机，但本仓库 github.com 后缀已经把它归到 GitHub。单独再写一条只有在引入会拦截它的广告集合时才需要，作为误杀例外而不是新分流。
- `域名后缀` `github.blog` — 该收。GitHub 第一方博客、OAuth 应用域和状态页，2026-09-29 的 v2fly github 列表里有。
- `域名后缀` `githubapp.com` — 该收。GitHub 第一方博客、OAuth 应用域和状态页，2026-09-29 的 v2fly github 列表里有。
- `域名后缀` `githubstatus.com` — 该收。GitHub 第一方博客、OAuth 应用域和状态页，2026-09-29 的 v2fly github 列表里有。

### PayPal

本仓库 2 条，另一版 3 条。两边都有 2，仅本仓库 0，仅另一版 1。

默认都是美国固定，都不跟随国外默认。paypal.com 与 paypalobjects.com 一致。JS SDK 的 CSP 还提到 venmo.com，两边都没把 Venmo 收进 PayPal。

两边都有：

- `域名后缀` `paypal.com` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `paypalobjects.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `paypal.me` — 该收。PayPal.me 收款短链，第一方域名。不要连带收 v2fly paypal 列表里的 paypa1.com 这类钓鱼相似域名，另一版也没有收那些。

### 广告拦截

本仓库 41 条，另一版 32 条。两边都有 0，仅本仓库 41，仅另一版 32。

两边都有：

- （无）

只有本仓库有：

- `域名后缀` `adcolony.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `adform.net` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `adnxs.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `adotmob.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `adsafeprotected.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `adsrvr.org` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `adtechus.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `advertising.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `alimama.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `amazon-adsystem.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `casalemedia.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `chartboost.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `criteo.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `doubleclick.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `doubleclick.net` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `doubleverify.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `everesttech.net` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `flashtalking.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `googleadservices.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `googlesyndication.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `googletagservices.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `inmobi.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `inner-active.mobi` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `ironsrc.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `media.net` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `moatads.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `openx.net` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `outbrain.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `pubmatic.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `quantserve.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `rubiconproject.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `scorecardresearch.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `smaato.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `smartadserver.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `taboola.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `tanx.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `tapjoy.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `teads.tv` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `umeng.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `umengcloud.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。
- `域名后缀` `vungle.com` — 该收。独立广告网络后缀，写在所有产品规则之前。另一版不写这些显式条，改走远程 category-ads-all / AdvertisingLite，两边集合不重合，不代表这些域名不该拦截。

只有另一版有：

- `完整域名` `adeventtracker.spotify.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `完整域名` `adstudio-assets.scdn.co` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `完整域名` `an.facebook.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `完整域名` `analytics.google.com` — 不确定。上游标了广告/统计，但 graph.* 也可能是客户端接口，analytics.google.com 会挡住 GA 后台。另一版自己也写了会连带误伤。
- `完整域名` `bat.bing.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `完整域名` `bloodhound.spotify.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `完整域名` `copilot-telemetry-service.githubusercontent.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `完整域名` `px.ads.linkedin.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `ad.games.dmm.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `ads.youtube.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `adservice.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `advertising.apple.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `analytics-alv.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `analytics.facebook.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `analytics.tiktok.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `api-adservices.apple.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `browser.events.data.msn.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `fcmatch.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `googleadapis.l.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `graph-fallback.instagram.com` — 不确定。上游标了广告/统计，但 graph.* 也可能是客户端接口，analytics.google.com 会挡住 GA 后台。另一版自己也写了会连带误伤。
- `域名后缀` `graph.instagram.com` — 不确定。上游标了广告/统计，但 graph.* 也可能是客户端接口，analytics.google.com 会挡住 GA 后台。另一版自己也写了会连带误伤。
- `域名后缀` `graph.whatsapp.com` — 不确定。上游标了广告/统计，但 graph.* 也可能是客户端接口，analytics.google.com 会挡住 GA 后台。另一版自己也写了会连带误伤。
- `域名后缀` `graph.whatsapp.net` — 不确定。上游标了广告/统计，但 graph.* 也可能是客户端接口，analytics.google.com 会挡住 GA 后台。另一版自己也写了会连带误伤。
- `域名后缀` `iad.apple.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `iadsdk.apple.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `mail-ads.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `marketingplatform.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `mobileads.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `pagead.l.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `partnerad.l.google.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名后缀` `pixel.facebook.com` — 该收。落在产品根域下的广告或跟踪主机，必须写在该产品规则之前，否则 YouTube/Google/Apple 后缀会把它们放行。本仓库广告列表没有这些子域。
- `域名集合` `category-ads-all` — 不该收。不要把整份 geosite 抄进本仓库生成器。本仓库 DNS/规则政策写明不发 geosite（空工作目录没有 geo 库，且上游含关键词规则）。另一版在 mihomo/sing-box 用它做远程集合是另一套设计。

### 国内直连

本仓库 72 条，另一版 22 条。两边都有 2，仅本仓库 70，仅另一版 20。

两边都有：

- `域名后缀` `b23.tv` — 一致。两边同类型、同值、同一分流。
- `域名后缀` `bilibili.com` — 一致。两边同类型、同值、同一分流。

只有本仓库有：

- `域名后缀` `10010.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `12306.cn` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `126.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `163.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `1688.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `360.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `36kr.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `4399.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `58.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `abchina.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `alipay.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `alipayobjects.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `aliyun.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `aliyundrive.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `amap.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `autonavi.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `baidu.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `bankcomm.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `bdstatic.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `biligame.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `ccb.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `cctv.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `chinaunicom.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `cmbchina.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `csdn.net` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `ctrip.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `dianping.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `dingtalk.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `douban.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `douyin.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `eastmoney.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `ele.me` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `gitee.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `hao123.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `hupu.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `ifeng.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `iqiyi.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `ixigua.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `jd.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `kuaishou.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `meituan.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `mgtv.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `mihoyo.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `netease.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `pinduoduo.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `qpic.cn` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `qq.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `sina.cn` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `sina.com.cn` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `smzdm.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `so.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `sogou.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `sohu.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `suning.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `taobao.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `tmall.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `toutiao.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `unionpay.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `vip.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `weibo.cn` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `weibo.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `xiaohongshu.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `xiaojukeji.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `xinhuanet.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `xueqiu.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `yangkeduo.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `youdao.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `youku.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `zhihu.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。
- `域名后缀` `zhimg.com` — 该收。审计过的国内产品后缀，每条有候选源、DNS 和公开站点。另一版几乎不写这些显式条，改靠 GEOSITE,cn。本仓库没有 geosite 时，这些条是国内直连唯一的命中来源，必须留。

只有另一版有：

- `完整域名` `qianwen.aliyun.com` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `完整域名` `tongyi.aliyun.com` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `完整域名` `yiyan.baidu.com` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `完整域名` `yuanbao.tencent.com` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `域名后缀` `bigmodel.cn` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `域名后缀` `biliapi.com` — 该收。哔哩哔哩大陆接口和视频 CDN，不是 bilibili.com 的子域，本仓库只收了 bilibili.com / b23.tv，这些会漏走代理。不要和港澳台解锁主机混用。
- `域名后缀` `biliapi.net` — 该收。哔哩哔哩大陆接口和视频 CDN，不是 bilibili.com 的子域，本仓库只收了 bilibili.com / b23.tv，这些会漏走代理。不要和港澳台解锁主机混用。
- `域名后缀` `bilivideo.cn` — 该收。哔哩哔哩大陆接口和视频 CDN，不是 bilibili.com 的子域，本仓库只收了 bilibili.com / b23.tv，这些会漏走代理。不要和港澳台解锁主机混用。
- `域名后缀` `bilivideo.com` — 该收。哔哩哔哩大陆接口和视频 CDN，不是 bilibili.com 的子域，本仓库只收了 bilibili.com / b23.tv，这些会漏走代理。不要和港澳台解锁主机混用。
- `域名后缀` `chatglm.cn` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `域名后缀` `deepseek.com` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `域名后缀` `delivery.mp.microsoft.com` — 不确定。微软更新/分发，国内常有 CDN，但是否应脱离 Microsoft 组直接 DIRECT，本次没有实测。
- `域名后缀` `doubao.com` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `域名后缀` `hdslb.com` — 该收。哔哩哔哩大陆接口和视频 CDN，不是 bilibili.com 的子域，本仓库只收了 bilibili.com / b23.tv，这些会漏走代理。不要和港澳台解锁主机混用。
- `域名后缀` `kimi.com` — 不确定。另一版写明国内外共用，待实测。moonshot.cn 可以直连，kimi.com 不要凭品牌直接归国内。
- `域名后缀` `moonshot.cn` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `域名后缀` `windowsupdate.com` — 不确定。微软更新/分发，国内常有 CDN，但是否应脱离 Microsoft 组直接 DIRECT，本次没有实测。
- `域名后缀` `zhipuai.cn` — 该收。国内版 AI，应直连，不能放进其他 AI。这是基线：其他 AI 不含豆包、DeepSeek、通义、文心、Kimi 国内版、智谱。
- `地理 IP` `CN` — 不该收。本仓库写明国内 IP 段没有可靠到能编进规则的源，不用 GEOIP 冒充。另一版把它当兜底。
- `域名集合` `cn` — 不该收。本仓库明确不用 geosite:cn 代替审计过的后缀，也不把整份国内域名表抄进来。

### 共享基础设施

本仓库 16 条，另一版 0 条。两边都有 0，仅本仓库 16，仅另一版 0。

两边都有：

- （无）

只有本仓库有：

- `域名后缀` `akamai.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `akamaihd.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `akamaized.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `amazonaws.com` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `azure.com` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `azure.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `azureedge.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `cloudfront.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `edgesuite.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `ggpht.com` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `googleapis.com` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `googleusercontent.com` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `gstatic.com` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `msecnd.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `windows.net` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。
- `域名后缀` `windowsazure.com` — 该收。共享 CDN/云根，绑国外默认，不单开可见组。产品精确主机在前。另一版没有这一层，把 googleapis.com 等挂进 Google/Microsoft，或干脆不写、靠国外默认兜底。整段 amazonaws.com、cloudfront.net、akamai.net 很宽，但是本仓库有意为之，不能改挂到某个业务组。

只有另一版有：

- （无）

### 开发下载

本仓库 0 条，另一版 34 条。两边都有 0，仅本仓库 0，仅另一版 34。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `production.cloudflare.docker.com` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `完整域名` `proxy.golang.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `完整域名` `repo.maven.apache.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `完整域名` `sum.golang.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `anaconda.com` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `anaconda.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `brew.sh` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `bun.sh` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `cocoapods.org` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `crates.io` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `deno.land` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `docker.com` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `docker.io` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `gcr.io` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `go.dev` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `gradle.org` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `jsr.io` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `k8s.io` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `maven.org` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `nodejs.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `npmjs.com` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `npmjs.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `nuget.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `packagist.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `pkg.dev` — 不确定。另一版标了维护者知识，或域名过宽（例如整段 docker.com、pkg.dev）。两个上游快照未收录的不要直接并。
- `域名后缀` `pub.dev` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `pypi.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `python.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `pythonhosted.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `quay.io` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `rubygems.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `rust-lang.org` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `rustup.rs` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。
- `域名后缀` `yarnpkg.com` — 该收。通用开发依赖，应进开发下载而不是 Claude/Cursor。Claude 官方网络表把 registry.npmjs.org 和 formulae.brew.sh 列进放行清单，但它们不是 Claude 产品。本仓库开发下载组还没有规则。

### 远程控制

本仓库 0 条，另一版 1 条。两边都有 0，仅本仓库 0，仅另一版 1。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `cursorvm.com` — 该收。官方要求放行 *.cursorvm.com 与嵌套 *.*.cursorvm.com，后缀能覆盖两层。本仓库把同一条写在 Cursor 组，归远程控制更合适，默认仍是日本（国外默认的默认地区）。

### 国外默认

本仓库 0 条，另一版 13 条。两边都有 0，仅本仓库 0，仅另一版 13。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `challenges.cloudflare.com` — 该收。人机验证、支付风控或邮件跳转，应放行到国外默认，不能 REJECT，也不能收进 OpenAI。只有在广告规则会误伤它们时才需要写在广告之前。
- `完整域名` `m.stripe.com` — 该收。人机验证、支付风控或邮件跳转，应放行到国外默认，不能 REJECT，也不能收进 OpenAI。只有在广告规则会误伤它们时才需要写在广告之前。
- `完整域名` `m.stripe.network` — 该收。人机验证、支付风控或邮件跳转，应放行到国外默认，不能 REJECT，也不能收进 OpenAI。只有在广告规则会误伤它们时才需要写在广告之前。
- `域名后缀` `amazon.co.jp` — 该收。亚马逊购物站归国外默认，不单开组。Prime 的更具体规则必须排在前面。本仓库 Prime 包仍是空的，所以现在加 amazon.com 不会误伤 Prime，但以后补 Prime 时顺序不能反。
- `域名后缀` `amazon.co.uk` — 该收。亚马逊购物站归国外默认，不单开组。Prime 的更具体规则必须排在前面。本仓库 Prime 包仍是空的，所以现在加 amazon.com 不会误伤 Prime，但以后补 Prime 时顺序不能反。
- `域名后缀` `amazon.com` — 该收。亚马逊购物站归国外默认，不单开组。Prime 的更具体规则必须排在前面。本仓库 Prime 包仍是空的，所以现在加 amazon.com 不会误伤 Prime，但以后补 Prime 时顺序不能反。
- `域名后缀` `app.link` — 该收。人机验证、支付风控或邮件跳转，应放行到国外默认，不能 REJECT，也不能收进 OpenAI。只有在广告规则会误伤它们时才需要写在广告之前。
- `域名后缀` `ct.sendgrid.net` — 该收。人机验证、支付风控或邮件跳转，应放行到国外默认，不能 REJECT，也不能收进 OpenAI。只有在广告规则会误伤它们时才需要写在广告之前。
- `域名后缀` `hcaptcha.com` — 该收。人机验证、支付风控或邮件跳转，应放行到国外默认，不能 REJECT，也不能收进 OpenAI。只有在广告规则会误伤它们时才需要写在广告之前。
- `域名后缀` `images-amazon.com` — 该收。亚马逊购物站归国外默认，不单开组。Prime 的更具体规则必须排在前面。本仓库 Prime 包仍是空的，所以现在加 amazon.com 不会误伤 Prime，但以后补 Prime 时顺序不能反。
- `域名后缀` `media-amazon.com` — 该收。亚马逊购物站归国外默认，不单开组。Prime 的更具体规则必须排在前面。本仓库 Prime 包仍是空的，所以现在加 amazon.com 不会误伤 Prime，但以后补 Prime 时顺序不能反。
- `域名后缀` `ssl-images-amazon.com` — 该收。亚马逊购物站归国外默认，不单开组。Prime 的更具体规则必须排在前面。本仓库 Prime 包仍是空的，所以现在加 amazon.com 不会误伤 Prime，但以后补 Prime 时顺序不能反。
- `域名集合` `geolocation-!cn` — 不该收。本仓库未命中规则用 MATCH/FINAL 到国外默认，不需要再加 geolocation-!cn。该集合含宽规则，且本仓库不发 geosite。

### 系统联网检测

本仓库 0 条，另一版 6 条。两边都有 0，仅本仓库 0，仅另一版 6。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `完整域名` `captive.apple.com` — 该收。系统联网检测应固定直连，和节点健康检查不是同一种流量。本仓库 DNS 意图提到部分主机，但路由规则没有发出这些条。
- `完整域名` `connect.rom.miui.com` — 该收。系统联网检测应固定直连，和节点健康检查不是同一种流量。本仓库 DNS 意图提到部分主机，但路由规则没有发出这些条。
- `完整域名` `connectivitycheck.platform.hicloud.com` — 该收。系统联网检测应固定直连，和节点健康检查不是同一种流量。本仓库 DNS 意图提到部分主机，但路由规则没有发出这些条。
- `完整域名` `wifi.vivo.com.cn` — 该收。系统联网检测应固定直连，和节点健康检查不是同一种流量。本仓库 DNS 意图提到部分主机，但路由规则没有发出这些条。
- `域名后缀` `msftconnecttest.com` — 该收。系统联网检测应固定直连，和节点健康检查不是同一种流量。本仓库 DNS 意图提到部分主机，但路由规则没有发出这些条。
- `域名后缀` `msftncsi.com` — 该收。系统联网检测应固定直连，和节点健康检查不是同一种流量。本仓库 DNS 意图提到部分主机，但路由规则没有发出这些条。

### 局域网/保留地址

本仓库 0 条，另一版 18 条。两边都有 0，仅本仓库 0，仅另一版 18。

两边都有：

- （无）

只有本仓库有：

- （无）

只有另一版有：

- `域名后缀` `home.arpa` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `域名后缀` `lan` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `域名后缀` `local` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `域名后缀` `localdomain` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `域名后缀` `localhost` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `0.0.0.0/8` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `10.0.0.0/8` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `100.64.0.0/10` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `127.0.0.0/8` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `169.254.0.0/16` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `172.16.0.0/12` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `192.168.0.0/16` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `224.0.0.0/4` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv4 段` `255.255.255.255/32` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv6 段` `::1/128` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv6 段` `fc00::/7` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv6 段` `fe80::/10` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。
- `IPv6 段` `ff00::/8` — 该收。标准局域网和保留地址，应固定 DIRECT。本仓库 policy 写明尚未发出 skip-proxy / bypass-tun。

## 结论

OpenAI、Claude、Cursor、Apple AI 这几组，本仓库更合适做底：它按官方允许表收最小集，匹配类型不放宽，Apple AI 18 条独立且默认美国。另一版的 AI 覆盖更全，但 Cursor 的 `cursor.com` 后缀、Sora 停服域名，以及把 Apple 智能主机收进默认直连的 Apple 组，不该照搬。
流媒体、开发下载、国内 AI 直连、局域网和联网检测，另一版更合适：本仓库这些组大多有名字没有域名，流量实际掉进国外默认或漏走代理。广告方面两边互补，不是谁替代谁。国内普通网站，本仓库 72 条显式后缀在「不用 geosite」的前提下必须留；另一版的 GEOSITE/GEOIP 兜底不要抄进本仓库生成器。

### 建议并入本仓库的另一版条目

- OpenAI：`chat.com` 后缀，`chatgpt.livekit.cloud` 后缀。不要并 `sora.com`。
- Cursor：精确主机 `anysphere-binaries.s3.us-east-1.amazonaws.com`；把 `cursorvm.com` 从 Cursor 组挪到远程控制（规则保留）。不要用 `cursor.com` 后缀替换 `downloads.cursor.com`。另补两边都没有的 `accounts.spacex.ai`、`accounts.x.ai` 两个完整域名。
- Copilot：可把 `copilot.cloud.microsoft` 从完整域名放宽为后缀（仍不要动 `cloud.microsoft` 整段）。`copilot.ai`、`sydney.bing.com`、githubnext、附件存储桶先不要并。
- 其他 AI：`mistral.ai`、`huggingface.co`、`groq.com`、`openrouter.ai`、`midjourney.com`、`elevenlabs.io`、`elevenlabs.com`、`meta.ai`。不要并 S3/Cloudinary 桶。`pplx.ai` 继续不收，直到有官方表。
- 国内直连：`deepseek.com`、`doubao.com`、`moonshot.cn`、`chatglm.cn`、`bigmodel.cn`、`zhipuai.cn`，以及通义、千问、元宝、文心的精确主机；哔哩哔哩 `hdslb.com`、`bilivideo.com`、`bilivideo.cn`、`biliapi.com`、`biliapi.net`。`kimi.com` 先不要。
- YouTube：补后缀 `youtube.com`、`youtu.be`、`youtube-nocookie.com`、`ytimg.com`、`googlevideo.com`、`youtubekids.com`，以及 `youtubeembeddedplayer.googleapis.com`、`yt3.ggpht.com`、`yt3.googleusercontent.com`、`s.youtube.com`。现有 12 条精确主机在后缀落地前保留，不要改类型。
- Netflix：`fast.com`。`netflix.net` 和 `netflixdnstest*` 先不要。
- PayPal：`paypal.me`。不要并 v2fly 里的相似钓鱼域。
- 空的流媒体组：各产品品牌后缀（disneyplus.com、hbomax.com、hbo.com、primevideo.com、amazonvideo.com、hulu.com、hulu.jp、abema.tv、dmm.com、nicovideo.jp 等），以及必须排在更宽规则前的 `atv-ps.amazon.com`、`hulu.playback.edge.bamgrid.com`。`bilibili.tv` 归港澳台而不是其他流媒体。不要并 CloudFront/Akamai 叶子，不要把 `api.bilibili.com` 送去台湾，不要收 `byteoversea.com`，`max.com` 先不要。
- Apple：在 Apple AI 之后补 `icloud.com`、`itunes.com`、`me.com`、`appstore.com` 等。不要补 `apple-dns.net`。Apple Music/TV 的 `music.apple.com`、`tv.apple.com` 和 itunes 流媒体主机要写在 `apple.com` 前面。
- Google 组：补 gmail.com、blogger.com、blogspot.com、android.com、chrome.com、g.co、goo.gl 等第一方域。不要把 googleapis.com、gstatic.com、googleusercontent.com、ggpht.com 从共享基础设施挪进 Google 组。187 条官方国家域保留。
- GitHub：保留 `github.io`。可补 `github.blog`、`githubstatus.com`、`githubapp.com`。
- Telegram：可补 `telegra.ph`、`tdesktop.com`。14 条官方 CIDR 两边已一致，保留。
- 开发下载：npm、PyPI、crates、Go proxy、Maven Central、Homebrew、docker.io 等。gradle.org、bun.sh、jsr.io、整段 docker.com 先不要。
- 广告：补落在产品根下的 `ads.youtube.com`、`adservice.google.com`、`pagead.l.google.com` 等，并保持在产品规则之前。不要引入 `GEOSITE,category-ads-all`。`graph.instagram.com` 先不要拦截。
- 局域网保留地址和联网检测（captive.apple.com、msftconnecttest.com、msftncsi.com）应发成 DIRECT。
- 亚马逊购物域归国外默认，且以后补 Prime 时 Prime 规则必须在前。

### 本仓库有、另一版没有、应保留的

- Apple AI 全部 18 条，类型不变，默认美国，且排在任何 Apple 通用后缀之前。
- OpenAI 6 条、Claude 的 `claude.app` 与另外 5 条第一方后缀、Cursor 的 `downloads.cursor.com` 与四条官方后缀（`cursorvm.com` 保留但改组）。
- Google AI 的 7 条，尤其是三条 googleapis 精确主机和 `gemini.google.com`、`aistudio.google.com` 后缀。
- Copilot 9 条里与 GitHub 允许表一致的部分，以及没有放宽成 bing.com 的做法。`copilot.ai` 先留着，标不确定。
- 其他 AI 现有 4 条。
- YouTube 现有 12 条精确主机（在补上后缀之前它们是唯一命中）。
- Netflix 的 7 条 Open Connect 域。
- PayPal 两条与「美国固定、不跟随国外默认」。
- Telegram 的 `telegram.org`、`t.me` 和 14 条官方 CIDR。
- X 的四条（含 x.com）。x.com 是产品域，两边都收了；它会盖住 x.com 上的 Grok，这是域名拆不开，不是误收。
- GitHub 的 `github.io`，以及 github.com / githubusercontent.com 等 /meta 域。
- 广告 41 条独立广告网络。
- 国内直连 72 条。
- 共享基础设施 16 条，继续绑国外默认。
- Google 官方 187 个搜索国家域（`google.cn` 的出口是否走代理仍不确定，域名先留在 Google 组）。
- Microsoft 68 条 M365 端点，不要被另一版的 `bing.com` / `live.com` / `azure.com` 整段替换。

### 哪一版更合适（按分流）

| 分流 | 更合适的底 | 原因 |
|---|---|---|
| OpenAI | 本仓库，另并 chat.com 与 chatgpt.livekit.cloud | 官方最小集已对齐；Sora 域名不该加 |
| Claude | 本仓库 | 多出来的 claude.app 有当日 Desktop 文档；另一版多的两条没有进官方表 |
| Cursor | 本仓库的匹配宽度，另一版的远程控制归属 | 不要 cursor.com 整段；要 S3 精确主机；cursorvm 归远程控制；两边都要补新的登录主机 |
| Google AI | 本仓库 | 另一版多出的 30 多条大多只有上游列表，官方表本次没复核到 |
| Copilot | 本仓库，入口主机可改为后缀 | 与 GitHub 允许表一致；不要 sydney.bing.com 和共享存储桶 |
| 其他 AI | 本仓库打底，并入一批品牌域 | 国内 AI 必须留在直连，不能跟着这组走日本 |
| Apple AI | 本仓库 | 另一版没有这组，且会被 Apple 直连吞掉 |
| YouTube | 另一版的后缀更够用 | 本仓库精确主机太窄，但不要删，应加后缀 |
| Netflix | 本仓库 7 条，另加 fast.com | 解锁入口两边都未验证 |
| 其余流媒体 | 另一版的品牌域 | 本仓库组是空的；CDN 叶子和过宽域不要一起搬 |
| Telegram / X / 社交 | 大体持平，本仓库更窄 | Telegram CIDR 已一致；X 的停服域不要加；Meta 的 fbcdn 可以补 |
| Apple / Music | 本仓库的 Apple AI 前置 + 另一版的 icloud/itunes 与 Music 主机 | 不要 apple-dns.net |
| Google | 本仓库的 187 国家域 + 另一版的 gmail 等产品域 | 共享根留在共享基础设施 |
| Microsoft | 本仓库 | 另一版的 bing/live/azure 整段过宽 |
| GitHub | 本仓库，可补博客和状态页 | github.io 必须留 |
| PayPal | 两边结构相同，补 paypal.me | 美国固定不要改 |
| 广告 | 两边叠在一起 | 显式广告网络留本仓库；产品子域广告用另一版；不抄 geosite |
| 国内直连 | 本仓库 72 条 + 另一版国内 AI 和哔哩哔哩 CDN | 不抄 GEOSITE,cn / GEOIP,CN |
| 共享基础设施 | 本仓库 | 另一版没有这一层 |
| 开发下载 / 局域网 / 联网检测 | 另一版 | 本仓库有组或有 DNS 意图，但没有这些路由 |

整体仍都不是生产就绪：本仓库导入和实机未验证；另一版 Netflix 解锁和固定 PayPal 节点也是空的，真实订阅不在仓库里。以上「该收」只表示规则归属，不表示已经在设备上打通过。

