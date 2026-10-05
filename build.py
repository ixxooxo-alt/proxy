#!/usr/bin/env python3
"""从统一源生成四个客户端的配置。

用法：
  python3 build.py                         生成公开产物到 dist/（订阅为占位符，可分享）
  python3 build.py --check                 只检查 dist/ 是否与统一源一致（含 manifest.json，不写文件）
  python3 build.py --sub-url URL [...]     额外生成已填好订阅的私密产物到 dist/private/（勿分享）
  python3 build.py --singbox-nodes 订阅.yaml      把 Clash/mihomo 格式订阅转换成 sing-box 节点，写入 dist/private/
                                                  （同时写出 节点分组报告.txt：每个节点按名称进了哪个地区组）
  python3 build.py --singbox-sub-url URL          同上，直接在本机下载订阅（UA: clash.meta）
订阅链接也可以放在环境变量 SUB_URLS（多个用英文逗号分隔），避免留在命令历史里。

source/local.yaml（个人覆盖：固定节点、已验证解锁节点、公司内网等）只进入 dist/private/，公开产物始终不含它。

生成是“全部成功才替换”：先在内存里生成全部公开和私密文件并做结构检查，任何一步失败都不改动现有产物；
写入时先写临时文件，全部写好再逐个替换，替换中途出错会把已替换的文件恢复成旧版本。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from generator import emit_loon, emit_mihomo, emit_qx, emit_singbox, nodes as nodeconv, regions, verify  # noqa: E402
from generator.audit import render_audit  # noqa: E402
from generator.model import SourceError, build_plan, load  # noqa: E402
from generator.util import sha256_text  # noqa: E402

GENERATOR_VERSION = "1.4.0"

PUBLIC_OUTPUTS = {
    "mihomo/mihomo-profile.yaml": lambda m, p: emit_mihomo.build(m, p, "profile"),
    "mihomo/mihomo-core.yaml": lambda m, p: emit_mihomo.build(m, p, "core"),
    "sing-box/sing-box-1.14.json": lambda m, p: emit_singbox.build(m, p, "1.14"),
    "sing-box/sing-box-1.12.json": lambda m, p: emit_singbox.build(m, p, "1.12"),
    "loon/loon.conf": lambda m, p: emit_loon.build(m, p),
    "quantumultx/quantumultx.conf": lambda m, p: emit_qx.build(m, p),
}
PRIVATE_NOTE = "本目录包含你的订阅链接、节点凭据或个人覆盖（local.yaml），只用于导入自己的设备，不要上传、提交或发给别人。\n"


def render_public(model, plan, root: str = ROOT) -> dict:
    files = {path: fn(model, plan) for path, fn in PUBLIC_OUTPUTS.items()}
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "source_version": model.project["project"]["source_version"],
        "docs_checked": str(model.project["project"]["docs_checked"]),
        "source_sha256": source_digest(root),
        "rule_counts": {
            "lan_and_system": len(plan.lan),
            "ad_exceptions": len(plan.exceptions),
            "ads_local": len(plan.ads_local),
            "product": len(plan.product),
            "service_ip": len(plan.service_ip),
            # 部分服务只写进某些客户端（例如国内常用网站不写进 Loon / QX，原因见 docs/06）
            "product_by_client": {f: len(plan.product_for(f)) for f in ("mihomo", "singbox", "loon", "quantumultx")},
        },
        "outputs": {path: sha256_text(text) for path, text in sorted(files.items())},
        "targets": model.project["targets"],
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return files


def _source_files(root: str = ROOT) -> list:
    """统一源 + 生成器 + 本文件，返回按相对路径排序的 [(相对路径, 内容)]。不含 source/local.yaml（个人覆盖）。
    路径统一用 “/”，读文件时换行统一为 LF，所以同一份源在 Windows、macOS、Linux 上得到相同的摘要。"""
    parts = []
    for base in ("source", "generator"):
        for dirpath, _, names in os.walk(os.path.join(root, base)):
            for n in names:
                if n.endswith((".yaml", ".py")) and not (base == "source" and n == "local.yaml"):
                    fp = os.path.join(dirpath, n)
                    rel = os.path.relpath(fp, root).replace(os.sep, "/")
                    with open(fp, encoding="utf-8") as f:       # 文本模式读取会把 CRLF 转成 LF
                        parts.append((rel, f.read()))
    with open(os.path.abspath(__file__), encoding="utf-8") as f:   # 生成流程与 manifest 也由本文件决定（审核 F10）
        parts.append(("build.py", f.read()))
    return sorted(parts)


def source_digest(root: str = ROOT) -> str:
    return sha256_text("\n".join(rel + "\n" + text for rel, text in _source_files(root)))


def display_path(path: str, root: str = ROOT) -> str:
    """尽量显示相对项目根目录的路径；Windows 上跨盘符时 relpath 会报错，退回绝对路径。"""
    try:
        return os.path.relpath(path, root)
    except ValueError:
        return os.path.abspath(path)


def same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def write_all(writes: dict) -> None:
    """writes：{绝对路径: 内容}。全部成功才生效（审核 F07）：
    1. 每个文件先写到同目录的临时文件；任何一个写失败，删掉全部临时文件，原文件一个不动。
    2. 全部写好后逐个替换，替换前把旧文件改名备份；中途出错就把已替换的恢复成备份、删掉新增的文件。
    3. 全部替换成功后删除备份。
    进程被强行终止或断电时仍可能留下 .bak / .new 文件，可以手动恢复或删除。"""
    tag = f"{os.getpid()}"
    staged = []
    try:
        for path, text in writes.items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = f"{path}.new-{tag}"
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            staged.append((path, tmp))
    except Exception:
        for _, tmp in staged:
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    done = []      # (path, backup 或 None)
    try:
        for path, tmp in staged:
            backup = None
            if os.path.exists(path):
                backup = f"{path}.bak-{tag}"
                os.replace(path, backup)
            done.append((path, backup))
            os.replace(tmp, path)
    except Exception:
        for path, backup in reversed(done):
            if backup:
                os.replace(backup, path)
            elif os.path.exists(path):
                os.remove(path)
        for _, tmp in staged:
            if os.path.exists(tmp):
                os.remove(tmp)
        raise
    for _, backup in done:
        if backup and os.path.exists(backup):
            os.remove(backup)


def _private_manifest(public_manifest: str, private: dict, root: str) -> str:
    local_path = os.path.join(root, "source", "local.yaml")
    local_sha = None
    if os.path.exists(local_path):
        with open(local_path, "rb") as f:
            local_sha = hashlib.sha256(f.read()).hexdigest()
    pub = json.loads(public_manifest)
    return json.dumps({
        "generator_version": pub["generator_version"],
        "source_version": pub["source_version"],
        "source_sha256": pub["source_sha256"],
        "local_yaml_sha256": local_sha,
        "outputs": {k: sha256_text(v) for k, v in sorted(private.items())},
    }, ensure_ascii=False, indent=2) + "\n"


def main(argv=None, root: str = ROOT) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sub-url", action="append", default=[])
    ap.add_argument("--singbox-nodes")
    ap.add_argument("--singbox-sub-url")
    ap.add_argument("--out", default=os.path.join(root, "dist"))
    a = ap.parse_args(argv)

    # ---------- 1. 公开模型（不含 local.yaml） ----------
    try:
        model = load(root, include_local=False)
        plan = build_plan(model)
    except SourceError as e:
        print(e, file=sys.stderr)
        print("统一源有错误，未改动任何产物。", file=sys.stderr)
        return 2
    files = render_public(model, plan, root)

    if a.check:
        drift = []
        for rel, text in files.items():          # 含 manifest.json（审核 F10：以前跳过了它）
            path = os.path.join(a.out, rel)
            if not os.path.exists(path):
                drift.append(rel + "（缺失）")
                continue
            with open(path, encoding="utf-8") as f:
                if f.read() != text:
                    drift.append(rel)
        if drift:
            print("以下产物与统一源不一致，需要重新生成：\n  " + "\n  ".join(drift))
            return 1
        print("产物与统一源一致（含 manifest.json）。")
        return 0

    # ---------- 2. 私密产物（订阅、节点、local.yaml），全部在内存里生成 ----------
    private = {}
    has_local = os.path.exists(os.path.join(root, "source", "local.yaml"))
    sub_urls = [u for u in a.sub_url if u]
    sub_urls += [u.strip() for u in os.environ.get("SUB_URLS", "").split(",") if u.strip()]
    try:
        pmodel, pplan = model, plan
        if has_local:
            pmodel = load(root, include_local=True)
            pplan = build_plan(pmodel)
        if sub_urls or has_local:
            subs = sub_urls or None
            private["mihomo-profile.yaml"] = emit_mihomo.build(pmodel, pplan, "profile", subs)
            private["mihomo-core.yaml"] = emit_mihomo.build(pmodel, pplan, "core", subs)
            private["loon.conf"] = emit_loon.build(pmodel, pplan, subs)
            private["quantumultx.conf"] = emit_qx.build(pmodel, pplan, subs)
        if a.singbox_nodes or a.singbox_sub_url:
            if a.singbox_nodes:
                with open(a.singbox_nodes, encoding="utf-8") as f:
                    text = f.read()
            else:
                text = nodeconv.fetch_subscription(a.singbox_sub_url)
            proxies = nodeconv.load_clash_proxies(text)
            converted, report, renamed = nodeconv.convert(proxies, emit_singbox.reserved_tags(pmodel))
            private["sing-box-1.14.json"] = emit_singbox.build(pmodel, pplan, "1.14", converted, renamed)
            private["sing-box-1.12.json"] = emit_singbox.build(pmodel, pplan, "1.12", converted, renamed)
            empty = [o["tag"] for o in json.loads(private["sing-box-1.14.json"])["outbounds"]
                     if o.get("type") in ("selector", "urltest") and o.get("outbounds") == [emit_singbox.PLACEHOLDER_TAG]]
            skipped = len(proxies) - len(converted)
            lines = [f"共 {len(proxies)} 个节点，转换 {len(converted)} 个（其中改名 {len(renamed)} 个），跳过 {skipped} 个。"]
            lines += report
            if empty:
                lines.append("")
                lines.append(f"以下组没有匹配到任何节点，已指向“{emit_singbox.PLACEHOLDER_TAG}”（拒绝连接，不会直连）：")
                lines += [f"  {t}" for t in empty]
            private["sing-box-节点转换报告.txt"] = "\n".join(lines) + "\n"
            print(f"sing-box：转换 {len(converted)}/{len(proxies)} 个节点；{len(empty)} 个组没有节点。"
                  "详情见 sing-box-节点转换报告.txt")
            # 这份订阅里每个节点按名称进了哪个地区组（四个客户端用的是同一套规则；只用到节点名称）
            names = list(dict.fromkeys(str(p["name"]) for p in proxies if isinstance(p, dict) and p.get("name") is not None))
            rep_lines, stats = regions.render_report(pmodel.region_spec, names, show_all=True)
            private["节点分组报告.txt"] = "\n".join(rep_lines) + "\n"
            print(f"节点分组：没认出地区 {stats['unrecognized']} 个，说不清落地 {stats['ambiguous']} 个，"
                  f"当成提示行（不进任何组）{stats['info']} 个。详情见 节点分组报告.txt")
        elif has_local:
            private["sing-box-1.14.json"] = emit_singbox.build(pmodel, pplan, "1.14")
            private["sing-box-1.12.json"] = emit_singbox.build(pmodel, pplan, "1.12")
    except SourceError as e:
        print(e, file=sys.stderr)
        print("local.yaml 有错误，未改动任何产物。", file=sys.stderr)
        return 2
    except Exception as e:           # 订阅下载失败、节点文件损坏等
        print(f"生成私密产物失败：{type(e).__name__}: {e}", file=sys.stderr)
        print("未改动任何产物（公开产物也没有更新）。", file=sys.stderr)
        return 3

    # ---------- 3. 写盘前的结构检查（审核 F09） ----------
    problems = verify.check_outputs(files) + verify.check_outputs({f"private/{k}": v for k, v in private.items()})
    if problems:
        print("生成的配置结构有问题，未改动任何产物：\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2

    # ---------- 4. 一次性写入 ----------
    writes = {os.path.join(a.out, rel): text for rel, text in files.items()}
    if same_path(a.out, os.path.join(root, "dist")):
        writes[os.path.join(root, "docs", "04-规则清单与证据.md")] = render_audit(model, plan)
    if private:
        pdir = os.path.join(a.out, "private")
        private["manifest.json"] = _private_manifest(files["manifest.json"], private, root)
        private["请勿分享.txt"] = PRIVATE_NOTE
        writes.update({os.path.join(pdir, rel): text for rel, text in private.items()})
    try:
        write_all(writes)
    except OSError as e:
        print(f"写入失败，已恢复原有产物：{e}", file=sys.stderr)
        return 4
    print(f"已生成 {len(files)} 个公开产物到 {display_path(a.out, root)}（订阅为占位符）")
    if private:
        why = "、".join(x for x, on in (("订阅", bool(sub_urls)), ("节点", bool(a.singbox_nodes or a.singbox_sub_url)),
                                        ("local.yaml", has_local)) if on)
        print(f"私密产物已写入 {display_path(os.path.join(a.out, 'private'), root)}（含{why}，请勿分享）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
