"""第二个原型（proto2）：只把十份简易版加进 tests/helpers.py 的客户端登记，并把“简易版严格版”的期望键映射到同一个 App 的严格版，
别的测试一行不改——看哪些现有测试因为“默认是完整版的组结构”而失败，顺便量测试多跑了多久。只改 scratch 里的副本。
用法：python3 -B patch_tests_proto2.py <proto2 目录>
"""
import os
import sys

P = sys.argv[1]


def sub(rel, old, new):
    path = os.path.join(P, rel)
    with open(path, encoding="utf-8") as f:
        s = f.read()
    assert s.count(old) == 1, (rel, old[:60])
    with open(path, "w", encoding="utf-8") as f:
        f.write(s.replace(old, new))


sub("tests/helpers.py", '''    "stash-strict": "stash/stash-strict.yaml",
}''', '''    "stash-strict": "stash/stash-strict.yaml",
    # 简易版（原型）
    "mihomo-simple-profile": "mihomo/mihomo-simple-profile.yaml",
    "mihomo-simple-core": "mihomo/mihomo-simple-core.yaml",
    "singbox-simple-1.14": "sing-box/sing-box-simple-1.14.json",
    "singbox-simple-1.12": "sing-box/sing-box-simple-1.12.json",
    "loon-simple": "loon/loon-simple.conf",
    "quantumultx-simple": "quantumultx/quantumultx-simple.conf",
    "loon-simple-strict": "loon/loon-simple-strict.conf",
    "quantumultx-simple-strict": "quantumultx/quantumultx-simple-strict.conf",
    "stash-simple": "stash/stash-simple.yaml",
    "stash-simple-strict": "stash/stash-simple-strict.yaml",
}''')
sub("tests/helpers.py", '''STRICT_CLIENTS = ("loon-strict", "quantumultx-strict", "stash-strict")''',
    '''STRICT_CLIENTS = ("loon-strict", "quantumultx-strict", "stash-strict", "loon-simple-strict", "quantumultx-simple-strict",
                  "stash-simple-strict")''')
sub("tests/helpers.py", '''STRICT_OF = {"loon": "loon-strict", "quantumultx": "quantumultx-strict", "stash": "stash-strict"}''',
    '''STRICT_OF = {"loon": "loon-strict", "quantumultx": "quantumultx-strict", "stash": "stash-strict",
             "loon-simple": "loon-simple-strict", "quantumultx-simple": "quantumultx-simple-strict", "stash-simple": "stash-simple-strict"}''')
sub("tests/helpers.py", '''LOON_CLIENTS = ("loon", "loon-strict")
QX_CLIENTS = ("quantumultx", "quantumultx-strict")
STASH_CLIENTS = ("stash", "stash-strict")''', '''LOON_CLIENTS = ("loon", "loon-strict", "loon-simple", "loon-simple-strict")
QX_CLIENTS = ("quantumultx", "quantumultx-strict", "quantumultx-simple", "quantumultx-simple-strict")
STASH_CLIENTS = ("stash", "stash-strict", "stash-simple", "stash-simple-strict")''')
sub("tests/helpers.py", '''LQ_STRICT_OF = {"loon": "loon-strict", "quantumultx": "quantumultx-strict"}''',
    '''LQ_STRICT_OF = {"loon": "loon-strict", "quantumultx": "quantumultx-strict",
                "loon-simple": "loon-simple-strict", "quantumultx-simple": "quantumultx-simple-strict"}


def base_of(client: str) -> str:
    """简易版 → 规则相同的完整版那一份（期望、官方内核记录都按它查）。"""
    return client.replace("-simple", "")''')
sub("tests/helpers.py", '''    pc = case.get("per_client") or {}
    if client in pc:
        return pc[client]''', '''    pc = case.get("per_client") or {}
    client = base_of(client)
    if client in pc:
        return pc[client]''')
sub("tests/test_real_data.py", '''    exp = probe["expect"][client if is_strict(client) else family(client)]''',
    '''    exp = probe["expect"][client.replace("-simple", "") if is_strict(client) else family(client)]''')
print("ok")
