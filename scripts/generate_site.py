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
    "agent": ["id", "name", "industry", "region", "scale", "channel",
              "workflow", "setup", "tools", "revenue", "cost", "time",
              "entry", "keys", "risks", "example", "sources"],
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


def load_models() -> tuple[list[dict], list[str]]:
    """读取全部条目并在必填字段校验后返回 (valid_models, errors)。

    2026-08-09 修正（P0-5）：单条坏数据不再 raise SystemExit 全量中止——
    连环崩根因（real_cases 毒文件 / archify Label 超宽）曾拖死整条重建线。
    坏条目跳过并收集错误，由 main 决定：单条失败不阻塞其余 240 条重建。"""
    models = []
    errors: list[str] = []
    for f in sorted(DATA.glob("*.json")):
        if f.name.startswith("."):
            continue  # 隐藏状态文件（.collect_state.json / .collect.lock）
        if f.name in SKIP:
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            errors.append(f"[{f.name}] JSON 解析失败: {e}")
            continue
        for dim in NORM:
            if m.get(dim, "") in NORM[dim]:
                m[dim] = NORM[dim][m[dim]]
        m["industry"] = norm_industry(m.get("industry", ""))
        req = REQUIRED_BY_TYPE.get(m.get("type", "model"), REQUIRED)
        missing = [k for k in req if k not in m or m[k] in (None, "", [], {})]
        if missing:
            errors.append(f"[{f.name}] 缺必填字段(type={m.get('type','model')}): {missing}")
            continue
        if not slug_ok(m["id"]):
            errors.append(f"[{f.name}] id 非法: {m['id']}")
            continue
        models.append(m)
    if _IND_UNKNOWN:
        print(f"⚠️ industry 未命中目录（已归\"其他\"，考虑扩 IND_CATALOG/IND_KEYS）：{_IND_UNKNOWN}", file=__import__('sys').stderr)
    return models, errors


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


def _render_arch(ir: dict, rid: str) -> Path:
    """调 archify 渲染 workflow，输出 models/<rid>.html。

    2026-08-09 修正（P0-4）：archify validateWorkflow 对「Label 宽于节点」硬抛
    （executions.db 4 条实据：蕉内/安克/追觅「~109px wider than node (92px)」）——
    原实现 raise RuntimeError 让坏条目毒化整轮重建。现在失败后自动把全部 label
    缩短重试一次（label≤6字/sublabel≤10字），仍失败才 raise 由 main 跳过该条。"""
    out = MODELS_OUT / f"{rid}.html"
    for attempt, shorten in ((1, False), (2, True)):
        ir2 = ir
        if shorten:
            # 深度复制并缩短全部 label/sublabel（防超宽）
            import copy
            ir2 = copy.deepcopy(ir)
            for n in ir2.get("nodes", []):
                if isinstance(n.get("label"), str) and len(n["label"]) > 6:
                    n["label"] = n["label"][:6]
                if isinstance(n.get("sublabel"), str) and len(n["sublabel"]) > 10:
                    n["sublabel"] = n["sublabel"][:10]
            for p in ir2.get("phases", []):
                if isinstance(p.get("label"), str) and len(p["label"]) > 6:
                    p["label"] = p["label"][:6]
        tmp = ROOT / "scripts" / f".tmp-{rid}.json"
        tmp.write_text(json.dumps(ir2, ensure_ascii=False, indent=1), encoding="utf-8")
        try:
            r = subprocess.run(["node", str(ARCHIFY), "render", "workflow", str(tmp), str(out)],
                               capture_output=True, text=True)
            if r.returncode == 0:
                return out
            err = r.stderr[-800:]
            if not shorten and "wider than node" in err:
                print(f"      [retry] {rid} Label 超宽，缩短后重渲染…")
                continue
            raise RuntimeError(f"archify render 失败 [{rid}]: {err}")
        finally:
            tmp.unlink(missing_ok=True)
    raise RuntimeError(f"archify render 失败 [{rid}]（缩短 label 后仍失败）")


def render_workflow(m: dict) -> Path:
    ir = build_workflow(m)
    return _render_arch(ir, m["id"])


def esc(s) -> str:
    s = str(s)
    # 2026-08-09 修正（P0-6）：补 \n\r\t 转义——此前 91 处 data-search 属性值含
    # 原始换行导致 HTML 属性跨行（属性未闭合，解析边界错位）。属性值内统一转义为实体。
    # 2026-08-09 补丁（reviewer C2）：文中还有字面 `\n` 两字符转义（数据源存的反斜杠+n），
    # 一并替换为空格——否则属性值里出现字面转义序列（speech recognition.\n\n）。
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;")
             .replace("\n", "&#10;").replace("\r", "&#13;").replace("\t", "&#9;")
             .replace("\\n", " ").replace("\\r", " ").replace("\\t", " "))


def li(items) -> str:
    return "".join(f"<li>{esc(x)}</li>" for x in items)


# <<< G2-TEMPLATE-INJECT >>>
IND_EMOJI_M = {
    "AI/大模型": "🤖", "SaaS/企业软件": "💻", "云计算": "☁️", "其他": "🧩",
    "内容/创作者经济": "🎬", "医疗/养老": "🩺", "宠物": "🐾", "教育/知识付费": "📚",
    "旅游": "✈️", "本地生活": "🏪", "电商/零售": "🛒", "营销/广告": "📣",
    "金融科技": "💳", "餐饮/茶饮": "🍜",
}
DETAIL_CSS = """/* 贴纸详情页公共样式 */
:root {
  --bg:#282828; --card:#3c3836; --stroke:#1d2021; --fg:#ebdbb2; --dim:#a89984;
  --acc:#fabd2f; --blue:#83a598; --orange:#fe8019; --purple:#d3869b;
  --shadow-c:#1d2021; --tape:rgba(250,189,47,.20); --footer-fg:#ebdbb2;
  --ind-fintech:#b8bb26; --ind-ai:#83a598; --ind-ecom:#fe8019; --ind-other:#928374;
  --ind-mkt:#fb4934; --ind-med:#d3869b; --ind-content:#fabd2f; --ind-travel:#8ec07c; --ind-local:#a89984;
}
*{margin:0;padding:0;box-sizing:border-box}
html{scrollbar-color:color-mix(in srgb,var(--fg) 25%,transparent) transparent}
body{background:var(--bg);color:var(--fg);font-family:"Noto Sans SC","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;font-weight:500;-webkit-font-smoothing:antialiased}
::-webkit-scrollbar{width:14px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:color-mix(in srgb,var(--fg) 25%,transparent);border:4px solid var(--bg)}

/* sticky-bar */
.sticky-bar{background:var(--bg);border-bottom:3px solid var(--stroke);transition:box-shadow .2s,transform .3s}
.sticky-inner{max-width:1344px;margin:0 auto;padding:0 48px;display:flex;align-items:center;justify-content:space-between;height:48px}
.sticky-meta{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:13px;font-weight:700;color:var(--dim)}
/* header progress + color-ribbon + sticker（2026-08-16） */
.progress-wrap{height:3px;background:var(--card);overflow:hidden}
.progress-bar{height:100%;width:0%;background:linear-gradient(90deg,var(--blue),var(--orange),var(--purple),var(--green));transition:width .1s linear}
.color-ribbon{display:flex;height:6px;border-bottom:3px solid var(--stroke)}
.color-ribbon .seg{height:100%;position:relative;overflow:hidden;width:auto}
.color-ribbon .seg-model{width:45%;background:var(--blue)}
.color-ribbon .seg-journey{width:30%;background:var(--orange)}
.color-ribbon .seg-scam{width:25%;background:var(--purple)}
.color-ribbon .seg-agent{width:15%;background:var(--ind-fintech)}
.color-ribbon .seg::after{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,transparent 30%,rgba(255,255,255,.35) 50%,transparent 70%,transparent);background-size:300% 100%;animation:shimmer 3s ease-in-out infinite}
.sticker{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:16px;font-weight:800;background:var(--acc);color:#111;padding:5px 12px;border:2px solid var(--stroke);box-shadow:4px 4px 0 var(--shadow-c);display:inline-block;line-height:1.3;white-space:nowrap}


@keyframes shimmer{0%{background-position:0% 0}100%{background-position:300% 0}}
@media(max-width:720px){
  .sticky-inner{height:40px;padding:0 16px}
  .sticker{font-size:13px;padding:3px 8px;box-shadow:2px 2px 0 var(--shadow-c)}
}

.wrap{max-width:1344px;margin:0 auto;padding:0 48px}

/* crumb */
.crumb{display:flex;align-items:center;gap:10px;padding:24px 0 0;font-size:14px;font-weight:700}
.crumb a{color:var(--fg);text-decoration:none;border:2px solid var(--stroke);background:var(--card);box-shadow:3px 3px 0 var(--shadow-c);padding:6px 12px;font-weight:800}
.crumb a:hover{transform:translate(1px,1px)}
.crumb .here{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:12px;color:var(--dim);letter-spacing:.5px}

/* detail hero */
.detail-hero{display:flex;gap:16px;align-items:center;padding:16px 0 12px;position:relative}
.d-hero-emoji{flex:none;width:36px;height:36px;border:2px solid var(--stroke);background:var(--acc);color:#111;display:grid;place-items:center;font-size:18px}
.d-hero-body{flex:1;min-width:0}
.d-hero-body h1{font-size:24px;font-weight:900;line-height:1.3;letter-spacing:-.5px}
.d-hero-body .how{font-size:14px;line-height:1.6;color:var(--dim);max-width:720px;margin-top:4px}
.d-hero-badge{flex:none;font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:12px;font-weight:800;background:var(--stroke);color:var(--dim);padding:4px 10px;white-space:nowrap}

/* field grid */
.field-sec{padding-bottom:8px}
.sec{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;gap:16px;flex-wrap:wrap}
.sec h2{font-size:24px;font-weight:900;letter-spacing:-.5px;display:flex;align-items:center;gap:12px}
.sec h2::before{content:"";width:18px;height:18px;background:var(--acc);border:3px solid var(--stroke);display:inline-block}
.sec-note{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:12px;font-weight:700;color:var(--dim);letter-spacing:.5px}
.fields{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}
.field{background:var(--card);border:3px solid var(--stroke);box-shadow:var(--shadow-c) 6px 6px 0;padding:18px 16px;display:flex;flex-direction:column;gap:8px;min-width:0}
.field .k{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:12px;font-weight:800;letter-spacing:1.5px;color:var(--dim)}
.field .v{font-size:16px;font-weight:900;line-height:1.4;min-width:0;overflow:hidden}
.field .v .tag{display:inline-block;font-size:14px;font-weight:800;line-height:1;padding:7px 11px;border:2px solid var(--stroke);color:#fff;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.field .v .tag.bright{color:#111}
.tag.ind-fintech{background:var(--ind-fintech)} .tag.ind-ai{background:var(--ind-ai)}
.tag.ind-ecom{background:var(--ind-ecom)} .tag.ind-other{background:var(--ind-other)}
.tag.ind-mkt{background:var(--ind-mkt)} .tag.ind-med{background:var(--ind-med)}
.tag.ind-content{background:var(--ind-content)} .tag.ind-travel{background:var(--ind-travel)}
.tag.ind-local{background:var(--ind-local)}
.tag.ind-fintech,.tag.ind-ai,.tag.ind-ecom,.tag.ind-mkt,.tag.ind-med{color:#1d2021}
.scale{display:inline-flex;gap:3px;align-items:center}
.scale i{width:14px;height:14px;border:2px solid var(--stroke);box-sizing:border-box}
.scale i.on{background:var(--stroke)}

/* diagram */
.diagram{background:var(--card);border:4px solid var(--stroke);box-shadow:var(--shadow-c) 8px 8px 0;padding:10px;margin:0 0 32px;cursor:zoom-in;position:relative}
.diagram::after{content:"🔍 点击放大";position:absolute;right:12px;top:10px;font-size:12px;color:var(--dim);background:var(--card);padding:2px 8px;border:2px solid var(--stroke);pointer-events:none}
.diagram iframe{width:100%;height:auto;aspect-ratio:720/var(--diag-h,520);border:0;background:var(--bg);display:block;pointer-events:none}
.hit{position:absolute;inset:0;cursor:zoom-in}
.zview{position:fixed;inset:0;z-index:99;background:#000;display:none;overflow:auto}
.zview.on{display:block}
.zview iframe{display:block;min-width:720px;width:100%;height:auto;aspect-ratio:720/var(--diag-h,520);border:0;background:var(--bg);margin:0 auto}
.zclose{position:fixed;top:10px;right:14px;z-index:100;background:var(--bg);border:2px solid var(--stroke);color:var(--fg);font-size:18px;padding:3px 12px;cursor:pointer}

/* content sections */
.section{background:var(--card);border:4px solid var(--stroke);box-shadow:var(--shadow-c) 8px 8px 0;padding:24px 26px;margin:0 0 32px}
.section h2{font-size:20px;font-weight:900;margin-bottom:14px;display:flex;align-items:center;gap:10px;color:var(--fg)}
.section h2::before{content:"";width:14px;height:14px;background:var(--acc);border:2px solid var(--stroke)}
.section h2.alert{color:var(--red)}
.section p{font-size:15px;line-height:1.9;color:var(--dim);margin:8px 0}
.section ul{margin:6px 0 0;padding-left:22px}
.section li{font-size:15px;line-height:1.8;margin:6px 0}
.section li strong{color:var(--fg)}
.warn{background:var(--card);border:4px solid var(--red);box-shadow:var(--shadow-c) 8px 8px 0;padding:16px 20px;margin:0 0 32px;color:var(--red);font-size:15px;font-weight:700}
.legal{background:var(--card);border:3px dashed var(--dim);padding:14px 18px;margin:0 0 32px;font-size:14px;color:var(--dim)}
.mstone{background:var(--bg);border:3px solid var(--stroke);box-shadow:var(--shadow-c) 4px 4px 0;padding:14px 18px;margin:10px 0}
.mstone.fail{border-left:6px solid var(--red)} .mstone.turn{border-left:6px solid var(--acc)} .mstone.ok{border-left:6px solid var(--green)}
.ms-time{color:var(--dim);font-size:13px;font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-weight:700}
.ms-stage{font-size:17px;font-weight:800;margin:4px 0;color:var(--fg)}
.ms-tag{font-size:12px;color:var(--acc);background:var(--bg);border:2px solid var(--acc);padding:1px 8px;font-weight:800}
.ms-detail{font-size:14px;line-height:1.7;margin:6px 0 0;color:var(--dim)}
.kw{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;margin:8px 0 32px}
.swot-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:14px 0 32px}
.swot{background:var(--card);border:3px solid var(--stroke);box-shadow:var(--shadow-c) 4px 4px 0;padding:14px 16px}
.swot.green{border-top:6px solid var(--green)} .swot.rose{border-top:6px solid var(--red)}
.swot.cyan{border-top:6px solid var(--aqua)} .swot.yellow{border-top:6px solid var(--acc)}
.swot h3{margin:0 0 8px;font-size:15px;font-weight:900}
.swot ul{margin:0;padding-left:18px}
.swot li{font-size:14px;line-height:1.6;margin:4px 0;color:var(--dim)}
.src{color:var(--dim);font-size:14px;margin-bottom:32px}
.src ul{margin:6px 0 0;padding-left:22px}
.src li{margin:4px 0;word-break:break-all}
.src a{color:var(--aqua)}

/* card — compact design */
.related{margin:0 0 40px}
.related-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
a.card-link{display:block;text-decoration:none;color:inherit}
.card{position:relative;background:var(--card);border:2px solid var(--stroke);padding:12px 14px;display:flex;flex-direction:column;gap:5px;height:100%;min-width:0}
.card:hover{border-color:var(--acc)}
.card h3{font-size:17px;font-weight:800;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card p{font-size:13px;color:var(--dim);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.tag-row{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.tag-badge{font-size:10px;font-weight:800;padding:2px 7px;border-radius:2px;white-space:nowrap;line-height:1.5;color:#1d2021}
.tag-badge.bright{color:#111}
.tag-text{font-size:11px;font-weight:700;color:var(--dim);white-space:nowrap;line-height:1.5}

/* footer */
.footer{margin-top:64px;background:var(--stroke);color:var(--footer-fg);padding:26px 48px;display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}
.f-left{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.f-sticker{background:var(--acc);color:#111;border:3px solid var(--stroke);font-weight:900;font-size:15px;padding:9px 16px;transform:rotate(-1deg)}
.f-note{font-size:14px;font-weight:500;opacity:.85}
.f-right{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:14px;font-weight:700;letter-spacing:1px;opacity:.9}

@media (max-width:1100px){
  .fields{grid-template-columns:repeat(2,minmax(0,1fr))}
  .related-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .detail-hero{flex-direction:column;gap:12px}
  .d-hero-body h1{font-size:20px}
  .sticky-inner{padding:10px 20px}
}
@media (max-width:720px){
  .wrap{padding:0 20px}
}
"""

