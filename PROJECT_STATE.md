# 项目状态与交接

更新：2026-10-05　统一源 2026.10.05-1（r10）　生成器 1.4.0　摘要见 `dist/manifest.json`

## 已完成（有证据）

| 任务 | 状态 | 证据 |
|---|---|---|
| T1 核对四端目标版本与语法 | 已验证（文档 / 源码层面） | `docs/02-语法依据与能力矩阵.md` |
| T2 统一模型：地区、模式、业务组、专用入口、规则、例外、DNS | 已验证 | `source/`、`generator/model.py`、`tests/test_source.py` |
| T3 规则数据与逐条证据 | 已完成；社区来源已按固定快照核对 | `docs/04-规则清单与证据.md`、`docs/evidence/上游规则对照.md` |
| T4 四个生成后端 + 平台变体 | 已验证（模拟器 + 上游字段核对 + mihomo / sing-box 官方程序检查） | `dist/`、`docs/evidence/*.log`、`docs/evidence/official-check.log` |
| T5 测试：路由、结构、例外一致性、安全边界、节点转换（含负向输入）、跨平台、证据记录、连接记录分析、对照报告迁入、生成流程（回滚、写盘前检查、manifest、个人覆盖隔离）、检查脚本退出码、局域网 DNS、节点按名称分地区、真实上游数据下的路由与 DNS、版本对比工具、sing-box 拨号解析、策略组图标、Git 忽略私密文件 | 已验证（188 项；变异检查：70 类全部被发现） | `docs/evidence/tests.log`、`tools/check_mutations.py` |
| T6 导入 / 更新 / 诊断 / 回滚说明 | 已完成 | `docs/01-导入、更新、诊断与回滚.md` |
| T7 第 1 轮外部审核意见核实与处理 | 已完成（2 项修复、2 项规避、2 项待真机） | `docs/08-外部审核记录.md` |
| T8 按上游快照核对社区来源规则（审核建议 3） | 已完成：更正 19 条证据、升级 49 条维护者知识、补充 137 条上游支持的功能域名、上游广告条目四端一致 | `docs/08`“第 1 轮建议 3 的执行”、`docs/evidence/upstream-evidence-check.log` |
| T9 真机验收操作清单、Clash 连接记录分析工具 | 已完成（工具有测试；清单待执行） | `docs/09-真机验收操作清单.md`、`tools/check_connections.py` |
| T10 第 2 轮：Cursor 对照报告 + 2026-09-29 补充需求（Apple AI 组；迁入 Google 187 国家域名、M365 31 条、41 条广告、70 条国内域名、claude.app、Cursor 新登录地址；删除 / 移出 sora.com、azure.com、byteoversea 等） | 已完成（自动测试与核对工具层面） | `docs/08` 第 2 轮、`docs/evidence/cursor-迁入核对.md`、`tools/check_cursor_report.py` |
| T11 第 3 轮：Astra 独立审核 F01–F12 全部修复；2026-09-30 决定（Cursor 与 Grok 合并为 Grok 组、远程规则集跟随上游、补开发下载入口、Braintree 不进 PayPal 组） | 已完成（自动测试、变异检查、官方程序检查） | `docs/08` 第 3 轮、`docs/evidence/astra-r5/` |
| T12 节点按名称分地区改为由词表生成（2026-10-02 的要求）：`source/regions.yaml` 词表与判断顺序、四端共用的筛选正则、`local.yaml` 的本地补充、检查工具 `tools/check_node_names.py` | 已完成（Python 测试、ICU 引擎、mihomo 官方内核实际分组）；Loon / Quantumult X 未在 App 里验证 | `docs/02`“节点名称分地区”、`docs/evidence/icu-check.log`、`official-check.log`、`节点名称分组-r6与r7对比.md` |
| T13 第 4 轮：GPT 独立审核（r7）F01–F06 全部处理；2026-10-04 决定（Qwen 走国外默认；说不清落地的节点只留在手动组）。另修了自己发现的 Loon 广告列表只订阅一半的问题；mihomo 上整段 `.ms` 走国内直连这一处，r8 加过更正规则，后来按用户的决定删掉（见 T14） | 已完成（自动测试、变异检查、官方内核 + 真实上游数据核对、ICU）；Loon / Quantumult X 未在 App 里验证 | `docs/08` 第 4 轮、`docs/evidence/gpt-r7/`、`docs/evidence/real-route-check.log`、`docs/evidence/与r7的对比.md` |
| T14 r9：r8 交付后用户决定“第一个删掉吧”——删掉只写进 mihomo 的整段 `.ms` 更正规则，跟随上游。mihomo 上没有被产品规则接住的 `.ms` 域名走国内直连，作为已知行为写进文档和测试；全部检查在 r9 的代码上重跑 | 已完成（160 项测试、53 类变异、官方内核实测 `example.ms` → 国内直连）；Loon / Quantumult X、sing-box 的产物相对 r8 没有实质变化 | `docs/08`“第 4 轮之后”一节、`docs/06`“2026-10-04”一节 |
| T15 第 5 轮：GPT 独立审核（r9）F01、F02 都属实、都已处理——名字里提到的地区不在落地位置的节点（`日本中转 01`、`Premium 01 \| 解锁美国`）不再进自动类的组；sing-box 拨号时局域网里的名字改由系统 DNS 解析。另：地名和中转词之间的连接符同等对待（自己发现的）；官方记录按 sing-box 版本分开 | 已完成（自动测试、变异检查、官方内核实际分组与实际拨号、ICU）；Loon / Quantumult X 未在 App 里验证 | `docs/08` 第 5 轮、`docs/evidence/gpt-r9/`、`docs/evidence/real-route-check.log`、`docs/evidence/与上一版的对比.md`（r9 → r10） |
| T16 策略组图标（用户 2026-10-04 夜的要求：用用户图标仓库 `ixxooxo-alt/icon` 里的图）：地址写进 Loon、Quantumult X、mihomo 的配置。没有生成或修改任何图片，没有改动图标仓库 | 已完成（地址与图标仓库的检出目录逐个核对；自动测试、变异检查）；三个客户端里显示不显示未验证 | `source/icons.yaml`、`docs/02`“策略组图标”、`docs/evidence/icons-check.log` |
| T17 为放进 GitHub 仓库做准备（用户的要求：新版本放进 `ixxooxo-alt/proxy`）：`.gitignore`、英文 `README.md` + 中文 `README.zh-CN.md`（照仓库已有的摆法）、Git 忽略私密文件的测试 | 已准备好；写这份文档时**还没有放进仓库**（见下表） | `.gitignore`、`tests/test_local_and_private.py`、`docs/06` 待决事项第 13 项 |
| T18 交付前自查（2026-10-05，我自己做的，不是审核意见）：把 F01 那一类问题用没见过的写法又查了一遍，补了四处——国旗和文字用同一套“落地位置”的条件（`🇯🇵中转 01`、`IEPL 01 🇺🇸解锁`）、单个字的“港”在更长的词里不单独算（`经香港 01`、`港日中转 01`）、`via` / `经` 后面和“解锁”前面也认连字符与下划线（`via-HK-01`、`日本-解锁-01`）、连接符多认间隔号 / 句点 / 斜杠 / 破折号（`香港·中转·01`）。7 种认不出的中转写法没有改，记为已知限制 | 已完成（自动测试、变异检查、官方内核实际分组、ICU）；正则因此长了约 6%，Loon / Quantumult X 未在 App 里验证 | `docs/08` 第 5 轮“交付前自查”、`docs/06` 最后一节、`tests/node_names.yaml` 的 `known_auto_limits` |

