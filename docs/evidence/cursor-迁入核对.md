# Cursor 版迁入核对（自动生成，请勿手改）

由 `tools/check_cursor_report.py --write` 生成。输入是 Cursor 云端的逐条对照明细 `docs/evidence/cursor-对照明细.csv`（报告里“本仓库”= Cursor 版，“另一版”= 本工程），按当前统一源 `2026.10.05-1` 计算每条规则的去向。
“去向”按 mihomo 计算；后缀规则同时测根域和一个子域。Loon / Quantumult X 与 mihomo 不同的只有“只写进 mihomo / sing-box”那一类。

## 一、Cursor 版的规则在本工程里进哪个组

Cursor 版共 533 条：同组 435，同组（只写进 mihomo / sing-box） 70，无专门规则 18，不同组 9，已替换 1。

| 分流 | 同组 | 同组（只写进 mihomo / sing-box） | 已替换 | 不同组 | 无专门规则 |
|---|---|---|---|---|---|
| OpenAI | 6 |  |  |  |  |
| Claude | 6 |  |  |  |  |
| Cursor | 4 |  |  | 1 |  |
| Google AI | 5 |  |  | 2 |  |
| Copilot | 8 |  |  |  | 1 |
| 其他 AI | 2 |  |  | 2 |  |
| Apple AI | 17 |  | 1 |  |  |
| YouTube | 10 |  |  |  | 2 |
| Netflix | 7 |  |  |  |  |
| Spotify | 2 |  |  |  |  |
| TikTok | 3 |  |  |  |  |
| Twitch | 3 |  |  |  |  |
| Bahamut | 1 |  |  |  |  |
| Telegram | 16 |  |  |  |  |
| X | 4 |  |  |  |  |
| Meta 社交 | 8 |  |  |  | 1 |
| WhatsApp | 3 |  |  |  |  |
| LINE | 4 |  |  |  |  |
| Discord | 4 |  |  |  |  |
| Reddit | 4 |  |  |  | 1 |
| LinkedIn | 3 |  |  |  |  |
| Apple | 10 |  |  |  |  |
| Google | 187 |  |  |  |  |
| Microsoft | 68 |  |  |  |  |
| GitHub | 5 |  |  |  | 1 |
| PayPal | 2 |  |  |  |  |
| 广告拦截 | 41 |  |  |  |  |
| 国内直连 | 2 | 70 |  |  |  |
| 共享基础设施 |  |  |  | 4 | 12 |

去向不同、没有专门规则或被替换的条目，逐条写明处理：

| 分流 | 类型 | 值 | 报告判断 | 本工程去向 | 处理 |
|---|---|---|---|---|---|
| Cursor | 域名后缀 | `cursorvm.com` | 不该收 | 远程控制 | Cursor 官方文档写明是 Grok Bot 托管计算机，本工程归远程控制（报告也建议这样挪） |
| Google AI | 域名后缀 | `aistudio.google.com` | 该收 | Google AI / Google | 本工程按精确主机写（归 Google AI），子域会走 Google；目前没有已知子域，对现有主机结果相同 |
| Google AI | 域名后缀 | `gemini.google.com` | 该收 | Google AI / Google | 本工程按精确主机写（归 Google AI），子域会走 Google；目前没有已知子域，对现有主机结果相同 |
| Copilot | 域名后缀 | `copilot.ai` | 不确定 | 兜底 | 归属未证实（报告也标“不确定”），不是 Microsoft 的域名；未收录，落入国外默认 |
| 其他 AI | 域名后缀 | `grok.com` | 一致 | Grok | 2026-09-30 用户决定 Grok / xAI 与 Cursor 合并为 Grok 组，不再归其他 AI |
| 其他 AI | 域名后缀 | `x.ai` | 一致 | Grok | 2026-09-30 用户决定 Grok / xAI 与 Cursor 合并为 Grok 组，不再归其他 AI |
| Apple AI | 关键词 | `siri` | 该收 | Apple AI（三条后缀） | 按 2026-09-29 补充需求，关键词换成 siri.apple.com、siri.com、applesiri.cn 三条后缀 |
| YouTube | 完整域名 | `www.youtubeeducation.com` | 该收 | 兜底 | 未收录，落入国外默认（YouTube 组默认也是国外默认） |
| YouTube | 完整域名 | `youtubeeducation.com` | 该收 | 兜底 | 未收录，落入国外默认（YouTube 组默认也是国外默认） |
| Meta 社交 | 域名后缀 | `instagr.am` | 该收 | 兜底 | Instagram 短链接，未收录，落入国外默认 |
| Reddit | 域名后缀 | `redditinc.com` | 该收 | 兜底 | 公司官网，按采纳原则不收，落入国外默认 |
| GitHub | 域名后缀 | `github.io` | 该收 | 兜底 | GitHub Pages 托管第三方站点，按共享托管根域不收（见 github 服务的 shared_excluded），落入国外默认 |
| 共享基础设施 | 域名后缀 | `akamai.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `akamaihd.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `akamaized.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `amazonaws.com` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `azure.com` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `azure.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `azureedge.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `cloudfront.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `edgesuite.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `ggpht.com` | 该收 | Google | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 |
| 共享基础设施 | 域名后缀 | `googleapis.com` | 该收 | Google | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 |
| 共享基础设施 | 域名后缀 | `googleusercontent.com` | 该收 | Google | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 |
| 共享基础设施 | 域名后缀 | `gstatic.com` | 该收 | Google | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 |
| 共享基础设施 | 域名后缀 | `msecnd.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `windows.net` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |
| 共享基础设施 | 域名后缀 | `windowsazure.com` | 该收 | 兜底 | 共享云 / CDN 根域：本工程不给它写专门规则，交给兜底（境外域名 → 国外默认；解析到国内 IP 的 → 国内直连）。Cursor 版把它显式绑到国外默认 |