def _seo_desc(m: dict, limit: int = 150) -> str:
    """详情页 SEO 描述：按类型取代表性字段，压缩空白截断（纯 SEO 层，2026-08-13）。"""
    def pick(keys):
        for k in keys:
            v = m.get(k)
            if isinstance(v, list):
                v = v[0] if v else ""
            if v and str(v).strip():
                return str(v)
        return str(m.get("name", ""))
    t = m.get("type", "model")
    if t == "model":
        text = pick(("target", "revenue", "moat", "background"))
    elif t == "journey":
        text = pick(("origin", "company", "founders"))
    elif t == "scam":
        text = pick(("victims", "red_flags", "how_it_works"))
    else:
        text = pick(("workflow", "revenue", "entry"))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")

def _detail_head(m: dict, title_suffix: str) -> str:
    """详情页 <head> + CSS + 吸顶 sticky-bar markup（统一出口，3 类详情页自动覆盖）
    2026-08-13 SEO：动态 canonical + OG/Twitter + Article JSON-LD（纯 head 层，零视觉）。"""
    title = f"{m['name']} · {title_suffix} · 商业灵感 biz.saaaai.com"
    desc = _seo_desc(m)
    raw_url = f"https://biz.saaaai.com/{m['id']}.html"
    page_url = f"https://biz.saaaai.com/{esc(m['id'])}.html"
    ld = {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": m.get("name", ""),
        "description": desc,
        "mainEntityOfPage": {"@type": "WebPage", "@id": raw_url},
        "inLanguage": "zh-CN",
        "author": {"@type": "Organization", "name": "商业灵感 biz.saaaai.com"},
        "publisher": {"@type": "Organization", "name": "商业灵感 biz.saaaai.com"},
    }
    ld_html = json.dumps(ld, ensure_ascii=False)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{page_url}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="商业灵感 biz.saaaai.com">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{page_url}">
<meta property="og:locale" content="zh_CN">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{esc(title)}">
<meta name="twitter:description" content="{esc(desc)}">
<script type="application/ld+json">
{ld_html}
</script>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
{DETAIL_CSS}
</style>
</head>
<body>
<div class="sticky-bar" id="sticky-bar">
  <div class="progress-wrap"><div class="progress-bar" id="progress"></div></div>
  <div class="color-ribbon">
    <div class="seg seg-model"></div>
    <div class="seg seg-journey"></div>
    <div class="seg seg-scam"></div>
    <div class="seg seg-agent"></div>
  </div>
  <div class="sticky-inner">
    <span class="sticker">biz.saaaai.com</span>
    <span class="sticky-meta">{esc(title_suffix)}</span>
  </div>
</div>
<div class="wrap">"""

def _detail_foot(now_str: str) -> str:
    return f"""</div>
<footer class="footer">
  <div class="f-left">
    <span class="f-sticker">商业灵感</span>
    <span class="f-note">biz.saaaai.com · {now_str}</span>
  </div>
  <div class="f-right">商业灵感 © 2026 · biz.saaaai.com</div>
</footer>
<script>
(function(){{
  var progress=document.getElementById('progress');
  var ticking=false;
  function update(){{ var y=window.scrollY;
    var maxScroll=document.documentElement.scrollHeight - window.innerHeight;
    if(progress) progress.style.width = Math.min(y / maxScroll * 100, 100) + '%';
    ticking=false;
  }}
  window.addEventListener('scroll',function(){{ if(!ticking){{ requestAnimationFrame(update); ticking=true; }} }},{{passive:true}});
  update();
}})();
</script>
</body>
</html>"""

def _detail_hero(m: dict, emoji: str, badge: str, how: str, zoom: bool, diag_h: int = 520) -> str:
    """详情页 hero：贴纸 + 胶带 + h1 + badge + how + 流程图（model 可 zoom）"""
    if zoom:
        diag = f"""<div class="diagram" style="--diag-h:{diag_h}"><iframe src="models/{esc(m['id'])}.html?embed=1" title="模式流程图"></iframe>
<div class="hit"></div></div>
<div class="zview" id="zview"><iframe src="models/{esc(m['id'])}.html?embed=1" title="模式流程图(全屏)"></iframe>
<button class="zclose" aria-label="关闭">✕</button></div>
<script>
const z=document.getElementById('zview');
const dg=document.querySelector('.diagram');
if(dg){{dg.addEventListener('click',()=>z.classList.add('on'));
z.querySelector('.zclose').addEventListener('click',e=>{{e.stopPropagation();z.classList.remove('on');}});
z.addEventListener('click',e=>{{if(e.target===z)z.classList.remove('on');}});
document.addEventListener('keydown',e=>{{if(e.key==='Escape')z.classList.remove('on');}});}}
</script>"""
    else:
        diag = f"""<div class="diagram"><iframe src="models/{esc(m['id'])}.html?embed=1" title="流程时间线"></iframe></div>"""
    return f"""<div class="crumb">
  <a href="index.html">← 贴纸墙</a>
  <span class="here">{esc(badge)} · DETAIL</span>
</div>
<section class="detail-hero">
  <div class="d-hero-emoji" aria-hidden="true">{emoji}</div>
  <div class="d-hero-body">
    <h1>{esc(m['name'])}</h1>
    <p class="how">{esc(how)}</p>
  </div>
  <div class="d-hero-badge">{esc(badge)}</div>
</section>
<section class="field-sec">
  <div class="sec">
    <h2>关键字段</h2>
    <span class="sec-note">FIELD STAMPS</span>
  </div>
  <div class="fields">
    <div class="field"><span class="k">INDUSTRY 行业</span><span class="v"><span class="tag {_ind_cls(m.get('industry','其他'))}{" bright" if m.get('industry') in ("内容/创作者经济","旅游","本地生活","其他") else ""}">{esc(m.get('industry','其他'))}</span></span></div>
    <div class="field"><span class="k">REGION 地区</span><span class="v">{esc(m.get('region',''))}</span></div>
    <div class="field"><span class="k">SCALE 规模</span><span class="v">{esc(m.get('scale',''))}</span></div>
    <div class="field"><span class="k">CHANNEL 渠道</span><span class="v">{esc(m.get('channel',''))}</span></div>
  </div>
