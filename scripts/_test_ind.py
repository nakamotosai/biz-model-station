import sys
sys.path.insert(0, "/home/ubuntu/biz-research/scripts")
sys.path.insert(0, "/home/ubuntu/.hermes/local/intel_hub")
import collect
import re
FILL = "把日常重复性事务标准化成固定步骤，安排专人按清单执行，每周核对一次进度，把扩展方向记录到共享表格里，等效果稳定后再考虑是否增加投入。"
def pad(s,n=3): return s + (FILL*n)
DEF_RF = ["不签任何协议","只能私下转账","态度反复催促"]
def mk_agent(name, industry="其他", wf="", rv="按单收费，按月结算"):
    core = (wf or FILL*3)
    return {"id": re.sub(r"[^a-z0-9-]","",name.lower()) or "x", "name": name, "industry": industry,
      "region":"中","scale":"中型","channel":"web","workflow":pad(core)[:500],
      "setup":FILL*3, "revenue":pad(rv)[:250],
      "cost":"租金人力等固定开销，按预算控制", "time":"每天固定两小时维护", "entry":"需要一定经验",
      "tools":["工具甲","工具乙","工具丙","工具丁"],"keys":["要点1","要点2","要点3","要点4"],
      "risks":["竞争加剧","政策变化","现金流不稳"],"example":["某案例甲","某案例乙","某案例丙"],
      "sources":["http://a.com","http://b.com"]}
def mk_scam(name, industry="其他", hi=None, rf=None):
    return {"id": re.sub(r"[^a-z0-9-]","",name.lower()) or "x", "name": name, "industry": industry,
      "region":"中","scale":"中型","channel":"web",
      "victims":(FILL + "受害者容易在诱导下放松警惕服从安排，事后才发觉上当")*3,
      "how_it_works": hi or ["先用话术接近","再提出收费项","不断追加名目","质疑就回避"],
      "red_flags": (rf or DEF_RF),
      "real_cases":["案例一：多位受害者报案","案例二：涉案金额累计较大"],
      "official_alerts":["相关部门已发布提醒"],"protection":["核实资质","不提前付款"],
      "sources":["http://a.com","http://b.com"]}
def mk_model(name):
    return {"id":"mm"+re.sub(r"[^a-z0-9-]","",name), "name":name, "industry":"其他",
      "background":FILL*3,"target":FILL*2,"revenue":FILL*2,"cost":FILL*2,"moat":FILL*2,
      "region":"中","scale":"中型","channel":"web","type":"model",
      "swot":{"s":[FILL,"强项"],"w":[FILL,"弱点"],"o":[FILL,"机会"],"t":[FILL,"威胁"]},
      "keys":[FILL,"关键"],"risks":[FILL,"风险"],"example":[FILL,"示例"],
      "sources":["http://a.com","http://b.com"]}
cases = [
  ("agent 简历求职", mk_agent("简历优化代写求职外包", wf="帮写简历指导求职面试包装经历"), "agent", "教育/知识付费"),
  ("agent 房产中介", mk_agent("房源平台", wf="帮房产中介找房源撮合客户"), "agent", "本地生活"),
  ("agent 跨境电商", mk_agent("电商选品独立站", wf="把商品上架亚马逊独立站销售"), "agent", "电商/零售"),
  ("scam 老照片剪辑", mk_scam("老照片修复剪辑收费骗局", hi=["承诺修复老照片","用剪辑软件制作视频","随后不断加价"]), "scam", "内容/创作者经济"),
  ("scam 虚拟币挖矿", mk_scam("虚拟币挖矿资金盘骗局", hi=["诱导购买挖矿机","宣称币价翻倍","让你拉人头推广"], rf=["高收益保本","夸大回报","催促打款"]), "scam", "金融科技"),
  ("agent 无关键词回落", mk_agent("某某小店", wf=FILL*2), "agent", "其他"),
  ("model 名称含金融不被污染", mk_model("AI金融风控平台"), "model", "其他(保持)"),
  ("agent 已命中目录直接用", mk_agent("普通店","本地生活"), "agent", "本地生活(直接用)"),
  ("agent email营销不误判AI", mk_agent("email邮件营销自动化", wf="帮客户批量发email营销推广"), "agent", "营销/广告"),
]
for label, m, kind, expect in cases:
    r = collect.normalize(m, kind)
    got = (r or {}).get("industry","<None>")
    exp = expect.split("(")[0].strip()
    ok = "OK " if exp==got else "!! "
    print(ok + label + " ["+kind+"]: got=《" + str(got) + "》 expect=" + expect)
