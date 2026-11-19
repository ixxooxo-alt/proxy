已完成压缩包校验，并按 00-审核说明.md 对 r22 送审稿（2026.11.18-1 / 生成器 1.13.0） 完成了代码、配置、打包验包与文档复核。
一、压缩包校验与本机自动检查结果
 * 压缩包完整性：与提供信息完全一致——650 个文件、13,643,181 字节，SHA-256 为 d61f3d1e3902d8bd73db53ca43a9db73c0d49dd2eb7285d4c5ebca1b248661af。
 * 本机检查（Linux / Python 3.11.2 / PyYAML 6.0 / ICU 72）：
   * python3 build.py --check：通过（产物与统一源一致，含 manifest.json）。
   * python3 -m unittest discover -s tests：369 项全部通过（约 265 秒）。
   * python3 tools/check_cursor_report.py：通过（533 条对齐，结果正常）。
   * python3 tools/check_icu.py --public：通过（13 条筛选正则与简易版全部节点正则在 ICU 72 与 Python 上完全一致，641 条手写期望全部符合）。
   * 未在本机运行：官方 mihomo / sing-box 二进制复测（本环境无对应二进制）、全部 248 类变异、真机验收。
二、已确认的问题
R22-F01：SubscriptionLoader 的整数正则在特定未加引号字符串上会直接崩溃或误解析
 * 严重程度：导入失败（仅影响带特定订阅生成 sing-box 私密配置）
 * 文件与位置：generator/nodes.py 第 577–596 行（SubscriptionLoader 的 tag:yaml.org,2002:int 正则与 _construct_go_int）
 * 为什么错：正则 0[xX][0-9a-fA-F_]+（以及 0b / 0o、0[0-7_]*）允许前缀后只有下划线或尾部带下划线。实测：
   * password: 0x_（或 0b_、0o_）命中整数正则后，_construct_go_int 删去 _ 得到空串，调用 int("", 16) 直接抛出 ValueError，在 load_clash_proxies() 阶段中断整份订阅加载，而不是跳过单个节点。
   * password: 0_ 被解析为整数 0（_text 写成 "0"）。
 * 依据：本机实测 yaml.load("password: 0x_", Loader=nodes.SubscriptionLoader) 抛出 ValueError: invalid literal for int() with base 16: ''；yaml.load("password: 0_", ...) 返回 int(0)。在 Go 标准库 strconv.ParseInt（go.yaml.in/yaml/v3 resolve.go 使用）中，下划线只能出现在相邻数字之间（不允许 0x_ 或尾随 _），解析失败后会回落为 !!str，mihomo 会保留原字符串。
 * 建议怎么改：收紧 int 隐式解析正则，要求下划线只能夹在合法数字中间（且 0x/0b/0o 后至少跟一个有效数字）；在 _construct_go_int 中对意外的 ValueError 回落返回原始字符串，避免单个畸形标量打断整份订阅解析。
R22-F02：SubscriptionLoader 对超过 64 位上限的未加引号数字与 mihomo / go-yaml v3 行为不一致
 * 严重程度：分流错误（低；仅影响带特定订阅生成 sing-box 私密配置）
 * 文件与位置：generator/nodes.py 第 577–596 行、第 51–57 行（_text）
 * 为什么错：Python int 无位宽上限，SubscriptionLoader 将 21 位未加引号纯数字（如 password: 123456789012345678901）解析为 int，_text() 原样输出为十进制字符串。但在 go.yaml.in/yaml/v3 中，超出 int64 / uint64 范围的数字会溢出并回落到 strconv.ParseFloat(..., 64)，mihomo 的 decodeString 会将其转成科学计数法（与 0089 同类，两边凭据不一致）。
 * 依据：本机实测 yaml.load("password: 123456789012345678901", Loader=nodes.SubscriptionLoader) 返回 int(123456789012345678901)；与 docs/08 第 22 轮 C3 所述 go.yaml.in/yaml/v3 resolve.go 先 ParseInt(64) / ParseUint(64)、失败再 ParseFloat(64) 的逻辑不一致。
 * 建议怎么改：在 _construct_go_int 中判断数值是否超出 64 位整数范围（< -(1 << 63) 或 >= (1 << 64)）；超出时转为 float（匹配 go-yaml v3），由 _text() 统一拦下并提示加引号。