“同组（只写进 mihomo / sing-box）”是国内常用网站：Loon / QX 不写这些规则，由 `GEOIP,CN` 兜底直连，原因见 `docs/06`。

## 二、报告判为“不该收”的本工程条目

共 31 条。

| 分流 | 类型 | 值 | 现在 | 处理 | 报告理由 |
|---|---|---|---|---|---|
| OpenAI | 域名后缀 | `sora.com` | 已不在 | 已删除（采纳）：Sora 已停服，导出页 sora.chatgpt.com 由 chatgpt.com 覆盖 | Sora 网页/App 已于 2026-04-26 停服，API 于 2026-09-24 停服；导出页是 sora.chatgpt.com，已被 chatgpt.com 后缀覆盖。 |
| Cursor | 域名后缀 | `cursor.com` | 仍在（cursor → Grok） | 保留后缀：cursor.com 的子域都属于 Cursor（官网、控制台、登录跳转、文档），归 Cursor 组不会误收第三方；证据由官方改标为 dlc（官方网络文档只列了 downloads.cursor.com） | 官方推荐模式是 *.cursor.sh、*.cursor-cdn.com、*.cursorapi.com、*.cursorvm.com，颗粒列表只有 downloads.cursor.com，没有 *.cursor.com。整段后缀会吞掉未列出的子域。 |
| Google AI | 完整域名 | `aistudio.google.com` | 仍在（google_ai → Google AI） | 保留：报告的理由是 Cursor 版已有同名后缀，对本工程不适用 | 本仓库已有同名域名后缀，精确主机是其子集合，再写一条不增加命中。 |
| Google AI | 完整域名 | `daily-cloudcode-pa.googleapis.com` | 仍在（google_ai → Google AI） | 保留：上游 dlc 归入 Gemini Code Assist；官方清单未列，已在规则说明里注明 | 另一版自己注明 2026-09-23 复核时不在 Gemini Code Assist 官方清单内。 |
| Google AI | 完整域名 | `gemini.google.com` | 仍在（google_ai → Google AI） | 保留：报告的理由是 Cursor 版已有同名后缀，对本工程不适用 | 本仓库已有同名域名后缀，精确主机是其子集合，再写一条不增加命中。 |
| 其他 AI | 完整域名 | `ppl-ai-file-upload.s3.amazonaws.com` | 仍在（perplexity → 其他 AI） | 保留：只收 Perplexity 专属的这一个存储桶主机，不收云根域（与报告认可的 Cursor 专属 S3 主机同一原则） | 共享 S3 / Cloudinary 上的桶。精确主机仍是别人的云，本仓库约定这种依赖不进产品组，交给国外默认。 |
| 其他 AI | 完整域名 | `pplx-res.cloudinary.com` | 仍在（perplexity → 其他 AI） | 保留：只收 Perplexity 专属的这一个资源主机，不收云根域（与报告认可的 Cursor 专属 S3 主机同一原则） | 共享 S3 / Cloudinary 上的桶。精确主机仍是别人的云，本仓库约定这种依赖不进产品组，交给国外默认。 |
| TikTok | 域名后缀 | `byteoversea.com` | 已不在 | 已移出 TikTok（采纳），byteglb.com 一并移出 | 字节海外共用根，不是 TikTok 独占。本仓库审计明确不收，收了会把其他字节海外产品卷进 TikTok 组。 |
| TikTok | 域名后缀 | `byteoversea.net` | 已不在 | 已移出 TikTok（采纳） | 字节海外共用根，不是 TikTok 独占。本仓库审计明确不收，收了会把其他字节海外产品卷进 TikTok 组。 |
| Bilibili 港澳台 | 完整域名 | `api.bilibili.com` | 仍在（bilibili_hmt → Bilibili 港澳台） | 保留：需求要求港澳台内容走 Bilibili 港澳台，这些接口主机大陆与港澳台共用、按域名拆不开；代价与切换方法见 docs/06 第 5 项 | 和大陆客户端共用主机。排在 bilibili.com 国内直连前面会把大陆 API 送去台湾。另一版自己也写了「与大陆使用共用主机」。 |
| Bilibili 港澳台 | 完整域名 | `app.bilibili.com` | 仍在（bilibili_hmt → Bilibili 港澳台） | 保留：需求要求港澳台内容走 Bilibili 港澳台，这些接口主机大陆与港澳台共用、按域名拆不开；代价与切换方法见 docs/06 第 5 项 | 和大陆客户端共用主机。排在 bilibili.com 国内直连前面会把大陆 API 送去台湾。另一版自己也写了「与大陆使用共用主机」。 |
| Bilibili 港澳台 | 完整域名 | `bangumi.bilibili.com` | 仍在（bilibili_hmt → Bilibili 港澳台） | 保留：需求要求港澳台内容走 Bilibili 港澳台，这些接口主机大陆与港澳台共用、按域名拆不开；代价与切换方法见 docs/06 第 5 项 | 和大陆客户端共用主机。排在 bilibili.com 国内直连前面会把大陆 API 送去台湾。另一版自己也写了「与大陆使用共用主机」。 |
| X | 域名后缀 | `periscope.tv` | 仍在（x → X） | 保留：域名仍属 X，归 X 组没有副作用（上游 dlc twitter 列表仍收录） | 本仓库审计把 Periscope / pscp 标为已停产品，不再收。 |
| X | 域名后缀 | `pscp.tv` | 仍在（x → X） | 保留：域名仍属 X，归 X 组没有副作用（上游 dlc twitter 列表仍收录） | 本仓库审计把 Periscope / pscp 标为已停产品，不再收。 |
| Apple | 域名后缀 | `apple-dns.net` | 仍在（apple → Apple） | 保留在 Apple 组（2026-09-29 补充需求明确要求）；Apple AI 的 20 条都写在它之前 | 会匹配 mask.apple-dns.net 等 Apple AI 主机。另一版没有 Apple AI 组，这些流量会进默认 DIRECT 的 Apple 组。本仓库不应在 Apple AI 18 条之前加入这条后缀。 |
| Google | 域名后缀 | `ggpht.com` | 仍在（google → Google） | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 | 这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。 |
| Google | 域名后缀 | `googleapis.com` | 仍在（google → Google） | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 | 这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。 |
| Google | 域名后缀 | `googleusercontent.com` | 仍在（google → Google） | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 | 这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。 |
| Google | 域名后缀 | `gstatic.com` | 仍在（google → Google） | 设计差异：本工程把 Google 共享根放在 Google 组（默认国外默认，与 Cursor 版“共享基础设施”的出口相同），Gemini API、YouTube 接口等专属主机排在它前面；用户可以整体切换 Google 组 | 这些是共享根。本仓库放在共享基础设施并绑国外默认，产品精确主机（Gemini API、YouTube 接口）排在前面。挂到 Google 组会让用户把 Google 改成直连时，把 API 和头像 CDN 一起改掉。 |
| Google | 域名后缀 | `recaptcha.net` | 仍在（google → Google） | 保留后缀：这是 Google 为访问不了 google.com 的地区准备的 reCAPTCHA 域名，子域都属于 Google；证据标维护者知识 | 另一版写明上游只有 recaptcha.net 与 www.recaptcha.net 两个精确主机，收成后缀是放宽。 |
| Microsoft | 域名后缀 | `azure.com` | 已不在 | 已移出 Microsoft（采纳），并加入共享云禁收名单 | azure.com 本仓库在共享基础设施；bing.com 整段会吞掉搜索，Copilot 只能靠更具体的 sydney.bing.com 抢先。官方 Copilot 文档要求的是 M365 与 copilot.cloud.microsoft，不是整段 Bing。 |
| Microsoft | 域名后缀 | `bing.com` | 仍在（microsoft → Microsoft） | 保留：Microsoft 第一方域名（必应、Microsoft 账户、静态资源短域），不托管第三方内容；Copilot 的更具体规则排在前面 | azure.com 本仓库在共享基础设施；bing.com 整段会吞掉搜索，Copilot 只能靠更具体的 sydney.bing.com 抢先。官方 Copilot 文档要求的是 M365 与 copilot.cloud.microsoft，不是整段 Bing。 |
| Microsoft | 域名后缀 | `bing.net` | 仍在（microsoft → Microsoft） | 保留：Microsoft 第一方域名（必应、Microsoft 账户、静态资源短域），不托管第三方内容；Copilot 的更具体规则排在前面 | azure.com 本仓库在共享基础设施；bing.com 整段会吞掉搜索，Copilot 只能靠更具体的 sydney.bing.com 抢先。官方 Copilot 文档要求的是 M365 与 copilot.cloud.microsoft，不是整段 Bing。 |
| Microsoft | 域名后缀 | `gfx.ms` | 仍在（microsoft → Microsoft） | 保留：Microsoft 第一方域名（必应、Microsoft 账户、静态资源短域），不托管第三方内容；Copilot 的更具体规则排在前面 | 过宽。本仓库已有 login.live.com、oneclient.sfx.ms 等 endpoints 精确主机，整段 live.com / *.ms 短域会卷进未审计子域。 |
| Microsoft | 域名后缀 | `live.com` | 仍在（microsoft → Microsoft） | 保留：Microsoft 第一方域名（必应、Microsoft 账户、静态资源短域），不托管第三方内容；Copilot 的更具体规则排在前面 | 过宽。本仓库已有 login.live.com、oneclient.sfx.ms 等 endpoints 精确主机，整段 live.com / *.ms 短域会卷进未审计子域。 |
| Microsoft | 域名后缀 | `sfx.ms` | 仍在（microsoft → Microsoft） | 保留：Microsoft 第一方域名（必应、Microsoft 账户、静态资源短域），不托管第三方内容；Copilot 的更具体规则排在前面 | 过宽。本仓库已有 login.live.com、oneclient.sfx.ms 等 endpoints 精确主机，整段 live.com / *.ms 短域会卷进未审计子域。 |
| GitHub | 域名后缀 | `collector.github.com` | 仍在（误杀例外 → GitHub） | 保留为误杀例外：mihomo / sing-box 用的 category-ads-all 会拦它，GitHub 官方 Copilot 放行清单要求放行 | GitHub 官方 Copilot 允许表有这台遥测主机，但本仓库 github.com 后缀已经把它归到 GitHub。单独再写一条只有在引入会拦截它的广告集合时才需要，作为误杀例外而不是新分流。 |
| 广告拦截 | 域名集合 | `category-ads-all` | 设计差异 | 设计差异：本工程在 mihomo / sing-box 引用远程集合（category-ads-all 广告拦截，cn / geolocation-!cn / GEOIP,CN 兜底），Loon / QX 用 AdvertisingLite 广告集合与 GEOIP,CN 兜底；未命中专门规则的流量才走到这些集合。理由见 docs/03、docs/06 | 不要把整份 geosite 抄进本仓库生成器。本仓库 DNS/规则政策写明不发 geosite（空工作目录没有 geo 库，且上游含关键词规则）。另一版在 mihomo/sing-box 用它做远程集合是另一套设计。 |
| 国内直连 | 地理 IP | `CN` | 设计差异 | 设计差异：本工程在 mihomo / sing-box 引用远程集合（category-ads-all 广告拦截，cn / geolocation-!cn / GEOIP,CN 兜底），Loon / QX 用 AdvertisingLite 广告集合与 GEOIP,CN 兜底；未命中专门规则的流量才走到这些集合。理由见 docs/03、docs/06 | 本仓库写明国内 IP 段没有可靠到能编进规则的源，不用 GEOIP 冒充。另一版把它当兜底。 |
| 国内直连 | 域名集合 | `cn` | 设计差异 | 设计差异：本工程在 mihomo / sing-box 引用远程集合（category-ads-all 广告拦截，cn / geolocation-!cn / GEOIP,CN 兜底），Loon / QX 用 AdvertisingLite 广告集合与 GEOIP,CN 兜底；未命中专门规则的流量才走到这些集合。理由见 docs/03、docs/06 | 本仓库明确不用 geosite:cn 代替审计过的后缀，也不把整份国内域名表抄进来。 |
| 国外默认 | 域名集合 | `geolocation-!cn` | 设计差异 | 设计差异：本工程在 mihomo / sing-box 引用远程集合（category-ads-all 广告拦截，cn / geolocation-!cn / GEOIP,CN 兜底），Loon / QX 用 AdvertisingLite 广告集合与 GEOIP,CN 兜底；未命中专门规则的流量才走到这些集合。理由见 docs/03、docs/06 | 本仓库未命中规则用 MATCH/FINAL 到国外默认，不需要再加 geolocation-!cn。该集合含宽规则，且本仓库不发 geosite。 |
