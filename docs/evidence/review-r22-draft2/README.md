Ran fetch and checkout commit 8558a27 and check disk space

I am fetching commit `8558a27` from `claude/r12-gpt-review-handling-q4onlv` and checking the environment before starting the audit of the r22 second review draft.

Analyzed 00-审核说明.md:L1-184
Ran diff f60ee42..8558a27 and list review archives and draft2 logs
Ran find section line numbers in docs/00 and docs/08
Analyzed 08-外部审核记录.md:L826-980
Analyzed 00-需求原文.md:L1418-1562
Analyzed README.md:L1-184
Analyzed README.md:L1-68
Analyzed README.txt:L1-29
Ran check git log, diff stat, and Python 3.12 · Exited with code 1
Analyzed nodes.py:L1-450
Analyzed verify_package.sh:L1-144
Analyzed package_check.py:L1-121
Analyzed selftest_package.py:L1-192
Analyzed nodes.py:L451-948
Analyzed pack.py:L1-130
Analyzed model.py:L1-800
Analyzed verify.py:L1-758
Analyzed r22b_review_probes.py:L1-232
Analyzed model.py:L740-878
Analyzed verify.py:L680-758
Analyzed ai.yaml:L1-289
Analyzed adblock.yaml:L1-179
Analyzed regions.yaml:L1-238
Ran inspect diff of emitters, audit, strict, source files
Analyzed check_mutations.py:L1-320
Analyzed check_mutations.py:L580-900
Analyzed regions.py:L1-800
Analyzed project.yaml:L1-135
Analyzed regions.py:L740-1116
Analyzed check_mutations.py:L900-997
Analyzed check_mutations.py:L320-580
Analyzed run_quick.sh:L1-87
Analyzed README.md:L1-60
Ran setup clean Python 3.12 venv and run build/mutation edit checks
Analyzed test_nodes.py:L250-600
Analyzed test_run_checks.py:L1-125
Analyzed test_build_pipeline.py:L220-500
Analyzed r22b_private_vs_r22draft.py:L1-246
Checked task Setup clean Python 3.12 venv and run build/mutation edit checks
Analyzed test_nodes.py:L595-637
Ran install PyYAML in Python 3.12 venv and inspect draft2 log headers
Analyzed 06-已知限制与待决事项.md:L1-320
Analyzed 06-已知限制与待决事项.md:L321-454
Created audit_checks.py
Ran run static audit script for mutations, lan, regions, real_sets · Exited with code 1
Ran clean up temp dirs and prepare D:\audit_tmp
Ran run audit_checks.py, build.py --check, and check_cursor_report.py
Checked task Run audit_checks.py, build.py --check, and check_cursor_report.py
Searched "160.79.104.0/23" "153.61.224.0/22" "2607:6bc0::/48" anthropic OR claude ip addresses
Searched site:docs.stripe.com "r.stripe.com" OR "m.stripe.com" OR "m.stripe.network" domains firewall
Searched site:trust.anthropic.com subprocessors OR "trust.anthropic.com/subprocessors"
Analyzed output.txt:L40-114
Ran run full 383-test unittest suite on Python 3.12
Ran run check_icu.py and selftest_package.py
Ran fetch pinned go-yaml v3.0.5 and mihomo v1.19.31 source files
Analyzed go_yaml_resolve.go:L1-326
Analyzed mihomo_structure.go:L1-627
Analyzed go_yaml_decode.go:L650-900
Analyzed mihomo_provider.go:L150-350
Analyzed go_yaml_decode.go:L900-1018
Analyzed mihomo_provider.go:L350-468
Analyzed r22_singbox_enum_sweep.py:L1-125
Checked task Run check_icu.py and selftest_package.py
Checked task Run full 383-test unittest suite on Python 3.12
Ran check mihomo v1.19.31 outbound and uTLS implementations
Ran fetch pinned sing-box v1.14.1 outbound and uTLS source files
Analyzed sb114_vmess.go:L1-212
Analyzed sb114_utls.go:L1-250
Analyzed sb114_tuic.go:L1-151
Checked task Run full 383-test unittest suite on Python 3.12
Analyzed sb114_utls.go:L251-398
Analyzed sb114_vless.go:L1-224
Ran verify sing-box reverse_mapping and upstream adblock lists for Sentry/Claude hosts
Checked task Verify sing-box reverse_mapping and upstream adblock lists for Sentry/Claude hosts
Checked task Run full 383-test unittest suite on Python 3.12
Created audit_docs.py
Ran run doc consistency and log numbers audit script
Analyzed output.txt:L20-218
Checked task Verify sing-box reverse_mapping and upstream adblock lists for Sentry/Claude hosts
Checked task Run full 383-test unittest suite on Python 3.12
Ran download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Analyzed 03-DNS决策表.md:L1-300
Analyzed README.zh-CN.md:L1-163
Analyzed PROJECT_STATE.md:L1-103
Searched "cdn.sift.com" OR "cdn.siftscience.com" OR "beacon.sift.com" sift javascript snippet domain
Searched "platform.claude.com/docs/en/api/ip-addresses" OR "docs.anthropic.com" "160.79.104.0/23" "153.61.224.0/22"
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Analyzed README.md:L1-157
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Ran check dist counts vs docs/03 & docs/04, and run check_mutations --check-edits
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Checked task Check dist counts vs docs/03 & docs/04, and run check_mutations --check-edits
Ran check nature: shared usage and task-504 counts
Ran audit all non-test-name expect strings in check_mutations.py
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Checked task Check dist counts vs docs/03 & docs/04, and run check_mutations --check-edits
Ran inspect M99, M111, M128, M177, M185 in tests and r21 mutations.log
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Checked task Check dist counts vs docs/03 & docs/04, and run check_mutations --check-edits
Ran detect silent no-op chained .replace() calls across all 272 mutations
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Checked task Check dist counts vs docs/03 & docs/04, and run check_mutations --check-edits
Created audit_packaging_and_nodes.py
Ran run packaging, nodes, timestamp, and shadowing edge-case tests
Listed 2 tasks
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Analyzed task-528.log:L1-64
Killing task Download Windows mihomo v1.19.31 and sing-box 1.14.1 binaries to D:\audit_tmp\bins
Canceled download Windows mihomo and sing-box binaries via curl
Ran test model.py shadowing for project.yaml lan.domain_suffix
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo and sing-box binaries via curl
Ran test model.py shadowing for project.yaml lan.domain_suffix
Ran test model.py shadowing with extra_services in local.yaml
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download Windows mihomo and sing-box binaries via curl
Killed task Download Windows mihomo and sing-box binaries via curl
Ran verify model.py shadowing bug on project.yaml lan.domain_suffix
Canceled download mihomo and sing-box binaries with OpenSSL curl
Ran verify model.py shadowing bug on project.yaml lan.domain_suffix
Checked task Run full 383-test unittest suite on Python 3.12
Checked task Download mihomo and sing-box binaries with OpenSSL curl
Ran confirm foo.localhost and 10.1.2.3/32 bypass model.py fixed-direct shadowing check · Exited with code 1
Ran list skipped Windows tests and confirm model.py lan shadowing gap · Exited with code 1
Checked task Download mihomo and sing-box binaries with OpenSSL curl
Ran get exact skipped test names and confirm model.py lan shadowing gap · Exited with code 1
Ran check emitted DNS and route rules for foo.localhost and 10.1.2.3/32 · Exited with code 1
Checked task Download mihomo and sing-box binaries with OpenSSL curl
Killed task Download mihomo and sing-box binaries with OpenSSL curl
Canceled download mihomo and sing-box binaries with resume and 300s timeout
Ran inspect generated DNS and route rules for foo.localhost and 10.1.2.3/32 · Exited with code 1
Ran confirm DNS vs route split on foo.localhost and 10.1.2.3/32 · Exited with code 1
Ran check check_mutations CLI flags and test selftest_package with PYTHONUTF8=1
Ran verify sing-box and mihomo output for foo.localhost and 10.1.2.3/32 · Exited with code 1
Canceled run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Check check_mutations CLI flags and test selftest_package with PYTHONUTF8=1
Ran confirm DNS vs route split on foo.localhost and 10.1.2.3/32
Checked task Download mihomo and sing-box binaries with resume and 300s timeout
Analyzed selftest_package.py:L1-45
Checked task Download mihomo and sing-box binaries with resume and 300s timeout
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Ran check Python UTF-8 mode vs -I encoding and binary download progress
Ran test selftest_package.py on Windows without PYTHONUTF8
Analyzed check_mutations.py:L740-970
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Test selftest_package.py on Windows without PYTHONUTF8
Ran check test coverage of new Claude third-party hosts and Anthropic IPs
Checked task Download mihomo and sing-box binaries with resume and 300s timeout
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Test selftest_package.py on Windows without PYTHONUTF8
Ran check all new Claude third-party hosts against upstream adblock lists and real_sets.json
Ran check real_sets.json adblock membership for all new Claude hosts
Checked task Download mihomo and sing-box binaries with resume and 300s timeout
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Test selftest_package.py on Windows without PYTHONUTF8
Ran check download progress and domain-list-community ad lists for new Claude hosts
Killed task Download mihomo and sing-box binaries with resume and 300s timeout
Canceled download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Analyzed 06-已知限制与待决事项.md:L330-420
Analyzed r22b_review_probes.py:L1-232
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Test selftest_package.py on Windows without PYTHONUTF8
Checked task Download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Analyzed nodes.py:L250-495
Analyzed nodes.py:L496-715
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Analyzed nodes.py:L180-250
Analyzed 08-外部审核记录.md:L750-900
Analyzed package_check.py:L1-121
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Ran verify commit timestamps and check binary download progress
Analyzed verify_package.sh:L1-120
Analyzed verify_package.sh:L121-144
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Analyzed selftest_package.py:L45-192
Ran check r22_draft2 logs for sensitive paths and check binary download progress
Checked task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Analyzed check_mutations.py:L1-145
Ran check sing-box release download headers and active mutation temp dirs
Analyzed check_mutations.py:L245-280
Killed task Run targeted mutations M46 M52 M249 M262 M268 with skip-baseline
Checked task Download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Ran run mutation check M249 with skip-baseline
Ran run mutation check M262 with skip-baseline
Ran run mutation check M268 with skip-baseline
Ran check binary download sizes in D:\audit_tmp\bins
Ran fetch and inspect pinned sing-box v1.14.1 option Go structs
Killed task Download sing-box 1.14.1 and mihomo v1.19.31 with stall detection and retry
Ran list fetched upstream Go source files
Checked task Fetch and inspect pinned sing-box v1.14.1 option Go structs
Checked task List fetched upstream Go source files
Analyzed go_yaml_resolve.go:L160-326
Analyzed sb_opt_v2ray.go:L1-115
Analyzed sb_opt_tuic.go:L1-35
Analyzed sb_opt_vmess.go:L1-30
Analyzed sb_opt_ss.go:L1-35
Analyzed nodes.py:L740-890
Analyzed go_yaml_resolve.go:L1-160
Analyzed sb114_tuic.go:L1-120
Analyzed sb114_ss.go:L1-120
Analyzed nodes.py:L1-180
Analyzed mihomo_structure.go:L160-280
Analyzed mihomo_provider.go:L375-440
Ran check Go stdlib time/format.go exact parsing rules for timestamps
Analyzed go_time_format.go:L1150-1350
Analyzed mihomo_structure.go:L110-165
Analyzed go_time_format.go:L1130-1155
Analyzed go_time_format.go:L1450-1510
Analyzed go_yaml_decode.go:L760-795
Analyzed go_yaml_decode.go:L905-960
Checked task Run mutation check M249 with skip-baseline
Checked task Run mutation check M262 with skip-baseline
Checked task Run mutation check M268 with skip-baseline
Ran verify 1e-500 underflow, uncaught transport exceptions, and M46/M52 partial no-ops
Analyzed ai.yaml:L20-175
Analyzed 03-DNS决策表.md:L20-60
Analyzed 03-DNS决策表.md:L165-185
Analyzed README.txt:L1-29
Analyzed 04-规则清单与证据.md:L75-170
Checked task Run mutation check M249 with skip-baseline
Checked task Run mutation check M262 with skip-baseline
Checked task Run mutation check M268 with skip-baseline
Timed 10m

