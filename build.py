#!/usr/bin/env python3
"""从统一源生成四个客户端的配置。

用法：
  python3 build.py                         生成公开产物到 dist/（订阅为占位符，可分享）
  python3 build.py --check                 只检查 dist/ 是否与统一源一致（不写文件）
  python3 build.py --sub-url URL [...]     额外生成已填好订阅的私密产物到 dist/private/（勿分享）
  python3 build.py --singbox-nodes 订阅.yaml      把 Clash/mihomo 格式订阅转换成 sing-box 节点，写入 dist/private/
  python3 build.py --singbox-sub-url URL          同上，直接在本机下载订阅（UA: clash.meta）
订阅链接也可以放在环境变量 SUB_URLS（多个用英文逗号分隔），避免留在命令历史里。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from generator import emit_loon, emit_mihomo, emit_qx, emit_singbox, nodes as nodeconv  # noqa: E402
from generator.audit import write_audit  # noqa: E402
from generator.model import SourceError, build_plan, load  # noqa: E402
from generator.util import sha256_text  # noqa: E402

GENERATOR_VERSION = "1.0.0"

PUBLIC_OUTPUTS = {
    "mihomo/mihomo-profile.yaml": lambda m, p: emit_mihomo.build(m, p, "profile"),
    "mihomo/mihomo-core.yaml": lambda m, p: emit_mihomo.build(m, p, "core"),
    "sing-box/sing-box-1.14.json": lambda m, p: emit_singbox.build(m, p, "1.14"),
    "sing-box/sing-box-1.12.json": lambda m, p: emit_singbox.build(m, p, "1.12"),
    "loon/loon.conf": lambda m, p: emit_loon.build(m, p),
    "quantumultx/quantumultx.conf": lambda m, p: emit_qx.build(m, p),
}


def render_public(model, plan) -> dict:
    files = {path: fn(model, plan) for path, fn in PUBLIC_OUTPUTS.items()}
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "source_version": model.project["project"]["source_version"],
        "docs_checked": str(model.project["project"]["docs_checked"]),
        "source_sha256": source_digest(),
        "rule_counts": {
            "lan_and_system": len(plan.lan),
            "ad_exceptions": len(plan.exceptions),
            "ads_local": len(plan.ads_local),
            "product": len(plan.product),
            "service_ip": len(plan.service_ip),
        },
        "outputs": {path: sha256_text(text) for path, text in sorted(files.items())},
        "targets": model.project["targets"],
    }
    files["manifest.json"] = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    return files


def _source_files() -> list:
    """统一源 + 生成器文件，返回按相对路径排序的 [(相对路径, 内容)]。
    路径统一用 “/”，读文件时换行统一为 LF，所以同一份源在 Windows、macOS、Linux 上得到相同的摘要。"""
    parts = []
    for base in ("source", "generator"):
        for dirpath, _, names in os.walk(os.path.join(ROOT, base)):
            for n in names:
                if n.endswith((".yaml", ".py")):
                    fp = os.path.join(dirpath, n)
                    rel = os.path.relpath(fp, ROOT).replace(os.sep, "/")
                    with open(fp, encoding="utf-8") as f:       # 文本模式读取会把 CRLF 转成 LF
                        parts.append((rel, f.read()))
    return sorted(parts)


def source_digest() -> str:
    return sha256_text("\n".join(rel + "\n" + text for rel, text in _source_files()))


def display_path(path: str) -> str:
    """尽量显示相对项目根目录的路径；Windows 上跨盘符时 relpath 会报错，退回绝对路径。"""
    try:
        return os.path.relpath(path, ROOT)
    except ValueError:
        return os.path.abspath(path)


def same_path(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def write_files(base: str, files: dict) -> None:
    for rel, text in files.items():
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)       # 原子替换：生成失败时保留上一份有效产物


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--sub-url", action="append", default=[])
    ap.add_argument("--singbox-nodes")
    ap.add_argument("--singbox-sub-url")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    a = ap.parse_args(argv)

    try:
        model = load(ROOT)
        plan = build_plan(model)
    except SourceError as e:
        print(e, file=sys.stderr)
        print("统一源有错误，未改动任何产物。", file=sys.stderr)
        return 2

    files = render_public(model, plan)

    if a.check:
        drift = []
        for rel, text in files.items():
            path = os.path.join(a.out, rel)
            if rel == "manifest.json":
                continue
            if not os.path.exists(path) or open(path, encoding="utf-8").read() != text:
                drift.append(rel)
        if drift:
            print("以下产物与统一源不一致，需要重新生成：\n  " + "\n  ".join(drift))
            return 1
        print("产物与统一源一致。")
        return 0

    write_files(a.out, files)
    if same_path(a.out, os.path.join(ROOT, "dist")):
        write_audit(model, plan, os.path.join(ROOT, "docs", "04-规则清单与证据.md"))
    print(f"已生成 {len(files)} 个公开产物到 {display_path(a.out)}（订阅为占位符）")

    sub_urls = [u for u in a.sub_url if u]
    env = os.environ.get("SUB_URLS", "")
    sub_urls += [u.strip() for u in env.split(",") if u.strip()]
    private = {}
    if sub_urls:
        private["mihomo-profile.yaml"] = emit_mihomo.build(model, plan, "profile", sub_urls)
        private["mihomo-core.yaml"] = emit_mihomo.build(model, plan, "core", sub_urls)
        private["loon.conf"] = emit_loon.build(model, plan, sub_urls)
        private["quantumultx.conf"] = emit_qx.build(model, plan, sub_urls)

    if a.singbox_nodes or a.singbox_sub_url:
        if a.singbox_nodes:
            with open(a.singbox_nodes, encoding="utf-8") as f:
                text = f.read()
        else:
            text = nodeconv.fetch_subscription(a.singbox_sub_url)
        proxies = nodeconv.load_clash_proxies(text)
        converted, report = nodeconv.convert(proxies)
        private["sing-box-1.14.json"] = emit_singbox.build(model, plan, "1.14", converted)
        private["sing-box-1.12.json"] = emit_singbox.build(model, plan, "1.12", converted)
        empty = [o["tag"] for o in json.loads(private["sing-box-1.14.json"])["outbounds"]
                 if o.get("type") in ("selector", "urltest") and o.get("outbounds") == [emit_singbox.PLACEHOLDER_TAG]]
        lines = [f"共 {len(proxies)} 个节点，转换 {len(converted)} 个，跳过 {len(report)} 个。"] + report
        if empty:
            lines.append("")
            lines.append(f"以下组没有匹配到任何节点，已指向“{emit_singbox.PLACEHOLDER_TAG}”（拒绝连接，不会直连）：")
            lines += [f"  {t}" for t in empty]
        private["sing-box-节点转换报告.txt"] = "\n".join(lines) + "\n"
        print(f"sing-box：转换 {len(converted)}/{len(proxies)} 个节点；{len(empty)} 个组没有节点。详情见 sing-box-节点转换报告.txt")

    if private:
        pdir = os.path.join(a.out, "private")
        write_files(pdir, private)
        with open(os.path.join(pdir, "请勿分享.txt"), "w", encoding="utf-8") as f:
            f.write("本目录包含你的订阅链接或节点凭据，只用于导入自己的设备，不要上传、提交或发给别人。\n")
        print(f"私密产物已写入 {display_path(pdir)}（含订阅 / 节点凭据，请勿分享）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
