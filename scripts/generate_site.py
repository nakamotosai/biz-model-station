#!/usr/bin/env python3
"""generate_site.py — 商业模式情报站站点生成器（v2：workflow 流程图）

输入：data/*.json（每条一个商业模式，schema 见 data/SCHEMA.md）
流程：
  1. 读取全部条目，校验必填字段
  2. 每条生成 archify workflow 流程图（泳道：背景/客户/盈利/护城河/风险）
  3. 生成 site/<id>.html（图 iframe + 完整文字解说：背景/目标客户/盈利点/成本/护城河/SWOT）
  4. 生成 site/index.html（gruvbox 卡片索引，可按地区/行业/规模/渠道过滤）
  5. 生成 site/data.json（机器可读清单）

用法：
  python3 generate_site.py                 # 全量重建
  python3 generate_site.py --only <id>     # 只重建某条
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from anubis.verifier import run_verifier, Verdict

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SITE = ROOT / "site"
MODELS_OUT = SITE / "models"
ARCHIFY = None
for cand in [ROOT / "archify" / "bin" / "archify.mjs",
             Path(r"C:\Users\sai\.pi\agent\skills\archify\bin\archify.mjs")]:
    if cand.exists():
        ARCHIFY = cand
        break
if ARCHIFY is None:
    raise SystemExit("archify.mjs 未找到，设置 ARCHIFY 路径")

SKIP = {"SCHEMA.json", "index.json", "topics.json", "SCHEMA.md"}
# 三类条目各必填字段（按 type 分派；缺 type 视为 model 向后兼容现有 187 条）
REQUIRED_BY_TYPE = {
    "model": ["id", "name", "industry", "region", "scale", "channel", "background",
              "target", "revenue", "cost", "moat", "swot", "keys", "risks", "sources"],
    "journey": ["id", "name", "company", "founders", "industry", "region", "scale",
                "channel", "origin", "milestones", "turning_points", "failures",
                "keys", "lessons", "metrics", "sources"],
    "scam": ["id", "name", "industry", "region", "scale", "channel", "victims",
             "how_it_works", "red_flags", "real_cases", "official_alerts",
             "protection", "sources"],
}
REQUIRED = REQUIRED_BY_TYPE["model"]  # 向后兼容引用
DIMENSIONS = {"region": "地区", "scale": "规模", "channel": "渠道", "industry": "行业"}

# gruvbox dark 调色板
C_BG = "#282828"; C_BG0 = "#1d2021"; C_FG = "#ebdbb2"; C_DIM = "#a89984"
C_ACCENT = "#fabd2f"; C_GREEN = "#b8bb26"; C_AQUA = "#8ec07c"
C_RED = "#fb4934"; C_PURPLE = "#d3869b"; C_BLUE = "#83a598"
# 字体调参（font-panel 调定 2026-08-04）
# 正文：weight 300 / line-height 2.0 / 灰度 50%（var(--fg)×50%+var(--bg)）；标题：weight 500（字号保持现状）
FONT_STYLE = """body,article,li,p,.card-how,.explain p,.explain li,.swot li,.src li,.chip,.count
  { font-weight:300 !important; line-height:2.0 !important;
    color:color-mix(in srgb,var(--fg) 50%,var(--bg)) !important; }