正在等待并行运行的 3 项抽样变异检查（`M249`、`M262`、`M268`）完成，完成后清理临时文件并输出完整审核报告。

Checked task Run mutation check M262 with skip-baseline
Checked task Run mutation check M268 with skip-baseline
Ran verify repo cleanliness, confirm exact doc line numbers, and clean up D:\audit_tmp
Analyzed output.txt:L1-38

## 总结论

- **审核对象**：`ixxooxo-alt/proxy` 分支 `claude/r12-gpt-review-handling-q4onlv` 提交 `8558a2783c670a923974c1ec688d43bbc688a484`（`8558a27`，r22 第二份送审稿；对照第一份送审稿 `f60ee42` 与 `main` 上的 r21b `a6671c1`）。
- **总体判断**：**暂不建议直接定稿；建议先修复本轮查出的高/中优先级代码缺陷与文档事实错误，再跑全套 272 类变异与 `tools/run_checks.sh`。**
  - **25 个公开产物**：未发现确定的导入失败、默认分流错误或凭据/订阅泄漏；`build.py --check`、383 项测试（Windows 下 380 通过、3 项因无 `/proc/net/udp` 跳过）、Windows `icu.dll` 校验、272 类变异编辑检查及抽跑的 `M249`、`M262`、`M268` 均通过。
  - **私密 SFA 节点转换（已确认，导入失败 / 分流偏差）**：`generator/nodes.py` 对 `name`、`server` 未经 `_text()` 直接 `str()`，不会按 `r22b_review_probes.py` 所宣称的那样跳过小数/日期/布尔节点；更严重的是 `alpn`、`ws-opts`/`grpc-opts`/`h2-opts`/`http-opts` 的路径/请求头/主机、以及 `tuic` 的 `udp-relay-mode` 会将 YAML 读出的数字/布尔原样写入 sing-box JSON，且 `generator/verify.py` 未拦截，按 sing-box v1.14.1 源码（强类型 `string` / `badoption.Listable[string]` / `uint32`）会导致整份私密 SFA 配置反序列化失败、无法启动。
  - **规则规划与节点分地区（已确认，条件性分流/DNS 退步）**：
    1. `generator/model.py` 的 `build_plan()` 在用 `lan_keys` 去重 `real_ip_direct` 时未按客户端过滤，若 `local.yaml` 为单一客户端定义了含 `dns.real_ip` 域名（如 `time.windows.com`）的 `DIRECT` 服务，会令其余 4 个客户端丢失该域名的固定直连；
    2. `R22-F06` 固定直连遮挡检查漏了 `project.yaml` 的 `lan.domain_suffix`（特别是未出现在 `dns.real_ip` 里的 `localhost`）与 `lan.ip_cidr`，导致 `foo.localhost -> 国外默认` 在 mihomo 上重现“路由走直连、DNS 走境外”分裂；
    3. `source/regions.yaml` 将 `港德/港英/港法/港欧/港歐` 从 `words` 移入 `patterns` 后，受 `generator/regions.py` 将所有 `patterns` 标为非国名（`core=False`）的影响，这五个词被静默降级为“城市一级”，导致 `港德-日本 01`、`美国 港英 01` 等原本该归“其他地区”的节点错误落入目标地区手动组。
  - **Claude 组新增第三方规则（规则取舍与文档事实）**：Anthropic 官方 IP 段核实准确，排除 Sentry、`34.8.0.0/16`、`fcmtoken.googleapis.com` 和 `us5.datadoghq.com` 整段后缀的判断扎实；但 **`docs/06` 第 374 行对 3 段 Anthropic IP “不会为了匹配去解析域名”的说法在 Quantumult X 标准版上不成立**（QX 无 `no-resolve`，且这 3 条排在 Telegram IP 段之前）；此外 `r.stripe.com` 与其余 Stripe 支付/风控域名、Intercom 两主机与其余 Intercom 主机被拆在不同策略组，切换 Claude 地区时存在跨地区拆分风险；全部 11 条新第三方共用规则在 `source/services/ai.yaml` 中缺 `nature: shared` 而在 `docs/04` 被标成“专属”。
  - **发布验包与变异检查工具（已确认）**：`package_check.py unpack` 对空目录条目（甚至 `proxy-rules/dist/private/`、`.git/`、`extra-dir//`）放行并返回 0，且遇到坏 CRC 未提前返回而抛出未捕获 `zipfile.BadZipFile`；`selftest_package.py` 在中文 Windows 上无论是否设置 `PYTHONUTF8=1` 均因 `-I` 与 `bash` 编码冲突直接崩溃；`check_mutations.py` 的 `judge()` 在文档声明支持的 Python 3.10 下必然误判 `M177`、`M185` 为“未发现”，且 `M46`/`M52` 存在链式 `.replace()` 静默半失效（`--check-edits` 查不出来），以及未忽略 `.git` 导致 Windows 临时目录大量泄漏。

