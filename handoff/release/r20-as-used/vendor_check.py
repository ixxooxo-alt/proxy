"""运行环境核对（r18 起用的，r19、r20 照用）：按 ~/proxy-vendor/SOURCES.txt 重新算每个文件的 SHA-256、看每个源码目录的提交号
和有没有改动；Stash 文档包按它自带的 MANIFEST.txt（制表符分隔：原网址、文件名、下载时间、大小、SHA-256、完整性）核对。
只读，不运行那些目录里的任何东西。用法：python3 handoff/release/r20-as-used/vendor_check.py > ~/proxy-work/vendor20-check.txt"""
import datetime, hashlib, os, subprocess, sys

V = os.path.expanduser(os.environ.get("PROXY_VENDOR", "~/proxy-vendor"))
DOCS = os.path.join(V, "src", "stash-docs-2026-10-13")


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


print("时间 " + datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S") + "（UTC）")
bad, files, dirs = [], 0, 0
with open(os.path.join(V, "SOURCES.txt"), encoding="utf-8") as f:
    lines = [ln.rstrip("\n") for ln in f if ln.strip() and not ln.startswith("#")]
for ln in lines:
    want, rel = ln.split("  ", 1)
    p = os.path.join(V, rel)
    if rel.startswith("src/"):
        dirs += 1
        head = subprocess.run(["git", "-C", p, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "-C", p, "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
        ok = head == want and not dirty
        print(f"{'对' if ok else '不对'}  {rel}：提交 {head[:12]}（登记的 {want[:12]}）{'' if not dirty else '；有改动'}")
    else:
        files += 1
        got = sha(p) if os.path.exists(p) else "（没有这个文件）"
        ok = got == want
        print(f"{'对' if ok else '不对'}  {rel}：{got[:16]}…（登记的 {want[:16]}…）")
    if not ok:
        bad.append(rel)
n_docs = 0
with open(os.path.join(DOCS, "MANIFEST.txt"), encoding="utf-8") as f:
    rows = [ln.rstrip("\n").split("\t") for ln in f][1:]
for url, name, _when, size, want, _state in (r for r in rows if len(r) == 6):      # 最后一行是一句注，不是文件
    p = os.path.join(DOCS, name)
    ok = os.path.exists(p) and os.path.getsize(p) == int(size) and sha(p) == want
    n_docs += 1
    if not ok:
        bad.append("stash-docs/" + name)
        print(f"不对  stash-docs/{name}")
if bad:
    print("不对的：" + "、".join(bad))
    sys.exit(1)
print(f"文件 {files} 个都对；源码目录 {dirs} 个，提交号都对、没有改动；Stash 文档包 {n_docs} 个文件都对")
