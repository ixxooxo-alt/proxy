# proxy r15 审核报告

审核提交：**dc90da785b654f7ab318354da23f392502303e52**，分支 **claude/r12-gpt-review-handling-q4onlv**。统一源 2026.10.13-1，生成器 1.8.0。基线：r14 的 3f456689579a7010a5c6aacd683f472e19dd6ca4。审核日期：2026-10-13。

本轮按根目录《00-审核说明.md》的六个重点审查 r14→r15 增量，并回看相关生成器、需求、已知限制和第 10 轮处理记录。没有审核 main，没有修改项目文件、提交或推送代码。

## 结论与优先级

**本轮没有确认到 r15 新增的导入失败、分流错误或 DNS 泄漏。** 这是一份增量代码审核结论，不等于四端真机验收通过，也不等于已经证明“所有国外出口都不交给国内 DNS”。

最影响你两个目标的部分：

- r15 没有改变 DNS 和策略组配置；没有为了修 UDP 或统一 DNS 而把国内网站整体改交境外 DNS。国内网站是否快，仍需实际网络测量，不能从测试通过推出。
- 第 21 项按你选择的①维持现状；默认直连组切到国外以后，命中国内域名集合的名字，在 mihomo 需要本机解析的代理路径上仍可能交给国内 DNS。这是已明确接受的限制，不作为本轮新问题重复报告。
- `afpapi.alimama.com` 的补拦落实正确；未将上游关键词扩大为新的全局关键词拦截。
- 确认 **1 项记录器实现问题（R15-F01）**、**1 项遗漏的旧说明（R15-F02）**，以及若干非阻断建议。
- sing-box UDP 的根因、其他协议及 TUN 的影响，本轮**未能作出运行验证结论**。三个官方版本均在启动阶段遭遇 netlink 权限限制，详见后文。不能把仓库已有记录写成我本轮独立复现的结果。

## 已确认问题

### R15-F01：SOCKS5 记录器会把不应接受的报文计入正常收到的目标

**类别：文档不符／测试工具问题；优先级中。不是生产配置的安全漏洞。**

位置（均为本次固定提交）：

- `tools/check_real_routes.py:855–895`，`Socks5Recorder._serve`。
- 第 861–862 行丢弃客户端提供的方法列表，无条件选择无认证。
- 第 878–895 行在固定 8 秒内读取 UDP；没有跟随控制 TCP 连接关闭而终止关联；直接跳过 RSV、FRAG 字段。
- `00-审核说明.md`“本轮改了什么”第 3 条把它概括为按 RFC 1928 处理 CONNECT、UDP ASSOCIATE。

**独立复现：** 直接向记录器发送协议字节，不经过 mihomo/sing-box，得到：

| 输入 | 实际结果 | RFC 1928 要求或相应边界 |
|---|---|---|
| 只提供方法 02（用户名／密码） | 返回 `05 00`，选择未被提供的方法 | 第 3 节：应从客户端提供的方法中选择；无可接受方法时返回 FF |
| FRAG=1、目标 `fragment.example`，仅发送这一片 | 正常记为 `udp/domain/fragment.example` | 第 7 节：不实现分片的实现必须丢弃 FRAG 非零的数据报；这里没有重组实现 |
| UDP ASSOCIATE 的控制 TCP 已关闭，再向原 UDP 端口发 `afterclose.example` | 仍正常记录 | 第 6 节：关联随创建它的 TCP 连接终止 |
| 正常 FRAG=0、目标 `valid.example` | 正常记录 | 正向对照通过 |

**为什么需要改：** 当前指标表示“测试接收端观察到了目标字段”，尚不能等同于“符合所声明协议范围的服务端接受了有效请求”。未来内核出现分片或连接生命周期错误，记录器可能照样给出 `domain`，造成假阳性。源地址和请求头版本／保留位也没有完整校验。

**影响边界：** 当前发送工具使用无认证、FRAG=0，并保持控制连接；上述反例没有推翻 r15 正常路径的已有结果，也不能解释仓库记录的 `unsupported address`。它们是记录器独立存在的问题。

