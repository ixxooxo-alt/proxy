# 统一分流规则与多客户端配置

[English](README.md)

> 审核者请先读 `00-审核说明.md`。

一份自有、可审计、可测试的规则源（`source/`），由生成器（`generator/`）同时产出 Loon、Quantumult X、mihomo（Clash Verge Rev / Clash Meta for Android / 内核）和 sing-box（SFA）的配置。四个客户端不各自手写，改规则只改 `source/`，再重新生成。

## 直接用：拿哪个文件

| 设备 / 客户端 | 文件 | 使用前要做的事 |
|---|---|---|
| iPhone / iPad / Mac：Loon | `dist/loon/loon.conf`（标准版）；`dist/loon/loon-strict.conf`（严格版，可选，见下面“严格版”一段） | 把 `[Remote Proxy]` 里的占位链接换成你的订阅 |
| iPhone / iPad / Mac：Quantumult X | `dist/quantumultx/quantumultx.conf`（标准版）；`dist/quantumultx/quantumultx-strict.conf`（严格版，可选） | 把 `[server_remote]` 里的占位链接换成你的订阅 |
| Windows / macOS：Clash Verge Rev | `dist/mihomo/mihomo-profile.yaml` | 把 `proxy-providers` 的 `url` 换成你的订阅；App 里有几个开关要手动确认（虚拟网卡开、“DNS 覆写”关等），见 `docs/01`“每个客户端要手动确认的开关” |
| Android：Clash Meta for Android | `dist/mihomo/mihomo-profile.yaml` | 同上 |
| Linux / 路由器：mihomo 内核直接运行 | `dist/mihomo/mihomo-core.yaml` | 同上；含本机端口与控制面，TUN 默认关闭 |
| Android：SFA（sing-box） | 需要在本机生成（见下） | sing-box 不支持订阅，节点必须写进配置 |

占位链接是 `https://REPLACE-ME.invalid/请替换为你的订阅链接`，不替换就无法使用。Loon、Quantumult X、Clash Verge Rev 也可以先导入、再在 App 里把订阅换掉（做法见 `docs/01`“导入前”）。订阅链接属于私密信息，不要写回 `source/`，也不要把替换后的文件发给别人。

**这是哪一版**：每份配置开头的注释里写着“统一源版本”，`dist/manifest.json` 里也有。这份说明对应 `2026.10.07-2`（r14：处理 GPT 对 r13 的审核——mihomo 上走代理组的产品域名改问境外 DNS；再加上使用者 2026-10-07 定下的待决事项——“国内直连”固定直连（组里只剩 DIRECT）、对时和运营商认证的名字四端固定直连、Bilibili 港澳台默认直连、友盟和阿里妈妈只拦统计 / 广告子域、Apple AI 去掉三条宽规则、取消 Netflix·解锁入口、Clash 上不带点的名字交给系统 DNS、Quantumult X 严格版多一份国内大清单。四个客户端的配置都变了，逐项见 `docs/06`）。r12–r14 做完时都没有立刻推到 GitHub 仓库 `ixxooxo-alt/proxy` 的 `main`（用户 2026-10-06 的要求：先交给 GPT 审核），在审核用的分支上；那时仓库的 `main` 里是上一版 r11（`2026.10.05-2`）。仓库里现在是哪一版，以 `main` 分支 `dist/manifest.json` 的 `source_version` 为准——旧版的配置不含之后各轮的修正，也没有严格版。

**严格版（Loon / Quantumult X，2026-10-06 新增，可选）**：标准版里，没有被任何域名规则接住的域名要先用国内 DNS 解析，再按 IP 决定直连还是走代理——国内 DNS 看得到这些域名。严格版不解析它们，直接交给“国外默认”；国内网站靠一份国内域名清单认出来，照常由国内 DNS 解析后直连，所以国内网站的解析没有变慢。代价是清单里没有的国内网站会走代理（能打开，会慢）。两份配置的策略组、订阅、图标完全相同，可以在 App 里随时切换。**严格版没有在手机上验证过**，两个 App 的规则先后有四处靠推断；它还依赖仓库 `main` 分支里 `dist/loon/rules/`、`dist/quantumultx/rules/` 下的规则文件（Loon 一个、Quantumult X 三个），仓库更新到这一版之前用不了。怎么用、怎么切回见 `docs/01`，做法和限制见 `docs/03`、`docs/06`，上手机先按 `docs/09` 第 1b 节走一遍。Clash 系客户端和 SFA 没有严格版：它们的配置设计上就不把走代理的域名交给国内 DNS，前提是几个开关设对（`docs/01`“每个客户端要手动确认的开关”）；核对时查出来的三类例外（`docs/06` 第 14–16 项）在 r14 都改了。

