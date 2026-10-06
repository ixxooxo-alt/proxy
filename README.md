# 统一分流规则与多客户端配置

> 审核者请先读 `00-审核说明.md`。

一份自有、可审计、可测试的规则源（`source/`），由生成器（`generator/`）同时产出 Loon、Quantumult X、mihomo（Clash Verge Rev / Clash Meta for Android / 内核）和 sing-box（SFA）的配置。四个客户端不各自手写，改规则只改 `source/`，再重新生成。

## 直接用：拿哪个文件

| 设备 / 客户端 | 文件 | 使用前要做的事 |
|---|---|---|
| iPhone / iPad / Mac：Loon | `dist/loon/loon.conf` | 把 `[Remote Proxy]` 里的占位链接换成你的订阅 |
| iPhone / iPad / Mac：Quantumult X | `dist/quantumultx/quantumultx.conf` | 把 `[server_remote]` 里的占位链接换成你的订阅 |
| Windows / macOS：Clash Verge Rev | `dist/mihomo/mihomo-profile.yaml` | 把 `proxy-providers` 的 `url` 换成你的订阅 |
| Android：Clash Meta for Android | `dist/mihomo/mihomo-profile.yaml` | 同上 |
| Linux / 路由器：mihomo 内核直接运行 | `dist/mihomo/mihomo-core.yaml` | 同上；含本机端口与控制面，TUN 默认关闭 |
| Android：SFA（sing-box） | 需要在本机生成（见下） | sing-box 不支持订阅，节点必须写进配置 |

占位链接是 `https://REPLACE-ME.invalid/请替换为你的订阅链接`，不替换就无法使用。订阅链接属于私密信息，不要写回 `source/`，也不要把替换后的文件发给别人。

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
- **Apple AI**：Apple 智能、Siri、iCloud 专用代理，默认美国（可切到其他支持 Apple 智能的地区，没有 DIRECT）；规则排在 Apple 组之前。Apple 地图 / 定位的一部分、App Store 图片、CloudKit 也会跟着这组走，见 `docs/06` 第 8 项。
- **地区入口**（香港、日本、韩国、台湾、新加坡、美国）：选择这个地区的工作模式，默认“手动优先”。设计目标是：先用你在“X·手动”里选的节点，它挂了换到同地区可用的节点，恢复后切回，不跨国，也不偷偷直连。mihomo 按这个设计生成；Loon 的组嵌套、Quantumult X 的恢复切回、各端实际多久切换，都还没在真机上确认（见 `docs/06`）。
- **其他地区**：纯手动。落地在其他国家的节点、名字里认不出地区的节点都在这里。
- **节点怎么分到地区**：只看节点名字（国旗、地名、城市、代码），按 `source/regions.yaml` 的词表和固定顺序判断：中转 / 入口位置的地名不算落地，“剩余流量”“到期”这类提示行不进任何组，说不清落地的同时进两个组。它不证明节点实际从哪里出去。想知道自己订阅里每个节点进了哪个组、为什么，用 `python3 tools/check_node_names.py`；分错或没认出来的在 `source/local.yaml` 里补（见 `docs/01`“节点按名称分地区”）。
- **PayPal·美国固定**：独立挑一个美国节点，不跟随国外默认。
- **Netflix·解锁入口**：目前没有解锁验证记录，暂时按地区选择。

各端能力不完全一样（例如 sing-box 没有“手动优先”，默认改为同地区自动测速），见 `docs/02-语法依据与能力矩阵.md` 和 `docs/06-已知限制与待决事项.md`。

## 目录