</section>
{diag}"""

def _ind_cls(ind: str) -> str:
    return {"金融科技": "ind-fintech", "AI/大模型": "ind-ai", "电商/零售": "ind-ecom",
            "其他": "ind-other", "营销/广告": "ind-mkt", "医疗/养老": "ind-med",
            "内容/创作者经济": "ind-content", "旅游": "ind-travel", "本地生活": "ind-local"}.get(ind, "ind-other")

def _related_html2(related: list[dict] | None) -> str:
    """详情页相关推荐区 HTML（贴纸小卡）"""
    if not related:
        return ""
    cards = []
    for x in related:
        tags = "".join(f'<span class="tag-badge" style="background:var(--{_ind_cls(x.get("industry","其他"))})">{esc(x.get("industry",""))}</span>'
                       for k in ("industry",) if x.get(k))
        cards.append(
            f'<a class="card-link" href="{esc(x["id"])}.html"><article class="card">'
            f'<div class="tag-row">{tags}<span class="tag-text">{esc(x.get("region",""))}</span></div>'
            f'<h3>{esc(x["name"])}</h3>'
            f'</article></a>')
    return (f'<div class="related"><div class="sec"><h2>相关条目</h2>'
            f'<span class="sec-note">同行业 / 同规模推荐</span></div>'
            f'<div class="related-grid">{"".join(cards)}</div></div>')
# <<< G2-TEMPLATE-END >>>

def render_model_page(m: dict, related: list[dict] | None = None) -> None:
    dims = {"industry": m["industry"], "region": m["region"],
            "scale": m["scale"], "channel": m["channel"]}
    # 图高随泳道数变化：viewBox 高=52+L×104+(L−1)×20+124；统一 720 宽 → aspect-ratio 720/高
    n_lanes = len(build_workflow(m)["lanes"])
    diag_h = 52 + n_lanes * 104 + (n_lanes - 1) * 20 + 124
    srcs = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>'
                   for u in m["sources"])
    swot_html = ""
    for key, title, dot in (("s", "优势 Strengths", "green"),
                            ("w", "劣势 Weaknesses", "rose"),
                            ("o", "机会 Opportunities", "cyan"),
                            ("t", "威胁 Threats", "yellow")):
        items = s(m["swot"], key)
        swot_html += f'<div class="swot {dot}"><h3>{title}</h3><ul>{li(items)}</ul></div>'
    page = (
        _detail_head(m, "商业模式")
        + _detail_hero(m, IND_EMOJI_M.get(m.get("industry", ""), "🧩"), "MODEL",
                       str(m.get("revenue", "")).split('；')[0].split('。')[0][:120], True, diag_h)
        + f"""<div class="section"><h2>📌 背景</h2><p>{esc(m['background'])}</p></div>
<div class="section"><h2>👤 目标客户</h2><p>{esc(m['target'])}</p></div>
<div class="section"><h2>💰 盈利点</h2><p>{esc(m['revenue'])}</p></div>
<div class="section"><h2>🧮 成本结构</h2><p>{esc(m['cost'])}</p></div>
<div class="section"><h2>🛡️ 护城河</h2><p>{esc(m['moat'])}</p></div>
<div class="section"><h2>🔑 成功关键</h2><ul>{li(m.get('keys', []))}</ul></div>
<div class="section"><h2 class="alert">⚠️ 风险</h2><ul>{li(m.get('risks', []))}</ul></div>
<div class="section"><h2>🏢 案例</h2><ul>{li(m.get('example', []))}</ul></div>
<div class="section"><h2>📊 SWOT 分析</h2><div class="swot-grid">{swot_html}</div></div>
<div class="src"><strong>来源</strong><ul>{"".join(srcs)}</ul></div>
{_related_html2(related)}
"""
        + _detail_foot(datetime.now().strftime('%Y-%m-%d'))
    )
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


def render_journey_page(m: dict, related: list[dict] | None = None) -> None:
    ir = build_journey_timeline(m)
    _render_arch(ir, m["id"])
    srcs = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>'
                   for u in m["sources"])
    ms_html = "".join(
        f'<div class="mstone {"fail" if x.get("outcome")=="失败" else "turn" if x.get("outcome") in ("拐点","转折") else "ok"}">'
        f'<div class="ms-time">{esc(x.get("time",""))}</div>'
        f'<div class="ms-stage">{esc(x.get("stage",""))} <span class="ms-tag">{esc(x.get("outcome",""))}</span></div>'
        f'<div class="ms-detail">{esc(x.get("detail",""))}</div></div>' for x in m.get("milestones", []))
    metrics_html = "".join(f'<li><strong>{esc(k)}</strong>：{esc(v)}</li>' for k, v in m.get("metrics", {}).items())
    page = (
        _detail_head(m, "发家路径")
        + _detail_hero(m, "🛤", "JOURNEY",
                       "创办：" + str(m.get("founders", "")) + " · " + str(m.get("company", "")), False)
        + f"""<div class="section"><h2>起步缘由</h2><p>{esc(m.get('origin',''))}</p></div>
<div class="section"><h2>发家里程碑</h2>{ms_html}</div>
<div class="section"><h2>转折点</h2><ul>{li(m.get('turning_points',[]))}</ul></div>
<div class="section"><h2>失败与踩坑</h2><ul>{li(m.get('failures',[]))}</ul></div>
<div class="kw"><div class="section"><h2>关键成功要素</h2><ul>{li(m.get('keys',[]))}</ul></div>
<div class="section"><h2>经验教训</h2><ul>{li(m.get('lessons',[]))}</ul></div></div>
<div class="section"><h2>核心数据</h2><ul>{metrics_html}</ul></div>
<div class="section"><h2>竞争对手 / 同行</h2><p>{esc(m.get('competitors',''))}</p></div>
<div class="src"><strong>来源</strong><ul>{"".join(srcs)}</ul></div>
{_related_html2(related)}
"""
        + _detail_foot(datetime.now().strftime('%Y-%m-%d'))
    )
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


def _fmt_arr_item(x) -> str:
    """列表项渲染规整：str 原样返回；dict 按「date agency: alert/message」拼文本。

    2026-08-09 修正（P0-2）：旧数据 official_alerts/real_cases 有 dict 数组变体
    （{date,agency,alert}），此前 esc() 直转 Python repr 渲染到页面
    （<li>{'date': '2026-07-22', ...}</li>）。渲染层统一拼成可读文本，兼容 str 项。"""
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        d, ag = x.get("date"), x.get("agency")
        body = x.get("alert") or x.get("message") or x.get("detail") or x.get("case") or x.get("desc") or ""
        head = ""
        if isinstance(d, str) and d.strip():
            head += d.strip()
        if isinstance(ag, str) and ag.strip():
            head += (f" {ag.strip()}" if head else ag.strip())
        body = str(body).strip()
        if head and body:
            return f"{head}：{body}"
        return body or str(x)
    return str(x)


def render_scam_page(m: dict, related: list[dict] | None = None) -> None:
    ir = build_scam_flow(m)
    _render_arch(ir, m["id"])
    srcs = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>'
                   for u in m["sources"])
    steps_html = "".join(f'<li>{esc(s)}</li>' for s in m.get("how_it_works", []))
    flags_html = "".join(f'<li>🚩 {esc(x)}</li>' for x in m.get("red_flags", []))
    cases_html = "".join(f'<li>{esc(_fmt_arr_item(c))}</li>' for c in m.get("real_cases", []))
    alerts_html = "".join(f'<li>{esc(_fmt_arr_item(a))}</li>' for a in m.get("official_alerts", []))
    prot_html = "".join(f'<li>✅ {esc(p)}</li>' for p in m.get("protection", []))
    page = (
        _detail_head(m, "避坑指南")
        + _detail_hero(m, "⚠️", "SCAM",
                       str(m.get("victims", "")), False)
        + f"""<div class="warn">⚠️ 本条目汇总骗局手法与官方警示，不构成投资或法律建议；如遇受害请立即报警（12339）。</div>
<div class="section"><h2>骗谁</h2><p>{esc(m.get('victims',''))}</p></div>
<div class="section"><h2 class="alert">骗局怎么运作</h2><ul>{steps_html}</ul></div>
<div class="section"><h2 class="alert">红旗信号（看到这些快跑）</h2><ul>{flags_html}</ul></div>
<div class="section"><h2>真实案例</h2><ul>{cases_html}</ul></div>
<div class="section"><h2>官方态度</h2><ul>{alerts_html}</ul></div>
<div class="section"><h2>怎么防护</h2><ul>{prot_html}</ul></div>
<div class="legal">⚖️ {esc(m.get('legal_note',''))}</div>
<div class="src"><strong>来源</strong><ul>{"".join(srcs)}</ul></div>
{_related_html2(related)}
"""
        + _detail_foot(datetime.now().strftime('%Y-%m-%d'))
    )
    (SITE / f"{m['id']}.html").write_text(page, encoding="utf-8")



# ---------------------------------------------------------------------------
# 板块四 agent：AI实干家 workflow 骨架 + 详情页
# ---------------------------------------------------------------------------
def build_agent_workflow(m: dict) -> dict:
    """AI实干家 3 泳道 workflow 骨架：输入→AI处理→输出变现"""
    rid = re.sub(r"[^a-zA-Z0-9_-]", "-", m["id"]).strip("-") or "agent"
    lanes = [
        {"id": "input", "label": "输入 - 数据来源"},
        {"id": "ai", "label": "AI 处理 - 核心工作流"},
        {"id": "output", "label": "输出 - 变现交付"},
    ]
    nodes = []
    edges = []
    main_path = []
    # 三阶段：col 0(搭建) / 2(运行) / 4(变现)
    # 输入节点
    in_id = f"{rid}-in-0"
    nodes.append({"id": in_id, "lane": "input", "col": 0, "type": "cloud",
                  "label": "数据/信号", "sublabel": sub(m.get("workflow", "输入"), 8)})
    main_path.append(in_id)
    # AI处理节点
    ai_id = f"{rid}-ai-2"
    tools = m.get("tools", [])
    ai_label = tools[0] if tools else "AI Agent"
    nodes.append({"id": ai_id, "lane": "ai", "col": 2, "type": "messagebus",
                  "label": "AI 处理", "sublabel": sub(ai_label, 8)})
    edges.append({"id": f"{rid}-e1", "from": in_id, "to": ai_id, "variant": "default"})
    main_path.append(ai_id)
    # 输出节点
    out_id = f"{rid}-out-4"
    rev = m.get("revenue", "变现")
    nodes.append({"id": out_id, "lane": "output", "col": 4, "type": "database",
                  "label": "交付变现", "sublabel": sub(rev, 8)})
    edges.append({"id": f"{rid}-e2", "from": ai_id, "to": out_id, "variant": "default"})
    main_path.append(out_id)
    # 人工审核信息已包含在详情页，不设独立节点（避免 archify 孤立节点验证失败）
    cards = [
        {"dot": "amber", "title": "成功关键",
         "items": [sub(x, 40) for x in m.get("keys", [])] or ["（待补）"]},
        {"dot": "rose", "title": "风险",
         "items": [sub(x, 40) for x in m.get("risks", [])] or ["（待补）"]},
        {"dot": "emerald", "title": "真实案例",
         "items": [sub(x, 40) for x in m.get("example", [])] or ["（待补）"]},
    ]
    phases = [
        {"id": "setup", "label": "搭建", "fromCol": 0, "toCol": 1, "variant": "emphasis"},
        {"id": "run", "label": "运行", "fromCol": 2, "toCol": 3},
        {"id": "cash", "label": "变现", "fromCol": 4, "toCol": 5},
    ]
    return {
        "schema_version": 1, "diagram_type": "workflow",
        "meta": {"title": m["name"][:40],
                 "subtitle": f"{m.get('region','')} · {m.get('industry','')} · AI实干家",
                 "quality_profile": "standard", "output": f"{m['id']}.html"},
        "lanes": lanes, "phases": phases, "mainPath": main_path,
        "nodes": nodes, "edges": edges, "cards": cards,
    }


def render_agent_page(m: dict, related: list[dict] | None = None) -> None:
    """AI实干家详情页"""
    ir = build_agent_workflow(m)
    _render_arch(ir, m["id"])
    srcs = "".join(f'<li><a href="{esc(u)}" target="_blank" rel="noopener">{esc(u)}</a></li>'
                   for u in m["sources"])
    tools_html = "".join(f'<li>🔧 {esc(t)}</li>' for t in m.get("tools", []))
    example_html = "".join(f'<li>📌 {esc(e)}</li>' for e in m.get("example", []))
    keys_html = "".join(f'<li>✅ {esc(k)}</li>' for k in m.get("keys", []))
    risks_html = "".join(f'<li>⚠️ {esc(r)}</li>' for r in m.get("risks", []))
    page = (
        _detail_head(m, "AI实干家")
        + _detail_hero(m, "🤖", "AGENT",
                       f"工作流：{esc(m.get('workflow',''))[:120]}", False)
        + f"""<div class="section"><h2>🔧 工作流</h2><p>{esc(m.get('workflow',''))}</p></div>
