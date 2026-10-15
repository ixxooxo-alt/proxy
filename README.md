# proxy-routing

[中文](README.zh-CN.md)

**One rule source. Five clients. Every rule has a recorded source.**

A single, auditable split-routing (分流) rule set that generates matching configs for **Loon**, **Quantumult X**, **mihomo / Clash Meta**, **sing-box** and (since r16) **Stash** from one place. You edit rules once in `source/`; the generator builds every client's config, so the clients never drift apart.

![clients](https://img.shields.io/badge/clients-Loon%20%7C%20Quantumult%20X%20%7C%20mihomo%20%7C%20sing--box%20%7C%20Stash-blue)
![tests](https://img.shields.io/badge/tests-311%20passing-brightgreen)
![python](https://img.shields.io/badge/python-3.10%2B-informational)
![status](https://img.shields.io/badge/real--device%20testing-not%20yet%20done-orange)

> **Bring your own subscription.** No nodes or subscription links ship with this repo. Every config uses the placeholder `https://REPLACE-ME.invalid/...`, and nothing connects until you replace it with your own subscription.

This README describes source version **2026.10.15-1**. The version is written in the header comment of every generated config and in `dist/manifest.json`; check it before importing. This is r18. It answers an external review of r17 and runs the check the owner chose for item 22 of `docs/06`. The review found a race in the checking tools: the stand-in DNS servers were closed without waiting for their receiving thread, so a malformed query that had already arrived could be recorded only after the check had passed; the stand-ins and the local SOCKS5 receiver now finish what they have already received before the results are summarised (deterministic regression tests added), and the results with the fixed tools are the same as r17's. In the configs only comments changed: the header of the strict variants now says that domains matching no rule are not resolved locally *for rule matching* (the old wording promised more than that), and every header carries the new version; rules, DNS and groups are unchanged, and the two sing-box configs are byte-identical to r17. For item 22 the official sing-box 1.14.3 binary was run here: behind a selector or URL-test group it no longer drops UDP packets addressed to a domain name, and on the generated config everything else matches 1.14.1 (TUN was not tested; which version SFA runs on the owner's phone decides what, if anything, to change). r17, the version before, answered an external review of r16: every region filter in the two Stash configs now starts by excluding the built-in policy names DIRECT, REJECT and REJECT-DROP (Stash's docs say an empty proxy provider is replaced by DIRECT, and r16's “other regions” filter, which takes every name that matches none of the six regions, would have taken that DIRECT too — unverified on a device whether the app ever does this); the checking tools now record every malformed SOCKS5 request and unreadable DNS query instead of dropping some silently; the Stash DNS notes were narrowed (the reasons for not using `follow-rule` are untested costs, not impossibilities). Routing and DNS on Loon, Quantumult X, mihomo and sing-box are unchanged — their six text configs differ from r16 only in the version string in the header comment, and the two sing-box configs are byte-identical to r16. r16, the version before, added **two Stash configs** (`dist/stash/stash.yaml`, and an optional strict variant `stash-strict.yaml`), written from Stash's official documentation and never imported into the app, and it answers an external review of r15. That review led to changes in the checking tools and the documentation only: routing and DNS on Loon, Quantumult X, mihomo and sing-box are unchanged — their six text configs differ from r15 only in the version string in the header comment, and the two sing-box configs are byte-identical to r15; the header of the Quantumult X copy of the large upstream domestic list now also gives the date of the last change. While checking the review, sing-box 1.14.1 was found to drop UDP packets addressed to a domain name when they pass through a selector or URL-test group (SOCKS, Shadowsocks and Trojan outbounds; not VMess; not on 1.12.0 behind a selector); whether to work around it in the config is item 22 of `docs/06`, still left to the owner (the r16 review added a source-level explanation and found a matching fix in sing-box 1.14.3's source, not yet verified by running it), and the config is unchanged. r15, the version before, blocked one more Alimama ad host, `afpapi.alimama.com`, on all four clients of the time. r14 changed every client's config: mihomo's DNS policy sends the names of proxied products to the foreign resolver; the “国内直连” (domestic direct) group is fixed to DIRECT with no other choice; the eight names that need real addresses (time servers, carrier sign-in) are routed DIRECT on every client; Bilibili HK/MO/TW defaults to DIRECT; Umeng and Alimama are blocked only on the subdomains upstream marks as ads/tracking; three broad Apple AI rules were dropped; the separate “Netflix unlock entry” group is gone; on mihomo, dotless names and the upstream `private` set go to the system resolver; the Quantumult X strict variant gets a copy of the large upstream domestic list. None of r12–r18 was pushed to `main` straight away (each sits on a branch for review), so `main` may still hold an older version: go by `source_version` in `dist/manifest.json` on `main`. The badges above are static text, not a CI status: the tests were run on Linux (Python 3.13) in a cloud session on 2026-10-15 (UTC).

---

## ✨ Features

- **One source, many outputs.** `source/*.yaml` → `python3 build.py` → configs for Loon, Quantumult X, mihomo (profile + core), sing-box (a 1.14 config and a 1.12-compatible one) and Stash. The Stash config has the same rules, in the same order, and the same groups as the mihomo one; only the DNS section and the handling of empty groups differ.
- **43 service groups**, including:
  - **AI:** OpenAI, Claude, Grok (Cursor and xAI share one group), Google AI, Copilot, Apple AI, Other AI
  - **Streaming:** YouTube, Netflix, Disney+, Max, Prime Video, Hulu US, Hulu Japan, Abema, DMM, Japanese media, Spotify, TikTok, Twitch, Bilibili HK/MO/TW, Bahamut, Other streaming
  - **Social:** Telegram, X, Meta, WhatsApp, LINE, Discord, Reddit, LinkedIn
  - **Big tech and dev:** Apple, Apple Music/TV, Apple Push (push notifications, direct by default), Google, Microsoft, GitHub, Dev downloads, Remote control
  - **Payments:** PayPal, pinned to a dedicated **US** node group
- **Region-aware routing.** Hong Kong, Japan, Korea, Taiwan, Singapore and US entry groups, plus "Other regions" (manual only). Unmatched overseas traffic goes to **Foreign Default**, which starts on Japan.
- **Nodes are sorted into regions by name**, from a word list in `source/regions.yaml` rather than hand-written regexes. Each region has two filters: a loose one for the manual group, and a strict one for the auto / failover / balance groups. A node whose name does not clearly say where it lands (`Japan-US 01`, `日本中转 01`, `🇯🇵 Relay 01`, `Premium 01 | Unlock US`) stays in the manual group only. Only a short list of relay wordings is recognised (`中转`, `中继`, `转`, `入口`, `relay`, `transit`, `via`, `经`); other wordings such as `Singapore Entry 01` are read as a landing node. Names are a first-pass filter; they do not prove where a node actually exits.
- **Manual-first failover (design goal).** Your hand-picked node is used first; if it goes down, the group switches to an available node *in the same region* and switches back when yours recovers, without jumping countries or going direct. mihomo is generated to this design (checked against its source). Loon's group nesting, Quantumult X's switch-back and the real switching times are not confirmed on devices yet. sing-box has no equivalent, so its region entries default to same-region auto.
- **Fails closed.** On mihomo, a region filter that matches no nodes rejects the traffic (`empty-fallback: REJECT`); on sing-box an empty group points to a blocking placeholder. Stash's docs say a group with no proxies is treated as DIRECT, so each region gets a placeholder node that cannot connect (`香港·无可用节点` etc., pointing at port 1 on the device itself); a region with no nodes is left with only that placeholder and fails instead of going direct, and since r17 no region filter accepts the names DIRECT, REJECT or REJECT-DROP. A failing placeholder is not proof that nothing goes direct: what the app does when a whole subscription is empty, cached or partly failed is untested. Empty-group behaviour on Loon and Quantumult X, and all of this on Stash, is unverified on devices.
- **China direct and LAN direct.** Mainland domains and IPs (GeoSite/GeoIP CN) and private ranges (`192.168.x.x`, `10.x`, `.lan`, `.local`, `home.arpa` …) connect directly, and LAN names are resolved by the system DNS.
- **Ad blocking.** A remote ad list per client family (`category-ads-all` on mihomo, sing-box and Stash, blackmatrix7 *AdvertisingLite* on Loon and Quantumult X), plus 71 local block rules and 10 false-positive exceptions. No rewrites, scripts or MITM are included.
- **Split DNS.** On mihomo and sing-box: fake-ip, domestic DoH (223.5.5.5; mihomo also 1.12.12.12) for direct traffic, foreign DoH through the proxy for the rest. Loon, Quantumult X and Stash use domestic DoH only, so in their standard configs domains that match no rule are resolved by a domestic resolver (see known limits and the strict variant below). On Stash (always fake-ip, per its docs) proxied TCP hands the domain to the node, and proxied UDP is resolved through the proxy at 1.0.0.1 by default; Stash's option to send DNS queries along the rules (`follow-rule`) is not used, for reasons given in `docs/03`. AAAA answers are off by default on mihomo, sing-box and Quantumult X (`no-ipv6`); Stash's docs say its tunnel is IPv4-only by default.
- **Optional strict variant for Loon, Quantumult X and Stash** (`loon-strict.conf`, `quantumultx-strict.conf`, `stash-strict.yaml`). Connections whose domain matches no rule are not resolved locally for rule matching and go straight to Foreign Default (queries apps send themselves, non-A/AAAA types and how a proxy protocol relays UDP are outside that promise); mainland sites are recognised by a domestic domain list instead of by resolving them. The cost: a mainland site missing from the list goes through the proxy. Both variants share the same groups and can be switched in the app. The Loon and Quantumult X strict variants reference rule files under `dist/…/rules/` on the repository's `main` branch (one for Loon, three for Quantumult X) and rely on rule-order assumptions the official docs do not fully state; the Stash one subscribes to an upstream list directly (blackmatrix7's *ChinaMax_Domain_For_Clash*). All three are **untested on devices**.
- **Policy-group icons.** On Loon, Quantumult X, mihomo-based clients and Stash each of the 81 policy groups carries an icon URL pointing to the owner's icon repository ([ixxooxo-alt/icon](https://github.com/ixxooxo-alt/icon)). Icons only affect how groups look. Set `enabled: false` in `source/icons.yaml` and rebuild to get the same configs without them.
- **Safe defaults.** In the core config the controller listens on `127.0.0.1:9090`, `allow-lan` is `false`, and TUN is off.
- **A recorded source for every rule.** Each rule carries an evidence ID (official docs, a pinned community snapshot, or a maintainer note). The generator stops with an error on duplicate ownership or shadowed rules instead of silently producing output.
- **Private builds stay private.** Configs built with your subscription go to `dist/private/`, never to the shareable `dist/` outputs. `dist/private/` and `source/local.yaml` are listed in `.gitignore`.

## 📱 Supported clients

| Device / client | File | Before importing |
|---|---|---|
| iPhone / iPad / Mac: **Loon** (3.0.3+) | `dist/loon/loon.conf` (standard) or `dist/loon/loon-strict.conf` (strict, optional) | Replace the placeholder under `[Remote Proxy]` with your subscription |
| iPhone / iPad / Mac: **Quantumult X** | `dist/quantumultx/quantumultx.conf` (standard) or `dist/quantumultx/quantumultx-strict.conf` (strict, optional) | Replace the placeholder under `[server_remote]` |
| Windows / macOS: **Clash Verge Rev** | `dist/mihomo/mihomo-profile.yaml` | Replace `url` under `proxy-providers`; use TUN mode and keep the app's “DNS override” (DNS 覆写) switch off so the profile's own `dns:` section is used; the full list of switches to check by hand is in `docs/01` (none of it verified in the app) |
| Android: **Clash Meta for Android** | `dist/mihomo/mihomo-profile.yaml` | Same as above |
| Linux / router: **mihomo core** | `dist/mihomo/mihomo-core.yaml` | Same as above (includes local ports and controller; TUN off) |
| Android: **SFA (sing-box)** | Build locally (see below) | sing-box can't use subscriptions, so nodes must be written into the config |
| iPhone / iPad / Mac: **Stash** (added in r16) | `dist/stash/stash.yaml` (standard) or `dist/stash/stash-strict.yaml` (strict, optional) | Replace `url` under `proxy-providers` with your subscription (Clash / Stash format). **Never tried in the app**: first check that each region's groups contain nodes, as in section “1c. Stash” of `docs/09` |

## 🚀 Quick start

### Option A: import a ready-made file

1. Download the file for your client from the table above.
2. Replace `https://REPLACE-ME.invalid/请替换为你的订阅链接` with **your own** subscription URL (or import first and change the subscription inside the app).
3. Import it into your client and pick a node in each region's "manual" group.

> Don't commit or share a file once your subscription is in it.

### Option B: build with your subscription (also needed for sing-box)

Requires Python 3.10+ and PyYAML.

```bash
pip install pyyaml

# read -s keeps the subscription out of your shell history
read -rs SUB_URLS && export SUB_URLS
python3 build.py                                  # public outputs -> dist/, private outputs -> dist/private/

# sing-box (SFA): convert a Clash/mihomo subscription into sing-box outbounds
python3 build.py --singbox-sub-url "$SUB_URLS"    # or: --singbox-nodes downloaded-sub.yaml
```

The node converter only accepts nodes it can represent exactly. Unsupported protocols or parameters are skipped and listed in `dist/private/sing-box-节点转换报告.txt`. TLS checks are never loosened.

### Customize without losing updates

Copy `source/local.example.yaml` to `source/local.yaml` to pin a PayPal node, add your own rules, or tell the generator which region an oddly named node belongs to. Updating the shared source won't overwrite it, and it only affects `dist/private/`.

To see which region group each of your nodes lands in, and why, run `python3 tools/check_node_names.py names.txt` (node names only; no subscription link needed).

## 🛠 Editing rules

1. Add or remove rules in `source/services/*.yaml`. Give each one an `ev` (evidence ID).
2. Run `python3 build.py`. If rules conflict, the build fails and no outputs change.
3. Run `python3 -m unittest discover -s tests`.

## 📂 Layout

```
source/      single source of truth (regions, groups, services, adblock, evidence, icons, strict-variant settings, domestic domain lists)
generator/   emitters for Loon, Quantumult X, mihomo, sing-box, Stash
tests/       independent expectations + per-client match-semantics emulation
tools/       node-name report, official-core checks, upstream evidence checks, icon check, Clash connection-log analyzer
dist/        generated, shareable outputs (except dist/private/); loon/rules/ and quantumultx/rules/ hold the rule files the Loon / Quantumult X strict variants reference; stash/ holds the two Stash configs
docs/        requirements, syntax/capability matrix, DNS decisions, rule list, test records, known limits (Chinese)
```

## 📚 Rule sources and credits

- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community): pinned snapshot used as rule evidence, and as the source of the domestic domain list shipped for the strict variants (MIT; licence text in `source/data/`)
- [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script): rule evidence, plus the *AdvertisingLite* ad list (Loon / Quantumult X) and *ChinaMax_Domain*, which the Loon strict variant subscribes to directly (the Stash strict variant subscribes to its Clash edition, *ChinaMax_Domain_For_Clash*); since r14 a copy of a pinned snapshot of it, converted to Quantumult X syntax, is shipped for the Quantumult X strict variant (`source/data/cn-domains-max.txt`, `dist/quantumultx/rules/cn-domains-max.list`; GPL-2.0, licence text in `source/data/LICENSE-ios_rule_script.txt`)
- [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat): GeoSite / GeoIP data for mihomo (downloaded at runtime via jsDelivr)
- [SagerNet/sing-geosite](https://github.com/SagerNet/sing-geosite) and [sing-geoip](https://github.com/SagerNet/sing-geoip): rule sets for sing-box
- Stash's `GEOSITE` rules use v2fly/domain-list-community data that the app itself downloads from github.com on first use (per its docs); its GeoIP database ships with the app
- Official service docs (OpenAI, Anthropic, Cursor, Google, Microsoft, GitHub, …), as recorded in `source/evidence.yaml`
- Policy-group icons: [ixxooxo-alt/icon](https://github.com/ixxooxo-alt/icon) (the images are not part of this repository)

Remote lists are fetched by the clients themselves and follow upstream, so the same config can match differently on different days.

## ✅ Verification status

- 311 automated tests pass. Field names in the mihomo and sing-box outputs were checked against mihomo v1.19.31 and sing-box v1.14.1 source. 561 community-sourced rules were checked one by one against pinned upstream snapshots.
- `mihomo -t` (v1.19.31) and `sing-box check` (v1.14.1 for the 1.14 config, v1.12.0 for the compatible one) pass on the generated configs. Other core versions, including sing-box 1.13 and the cores bundled with Clash Verge Rev, Clash Meta for Android and SFA, were not run.
- Routing was checked with the official cores and real upstream data files: 270 targets on mihomo v1.19.31 and on both sing-box versions, plus DNS decisions (22 on sing-box, 15 on mihomo), dial-time resolver cases (12 on each core) and outbound-side resolution (8 hosts, over TCP and UDP through SOCKS and over WireGuard; the SOCKS outbound is a local SOCKS5 receiver that records whether the node got the name, an address or nothing — since r16 it refuses what RFC 1928 says to refuse, such as fragmented UDP datagrams and packets after the control connection closes — and the default-direct groups are checked again after being switched to a proxy), all matching hand-written expectations. Outbounds were replaced with rejects and nothing left the machine, so this shows which group a connection is handed to, not connectivity. Loon, Quantumult X and Stash have no core that runs on a computer; for them (standard and strict variants) there is only an in-house emulator. For Stash the emulator applies the mihomo rule semantics (the rules are the same, line for line) and approximates Stash's own `GEOSITE` data with SagerNet's rule sets.
- “Proxied domains are not handed to a domestic resolver” (mihomo and sing-box only), checked with the official cores and stand-in DNS servers: a domain routed to a proxy group is not queried anywhere during the connection; a domain that matches no domain rule is queried at the foreign resolver only; with the foreign resolver made silent (the only failure mode tried), neither core falls back to the domestic or system resolver. Since r14 the check also covers the outbound side: mihomo resolves the target locally when it relays UDP through almost any proxy protocol and for WireGuard-type outbounds, so mihomo's DNS policy now sends proxied products' names to the foreign resolver (r13 sent some, e.g. `qwen.ai`, to the domestic one). A sweep of representative hosts for every entry that goes to the domestic resolver now finds none on either core whose connection is nevertheless routed to a proxy group (r13: 5 on sing-box, 364 on mihomo; the three kinds were fixed in r14 — counts for that day's upstream data and that sampling, not a proof over all domains). The r15 receiver showed that sing-box 1.14.1 did not send UDP packets addressed to a domain name through a SOCKS outbound; r16 traced this to the group layer: behind a selector or URL-test group, SOCKS, Shadowsocks and Trojan outbounds drop such packets (log: “unsupported address”), VMess does not; 1.12.0 does not behind a selector (it did drop one, with no log line, behind a URL-test group with SOCKS — cause not traced). No resolver saw the name, so it is not a leak, but UDP (QUIC and the like) to proxied sites probably does not get through on SFA — item 22 of `docs/06`, waiting for the owner's decision. The r16 review traced it in the source: the group wraps the UDP connection in a type that keeps only the plain `net.PacketConn` interface, so the domain-name address is lost (the first two steps were checked here against the v1.14.1 source; sing-box 1.14.3 changes that wrapper). In r18 the official 1.14.3 binary was run here: behind a selector or URL-test group SOCKS, Shadowsocks, Trojan and VMess all sent the packet addressed to a domain name, and on the generated config the node received the domain name where 1.14.1 sent nothing; everything else matched 1.14.1. TUN with fake IPs, the path the phone uses, was not tested. These checks use a local proxy port, not TUN; queries the system sends outside the tunnel and browsers' own secure DNS are outside their scope.
- Node grouping by name: 632 hand-labelled names (seven of them, added in r16, are the Stash placeholder names, which must land only in their own region) give the same result in Python, in ICU (the regex engine the Apple apps are assumed to use) and in the official mihomo core. None of them come from a real subscription. Which regex engine Stash uses for `filter` is not documented; if it lacks lookaround the region filters will not work (`docs/06`).
- Thirteen rounds of external input so far (the seventh was a design review before r12 was built; the thirteenth is the audit of r17 that this version answers); findings and fixes are in `docs/08-外部审核记录.md`.
- **Not yet tested on real devices.** None of the configs has been imported into Loon, Quantumult X, Clash Verge Rev, Clash Meta for Android, SFA or Stash and checked in real use. See `docs/05-验收记录.md` and `docs/09-真机验收操作清单.md`.
- Most important open points (see `docs/06-已知限制与待决事项.md`): the Stash configs (new in r16) were written from Stash's documentation (42 pages, its llms.txt and the example config, downloaded on the owner's behalf; this machine cannot reach stash.wiki, and the r16 reviewer found all 44 items identical to the site that day) and never imported — the regex engine for region filters, where the placeholder nodes sort within a group (if first, the manual groups and “PayPal·美国固定” start on a placeholder that cannot connect until you pick a node), what happens when a subscription is empty (first download failed, cached update failed, one of several failed, or no nodes — four cases in `docs/09`), and the first-use download of `GEOSITE` data from github.com all need checking on a device (`docs/09`, section 1c); sing-box 1.14.1's UDP drop behind groups (item 22; gone on 1.14.3 in the local test, so first check which version SFA runs); the three strict variants are wholly unverified on devices, and the Loon and Quantumult X ones are unusable until the repository's `main` branch carries this version's rule files; the client-side switches listed in `docs/01` (TUN, DNS override, strict route on Windows, Android Private DNS) were taken from source code and official docs and not checked in the apps; mihomo's `system` resolver is not guaranteed to be your router — on macOS with Clash Verge Rev's TUN on, the app points the system DNS at 114.114.114.114, so LAN names likely fail to resolve (inferred from source, untested); whether Loon and Quantumult X resolve targets locally when relaying UDP is not known (Quantumult X's official sample says, without singling out UDP, that resolved addresses are only used for rule matching and direct connections; Loon's docs say nothing); on mihomo, names in the upstream domestic set that belong to a default-direct group (`api.bilibili.com`, `www.apple.com.cn`) still go to the domestic resolver for UDP and WireGuard after you switch the group to a proxy — item 21 of `docs/06`, where the owner chose to keep this as a known limitation; which mihomo core Clash Verge Rev / Clash Meta for Android bundle — resolving LAN-hosted proxy servers through the system DNS needs mihomo v1.19.20 or later, older cores ignore that field; whether Loon and Quantumult X accept the long region filters (12–16 KB each) and the icon parameter; whether Quantumult X applies `server-tag-regex` to its auto and balance policies; Loon's second ad-list file uses a format its official docs don't describe; Netflix uses ordinary region groups, so whether a node unlocks it is up to you; health-check and failover timings are design targets, not measurements.

## ⚠️ Disclaimer

This project contains routing rules only, with no proxy servers, nodes or accounts. You are responsible for following the laws of your jurisdiction and the terms of service of the networks and services you use. Provided as-is, without warranty.