.explain strong,.swot h3 { color:var(--fg) !important; }
h1,h2,h3,.card-head h3 { font-weight:500 !important; }"""
# 字段归一化（采集器/旧数据存在简写与全称并存，runbook 规范以简写为准）
NORM = {
    "region": {"中国": "中", "美国": "美", "日本": "日"},
    "scale": {"中企": "中型", "中小企": "中型", "混合": "中型", "中小创作者·平台生态": "小企"},
    "channel": {}, "industry": {},
}
# industry 固定目录（SSOT · 采集器/生成器都只能用这里的值；新增行业先加这里再用）
# "其他" 兜底：任何未命中目录的值归"其他"并告警，便于复查是否该扩目录
IND_CATALOG = [
    "AI/大模型", "SaaS/企业软件", "云计算", "金融科技", "内容/创作者经济",
    "电商/零售", "本地生活", "餐饮/茶饮", "教育/知识付费", "医疗/养老",
    "营销/广告", "旅游", "宠物", "其他",
]
# 旧数据子串归一（仅用于一次性收敛历史碎值；新数据必须直接写目录规范值）
IND_KEYS = [
    ("AI/大模型", ["ai", "大模型", "agent", "生成式", "人工智能", "aigc", "半导体", "开源软件"]),
    ("SaaS/企业软件", ["saas", "企业软件", "软件订阅", "软件投资", "定价与变现", "独立saas", "独立开发", "工具软件", "效率工具", "虚拟产品"]),
    ("云计算", ["云计算", "云服务", "基础设施"]),
    ("金融科技", ["金融科技", "支付", "碳交易"]),
    ("内容/创作者经济", ["内容", "创作者", "短剧", "漫画", "影视", "流媒体", "自媒体", "会员媒体", "法人媒体", "会员经济/媒体"]),
    ("电商/零售", ["电商", "零售", "即时零售", "跨境电商", "社交电商", "数字商品", "数字服务", "消费电子"]),
    ("本地生活", ["本地生活", "本地服务", "o2o", "到店"]),
    ("餐饮/茶饮", ["餐饮", "茶饮", "咖啡", "食品加工", "餐饮供应链"]),
    ("教育/知识付费", ["教育", "知识付费", "知识变现", "母婴"]),
    ("营销/广告", ["营销", "广告", "it服务", "it咨询", "dx咨询", "系统集成", "代运营", "it・", "自动化/流程", "企业服务咨询"]),
    ("医疗/养老", ["医疗", "数字医疗", "养老", "慢病"]),
    ("旅游", ["旅游", "体验经济"]),
    ("宠物", ["宠物"]),
]
_IND_UNKNOWN = set()

def norm_industry(val: str) -> str:
    v = val.strip()
    if v in IND_CATALOG:
        return v
    low = v.lower()
    for canon, keys in IND_KEYS:
        for k in keys:
            if k.lower() in low:
                return canon
    _IND_UNKNOWN.add(val)
    return "其他"



def slug_ok(s: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*", s))


def load_models() -> list[dict]:
    models = []
    for f in sorted(DATA.glob("*.json")):
        if f.name.startswith("."):
            continue  # 隐藏状态文件（.collect_state.json / .collect.lock）
        if f.name in SKIP:
            continue
        m = json.loads(f.read_text(encoding="utf-8"))
        for dim in NORM:
            if m.get(dim, "") in NORM[dim]:
                m[dim] = NORM[dim][m[dim]]
        m["industry"] = norm_industry(m.get("industry", ""))
        req = REQUIRED_BY_TYPE.get(m.get("type", "model"), REQUIRED)
        for k in req:
            if k not in m or m[k] in (None, "", [], {}):
                raise SystemExit(f"[{f.name}] 缺必填字段(type={m.get('type','model')}): {k}")
        if not slug_ok(m["id"]):
            raise SystemExit(f"[{f.name}] id 非法: {m['id']}")
        models.append(m)
    if _IND_UNKNOWN:
        print(f"⚠️ industry 未命中目录（已归\"其他\"，考虑扩 IND_CATALOG/IND_KEYS）：{_IND_UNKNOWN}", file=__import__('sys').stderr)
    return models


def s(swot: dict, key: str) -> list[str]:
    v = swot.get(key) or []
    if isinstance(v, str):
        return [v]
    return [str(x) for x in v if str(x).strip()][:3]


def sub(s, n: int = 6) -> str:
    """sublabel 短摘要：优先提取语义关键片段（百分比/计费词/模式词），
    避免硬截 6 字产生「品牌方主要收…」类无语义标签。支持 str/list。"""
    if isinstance(s, list):
        s = " ".join(str(x) for x in s)
    s = (s or "").replace("\n", " ").strip()
    if len(s) <= n:
        return s
    # 1) 关键片段：完整百分比范围 / 4-6 字机制短语
    m = re.search(r"[\d.]+%[\s\-~至到]*[\d.]*%?|按[\u4e00-\u9fa5]{1,3}(抽|分|计|结)[\u4e00-\u9fa5]{0,2}|"
                  r"平台抽成|抽佣分账|按月订阅|按年订阅|会员订阅|批发差价|差价毛利|"
                  r"服务费|加盟费|代理费|手续费|按结果|按用量|按席位|按单|按笔", s)
    if m:
        frag = m.group(0).strip()
        return frag if len(frag) <= n else frag[:n] + "…"
    # 2) 标点切首段（语义完整）
    for sep in "；;，,。.!！？?：:":
        head = s.split(sep)[0].strip()
        if 0 < len(head) <= n:
            return head
    # 3) 兜底截断
    return s[:n] + "…"


# ---------------------------------------------------------------------------
# 差异化流程图：按商业模式族分类，每族一种独立泳道/节点/连线骨架
# 之前全站套用同一「背景→客户→盈利→护城河→风险」五格模板，图全雷同。
# 现按 revenue 文本关键词路由到 7 个结构族，骨架各不相同（泳道数/列位/节点类型/连线语义）。
# ---------------------------------------------------------------------------
FAMILY_LABEL = {
    "commission":   "双边撮合抽佣",
    "subscription": "订阅会员制",
    "supply_chain": "供应链加盟",
    "creator":      "创作者分成",
    "agency":       "服务代理/项目制",
    "asset":        "硬件资产+服务",
    "generic":      "通用变现链",
}


_FAM_OVERRIDE = {
    "local-life-platform-commission": "commission",
    "carbon-asset-ccer-dev-agency": "agency",
    "zero-commission-ordering-saas-2026": "subscription",
    "smb-dx-ai-subsidy-adoption": "agency",
    "open-source-commercialization": "asset",
    "cross-border-overseas-warehouse-0commission": "agency",
    "star-ip-merch-crowdfunding-platform": "commission",
    "micro-saas-indie-ai-agents": "subscription",
    "micro-saas-solo-tools": "subscription",
    "instant-retail-ai-fulfillment-saas": "subscription",
    "digital-human-livestream": "agency",
    "aggregated-payment-merchant-saas": "commission",
    "brand-self-broadcast-matrix-plus-ai-agent": "subscription",
    "dtc-brand-overseas-social-commerce-full-link-agency": "agency",
    "chronic-disease-management-ai-closed-loop": "agency",
    "agentic-outsourcing-pay-by-results": "agency",
    "interest-e-commerce": "commission",
    "ai-vtuber-agency-end-to-end": "agency",
    "instant-retail-margin-optimization": "generic",
    "carbon-accounting-esg-saas": "subscription",
    "usage-outcome-based-saas-pricing": "agency",
    "managed-ai-agent-bpo-service": "agency",
    "nvidia-data-center-ai-infra": "asset",
    "netflix-ads-membership": "subscription",
    "zero-app-private-domain-group-buying": "supply_chain",
    "google-cloud-ai-backlog": "asset",
    "solar-rooftop-bipv-asset-service": "asset",
    "beauty-pie-membership-club": "subscription",
    "supply-chain-ai-credit-platform": "commission",
    "wechat-private-domain": "generic",
    "cross-border-short-drama-localization-platform": "agency",
    "vertical-ai-agent": "agency",
    "note-pro-b2b-ownmedia": "subscription",
    "anime-ip-cross-media-operations": "generic",
    "microsoft-azure-cloud-ai": "asset",
    "paid-newsletter-platform-economy": "subscription",
    "creator-economy-ai-stack": "subscription",
    "knowledge-paid-0commission-scrm": "subscription",
    "waste-to-energy-digital-operator": "agency",
    "creator-ai-knowledge-membership": "subscription",
    "smart-fitness-studio": "subscription",
    "digital-human-livestream-provider": "subscription",
    "restaurant-saas-pos": "subscription",
    "social-behavior-credit-scoring-for-sme": "agency",
    "skeb-commission-commission": "commission",
    "brand-original-podcast-agency": "agency",
    "llm-fine-tuning-entreprise-service": "agency",
    "pet-care-wash-retail-saas": "subscription",
    "token-factory-commercial-operation": "asset",
    "legal-ai-agent-saas": "agency",
    "ai-content-factory-outsourcing": "agency",
    "ai-idol-voice-data-ads-agency": "agency",
    "agricultural-b2b-processing-matchmaking": "commission",
    "ai-receptionist-agency": "subscription",
    "creator-economy-ai-efficiency-tools": "subscription",
}


def classify_family(m: dict) -> str:
    """先查人工校准覆盖表（族校准 2026-08-04，55 条），再走关键词规则。"""
    rid = m.get("id", "")
    if rid in _FAM_OVERRIDE:
        return _FAM_OVERRIDE[rid]
    rev = (m.get("revenue", "") or "")
    name = (m.get("name", "") or "").lower()
    ind = (m.get("industry", "") or "").lower()
    blob = f"{rev} {name} {ind}"
    if re.search(r"加盟|供货|供应链|进销|批发|出货|食材|包材|中央厨房|"
                 r"进货|供应链服务|供应.*总部|向加盟|供应链.*利润|供货价", rev):
        return "supply_chain"
    if re.search(r"创作者|粉丝|打赏|付费阅读|付费文章|稿费|内容付费|剧本|剧集|"
                 r"记者|会员媒体", blob):
        return "creator"
    if re.search(r"佣金|抽佣|撮合|成交额抽|交易抽佣|每笔.*抽|按成交|交易手续费|分润|"
                 r"平台.*抽成|商家.*佣金|成交.*比例", rev):
        return "commission"
    if re.search(r"项目费|按项目|导入顾问费|顾问费|一次性搭|按单|项目制|外包|"
                 r"代购|代理购物|买手|按效果.*费|按结果", blob):
        return "agency"
    if re.search(r"硬件卖|GPU.*销售|卖硬件|基因组|设备.*使用量|算力.*批发|"
                 r"燃烧优化|运维服务费|光伏.*服务|数据集.*出售|卖.*算力|运维费", rev):
        return "asset"
    if re.search(r"订阅|会员|月费|年费|会费|席位|按月|按年|经常性收入|ARR|"
                 r"季卡|年卡|月卡|按席位", rev):
        return "subscription"
    return "generic"


def _money(rev: str) -> str:
    """提取盈利机制短摘要：优先 % / 抽佣 / 计费关键词，否则取首句前 12 字。"""
    m = re.search(r"\d+[%‰]|按成交.*抽|按流水.*抽|每笔.*抽|抽佣|计费|订阅费|会员费", rev)
    if m:
        return m.group(0)[:6]
    return sub(rev.split("；")[0].split("\n")[0], 6)


def _bn(rid: str, lane: str, col: int, ntype: str, label: str, sublabel: str = "") -> dict:
    """构造一个节点。sublabel 统一用 sub() 截 12 字。"""
    n: dict = {"id": f"{rid}-{lane}-{col}", "lane": lane, "col": col, "type": ntype, "label": label}
    if sublabel:
        n["sublabel"] = sub(sublabel)
    return n


def _edge(rid: str, eid: str, frm: str, to: str, **kw) -> dict:
    e = {"id": f"{rid}-{eid}", "from": frm, "to": to}
    e.update(kw)
    return e


def _fam_commission(m: dict, rid: str) -> tuple:
    lanes = [{"id": "supply", "label": "供给侧"},
             {"id": "plat", "label": "平台撮合"},
             {"id": "demand", "label": "需求侧"}]
    ind = m["industry"][:6]
    sup = _bn(rid, "supply", 0, "external", "供应商", f"{ind}供给方")
    onboard = _bn(rid, "plat", 0, "frontend", "入驻上架", "商家准入")
    match = _bn(rid, "plat", 2, "messagebus", "智能匹配", m.get("keys", ["匹配机制"])[0])
    deal = _bn(rid, "plat", 3, "database", "下单成交", "撮合成交")
    buyer = _bn(rid, "demand", 0, "external", "需求方", m["target"])
    take = _bn(rid, "plat", 5, "cloud", "抽佣分账", _money(m["revenue"]))
    nodes = [sup, onboard, match, deal, buyer, take]
    edges = [
        _edge(rid, "e1", sup["id"], onboard["id"], variant="default", route="drop",
              fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e2", onboard["id"], match["id"], variant="default",
              label="聚合供给", fromSide="right", toSide="left", labelSegment=1),
        _edge(rid, "e3", buyer["id"], match["id"], variant="emphasis", label="发起需求",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e4", match["id"], deal["id"], variant="emphasis"),
        _edge(rid, "e5", deal["id"], take["id"], variant="emphasis", label="按成交抽佣",
              fromSide="right", toSide="left", labelSegment=1),
    ]
    phases = [{"id": "agg", "label": "聚合", "fromCol": 0, "toCol": 1},
              {"id": "match", "label": "匹配", "fromCol": 2, "toCol": 2, "variant": "emphasis"},
              {"id": "deal", "label": "成交", "fromCol": 3, "toCol": 3},
              {"id": "take", "label": "变现", "fromCol": 5, "toCol": 5}]
    return lanes, nodes, edges, phases, [sup["id"], onboard["id"], match["id"], deal["id"], take["id"]]


def _fam_subscription(m: dict, rid: str) -> tuple:
    lanes = [{"id": "prod", "label": "产品价值"},
             {"id": "pay", "label": "会员付费"},
             {"id": "keep", "label": "续费留存"}]
    free = _bn(rid, "prod", 0, "frontend", "免费/试用", "获客漏斗")
    tier = _bn(rid, "prod", 2, "messagebus", "分层权益", m.get("keys", ["分级权益"])[0])
    pay = _bn(rid, "pay", 2, "database", "订阅付费", _money(m["revenue"]))
    renew = _bn(rid, "keep", 3, "cloud", "续费复购", m["moat"])
    arpu = _bn(rid, "keep", 5, "external", "ARPU增值", m["revenue"].split("；")[0])
    nodes = [free, tier, pay, renew, arpu]
    edges = [
        _edge(rid, "e1", free["id"], tier["id"], variant="default", label="引导转化"),
        _edge(rid, "e2", tier["id"], pay["id"], variant="emphasis", label="按月/年订阅",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e3", pay["id"], renew["id"], variant="default", label="续费提醒"),
        _edge(rid, "e4", renew["id"], arpu["id"], variant="default", label="交叉销售"),
    ]
    phases = [{"id": "acq", "label": "获客", "fromCol": 0, "toCol": 1},
              {"id": "paid", "label": "付费", "fromCol": 2, "toCol": 2, "variant": "emphasis"},
              {"id": "renew", "label": "续费", "fromCol": 3, "toCol": 5}]
    return lanes, nodes, edges, phases, [free["id"], tier["id"], pay["id"], renew["id"], arpu["id"]]


def _fam_supply_chain(m: dict, rid: str) -> tuple:
    lanes = [{"id": "hq", "label": "品牌总部"},
             {"id": "sup", "label": "供应链"},
             {"id": "store", "label": "门店终端"}]
    hq = _bn(rid, "hq", 0, "backend", "品牌总部", "统一品牌")
    goods = _bn(rid, "sup", 2, "database", "食材/包材供货", m["revenue"].split("；")[0])
    wholesale = _bn(rid, "sup", 3, "messagebus", "加价批发", _money(m["revenue"]))
    st = _bn(rid, "store", 3, "frontend", "加盟门店", m["target"])
    sell = _bn(rid, "store", 5, "external", "终端销售", "差价毛利")
    nodes = [hq, goods, wholesale, st, sell]
    edges = [
        _edge(rid, "e1", hq["id"], goods["id"], variant="default", label="集中采购",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e2", goods["id"], wholesale["id"], variant="emphasis"),
        _edge(rid, "e3", wholesale["id"], st["id"], variant="default", label="配送到店",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e4", st["id"], sell["id"], variant="emphasis", label="门店售卖"),
    ]
    phases = [{"id": "make", "label": "生产", "fromCol": 0, "toCol": 1},
              {"id": "ship", "label": "铺货", "fromCol": 2, "toCol": 3, "variant": "emphasis"},
              {"id": "sell", "label": "销售", "fromCol": 4, "toCol": 4}]
    return lanes, nodes, edges, phases, [hq["id"], goods["id"], wholesale["id"], st["id"], sell["id"]]


def _fam_creator(m: dict, rid: str) -> tuple:
    lanes = [{"id": "cr", "label": "创作者"},
             {"id": "plat", "label": "分发平台"},
             {"id": "fan", "label": "粉丝付费"}]
    make = _bn(rid, "cr", 0, "frontend", "内容创作", "独家内容")
    upload = _bn(rid, "plat", 1, "messagebus", "上传分发", "平台流量")
    fan = _bn(rid, "fan", 2, "external", "粉丝读者", m["target"])
    pay = _bn(rid, "fan", 3, "database", "付费/打赏", _money(m["revenue"]))
    split = _bn(rid, "plat", 5, "cloud", "平台抽成", "按笔分账")
    nodes = [make, upload, fan, pay, split]
    edges = [
        _edge(rid, "e1", make["id"], upload["id"], variant="default", label="发布作品",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e2", upload["id"], fan["id"], variant="default", label="触达粉丝",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e3", fan["id"], pay["id"], variant="emphasis"),
        _edge(rid, "e4", pay["id"], split["id"], variant="emphasis", label="平台分账"),
    ]
    phases = [{"id": "make", "label": "创作", "fromCol": 0, "toCol": 1},
              {"id": "dist", "label": "分发", "fromCol": 2, "toCol": 3, "variant": "emphasis"},
              {"id": "cash", "label": "变现", "fromCol": 4, "toCol": 5}]
    return lanes, nodes, edges, phases, [make["id"], upload["id"], fan["id"], pay["id"], split["id"]]


def _fam_agency(m: dict, rid: str) -> tuple:
    lanes = [{"id": "cli", "label": "客户需求"},
             {"id": "do", "label": "交付执行"},
             {"id": "bill", "label": "收费结算"},
             {"id": "risk", "label": "风险", "variant": "exception"}]
    lead = _bn(rid, "cli", 0, "external", "客户委托", m["target"])
    scope = _bn(rid, "do", 1, "frontend", "需求拆解", "方案设计")
    do = _bn(rid, "do", 3, "messagebus", "执行交付", m.get("keys", ["交付"])[0])
    verify = _bn(rid, "do", 5, "security", "结果验收", "按结果计费")
    bill = _bn(rid, "bill", 5, "database", "项目/效果费", _money(m["revenue"]))
    risk = _bn(rid, "risk", 5, "security", "主要风险", m.get("risks", ["风险"])[0])
    nodes = [lead, scope, do, verify, bill, risk]
    edges = [
        _edge(rid, "e1", lead["id"], scope["id"], variant="default", label="接单",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e2", scope["id"], do["id"], variant="emphasis", label="执行"),
        _edge(rid, "e3", do["id"], verify["id"], variant="default", label="验收"),
        _edge(rid, "e4", verify["id"], bill["id"], variant="emphasis", label="按效果结算",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e5", bill["id"], risk["id"], variant="security", label="要防什么",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
    ]
    phases = [{"id": "lead", "label": "接单", "fromCol": 0, "toCol": 1},
              {"id": "exec", "label": "交付", "fromCol": 3, "toCol": 4, "variant": "emphasis"},
              {"id": "pay", "label": "结算", "fromCol": 5, "toCol": 5}]
    return lanes, nodes, edges, phases, [lead["id"], scope["id"], do["id"], verify["id"], bill["id"]]


def _fam_asset(m: dict, rid: str) -> tuple:
    lanes = [{"id": "hw", "label": "硬件资产"},
             {"id": "ops", "label": "部署运维"},
             {"id": "rev", "label": "持续收入"},
             {"id": "risk", "label": "风险", "variant": "exception"}]
    hw = _bn(rid, "hw", 0, "external", "硬件/设备", "重资产")
    install = _bn(rid, "ops", 1, "frontend", "部署安装", "交钥匙")
    ops = _bn(rid, "ops", 3, "messagebus", "持续运维", m.get("keys", ["运维"])[0])
    meter = _bn(rid, "rev", 4, "database", "按用量计费", _money(m["revenue"]))
    svc = _bn(rid, "rev", 5, "cloud", "服务/订阅", m["revenue"].split("；")[0])
    risk = _bn(rid, "risk", 5, "security", "主要风险", m.get("risks", ["风险"])[0])
    nodes = [hw, install, ops, meter, svc, risk]
    edges = [
        _edge(rid, "e1", hw["id"], install["id"], variant="emphasis", label="售出",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e2", install["id"], ops["id"], variant="default", label="上线"),
        _edge(rid, "e3", ops["id"], meter["id"], variant="default", label="计量",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e4", meter["id"], svc["id"], variant="default"),
        _edge(rid, "e5", svc["id"], risk["id"], variant="security", label="要防什么",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
    ]
    phases = [{"id": "ship", "label": "交付", "fromCol": 0, "toCol": 1, "variant": "emphasis"},
              {"id": "run", "label": "运行", "fromCol": 2, "toCol": 3},
              {"id": "cash", "label": "变现", "fromCol": 4, "toCol": 5}]
    return lanes, nodes, edges, phases, [hw["id"], install["id"], ops["id"], meter["id"], svc["id"]]


def _fam_generic(m: dict, rid: str) -> tuple:
    lanes = [{"id": "mkt", "label": "市场"},
             {"id": "prod", "label": "产品"},
             {"id": "rev", "label": "收入"},
             {"id": "risk", "label": "风险", "variant": "exception"}]
    mkt = _bn(rid, "mkt", 0, "external", "市场需求", m["target"])
    prod = _bn(rid, "prod", 2, "messagebus", "产品交付", m.get("keys", ["交付"])[0])
    rev = _bn(rid, "rev", 4, "database", "收费变现", _money(m["revenue"]))
    risk = _bn(rid, "risk", 5, "security", "主要风险", m.get("risks", ["风险"])[0])
    nodes = [mkt, prod, rev, risk]
    edges = [
        _edge(rid, "e1", mkt["id"], prod["id"], variant="default", label="切入需求",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e2", prod["id"], rev["id"], variant="emphasis", label="变现",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
        _edge(rid, "e3", rev["id"], risk["id"], variant="security", label="防范",
              route="drop", fromSide="bottom", toSide="top", labelSegment=1),
    ]
    phases = [{"id": "mkt", "label": "市场", "fromCol": 0, "toCol": 1},
              {"id": "prod", "label": "产品", "fromCol": 2, "toCol": 3, "variant": "emphasis"},
              {"id": "rev", "label": "变现", "fromCol": 4, "toCol": 5}]
    return lanes, nodes, edges, phases, [mkt["id"], prod["id"], rev["id"], risk["id"]]


_FAM_BUILDERS = {
    "commission":   _fam_commission,
    "subscription": _fam_subscription,
    "supply_chain": _fam_supply_chain,
    "creator":      _fam_creator,
    "agency":       _fam_agency,
    "asset":        _fam_asset,
    "generic":      _fam_generic,
}


def build_workflow(m: dict) -> dict:
    """商业模式 → archify workflow 流程图。
    按商业模式族分类（classify_family），每族一种独立骨架：
      泳道数 / 列位 / 节点类型 / 连线语义 / phase 都不同。
    节点 sublabel 从该模式的真实字段（target/revenue/moat/keys）取摘要。
    """
    rid = re.sub(r"[^a-zA-Z0-9_-]", "-", m["id"]).strip("-") or "model"
    fam = classify_family(m)
    lanes, nodes, edges, phases, main_path = _FAM_BUILDERS[fam](m, rid)
    sw = s(m["swot"], "s"); wk = s(m["swot"], "w")
    op = s(m["swot"], "o"); th = s(m["swot"], "t")
    cards = [
        {"dot": "emerald", "title": "优势 Strengths",
         "items": sw if sw else ["（待补）"]},
        {"dot": "rose", "title": "劣势 Weaknesses",
         "items": wk if wk else ["（待补）"]},
        {"dot": "cyan", "title": "机会 Opportunities",
         "items": op if op else ["（待补）"]},
        {"dot": "amber", "title": "威胁 Threats",
         "items": th if th else ["（待补）"]},
    ]
    return {
        "schema_version": 1,
        "diagram_type": "workflow",
        "meta": {
            "title": m["name"][:40],
            "subtitle": f"{m['region']} · {m['industry']} · {m['scale']} · {m['channel']} · {FAMILY_LABEL[fam]}",
            "quality_profile": "standard",
            "output": f"{m['id']}.html",
        },
        "lanes": lanes,
        "phases": phases,
        "mainPath": main_path,
        "nodes": nodes,
        "edges": edges,
        "cards": cards,
    }


def render_workflow(m: dict) -> Path:
    ir = build_workflow(m)
    tmp = ROOT / "scripts" / f".tmp-{m['id']}.json"
    tmp.write_text(json.dumps(ir, ensure_ascii=False, indent=1), encoding="utf-8")
    out = MODELS_OUT / f"{m['id']}.html"
    r = subprocess.run(["node", str(ARCHIFY), "render", "workflow", str(tmp), str(out)],
                       capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"archify render 失败 [{m['id']}]: {r.stderr[-800:]}")
    return out


def esc(s) -> str:
    s = str(s)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


def li(items) -> str:
    return "".join(f"<li>{esc(x)}</li>" for x in items)


def render_model_page(m: dict) -> None:
    dims = {"industry": m["industry"], "region": m["region"],
            "scale": m["scale"], "channel": m["channel"]}
    # 图高随泳道数变化：viewBox 高=52+L×104+(L−1)×20+124；统一 720 宽 → aspect-ratio 720/高
    n_lanes = len(build_workflow(m)["lanes"])
    diag_h = 52 + n_lanes * 104 + (n_lanes - 1) * 20 + 124
    chips = "".join(f'<span class="chip">{esc(k)}：{esc(v)}</span>' for k, v in dims.items())
    srcs = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>'
                   for u in m["sources"])
    swot_html = ""
    for key, title, dot in (("s", "优势 Strengths", "green"),
                            ("w", "劣势 Weaknesses", "rose"),
                            ("o", "机会 Opportunities", "cyan"),
                            ("t", "威胁 Threats", "yellow")):
        items = s(m["swot"], key)
        swot_html += f'<div class="swot {dot}"><h3>{title}</h3><ul>{li(items)}</ul></div>'
    page = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(m['name'])} · 商业模式情报站</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
:root {{ --bg:{C_BG}; --bg0:{C_BG0}; --fg:{C_FG}; --dim:{C_DIM};
  --acc:{C_ACCENT}; --green:{C_GREEN}; --aqua:{C_AQUA}; --red:{C_RED}; --purple:{C_PURPLE}; --blue:{C_BLUE}; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; background:var(--bg); color:var(--fg);
  font-family:"Maple Mono NF CN","PingFang SC","Microsoft YaHei UI",system-ui,sans-serif; }}
* {{ scrollbar-width:thin; scrollbar-color:color-mix(in srgb,var(--fg) 28%,transparent) transparent; }}
*::-webkit-scrollbar {{ width:8px; height:8px; }}
*::-webkit-scrollbar-track {{ background:transparent; }}
*::-webkit-scrollbar-thumb {{ background:color-mix(in srgb,var(--fg) 22%,transparent); border-radius:999px; }}
body {{ padding:32px 20px 80px; }}
.wrap {{ max-width:1200px; margin:0 auto; }}
a {{ color:var(--aqua); }}
.bread {{ color:var(--dim); font-size:14px; margin-bottom:8px; }}
.bread a {{ color:var(--dim); text-decoration:none; }} .bread a:hover {{ color:var(--aqua); }}
h1 {{ font-size:30px; margin:4px 0 10px; }}
.chips {{ margin:6px 0 18px; display:flex; flex-wrap:wrap; gap:8px; }}
.chip {{ background:var(--bg0); border:1px solid color-mix(in srgb,var(--fg) 18%,transparent);
  border-radius:999px; padding:4px 14px; font-size:14px; color:var(--dim); }}
.diagram {{ background:var(--bg0); border:1px solid color-mix(in srgb,var(--fg) 14%,transparent);
  border-radius:10px; padding:10px; margin:8px 0 26px; cursor:zoom-in; position:relative; }}
.diagram::after {{ content:"🔍 点击放大"; position:absolute; right:12px; top:10px; font-size:12px;
  color:var(--dim); background:var(--bg0); padding:2px 8px; border-radius:999px;
  border:1px solid color-mix(in srgb,var(--fg) 18%,transparent); pointer-events:none; }}
.diagram iframe {{ width:100%; height:auto; aspect-ratio:720/{diag_h}; border:0;
  border-radius:6px; background:var(--bg0); display:block; pointer-events:none; }}
.hit {{ position:absolute; inset:0; cursor:zoom-in; }}
.zview {{ position:fixed; inset:0; z-index:99; background:#000; display:none; overflow:auto; }}
.zview.on {{ display:block; }}
.zview iframe {{ display:block; min-width:720px; width:100%; height:auto; aspect-ratio:720/{diag_h}; border:0;
  background:var(--bg0); margin:0 auto; }}
.zclose {{ position:fixed; top:10px; right:14px; z-index:100; background:var(--bg0);
  border:1px solid color-mix(in srgb,var(--fg) 30%,transparent); color:var(--fg);
  font-size:18px; padding:3px 12px; border-radius:999px; cursor:pointer; }}
.explain {{ background:var(--bg0); border-left:3px solid var(--acc); border-radius:0 8px 8px 0;
  padding:18px 22px; margin:0 0 26px; }}
.explain h2 {{ margin:0 0 10px; font-size:20px; color:var(--acc); }}
.explain p {{ margin:8px 0 22px; line-height:1.75; font-size:16px; }}
.explain ul {{ margin:6px 0; padding-left:22px; }}
.explain li {{ line-height:1.7; font-size:16px; margin:4px 0; }}
.swot-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:12px; margin:14px 0 22px; }}
.swot {{ background:var(--bg); border:1px solid color-mix(in srgb,var(--fg) 16%,transparent);
  border-radius:8px; padding:12px 16px; }}
.swot.green {{ border-top:3px solid var(--green); }}
.swot.rose {{ border-top:3px solid var(--red); }}
.swot.cyan {{ border-top:3px solid var(--aqua); }}
.swot.yellow {{ border-top:3px solid var(--acc); }}
.swot h3 {{ margin:0 0 8px; font-size:15px; }}
.swot ul {{ margin:0; padding-left:18px; }}
.swot li {{ font-size:14px; line-height:1.6; margin:4px 0; }}
.src {{ color:var(--dim); font-size:14px; }}
.src ul {{ margin:6px 0 0; padding-left:22px; }}
.src li {{ margin:4px 0; word-break:break-all; }}
.back {{ display:inline-block; margin-top:26px; padding:8px 18px; background:var(--bg0);
  border:1px solid color-mix(in srgb,var(--fg) 22%,transparent); border-radius:8px;
  color:var(--fg); text-decoration:none; font-size:15px; }}
.back:hover {{ border-color:var(--acc); color:var(--acc); }}
{FONT_STYLE}
</style></head><body><div class="wrap">
<div class="bread"><svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" style="width:22px;height:22px;vertical-align:-5px;margin-right:6px;;" aria-hidden="true"><rect x="2" y="2" width="44" height="44" rx="11" fill="#1d2021"/><rect x="2" y="2" width="44" height="44" rx="11" stroke="#ebdbb2" stroke-opacity="0.25" stroke-width="1.4"/><path d="M24 11v8M37 24h-8M24 37v-8M11 24h8" stroke="#ebdbb2" stroke-opacity="0.4" stroke-width="2" stroke-linecap="round"/><circle cx="24" cy="9.5" r="4.2" fill="#b8bb26"/><circle cx="38.5" cy="24" r="4.2" fill="#83a598"/><circle cx="24" cy="38.5" r="4.2" fill="#8ec07c"/><circle cx="9.5" cy="24" r="4.2" fill="#d3869b"/><circle cx="24" cy="24" r="6" fill="#fabd2f"/><path d="M24 20.5v7M20.5 24h7" stroke="#1d2021" stroke-width="2.2" stroke-linecap="round"/></svg><a href="index.html">← 返回商业模式情报站</a></div>
<h1>{esc(m['name'])}</h1>
<div class="chips">{chips}</div>
<div class="diagram"><iframe src="models/{esc(m['id'])}.html?embed=1" title="模式流程图"></iframe>
<div class="hit"></div></div>
<div class="zview" id="zview"><iframe src="models/{esc(m['id'])}.html?embed=1" title="模式流程图(全屏)"></iframe>
<button class="zclose" aria-label="关闭">✕</button></div>
<script>
const z=document.getElementById('zview');
document.querySelector('.diagram').addEventListener('click',()=>z.classList.add('on'));
z.querySelector('.zclose').addEventListener('click',e=>{{e.stopPropagation();z.classList.remove('on');}});
z.addEventListener('click',e=>{{if(e.target===z)z.classList.remove('on');}});
document.addEventListener('keydown',e=>{{if(e.key==='Escape')z.classList.remove('on');}});
</script>
<div class="explain">
  <h2>模式全解</h2>
  <p><strong>📌 背景：</strong>{esc(m['background'])}</p>
  <p><strong>👤 目标客户：</strong>{esc(m['target'])}</p>
  <p><strong>💰 盈利点：</strong>{esc(m['revenue'])}</p>
  <p><strong>🧮 成本结构：</strong>{esc(m['cost'])}</p>
  <p><strong>🛡️ 护城河：</strong>{esc(m['moat'])}</p>
  <p><strong>🔑 成功关键：</strong></p><ul>{li(m.get('keys', []))}</ul>
  <p><strong>⚠️ 风险：</strong></p><ul>{li(m.get('risks', []))}</ul>
  <p><strong>🏢 案例：</strong></p><ul>{li(m.get('example', []))}</ul>
  <div class="swot-grid">{swot_html}</div>
</div>
<div class="src"><strong>来源</strong><ul>{"".join(srcs)}</ul></div>
<a class="back" href="index.html">← 返回索引</a>
</div></body></html>"""
    (SITE / f"{m['id']}.html").write_text(page, encoding="utf-8")