## 待验证 / 受阻

| 任务 | 状态 | 原因 |
|---|---|---|
| **Loon / Quantumult X 导入本版配置，看策略组、图标和地区组里的节点对不对** | 待验证（最优先；这一版风险比 r7 大） | 这一版六份配置相对 r9 都变了，导入过 r9 的也要重新导入。地区筛选正则每条 12–16 KB、每个地区两条，只在 ICU 引擎上核对过；这两个 App 用的引擎、对长度的限制都没有官方说明。这一版每个策略组的行尾多了图标地址：先看 81 个策略组是不是都在（Loon 的写法依据最弱），再看图标；有问题先换成不带图标的同一版。Quantumult X 另要看“X·自动”“X·负载均衡”是否按正则取节点；Loon 另要看第二个广告列表文件是否加载出三万多条。步骤见 `docs/09` 第 1 节；出问题先切回 2026.09.30-1 的配置 |
| **把这一版放进 GitHub 仓库 `ixxooxo-alt/proxy`** | 受阻：等用户给 Claude 的 GitHub 应用授权 | 写这份文档时仓库里是 Cursor Agent 在 2026-10-05 00:35 放进去的旧版（统一源 2026.09.23-2，r4）。写这份文档时我已经在会话里申请过这个仓库：读取可以，**推送被拒绝**——Claude 的 GitHub 应用还没有被授权访问它，要你在 GitHub 上给这个仓库安装（或重新关联）这个应用，链接我在对话里发过。授权生效以后，我会把这一版直接推到 `main`、替换旧文件——这是你 2026-10-05 的决定（“main 没有用 你直接更新 main”；我原来打算先放到一个分支上等你合并，因为 `main` 上的文件可能正被客户端按地址订阅，你说明了没有在用）。做成没有，看 `main` 分支根目录 `dist/manifest.json` 的 `source_version`：`2026.10.05-1` 是这一版，`2026.09.23-2` 是旧版——还是旧版的话，从仓库地址导入的也是旧版配置：授权还没有生效，或者我没能推上去（`docs/06` 待决事项第 13 项） |
| 请审核方复核这一轮的修改 | 待进行 | 范围可以只限改动的部分；改动清单与建议攻击的点见 `00-审核说明.md` |
| 用真实订阅的节点名核对分组 | 待用户提供 | 样本是归纳的常见写法和独立来源的国家 / 城市名，不是任何一家机场的真实节点名。这一版把只写“地名 + 中转”“国旗 + 中转”的节点从自动类的组里拿掉了，用户的机场如果大多这样命名，自动组会少很多（`docs/06` 待决事项第 12 项）；反过来，规则不认识的中转说法（`经由`、`跳板`、`Entry` 等）会被当成落地放进自动组（`docs/06` 最后一节）。两头都要看真实的节点名才知道有多少。用户说以后多订阅几家再把节点列表截图发来；届时用 `tools/check_node_names.py` 核对，再补词表或 `local.yaml` |
| Windows 上重跑测试 | 待验证 | r5 已由 Astra 在 Windows（Python 3.12.13）上跑过 58/58；之后几轮改动较多，需要再跑一次 188 项。`tools/check_icu.py` 在 Windows（icu.dll）和 macOS（libicucore）上的路径没有跑过，找不到 ICU 时那一项测试会自动跳过 |
| 带真实订阅的私密配置过官方检查 | 待验证 | 公开配置和样例节点已通过 mihomo / sing-box 官方检查；真实订阅只在你的电脑上，需要你本机运行一次 |
| 十个平台真机验收（优先：QX 策略名、Loon 手动优先组成员） | 待验证 | 没有设备、订阅与账号；操作步骤见 `docs/09-真机验收操作清单.md`，记录表见 `docs/05-验收记录.md` |
| 21 条维护者知识规则的实测 | 待验证 | 两个上游快照里都没有，需要真机抓包或实测命中（清单见 `docs/evidence/上游规则对照.md`） |
| Apple AI 真机：Siri / Apple 智能走美国；地图、App Store、iCloud 同步正常 | 待验证 | 需要支持 Apple 智能的设备与地区；步骤见 `docs/09` 第 2 节 |
| 迁入的 9 条无同值上游依据的广告（尤其友盟、阿里妈妈整域拦截）是否误伤 | 待验证 | 需要在常用国内 App 上实测；见 `docs/06` 第 7 项 |
| 需求决定项 13 项 | 受阻（等待决定） | 见 `docs/06-已知限制与待决事项.md`（第 7–9 项是 2026-09-29 迁入带来的；第 10–11 项是 2026-10-04 的：Loon / QX 要不要加境外域名集合、Loon 第二个广告文件不被接受时怎么办；第 12–13 项是 2026-10-05 的：只写“地名 + 中转”的节点只进手动组这个取舍、把这一版放进 GitHub 仓库） |
| 工作环境重建后的遗留 | 已说明 | 2026-10-05 原来的云端环境被换掉，工程是按操作记录从 r5 的交付包逐步重做的（每一轮的摘要、产物、测试项数与当时的记录一致），全部检查在新环境重跑。和前几轮不同的三样：运行环境（Python 3.11.17 / PyYAML 6.0.1）、真实数据核对用的上游文件（2026-10-05 当天的）、`tests/data/cldr_tz_names.json`（重新导出，条目数相同，内容是否逐字相同无法核对）。r6–r9 的交付包如果你手里还有，以你手里的为准；我这边重做出来的 r6–r9 只用来做版本对比 |
| 定期带新下载的上游数据重跑 `tools/check_real_routes.py` | 持续 | 上游的国内 / 国外 / 广告集合每天在变；这一版的核对只对当时取得的那几份文件成立（哈希记在 `tests/data/real_sets.json`）。命令见 `docs/01` |
| 策略组图标在真机上的显示 | 待验证 | 地址已写进配置（T16）；Loon、Quantumult X、Clash Verge Rev、Clash Meta for Android 里显示不显示都没有看过。图标仓库以后改名或删图会让对应的组没有图标，更新图标仓库后重跑 `tools/check_icons.py` |

