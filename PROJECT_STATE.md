# 项目状态与交接

更新：2026-10-02　统一源 2026.10.02-1　生成器 1.2.0　摘要见 `dist/manifest.json`

## 已完成（有证据）

| 任务 | 状态 | 证据 |
|---|---|---|
| T1 核对四端目标版本与语法 | 已验证（文档 / 源码层面） | `docs/02-语法依据与能力矩阵.md` |
| T2 统一模型：地区、模式、业务组、专用入口、规则、例外、DNS | 已验证 | `source/`、`generator/model.py`、`tests/test_source.py` |
| T3 规则数据与逐条证据 | 已完成；社区来源已按固定快照核对 | `docs/04-规则清单与证据.md`、`docs/evidence/上游规则对照.md` |
| T4 四个生成后端 + 平台变体 | 已验证（模拟器 + 上游字段核对 + mihomo / sing-box 官方程序检查） | `dist/`、`docs/evidence/*.log`、`docs/evidence/official-check.log` |
| T5 测试：路由、结构、例外一致性、安全边界、节点转换（含负向输入）、跨平台、证据记录、连接记录分析、对照报告迁入、生成流程（回滚、写盘前检查、manifest、个人覆盖隔离）、检查脚本退出码、局域网 DNS、节点按名称分地区 | 已验证（125 项；变异检查 35 类全部被发现） | `docs/evidence/tests.log`、`tools/check_mutations.py` |
| T6 导入 / 更新 / 诊断 / 回滚说明 | 已完成 | `docs/01-导入、更新、诊断与回滚.md` |
| T7 第 1 轮外部审核意见核实与处理 | 已完成（2 项修复、2 项规避、2 项待真机） | `docs/08-外部审核记录.md` |
| T8 按上游快照核对社区来源规则（审核建议 3） | 已完成：更正 19 条证据、升级 49 条维护者知识、补充 137 条上游支持的功能域名、上游广告条目四端一致 | `docs/08`“第 1 轮建议 3 的执行”、`docs/evidence/upstream-evidence-check.log` |
| T9 真机验收操作清单、Clash 连接记录分析工具 | 已完成（工具有测试；清单待执行） | `docs/09-真机验收操作清单.md`、`tools/check_connections.py` |
| T10 第 2 轮：Cursor 对照报告 + 2026-09-29 补充需求（Apple AI 组；迁入 Google 187 国家域名、M365 31 条、41 条广告、70 条国内域名、claude.app、Cursor 新登录地址；删除 / 移出 sora.com、azure.com、byteoversea 等） | 已完成（自动测试与核对工具层面） | `docs/08` 第 2 轮、`docs/evidence/cursor-迁入核对.md`、`tools/check_cursor_report.py` |
| T11 第 3 轮：Astra 独立审核 F01–F12 全部修复；2026-09-30 决定（Cursor 与 Grok 合并为 Grok 组、远程规则集跟随上游、补开发下载入口、Braintree 不进 PayPal 组） | 已完成（自动测试、变异检查、官方程序检查） | `docs/08` 第 3 轮、`docs/evidence/astra-r5/` |
| T12 节点按名称分地区改为由词表生成（2026-10-02 的要求）：`source/regions.yaml` 词表与判断顺序、四端共用的筛选正则、`local.yaml` 的本地补充、检查工具 `tools/check_node_names.py` | 已完成（Python 测试、ICU 引擎、mihomo 官方内核实际分组）；Loon / Quantumult X 未在 App 里验证 | `docs/02`“节点名称分地区”、`docs/evidence/icu-check.log`、`official-check.log`、`节点名称分组-新旧对比.md` |

## 待验证 / 受阻

| 任务 | 状态 | 原因 |
|---|---|---|
| **Loon / Quantumult X 导入本版配置，看地区组里的节点对不对** | 待验证（本版最优先） | 地区筛选正则每条约 10 KB，只在 ICU 引擎上核对过；这两个 App 用的引擎、对长度的限制都没有官方说明。Quantumult X 另要看“X·自动”“X·负载均衡”是否按正则取节点。步骤见 `docs/09` 第 1 节；出问题先切回 2026.09.30-1 的配置 |
| 用真实订阅的节点名核对分组 | 待用户提供 | 样本是归纳的常见写法和独立来源的国家 / 城市名，不是任何一家机场的真实节点名。用户说以后多订阅几家再把节点列表截图发来；届时用 `tools/check_node_names.py` 核对，再补词表或 `local.yaml` |
| Windows 上重跑测试 | 待验证 | r5 已由 Astra 在 Windows（Python 3.12.13）上跑过 58/58；之后两轮改动较多，需要再跑一次 125 项。`tools/check_icu.py` 在 Windows（icu.dll）和 macOS（libicucore）上的路径没有跑过，找不到 ICU 时那一项测试会自动跳过 |
| 带真实订阅的私密配置过官方检查 | 待验证 | 公开配置和样例节点已通过 mihomo / sing-box 官方检查；真实订阅只在你的电脑上，需要你本机运行一次 |
| 十个平台真机验收（优先：QX 策略名、Loon 手动优先组成员） | 待验证 | 没有设备、订阅与账号；操作步骤见 `docs/09-真机验收操作清单.md`，记录表见 `docs/05-验收记录.md` |
| 21 条维护者知识规则的实测 | 待验证 | 两个上游快照里都没有，需要真机抓包或实测命中（清单见 `docs/evidence/上游规则对照.md`） |
| Apple AI 真机：Siri / Apple 智能走美国；地图、App Store、iCloud 同步正常 | 待验证 | 需要支持 Apple 智能的设备与地区；步骤见 `docs/09` 第 2 节 |
| 迁入的 9 条无同值上游依据的广告（尤其友盟、阿里妈妈整域拦截）是否误伤 | 待验证 | 需要在常用国内 App 上实测；见 `docs/06` 第 7 项 |
| 需求决定项 9 项 | 受阻（等待决定） | 见 `docs/06-已知限制与待决事项.md`（第 7–9 项是 2026-09-29 迁入带来的） |
| 策略组图标 | 未开始（按用户要求暂缓） | 用户说等最终版定版、审核完再生成；本轮没有生成。届时待定：图标来源与风格，以及图标集里没有的几个业务组怎么处理 |

## 下一条具体操作

1. 在 Loon / Quantumult X 上导入本版配置（保留上一版），按 `docs/09` 第 1 节检查：有没有报错、地区组里的节点对不对、Quantumult X 的“自动”“负载均衡”组成员是否和“手动”相同。结果发回来。
2. 把订阅里的节点名交给 `python3 tools/check_node_names.py`（或把节点列表截图 / 文本发回来），按报告在 `source/local.yaml` 的 `node_names` 里补，常见写法并入 `source/regions.yaml`。
3. 在 Windows 上运行 `python -m unittest discover -s tests`，确认 125 项通过。
4. 填订阅后运行 `mihomo -t -d . -f dist/private/mihomo-core.yaml`（SFA 用户再跑 `sing-box check -c dist/private/sing-box-1.14.json`），记录结果。
5. 按 `docs/09-真机验收操作清单.md` 做其余真机验收：Loon 的“香港·手动优先”成员列表、QX 带 `/`、`+` 的策略名；电脑上的分流结果用 `tools/check_connections.py` 分析。
6. 回复 `docs/06` 的待决事项，按结果修改 `source/` 并重新生成。
7. 交给审核：审核说明见 `00-审核说明.md`（含本轮变更与重点）。
8. 图标：等用户确认最终版之后再做。