# ---------------------------------------------------------------------------
# 板块二 journey：发家路径时间线 workflow 骨架 + 详情页
# ---------------------------------------------------------------------------
def build_journey_timeline(m: dict) -> dict:
    rid = re.sub(r"[^a-zA-Z0-9_-]", "-", m["id"]).strip("-") or "journey"
    ms = m.get("milestones", [])
    # 三泳道：主时间带（阶段序列） / 失败与拐点事件带 / 关键数据带
    lanes = [{"id": "main", "label": "发家路径"},
             {"id": "events", "label": "失败与拐点"},
             {"id": "data", "label": "关键数据"}]
    nodes, edges, phases = [], [], []
    main_path = []
    # 可视化最多 3 个关键阶段（col 0/2/4 跳排避免相邻像素过密）
    # 选取优先级：失败 < 拐点/转折 < PMF < 增长；其余阶段在详情页文字呈现
    def _rank(st):
        o = st.get("outcome", "")
        if o == "失败": return 0
        if o in ("拐点", "转折"): return 1
        if o == "PMF": return 2
        return 3
    if len(ms) <= 3:
        viz = ms
    else:
        # 各优先级取一个，凑不够 3 个再补首尾
        picked, seen = [], set()
        for r in (0, 1, 2, 3):
            for i, st in enumerate(ms):
                if i in seen: continue
                if _rank(st) == r:
                    picked.append(st); seen.add(i); break
            if len(picked) == 3: break
        if len(picked) < 3:
            for i, st in enumerate(ms):
                if i in seen: continue
                picked.append(st); seen.add(i)
                if len(picked) == 3: break
        viz = picked
    nid_prev = None
    for i, st in enumerate(viz):
        col = i * 2
        outcome = st.get("outcome", "")
        ntype = "security" if outcome == "失败" else ("messagebus" if outcome in ("拐点","转折") else "cloud")
        nid = f"{rid}-main-{col}"
        nodes.append({"id": nid, "lane": "main", "col": col, "type": ntype,
                       "label": sub(st.get("stage", ""), 8),
                       "sublabel": sub(st.get("time", ""), 8)})
        main_path.append(nid)
        if outcome in ("失败", "拐点", "转折"):
            eid = f"{rid}-ev-{col}"
            nodes.append({"id": eid, "lane": "events", "col": col, "type": "security",
                          "label": "失败" if outcome == "失败" else "拐点",
                          "sublabel": sub(st.get("detail", ""), 8)})
            if nid_prev:
                edges.append(_edge(rid, f"te{i}", nid_prev, eid, variant="security",
                                   route="drop", fromSide="bottom", toSide="top", labelSegment=1))
            else:
                edges.append(_edge(rid, f"te{i}", nid, eid, variant="security",
                                   route="drop", fromSide="bottom", toSide="top", labelSegment=1))
        if nid_prev:
            edges.append(_edge(rid, f"tm{i}", nid_prev, nid, variant="default"))
        nid_prev = nid
    # 数据带
    if m.get("metrics"):
        mid = f"{rid}-data-0"
        first_metric = list(m["metrics"].items())[0]
        nodes.append({"id": mid, "lane": "data", "col": 0, "type": "database",
                       "label": "核心数据",
                       "sublabel": sub(f"{first_metric[0]}={first_metric[1]}", 10)})
    cards = [
        {"dot": "amber", "title": "失败与踩坑",
         "items": [sub(x, 40) for x in m.get("failures", [])] or ["（待补）"]},
        {"dot": "emerald", "title": "关键成功要素",
         "items": [sub(x, 40) for x in m.get("keys", [])] or ["（待补）"]},
        {"dot": "cyan", "title": "经验教训",
         "items": [sub(x, 40) for x in m.get("lessons", [])] or ["（待补）"]},
    ]
    phases = [{"id": "p0", "label": "起步", "fromCol": 0, "toCol": 1},
              {"id": "p1", "label": "探索", "fromCol": 2, "toCol": 3},
              {"id": "p2", "label": "增长", "fromCol": 4, "toCol": 4, "variant": "emphasis"}]
    return {
        "schema_version": 1, "diagram_type": "workflow",
        "meta": {"title": m["name"][:40],
                 "subtitle": f"{m.get('region','')} · {m.get('industry','')} · 发家路径",
                 "quality_profile": "standard", "output": f"{m['id']}.html"},
        "lanes": lanes, "phases": phases, "mainPath": main_path,
        "nodes": nodes, "edges": edges, "cards": cards,
    }