<div class="section"><h2>🛠 搭建门槛</h2><p>{esc(m.get('setup',''))}</p></div>
<div class="section"><h2>🧰 工具链</h2><ul>{tools_html}</ul></div>
<div class="kw"><div class="section"><h2>💰 收入</h2><p>{esc(m.get('revenue',''))}</p></div>
<div class="section"><h2>💸 成本</h2><p>{esc(m.get('cost',''))}</p></div>
<div class="section"><h2>⏱ 时间投入</h2><p>{esc(m.get('time',''))}</p></div></div>
<div class="section"><h2>🚀 新手入行指南</h2><p>{esc(m.get('entry',''))}</p></div>
<div class="kw"><div class="section"><h2>🔑 成功关键</h2><ul>{keys_html}</ul></div>
<div class="section"><h2>⚠️ 风险</h2><ul>{risks_html}</ul></div></div>
<div class="section"><h2>📌 真实案例</h2><ul>{example_html}</ul></div>
<div class="src"><strong>来源</strong><ul>{"".join(srcs)}</ul></div>
{_related_html2(related)}
"""
        + _detail_foot(datetime.now().strftime('%Y-%m-%d'))
    )
    (SITE / f"{m['id']}.html").write_text(page, encoding="utf-8")

def _region_group(v: str) -> str:
    """region 31 个离散值折叠为 6 组（chips 用；卡片仍显示原值）。"""
    v = str(v)
    if not v:
        return "其他"
    if "全球" in v:
        return "全球"
    if "中" in v or "全国" in v or "内地" in v:
        return "中国"
    if "美" in v or "USA" in v or "United" in v:
        return "美国"
    if "日" in v:
        return "日本"
    if "跨" in v or "跨境" in v:
        return "跨地区"
    return "其他"


def _scale_group(v: str) -> str:
    """scale 15 个离散值折叠为 4 组（chips 用）。"""
    v = str(v)
    if not v:
        return "其他"
    if "灰产" in v:
        return "灰产"
    if any(x in v for x in ("巨头", "巨頭", "上市", "独角兽", "IPO")):
        return "巨头"
    if any(x in v for x in ("中型", "成长", "Million")):
        return "中型"
    if any(x in v for x in ("小企", "个人", "私有")):
        return "小企"
    return "其他"


def _hot_score(m: dict) -> int:
    """热度启发式：y2026_hot 文本中趋势词加权 + 大数字出现次数，clamp 0-100。"""
    t = str(m.get("y2026_hot", ""))
    s = 0
    for kw in ("热潮", "爆发", "风口", "爆火", "火热", "疯狂", "抢", "井喷", "元年"):
        s += t.count(kw) * 3
    for kw in ("增长", "破", "突破", "亿", "万亿", "千万", "月活", "用户"):
        s += t.count(kw)
    return min(100, s)


def _rev_label(m: dict) -> str:
    """变现标签：从 revenue 文本关键词归出一句话标签（model 卡提权用）。"""
    r = str(m.get("revenue", ""))
    rules = (
        ("抽佣/撮合", "抽佣|佣金|抽成|撮合|交易手续费|按成交|分润"),
        ("订阅/会员", "订阅|会员|月费|年费|经常性|ARR|席位|SaaS"),
        ("广告/流量", "广告|流量变现|CPM|竞价|信息流"),
        ("卖货/零售", "卖货|销售|批发|供货|零售|加盟|门店|连锁"),
        ("服务/项目费", "服务费|项目费|按单|外包|咨询|顾问|代运营"),
        ("硬件/设备", "硬件|设备|GPU|机器|仪器"),
        ("授权/许可", "授权|许可|牌照|加盟费"),
    )
    for label, pat in rules:
        if re.search(pat, r):
            return label
    return "变现"


def _agent_rev_label(m: dict) -> str:
    """agent 收入标签"""
    r = str(m.get("revenue", "")).lower()
    if "万" in r or "k" in r:
        return "月入万+"
    if "千" in r:
        return "月入千级"
    return "AI实干家"


def _related(m: dict, pool: list[dict], k: int = 4) -> list[dict]:
    """详情页相关推荐：同行业 → 同规模 → 同地区，去重取前 k，排除自身。"""
    out = []
    for key in ("industry", "scale", "region"):
        for x in pool:
            if x["id"] == m["id"] or x in out:
                continue
            if x.get(key) and x.get(key) == m.get(key):
                out.append(x)
                if len(out) >= k:
                    return out
    return out


def _related_html(related: list[dict] | None) -> str:
    """详情页相关推荐区 HTML（同族 4 条小卡）。"""
    if not related:
        return ""
    cards = []
    for x in related:
        tags = "".join(
            f'<span class="t">{esc(x.get(k, ""))}</span>'
            for k in ("industry", "region") if x.get(k))
        cards.append(
            f'<a class="rcard" href="{esc(x["id"])}.html"><span class="rname">{esc(x["name"])}</span>'
            f'<span class="rtags">{tags}</span></a>')
    return (f'<div class="related"><h2>📎 相关条目</h2><div class="rgrid">{"".join(cards)}</div></div>')


def build_index(models: list[dict]) -> None:
    by_type = {'model': [], 'journey': [], 'scam': [], 'agent': []}
    for m in models:
        by_type.setdefault(m.get('type', 'model'), []).append(m)
    # 三组多选 chips：industry 原值、region/scale 折叠组；channel 值太脏不进 chips 只进搜索文本
    ind_opts = sorted({mm.get("industry", "") for mm in by_type["model"] if mm.get("industry")})
    reg_opts = ["中国", "美国", "日本", "全球", "跨地区", "其他"]
    sca_opts = ["巨头", "中型", "小企", "灰产"]
    chip_html = ""
    for dim, label, opts in (("industry", "行业", ind_opts),
                             ("gregion", "地区", reg_opts),
                             ("gscale", "规模", sca_opts)):
        chips = "".join(
            f'<button class="chip" data-dim="{dim}" data-val="{esc(o)}">{esc(o)}</button>' for o in opts)
        chip_html += f'<div class="fgroup" data-dim="{dim}"><span class="flabel">{label}</span><div class="fchips">{chips}</div></div>'

    IND_EMOJI = {
        "AI/大模型": "🤖", "SaaS/企业软件": "💻", "云计算": "☁️", "其他": "🧩",
        "内容/创作者经济": "🎬", "医疗/养老": "🩺", "宠物": "🐾", "教育/知识付费": "📚",
        "旅游": "✈️", "本地生活": "🏪", "电商/零售": "🛒", "营销/广告": "📣",
        "金融科技": "💳", "餐饮/茶饮": "🍜",
    }
    IND_CLS = {
        "金融科技": "ind-fintech", "AI/大模型": "ind-ai", "电商/零售": "ind-ecom",
        "其他": "ind-other", "营销/广告": "ind-mkt", "医疗/养老": "ind-med",
        "内容/创作者经济": "ind-content", "旅游": "ind-travel", "本地生活": "ind-local",
    }
    IND_BRIGHT = ["内容/创作者经济", "旅游", "本地生活", "其他"]
    SCALE_CLS = {"巨头": "g-x", "中型": "g-m", "小企": "g-s", "灰产": "g-b"}
    SCALE_DOTS = {"巨头": 5, "中型": 3, "小企": 1, "灰产": 4, "": 0, "其他": 0}

    def tag_ind(ind: str) -> str:
        cls = IND_CLS.get(ind, "ind-other")
        return f'<span class="tag ind {cls}{" bright" if ind in IND_BRIGHT else ""}">{esc(ind)}</span>'

    def scale_dots(scl: str) -> str:
        n = SCALE_DOTS.get(scl, 0)
        return ('<span class="scale" title="规模 ' + esc(scl) + '">' +
                "".join(f'<i class="{"on" if i < n else ""}"></i>' for i in range(5)) + "</span>")

    def card_meta(m: dict, dims: dict) -> str:
        """卡片顶行：行业色标签 + 地区 + 规模"""
        ind_cls = IND_CLS.get(dims.get("industry", "其他"), "ind-other")
        bright = " bright" if dims.get("industry", "") in IND_BRIGHT else ""
        ind = f'<span class="tag-badge{bright}" style="background:var(--{ind_cls})">{esc(dims.get("industry",""))}</span>'
        region = f'<span class="tag-text">{esc(dims.get("region",""))}</span>'
        scale = f'<span class="tag-text">{esc(dims.get("scale",""))}</span>'
        return f'<div class="tag-row">{ind}{region}{scale}</div>'

    def stamp_txt(m: dict) -> str:
        """圆章两字一行：model 用变现标签；journey 用核心数据首 key；scam 用红旗信号首 4 字"""
        t = m.get("type", "model")
        if t == "journey":
            met = m.get("metrics", {}) or {}
            k = next((k for k in ("估值", "ARR", "年营收", "市值", "月活用户", "DAU") if k in met), None)
            v = (k or "核心")[:2]
            return f"{v}<br>{'数据' if len(k or '') > 2 else ''}" if False else (k[:2] + "<br>" + (k[2:4] or "数据")) if k and len(k) > 2 else (k or "核心") + "<br>数据"
        if t == "agent":
            rev = str(m.get("revenue", ""))[:4]
            return (rev[:2] + "<br>" + rev[2:4]) if len(rev) >= 4 else (rev + "<br>收入") if len(rev) == 2 else "AI实干"
        if t == "scam":
            fl = m.get("red_flags") or []
            s0 = str(fl[0])[:4] if fl else "防坑揭露"
            return (s0[:2] + "<br>" + s0[2:4]) if len(s0) >= 4 else (s0 + "警惕") if len(s0) == 2 else (s0 + "<br>警惕") if len(s0) == 1 else "防坑<br>揭露"
        rev = _rev_label(m)
        parts = rev.split("/") if "/" in rev else [rev[:2], rev[2:4] or "模式"]
        return "<br>".join(p for p in parts[:2] if p) or "模式<br>要点"

    model_cards = []
    for m in by_type['model']:
        dims = {"industry": m.get('industry', ''), "region": m.get('region', ''),
                "scale": m.get('scale', ''), "channel": m.get('channel', '')}
        data_attr = " ".join(f'data-{k}="{esc(v)}"' for k, v in dims.items())
        data_attr += f' data-gregion="{esc(_region_group(m.get("region","")))}" data-gscale="{esc(_scale_group(m.get("scale","")))}"'
        search_txt = " ".join([m.get('name', ''), m.get('industry', ''), m.get('region', ''),
                               m.get('scale', ''), str(m.get('channel', ''))])
        rev = str(m.get('revenue', ''))
        first_sentence = rev.split('；')[0].split('。')[0]
        if len(first_sentence) > 90:
            first_sentence = first_sentence[:90] + "…"
        summary = first_sentence or "（模式要点见详情）"
        meta = card_meta(m, dims)
        model_cards.append(f"""<article class="card" {data_attr}
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" data-type="model">
  <a class="card-link" href="{esc(m['id'])}.html">
    {meta}
    <h3>{esc(m['name'])}</h3>
    <p>{esc(summary)}</p>
  </a>
