"""一次性估算：blackmatrix7 ChinaMax_Domain.list 里有多少条，Quantumult X 严格版接不住。
只读两个清单和已生成的配置，不改任何文件。用法：coverage.py <bm7 清单> <自有清单> <qx 严格版配置>"""
import sys, collections

def read_list(path):
    suf, exact = set(), set()
    for line in open(path, encoding="utf-8"):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        (suf if s.startswith(".") else exact).add(s.lstrip(".").lower())
    return suf, exact

def parents(d):
    parts = d.split(".")
    for i in range(len(parts)):
        yield ".".join(parts[i:])

def covered(d, is_suffix, suf, exact):
    if any(p in suf for p in parents(d)):
        return True
    return (not is_suffix) and d in exact

bm_suf, bm_exact = read_list(sys.argv[1])
own_suf, own_exact = read_list(sys.argv[2])

# QX 严格版 [filter_local] 里按域名判断的规则
loc_suf, loc_exact, loc_kw = set(), set(), []
sec = None
for line in open(sys.argv[3], encoding="utf-8"):
    s = line.strip()
    if s.startswith("["):
        sec = s
        continue
    if sec != "[filter_local]" or not s or s.startswith(("#", ";", "//")):
        continue
    f = [x.strip() for x in s.split(",")]
    t = f[0].lower()
    if t == "host-suffix":
        loc_suf.add(f[1].lower())
    elif t == "host":
        loc_exact.add(f[1].lower())
    elif t == "host-keyword":
        loc_kw.append(f[1].lower())

def local_hit(d, is_suffix):
    if any(p in loc_suf for p in parents(d)):
        return True
    if any(k in d for k in loc_kw):
        return True
    return (not is_suffix) and d in loc_exact

total = len(bm_suf) + len(bm_exact)
by_own = by_local = left = 0
left_tld = collections.Counter()
left_examples = []
for d, is_suffix in [(d, True) for d in sorted(bm_suf)] + [(d, False) for d in sorted(bm_exact)]:
    if covered(d, is_suffix, own_suf, own_exact):
        by_own += 1
    elif local_hit(d, is_suffix):
        by_local += 1
    else:
        left += 1
        left_tld[d.rsplit(".", 1)[-1]] += 1
        left_examples.append(d)

print("bm7 清单条数", total, "（后缀", len(bm_suf), "精确", len(bm_exact), "）")
print("自有清单条数", len(own_suf) + len(own_exact), "（后缀", len(own_suf), "精确", len(own_exact), "）")
print("QX 严格版本地域名规则：后缀", len(loc_suf), "精确", len(loc_exact), "关键词", len(loc_kw))
print("自有清单接得住", by_own, "%.1f%%" % (100 * by_own / total))
print("自有清单接不住、但本地规则先接走", by_local)
print("两边都接不住（Loon 严格版直连、QX 严格版走代理）", left, "%.1f%%" % (100 * left / total))
print("接不住的按结尾分：", left_tld.most_common(12))
known = ["baidu.com", "qq.com", "taobao.com", "tmall.com", "jd.com", "weibo.com", "bilibili.com", "zhihu.com",
         "douyin.com", "163.com", "alipay.com", "meituan.com", "ctrip.com", "xiaohongshu.com", "pinduoduo.com",
         "iqiyi.com", "youku.com", "12306.cn", "icbc.com.cn", "cmbchina.com", "douban.com", "csdn.net",
         "dianping.com", "ele.me", "mi.com", "huawei.com", "sina.com.cn", "sohu.com", "weixin.qq.com", "amap.com"]
print("常见网站自有清单接得住的：", sum(1 for k in known if covered(k, False, own_suf, own_exact) or local_hit(k, False)), "/", len(known),
      "接不住：", [k for k in known if not (covered(k, False, own_suf, own_exact) or local_hit(k, False))])
import random
random.seed(20261006)
print("接不住的随机 30 条：", random.sample(left_examples, 30))