def render_journey_page(m: dict) -> None:
    ir = build_journey_timeline(m)
    tmp = ROOT / "scripts" / f".tmp-{m['id']}.json"
    tmp.write_text(json.dumps(ir, ensure_ascii=False, indent=1), encoding="utf-8")
    out = MODELS_OUT / f"{m['id']}.html"
    r = subprocess.run(["node", str(ARCHIFY), "render", "workflow", str(tmp), str(out)],
                       capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"archify render 失败 [{m['id']}]: {r.stderr[-800:]}")
    dims = {"industry": m["industry"], "region": m["region"], "scale": m["scale"], "channel": m["channel"]}
    chips = "".join(f'<span class="chip">{esc(k)}：{esc(v)}</span>' for k, v in dims.items())
    srcs = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>' for u in m["sources"])
    ms_html = "".join(
        f'<div class="mstone {"fail" if x.get("outcome")=="失败" else "turn" if x.get("outcome") in ("拐点","转折") else "ok"}">'
        f'<div class="ms-time">{esc(x.get("time",""))}</div>'
        f'<div class="ms-stage">{esc(x.get("stage",""))} <span class="ms-tag">{esc(x.get("outcome",""))}</span></div>'
        f'<div class="ms-detail">{esc(x.get("detail",""))}</div></div>' for x in m.get("milestones", []))
    metrics_html = "".join(f'<li><strong>{esc(k)}</strong>：{esc(v)}</li>' for k, v in m.get("metrics", {}).items())
    page = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(m['name'])} · 发家路径 · 商业模式情报站</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