**策略组图标**（2026-10-05 起）：Loon、Quantumult X、Clash 系客户端的 81 个策略组各带一个图标地址，指向图标仓库 `https://github.com/ixxooxo-alt/icon` 里和策略组同名的图（256px）；sing-box 没有图标字段。图标只影响显示，不影响分流；图片不在本工程里。三个客户端里显示不显示还没有在真机上看过，Loon 的写法依据最弱——导入后策略组少了或报错时，把 `source/icons.yaml` 的 `enabled` 改成 `false` 重新生成，得到不带图标的同一份配置（`docs/01`“策略组图标”）。

### 在自己电脑上生成带订阅的版本（可选）

需要 Python 3.10+ 和 PyYAML（`pip install pyyaml`）。

macOS / Linux（bash、zsh）：

```bash
# 用 read 粘贴订阅，输入不回显，也不会进命令历史（直接写 export SUB_URLS='…' 会留在历史里）
read -rs SUB_URLS && export SUB_URLS
python3 build.py                       # 公开产物在 dist/，带订阅的私密产物在 dist/private/

# sing-box（SFA）：把 Clash / mihomo 格式的订阅转换成节点
python3 build.py --singbox-sub-url "$SUB_URLS"     # 或 --singbox-nodes 下载好的订阅.yaml
```

Windows（PowerShell）：

```powershell
# Read-Host 输入的内容不会进 PowerShell 的命令历史
$env:SUB_URLS = Read-Host "粘贴订阅链接"
python build.py
python build.py --singbox-sub-url $env:SUB_URLS
```

转换器只接受能原样表达的节点：不支持的协议或参数会写进 `dist/private/sing-box-节点转换报告.txt` 并跳过，不会悄悄删参数、改协议或放宽 TLS 校验；与策略组同名的节点会改名并写进报告。

有 `source/local.yaml` 时，个人覆盖（固定节点、公司内网等）只写进 `dist/private/`；公开的 `dist/` 始终不含它，可以放心分享。

## 策略组怎么用

- **业务组**（OpenAI、YouTube、Telegram……）：第一项是默认出口，可以手动切到别的地区。客户端会按组名记住你的选择，重新导入或更新配置不会覆盖。
- **国外默认**：七个地区入口，默认日本。
- **Grok**：Cursor 与 Grok / xAI 合在一个组（2026-09-30 起 Cursor 用 xAI 账号登录），默认日本。X 应用里的 Grok 与 x.com 共用地址，仍归 X。
- **Apple Push**（2026-10-06）：Apple 的推送通知（`*.push.apple.com`）单独一组，默认直连，和以前跟着 Apple 组时效果一样。通知来得慢、收不到，想让它走代理时，把这个组切到“国外默认”或某个地区；切过去以后推送通不通没有实测。
- **Apple AI**：Apple 智能、Siri、iCloud 专用代理，默认美国（可切到其他支持 Apple 智能的地区，没有 DIRECT）；规则排在 Apple 组之前。2026-10-07 起按使用者的决定去掉了三条宽规则，Apple 地图 / 定位、App Store 图片、CloudKit 不再跟着这组走（`docs/06` 第 8 项）。
- **地区入口**（香港、日本、韩国、台湾、新加坡、美国）：选择这个地区的工作模式，默认“手动优先”。设计目标是：先用你在“X·手动”里选的节点，它挂了换到同地区可用的节点，恢复后切回，不跨国，也不偷偷直连。mihomo 按这个设计生成；Loon 的组嵌套、Quantumult X 的恢复切回、各端实际多久切换，都还没在真机上确认（见 `docs/06`）。“同地区”指的是名字指向这个地区：自动 / 故障转移 / 负载均衡只在“名字里有落地位置上的本地区字样、而且只指向本地区”的节点里挑，但名字证明不了节点实际从哪里出去。
- **其他地区**：纯手动。落地在其他国家的节点、名字里认不出地区的节点都在这里。
- **节点怎么分到地区**：只看节点名字（国旗、地名、城市、代码），按 `source/regions.yaml` 的词表和固定顺序判断：中转 / 入口位置的地名、“解锁”说明里的地名都不算落地；“剩余流量：…”“官网：…”这类提示行不进任何组（名字里只是带了“官网”“流量”字样的真节点照常进组）；名字说不清落地的节点只进所列地区的“手动”组，不进“自动 / 故障转移 / 负载均衡”——包括指向两个地区的（`日本-美国 01`），以及 2026-10-05 起名字里提到的地区不在落地位置的（只写“地名 + 中转”的 `香港中转 01`、国旗后面直接接着中转词的 `🇭🇰 中转 01`、地区只在解锁说明里的 `Premium 01 | 解锁美国`）。你的机场如果大多是“香港中转 01”这种写法，自动组会少很多，见 `docs/06` 待决事项第 12 项。反过来，规则只认识“中转、中继、转、入口、relay、transit、via、经”这几个词，换一种说法（`经由日本 01`、`香港跳板 01`、`Singapore Entry 01`）会被当成落地、进自动组，见 `docs/06` 最后一节。它不证明节点实际从哪里出去。想知道自己订阅里每个节点进了哪个组、为什么，用 `python3 tools/check_node_names.py`；分错或没认出来的在 `source/local.yaml` 里补（见 `docs/01`“节点按名称分地区”）。
- **PayPal·美国固定**：独立挑一个美国节点，不跟随国外默认。
- **Netflix**：2026-10-07 起按普通分组（取消了单独的“Netflix·解锁入口”，`docs/06` 第 3 项），默认国外默认；节点解锁不了时在组里换地区或换节点。
- **Qwen 国际版**（`qwen.ai`、`qwenlm.ai`）：走国外默认（2026-10-04 的决定；上游的国内域名集合把它算作国内，这里用显式规则改过来）。国内版通义 / 千问走国内直连。
- **`.ms` 域名（只在 Clash 系客户端上）**：上游的国内域名集合里有整段 `.ms`。按 2026-10-04 的决定不更正、跟随上游：`aka.ms`、`1drv.ms` 等有规则的照常走 Microsoft 组，其余 `.ms` 域名走国内直连。SFA、Loon、Quantumult X 不受影响。见 `docs/06`。