---

## 一、五个重点检查领域的核实结论

### 1. 第 24、25 轮审核的核实与处理（含三处未照建议修改与交稿前自查）

- **三处未照审核建议做的决定——均经上游固定版本源码核对，判断成立**：
  1. **`R22-F09`（VMess `auto` + TLS 写明 `aes-128-gcm`，不跳过）**：核对 `SagerNet/sing-box@v1.14.1` `protocol/vmess/outbound.go:95-102`（`security == "auto" && outbound.tlsConfig != nil` 改写为 `"zero"`）与 `MetaCubeX/mihomo@v1.19.31` `adapter/outbound/vmess.go:476,485`（经 `sing-vmess` 在 amd64/arm64 选 `aes-128-gcm`）。考虑到订阅中 `cipher: auto` + TLS 极常见，显式写 `aes-128-gcm`、在报告提示并用 `verify.py` 拦 `auto+TLS` 是合理取舍（`verify.py` 也已按白名单拦住显式空字符串 `security: ""`）。
  2. **`R22-F11`（保留五个旧版 Chrome uTLS 别名并在报告说明）**：核对 `SagerNet/sing-box@v1.14.1` `common/tls/utls_client.go:371-376`（五者 `fallthrough` 至 `HelloChrome_Auto`）与 `MetaCubeX/mihomo@v1.19.31` `component/tls/utls.go:95-99`（标注 deprecated）。节点可正常连通，保留并在报告注明比直接跳过更合理。
  3. **第 24 轮 `F01`（不按 Go 字面量收紧下划线，而是照 `go-yaml v3.0.5` 先去掉下划线）**：核对 `yaml/go-yaml@v3.0.5` `resolve.go:191-209`（`plain := strings.Replace(in, "_", "", -1)` 后再调用 `strconv.ParseInt`/`ParseUint`/`ParseFloat`）。作者没有照搬“下划线只能在数字中间”的建议是正确的，`0_`、`1__0`、`0x1_` 确实与 `go-yaml` 一致。
- **其余关键处理与交稿前自查的复核**：
  - `R22-F04`（`reverse_mapping` 记 A/AAAA 的 `Hdr.Name`，CNAME 场景认回别名）：核对 `SagerNet/sing-box@v1.14.1` `dns/router.go:1122-1135`，属实且文档收窄准确。
  - `R22-F13` 交稿前自查（重复键改为构树后、合并展开前，仅查最外层及 `proxies`）：核对 `yaml/go-yaml@v3.0.5` `decode.go:768-783, 878-953` 与 `MetaCubeX/mihomo@v1.19.31` `adapter/provider/provider.go:384`，方向正确；仅留一处极小边界差异（见下节 F-N3）。
  - **存在漏修/引入退步的条目**：`R22-F05` 漏了 `build_plan()` 里的 `lan_keys`（F-R1）；`R22-F06` 漏了 `project.yaml` 的 `lan.domain_suffix` / `lan.ip_cidr`（F-R2）；`R22-F15` 引入了五词降级为城市词的退步（F-R3）；`R22-F12` 漏了 `name`/`server` 与多处传输/TLS 字段的 `_text()` 校验（F-I1、F-I2）；`R22-F03` 漏查空目录条目与坏 CRC 提前返回（F-T1、F-T2）；`R22-F16` 的 `judge()` 未兼容 Python 3.10（F-T4）。

### 2. 订阅读法（`generator/nodes.py`）与 `r22b_review_probes.py` 的充分性