:root {{ --bg:{C_BG}; --bg0:{C_BG0}; --fg:{C_FG}; --dim:{C_DIM}; --acc:{C_ACCENT}; --green:{C_GREEN}; --aqua:{C_AQUA}; --red:{C_RED}; }}
* {{ box-sizing:border-box; }} html,body {{ margin:0;padding:0;background:var(--bg);color:var(--fg);font-family:"Maple Mono NF CN","PingFang SC","Microsoft YaHei UI",system-ui,sans-serif; }}
body {{ padding:32px 20px 80px; }} .wrap {{ max-width:1200px;margin:0 auto; }}
a {{ color:var(--aqua); }} .bread {{ color:var(--dim);font-size:14px;margin-bottom:8px; }} .bread a {{ color:var(--dim);text-decoration:none; }} .bread a:hover {{ color:var(--aqua); }}
h1 {{ font-size:30px;margin:4px 0 10px; }} .chips {{ margin:6px 0 18px;display:flex;flex-wrap:wrap;gap:8px; }}
.chip {{ background:var(--bg0);border:1px solid color-mix(in srgb,var(--fg) 18%,transparent);border-radius:999px;padding:4px 14px;font-size:14px;color:var(--dim); }}
.diagram {{ background:var(--bg0);border:1px solid color-mix(in srgb,var(--fg) 14%,transparent);border-radius:10px;padding:10px;margin:8px 0 26px; }}
.diagram iframe {{ width:100%;height:auto;aspect-ratio:720/520;border:0;border-radius:6px;background:var(--bg0);display:block; }}
.sub {{ color:var(--dim);font-size:15px;margin:0 0 12px; }}
.section {{ background:var(--bg0);border-left:3px solid var(--acc);border-radius:0 8px 8px 0;padding:18px 22px;margin:0 0 26px; }}
.section h2 {{ margin:0 0 10px;font-size:20px;color:var(--acc); }}
.mstone {{ background:var(--bg);border:1px solid color-mix(in srgb,var(--fg) 14%,transparent);border-radius:8px;padding:12px 16px;margin:8px 0; }}
.mstone.fail {{ border-left:3px solid var(--red); }} .mstone.turn {{ border-left:3px solid var(--acc); }} .mstone.ok {{ border-left:3px solid var(--green); }}
.ms-time {{ color:var(--dim);font-size:13px; }} .ms-stage {{ font-size:16px;font-weight:500;margin:4px 0; }} .ms-tag {{ font-size:12px;color:var(--acc);background:color-mix(in srgb,var(--acc) 14%,transparent);padding:1px 8px;border-radius:999px; }}
.ms-detail {{ font-size:14px;line-height:1.7;margin:6px 0 0; }}
.kw {{ display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin:8px 0; }}
.kw ul {{ margin:0;padding-left:18px; }} .kw li {{ font-size:14px;line-height:1.7;margin:4px 0; }}
.src {{ color:var(--dim);font-size:14px; }} .src ul {{ margin:6px 0 0;padding-left:22px; }} .src li {{ margin:4px 0;word-break:break-all; }}
.back {{ display:inline-block;margin-top:26px;padding:8px 18px;background:var(--bg0);border:1px solid color-mix(in srgb,var(--fg) 22%,transparent);border-radius:8px;color:var(--fg);text-decoration:none;font-size:15px; }}
{FONT_STYLE}
</style></head><body><div class="wrap">
<div class="bread"><a href="index.html">← 返回商业模式情报站</a></div>
<h1>{esc(m['name'])}</h1>
<div class="chips">{chips}</div>
<div class="sub">创办人：{esc(m.get('founders',''))} · {esc(m.get('company',''))}</div>
<div class="diagram"><iframe src="models/{esc(m['id'])}.html?embed=1" title="发家路径时间线"></iframe></div>
<div class="section"><h2>起步缘由</h2><p>{esc(m.get('origin',''))}</p></div>
<div class="section"><h2>发家里程碑</h2>{ms_html}</div>
<div class="section"><h2>转折点</h2><ul>{li(m.get('turning_points',[]))}</ul></div>
<div class="section"><h2>失败与踩坑</h2><ul>{li(m.get('failures',[]))}</ul></div>
<div class="kw"><div class="section"><h2>关键成功要素</h2><ul>{li(m.get('keys',[]))}</ul></div>
<div class="section"><h2>经验教训</h2><ul>{li(m.get('lessons',[]))}</ul></div></div>
<div class="section"><h2>核心数据</h2><ul>{metrics_html}</ul></div>
<div class="section"><h2>竞争对手 / 同行</h2><p>{esc(m.get('competitors',''))}</p></div>
<div class="src"><strong>来源</strong><ul>{"".join(srcs)}</ul></div>
<a class="back" href="index.html">← 返回索引</a>
</div></body></html>"""
    (SITE / f"{m['id']}.html").write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------------
# 板块三 scam：避坑指南骗局拆解 workflow 骨架 + 详情页
# ---------------------------------------------------------------------------
def build_scam_flow(m: dict) -> dict:
    rid = re.sub(r"[^a-zA-Z0-9_-]", "-", m["id"]).strip("-") or "scam"
    steps = m.get("how_it_works", [])
    lanes = [{"id": "scammer", "label": "骗子动作链"},
             {"id": "victim", "label": "受害者视角"},
             {"id": "defense", "label": "官方防线"}]
    nodes, edges, phases, main_path = [], [], [], []
    # 可视化最多 3 步（col 0/2/4 跳排）；余下步骤在详情页文字呈现
    viz_steps = steps[:3] if len(steps) > 3 else steps
    prev = None
    for i, step in enumerate(viz_steps):
        col = i * 2
        nid = f"{rid}-sc-{col}"
        nodes.append({"id": nid, "lane": "scammer", "col": col, "type": "security",
                      "label": f"第{i+1}步", "sublabel": sub(step, 8)})
        main_path.append(nid)
        vid = f"{rid}-vi-{col}"
        nodes.append({"id": vid, "lane": "victim", "col": col, "type": "database",
                      "label": "受害者看到", "sublabel": sub(step, 8)})
        if prev:
            edges.append(_edge(rid, f"es{i}", prev, nid, variant="security"))
        edges.append(_edge(rid, f"ev{i}", nid, vid, variant="default", route="drop",
                           fromSide="bottom", toSide="top", labelSegment=1))
        prev = nid
    # 官方防线带：红旗信号单点（与末 step 同 col，独立显示不连线避免穿越同 col 的 victim 节点）
    if m.get("red_flags"):
        fid = f"{rid}-def-0"
        last_col = (len(viz_steps) - 1) * 2 if viz_steps else 0
        nodes.append({"id": fid, "lane": "defense", "col": last_col, "type": "messagebus",
                      "label": "红旗信号", "sublabel": sub(m["red_flags"][0], 8)})
    cards = [
        {"dot": "rose", "title": "红旗信号（别上当）",
         "items": [sub(x, 40) for x in m.get("red_flags", [])] or ["（待补）"]},
        {"dot": "amber", "title": "真实案例",
         "items": [sub(x, 40) for x in m.get("real_cases", [])] or ["（待补）"]},
        {"dot": "emerald", "title": "怎么防护",
         "items": [sub(x, 40) for x in m.get("protection", [])] or ["（待补）"]},
    ]
    phases = [{"id": "hook", "label": "引流", "fromCol": 0, "toCol": 1, "variant": "emphasis"},
              {"id": "trap", "label": "收割", "fromCol": 2, "toCol": 4}]
    return {
        "schema_version": 1, "diagram_type": "workflow",
        "meta": {"title": m["name"][:40],
                 "subtitle": f"{m.get('region','')} · {m.get('industry','')} · 避坑指南",
                 "quality_profile": "standard", "output": f"{m['id']}.html"},
        "lanes": lanes, "phases": phases, "mainPath": main_path,
        "nodes": nodes, "edges": edges, "cards": cards,
    }


def render_scam_page(m: dict) -> None:
    ir = build_scam_flow(m)
    tmp = ROOT / "scripts" / f".tmp-{m['id']}.json"
    tmp.write_text(json.dumps(ir, ensure_ascii=False, indent=1), encoding="utf-8")
    out = MODELS_OUT / f"{m['id']}.html"
    r = subprocess.run(["node", str(ARCHIFY), "render", "workflow", str(tmp), str(out)],
                       capture_output=True, text=True)
    tmp.unlink(missing_ok=True)
    if r.returncode != 0:
        raise RuntimeError(f"archify render 失败 [{m['id']}]: {r.stderr[-800:]}")
    dims = {"industry": m["industry"], "region": m["region"], "scale": m["scale"], "channel": m["channel"]}
    chips = "".join(f'<span class="chip">{esc(k)}：{esc(v)}</span>' for k, v in dims.items())
    srcs = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>' for u in m["sources"])
    steps_html = "".join(f'<li>{esc(s)}</li>' for s in m.get("how_it_works", []))
    flags_html = "".join(f'<li>🚩 {esc(x)}</li>' for x in m.get("red_flags", []))
    cases_html = "".join(f'<li>{esc(c)}</li>' for c in m.get("real_cases", []))
    alerts_html = "".join(f'<li>{esc(a)}</li>' for a in m.get("official_alerts", []))
    prot_html = "".join(f'<li>✅ {esc(p)}</li>' for p in m.get("protection", []))
    page = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(m['name'])} · 避坑指南 · 商业模式情报站</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
:root {{ --bg:{C_BG}; --bg0:{C_BG0}; --fg:{C_FG}; --dim:{C_DIM}; --acc:{C_ACCENT}; --green:{C_GREEN}; --aqua:{C_AQUA}; --red:{C_RED}; }}
* {{ box-sizing:border-box; }} html,body {{ margin:0;padding:0;background:var(--bg);color:var(--fg);font-family:"Maple Mono NF CN","PingFang SC","Microsoft YaHei UI",system-ui,sans-serif; }}
body {{ padding:32px 20px 80px; }} .wrap {{ max-width:1200px;margin:0 auto; }}
a {{ color:var(--aqua); }} .bread {{ color:var(--dim);font-size:14px;margin-bottom:8px; }} .bread a {{ color:var(--dim);text-decoration:none; }} .bread a:hover {{ color:var(--aqua); }}
h1 {{ font-size:30px;margin:4px 0 10px; }} .chips {{ margin:6px 0 18px;display:flex;flex-wrap:wrap;gap:8px; }}
.chip {{ background:var(--bg0);border:1px solid color-mix(in srgb,var(--fg) 18%,transparent);border-radius:999px;padding:4px 14px;font-size:14px;color:var(--dim); }}
.diagram {{ background:var(--bg0);border:1px solid color-mix(in srgb,var(--fg) 14%,transparent);border-radius:10px;padding:10px;margin:8px 0 26px; }}
.diagram iframe {{ width:100%;height:auto;aspect-ratio:720/520;border:0;border-radius:6px;background:var(--bg0);display:block; }}
.warn {{ background:var(--bg0);border-left:3px solid var(--red);border-radius:0 8px 8px 0;padding:14px 18px;margin:0 0 22px;color:var(--red);font-size:15px; }}
.section {{ background:var(--bg0);border-left:3px solid var(--acc);border-radius:0 8px 8px 0;padding:18px 22px;margin:0 0 26px; }}
.section h2 {{ margin:0 0 10px;font-size:20px;color:var(--acc); }}
.section h2.alert {{ color:var(--red); }}
.section ul {{ margin:6px 0;padding-left:22px; }} .section li {{ line-height:1.7;font-size:15px;margin:4px 0; }}
.legal {{ background:var(--bg0);border:1px dashed var(--dim);border-radius:8px;padding:12px 16px;margin:0 0 22px;font-size:14px;color:var(--dim); }}
.src {{ color:var(--dim);font-size:14px; }} .src ul {{ margin:6px 0 0;padding-left:22px; }} .src li {{ margin:4px 0;word-break:break-all; }}
.back {{ display:inline-block;margin-top:26px;padding:8px 18px;background:var(--bg0);border:1px solid color-mix(in srgb,var(--fg) 22%,transparent);border-radius:8px;color:var(--fg);text-decoration:none;font-size:15px; }}
{FONT_STYLE}
</style></head><body><div class="wrap">
<div class="bread"><a href="index.html">← 返回商业模式情报站</a></div>
<h1>{esc(m['name'])}</h1>
<div class="chips">{chips}</div>
<div class="warn">⚠️ 本条目汇总骗局手法与官方警示，不构成投资或法律建议；如遇受害请立即报警（12339）。</div>
<div class="diagram"><iframe src="models/{esc(m['id'])}.html?embed=1" title="骗局拆解图"></iframe></div>
<div class="section"><h2>骗谁</h2><p>{esc(m.get('victims',''))}</p></div>
<div class="section"><h2 class="alert">骗局怎么运作</h2><ul>{steps_html}</ul></div>
<div class="section"><h2 class="alert">红旗信号（看到这些快跑）</h2><ul>{flags_html}</ul></div>
<div class="section"><h2>真实案例</h2><ul>{cases_html}</ul></div>
<div class="section"><h2>官方态度</h2><ul>{alerts_html}</ul></div>
<div class="section"><h2>怎么防护</h2><ul>{prot_html}</ul></div>
<div class="legal">⚖️ {esc(m.get('legal_note',''))}</div>
<div class="src"><strong>来源</strong><ul>{"".join(srcs)}</ul></div>
<a class="back" href="index.html">← 返回索引</a>
</div></body></html>"""
    (SITE / f"{m['id']}.html").write_text(page, encoding="utf-8")