各端能力不完全一样（例如 sing-box 没有“手动优先”，默认改为同地区自动测速），见 `docs/02-语法依据与能力矩阵.md` 和 `docs/06-已知限制与待决事项.md`。

## 目录

```
source/                 统一源（唯一需要手改的地方）
  project.yaml          地区的工作模式、健康检查、DNS、局域网
  regions.yaml          按节点名称分地区：六个地区与其他国家的词表（分国名、城市两级）、提示行的词、中转词、“解锁”类词与判断顺序
  groups.yaml           业务策略组与默认出口、PayPal 专用入口
  icons.yaml            策略组图标：哪个组用图标仓库里的哪张图（图片不在本工程里）
  strict.yaml           Loon / Quantumult X 严格版：国内域名清单用哪些、自有规则文件发布在哪里
  data/cn-domains.txt   严格版的自有国内域名清单（由 tools/update_cn_list.py 从 domain-list-community 的固定快照生成，MIT；不要手改）
  data/cn-domains-max.txt  Quantumult X 严格版用的上游国内大清单副本（同一个工具从 blackmatrix7 的固定快照照录，GPL-2.0，许可在 data/LICENSE-ios_rule_script.txt；不要手改）
  services/*.yaml       每个服务的规则，逐条带证据
  adblock.yaml          广告集合、自有拦截、误杀例外、HTTPDNS
  evidence.yaml         证据登记（官方文档 / 社区规则集固定快照 / 维护者知识）
  local.example.yaml    本地覆盖示例（固定节点、已验证解锁节点、自定义规则、节点名称的本地补充）
generator/              生成器
tests/                  测试：独立写出的期望 + 各客户端匹配语义模拟
tools/                  check_node_names.py：看一批节点名各进哪个地区组、为什么
                        可选：官方程序检查（含 mihomo 内核实际分组）；用官方内核和真实上游数据核对路由与 DNS 去向；ICU 正则核对；
                        用上游源码核对字段名；按上游规则集快照核对证据；对照 Cursor 版报告核对迁入；变异检查；
                        分析 Clash 连接记录；与上一版交付包对比；拿图标仓库的检出目录核对图标地址；
                        国内 DNS 与路由的逐条扫描；重新生成 / 核对严格版的国内域名清单
dist/                   生成产物（公开，可分享；private/ 除外）。loon/rules/、quantumultx/rules/ 是严格版引用的规则文件
docs/                   需求原文与对照、说明、依据、DNS 决策、规则清单、验收记录、已知限制、真机验收操作清单
00-审核说明.md          给审核者的说明与检查重点
README.md               英文说明；README.zh-CN.md 是这份中文说明
.gitignore              不进 Git 的文件：dist/private/（带订阅的私密产物）、source/local.yaml（个人覆盖）、缓存
```