```
source/                 统一源（唯一需要手改的地方）
  project.yaml          地区的工作模式、健康检查、DNS、局域网
  regions.yaml          按节点名称分地区：六个地区与其他国家的词表、信息节点的词、中转词与判断顺序
  groups.yaml           业务策略组与默认出口、PayPal / Netflix 专用入口
  services/*.yaml       每个服务的规则，逐条带证据
  adblock.yaml          广告集合、自有拦截、误杀例外、HTTPDNS
  evidence.yaml         证据登记（官方文档 / 社区规则集固定快照 / 维护者知识）
  local.example.yaml    本地覆盖示例（固定节点、已验证解锁节点、自定义规则、节点名称的本地补充）
generator/              生成器
tests/                  测试：独立写出的期望 + 各客户端匹配语义模拟
tools/                  check_node_names.py：看一批节点名各进哪个地区组、为什么
                        可选：官方程序检查（含 mihomo 内核实际分组）；ICU 正则核对；用上游源码核对字段名；按上游规则集快照核对证据；
                        对照 Cursor 版报告核对迁入；变异检查；分析 Clash 连接记录；节点分组新旧对比
dist/                   生成产物（公开，可分享；private/ 除外）
docs/                   需求原文与对照、说明、依据、DNS 决策、规则清单、验收记录、已知限制、真机验收操作清单
00-审核说明.md          给审核者的说明与检查重点
```

## 改规则

1. 在 `source/services/*.yaml` 里增删规则，每条写明 `ev`（证据 id）。证据写 `dlc` / `bm7-snap`（社区规则集）时，要在有上游检出目录的机器上运行 `python3 tools/check_upstream_evidence.py --dlc … --bm7 … --write` 更新核对记录，否则测试会失败；拿不出依据的写 `maintainer`。
2. `python3 build.py` 重新生成；源数据有冲突（重复归属、共享云根域、例外遮挡、拼错的字段、重复的键、引用不存在的组等）时会直接报错，不改动任何产物。
3. `python3 -m unittest discover -s tests` 跑测试；或 `bash tools/run_checks.sh` 一次跑完生成、测试和各项核对，任何一步失败都以非零退出码结束。
4. 需要只属于你自己的规则、固定 PayPal 节点、登记 Netflix 已验证节点、给某家机场特有的节点名补地区时，复制 `source/local.example.yaml` 为 `source/local.yaml` 再改，它与默认值分开，更新统一源不会覆盖。
5. 改地区的关键词：改 `source/regions.yaml` 的词表（不要手写正则，四端的筛选都由生成器拼出）。同一个词不能出现在两个地区；纯英文的词放 `latin`。改完跑测试：每个词都必须归它所在的地区，其他国家的名称不能被认成六个地区之一。

## 验证状态

自动测试 125 项全部通过。官方程序 mihomo v1.19.31（`-t`）、sing-box v1.14.1 与 v1.12.0（`check`）检查了全部公开配置和一份带样例节点的 sing-box 配置，都通过；另用两者的源码核对了产物中的全部字段名。554 条社区来源规则已按 domain-list-community 与 blackmatrix7 的固定快照逐条核对（`docs/evidence/上游规则对照.md`）。经过 3 轮外部审核（第 2 轮是与 Cursor 版的逐条对照，第 3 轮是 Astra 的独立审核），意见与处理见 `docs/08-外部审核记录.md`。

节点按名称分地区（2026-10-02 改为由词表生成）：498 个人工写期望的节点名、CLDR 的 249 个国家 / 地区名和时区库的城市名，在 Python、ICU 正则引擎（Linux 上的 ICU 74）和 mihomo 官方内核（实际启动、从本地文件订阅取 2158 个假节点分组）上结果一致。这些都不是真实订阅；你的订阅里每个节点的去向用 `tools/check_node_names.py` 看。

Loon 和 Quantumult X 没有命令行检查工具，**没有**在任何真机上导入或实测。这一版的地区筛选正则比上一版长很多（每条约 10 KB），这两个 App 上能否正常导入、分组是否正确还不知道，请先按 `docs/09-真机验收操作清单.md` 第 1 节检查，保留上一版配置以便切回。逐项记录见 `docs/05-验收记录.md`；上真机怎么测、怎么判断，见 `docs/09`（也可以交给能访问你电脑的 AI 按第 6 节读取 Clash 的连接记录）。