def build_index(models: list[dict]) -> None:
    by_type = {'model': [], 'journey': [], 'scam': []}
    for m in models:
        by_type.setdefault(m.get('type', 'model'), []).append(m)
    # 过滤器维度仅对 model 有意义（journey/scam 维度过窄）
    options = {}
    for dim in DIMENSIONS:
        options[dim] = sorted({mm.get(dim, '') for mm in by_type['model'] if mm.get(dim)})
    opt_html = ""
    for dim, label in DIMENSIONS.items():
        opts = "".join(f'<option value="{esc(o)}">{esc(o)}</option>' for o in options[dim])
        opt_html += (f'<select id="f-{dim}" data-dim="{dim}"><option value="">{label}：全部</option>{opts}</select>')
    model_cards = []
    for m in by_type['model']:
        dims = {"industry": m.get('industry',''), "region": m.get('region',''),
                "scale": m.get('scale',''), "channel": m.get('channel','')}
        data_attr = " ".join(f'data-{k}="{esc(v)}"' for k, v in dims.items())
        model_cards.append(f"""<article class="card" {data_attr}>
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="card-head"><h3>{esc(m['name'])}</h3><span class="arrow">→</span></div>
    <p class="card-how">{esc(str(m.get('revenue',''))[:100])}</p>
    <div class="tags">{''.join(f'<span class="t">{esc(dims[k])}</span>' for k in DIMENSIONS)}</div>
  </a>
</article>""")
    journey_cards = []
    for m in by_type['journey']:
        ms = m.get('milestones', [])
        n_fail = sum(1 for x in ms if x.get('outcome') == '失败')
        tags = {'industry': m.get('industry',''), 'region': m.get('region',''), 'scale': m.get('scale','')}
        tag_html = "".join(f'<span class="t">{esc(tags[k])}</span>' for k in ('industry','region','scale') if tags[k])
        journey_cards.append(f"""<article class="card journey-card">
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="card-head"><h3>🛤 {esc(m['name'])}</h3><span class="arrow">→</span></div>
    <p class="card-how">创办：{esc(m.get('founders',''))} · {len(ms)} 阶段 · {n_fail} 次失败踩坑</p>
    <div class="tags">{tag_html}</div>
  </a>
</article>""")
    scam_cards = []
    for m in by_type['scam']:
        tags = {'industry': m.get('industry',''), 'region': m.get('region',''), 'scale': m.get('scale','')}
        tag_html = "".join(f'<span class="t">{esc(tags[k])}</span>' for k in ('industry','region','scale') if tags[k])
        scam_cards.append(f"""<article class="card scam-card">
  <a class="card-link" href="{esc(m['id'])}.html">
    <div class="card-head"><h3>⚠️ {esc(m['name'])}</h3><span class="arrow">→</span></div>
    <p class="card-how">受骗人群：{esc(str(m.get('victims',''))[:80])}</p>
    <div class="tags">{tag_html}</div>
  </a>
</article>""")
    index = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>商业模式情报站 · 2026 商业情报图鉴</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