R22-F03：转换器两处类型边界不一致（Hysteria2 password: 0 被误跳过；整数字段接受布尔值）
 * 严重程度：分流错误 / 建议（低；仅影响带特定订阅生成 sing-box 私密配置）
 * 文件与位置：generator/nodes.py 第 465 行（Hysteria2 密码读取），以及第 369、412、417、509、525、528 行（int(...) 强转）
 * 为什么错：
   * 第 465 行写成 pw = _take(d, used, "password") or _take(d, used, "auth")。当订阅中写了未加引号的 password: 0（Python 假值）且无 auth 时，会误判为 缺少必填字段 password 并跳过；而同文件 ss / trojan / tuic / anytls 均调用 _req()，实测 password: 0 都能正常转为 "0"。
   * Python 中 bool 是 int 的子类，直接调用 int(v) 会把 port: true、alterId: true 等布尔值静默转为 1（本机已复现），而 mihomo 的整数解码不接受布尔值。
 * 依据：本机实测 convert_one 对 hysteria2 传入 password: 0 抛 Unsupported: 缺少必填字段 password，同输入对 ss / trojan 返回 "0"；对 vmess 传入 port: True, alterId: True 返回 server_port: 1, alter_id: 1。
 * 建议怎么改：Hysteria2 改用 pw = _take(d, used, "password")，仅在 pw is None or pw == "" 时回退读取 auth；新增 _int_value(v, key) 辅助函数，显式拒绝 isinstance(v, bool)。
R22-F04：验包脚本的扫描排除未锚定路径、后缀覆盖不全，且未检查 zip 目录条目与重名条目
 * 严重程度：安全或泄漏 / 建议（低；发布验收环节）
 * 文件与位置：handoff/release/verify_package.sh 第 96–98 行；handoff/release/package_check.py 第 41–49 行
 * 为什么错：
   * verify_package.sh 第 96–97 行调用 scan 时，排除正则写的是 'tests/' 和 'tests/|SECRET123'，未锚定到行首路径（^proxy-rules/tests/）。若非测试文件中的某一行泄露了凭据且同行恰好包含 tests/ 或 SECRET123 子串，会被 grep -v -E 静默放过。
   * 第 97–98 行“令牌、密码”扫描仅 --include 了 *.conf / *.yaml / *.json / *.md，未覆盖 *.yml / *.txt / *.py / *.sh。
   * package_check.py 第 41–43 行的 unsafe 路径检查只遍历了 not i.is_dir() 的文件条目，跳过目录条目；第 49 行用字典推导收集文件内容，若 zip 含同名重复条目会静默覆盖前者。
 * 依据：handoff/release/verify_package.sh 第 86–98 行与 handoff/release/package_check.py 第 41–49 行源码。
 * 建议怎么改：排除正则改为 ^proxy-rules/tests/（SECRET123 也限定到具体样例文件或行前缀）；为“令牌、密码”扫描补上 --include='*.yml' --include='*.txt'；package_check.py 对 z.infolist() 全部条目做路径安全检查，并显式拒绝重复文件名。
R22-F05：文档中仍有 4 处遗留旧说法
 * 严重程度：文档不符
 * 文件与位置：
   * docs/01-导入、更新、诊断与回滚.md 第 20 行：仍写 这一版（r21）是 2026.10.31-1，未更新为 r22 送审稿（2026.11.18-1）或写清 main 为 r21b、本分支为 r22。
   * docs/02-语法依据与能力矩阵.md 第 132 行：写 sing-box 的两份没有任何图标字段，r20 加入简易版后实际为四份。
   * docs/05-验收记录.md 第 114 行：写 Loon、Quantumult X、Stash（各两份）、mihomo（两份）的八份产物里 81 个策略组；同页第 19、67 行已按 C8 更新为十六份，tests/test_icons.py 的 WITH_ICONS 也实际检查 16 份。
   * README.md 第 46 行：AAAA answers are off by default on mihomo, sing-box and Quantumult X (no-ipv6)，漏列了 r22 已修正为官方取值 ip-mode = v4-only 的 Loon。
 * 依据：对应文件行内容、tests/test_icons.py 第 30–32 行、dist/manifest.json（含 4 份 sing-box 配置），以及 Loon 官方通用配置文档（v4-only 行为为“仅使用 IPv4，不查询 AAAA，并拒绝 IPv6 连接”）。
 * 建议怎么改：将上述 4 处同步更新（docs/05 若保留为 r21 验收快照，至少与同页第 19、67 行口径保持一致）。