## 改规则

1. 在 `source/services/*.yaml` 里增删规则，每条写明 `ev`（证据 id）。证据写 `dlc` / `bm7-snap`（社区规则集）时，要在有上游检出目录的机器上运行 `python3 tools/check_upstream_evidence.py --dlc … --bm7 … --write` 更新核对记录，否则测试会失败；拿不出依据的写 `maintainer`。
2. `python3 build.py` 重新生成；源数据有冲突（重复归属、共享云根域、例外遮挡、拼错的字段、重复的键、引用不存在的组等）时会直接报错，不改动任何产物。
3. `python3 -m unittest discover -s tests` 跑测试；或 `bash tools/run_checks.sh` 一次跑完生成、测试和各项核对，任何一步失败都以非零退出码结束。
4. 需要只属于你自己的规则、固定 PayPal 节点、给某家机场特有的节点名补地区时，复制 `source/local.example.yaml` 为 `source/local.yaml` 再改，它与默认值分开，更新统一源不会覆盖。
5. 改地区的关键词：改 `source/regions.yaml` 的词表（不要手写正则，四端的筛选都由生成器拼出）。同一个词不能出现在两个地区；纯英文的词放 `latin`；国名、代码放 `country`，城市、运营商放 `words` / `latin`。改完跑测试：每个词都必须归它所在的地区，其他国家的名称不能被认成六个地区之一。
6. 某个域名“必须走某个组”时写成显式规则，不要只写在说明里：上游的国内 / 国外域名集合每天在变，没有显式规则的域名会跟着上游走。`shared_excluded` 里的条目如果写了 `to`（去向）和 `probe`（具体主机），测试会按它核对；改了规则或加了用例之后，在有官方内核和上游数据的机器上运行 `tools/check_real_routes.py … --write-snapshot` 更新快照，否则测试会失败并提示。
7. 严格版的国内域名清单（`source/data/cn-domains.txt`，和 Quantumult X 用的大清单副本 `source/data/cn-domains-max.txt`）不要手改：它们由 `tools/update_cn_list.py` 从 domain-list-community、blackmatrix7 的固定快照生成，测试会核对。要给严格版补一个清单里没有的国内网站，在 `source/services/` 里给它加一条交给“国内直连”的规则（四个客户端都生效；Loon / Quantumult X 上本地规则先于远程的广告集合，这个域名下如果有广告主机就拦不到了，见 `docs/06`），或者写在 `source/local.yaml` 里（只进私密产物）。

## 验证状态

自动测试 ⟦tests_n⟧ 项全部通过。官方程序 mihomo v1.19.31（`-t`）、sing-box v1.14.1 与 v1.12.0（`check`）检查了 mihomo、sing-box 的全部公开配置和一份带样例节点的 sing-box 配置，都通过；另用两者的源码核对了这四份产物中的全部字段名。561 条社区来源规则已按 domain-list-community 与 blackmatrix7 的固定快照逐条核对（`docs/evidence/上游规则对照.md`）。外部意见一共 9 轮（第 2 轮是与 Cursor 版的逐条对照，第 3 轮是 Astra 的独立审核，第 4、5、6、8、9 轮是 GPT 对交付包 / 分支的独立审核，第 7 轮是 GPT 在 r12 动手之前对做法的两段评审），意见与处理见 `docs/08-外部审核记录.md`。

用真实上游数据核对过路由（2026-10-04 起）：规则原样、出口全部换成拒绝、只监听本机，把 269 个目标交给官方 mihomo v1.19.31、sing-box v1.14.1 与 v1.12.0 实际判断，结果与人工写的期望一致（其中一条是上面说的 `.ms`：期望写的就是“mihomo 上走国内直连”这个已知行为）；另核对了 DNS 去向（sing-box 22 条、mihomo ⟦mihomo_dns_n⟧ 条）、连接时的解析（两个内核各 12 条：节点服务器的名字、域名形式的直连目标、走代理组的域名、没被域名规则接住的域名，各交给哪一类 DNS）和出站时的解析（r14 加：8 个主机，走代理的出口换成真的 SOCKS / WireGuard 出口，看出口自己会不会再解析目标、交给谁）。这只对核对那一天的上游数据成立（文件的 SHA-256 记在 `tests/data/real_sets.json`），上游每天在变。Loon / Quantumult X 没有能在电脑上运行的官方内核，这两端（标准版和严格版）只有自制模拟器的结果。