:root {{ --bg:{C_BG}; --bg0:{C_BG0}; --fg:{C_FG}; --dim:{C_DIM};
  --acc:{C_ACCENT}; --green:{C_GREEN}; --aqua:{C_AQUA}; --red:{C_RED}; --purple:{C_PURPLE}; --blue:{C_BLUE}; }}
* {{ box-sizing:border-box; }}
html,body {{ margin:0; padding:0; background:var(--bg); color:var(--fg);
  font-family:"Maple Mono NF CN","PingFang SC","Microsoft YaHei UI",system-ui,sans-serif; }}
* {{ scrollbar-width:thin; scrollbar-color:color-mix(in srgb,var(--fg) 28%,transparent) transparent; }}
*::-webkit-scrollbar {{ width:8px; height:8px; }}
*::-webkit-scrollbar-thumb {{ background:color-mix(in srgb,var(--fg) 22%,transparent); border-radius:999px; }}
body {{ padding:40px 20px 100px; }}
.wrap {{ max-width:1200px; margin:0 auto; }}
header {{ margin-bottom:22px; }}
.brand {{ display:flex; align-items:center; gap:16px; }}
.brand svg {{ flex:none; width:52px; height:52px; }}
h1 {{ font-size:34px; margin:0 0 6px; }}
h1 .acc {{ color:var(--acc); }}
.sub {{ color:var(--dim); font-size:15px; margin:0 0 18px; }}
.tabs {{ display:flex; gap:4px; margin:0 0 22px; border-bottom:1px solid color-mix(in srgb,var(--fg) 18%,transparent); flex-wrap:wrap; }}
.tab {{ background:none; border:none; color:var(--dim); font-size:18px; padding:10px 22px; cursor:pointer;
  font-family:inherit; border-bottom:2px solid transparent; margin-bottom:-1px; }}