</article>""")

    journey_cards = []
    for m in by_type['journey']:
        ms = m.get('milestones', [])
        n_fail = sum(1 for x in ms if x.get('outcome') == '失败')
        dims = {"industry": m.get('industry', ''), "region": m.get('region', ''),
                "scale": m.get('scale', ''), "channel": m.get('channel', '')}
        jdata = " ".join(f'data-{k}="{esc(v)}"' for k, v in dims.items())
        jdata += f' data-gregion="{esc(_region_group(m.get("region","")))}" data-gscale="{esc(_scale_group(m.get("scale","")))}"'
        met = m.get('metrics', {}) or {}
        met_str = ""
        for k in ('最新估值', '估值', 'ARR', '年营收', '市值', '年收入', '月活用户', 'DAU'):
            if k in met and met[k]:
                met_str = f" · {esc(k)}：{esc(str(met[k]))[:40]}"
                break
        search_txt = " ".join([m.get('name', ''), m.get('company', ''), m.get('industry', ''),
                               m.get('region', ''), str(m.get('origin', '')),
                               str(m.get('lessons', ''))])
        meta = card_meta(m, dims)
        journey_cards.append(f"""<article class="card" data-type="journey"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {jdata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    {meta}
    <h3>{esc(m['name'])}</h3>
    <p>创办：{esc(m.get('founders', ''))} · {len(ms)} 阶段 · {n_fail} 次失败踩坑{met_str}</p>
  </a>
</article>""")

    scam_cards = []
    for m in by_type['scam']:
        dims = {"industry": m.get('industry', ''), "region": m.get('region', ''),
                "scale": m.get('scale', ''), "channel": m.get('channel', '')}
        sdata = " ".join(f'data-{k}="{esc(v)}"' for k, v in dims.items())
        sdata += f' data-gregion="{esc(_region_group(m.get("region","")))}" data-gscale="{esc(_scale_group(m.get("scale","")))}"'
        how = m.get('how_it_works', [])
        how_first = how[0] if how else str(m.get('victims', ''))
        if len(how_first) > 90:
            how_first = how_first[:90] + "…"
        search_txt = " ".join([m.get('name', ''), m.get('industry', ''), m.get('region', ''),
                               str(m.get('victims', '')), str(m.get('how_it_works', '')),
                               str(m.get('red_flags', ''))])
        meta = card_meta(m, dims)
        scam_cards.append(f"""<article class="card" data-type="scam"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {sdata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    {meta}
    <h3>{esc(m['name'])}</h3>
    <p>手法：{esc(how_first)}</p>
  </a>
</article>""")

        agent_cards = []
    for m in by_type.get('agent', []):
        dims = {'industry': m.get('industry', ''), 'region': m.get('region', ''),
                'scale': m.get('scale', ''), 'channel': m.get('channel', '')}
        adata = ' '.join(f'data-{k}="{esc(v)}"' for k, v in dims.items())
        adata += f' data-gregion="{esc(_region_group(m.get("region","")))}" data-gscale="{esc(_scale_group(m.get("scale","")))}"'
        rev = str(m.get('revenue', ''))
        rev_first = rev.split('；')[0].split('。')[0][:90]
        search_txt = ' '.join([m.get('name', ''), str(m.get('workflow', '')), str(m.get('setup', '')),
                               m.get('industry', ''), m.get('region', ''), str(m.get('tools', ''))])
        meta = card_meta(m, dims)
        agent_cards.append(f'''<article class="card" data-type="agent"
  data-search="{esc(search_txt)}" data-hot="{_hot_score(m)}" {adata}>
  <a class="card-link" href="{esc(m['id'])}.html">
    {meta}
    <h3>{esc(m['name'])}</h3>
    <p>工作流：{esc(rev_first)}</p>
  </a>
</article>''')

    n_model, n_journey, n_scam, n_agent = len(by_type['model']), len(by_type['journey']), len(by_type['scam']), len(by_type.get('agent', []))
    n_total = n_model + n_journey + n_scam + n_agent

    # tab 内部 key → 中文显示名（view-btn 大字、stamp、cta、wall-title 全用这个，禁再出现英文 MODEL/JOURNEY/SCAM）
    TAB_LABEL = {'model': '商业模式', 'journey': '发家历程', 'scam': '骗局揭秘', 'agent': 'AI实干家'}
    # 编辑精选：三板块入口引导卡（三种方案对比展示，点击切对应 tab 并滚到卡片墙）
    def _pick_card_b(tab: str, label: str, blurb: str, n: int) -> str:
        """方案B：信息卡 — 标签 + 计数 + 按钮"""
        return f"""<button class="pick pick-b v-{tab}" data-tab="{tab}" type="button">
  <div class="pick-b-head">
    <span class="pick-b-count"><b>{n}</b> 条</span>
  </div>
  <div class="pick-b-body">
    <div class="pick-b-name">{esc(label)}</div>
    <div class="pick-b-sub">{esc(blurb)}</div>
  </div>
  <span class="pick-b-btn">浏览全部 →</span>
</button>"""

    picks_html = ""
    # 引导卡：三板块入口（方案B 定稿，直接渲染，无调参面板）
    picks_html += '<div class="picks-grid">'
    picks_html += _pick_card_b('model', TAB_LABEL['model'], "订阅/分润/代运营·340 种赚钱路数全收录", n_model)
    picks_html += _pick_card_b('journey', TAB_LABEL['journey'], "起家·融资·上市/翻车各阶段真实时间线", n_journey)
    picks_html += _pick_card_b('scam', TAB_LABEL['scam'], "手法·话术·跑路路径全揭露（6 步拆解）", n_scam)
    picks_html += _pick_card_b('agent', TAB_LABEL['agent'], "个人AI变现系统·代写/获客/内容/选品/线索", n_agent)
    picks_html += '</div>'

    now_str = datetime.now().strftime('%Y·%m·%d')
    index = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>商业灵感 · biz.saaaai.com — 商业模式情报站</title>
<meta name="description" content="biz.saaaai.com AI驱动的商业模式情报站：每日更新的赚钱模式拆解、企业发家历程、骗局识别、AI工具实践，数据由AI持续自动采集">
<link rel="canonical" href="https://biz.saaaai.com/">
<meta property="og:type" content="website">
<meta property="og:site_name" content="商业灵感 biz.saaaai.com">
<meta property="og:title" content="商业灵感 · biz.saaaai.com — 商业模式情报站">
<meta property="og:description" content="biz.saaaai.com AI驱动的商业模式情报站：每日更新的赚钱模式拆解、企业发家历程、骗局识别、AI工具实践，数据由AI持续自动采集">
<meta property="og:url" content="https://biz.saaaai.com/">
<meta property="og:locale" content="zh_CN">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="商业灵感 · biz.saaaai.com — 商业模式情报站">
<meta name="twitter:description" content="biz.saaaai.com AI驱动的商业模式情报站：每日更新的赚钱模式拆解、企业发家历程、骗局识别、AI工具实践，数据由AI持续自动采集">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebSite",
  "name": "商业灵感 · biz.saaaai.com — 商业模式情报站",
  "url": "https://biz.saaaai.com/",
  "description": "biz.saaaai.com AI驱动的商业模式情报站：每日更新的赚钱模式拆解、企业发家历程、骗局识别、AI工具实践，数据由AI持续自动采集",
  "inLanguage": "zh-CN"
}}
</script>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<style>
.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
:root {{
  --bg:#282828; --card:#3c3836; --stroke:#1d2021; --fg:#ebdbb2; --dim:#a89984;
  --acc:#fabd2f; --blue:#83a598; --orange:#fe8019; --purple:#d3869b;
  --shadow-c:#1d2021; --tape:rgba(250,189,47,.20); --footer-fg:#ebdbb2;
  --ind-fintech:#b8bb26; --ind-ai:#83a598; --ind-ecom:#fe8019; --ind-other:#928374;
  --ind-mkt:#fb4934; --ind-med:#d3869b; --ind-content:#fabd2f; --ind-travel:#8ec07c; --ind-local:#a89984;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
html{{scrollbar-color:color-mix(in srgb,var(--fg) 25%,transparent) transparent}}
body{{background:var(--bg);color:var(--fg);font-family:"Noto Sans SC","Noto Sans CJK SC","Source Han Sans SC","Microsoft YaHei",sans-serif;font-weight:500;-webkit-font-smoothing:antialiased}}
::-webkit-scrollbar{{width:14px}}
::-webkit-scrollbar-track{{background:transparent}}
::-webkit-scrollbar-thumb{{background:color-mix(in srgb,var(--fg) 25%,transparent);border:4px solid var(--bg)}}

.wrap{{max-width:1344px;margin:0 auto;padding:0 48px}}

/* sticky-bar：顶部全吸顶条（首页 + 详情页通用）*/
.sticky-bar{{background:var(--bg);border-bottom:3px solid var(--stroke);transition:box-shadow .2s,transform .3s}}
.sticky-inner{{max-width:1344px;margin:0 auto;padding:0 48px;display:flex;align-items:center;justify-content:space-between;height:48px}}
.sticky-meta{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:13px;font-weight:700;color:var(--dim)}}
/* header progress + color-ribbon + sticker（2026-08-16） */
.progress-wrap{{height:3px;background:var(--card);overflow:hidden}}
.progress-bar{{height:100%;width:0%;background:linear-gradient(90deg,var(--blue),var(--orange),var(--purple),var(--green));transition:width .1s linear}}
.color-ribbon{{display:flex;height:6px;border-bottom:3px solid var(--stroke)}}
.color-ribbon .seg{{height:100%;position:relative;overflow:hidden;width:auto}}
.color-ribbon .seg-model{{width:45%;background:var(--blue)}}
.color-ribbon .seg-journey{{width:30%;background:var(--orange)}}
.color-ribbon .seg-scam{{width:25%;background:var(--purple)}}
.color-ribbon .seg-agent{{width:15%;background:var(--ind-fintech)}}
.color-ribbon .seg::after{{content:'';position:absolute;inset:0;background:linear-gradient(90deg,transparent,transparent 30%,rgba(255,255,255,.35) 50%,transparent 70%,transparent);background-size:300% 100%;animation:shimmer 3s ease-in-out infinite}}
.sticker{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:16px;font-weight:800;background:var(--acc);color:#111;padding:5px 12px;border:2px solid var(--stroke);box-shadow:4px 4px 0 var(--shadow-c);display:inline-block;line-height:1.3;white-space:nowrap}}


@keyframes shimmer{{0%{{background-position:0% 0}}100%{{background-position:300% 0}}}}
@media(max-width:720px){{
  .sticky-inner{{height:40px;padding:0 16px}}
  .sticker{{font-size:13px;padding:3px 8px;box-shadow:2px 2px 0 var(--shadow-c)}}
}}

/* masthead（首屏内容条：左搜索框 / 右日期+计数，一行两栏） */
.masthead{{padding:14px 0 10px;border-bottom:3px solid var(--stroke)}}

.mast-title{{margin-bottom:12px}}
.site-title{{font-size:22px;font-weight:900;color:var(--fg);line-height:1.2;margin:0}}
.site-desc{{font-size:14px;color:var(--dim);margin-top:4px;line-height:1.4}}
.mast-row{{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}}
.mast-meta{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:14px;font-weight:700;text-align:right}}
.mast-meta .bar{{display:inline-block;width:26px;height:8px;background:var(--blue);border:2px solid var(--stroke);margin-right:6px;vertical-align:1px}}

/* search-bar：masthead 左栏 */
.search-bar{{display:flex;align-items:center;gap:10px;flex-wrap:wrap}}
.search-bar input{{font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;font-size:14px;font-weight:700;padding:9px 14px;border:2px solid var(--stroke);background:var(--card);color:var(--fg);box-shadow:3px 3px 0 var(--shadow-c);width:300px;transition:border-color .2s ease,box-shadow .2s ease}}
.search-bar input::placeholder{{color:var(--dim);opacity:.7}}
.search-bar input:focus{{outline:none;border-color:var(--acc);box-shadow:var(--acc) 3px 3px 0}}
.search-btn{{display:none;align-items:center;justify-content:center;width:42px;height:42px;border:4px solid var(--stroke);background:var(--acc);color:#111;font-size:18px;box-shadow:var(--shadow-c) 4px 4px 0;cursor:pointer;flex-shrink:0;padding:0;line-height:1;transition:transform .15s,box-shadow .15s}}
.search-btn:hover{{transform:translate(-2px,-2px);box-shadow:var(--shadow-c) 6px 6px 0}}
.search-bar .hint{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:12px;color:var(--dim);letter-spacing:.5px}}

/* view buttons + sort */
.views{{display:flex;gap:14px;margin-bottom:16px;flex-wrap:wrap;align-items:center}}
.view-btn{{font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;font-size:19px;font-weight:900;letter-spacing:1.5px;padding:13px 26px;border:4px solid var(--stroke);cursor:pointer;line-height:1;background:var(--card);color:var(--dim);transition:transform .3s cubic-bezier(.15,.75,.3,1),box-shadow .3s ease,background-color .3s ease,color .3s ease,border-color .3s ease}}
.view-btn .num{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:12px;font-weight:800;margin-left:10px;vertical-align:2px;opacity:.9;transition:opacity .2s ease}}
.view-btn.on.view-model{{background:var(--blue);color:#111}}
.view-btn.on.view-journey{{background:var(--orange);color:#111}}
.view-btn.on.view-scam{{background:var(--purple);color:#111}}
.view-btn.on.view-agent{{background:var(--ind-fintech);color:#111}}
.view-btn.on{{transform:translate(2px,2px);box-shadow:var(--shadow-c) 6px 6px 0}}
.view-btn:not(.on):hover{{transform:translateY(-3px) scale(1.02);box-shadow:var(--shadow-c) 10px 10px 0;filter:brightness(1.08)}}
.view-btn.on:hover{{transform:translateY(-2px) scale(1.02);box-shadow:var(--shadow-c) 8px 8px 0;filter:brightness(1.06)}}
.view-btn:not(.on):active{{transform:translate(1px,1px);box-shadow:var(--shadow-c) 5px 5px 0}}
.view-btn.on:active{{transform:translate(3px,3px) scale(1);box-shadow:var(--shadow-c) 4px 4px 0;filter:none}}
.sort-g{{margin-left:auto;display:flex;gap:8px;align-items:center}}
.sort{{font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;font-size:14px;font-weight:700;padding:7px 10px;border:2px solid var(--stroke);border-radius:0;background:var(--card);color:var(--fg);box-shadow:3px 3px 0 var(--shadow-c);cursor:pointer;transition:transform .25s cubic-bezier(.15,.75,.3,1),box-shadow .25s ease,border-color .25s ease}}
.sort:hover{{transform:translateY(-4px) scale(1.06);box-shadow:var(--shadow-c) 8px 8px 0;border-color:var(--acc)}}
.sort:active{{transform:translate(1px,1px) scale(1);box-shadow:2px 2px 0 var(--shadow-c)}}
.chip-acc{{font-size:14px;font-weight:700;padding:7px 13px;background:var(--acc);color:#111;border:2px solid var(--stroke);box-shadow:3px 3px 0 var(--shadow-c);cursor:pointer;white-space:nowrap;transition:transform .25s cubic-bezier(.15,.75,.3,1),box-shadow .25s ease,background-color .25s ease}}
.chip-acc:hover{{transform:translateY(-2px);box-shadow:var(--shadow-c) 5px 5px 0}}
.chip-acc:active{{transform:translate(1px,1px) scale(1);box-shadow:2px 2px 0 var(--shadow-c)}}

/* filters：三组垂直独立行（label 单独一列、chips 一列）；点击筛选按钮平滑展开/收起 */
.filters{{display:flex;flex-direction:column;gap:14px;padding:0;border-top:0 solid var(--stroke);border-bottom:0 solid var(--stroke);margin-bottom:0;max-height:0;overflow:hidden;opacity:0;transition:max-height .45s cubic-bezier(.2,.8,.2,1),opacity .35s ease,padding .35s ease,border-top-width .35s ease,border-bottom-width .35s ease,margin-bottom .35s ease}}
.filters.open{{padding:18px 0;border-top-width:3px;border-bottom-width:3px;margin-bottom:44px;max-height:700px;opacity:1}}
.fgroup{{display:grid;grid-template-columns:120px 1fr;align-items:start;gap:16px}}
.flabel{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:13px;font-weight:800;color:var(--dim);letter-spacing:1px;padding-top:6px}}
.fchips{{display:flex;flex-wrap:wrap;gap:8px}}
.chip{{font-size:14px;font-weight:700;padding:6px 13px;background:var(--card);border:2px solid var(--stroke);box-shadow:3px 3px 0 var(--shadow-c);cursor:pointer;white-space:nowrap;color:var(--fg);transition:transform .25s cubic-bezier(.15,.75,.3,1),box-shadow .25s ease,background-color .25s ease,color .25s ease}}
.chip:hover{{transform:translateY(-3px) scale(1.05);box-shadow:var(--shadow-c) 7px 7px 0}}
.chip:active{{transform:translate(1px,1px) scale(1);box-shadow:2px 2px 0 var(--shadow-c)}}
.chip.on{{background:var(--fg);color:var(--bg)}}

/* section heads */
.sec-note{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:12px;font-weight:700;color:var(--dim);letter-spacing:.5px}}

/* editor picks */
.picks-sec{{margin-top:40px;margin-bottom:56px}}
.pick{{background:var(--card);border:4px solid var(--stroke);box-shadow:var(--shadow-c) 8px 8px 0;padding:26px 22px 18px;position:relative;display:flex;flex-direction:column;gap:12px;height:268px;min-height:268px;max-height:268px;cursor:pointer;text-align:left;font-family:inherit;color:inherit;transition:transform .3s cubic-bezier(.15,.75,.3,1),box-shadow .3s ease}}
.pick.rot-l{{transform:rotate(-2deg)}}
.pick-tape{{position:absolute;top:-15px;left:50%;transform:translateX(-50%) rotate(-4deg);width:150px;height:27px;background:var(--tape);z-index:2}}
.pick-tape::after{{content:"";position:absolute;left:8px;right:8px;bottom:2px;height:1px;background:rgba(17,17,17,.18)}}
.pick-badge{{position:absolute;top:-16px;right:-12px;background:var(--acc);color:#111;border:3px solid var(--stroke);font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:14px;font-weight:900;letter-spacing:1px;padding:6px 12px;transform:rotate(4deg);z-index:3}}
.pick-cta{{margin-top:auto;font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:14px;font-weight:800;letter-spacing:1px;color:var(--acc);text-align:right}}
.pick:hover{{transform:translateY(-4px) rotate(-1deg) scale(1.01);box-shadow:var(--shadow-c) 10px 10px 0}}
.pick:active{{transform:translateY(-2px) rotate(-2deg) scale(1);box-shadow:var(--shadow-c) 8px 8px 0}}
.pick-top{{display:flex;align-items:flex-start;gap:12px}}
.pick h3{{font-size:21px;font-weight:900;line-height:1.3;letter-spacing:-.3px}}
.pick-blurb{{font-size:14px;color:var(--dim);line-height:1.6;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}

/* ==== 引导卡（方案B 定稿）==== */
.picks-grid{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:28px}}

/* 方案B：信息卡 — 标签 + 计数 + 按钮 */
.pick-b{{display:flex;flex-direction:column;gap:0;padding:34px;min-height:160px;height:auto;max-height:none;position:relative}}
.pick-b-head{{flex:1;align-self:stretch;display:flex;align-items:flex-start}}
.pick-b-count{{display:flex;align-items:baseline;gap:8px;font-family:"Noto Sans SC","Microsoft YaHei",sans-serif;font-size:13px;font-weight:700;color:var(--dim)}}
.pick-b-count b{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:46px;font-weight:900;line-height:1;letter-spacing:1px}}
.pick-b.v-model .pick-b-count b{{color:var(--blue)}}
.pick-b.v-journey .pick-b-count b{{color:var(--orange)}}
.pick-b.v-scam .pick-b-count b{{color:var(--purple)}}
.pick-b.v-agent .pick-b-count b{{color:var(--ind-fintech)}}
.pick-b-body{{flex:2;display:flex;flex-direction:column;justify-content:center;align-items:flex-start;min-height:0}} .pick-b-name{{margin-top:0;font-size:28px;font-weight:900;letter-spacing:1px;text-align:left}}
.pick-b-sub{{max-width:280px;font-size:14px;color:var(--fg);line-height:1.55;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;text-align:left}}
.pick-b-btn{{flex:none;align-self:flex-end;margin-top:0;padding:6px 18px;border:3px solid var(--stroke);box-shadow:4px 4px 0 var(--shadow-c);font-family:Noto Sans SC,Microsoft YaHei,sans-serif;font-size:15px;font-weight:800;text-align:center}}
.pick-b.v-model .pick-b-btn{{background:var(--blue);color:#111}}
.pick-b.v-journey .pick-b-btn{{background:var(--orange);color:#111}}
.pick-b.v-scam .pick-b-btn{{background:var(--purple);color:#111}}
.pick-b.v-agent .pick-b-btn{{background:var(--ind-fintech);color:#111}}

/* sticker wall */
.wall-sec{{padding-bottom:8px}}
.wall-head{{display:flex;justify-content:space-between;align-items:center;gap:24px;flex-wrap:wrap;padding-bottom:14px;border-bottom:3px solid var(--stroke);margin-bottom:14px}}
.wall-ctrl{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:26px}}
.wall-ctrl .sort-g{{display:flex;gap:8px;align-items:center;margin-left:8px}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px;position:relative}}
a.card-link{{display:flex;flex-direction:column;height:100%;text-decoration:none;color:inherit}}
.card{{position:relative;background:var(--card);border:2px solid var(--stroke);padding:12px 14px;display:flex;flex-direction:column;gap:5px;height:100%;min-width:0}}
.card:hover{{border-color:var(--acc)}}
.card h3{{font-size:17px;font-weight:800;line-height:1.35;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.card p{{font-size:13px;color:var(--dim);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}}
.tag-row{{display:flex;align-items:center;gap:6px;flex-wrap:wrap}}
.tag-badge{{font-size:10px;font-weight:800;padding:2px 7px;border-radius:2px;white-space:nowrap;line-height:1.5;color:#1d2021}}
.tag-badge.bright{{color:#111}}
.tag-text{{font-size:11px;font-weight:700;color:var(--dim);white-space:nowrap;line-height:1.5}}
.empty{{color:var(--dim);font-size:16px;display:none;padding:40px 0;text-align:center}}
.lazy-sentinel{{position:absolute;bottom:0;left:0;width:1px;height:1px;pointer-events:none}}

/* footer */
.footer{{margin-top:64px;background:var(--stroke);color:var(--footer-fg);padding:26px 48px;display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}}
.f-left{{display:flex;align-items:center;gap:16px;flex-wrap:wrap}}
.f-sticker{{background:var(--acc);color:#111;border:3px solid var(--stroke);font-weight:900;font-size:15px;padding:9px 16px;transform:rotate(-1deg)}}
.f-note{{font-size:14px;font-weight:500;opacity:.85}}
.f-right{{font-family:"Maple Mono NF CN","Maple Mono",Consolas,monospace;font-size:14px;font-weight:700;letter-spacing:1px;opacity:.9}}

@media (max-width:720px){{
  .picks-grid{{grid-template-columns:1fr 1fr;gap:16px;min-width:0}}
  .picks-grid .pick-b{{width:auto;min-width:0}}
  .grid{{grid-template-columns:1fr}}
  .pick{{height:auto;max-height:none}} .pick-b{{min-height:120px;padding:16px;gap:6px}}
  .pick-b-body{{flex:2;align-items:flex-start;justify-content:center}}
  .pick-b-sub{{display:none}}
  .pick-b-btn{{position:absolute;bottom:6px;right:6px;width:32px;height:28px;padding:0;align-items:center;justify-content:center;font-size:0;border-radius:4px;flex:none}}
  .pick-b-btn::after{{content:'→';font-size:18px;line-height:1}}
  .sticky-inner{{padding:8px 20px}}
  .wrap{{padding:0 20px}}
  .masthead{{flex-direction:column;align-items:stretch;gap:12px}}
  .mast-row{{flex-direction:column;align-items:stretch;gap:10px}}
  .site-title{{font-size:18px}}
  .site-desc{{font-size:13px}}
  .mast-meta{{white-space:normal;text-align:left;font-size:12px;line-height:1.7}}
  .search-bar input{{width:100%;max-width:300px}}
  .fgroup{{grid-template-columns:1fr}}
  .flabel{{padding-top:0}}
}}
@media(min-width:721px){{
  .pick-b-count b{{font-size:48px}}
  .pick-b-name{{font-size:40px}}
  .pick-b-sub{{font-size:15px}}
  .pick-b-btn{{font-size:14px}}
}}

</style>
</head>
<body>
<div class="sticky-bar" id="sticky-bar">
  <div class="progress-wrap"><div class="progress-bar" id="progress"></div></div>
  <div class="color-ribbon">
    <div class="seg seg-model"></div>
    <div class="seg seg-journey"></div>
    <div class="seg seg-scam"></div>
    <div class="seg seg-agent"></div>
  </div>
  <div class="sticky-inner">
    <span class="sticker">biz.saaaai.com</span>
    <span class="sticky-meta">共 {n_total} 条情报</span>
  </div>
</div>

<div class="wrap">

  <header class="masthead">
    <div class="mast-title">
      <h1 class="site-title">商业灵感 · 商业模式情报站</h1>
      <p class="site-desc">赚钱模式拆解 · 企业发家历程 · 骗局识别 · AI工具实践 — AI驱动的商业模式情报站，每日更新，全自动采集</p>
    </div>
    <div class="mast-row">
      <div class="search-bar">
        <input id="q" type="search" placeholder="🔍 搜模式 / 公司 / 行业…" autocomplete="off">
        <button id="search-btn" class="search-btn" style="display:none" onclick="doSearch()" title="搜索">🔍</button>
        <span class="hint">支持名称 / 行业 / 地区 / 关键词</span>
      </div>
      <div class="mast-meta">
        <div><span class="bar"></span>{now_str} — 全自动采集</div>
      </div>
    </div>
  </header>

  <section class="picks-sec" id="picks-sec">
    {picks_html}
  </section>

  <section class="wall-sec">
    <div class="wall-head">
        <h2 id="wall-title">{esc(TAB_LABEL['model'])} · 贴纸墙</h2>
        <span class="sec-note" id="wall-note">共 {n_model} 条 · 点卡片看详情</span>
      </div>
      <div class="wall-ctrl">
        <button class="view-btn view-model on" data-tab="model" type="button">{esc(TAB_LABEL['model'])}<span class="num">{n_model}</span></button>
        <button class="view-btn view-journey" data-tab="journey" type="button">{esc(TAB_LABEL['journey'])}<span class="num">{n_journey}</span></button>
        <button class="view-btn view-scam" data-tab="scam" type="button">{esc(TAB_LABEL['scam'])}<span class="num">{n_scam}</span></button>
        <button class="view-btn view-agent" data-tab="agent" type="button">{esc(TAB_LABEL['agent'])}<span class="num">{n_agent}</span></button>
        <div class="sort-g">
          <select class="sort" id="sort" aria-label="排序">
            <option value="">排序 · 默认</option>
            <option value="name">按名称</option>
            <option value="hot">按热度</option>
            <option value="scale">按规模</option>
          </select>
          <button class="chip-acc" id="btn-filter" type="button">筛选 ▾</button>
          <button class="chip-acc" id="btn-clear" type="button" style="display:none">清除 ×</button>
        </div>
      </div>
    <div class="filters" id="filters" aria-label="筛选">
      {chip_html}
    </div>
    <div class="grid" id="grid-model">{''.join(model_cards)}<div class="lazy-sentinel" data-grid="model"></div></div>
    <div class="grid" id="grid-journey" style="display:none">{''.join(journey_cards)}<div class="lazy-sentinel" data-grid="journey"></div></div>
    <div class="grid" id="grid-scam" style="display:none">{''.join(scam_cards)}<div class="lazy-sentinel" data-grid="scam"></div></div>
    <div class="grid" id="grid-agent" style="display:none">{''.join(agent_cards)}<div class="lazy-sentinel" data-grid="agent"></div></div>
    <div class="empty" id="empty">没有匹配的条目，换一组筛选试试。</div>
  </section>

</div>

<footer class="footer">
  <div class="f-left">
    <span class="f-sticker">共 {n_total} 条情报</span>
    <span class="f-note">生成时间 {now_str} · 数据由 AI 持续自动采集</span>
  </div>
  <div class="f-right">商业灵感 © 2026 · biz.saaaai.com</div>
</footer>

<script>
/* 搜索索引构建（所有卡片，含懒加载未显示的） */
var cardIndex = [];
function buildIndex() {{
  cardIndex.length = 0;
  var _idx = 0;
  Object.values(grids).forEach(function(g) {{
    [].slice.call(g.querySelectorAll('.card')).forEach(function(el) {{
      el._cardIdx = _idx;
      cardIndex.push({{
        el: el,
        _idx: _idx++,
        tab: g.id.replace('grid-',''),
        text: (el.dataset.search || '').toLowerCase(),
        dims: {{industry: el.dataset.industry||'', region: el.dataset.region||'',
               scale: el.dataset.scale||'', channel: el.dataset.channel||'',
               gregion: el.dataset.gregion||'', gscale: el.dataset.gscale||''}},
        hot: +el.dataset.hot || 0,
        name: (el.querySelector('h3')||{{}}).textContent || '',
        _matched: true
      }});
    }});
  }});
}}

const tabs = document.querySelectorAll('.view-btn[data-tab]');
const count = document.getElementById('wall-note');
const empty = document.getElementById('empty');
const q = document.getElementById('q');
const sortSel = document.getElementById('sort');
const grids = {{
  model: document.getElementById('grid-model'),
  journey: document.getElementById('grid-journey'),
  scam: document.getElementById('grid-scam'),
  agent: document.getElementById('grid-agent'),
}};
const SEC_TITLES = {{ model: '商业模式 · 贴纸墙', journey: '发家历程 · 贴纸墙', scam: '骗局揭秘 · 贴纸墙', agent: 'AI实干家 · 贴纸墙' }};
const wallTitle = document.getElementById('wall-title');
let active = 'model';
const sel = {{}};
var lastSearchKw = '';

/* sort dropdown change listener */
sortSel.addEventListener('change', function() {{ apply(); }});

document.querySelectorAll('.chip[data-dim]').forEach(function(ch) {{
  const d = ch.dataset.dim;
  if (!sel[d]) sel[d] = new Set();
  ch.addEventListener('click', function() {{
    const v = ch.dataset.val;
    if (sel[d].has(v)) {{ sel[d].delete(v); ch.classList.remove('on'); }}
    else {{ sel[d].add(v); ch.classList.add('on'); }}
    apply();
  }});
}});
const SCALE_W = {{'灰产':0,'小企':1,'中型':2,'巨头':3,'其他':1,'':1}};
function scaleRank(c) {{ return SCALE_W[c.dataset.gscale] ?? 1 }}

/* 搜索按钮显示/隐藏：打字显示按钮，清空还原 */
q.addEventListener('input', function() {{
  var btn = document.getElementById('search-btn');
  btn.style.display = q.value.trim() ? 'flex' : 'none';
  if (!q.value.trim() && lastSearchKw) {{
    lastSearchKw = '';
    cardIndex.forEach(function(item) {{ if (item.tab === active) item._matched = true; }});
    apply();
  }}
}});

/* Enter 键触发搜索 */
q.addEventListener('keydown', function(e) {{
  if (e.key === 'Enter') {{
    e.preventDefault();
    doSearch();
  }}
}});

/* 搜索：只匹配卡片名称，然后滚动到结果 */
function doSearch() {{
  var kw = q.value.trim().toLowerCase();
  lastSearchKw = kw;
  var btn = document.getElementById('search-btn');
  btn.style.display = kw ? 'flex' : 'none';

  if (!kw) {{
    cardIndex.forEach(function(item) {{ if (item.tab === active) item._matched = true; }});
    apply();
    return;
  }}

  cardIndex.forEach(function(item) {{
    if (item.tab !== active) return;
    item._matched = item.name.toLowerCase().includes(kw);
  }});

  apply();

  /* 滚动到第一个可见结果 */
  var firstVisible = cardIndex.find(function(item) {{
    return item.tab === active && item._matched;
  }});
  if (firstVisible) {{
    firstVisible.el.scrollIntoView({{behavior:'instant', block:'start'}});
  }}
}}

function apply() {{
  /* 基于现有 _matched（搜索结果）叠加筛选 + 排序 */
  visible = cardIndex.filter(function(item) {{
    if (item.tab !== active) return false;
    if (!item._matched) return false;
    for (const [d, setv] of Object.entries(sel)) {{
      if (setv.size && !setv.has(item.dims[d])) {{ return false; }}
    }}
    return true;
  }});

  /* 可见性集合 */
  var visibleSet = {{}};
  visible.forEach(function(item) {{ visibleSet[item._idx] = true; }});

  /* 增量 DOM 更新：只改状态变化的卡片 */
  var totalLoaded = 0;
  cardIndex.forEach(function(item) {{
    if (item.tab !== active) return;
    totalLoaded++;
    const isVisible = !!visibleSet[item._idx];
    const isHidden = item.el.style.display === 'none' || item.el.dataset.lazy === '1';
    if (isVisible && isHidden && item.el.dataset.lazy !== '1') item.el.style.display = '';
    else if (!isVisible && !isHidden) item.el.style.display = 'none';
    /* lazy cards: let IntersectionObserver handle reveal */
  }});

  /* 排序 */
  const sortv = sortSel.value;
  if (sortv === 'name') visible.sort(function(a,b) {{ return a.name.localeCompare(b.name,'zh'); }});
  else if (sortv === 'scale') visible.sort(function(a,b) {{ return scaleRank(b.el) - scaleRank(a.el); }});
  else if (sortv === 'hot') visible.sort(function(a,b) {{ return b.hot - a.hot; }});
  if (sortv) {{
    const grid = grids[active];
    const sent = grid.querySelector('.lazy-sentinel');
    visible.forEach(function(item) {{ grid.insertBefore(item.el, sent); }});
  }}

  /* 高亮标记 */
  if (lastSearchKw) {{
    cardIndex.forEach(function(item) {{
      if (item.tab !== active) return;
      var h3 = item.el.querySelector('h3');
      if (!h3) return;
      var txt = h3.textContent;
      var idx = txt.toLowerCase().indexOf(lastSearchKw);
      if (idx >= 0 && item._matched) {{
        h3.innerHTML = txt.slice(0, idx) + '<mark class="hl">' + txt.slice(idx, idx + lastSearchKw.length) + '</mark>' + txt.slice(idx + lastSearchKw.length);
      }} else if (h3.querySelector('.hl')) {{
        h3.innerHTML = txt;
      }}
    }});
  }} else {{
    /* 清除高亮 */
    cardIndex.forEach(function(item) {{
      if (item.tab !== active) return;
      var h3 = item.el.querySelector('h3');
      if (h3 && h3.querySelector('.hl')) h3.innerHTML = h3.textContent;
    }});
  }}

  empty.style.display = visible.length ? 'none' : 'block';
  wallTitle.textContent = SEC_TITLES[active];
  count.textContent = '共 ' + totalLoaded + ' 条 · 命中 ' + visible.length + ' 条 · 点卡片看详情';
}}

tabs.forEach(function(t) {{ t.addEventListener('click', function() {{
  tabs.forEach(function(x) {{ x.classList.toggle('on', x === t); }});
  active = t.dataset.tab;
  Object.entries(grids).forEach(function([k,g]) {{ g.style.display = (k === active) ? '' : 'none'; }});
  apply();
}}); }});

/* picks 引导卡：点卡切对应 tab + 滚到贴纸墙 */
document.querySelectorAll('.pick[data-tab]').forEach(function(p){{
  p.addEventListener('click', function(){{
    var tab = p.dataset.tab;
    var t = document.querySelector('.view-btn[data-tab="'+tab+'"]');
    if (t) t.click();
    var ws = document.querySelector('.wall-sec');
    if (ws) ws.scrollIntoView({{behavior:'instant', block:'start'}});
  }});
}});

buildIndex();
apply();

/* 懒加载：per-grid sentinel + per-grid hiddenPool + per-grid IO */
(function(){{
  var BATCH = 24;
  if(!('IntersectionObserver' in window)) return;
  var pools = {{}};
  var sentinels = {{}};
  var io = null;
  Object.keys(grids).forEach(function(tab){{
    var g = grids[tab];
    var s = g.querySelector('.lazy-sentinel[data-grid="'+tab+'"]');
    if(!s) return;
    var cards = [].slice.call(g.querySelectorAll('.card'));
    var hidden = cards.slice(BATCH);
    hidden.forEach(function(c){{ c.dataset.lazy='1'; c.style.display='none'; }});
    pools[tab] = hidden;
    sentinels[tab] = s;
  }});
  function observe(tab){{
    if (io) io.disconnect();
    io = new IntersectionObserver(function(entries){{
      if(entries.some(function(e){{ return e.isIntersecting; }})){{ reveal(tab); }}
    }}, {{rootMargin:'600px 0px'}});
    io.observe(sentinels[tab]);
  }}
  function reveal(tab){{
    var p = pools[tab] || [];
    var n = Math.min(BATCH, p.length);
    for(var i=0;i<n;i++){{ var c=p.shift(); c.dataset.lazy=''; c.style.display=''; }}
    if(p.length===0 && io) io.disconnect();
  }}
  observe(active);
  /* 切 tab 时重启 IO */
  document.querySelector('.wall-ctrl').addEventListener('click', function(e){{
    var b = e.target.closest('.view-btn[data-tab]'); if(!b) return;
    var tab = b.dataset.tab;
    setTimeout(function(){{ observe(tab); }}, 50);
  }});
}})();
</script>
</body>
</html>"""
    (SITE / "index.html").write_text(index, encoding="utf-8")
    (SITE / "index.html").write_text(index, encoding="utf-8")



def write_favicon() -> None:
    """写入站点头像（独立 SVG，供 favicon link 引用）。"""
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
<rect x="2" y="2" width="44" height="44" rx="11" fill="#1d2021"/>
<rect x="2" y="2" width="44" height="44" rx="11" stroke="#ebdbb2" stroke-opacity="0.15" stroke-width="1.2"/>
<polyline points="10,36 18,26 26,28 34,14" fill="none" stroke="#fabd2f" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="34" cy="14" r="4" fill="#fe8019"/>
<path d="M8 37 L40 37" stroke="#ebdbb2" stroke-opacity="0.2" stroke-width="1"/>
</svg>
'''
    (SITE / "favicon.svg").write_text(svg, encoding="utf-8")


def write_data_json(models: list[dict]) -> None:
    by_type = {"model": 0, "journey": 0, "scam": 0}
    for m in models:
        by_type[m.get("type", "model")] = by_type.get(m.get("type", "model"), 0) + 1
    manifest = {"updated": datetime.now().isoformat(timespec="seconds"),
                 "count": len(models), "by_type": by_type, "models": models}
    (SITE / "data.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")


def write_robots_txt() -> None:
    """robots.txt：训练型爬虫拦截 + 检索型放行 + Sitemap 指向（纯 SEO 层，2026-08-13）。"""
    agents = ["GPTBot", "ClaudeBot", "Google-Extended", "PerplexityBot",
              "CCBot", "Amazonbot", "Bytespider"]
    body = "\n\n".join(f"User-agent: {a}\nDisallow: /" for a in agents)
    content = (body
               + "\n\nUser-agent: *\nAllow: /\n\n"
               + "Sitemap: https://biz.saaaai.com/sitemap.xml\n")
    (SITE / "robots.txt").write_text(content, encoding="utf-8")


def write_sitemap_xml(models: list[dict]) -> None:
    """sitemap.xml：首页 + 全部详情页 slug（data/*.json 全量）。纯 SEO 层。"""
    urls = ['<url><loc>https://biz.saaaai.com/</loc>'
            '<changefreq>daily</changefreq><priority>1.0</priority></url>']
    for m in models:
        # 只列实际渲染成功的页面（渲染失败/数据缺失的条目不进 sitemap，避免失效 URL）
        if not (SITE / f"{m['id']}.html").exists():
            continue
        urls.append(f'<url><loc>https://biz.saaaai.com/{m["id"]}.html</loc>'
                    '<changefreq>weekly</changefreq><priority>0.8</priority></url>')
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           + "\n".join("  " + u for u in urls) + "\n</urlset>\n")
    (SITE / "sitemap.xml").write_text(xml, encoding="utf-8")


def write_seo_files(models: list[dict]) -> None:
    """站点 SEO 静态文件统一入口：robots.txt + sitemap.xml。"""
    write_robots_txt()
    write_sitemap_xml(models)


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
            if os.name != "posix":
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
    # 2026-08-09 修正（P0-7）：全量重建前 rmtree 旧 models 目录——否则数据已删的条目
    # （如 dreame-motor-tech）html 孤儿残留且 nginx 继续 serve。
    # --only 单条重建不清理（避免真空窗）；全量重建才整体重置。
    if not args.only:
        import shutil
        shutil.rmtree(MODELS_OUT, ignore_errors=True)
    MODELS_OUT.mkdir(parents=True, exist_ok=True)
    models, load_errors = load_models()
    if load_errors and not args.only:
        # 2026-08-09 修正（P0-5）：print 全部坏数据后继续重建（坏条跳过不阻塞），
        # 坏数据占比 >10% 才整体中止（防毒文件静默批量逃跑）
        print(f"[warn] {len(load_errors)} 条数据缺失必填/损坏，已跳过不渲染:")
        for e in load_errors:
            print(f"      {e}")
        if len(load_errors) > max(1, len(models) // 10):
            print(f"[err] 坏数据占比过高（{len(load_errors)}/{len(models)}），中止重建，需人工修复数据")
            for e in load_errors:
                print(f"    {e}")
            return 1
    if args.only:
        models = [m for m in models if m["id"] == args.only]
        if not models:
            raise SystemExit(f"无此 id: {args.only}")
    render_fail: list[str] = []
    for m in models:
        mtype = m.get("type", "model")
        pool = [x for x in models if x.get("type", "model") == mtype]
        related = _related(m, pool, k=4)
        try:
            if mtype == "journey":
                render_journey_page(m, related)
            elif mtype == "scam":
                render_scam_page(m, related)
            elif mtype == "agent":
                render_agent_page(m, related)
            else:
                render_workflow(m)
                render_model_page(m, related)
        except Exception as e:
            # 2026-08-09 修正（P0-4/5）：单条渲染失败（archify Label 超宽 / 字段类型坏）
            # 不再炸全量，记入 render_fail 继续下一条；>10% 失败才中止
            render_fail.append(f"{m['id']} ({mtype}): {e}")
            print(f"[warn] 渲染失败跳过 {m['id']}: {e}")
            continue
        print(f"[ok] {m['id']} ({mtype}) — {m['name']}")
    if render_fail and not args.only:
        print(f"[warn] {len(render_fail)} 条渲染失败被跳过:")
        for e in render_fail[:20]:
            print(f"    {e}")
        if len(render_fail) > max(1, len(models) // 10):
            print(f"[err] 渲染失败过多（{len(render_fail)}/{len(models)}），中止")
            return 1
    if not args.only:
        build_index(models)
        write_data_json(models)
        write_favicon()
        write_seo_files(models)
        print(f"[ok] index.html 共 {len(models)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())