“走代理的域名不交给国内 DNS”（2026-10-06 起，只说 mihomo 和 sing-box；`docs/03`）：用官方内核做了四项固定核对——走代理组的域名在规则判断时没有被任何 DNS 收到查询；没被域名规则接住的域名只问境外 DNS；把境外 DNS 换成只收不答，内核没有转去问国内或系统 DNS（只试了这一种失败方式）；出站时的解析（r14 加）：mihomo 转发 UDP、经 WireGuard 这类出口时会在本机解析目标域名，r14 起走代理的域名在这一步也只问境外 DNS（r13 时 `qwen.ai` 这类问的是国内 DNS，GPT 审核 r13 指出、核实时发现 UDP 也一样）。另把“名字会交给国内 DNS”的集合逐条取代表主机扫了一遍（逐条扫描），看路由有没有把其中哪个交给代理组：r14 两个内核都是 0 个（sing-box 17,699 个代表主机、mihomo 222,353 个）；r13 时是 sing-box 5 个、mihomo 364 个，三类分别是 `docs/06` 第 15、16、14 项，r14 都改了。这些个数只对核对那一天的上游数据和这种扫法成立，不是“全部域名”的证明。这些核对用的是本机的代理端口和替身 DNS，不是虚拟网卡；系统在虚拟网卡之外自己发的查询、浏览器自己的安全 DNS 归 `docs/01` 那张开关表管，那张表没有一项在 App 里验证过。

节点按名称分地区（2026-10-02 改为由词表生成，2026-10-04、2026-10-05 按审核意见改过，2026-10-05 交付前我自己又查了一遍、补了四处）：625 个人工写期望的节点名、CLDR 的 249 个国家 / 地区名和时区库的城市名，在 Python、ICU 正则引擎（Linux 上的 ICU 74）和 mihomo 官方内核（实际启动、从本地文件订阅取 2283 个假节点分组）上结果一致；手动组和自动类的组用的两条筛选都核对了。这些都不是真实订阅；你的订阅里每个节点的去向用 `tools/check_node_names.py` 看。

验证过的内核版本只有上面三个；Clash Verge Rev、Clash Meta for Android、SFA 内置的内核版本没有核对。这一版的检查是 ⟦run_window⟧在云端会话里跑的（Python 3.13.16；官方程序、上游数据和源码按 `handoff/setup_env.sh` 登记的版本和校验值取回），核对用的上游数据仍是 2026-10-05 发布的那一批；细节见 `docs/05`“已验证的事实”开头。

Clash 系客户端和 SFA 上有几个开关要自己确认（`docs/01`“每个客户端要手动确认的开关”；依据是源码和官方文档，没有一项在 App 里验证过）：要用虚拟网卡模式；Clash Verge Rev 的“DNS 覆写”保持关闭，Windows 上在 App 里打开“严格路由”（开完在运行时配置里核对），App 里的 IPv6 开关关掉；Android 系统设置里的“私人 DNS”选关闭。Mac 上开着 Clash Verge Rev 的虚拟网卡时，按源码推断用名字访问局域网设备（`nas.lan`）会解析不到，没有验证（`docs/06`“2026-10-07（r13）”一节）。另外，r11 加的“局域网里的节点由系统 DNS 解析”要 mihomo 内核 v1.19.20 或更新，旧内核会忽略这个字段（配置照常能用）。

Loon 和 Quantumult X 没有命令行检查工具，**没有**在任何真机上导入或实测。地区筛选正则每条 12–16 KB、每个地区两条（配置文件 Loon 约 242 KB、Quantumult X 约 404 KB，严格版各大 1–2 KB；Quantumult X 严格版另订阅约 3.5 MB 的国内大清单副本），每个策略组的行尾有图标地址，Loon 还订阅了一个格式未经官方文档确认的广告列表文件；这两个 App 上能否正常导入、分组是否正确还不知道，请先按 `docs/09-真机验收操作清单.md` 第 1 节检查，保留旧配置以便切回。**两份严格版是 r12 新增的，整份没有验证过**，要用先按 `docs/09` 第 1b 节走一遍。逐项记录见 `docs/05-验收记录.md`；上真机怎么测、怎么判断，见 `docs/09`（也可以交给能访问你电脑的 AI 按第 6 节读取 Clash 的连接记录）。