三、对“本轮请重点看”各项的逐项复核（含未照旧建议做的 5 处）
 * 三份复核（docs/08 第 21–23 轮）中未照建议做的 5 处：
   * 第 21 轮 F01（Trojan 强制开 TLS 并提示，不跳过）：合理。与 mihomo 忽略 tls 字段、始终走 TLS 的行为一致，既避免降级为明文也不丢掉可用节点，verify.py 第 272 行同步兜底。
   * 第 21 轮 F08（私密旧文件在 not_refreshed 与终端标出，不删不换目录）：合理。避免误删用户手放文件，且通过 manifest.json 的 not_refreshed 明确了来源和修改时间。
   * 第 22 轮 C1（Loon 用 ip-mode = v4-only，不加 ipv6-vif = off）：取舍合理（属推断，待真机确认）。依据 Loon 官方通用配置文档，v4-only 本身即拒绝 IPv6 连接且不查 AAAA；ipv6-vif = off 用于关闭 IPv6 VIF，在 iOS 上确有让 IPv6 流量绕过 TUN 的风险。已在 docs/06 和 docs/09 写明待双栈真机核对。
   * 第 22 轮 C3（前导零八进制）：核实准确。go.yaml.in/yaml/v3 确实按八进制解析 01234567，前一份报告的主要例子有误；但 SubscriptionLoader 仍有上面 R22-F01、R22-F02 两处边界差异需要补齐。
   * 第 22 轮 C5（“港”不把排除扩到澳加俄印土）：合理。避免误伤“深港加速”“港澳”等常见写法，且“港台 / 港臺 / 港新 / 港坡 / 港德 / 港英 / 港法 / 港欧 / 港歐”和繁体“臺中”的补丁已通过 ICU 与 Python 交叉验证。
 * 转换器是否误跳过可用节点：
   * 对照 handoff/notes/r22_draft/logs/singbox-enum-sweep.log 与 generator/nodes.py，各白名单均来自 sing-box 1.14.1 / 1.12.0 实测，未见把两个版本都接受的合法取值误拦；除 R22-F03 中 Hysteria2 的 password: 0 外，未见误跳过问题。
 * sing-box 开启 dns.reverse_mapping 的副作用：
   * 依据 sing-box 官方 DNS 文档，reverse_mapping 依赖应用先查 DNS 再建连，在系统统一代理并缓存 DNS 的环境（官方举例 macOS）中可能不准；此外多个域名共用同一真实 IP 时按最近一次解析结果反查。SFA 为 Android 环境，且 docs/03、docs/06 已如实说明上述边界与未真机验证的状态。
 * 打包与验包流程（handoff/release/）：
   * pack.py 改为仅从干净工作区的 Git 提交对象打包并拦截任意层级 private/ 与 local.yaml，verify_package.sh 改用独立 mktemp 子目录并在删除前经 package_check.py may-remove 校验路径不相交，整体能够防住 F05–F07 对应的私密泄漏与误删仓库风险；修复 R22-F04 后判定会更严密。
四、推测与待真机验证项（不计为已确认错误）
 * Loon ip-mode = v4-only 且不设 ipv6-vif 的实际表现：未在双栈真机上实测，需在定稿后按 docs/09 第 5 节“IPv6（Loon）”验证是否确实拦截 IPv6 字面地址且不绕过 TUN。
 * sing-box reverse_mapping: true 在 SFA TUN 下的 NTP 实际直连效果：目前仅基于源码与官方文档推断，需在 Android 真机日志中确认 NTP（如 time.windows.com）不再落入“国外默认”。
 * Windows 平台复测：r22 修复了 SOCKS5 接收端 FIN 关闭与 real_data.py 斜杠处理，但 369 项测试尚未在 Windows 上实跑验证。
如果您准备把这 5 处小修合并进 r22 定稿，我可以继续帮您直接核对修改后的补丁或重新跑一遍校验。