**建议：** 只在方法列表含 00 时接受无认证；校验请求版本和 RSV；暂不支持重组时明确拒绝 FRAG≠0；监视控制连接 EOF 并关闭对应 UDP socket；异常报文单独记为 `invalid`，不要计入成功样本。保留“只记录不转发”的定位，无需实现完整代理服务器。增加上述三个负向用例即可。

依据：[RFC 1928](https://www.rfc-editor.org/rfc/rfc1928.html)，1996-03，第 3、6、7 节。项目位置：[记录器](https://github.com/ixxooxo-alt/proxy/blob/dc90da785b654f7ab318354da23f392502303e52/tools/check_real_routes.py#L855)。

### R15-F02：出站核对函数仍保留“TCP、UDP 都原样交域名”的旧说明

**类别：文档不符；优先级低。**

位置：`tools/check_real_routes.py:1089–1091`，`singbox_outbound_probe` 的 docstring 中“sing-box 的代理出站把域名原样交给节点（TCP、UDP 都是）”。

这与同一版本 `docs/06-已知限制与待决事项.md` 的 r15 节、`tests/cases.yaml` 分版本的 `received` 期望不一致：仓库记录 1.14.1 的特定 SOCKS UDP 场景没有发送；未命中域名规则的目标还可能在本机经境外 DNS 解析后以 IP 交给节点。因此这条无条件概括已经不成立。

建议改成：“本项观察不同版本、路由和出站协议下实际交付的地址类型；结果以 DNS 记录及接收端记录分别判断，已知差异见 docs/06。”不需要改配置或原始证据。

依据是本提交内部相互矛盾的说明和期望，不依赖本轮成功运行 sing-box。

## 六个重点的审核结果

### 1. 第 21 项：两条解析路径与方案③

**主要改写正确。** mihomo v1.19.31 的 `dns/resolver.go` 创建直连解析器时，只有启用 `direct-nameserver-follow-policy` 才把默认策略赋给它；代理路径使用的默认解析器与其并非同一个概念。官方文档也分别说明这两个设置。r15 不再把当前配置的限制扩大成内核根本做不到，修复了 R14-F01。

依据：

- [mihomo v1.19.31 dns/resolver.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/dns/resolver.go#L617)，直连解析器构造。
- [mihomo DNS 官方文档](https://wiki.metacubex.one/config/dns/#direct-nameserver-follow-policy)。
- [v1.19.31 direct.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/direct.go)、[base.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/adapter/outbound/base.go)，直连解析与代理 UDP 解析路径。

现状应精确读成下表，不能只按业务组名字一概而论：

| 主机与情况 | 默认直连 | 改选需要本机解析目标的代理出口 |
|---|---|---|
| `www.apple.com`，本次固定数据中未命中国内集合 | 国内 direct-nameserver | 默认境外 nameserver |
| `api.bilibili.com`、`www.apple.com.cn`，命中国内集合 | 国内 | 仍可能是国内 nameserver-policy |
| SOCKS TCP 能直接承载目标域名的路径 | 按直连解析 | 不应套用“必须在本机解析”的结论；应看节点收到的目标 |

表中主机归属与运行结果来自本提交的固定数据及已存档记录；本轮核对了配置和机制，没有重新完成全套官方内核运行。上游集合更新以后，例子可能变化。一般规则应写为“看最终命中的 DNS 策略”，而非把是否在 cn 集合当作所有配置下的充要条件。

方案③成立的条件也写对了：`direct-nameserver: [system]`、follow-policy=false，加境外产品层，能使直连与代理本机解析分开；但 **system 不是路由器的同义词**。它把所有直连的解析交给系统提供的服务器，不能保证性能和局域网解析。

建议在 `docs/06` 第 21 项方案③后补两句（类别：建议，未启用方案，不是现行配置缺陷）：

1. 系统 DNS 必须最终指向独立可用的解析器。仅排除 TUN 自己的 DNS 地址，并不能排除本机 DNS 转发器又转回 mihomo 的间接环路；把 system 换成本机替身的测试也不验证这一点。这里是条件风险，没有证据说明你的设备已经循环。
2. fake-IP 只解决设备拿到的 A／AAAA 地址和后续映射，不能让 TXT 等查询自动随业务组选择变化。把产品策略静态改成境外后，非地址查询也会相应走该静态策略；应单独说明，不能宣传成所有 DNS 都跟着组切换。

客户端差异：Clash Verge Rev v2.5.7 修改系统 DNS 和运行配置这一点在文档中已有明确限定；macOS `/etc/resolv.conf` 最终内容仍应现场确认。CMFA 的系统 DNS 来自 App 传给内核的值；不能从 `system` 这个配置词推出是路由器。r15 把 Mac 结论列为推断、把实际设备列为未验证，证据等级合理。不要把 Linux 替身测试提升成 Mac／Android 实测。

### 2. `received_by_node` 与记录器

- ATYP=1／3／4 的地址长度、域名长度前缀、网络字节序端口的读取，正常报文路径没有发现新错。
- 为每个主机分配不同 127.0.1.x 地址，能够识别“本机先解析、再把 IP 交给节点”的情况。
- 独立构造同一主机的域名记录和对应 IP 记录，输出确实为 **`domain+ip`**，没有后一项覆盖前一项的问题。
- `received_by_node` 汇总时不区分 TCP／UDP。当前每种场景创建独立记录器，启动 canary 也不属于被测主机，因此没有确认到现有结果被串扰。建议把 transport 作为显式过滤条件，避免未来复用记录器时误归类。
- `-` 只能表示本次观察窗口没有记录到对应目标。它不能独自证明“正常远端解析”或“正常直连”；r15 主文档已不再这样推导，方向正确。若要区分失败原因，建议另记握手、有效 UDP 包数和核心错误，而不是扩充一个 `-` 的含义。
- RFC 子集的缺口见 R15-F01。

### 3. sing-box 1.14.1 SOCKS UDP：本轮能确认到哪里

**不能在本轮独立确认根因，也不能确认 SS／Trojan／VMess 或 TUN 是否同样受影响。** 没有把它列为新增项目错误。

仓库存档所描述的是：特定配置、mixed 入站、SOCKS 出站、域名 UDP 目标、1.14.1 日志出现 `packet upload closed: unsupported address`，接收端无对应包；1.12.0 对照能收到域名。这是值得跟进的可用性问题，尚不是所有协议都会丢 UDP 的证据。

本轮下载官方 Linux amd64 1.12.0、1.14.1、1.14.3，尝试不带规则集、不带 TUN、只有 mixed→SOCKS 的最小配置。结果：

| 版本 | 本轮运行结果 |
|---|---|
| 1.12.0 | 启动失败：`start service: operation not permitted` |
| 1.14.1 | 启动失败：`start service: create netlink socket: operation not permitted` |
| 1.14.3 | 启动失败：`start service: initialize network: create netlink socket: operation not permitted` |

这些错误发生在转发之前，不能当作 UDP 失败结果。本轮没有绕过环境权限限制。

**源码能说明但不能替代复现的部分：**

- [sing-box v1.14.1 protocol/socks/outbound.go](https://github.com/SagerNet/sing-box/blob/v1.14.1/protocol/socks/outbound.go#L96) 调用 sing 的 SOCKS 客户端；该版本 `go.mod` 依赖 sing v0.9.4。
- [sing v0.9.4 protocol/socks/packet.go](https://github.com/SagerNet/sing/blob/v0.9.4/protocol/socks/packet.go#L92) 的 `WritePacket` 使用 SOCKS 地址序列化器，并非协议设计上不支持域名。
- [同版本 common/metadata/serializer.go](https://github.com/SagerNet/sing/blob/v0.9.4/common/metadata/serializer.go#L49) 的 `unsupported address` 是地址 family 无法编码时返回；空／丢失目标地址是应检查的方向。**没有调用栈或运行插桩，不能据这一字符串宣布已定位到具体包装层。**
- Shadowsocks、Trojan、VMess 的出站实现不同，也有共享路由／报文转发层。既不能由 SOCKS 现象推出它们都坏，也不能因协议不同宣布它们不受影响。TUN fake-IP 还经过额外的目标还原与 NAT 包装，mixed 结果不能直接替代。

截至审核查询，官方最新稳定发布为 [1.14.3](https://github.com/SagerNet/sing-box/releases/tag/v1.14.3)；发布说明只概括为 fixes and improvements，**不足以证明此问题已修复**。不建议无依据地写“升级就能解决”，也不建议为了规避它将所有目标交给国内 DNS。

下一次可运行环境下的最小验证建议（类别：建议）：保留同一规范 SOCKS 接收端，分别测试域名／IPv4，去掉再加回 sniff、resolve 和 selector；每次记录控制请求、有效 UDP 包、日志。随后用本机配对服务端检查 SS／Trojan／VMess，再做真实 TUN fake-IP。先定位是哪一层丢了目标地址，再决定配置临时措施。远端用本机替身即可，不需要公开机场凭据。

### 4. `valid_and_split` 与 mihomo 域名树

r15 在 `tools/dns_route_consistency.py:148–171` 加的空串、尾点、首尾空白、空标签及通配符位置检查，**在项目当前 ASCII 域名／通配符范围和列出的 23 个样本上，与 v1.19.31 的逻辑相符**。这修复了 r14 的宽松接受问题；266 项测试包含该回归检查并全部通过。

不应宣称任意 Unicode 输入也逐字等价（类别：建议，非当前规则错误）：Python `str.isspace()` 与 Go `unicode.IsSpace` 的定义有边缘差异，例如 U+001C；Python 的 Unicode 小写转换也可能展开字符，而 Go `strings.ToLower` 是按 rune 的简单映射。例如 U+0130 的转换需要区别对待。当前项目没有依赖这些写法的证据，不据此报分流错误。保留文档里“只在项目用到的写法上核对过”的限定即可；将来允许 Unicode 原始策略时再补差分测试或先统一成 ASCII／IDNA。

另一个模拟边界：`DomainTrie.search` 用 `rstrip('.')` 去掉全部尾点，内核 DNS 入口的单个根点处理与直接 `DomainTrie.Search` 不是同一接口。不要把“DNS 输入预处理 + 查找”包装函数称为内核 Search 的无条件逐字复刻。正常 DNS 名字和当前策略不受影响。

依据：[mihomo v1.19.31 component/trie/domain.go](https://github.com/MetaCubeX/mihomo/blob/v1.19.31/component/trie/domain.go)，`ValidAndSplitDomain`、`Search`。

### 5. GPL-2.0 文件头

r14 的主要缺口已补：数据副本和生成规则写明来源、许可、项目转换内容、首次日期；许可全文在仓库。当前规则正文相对 r14 未变，不将本次改动定性为已经发生的许可违规。

**仍建议调整后续日期方案。** 位置：`generator/strict.py:139–140`，现在说明后续改动日期去 Git 提交记录看。GPL-2.0 第 2(a) 款要求修改文件自身带有修改说明和日期；单独下载 `.list` 的人并不会同时取得 Git 历史。仅以“首次生成日期 + 将来看提交记录”作为长期机制不够稳妥。

建议使用独立的“此数据／转换内容最后修改日期”，只在数据正文、过滤结果或该修改声明真正变化时更新，而不是每次统一源出版本都更新。这样既保留内容未变时字节不变的设计，也让独立分发的文件包含日期。首次生成日期可继续保留。这是具体完善建议，不要求给整份配置强加许可证，也不是法律结论。

依据：[GNU GPL v2 第 2(a) 款官方原文](https://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)。

### 6. 分层、严格版假设、证据等级

- `generator/emit_mihomo.py:42–95` 的产品 DNS 分层在本轮未变。默认代理组的域名先于 geosite 集合处理；更具体的直连例外仍保留国内解析，默认直连组没有被本轮偷偷并入境外层。构建一致性及相关回归测试通过。
- `source/adblock.yaml:148` 新增后缀规则是“该主机及子域”，没有复制全局 keyword。`tools/check_upstream_evidence.py:265–290` 只把同值的上游关键词当作覆盖依据。源码 diff 和生成结果支持四端补拦结论。上游远程列表未来变化仍受原有快照／更新限制，不重复报。
- `dialer-proxy` 链式出口、节点 `ip-version` 仍不能算已完成运行覆盖；没有证据提升其验证等级。本轮也没有在真实节点上验证。
- `docs/02` 对 Loon 单独 GEOIP 加 no-resolve、订阅顺序，以及 QX 远程顺序／远程域名规则与本地 IP 规则的关系，仍区分了官方文字、社区做法和推断。更新 `update-interval` 的依据等级是正确的。没有新增官方真机证据可把其余假设升级为确定事实。
- QX 官方示例关于代理与解析的一般说明，不能直接证明每种出站协议的 UDP 路径；Loon 本轮也没有新增官方逐协议材料或真机实测。r15 的限定比 r14 准确。
- `docs/05` 明确区分仓库当次 Linux 运行事实、源码推断和设备未验证，整体合理。本报告没有把仓库记载的全部检查冒充成本轮运行。R15-F02 是遗漏在函数注释中的旧说法。

## 本轮验证清单与未完成边界

| 项目 | 本轮结果 |
|---|---|
| Git 提交定位 | full SHA 与要求的 dc90da7 一致；detached worktree，未动 main |
| `python3 build.py --check` | 通过，产物含 manifest 与统一源一致 |
| unittest discover，tests/ | **266 项，0 failure，0 error，0 skipped** |
| 记录器独立协议探针 | 正向对照通过；三个负向缺口已复现；domain+ip 合并通过 |
| r14→r15 数据／生成器 diff | 实际路由增量为 afpapi 补拦；DNS／分组未改变 |
| 官方 sing-box 动态最小复现 | 三个版本启动受限，未进入转发测试 |
| 122 类变异、完整官方真实数据核对 | 本轮未重跑；仓库已有记录仅作为被审核材料 |
| Loon／QX／SFA／CVR／CMFA 真机、真实性能、TUN | 本轮未验证 |

测试期间出现的“统一源错误”“缺文件”等输出来自测试故意注入的负向用例；最终测试汇总为全通过，不是项目真实生成失败。

建议先修 R15-F01，再清掉 R15-F02；其余建议可逐条处理。现有信息不足以要求重写 DNS 架构、撤销第 21 项决定或把国外域名交给国内 DNS。本报告不替代严格版发布地址可用性和真机验收；原文已写明的限制继续有效。

## 附：记录器反例的最小复现

在本次提交的仓库根目录运行以下 Python，不启动代理内核，不访问公网：

```python
import sys, socket, struct, time
sys.path.insert(0, 'tools')
import check_real_routes as t
r = t.Socks5Recorder()
r.start()
try:
    with socket.create_connection(('127.0.0.1', r.port)) as c:
        c.sendall(b'\x05\x01\x02')
        print('only method 02 offered:', t._recv_exact(c, 2).hex())
    with socket.create_connection(('127.0.0.1', r.port)) as c:
        c.sendall(b'\x05\x01\x00')
        t._recv_exact(c, 2)
        c.sendall(b'\x05\x03\x00\x01' + bytes(6))
        rep = t._recv_exact(c, 10)
        relay = (socket.inet_ntoa(rep[4:8]), struct.unpack('!H', rep[8:10])[0])
        def send(frag, host):
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as u:
                u.sendto(bytes([0, 0, frag, 3, len(host)]) + host.encode()
                         + struct.pack('!H', 443) + b'payload', relay)
            time.sleep(0.3)
        send(0, 'valid.example')
        send(1, 'fragment.example')
        c.close()
        send(0, 'afterclose.example')
    print(r.seen)
finally:
    r.close()
```

本轮输出：方法响应 `0500`；seen 同时含 `valid.example`、`fragment.example`、`afterclose.example` 三个域名。
