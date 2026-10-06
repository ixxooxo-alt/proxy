# proxy-routing

[中文](README.zh-CN.md)

**One rule source. Four clients. Every rule has a recorded source.**

A single, auditable split-routing (分流) rule set that generates matching configs for **Loon**, **Quantumult X**, **mihomo / Clash Meta** and **sing-box** from one place. You edit rules once in `source/`; the generator builds every client's config, so the clients never drift apart.

![clients](https://img.shields.io/badge/clients-Loon%20%7C%20Quantumult%20X%20%7C%20mihomo%20%7C%20sing--box-blue)
![tests](https://img.shields.io/badge/tests-244%20passing-brightgreen)
![python](https://img.shields.io/badge/python-3.10%2B-informational)
![status](https://img.shields.io/badge/real--device%20testing-not%20yet%20done-orange)

> **Bring your own subscription.** No nodes or subscription links ship with this repo. Every config uses the placeholder `https://REPLACE-ME.invalid/...`, and nothing connects until you replace it with your own subscription.

This README describes source version **2026.10.06-1**. The version is written in the header comment of every generated config and in `dist/manifest.json`; check it before importing. This version was first handed over as an archive for review and was not pushed to the GitHub repository straight away, so the repository may still hold an older version: go by `source_version` in `dist/manifest.json` on `main`. The badges above are static text, not a CI status: the tests were run locally on Linux (Python 3.11) on 2026-10-06 (UTC).

---

## ✨ Features

- **One source, many outputs.** `source/*.yaml` → `python3 build.py` → configs for Loon, Quantumult X, mihomo (profile + core) and sing-box (a 1.14 config and a 1.12-compatible one).
- **43 service groups**, including:
  - **AI:** OpenAI, Claude, Grok (Cursor and xAI share one group), Google AI, Copilot, Apple AI, Other AI
  - **Streaming:** YouTube, Netflix, Disney+, Max, Prime Video, Hulu US, Hulu Japan, Abema, DMM, Japanese media, Spotify, TikTok, Twitch, Bilibili HK/MO/TW, Bahamut, Other streaming
  - **Social:** Telegram, X, Meta, WhatsApp, LINE, Discord, Reddit, LinkedIn
  - **Big tech and dev:** Apple, Apple Music/TV, Apple Push (push notifications, direct by default), Google, Microsoft, GitHub, Dev downloads, Remote control
  - **Payments:** PayPal, pinned to a dedicated **US** node group
- **Region-aware routing.** Hong Kong, Japan, Korea, Taiwan, Singapore and US entry groups, plus "Other regions" (manual only). Unmatched overseas traffic goes to **Foreign Default**, which starts on Japan.
- **Nodes are sorted into regions by name**, from a word list in `source/regions.yaml` rather than hand-written regexes. Each region has two filters: a loose one for the manual group, and a strict one for the auto / failover / balance groups. A node whose name does not clearly say where it lands (`Japan-US 01`, `日本中转 01`, `🇯🇵 Relay 01`, `Premium 01 | Unlock US`) stays in the manual group only. Only a short list of relay wordings is recognised (`中转`, `中继`, `转`, `入口`, `relay`, `transit`, `via`, `经`); other wordings such as `Singapore Entry 01` are read as a landing node. Names are a first-pass filter; they do not prove where a node actually exits.
- **Manual-first failover (design goal).** Your hand-picked node is used first; if it goes down, the group switches to an available node *in the same region* and switches back when yours recovers, without jumping countries or going direct. mihomo is generated to this design (checked against its source). Loon's group nesting, Quantumult X's switch-back and the real switching times are not confirmed on devices yet. sing-box has no equivalent, so its region entries default to same-region auto.
- **Fails closed.** On mihomo, a region filter that matches no nodes rejects the traffic (`empty-fallback: REJECT`); on sing-box an empty group points to a blocking placeholder. Empty-group behaviour on Loon and Quantumult X is unverified.
- **China direct and LAN direct.** Mainland domains and IPs (GeoSite/GeoIP CN) and private ranges (`192.168.x.x`, `10.x`, `.lan`, `.local`, `home.arpa` …) connect directly, and LAN names are resolved by the system DNS.
- **Ad blocking.** A remote ad list per client family (`category-ads-all` on mihomo and sing-box, blackmatrix7 *AdvertisingLite* on Loon and Quantumult X), plus 71 local block rules and 10 false-positive exceptions. No rewrites, scripts or MITM are included.
- **Split DNS.** On mihomo and sing-box: fake-ip, domestic DoH (223.5.5.5; mihomo also 1.12.12.12) for direct traffic, foreign DoH through the proxy for the rest. Loon and Quantumult X use domestic DoH only, so in their standard configs domains that match no rule are resolved by a domestic resolver (see known limits and the strict variant below). AAAA answers are off by default.
- **Optional strict variant for Loon and Quantumult X** (`loon-strict.conf`, `quantumultx-strict.conf`). Domains that match no rule are not resolved locally and go straight to Foreign Default; mainland sites are recognised by a domestic domain list instead of by resolving them. The cost: a mainland site missing from the list goes through the proxy. Both variants share the same groups and can be switched in the app. The strict variants reference three rule files under `dist/…/rules/` on the repository's `main` branch, rely on rule-order assumptions the official docs do not fully state, and are **untested on devices**.
- **Policy-group icons.** On Loon, Quantumult X and mihomo-based clients each of the 82 policy groups carries an icon URL pointing to the owner's icon repository ([ixxooxo-alt/icon](https://github.com/ixxooxo-alt/icon)). Icons only affect how groups look. Set `enabled: false` in `source/icons.yaml` and rebuild to get the same configs without them.
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

Copy `source/local.example.yaml` to `source/local.yaml` to pin a PayPal node, register a verified Netflix node, add your own rules, or tell the generator which region an oddly named node belongs to. Updating the shared source won't overwrite it, and it only affects `dist/private/`.

To see which region group each of your nodes lands in, and why, run `python3 tools/check_node_names.py names.txt` (node names only; no subscription link needed).

## 🛠 Editing rules

1. Add or remove rules in `source/services/*.yaml`. Give each one an `ev` (evidence ID).
2. Run `python3 build.py`. If rules conflict, the build fails and no outputs change.
3. Run `python3 -m unittest discover -s tests`.

## 📂 Layout

```
source/      single source of truth (regions, groups, services, adblock, evidence, icons, strict-variant settings, domestic domain list)
generator/   emitters for Loon, Quantumult X, mihomo, sing-box
tests/       independent expectations + per-client match-semantics emulation
tools/       node-name report, official-core checks, upstream evidence checks, icon check, Clash connection-log analyzer
dist/        generated, shareable outputs (except dist/private/); loon/rules/ and quantumultx/rules/ hold the rule files the strict variants reference
docs/        requirements, syntax/capability matrix, DNS decisions, rule list, test records, known limits (Chinese)
```

## 📚 Rule sources and credits

- [v2fly/domain-list-community](https://github.com/v2fly/domain-list-community): pinned snapshot used as rule evidence, and as the source of the domestic domain list shipped for the strict variants (MIT; licence text in `source/data/`)
- [blackmatrix7/ios_rule_script](https://github.com/blackmatrix7/ios_rule_script): rule evidence, plus the *AdvertisingLite* ad list (Loon / Quantumult X) and *ChinaMax_Domain*, which the Loon strict variant subscribes to directly (its data is not copied into this repository)
- [MetaCubeX/meta-rules-dat](https://github.com/MetaCubeX/meta-rules-dat): GeoSite / GeoIP data for mihomo (downloaded at runtime via jsDelivr)
- [SagerNet/sing-geosite](https://github.com/SagerNet/sing-geosite) and [sing-geoip](https://github.com/SagerNet/sing-geoip): rule sets for sing-box
- Official service docs (OpenAI, Anthropic, Cursor, Google, Microsoft, GitHub, …), as recorded in `source/evidence.yaml`
- Policy-group icons: [ixxooxo-alt/icon](https://github.com/ixxooxo-alt/icon) (the images are not part of this repository)

Remote lists are fetched by the clients themselves and follow upstream, so the same config can match differently on different days.

## ✅ Verification status

- 244 automated tests pass. Field names in the mihomo and sing-box outputs were checked against mihomo v1.19.31 and sing-box v1.14.1 source. 559 community-sourced rules were checked one by one against pinned upstream snapshots.
- `mihomo -t` (v1.19.31) and `sing-box check` (v1.14.1 for the 1.14 config, v1.12.0 for the compatible one) pass on the generated configs. Other core versions, including sing-box 1.13 and the cores bundled with Clash Verge Rev, Clash Meta for Android and SFA, were not run.
- Routing was checked with the official cores and real upstream data files: 260 targets on mihomo v1.19.31 and on both sing-box versions, plus DNS decisions (22 on sing-box, 11 on mihomo) and dial-time resolver cases (12 on each core), all matching hand-written expectations. Outbounds were replaced with rejects and nothing left the machine, so this shows which group a connection is handed to, not connectivity. Loon and Quantumult X have no core that runs on a computer; for them (standard and strict variants) there is only an in-house emulator.
- “Proxied domains are not handed to a domestic resolver” (mihomo and sing-box only), checked with the official cores and stand-in DNS servers: a domain routed to a proxy group is not queried anywhere during the connection; a domain that matches no domain rule is queried at the foreign resolver only; with the foreign resolver made silent, neither core falls back to the domestic or system resolver. A sweep of every entry that goes to the domestic resolver found 5 hosts on sing-box and 364 on mihomo whose connections are nevertheless routed to a proxy group; they are recorded as known cases and left as open decisions (`docs/06`, items 14–16). These checks use a local proxy port, not TUN; queries the system sends outside the tunnel and browsers' own secure DNS are outside their scope.
- Node grouping by name: 625 hand-labelled names give the same result in Python, in ICU (the regex engine the Apple apps are assumed to use) and in the official mihomo core. None of them come from a real subscription.
- Seven rounds of external input so far (the seventh was a design review before this version was built, not an audit of it); findings and fixes are in `docs/08-外部审核记录.md`.
- **Not yet tested on real devices.** None of the configs has been imported into Loon, Quantumult X, Clash Verge Rev, Clash Meta for Android or SFA and checked in real use. See `docs/05-验收记录.md` and `docs/09-真机验收操作清单.md`.
- Most important open points (see `docs/06-已知限制与待决事项.md`): the two strict variants are new and wholly unverified on devices, and unusable until the repository's `main` branch carries this version's rule files; the client-side switches listed in `docs/01` (TUN, DNS override, strict route on Windows, Android Private DNS) were taken from source code and official docs and not checked in the apps; which mihomo core Clash Verge Rev / Clash Meta for Android bundle — resolving LAN-hosted proxy servers through the system DNS needs mihomo v1.19.20 or later, older cores ignore that field; whether Loon and Quantumult X accept the long region filters (12–16 KB each) and the icon parameter; whether Quantumult X applies `server-tag-regex` to its auto and balance policies; Loon's second ad-list file uses a format its official docs don't describe; Netflix unlock has no verification record yet; health-check and failover timings are design targets, not measurements.

## ⚠️ Disclaimer

This project contains routing rules only, with no proxy servers, nodes or accounts. You are responsible for following the laws of your jurisdiction and the terms of service of the networks and services you use. Provided as-is, without warranty.
