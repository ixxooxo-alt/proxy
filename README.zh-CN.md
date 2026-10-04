# 统一分流规则与多客户端配置

[English](README.md)

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

```bash
# 订阅放在环境变量里，避免留在命令历史
export SUB_URLS='你的订阅链接'
python3 build.py                       # 公开产物在 dist/，带订阅的私密产物在 dist/private/

# sing-box（SFA）：把 Clash / mihomo 格式的订阅转换成节点
python3 build.py --singbox-sub-url "$SUB_URLS"     # 或 --singbox-nodes 下载好的订阅.yaml
```

转换器只接受能原样表达的节点：不支持的协议或参数会写进 `dist/private/sing-box-节点转换报告.txt` 并跳过，不会悄悄删参数、改协议或放宽 TLS 校验。

## 策略组怎么用

- **业务组**（OpenAI、YouTube、Telegram……）：第一项是默认出口，可以手动切到别的地区。客户端会按组名记住你的选择，重新导入或更新配置不会覆盖。
- **国外默认**：七个地区入口，默认日本。
- **地区入口**（香港、日本、韩国、台湾、新加坡、美国）：选择这个地区的工作模式，默认“手动优先”：先用你在“X·手动”里选的节点，它挂了自动换到同地区最快的节点，恢复后切回，不会跨国，也不会偷偷直连。
- **其他地区**：纯手动。
- **PayPal·美国固定**：独立挑一个美国节点，不跟随国外默认。
- **Netflix·解锁入口**：目前没有解锁验证记录，暂时按地区选择。

各端能力不完全一样（例如 sing-box 没有“手动优先”，默认改为同地区自动测速），见 `docs/02-语法依据与能力矩阵.md` 和 `docs/06-已知限制与待决事项.md`。

## 目录

```
source/                 统一源（唯一需要手改的地方）
  project.yaml          地区、模式、健康检查、DNS、局域网
  groups.yaml           业务策略组与默认出口、PayPal / Netflix 专用入口
  services/*.yaml       每个服务的规则，逐条带证据
  adblock.yaml          广告集合、自有拦截、误杀例外、HTTPDNS
  evidence.yaml         证据登记（官方文档 / 社区规则集固定快照 / 维护者知识）
  local.example.yaml    本地覆盖示例（固定节点、已验证解锁节点、自定义规则）
generator/              生成器
tests/                  测试：独立写出的期望 + 各客户端匹配语义模拟
tools/                  可选：用上游源码核对字段名；按上游规则集快照核对证据；分析 Clash 连接记录
dist/                   生成产物（公开，可分享；private/ 除外）
docs/                   需求原文与对照、说明、依据、DNS 决策、规则清单、验收记录、已知限制、真机验收操作清单
00-审核说明.md          给审核者的说明与检查重点
```

## 改规则

1. 在 `source/services/*.yaml` 里增删规则，每条写明 `ev`（证据 id）。证据写 `dlc` / `bm7-snap`（社区规则集）时，要在有上游检出目录的机器上运行 `python3 tools/check_upstream_evidence.py --dlc … --bm7 … --write` 更新核对记录，否则测试会失败；拿不出依据的写 `maintainer`。
2. `python3 build.py` 重新生成；源数据有冲突（重复归属、共享云根域、例外遮挡等）时会直接报错，不改动任何产物。
3. `python3 -m unittest discover -s tests` 跑测试。
4. 需要只属于你自己的规则、固定 PayPal 节点、登记 Netflix 已验证节点时，复制 `source/local.example.yaml` 为 `source/local.yaml` 再改，它与默认值分开，更新统一源不会覆盖。

## 验证状态

自动测试 51 项全部通过，另用 mihomo v1.19.31 与 sing-box v1.14.1 源码核对了产物中的全部字段名；490 条社区来源规则已按 domain-list-community 与 blackmatrix7 的固定快照逐条核对（`docs/evidence/上游规则对照.md`）；经过 1 轮外部审核，意见与处理见 `docs/08-外部审核记录.md`。**没有**用官方二进制做完整解析，**没有**在任何真机上导入或实测。逐项记录见 `docs/05-验收记录.md`；上真机怎么测、怎么判断，见 `docs/09-真机验收操作清单.md`（也可以交给能访问你电脑的 AI 按第 6 节读取 Clash 的连接记录）。