- **`go_plain_scalar` / `_go_timestamp` / `_go_parse_int` / `_go_int` 与 `go-yaml v3.0.5`、`mihomo v1.19.31` 核对**：
  - 经核对 `yaml/go-yaml@v3.0.5` `resolve.go:169-326` 与 Go 标准库 `time/format.go:1142-1325, 1526-1538`：时间戳 1–2 位小时、时区 `hr > 24 / mm > 60`、超过 9 位小数秒截断等细节，`nodes.py` 的实现与 Go 运行时保持了一致。
  - **仍存在的真实差异**：
    1. **浮点下溢**：`1e-500`（或 `1e-324`）在 Go `strconv.ParseFloat` 返回 `ErrRange`（下溢到 0），`go-yaml` 留作字符串；`nodes.py` 的 `_go_float()`（[generator/nodes.py#L843-L849](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/nodes.py#L843-L849)）只判 `math.isinf(f)`，实测把 `1e-500` 读成了 `float 0.0`。
    2. **`proxy-providers` 对非字符串 `name` 的严格校验**：`mihomo@v1.19.31` `adapter/provider/provider.go:416-423` 对 `mapping["name"]` 直接做 `name, ok := mName.(string); if !ok { continue }`，订阅中任何未加引号的数字/布尔/小数/日期 `name` 在 `proxy-providers` 里都会被静默丢弃（与顶层 `proxies:` 走 `structure.Decoder` 弱类型转字符串不同）。
    3. **顶层 `<<` 合并被同层 `proxies:` 覆盖时的重复键**：`go-yaml@v3.0.5` `decode.go:915-920` 通过 `mergedFields` 跳过被覆盖的 `*base.proxies`，而 `duplicate_keys()`（[generator/nodes.py#L781-L793](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/nodes.py#L781-L793)）仍递归检查 `*base.proxies`（实测触发误拒）。
- **`handoff/notes/r22b_review_probes.py` 的核对盲区（不够充分）**：
  1. 第 1 部分（[r22b_review_probes.py#L138-L152](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/notes/r22b_review_probes.py#L138-L152)）只把 `SCALARS`/`DATES` 交给 `nodes.go_plain_scalar()`，**从未调用 `nodes.convert()`**，却在输出文案中宣称“转换器也读成小数/日期（跳过节点）”——正好掩盖了 `convert_one()` 对 `name`/`server` 直接 `str()` 而未跳过节点的缺陷。
  2. 第 1 部分用顶层 `proxies:` 而不是 `proxy-providers` 测 `name`，未覆盖 `provider.go:420` 仅接受 `string` 的行为。
  3. 第 3、4 部分没有把 `nodes.convert()` 产出的整份 JSON 喂给 `sing-box check`，漏测了 `alpn`、`ws-opts`/`grpc-opts`/`h2-opts`/`http-opts`、`tuic.udp-relay-mode`、负整数等非字符串/越界字段。

### 3. 发布与验包工具（`verify_package.sh`、`package_check.py`、`selftest_package.py`）

- **“对不上就不运行包里的程序”**：核查 [verify_package.sh#L61-L90](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/release/verify_package.sh#L61-L90)，当 `package_check.py unpack` 返回非 0 时 `SAME=no`，确实跳过了 `$P/build.py` 与 `$P/tests`；且调用 `package_check.py` 使用了 `python3 -I` 隔离模块路径。**但存在一条空目录穿透路径**：`package_check.py` 忽略全部目录条目，构造包含额外空目录（包括 `proxy-rules/dist/private/`、`proxy-rules/.git/`、`proxy-rules/extra-dir//`）的包会令 `unpack` 返回 0（`SAME=yes`）并将这些空目录解出到磁盘（见 F-T1）。
- **测试判据**：[verify_package.sh#L84-L88](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/release/verify_package.sh#L84-L88) 改看退出码、`Ran N tests`（`N > 0`）和 `^OK( \(.*\))?$`，确实修复了 `R22-F02` 无 `PYTHONUNBUFFERED` 时的误判。但 `^OK( \(.*\))?$` 对 `skipped` 数量无上限（如极端情况下 `OK (skipped=383)` 仍判通过），正式验包若只跑在 Linux 上，可按平台校验跳过数。
- **自测用临时提交打包的做法**：[selftest_package.py#L61-L71,L148-L172](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/release/selftest_package.py#L61-L71) 在隔离临时克隆里建临时提交并用假作者信息提交、测完 `git reset --hard`，思路正确且不污染原仓库；但存在三处工程缺口：① 中文 Windows 下直接编码崩溃（F-T3）；② 未传 `-c commit.gpgsign=false`，若本机 Git 全局开了 GPG 签名则会失败或阻塞；③ `os.symlink`（L176）在无管理员/开发者模式的 Windows 上会抛 `WinError 1314`，且未覆盖坏 CRC 与多余空目录两类坏包。

### 4. 按客户端固定直连、遮挡检查、`regions.yaml` 改写、Claude 组新增规则

- **`Plan.lan_for` 调用点核查**：五个客户端生成器、`audit.py`、`strict.py`、`check_connections.py`、`intended_target` 均已改用 `plan.lan_for(...)`；但 **`generator/model.py` 自身的 `build_plan()`（L824–L831）漏了按客户端过滤 `lan_keys`**（见 F-R1）。（`build.py:81` 和 `tools/check_cursor_report.py:99` 读取 `plan.lan` 仅涉及公开统计/报告，当前公开源无单端直连规则，无即时错误。）
- **遮挡检查会不会误报合法写法**：测试与源码核对“宽规则走代理、窄规则固定直连”（如 `github.com` 代理 + `xxx.github.com` 直连）以及不同客户端之间互不干扰，均正常放行、**无误报**；但存在**漏报**：漏了 `project.yaml` 的 `lan.domain_suffix`（`localhost`）和 `lan.ip_cidr`（见 F-R2）。
- **`source/regions.yaml` 的 `(?<!香)港[德英法欧歐]`**：经本机 `icu.dll` 与 Python 实测，`香港英皇道 01`、`香港德輔道西 01`、`香港法院道 01`、`港德 01`、`深港德 01`、`港德中转 美国 01` 均分对；但因移入 `patterns` 后丧失 `core` 级别，与五大地区国名同现时会错进地区手动组（见 F-R3）。
- **Claude 组新增第三方地址与 IP 段**：
  - **合理且准确**：Anthropic 官方 IP 段（`160.79.104.0/23`、`153.61.224.0/22`、`2607:6bc0::/48`）与官方文档一致；拒收 `34.8.0.0/16`（GCP 公共段）、`fcmtoken.googleapis.com`（Google FCM）、`us5.datadoghq.com` 整段和 `us.sentry.io`（实测核对 pinned 上游 `AdvertisingLite` 与 `category-ads-all` 确实全部拦截 `sentry.io`）均非常审慎；`siftscience.com` 主页在 Loon/QX 被放行的副作用也已在 `docs/06:374` 诚实说明。
  - **存在的问题**：① `docs/06:374` 错把 3 条 Anthropic IP 说成在所有端都“不会为了匹配去解析域名”（见 F-D1）；② Stripe 仅收 `r.stripe.com` 而留 `api.stripe.com` / `m.stripe.com` / `m.stripe.network` / `checkout.stripe.com` 在 `国外默认`，Intercom 仅收两主机而留 `widget.intercom.io` / `js.intercomcdn.com` 在 `国外默认`，切换 Claude 地区时同一会话会分裂成两个出口 IP（见 F-R4）；③ Sift 仅收旧域 `siftscience.com` 未提新域 `sift.com`；④ `storage.googleapis.com` 的公用大流量回落影响与全部 11 条缺 `nature: shared` 标为“专属”（见 F-D2、F-S1）。

### 5. 变异检查新判据（`judge`）、`M249–M272` 与文档数字一致性

- **`judge()` 对已有 272 类变异是否会误判**：静态核对全部 272 类变异的 `expect` 与测试名，在 **Python 3.11–3.13** 上未发现误判，`M249`、`M262`、`M268` 本机实跑均精确命中预期测试并判定 `[发现]`；但 **`judge()` 在 Python 3.10 下必然误判 `M177` 与 `M185` 为“未发现”**（见 F-T4），且实跑输出中 `失败项 ['test_foo.test_foo']` 重复打印方法名。
- **`M249–M272` 覆盖度**：`M249–M272` 扎实覆盖了第 24、25 轮的主要代码修复，但**缺少对本轮新增 Claude 第三方地址/Anthropic IP 段的变异**（相较前轮新增 10 个域名有 `M243`），也缺对 `go-yaml` 下划线处理（第 24 轮 `F01`）的变异；此外还查出两条历史变异 **`M46` 与 `M52` 的链式 `.replace()` 有一半已静默失效**（见 F-T5）。
- **文档与日志一致性**：查出 **10 处明确的日期、数字、规则统计与旧版本残留不一致**（详见 F-D1 至 F-D5）。

---

## 二、已确认问题清单（按类别与严重度）

### 导入失败

#### [F-I1] 高（私密 SFA）：`generator/nodes.py` 多处 TLS / 传输 / TUIC 字段未经 `_text()`，将非字符串 YAML 标量直接写入 sing-box JSON 且 `verify.py` 未拦截
- **位置**：[generator/nodes.py#L272-L273](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/nodes.py#L272-L273)（`alpn`）、[L360-L431](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/nodes.py#L360-L431)（`ws-opts`/`grpc-opts`/`h2-opts`/`http-opts`）、[L670-L672](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/nodes.py#L670-L672)（`tuic.udp-relay-mode`）、[generator/verify.py#L265-L345](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/verify.py#L265-L345)。
- **复现与源码依据**：
  - 本机向 `nodes.load_clash_proxies()` + `nodes.convert()` 输入未加引号的常见/异常字段，再送入 `verify.check_singbox()`，全部通过且 `verify_probs=[]`：
    - `alpn: [h2, 1.1]` -> 写出 `"alpn": ["h2", 1.1]`（JSON 浮点数）
    - `ws-opts: {headers: {Host: 123, X-Flag: true}, path: 123}` -> 写出 `"headers": {"Host": 123, "X-Flag": true}, "path": 123`
    - `grpc-opts: {grpc-service-name: 123}` -> 写出 `"service_name": 123`
    - `h2-opts: {host: [123], path: 456}` -> 写出 `"host": [123], "path": 456`
    - `tuic` `udp-relay-mode: 123` -> 写出 `"udp_relay_mode": 123`
    - 另：`ws-opts.max-early-data: -1`、`alterId: -1`、`heartbeat-interval: -5`、`udp-over-tcp-version: 99` 也均原样写出且通过 `verify.check_singbox()`。
  - 核对 `SagerNet/sing-box@v1.14.1` 结构体定义：`option/tls.go:17`（`ALPN badoption.Listable[string]`）、`option/v2ray_transport.go:86-114`（`Path string`、`Method string`、`ServiceName string`、`Host badoption.Listable[string]`、`Headers badoption.HTTPHeader`、`MaxEarlyData uint32`）、`option/tuic.go:28`（`UDPRelayMode string`）。JSON 收到数字/布尔或负 `uint32` 会导致 `sing-box` 解析配置报错，**整份私密 SFA 配置无法启动**。
- **修改建议**：上述全部文字/列表/字典值字段统一经 `_text()`（以及字典键/值逐项校验类型），并对 `max-early-data`、`alterId`、`heartbeat-interval`、`udp-over-tcp-version`（`1`/`2`）做非负/范围校验；`verify.check_singbox()` 补相应类型校验。

#### [F-I2] 中（私密 SFA）：`convert_one()` 对 `name`、`server` 未走 `_text()`，与 mihomo 及 `r22b_review_probes.py` 声明行为不符
- **位置**：[generator/nodes.py#L504-L515](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/nodes.py#L504-L515)；[handoff/notes/r22b_review_probes.py#L138-L152](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/notes/r22b_review_probes.py#L138-L152)。
- **复现与源码依据**：
  - `convert_one()` 直接执行 `ob = {"tag": str(name), "server": str(server), "server_port": port}`。本机实测输入 `name: 2026-01-02`、`name: true`、`name: 123456789012345678901`、`server: 2026-01-02`、`server: true`、`server: [a, b]`，**全部未被跳过**，分别转成 `"tag": "2026-01-02"`、`"tag": "True"`、`"tag": "1.2345678901234568e+20"`、`"server": "True"`、`"server": "['a', 'b']"` 且通过 `verify.check_singbox()`。
  - 核对 `MetaCubeX/mihomo@v1.19.31`：`adapter/provider/provider.go:416-423` 在 `proxy-providers` 中对 `name` 严格要求 `string`（非 `string` 整条跳过）；`common/structure/structure.go:212-231` 对 `server`（以及顶层 `proxies:` 的 `name`）拒绝 `bool`、`time.Time`、列表，并将浮点按大写 `E` 格式化。
  - `r22b_review_probes.py:143,151` 因只测 `go_plain_scalar()` 而未调 `nodes.convert()`，导致其输出声称“转换器跳过节点”与实际实现相悖。
- **修改建议**：`server` 走 `_text(server, "server")`；`name` 至少走 `_text(name, "name")`（若完全对齐 mihomo `proxy-providers`，还可拒绝非 `str` 的 `name` 或注明差异）；`r22b_review_probes.py` 补测 `nodes.convert()` 和 `sing-box check` 闭环。

---

### 分流错误

#### [F-R1] 高（特定私密配置）：`build_plan()` 的 `lan_keys` 未按客户端过滤，单端 `DIRECT` 服务覆盖 `dns.real_ip` 会令其余客户端失去固定直连
- **位置**：[generator/model.py#L824-L831](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/model.py#L824-L831)。
- **复现**：
  - `validate()`（L656）对 `s.group == "DIRECT"` 允许写与 `dns.real_ip` 同值的规则；随后 `build_plan()` 计算 `lan_keys = {r.key for r in lan}` 时**不看 `r.clients`**，然后对 `m.real_ip` 跳过所有 `k in lan_keys`。
  - 本机实测：在 `local.yaml` 中添加 `group: DIRECT`、`clients: [mihomo]`、规则 `domain: time.windows.com`，结果 `plan.real_ip_direct` 中 `time.windows.com` 消失，导致 `singbox`、`loon`、`quantumultx`、`stash` 四端不再将其写入固定直连段，路由回落到 `Microsoft` 组（而在 DNS 侧它仍在 `dns.real_ip` 走国内 DNS，产生路由/DNS 不一致）。
- **修改建议**：计算 `lan_keys` 时仅纳入无 `clients` 限制（对全部 5 个客户端生效）的 `lan` 规则，或在各端生成/计算 `real_ip_direct_for(family)` 时按 `family` 独立去重。

#### [F-R2] 中（特定私密配置）：`R22-F06` 固定直连遮挡检查漏掉 `project.yaml` 的 `lan.domain_suffix`（`localhost`）与 `lan.ip_cidr`
- **位置**：[generator/model.py#L667-L683](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/model.py#L667-L683)。
- **复现**：
  - `validate()` 只收集了 `s.group == "DIRECT"` 的服务规则和 `m.real_ip`，**漏了 `m.lan`**（即 `project.yaml` 的 `lan.domain_suffix` 与 `lan.ip_cidr`）。由于 `localhost` 只在 `lan.domain_suffix` 中、不在 `dns.real_ip` 中，本机在 `local.yaml` 加入 `domain: foo.localhost -> 国外默认` 与 `ip4: 10.1.2.3/32 -> 国外默认`，均**未经报错直接通过 `model.load()`**。
  - 生成结果中：mihomo 的 `nameserver-policy` 写出 `foo.localhost: *dns-foreign`（精确匹配优先于 `+.localhost: [system]`），而路由里 `DOMAIN-SUFFIX,localhost,DIRECT` 排在 `DOMAIN,foo.localhost,国外默认` 之前——**准确重现了 `R22-F06` 要消灭的“路由固定直连、DNS 走境外”冲突**；`10.1.2.3/32` 也被 `10.0.0.0/8,DIRECT` 静默遮挡。
- **修改建议**：将 `m.lan` 的域名后缀和 IP 段一并纳入 `fixed_direct` 集合进行遮挡校验（IP 段可按 `ipaddress.ip_network.subnet_of()` 判断覆盖）。

#### [F-R3] 中（公开产物 / 节点分地区）：`港德/港英/港法/港欧/港歐` 移入 `patterns` 后被静默降级为“城市一级”，与五大地区国名同现时错入地区手动组
- **位置**：[source/regions.yaml#L201-L202](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/source/regions.yaml#L201-L202)、[generator/regions.py#L111-L118](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/regions.py#L111-L118)、[generator/regions.py#L790](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/regions.py#L790)。
- **复现**：
  - `Words.vocab("core")` 只取 `words` 和 `latin`、丢弃 `patterns`，且 `Classifier` 将 `other_countries.patterns` 全部标为 `core=False`（城市词级别）。
  - 本机实测 `classify()` 与生成正则对比：
    - `德国-日本 01` -> `groups=[]`（进“其他地区”，正确）
    - `港德-日本 01` -> `groups=['jp'], auto=[]`，理由：`有国名“日本”，也有其他国家的城市词“港德”`（错进日本手动组）
    - `美国 港英 01` -> `groups=['us'], auto=[]`（错进美国手动组）
    - `台湾 港欧 01` -> `groups=['tw'], auto=[]`（错进台湾手动组）
  - 虽不进自动组，但在完整版手动组与简易版地区组中会污染地区列表，且与 `docs/06:397` “`港德 / 港英 / 港法 / 港欧` 归其他地区”不符。
- **修改建议**：为 `other_countries`（或 `Words`）区分国名级正则 `core_patterns` 与城市级正则 `patterns`，让 `(?<!香)港[德英法欧歐]` 保持 `core=True`，并在 `tests/node_names.yaml` 补 `港德-日本 01` 等回归样本。

#### [F-R4] 中低（Claude 组规则取舍）：`r.stripe.com` 与 Intercom 仅收录部分主机，切换 Claude 地区时同一会话会分裂成两个出口 IP
- **位置**：[source/services/ai.yaml#L71-L74](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/source/services/ai.yaml#L71-L74)、[source/adblock.yaml](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/source/adblock.yaml)、[docs/06-已知限制与待决事项.md#L374](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/06-已知限制与待决事项.md#L374)。
- **事实核实**：
  - 当前 `r.stripe.com` 走 `Claude`，而 `api.stripe.com`、`checkout.stripe.com`、`billing.stripe.com`、`js.stripe.com`、`m.stripe.com`、`m.stripe.network` 全部走 `国外默认`；`api-iam.intercom.io`、`nexus-websocket-a.intercom.io` 走 `Claude`，而 `widget.intercom.io`、`js.intercomcdn.com` 走 `国外默认`。
  - 默认两者都在日本时无差异；**一旦将 `Claude` 切换到其他地区**，Claude 结账页面发往 `r.stripe.com` 的风控遥测与发往 `m.stripe.network` / `api.stripe.com` 的真实结账和 Stripe Radar 信号会从**不同地区/IP** 发出——既违背“让 Anthropic/付款链路只看到 Claude 出口 IP”的初衷，也有触发 Stripe Radar 跨 IP 风控的风险。
  - 另：Sift 现行主遥测/脚本域是 `cdn.sift.com` / `beacon.sift.com`，本版只收了旧域 `siftscience.com`（若收 `sift.com` 同样需注意 `AdvertisingLite` 对裸域 `sift.com` 的拦截）。
- **修改建议**：向使用者确认取舍——若按严格一致性走 Claude，可决定是否将 `m.stripe.com`、`m.stripe.network`（或 Stripe 结账相关域）与 Intercom 前端域一并对齐或改回统一走 `国外默认`；至少应在 `docs/06:374` 明确提示“切换 Claude 地区后 Stripe/Intercom 同一会话会拆成两个出口 IP”。

---

### 安全或泄漏（含工具安全边界）

#### [F-T1] 中（发布工具）：`package_check.py unpack` 对额外空目录条目（含 `dist/private/`、`.git/`、`extra-dir//`）放行并返回 0
- **位置**：[handoff/release/package_check.py#L45-L68](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/release/package_check.py#L45-L68)。
- **复现**：
  - `unsafe(n)` 用 `n.rstrip("/")`，因此双斜杠目录 `proxy-rules/extra-dir//` 绕过了 `"" in parts` 校验（且 L48 的 `":" in parts[0]` 因前面已查 `not n.startswith("proxy-rules/")` 成为不可达死代码）。
  - 后续 `got` 只遍历 `files = [i for i in infos if not i.is_dir()]`，对目录条目未做集合校验。本机向合法 zip 注入 `proxy-rules/dist/private/`、`proxy-rules/.git/`、`proxy-rules/extra-dir//` 三个空目录条目后运行 `package_check.py unpack`，**返回码为 0**，且 `z.extractall(dest)` 在磁盘上实际创建了这三个目录。
  - 另外未检查 ZIP 条目的 Unix symlink 权限位（`stat.S_ISLNK(i.external_attr >> 16)`；Python `extractall` 虽不解出符号链接，但第三方 `unzip` 解包时存在隐患）。
- **修改建议**：① `unsafe(n)` 仅对目录条目去掉**单个**尾部 `/`（`n[:-1] if n.endswith("/") else n`）再切分，拒绝双斜杠；② 校验所有目录条目只能是 `want` 文件的合法父目录集合（或直接禁止 pack.py 不生成的额外目录条目），且禁止 `forbidden`/`junk` 路径及 symlink 位。

---

### 工具与测试

#### [F-T2] 中（发布工具）：`package_check.py unpack` 遇到坏 CRC 未提前返回，导致未捕获 `BadZipFile` 崩溃且留下半解压目录
- **位置**：[handoff/release/package_check.py#L38-L40,L66-L68](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/release/package_check.py#L38-L40)。
- **复现**：构造单字节损坏 `README.md` 的 zip 并运行 `package_check.py unpack`，`z.testzip()` 查出坏 CRC 后只追加到 `problems`、未 `return 1`，随即执行 `z.extractall(dest)` 抛出未捕获的 `zipfile.BadZipFile: Bad CRC-32 for file 'proxy-rules/README.md'` 堆栈（`problems` 里的中文提示从未打印），同时留下残缺的解压目录。
- **修改建议**：`if bad_crc:` 直接打印提示并 `return 1`（在 `os.makedirs`/`extractall` 之前）。

#### [F-T3] 中（发布工具 / Windows）：`selftest_package.py` 在中文 Windows 上无论是否设 `PYTHONUTF8=1` 均直接崩溃
- **位置**：[handoff/release/selftest_package.py#L31-L33,L95,L114](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/release/selftest_package.py#L31-L33)。
- **复现**：
  - 设置 `PYTHONUTF8=1` 时：`selftest_package.py` 以 UTF-8 读子进程输出，但 L95 用 `python -I` 启动 `pack.py` 会屏蔽 `PYTHONUTF8=1`，使 `pack.py` 输出 GBK，触发 `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xcc` + `TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'`。
  - 取消 `PYTHONUTF8` 时：L95 通过，但 L114 调用 `bash verify_package.sh` 输出 UTF-8，而 `selftest_package.py` 按 GBK 解码，触发 `UnicodeDecodeError: 'gbk' codec can't decode byte 0xac` + 同样的 `TypeError`。
- **修改建议**：`pack.py` / `package_check.py` 启动时将 `stdout`/`stderr` 重配为 UTF-8（或用 `-I -X utf8`），`selftest_package.py` 的 `run()` 显式指定 `encoding="utf-8", errors="replace"`；同时 `fixture_commit()` 加上 `-c commit.gpgsign=false`。

#### [F-T4] 中（变异检查）：`tools/check_mutations.py` 的 `judge()` 在 Python 3.10 下必然将 `M177`、`M185` 误判为“未发现”
- **位置**：[tools/check_mutations.py#L41,L61-L64,L100](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/tools/check_mutations.py#L41-L65)、[L644](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/tools/check_mutations.py#L644)（`M177`）、[L673](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/tools/check_mutations.py#L673)（`M185`）。
- **分析**：
  - 项目文档声明需要 `Python 3.10+`。但 Python 3.10 的 `unittest` 输出格式为 `FAIL: test_foo (test_simple.Verifier)`（括号内**不含** `.test_foo`，从 Python 3.11 起才变成 `test_simple.Verifier.test_foo`）。
  - `M185` 预设 `test_simple.Verifier.test_generated_outputs_pass`，在 Python 3.10 下 `c` 是 `test_simple.Verifier`，`c == expect` 恒为 `False`；`M177` 预设 `SameAsFullOutsideGroups.test_mihomo`，落入 `else:` 子串分支，在 Python 3.10 失败段文本里也不存在该连写串，同样恒为 `False`。
  - 另：L100 打印 `[f'{c.split(".")[-1]}.{t}' ...]` 在 Python 3.11+ 下因 `c` 末尾已是 `t`，实跑输出了重复名如 `test_ss2022_keys_are_checked_like_singbox.test_ss2022_keys_are_checked_like_singbox`；且 `M177` 写成 `Class.method` 未走精确分支，建议统一改为 `test_simple.SameAsFullOutsideGroups.test_mihomo`。
- **修改建议**：在 `failure_sections()` / `judge()` 中将 `(t, c)` 规范化为完整编号 `full = c if c.endswith("." + t) else f"{c}.{t}"`，同时修复 Python 3.10 兼容与 L100 重复打印。

#### [F-T5] 中（变异检查）：`M46`、`M52` 链式 `.replace()` 静默半失效（`--check-edits` 无法察觉），且拷贝未排除 `.git` 在 Windows 泄漏磁盘空间
- **位置**：[tools/check_mutations.py#L73,L250-L256,L267-L269,L973](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/tools/check_mutations.py#L250-L269)。
- **复现**：
  - 实测 `M46` 与 `M52` 的生成 diff：
    - `M46` 第一段 `.replace()` 找的是旧代码 `mine + by_text_loose`（现为 `seen + by_text_loose`），**静默未生效**（宽松正则完全没改，只改了第 2、3 处）；
    - `M52` 第二段 `.replace()` 找的是旧正则 `'(?<!香)港(?![日韩韓美])'`（r22 已改为 `'(?<!香)港(?![日韩韓美台臺新坡德英法欧歐])'`），**静默未生效**（旧 `patterns` 未删）。
    - 因 `apply_edits` 只检查整个 lambda 返回 `s2 != s`，`--check-edits` 仍报 `272/272` 全部通过。
  - L73 与 L973 的 `shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns("__pycache__", "dist"))` 未排除 `.git`。在 Windows 上 `.git/objects/pack/*` 默认只读，`shutil.rmtree(..., ignore_errors=True)` 静默失败，运行一次 `--check-edits` 会向临时目录泄漏约 5 GB 只读副本（本机审核首次运行直接触发 `WinError 112` 磁盘满）。
- **修改建议**：将多步替换拆为逐条断言生效的辅助函数（或独立元组），更新 `M46`、`M52` 匹配文本；在 `ignore_patterns` 中加入 `".git"`，并在清理失败时处理只读位（`onerror`）。

#### [F-N3] 低（订阅读法边界）：`go_plain_scalar("1e-500")` 与顶层合并覆盖时的 `duplicate_keys()` 同 `go-yaml v3.0.5` 存在微小差异
- **位置**：[generator/nodes.py#L781-L793,L843-L849](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/generator/nodes.py#L843-L849)。
- **依据**：实测 `nodes.go_plain_scalar("1e-500")` 返回 `float 0.0`（Go `strconv.ParseFloat` 下溢返回 `ErrRange`，`go-yaml` 留字符串）；实测顶层写 `<<: *base`（含重复键的 `*base.proxies`）同时同层用 `proxies:` 覆盖时，`duplicate_keys()` 拒绝整份订阅，而 `go-yaml@v3.0.5` `decode.go:915-920` 跳过被覆盖的合并字段。均属极罕见输入，记为低优先级加固项。

---

### 文档不符

#### [F-D1] 中（事实错误 / DNS 口子）：`docs/06` 错误宣称 3 段 Anthropic IP “不会为了匹配去解析域名”，且 `docs/03`、`docs/06` 漏更 QX 标准版 IP 解析触发点
- **位置**：[docs/06-已知限制与待决事项.md#L374](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/06-已知限制与待决事项.md#L374)、[docs/06-已知限制与待决事项.md#L86](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/06-已知限制与待决事项.md#L86)、[docs/03-DNS决策表.md#L28](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/03-DNS决策表.md#L28)。
- **事实核实**：
  - `docs/06:374` 写 3 段 Anthropic IP `（只管直接连 IP 的连接，不会为了匹配去解析域名）`。但在 `dist/quantumultx/quantumultx.conf` 中，三条 `ip-cidr, 160.79.104.0/23, Claude` 等规则**不带 `no-resolve`**（QX 不支持 `no-resolve`），且排在 Telegram IP 段之前。标准版下未命中域名规则的域名走到这 3 条规则时**就会触发本机 DNS 解析**。
  - `docs/03:28` 与 `docs/06:86` 也仍只写“走到 Telegram 专属 IP 规则时会先解析”，未同步更新 Anthropic IP 段。

#### [F-D2] 低（性质标记与内部注释失配）：Claude 新增 11 条第三方规则在 `docs/04` 全标为“专属”，`source/services/ai.yaml` 有两处过时说明
- **位置**：[source/services/ai.yaml#L25,L65-L80](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/source/services/ai.yaml#L65-L80)、[docs/04-规则清单与证据.md#L157-L167](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/04-规则清单与证据.md#L157-L167)。
- **事实核实**：
  1. `ai.yaml:65-80` 的 11 条第三方共用地址均未写 `nature: shared`，导致自动生成的 `docs/04:157-167` 将它们全部标成 **`专属`**（第 159 行一边写 `专属` 一边备注“Google Cloud Storage 的公共入口”）。
  2. `ai.yaml:70` 注释仍写着 `Sentry 报错等也会走 Claude 组（docs/06 2026-11-20 一节）`——Sentry 已在 `23cd51a` 移除，且 `docs/06` 对应小节标题日期为 `2026-11-19`。
  3. `ai.yaml:25`（`openai.shared_excluded`）仍写 `*.intercom.io / *.intercomcdn.com → 国外默认`，未像 L27 的 `*.workos.com` 那样说明其中两台主机已分给 `Claude`。

#### [F-D3] 低（日期与数字错误）：快速检查日期写错一天，多份文档残留 r21 / r22 第一份送审稿的数字与计数
- **位置与实核对照**：
  1. **快速检查日期错写为 11-19**：[handoff/notes/r22_draft2/README.txt#L8](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/notes/r22_draft2/README.txt#L8) 与 [docs/08-外部审核记录.md#L861](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/08-外部审核记录.md#L861) 均写 `2026-11-19 01:47–01:56（UTC），提交 fc14b5f`；实查 `git log` 与 `handoff/notes/r22_draft2/logs/*.log`，提交 `fc14b5f` 与日志时间均为 **`2026-11-20 01:47–01:56 UTC`**。同日偏差亦见于 `README.zh-CN.md:34`、`README.md:25,129`、`PROJECT_STATE.md:3,59`。
  2. **`docs/03` 两条规则统计过期**：[docs/03-DNS决策表.md#L48](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/03-DNS决策表.md#L48) 仍写 `product-proxied：653 个后缀、108 个精确主机`（实测 `dist/sing-box/sing-box-1.14.json` 实际为 **670 个后缀、125 个精确主机**）；[docs/03-DNS决策表.md#L175](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/docs/03-DNS决策表.md#L175) 仍写 Loon 严格版 `[Rule]` 有 `28 条按 IP 判断的规则`（实测 `dist/loon/loon-strict.conf` 实际为 **31 条**，新增 3 条 Anthropic IP）。
  3. **`README.zh-CN.md` 数字与检查日期过时**：[README.zh-CN.md#L132](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/README.zh-CN.md#L132) 写 mihomo 逐条扫描 `222,353` 个代表主机，实查 `tests/data/real_sets.json` 与 `real-routes-snapshot.log` 为 **`222,358`**；[README.zh-CN.md#L136](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/README.zh-CN.md#L136) 仍写 r21 的 `2026-10-31（UTC）` 与 `Python 3.13.16`（r22 快速检查为 `2026-11-20`、`Python 3.13.18`）。
  4. **`README.md` 过时**：[README.md#L143](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/README.md#L143) 的 Version history 漏提第二份送审稿对 Claude 组的新增主机与 IP 段；[README.md#L151](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/README.md#L151) 末尾仍写 `2026-11-18 (UTC), for the r22 review draft`。
  5. **操作文档残留 `248` 类 / `369` 项旧数**：[00-审核说明.md#L164-L167](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/00-审核说明.md#L164-L167)（仍写 `248` 类、`r22_private_vs_r21b.py`、`--old-label r20 --new-label r21`）；[PROJECT_STATE.md#L25](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/PROJECT_STATE.md#L25)（T5 仍写 `369 项 / 248 类`）；[handoff/release/README.md#L22](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/release/README.md#L22) 与 [handoff/README.md#L271-L273](https://github.com/ixxooxo-alt/proxy/blob/8558a2783c670a923974c1ec688d43bbc688a484/handoff/README.md#L271-L273)（仍写 `248` 类）。

---

### 建议（非缺陷）

#### [F-S1] 建议：在 `docs/06` 补充 `storage.googleapis.com` 改走 Claude 组的带宽/流量提示，并补齐本轮新增规则的变异用例
- `storage.googleapis.com` 承载大量非 Anthropic 的公用 GCS 下载（浏览器/SDK/容器镜像/模型与依赖包）；若用户的 `Claude` 组使用专用住宅 IP 或带宽受限节点，流量和速度会受到明显影响，建议在 `docs/06:374` 显式提醒。
- 建议在 `tools/check_mutations.py` 补加针对 Claude 新增第三方主机/Anthropic IP 段、`R22-F01/F05` 遗漏点（`lan_keys`、`lan.domain_suffix`）和 `R22-F15` 五词国名级分类的变异测试。
- `verify_package.sh:96` 的 `--exclude=verify_package.sh --exclude=finalize.py --exclude=selftest_package.py` 按文件名全局排除，可顺手改为按 `proxy-rules/handoff/release/...` 相对路径排除；L126 路径巡检也可一并覆盖 `handoff/notes/`。

---

## 三、推断与未验证事项

以下事项在本轮审核中**未通过实跑验证**，结论仅基于源码分析或已有文档，不作为已证实运行结果：

1. **官方二进制实跑**：因本机网络无法从 GitHub Releases 完整拉取 Windows 版 `mihomo v1.19.31` 与 `sing-box 1.14.1` 压缩包，未在本地重跑 `tools/check_official.py`、`tools/check_real_routes.py` 和 `handoff/notes/r22b_review_probes.py`。上述关于 sing-box JSON 反序列化失败（F-I1）及 mihomo `proxy-providers` 行为（F-I2）的判断，均直接以**对应固定版本上游 Go 源码**（`SagerNet/sing-box@v1.14.1`、`MetaCubeX/mihomo@v1.19.31`、`yaml/go-yaml@v3.0.5`、Go `1.24` `time/format.go`）为依据。
2. **完整 272 类变异检查与 `tools/run_checks.sh`**：本轮仅全量跑了 `--check-edits` 并实跑了 `M249`、`M262`、`M268` 三类；其余 269 类仅做静态核对与 `M46`/`M52` 替换 diff 验证，未全量执行。
3. **跨 Python 版本与 Linux 实跑**：本机仅在 Windows + Python 3.12.13 下运行，`judge()` 在 Python 3.10 下的失败（F-T4）依据 Python 3.10 `unittest.TestCase.__str__` 输出格式推得，未在真实 Python 3.10 解释器上复现。
4. **真机导入、真实订阅与外网 DNS 行为**：未在 Loon、Quantumult X、Stash、SFA、Clash Verge Rev、Clash Meta for Android 真机上验证，亦未测试真实机场订阅与外网 CNAME/Stripe/Intercom 实网链路。

---

## 四、本轮验证边界与实跑命令记录

- **审核环境**：Windows（中文区域设置 `cp936`）、Python `3.12.13`、PyYAML `6.0.3`、Windows 系统 `icu.dll`、Git Bash；被审仓库检出至独立临时目录，提交固定为 `8558a2783c670a923974c1ec688d43bbc688a484`，审核全程未修改仓库任何文件。
- **实际运行的命令与结果**：
  1. `python build.py --check` -> **通过**（退出码 0，输出“产物与统一源一致（含 manifest.json）”）。
  2. `python -B -m unittest discover -s tests -v` -> **通过**（退出码 0，耗时 826.0s，`Ran 383 tests ... OK (skipped=3)`）。
     - **Windows 上跳过的 3 项**（均为 `tests/test_real_data.py` 的 `Socks5RecorderTool`，跳过原因均为 `没有 /proc/net/udp，确认不了包已经进了 UDP 口`）：
       - `test_recorder_stop_ignores_udp_packets_after_the_control_connection_closed`
       - `test_recorder_stop_ignores_udp_packets_after_the_control_connection_closes_mid_drain`
       - `test_recorder_stop_keeps_udp_packets_already_received`
  3. `python -B tools/check_icu.py --public --verbose` -> **通过**（退出码 0，Windows `icu.dll` 上全部样本与 Python 结果 100% 一致）。
  4. `python -B tools/check_cursor_report.py` -> **通过**（退出码 0）。
  5. `python -B tools/check_mutations.py --check-edits` -> **通过**（退出码 0，`272/272` 均改动了目标文件；另行编写检查脚本核对全部链式 `.replace()`，查出 `M46`、`M52` 静默半失效）。
  6. `python -B tools/check_mutations.py --skip-baseline M249` / `M262` / `M268`（在 383 项基线全过后并行抽跑）-> **3/3 均判定 `[发现]`**（退出码均为 0，各自耗时约 877–887s，`failures=1, skipped=5`，均命中各自预设测试名）。
  7. `python -B handoff/release/selftest_package.py` -> **失败**（退出码 1，详见 F-T3；设与不设 `PYTHONUTF8=1` 均在中文 Windows 上抛 `UnicodeDecodeError` + `TypeError`）。
  8. **针对性复现验证**：在独立临时目录中实测复现了 F-I1（15 组畸形/非字符串节点输入与 `verify.check_singbox()`）、F-I2（`name`/`server` 未经 `_text()`）、F-R1（单端 `DIRECT` 覆盖 `time.windows.com`）、F-R2（`foo.localhost` 与 `10.1.2.3/32` 绕过遮挡校验及 mihomo DNS/路由分裂）、F-R3（`港德-日本 01` 等分类结果）、F-T1（空目录绕过 `package_check.py unpack`）、F-T2（坏 CRC 抛未捕获 `BadZipFile`）、F-N3（`1e-500` 与顶层合并覆盖）；并拉取核对了 pinned 上游源码与广告名单（`yaml/go-yaml@v3.0.5`、`MetaCubeX/mihomo@v1.19.31`、`SagerNet/sing-box@v1.14.1`、`golang/go@go1.24.0`、`blackmatrix7/ios_rule_script@51d2e1d`、`v2fly/domain-list-community@c1c2cf0`）。