## 下一条具体操作

1. 把这一版交给审核方复核（范围：`00-审核说明.md` 列的改动）。
2. 在 Loon / Quantumult X 上导入本版配置（保留旧配置；可以先导入、再在 App 里换订阅，见 `docs/01`），按 `docs/09` 第 1 节检查：有没有报错；81 个策略组是不是都在、图标有没有出来；地区组里的节点对不对；“自动”组是不是“手动”组的一部分；Loon 的两条广告订阅是否都加载成功（看条数，再试 `app-measurement.com`）；Quantumult X 的“自动”“负载均衡”组里有没有节点。结果发回来。
3. 把订阅里的节点名交给 `python3 tools/check_node_names.py`（或把节点列表截图 / 文本发回来），按报告在 `source/local.yaml` 的 `node_names` 里补或指定，常见写法并入 `source/regions.yaml`。
4. 在 Windows 上运行 `python -m unittest discover -s tests`，确认 188 项通过。
5. 填订阅后运行 `mihomo -t -d . -f dist/private/mihomo-core.yaml`（SFA 用户再跑 `sing-box check -c dist/private/sing-box-1.14.json`），记录结果。
6. 按 `docs/09-真机验收操作清单.md` 做其余真机验收：Loon 的“香港·手动优先”成员列表、QX 带 `/`、`+` 的策略名；电脑上的分流结果用 `tools/check_connections.py` 分析。
7. 回复 `docs/06` 的待决事项（13 项），按结果修改 `source/` 并重新生成。
8. 让 GitHub 仓库的 `main` 变成这一版（待决事项第 13 项）：Claude 的 GitHub 应用的授权生效以后由我直接推到 `main`；推完以后 `main` 分支根目录 `dist/manifest.json` 的 `source_version` 应该是 `2026.10.05-1`，并确认 `dist/private/`、`source/local.yaml` 没有被传上去。如果还是 `2026.09.23-2`，说明授权没有生效、或者我没能推上去；不打算授权的话，把压缩包的内容放进仓库根目录。