.tab.active {{ color:var(--fg); border-bottom-color:var(--acc); }}
.tab:hover {{ color:var(--fg); }}
.tab .n {{ font-size:13px; color:var(--dim); margin-left:6px; }}
.tab.active .n {{ color:var(--acc); }}
.filters {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:24px; }}
.filters.hide {{ display:none; }}
.filters select {{ background:var(--bg0); color:var(--fg); border:1px solid color-mix(in srgb,var(--fg) 24%,transparent);
  border-radius:8px; padding:7px 12px; font-size:14px; font-family:inherit; }}
.filters select:focus {{ outline:none; border-color:var(--acc); }}
.count {{ color:var(--dim); font-size:14px; margin-bottom:14px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:16px; }}
.card {{ background:var(--bg0); border:1px solid color-mix(in srgb,var(--fg) 14%,transparent);
  border-radius:10px; overflow:hidden; transition:transform .12s ease, border-color .12s ease; }}
.card:hover {{ transform:translateY(-2px); border-color:var(--acc); }}
.card-link {{ display:block; padding:18px 18px 14px; color:var(--fg); text-decoration:none; }}
.card-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:10px; }}
.card-head h3 {{ margin:0; font-size:18px; line-height:1.4; }}
.arrow {{ color:var(--dim); font-size:20px; transition:color .12s; }}
.card:hover .arrow {{ color:var(--acc); }}
.card-how {{ color:var(--dim); font-size:14px; line-height:1.6; margin:10px 0 12px; }}
.tags {{ display:flex; flex-wrap:wrap; gap:6px; }}
.t {{ font-size:12px; color:var(--aqua); background:color-mix(in srgb,var(--aqua) 12%,transparent);
  padding:2px 10px; border-radius:999px; }}
.empty {{ color:var(--dim); font-size:16px; display:none; }}
footer {{ margin-top:40px; color:var(--dim); font-size:13px; }}
{FONT_STYLE}
</style></head><body><div class="wrap">
<header>
  <div class="brand"><svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="商业模式情报站 logo">
  <rect x="2" y="2" width="44" height="44" rx="11" fill="#1d2021"/>
  <rect x="2" y="2" width="44" height="44" rx="11" stroke="#ebdbb2" stroke-opacity="0.25" stroke-width="1.4"/>
  <path d="M24 11v8M37 24h-8M24 37v-8M11 24h8" stroke="#ebdbb2" stroke-opacity="0.4" stroke-width="2" stroke-linecap="round"/>
  <circle cx="24" cy="9.5" r="4.2" fill="#b8bb26"/>
  <circle cx="38.5" cy="24" r="4.2" fill="#83a598"/>
  <circle cx="24" cy="38.5" r="4.2" fill="#8ec07c"/>
  <circle cx="9.5" cy="24" r="4.2" fill="#d3869b"/>
  <circle cx="24" cy="24" r="6" fill="#fabd2f"/>
  <path d="M24 20.5v7M20.5 24h7" stroke="#1d2021" stroke-width="2.2" stroke-linecap="round"/>
  </svg>
  <div>
  <h1>商业模式情报站 <span class="acc">· biz.saaaai.com</span></h1>
  <p class="sub">三大板块：💰 赚钱模式（怎么赚钱）· 🛤 发家路径（公司怎么走过来）· ⚠️ 避坑指南（怎么不被骗）。数据由 AI 持续自动采集。</p>
  </div></div>
</header>
<div class="tabs">
  <button class="tab active" data-tab="model">💰 赚钱模式 <span class="n">{len(by_type['model'])}</span></button>
  <button class="tab" data-tab="journey">🛤 发家路径 <span class="n">{len(by_type['journey'])}</span></button>
  <button class="tab" data-tab="scam">⚠️ 避坑指南 <span class="n">{len(by_type['scam'])}</span></button>
</div>
<div class="filters" id="filters">{opt_html}</div>
<div class="count" id="count">共 {len(by_type['model'])} 条</div>
<div class="grid" id="grid-model">{''.join(model_cards)}</div>
<div class="grid" id="grid-journey" style="display:none">{''.join(journey_cards)}</div>
<div class="grid" id="grid-scam" style="display:none">{''.join(scam_cards)}</div>
<div class="empty" id="empty">没有匹配的条目，换一组筛选试试。</div>
<footer>· 生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')} · 全自动采集框架运行中 ·</footer>
</div>
<script>
const tabs = document.querySelectorAll('.tab');
const filters = document.getElementById('filters');
const count = document.getElementById('count');
const empty = document.getElementById('empty');
const grids = {{ model: document.getElementById('grid-model'),
                 journey: document.getElementById('grid-journey'),
                 scam: document.getElementById('grid-scam') }};
let active = 'model';
function apply() {{
  const grid = grids[active];
  const cards = grid.querySelectorAll('.card');
  const selects = filters.querySelectorAll('select');
  let n = 0;
  cards.forEach(c => {{
    let ok = true;
    if (active === 'model') {{
      selects.forEach(s => {{
        const v = s.value;
        if (v && c.dataset[s.dataset.dim] !== v) ok = false;
      }});
    }}
    c.style.display = ok ? '' : 'none';
    if (ok) n++;
  }});
  count.textContent = '共 ' + n + ' 条';
  empty.style.display = n ? 'none' : 'block';
  grid.style.display = n ? '' : 'none';
}}
tabs.forEach(t => t.addEventListener('click', () => {{
  tabs.forEach(x => x.classList.toggle('active', x === t));
  active = t.dataset.tab;
  filters.classList.toggle('hide', active !== 'model');
  Object.entries(grids).forEach(([k,g]) => g.style.display = (k === active) ? '' : 'none');
  apply();
}}));
filters.querySelectorAll('select').forEach(s => s.addEventListener('change', apply));
</script>
</body></html>"""
    (SITE / "index.html").write_text(index, encoding="utf-8")


def write_favicon() -> None:
    """写入站点头像（独立 SVG，供 favicon link 引用）。"""
    svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
<rect x="2" y="2" width="44" height="44" rx="11" fill="#1d2021"/>
<rect x="2" y="2" width="44" height="44" rx="11" stroke="#ebdbb2" stroke-opacity="0.25" stroke-width="1.4"/>
<path d="M24 11v8M37 24h-8M24 37v-8M11 24h8" stroke="#ebdbb2" stroke-opacity="0.4" stroke-width="2" stroke-linecap="round"/>
<circle cx="24" cy="9.5" r="4.2" fill="#b8bb26"/>
<circle cx="38.5" cy="24" r="4.2" fill="#83a598"/>
<circle cx="24" cy="38.5" r="4.2" fill="#8ec07c"/>
<circle cx="9.5" cy="24" r="4.2" fill="#d3869b"/>
<circle cx="24" cy="24" r="6" fill="#fabd2f"/>
<path d="M24 20.5v7M20.5 24h7" stroke="#1d2021" stroke-width="2.2" stroke-linecap="round"/>
</svg>
"""
    (SITE / "favicon.svg").write_text(svg, encoding="utf-8")


def write_data_json(models: list[dict]) -> None:
    by_type = {"model": 0, "journey": 0, "scam": 0}
    for m in models:
        by_type[m.get("type", "model")] = by_type.get(m.get("type", "model"), 0) + 1
    manifest = {"updated": datetime.now().isoformat(timespec="seconds"),
                 "count": len(models), "by_type": by_type, "models": models}
    (SITE / "data.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def _check_ownership() -> str | None:
    """重建前自检：site/、data/ 产物若被其他用户（如 root）写入过，
    重建必然 PermissionError。提前诊断并提示修复，返回错误信息。"""
    import getpass
    import stat as stat_mod
    me = getpass.getuser()
    for base in (SITE, DATA):
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            try:
                st = p.stat()
            except OSError:
                continue
            import pwd
            try:
                owner = pwd.getpwuid(st.st_uid).pw_name
            except KeyError:
                owner = str(st.st_uid)
            if owner != me:
                return (f"发现 {p} 属主为 {owner}（当前用户 {me}），"
                        f"重建无法写入。请先执行："
                        f"chown -R {me} {SITE} {DATA}")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只重建指定 id")
    args = ap.parse_args()
    err = _check_ownership()
    if err:
        print(f"[err] {err}")
        return 1
    MODELS_OUT.mkdir(parents=True, exist_ok=True)
    models = load_models()
    if args.only:
        models = [m for m in models if m["id"] == args.only]
        if not models:
            raise SystemExit(f"无此 id: {args.only}")
    for m in models:
        mtype = m.get("type", "model")
        if mtype == "journey":
            render_journey_page(m)
        elif mtype == "scam":
            render_scam_page(m)
        else:
            render_workflow(m)
            render_model_page(m)
        print(f"[ok] {m['id']} ({mtype}) — {m['name']}")
    if not args.only:
        build_index(models)
        write_data_json(models)
        write_favicon()
        print(f"[ok] index.html 共 {len(models)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



