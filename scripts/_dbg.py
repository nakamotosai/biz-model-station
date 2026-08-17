import sys, re, copy, collect
FILL = "把日常重复性事务标准化成固定步骤，安排专人按清单执行，每周核对一次进度，把扩展方向记录到共享表格里，等效果稳定后再考虑是否增加投入。"
def mk_scam(name, hi=None, rf=None):
    return {"id": re.sub(r"[^a-z0-9-]","",name.lower()) or "x", "name": name, "industry": "其他",
      "region":"中","scale":"中型","channel":"web",
      "victims":(FILL + "受害者容易在诱导下放松警惕服从安排，事后才发觉上当")*3,
      "how_it_works": hi or ["先用话术接近","再提出收费项","不断追加名目","质疑就回避"],
      "red_flags": (rf or ["不签任何协议","只能私下转账","态度反复催促"]),
      "real_cases":["案例一","案例二"],"official_alerts":["已提醒"],"protection":["核实","不预付"],
      "sources":["http://a.com","http://b.com"]}
for n,m in [("vb", mk_scam("虚拟币挖矿资金盘骗局", hi=["诱导购买挖矿机","宣称币价翻倍"], rf=["高收益保本","夸大回报","催促打款"])),
            ("old", mk_scam("老照片修复剪辑收费骗局", hi=["承诺修复老照片","用剪辑软件制作视频","随后不断加价"]))]:
    r = collect.normalize(copy.deepcopy(m),"scam")
    print(n, "->", r is not None and r.get("industry"))
    if r is None:
        for f in ("how_it_works","red_flags","real_cases","official_alerts","protection"):
            print("   ",f,len(m[f]))
        print("   victims len", len(str(m["victims"])))
