#!/usr/bin/env python3
"""collect.py — 商业模式情报站 自动采集器（Hermes cron 调用）

流程（一轮）：
  1. 读 data/topics.json 轮换选题（state 记 data/.collect_state.json）
  2. 经本机 search MCP（100.86.60.101:8091）搜索该选题的 2026 新线索
  3. 调 intel_hub LLM 按 SCHEMA 生成候选条目 JSON（草稿 → data/_drafts/）
  4. 校验必填 + 与 data/ 查重
  5. 通过 → data/<id>.json；重跑 scripts/generate_site.py 重建站点
  6. git commit + 输出摘要（Hermes 投递）

用法：
  python3 collect.py --dry-run     # 只到草稿，不落正式区/不重建/不 commit
  python3 collect.py               # 完整一轮
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import difflib
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DRAFTS = DATA / "_drafts"
STATE_PATH = DATA / ".collect_state.json"
MCP_URL = "http://100.86.60.101:8091/mcp"

sys.path.insert(0, str(Path.home() / ".hermes" / "local" / "intel_hub"))
from common import (  # noqa: E402
    call_direct_chat_completions_model,
    ensure_intel_state_dir,
    load_json,
    now_iso,
    rotate_telegram_message,
    save_json,
    send_telegram_json,
)
NOTIFY_HOME = Path.home() / ".hermes" / "local" / "intel_hub"
NOTIFY_STATE = NOTIFY_HOME / "state" / "biz_collect_notify.json"
NOTIFY_ACCOUNT = "default"
NOTIFY_CHAT_ID = "8138445887"
NOTIFY_STATE_KEY = "biz_collect_msg"
# 连续失败计数：LLM 抖/搜索抖/JSON 坏只记 audit_log，连续 3 轮全失败才 TG 告警一次（避免上游基建抖动刷屏骚扰）
FAIL_STATE = NOTIFY_HOME / "state" / "biz_collect_fail.json"
FAIL_THRESHOLD = 3

# 停止条件：条目总数达此值自动停（非实时新闻，积累到量即可；--limit N 可覆盖）
DEFAULT_LIMIT = 500
# 审计日志目录（一轮一文件，记录 LLM 原始输出/搜索结果/被拒原因，可回溯）
AUDIT_DIR = ROOT / "logs"
REQUIRED = ["id", "name", "industry", "region", "scale", "channel",
            "background", "target", "revenue", "cost", "moat",
            "swot", "keys", "risks", "example", "sources"]
REQUIRED_BY_KIND = {
    "model": REQUIRED,
    "journey": ["id", "name", "company", "founders", "industry", "region", "scale",
                "channel", "origin", "milestones", "turning_points", "failures",
                "keys", "lessons", "metrics", "sources"],
    "scam": ["id", "name", "industry", "region", "scale", "channel", "victims",
             "how_it_works", "red_flags", "real_cases", "official_alerts",
             "protection", "sources"],
}

# 日文假名（含片假名）——正文禁日文，命中拒收
_JP_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff\uff66-\uff9f]")
_COMMON_TAIL = ("3) 全部正文字段用简体中文写，禁任何日文假名词句；专名如 note/Skeb/蜜雪冰城可保留；\n"
                "4) 数字与案例必须有搜索结果支撑，没把握的字段宁缺勿编；\n"
                "5) 与已有条目重复/换皮（见已有清单）直接跳过；\n"
                "6) 正文禁夹中英混杂残句（孤立英文小写词后接中文逗号/分号这一类半中半英写法），\n"
                "   英文专名请整词保留在完整中文语境中，违者整条拒收。直接输出 JSON，禁输出思考过程。")
LLM_INSTRUCTIONS_MODEL = (
    "你是「商业模式情报站」的调研编辑。根据用户给出的 2026 年行业线索搜索结果，"
    "提炼 1~2 条真实、可验证的商业模式条目（type 缺省=model，不要写 type 字段）。\n"
    "硬性要求：\n"
    "1) 只输出一个 JSON 数组，不要任何解释文字/代码块标记；\n"
    "2) 每条字段必填：id(英文短横线slug)、name(≤40字中文名)、industry(只能从这14个里选一个：AI/大模型 / SaaS/企业软件 / 云计算 / 金融科技 / 内容/创作者经济 / 电商/零售 / 本地生活 / 餐饮/茶饮 / 教育/知识付费 / 医疗/养老 / 营销/广告 / 旅游 / 宠物 / 其他；找不到合适写「其他」，禁自创新词)、"
    "region(中|美|日|欧洲|东南亚|全球|跨地区)、scale(巨头|中型|小企|个人)、"
    "channel(线上|线下|实体|混合)、background(行业背景·为何2026热·2-3句)、"
    "target(目标客户·谁付钱)、revenue(盈利点·钱从哪来·3行内)、cost(成本结构)、"
    "moat(护城河)、swot(四维对象 s/w/o/t 各数组≥1条，含义=优势/劣势/机会/威胁)、"
    "keys(数组2-3成功关键)、risks(数组1-3风险)、example(数组1-3真实案例)、"
    "sources(数组≥2真实URL·从搜索结果挑·禁编造)；\n"
    + _COMMON_TAIL
)
LLM_INSTRUCTIONS_JOURNEY = (
    "你是「商业模式情报站」发家路径板块的调研编辑。根据用户搜索结果，"
    "提炼 1 条真实、可验证的企业发家路径条目（type=\"journey\"）。\n"
    "硬性要求：\n"
    "1) 只输出一个 JSON 数组（单条），不要解释文字/代码块标记；\n"
    "2) 每条必含字首字段：type=\"journey\"、id(英文slug)、name(≤40字·含公司名+一句话定位)、"
    "company(公司全称)、founders(创始人·可多人顿号分隔)、industry(14大类同model)、"
    "region(中|美|日|欧洲|东南亚|全球|跨地区)、scale(巨头|中型|小企|个人)、channel(同model)、"
    "y2026_hot(为何2026值得看·2-3行)、origin(起步缘由·为什么做这个·3-4行)、"
    "milestones(数组≥5·每项含 time/stage/outcome(失败|拐点|转折|PMF|增长)/detail·每项detail≥50字·至少2个失败或拐点)、"
    "turning_points(纯字符串数组≥3·每个元素一句话·禁止对象)、"
    "failures(纯字符串数组≥3·每个元素一句话·禁止对象)、"
    "keys(纯字符串数组≥4·每个元素一句话)、lessons(纯字符串数组≥4·每个元素一句话)、"
    "metrics(对象≥5键·核心数据如ARR/毛利/付费率/团队规模/融资额等·尽量带具体数字·禁止只用『未披露』敷衍)、"
    "competitors(一段话≥80字·同行对标)、"
    "sources(数组≥4真实URL·从搜索结果挑·禁编造·优先访谈/官方/行业文)；\n"
    "灵魂：阶段+转折+失败+决策+数据，失败与踩坑 > 成功叙事，禁编造；\n"
    + _COMMON_TAIL.replace("5) 与已有条目", "5) 与已有条目（jos版）")
)
LLM_INSTRUCTIONS_SCAM = (
    "你是「商业模式情报站」避坑指南板块的调研编辑。根据用户搜索结果，"
    "提炼 1 条真实、可验证的骗局拆解条目（type=\"scam\"）。\n"
    "硬性要求：\n"
    "1) 只输出一个 JSON 数组（单条），不要解释文字/代码块标记；\n"
    "2) 每条必含字首字段：type=\"scam\"、id(英文slug)、name(≤40字·骗局名+一句话)、"
    "industry(14大类同model)、region(同model)、scale(灰产或小企)、channel(同model)、"
    "y2026_hot(为何2026值得看·2-3行)、victims(一段话≥80字·受骗人群画像与心理弱点)、"
    "how_it_works(数组≥5·骗局步骤·每步≥60字带机制说明与话术)、red_flags(数组≥5·红旗信号·可识别特征)、"
    "real_cases(数组≥3·真实案例·带可查证细节如时间/金额/公司·人员一律脱敏：禁出现真实姓名，用「甲某/乙某/A某/B某」或「某女子」「某开发者」等代称·只引公开报道/官方通报已披露的信息)、"
    "official_alerts(数组≥3·官方警示·带日期与机构名)、protection(数组≥4·防护建议·每步可执行)、"
    "legal_note(一段话≥80字·法律提示·律师观点或法规依据)、"
    "sources(数组≥4真实URL·从搜索结果挑·禁编造·优先官方警示/新闻起底/专题报道)；\n"
    "灵魂：五段闭环—怎么运作→怎么识别→真实案例→官方态度→怎么防护；"
    "表述边界：只引用官方警示与已公开报道，不点名未定罪主体，加法律提示块；\n"
    + _COMMON_TAIL.replace("5) 与已有条目", "5) 与已有条目（scam版）")
)
LLM_INSTRUCTIONS_BY_KIND = {
    "model": LLM_INSTRUCTIONS_MODEL,
    "journey": LLM_INSTRUCTIONS_JOURNEY,
    "scam": LLM_INSTRUCTIONS_SCAM,
}
LLM_INSTRUCTIONS = LLM_INSTRUCTIONS_MODEL  # 向后兼容引用


def mcp_call(payload: dict, sid: str | None = None) -> dict:
    import http.client
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2025-06-18"}
    if sid:
        headers["Mcp-Session-Id"] = sid
    conn = http.client.HTTPConnection("100.86.60.101", 8091, timeout=30)
    conn.request("POST", "/mcp", body=json.dumps(payload), headers=headers)
    resp = conn.getresponse()
    body = resp.read().decode("utf-8", "replace")
    sid2 = resp.getheader("Mcp-Session-Id") or sid
    conn.close()
    return {"status": resp.status, "body": body, "sid": sid2}


def search(query: str) -> list[dict]:
    init = mcp_call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                "clientInfo": {"name": "biz-collect", "version": "1.0"}}})
    sid = init.get("sid")
    if not sid:
        return []
    res = mcp_call({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "search",
                               "arguments": {"query": query, "synthesize": False}}}, sid)
    body = res["body"]
    # 解析 SSE：逐行找 data: {...}
    results = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            try:
                frame = json.loads(line[6:])
            except Exception:
                continue
            if "result" in frame:
                content = frame["result"].get("content") or []
                for c in content:
                    if c.get("type") == "text":
                        try:
                            txt = json.loads(c["text"])
                            if isinstance(txt, dict) and "results" in txt:
                                txt = txt["results"]
                            if isinstance(txt, list):
                                results.extend(txt)
                            else:
                                results.append(txt)
                        except Exception:
                            pass
    return results


def load_topic() -> tuple[str, str, str]:
    """三池配额轮换，返回 (topic_id, topic_desc, kind)。kind 缺省=model。

    2026-08-06 根因修复：旧版纯顺序轮换只走全局 idx，journey/scam 选题追加在
    topics.json 末尾，要跑完 104 条 model（10min/条≈17h）才轮到第一个非 model
    选题，新板块长期空转。现按轮盘配额：每 5 轮 = 3×model + 1×journey + 1×scam，
    三池各自独立 idx 顺序推进（同选题跑完一轮后查重拒收，天然跳过）。
    """
    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    topics = json.loads((DATA / "topics.json").read_text(encoding="utf-8"))["topics"]
    by_kind: dict = {}
    for t in topics:
        by_kind.setdefault(t.get("kind", "model"), []).append(t)
    # 轮盘配额：2026-08-06 用户指令——model 池 199 条已足够，先冻结；
    # journey/scam 两池交替各 50% 追进度，待用户示意后恢复 model
    _QUOTA = ("journey", "scam")
    round_no = state.get("round", 0)
    kind = _QUOTA[round_no % len(_QUOTA)]
    pool = by_kind.get(kind) or by_kind["model"]
    # 旧版全局 idx 迁移：旧 idx 即 model 池位置（journey/scam 追加在末尾）
    if "idx_model" not in state and "idx" in state:
        state["idx_model"] = state["idx"] % max(len(by_kind["model"]), 1)
    idx = state.get("idx_%s" % kind, 0) % max(len(pool), 1)
    topic = pool[idx]
    state["idx_%s" % kind] = idx + 1
    state["round"] = round_no + 1
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return topic["id"], topic["desc"], topic.get("kind", "model")

def _norm_name(s: str) -> str:
    """归一化 name 用于相似度比较：去标点空格、转小写。"""
    return re.sub(r"[（()【】\[\]·、，,。.：:；;！!？?\-_/\\\s]+", "", str(s).lower())


def existing_records() -> dict:
    """扫描已有数据，返回 {ids, names, src_fps} 供去重判决。"""
    ids, names, src_fps = set(), [], set()
    for p in DATA.glob("*.json"):
        if p.name in ("topics.json", "index.json") or p.name.startswith("."):
            continue
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        ids.add(m.get("id", ""))
        names.append(_norm_name(m.get("name", "")))
        ss = tuple(sorted(set(m.get("sources", []))))
        if ss:
            src_fps.add(ss)
    return {"ids": ids, "names": names, "src_fps": src_fps}


def is_duplicate(cand: dict, ex: dict) -> tuple[bool, str]:
    """判决候选条目是否与已有重复。返回 (是否重复, 原因)。"""
    cid = cand.get("id", "")
    if cid and cid in ex["ids"]:
        return True, f"id 重复 ({cid})"
    src = tuple(sorted(set(cand.get("sources", []))))
    if src and src in ex["src_fps"]:
        return True, "sources 指纹完全重合"
    cn = _norm_name(cand.get("name", ""))
    if cn:
        for en in ex["names"]:
            if not en:
                continue
            r = difflib.SequenceMatcher(None, cn, en).ratio()
            if r >= 0.72:
                return True, f"name 相似度 {r:.2f}"
    return False, ""

def normalize(m: dict, kind: str = "model") -> dict | None:
    if not isinstance(m, dict):
        return None
    if m.get("id") in (None, ""):
        return None
    # 按 kind 选必填字段与校验逻辑
    req = REQUIRED_BY_KIND.get(kind, REQUIRED)
    for k in req:
        if k not in m or m[k] in (None, "", [], {}):
            return None
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", m["id"]):
        return None
    # 确保 type 字段与 kind 一致（journey/scam 必须带 type）
    if kind in ("journey", "scam"):
        m["type"] = kind
    # --- model 专属校验 ---
    if kind == "model":
        if not isinstance(m["swot"], dict) or set(m["swot"]) != {"s", "w", "o", "t"}:
            return None
        for dim in ("s", "w", "o", "t"):
            if not isinstance(m["swot"].get(dim), list) or not m["swot"][dim]:
                return None
        for arr_k in ("keys", "risks", "sources", "example"):
            if not isinstance(m[arr_k], list) or not m[arr_k]:
                return None
    # --- journey 专属校验 ---
    elif kind == "journey":
        ms = m.get("milestones", [])
        if not isinstance(ms, list) or len(ms) < 3:
            return None
        if not any(s.get("outcome") in ("失败", "拐点", "转折") for s in ms if isinstance(s, dict)):
            return None
        for arr_k in ("turning_points", "failures", "keys", "lessons", "sources"):
            if not isinstance(m.get(arr_k), list) or not m[arr_k]:
                return None
        if not isinstance(m.get("metrics"), dict) or not m["metrics"]:
            return None
    # --- scam 专属校验 ---
    else:  # scam
        for arr_k in ("how_it_works", "red_flags", "real_cases", "official_alerts", "protection", "sources"):
            if not isinstance(m.get(arr_k), list) or not m[arr_k]:
                return None
        if len(m["how_it_works"]) < 3 or len(m["red_flags"]) < 3 or len(m["real_cases"]) < 2:
            return None
    m["sources"] = [u for u in m["sources"] if isinstance(u, str)
                     and u.startswith(("http://", "https://"))]
    if len(m["sources"]) < 2:
        return None
    # journey/scam 的字符串数组字段可能被 LLM 偶发输出为对象/字典数组
    # （如 turning_points=[{time,desc}]），先规整回纯字符串数组再走后续日文/病句闸
    for arr_k in ("turning_points", "failures", "keys", "lessons",
                  "how_it_works", "red_flags", "real_cases", "protection"):
        v = m.get(arr_k)
        if not isinstance(v, list):
            continue
        fixed = []
        for x in v:
            if isinstance(x, str):
                fixed.append(x)
            elif isinstance(x, dict):
                for k in ("detail", "desc", "content", "text", "time"):
                    if isinstance(x.get(k), str) and x[k].strip():
                        fixed.append(x[k].strip())
                        break
        m[arr_k] = fixed
        if arr_k in ("turning_points", "failures", "keys", "lessons") and not fixed:
            return None
    # 正文禁日文假名（专名可含英文/Latin，但整个正文含假名即拒）
    # 按 kind 选不同正文字段集
    if kind == "model":
        text_fields = ["name", "industry", "region", "scale", "channel",
                       "background", "target", "revenue", "cost", "moat"]
        arr_text_fields = ("keys", "risks", "example")
    elif kind == "journey":
        text_fields = ["name", "company", "founders", "industry", "region", "scale", "channel", "origin"]
        arr_text_fields = ("turning_points", "failures", "keys", "lessons")
    else:  # scam
        text_fields = ["name", "industry", "region", "scale", "channel", "victims", "legal_note"]
        arr_text_fields = ("how_it_works", "red_flags", "real_cases", "official_alerts", "protection")
    for f in text_fields:
        if _JP_RE.search(str(m.get(f, ""))):
            return None
    for f in arr_text_fields:
        if any(_JP_RE.search(str(x)) for x in m.get(f, [])):
            return None
    if kind == "model":
        for dim in ("s", "w", "o", "t"):
            if any(_JP_RE.search(str(x)) for x in m["swot"][dim]):
                return None
    # LLM 偶尔把正文字段吐成 list，统一转 str（按 kind 选字段集）
    _str_fields = {"model": ("background","target","revenue","cost","moat"),
                   "journey": ("company","founders","origin","y2026_hot","competitors"),
                   "scam": ("victims","legal_note","y2026_hot")}
    for f in _str_fields.get(kind, ()):
        if isinstance(m.get(f), list):
            m[f] = " ".join(str(x) for x in m[f])
        if not isinstance(m.get(f), str):
            m[f] = str(m.get(f, ""))
    # region/scale 归一到 runbook 规范值（同 generate_site NORM），存盘即干净
    _NORM_R = {"中国": "中", "美国": "美", "日本": "日"}
    _NORM_S = {"中企": "中型", "中小企": "中型", "混合": "中型", "中小创作者·平台生态": "小企"}
    if m.get("region", "") in _NORM_R:
        m["region"] = _NORM_R[m["region"]]
    if m.get("scale", "") in _NORM_S:
        m["scale"] = _NORM_S[m["scale"]]
    # industry 归一到 14 大类（同 generate_site IND_CATALOG），找不到写"其他"
    _IND_CAT = ["AI/大模型", "SaaS/企业软件", "云计算", "金融科技", "内容/创作者经济",
                "电商/零售", "本地生活", "餐饮/茶饮", "教育/知识付费", "医疗/养老",
                "营销/广告", "旅游", "宠物", "其他"]
    _IND_KEYS = [
        ("AI/大模型", ["ai", "大模型", "agent", "生成式", "人工智能", "aigc", "半导体", "开源软件"]),
        ("SaaS/企业软件", ["saas", "企业软件", "软件订阅", "软件投资", "定价与变现", "独立saas", "独立开发", "工具软件", "效率工具", "虚拟产品"]),
        ("云计算", ["云计算", "云服务", "基础设施"]),
        ("金融科技", ["金融科技", "支付", "碳交易"]),
        ("内容/创作者经济", ["内容", "创作者", "短剧", "漫画", "影视", "流媒体", "自媒体", "会员媒体", "法人媒体", "会员经济/媒体"]),
        ("电商/零售", ["电商", "零售", "即时零售", "跨境电商", "社交电商", "数字商品", "数字服务", "消费电子"]),
        ("本地生活", ["本地生活", "本地服务", "o2o", "到店"]),
        ("餐饮/茶饮", ["餐饮", "茶饮", "咖啡", "食品加工", "餐饮供应链"]),
        ("教育/知识付费", ["教育", "知识付费", "知识变现", "母婴"]),
        ("医疗/养老", ["医疗", "数字医疗", "养老", "慢病"]),
        ("营销/广告", ["营销", "广告", "it服务", "it咨询", "dx咨询", "系统集成", "代运营", "it・", "自动化/流程", "企业服务咨询"]),
        ("旅游", ["旅游", "体验经济"]),
        ("宠物", ["宠物"]),
    ]
    ind = m.get("industry", "").strip()
    if ind not in _IND_CAT:
        low = ind.lower()
        hit = next((c for c, ks in _IND_KEYS if any(k in low for k in ks)), "其他")
        m["industry"] = hit
    return m


LOCK_PATH = DATA / ".collect.lock"


def _probe_url(u: str, timeout: float = 15) -> bool:
    """真实可达性探活（HEAD→GET 回退，每 method 重试 1 次容忍 WAF/抖动）。

    ROOT-CAUSE FIX (2026-08-06): 单次 10s 无重试对慢/WAF 站误判死链，
    导致 LLM 出了合规 JSON + 权威源（新华网/CCTV/澎湃）也被质量闸整条拒，
    表现为「连续失败」刷屏告警。判断死链前至少重试一次（MaxKB 教训
    doc_id 019fd366/evolution/portfolio-tick-rootfix 同源）。"""
    import urllib.request
    for method in ("HEAD", "GET"):
        for _attempt in (1, 2):  # 每 method 最多 2 次（首次 + 1 次重试）
            try:
                req = urllib.request.Request(u, method=method,
                                             headers={"User-Agent": "Mozilla/5.0 (biz-collect-probe)"})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    if r.status < 400:
                        return True
            except Exception:
                continue
    return False


def _gate_sources(m: dict) -> bool:
    """①来源探活：删除 404/不可达 URL，<2 条则拒收整条。"""
    live = [u for u in (m.get("sources") or []) if _probe_url(u)]
    m["sources"] = live
    return len(live) >= 2


# 病句/机翻特征：孤立 ASCII 词夹中文标点、异常「…」结尾、汉字连续重复、非法字符
# 2026-08-06 修正：①白名单漏了中文引号 «""»「」『』、破折号 —、间隔号 ·、省略号 …，
# 导致 5+X、零投入/分成 等正常中文商业写法被当机翻误杀（13:19 green-economy 2 条全拒）。
# ②第 1/2 段去掉句号 。：App。此举 / 。EaaS（ 是正常中文技术写作（英文缩写+句号），
#   只保留逗号/分号/冒号混排（，；：）作机翻强特征（youtube，订阅 类）。
# ③英文贴中文标点特征限「小写开头」词，豁免大写品牌/专名（Cursor，/ OpenAI，/
#   Anthropic，是正常写作——journey 的 Cursor 条目被误杀的根因，2026-08-06 修）。
# ④2026-08-06 晚：白名单加 –（en dash U+2013），LLM 输出数字区间「1%–3%」被误杀
#   （fake-ai-crypto-quant-fund 补全被拒根因）；—（em dash）此前已有。
# ⑥同轮：白名单加 ×（U+00D7 乘号），「7×24小时」正常写法被非法字符拒（ai-digital-human 补全拒因）。
# ⑤同轮：CamelCase 品牌中间小写段（Cursor，→ ursor，）被 [a-z] 段误杀 → 加 (?<![A-Za-z0-9]) 前缀
#   与 (?![A-Za-z0-9]) 后缀否定，只拦「独立小写词+中文标点」的真机翻特征。
#   （fake-ai-crypto-quant-fund 补全被拒根因）；—（em dash）此前已有。
# ⑦2026-08-07：白名单加 →（U+2192 箭头），「免费层引流→付费订阅」正常流程箭头被非法字符拒
#   （lovable-ai-app-builder-subscription 补全被拒根因）。
_GLITCH_RE = re.compile(
    r"(?<![A-Za-z0-9])[a-z][a-zA-Z0-9]{1,}[，；：]|[，；：][a-z][a-zA-Z0-9]{1,}(?![A-Za-z0-9])|"
    r"([\u4e00-\u9fa5])\1{3,}|…\s*$|^[…。，；]|"
    r"[^\u4e00-\u9fa5A-Za-z0-9%，。；：！？、（）()《》「」『』“”‘’'—–×→\-·…\s/+\$%‰~,\.]"
)


# 按 kind 选正文字段集（供 _gate_text / _gate_truncation 复用）
_GATE_STR_FIELDS = {
    "model": ("background", "target", "revenue", "cost", "moat"),
    "journey": ("origin", "y2026_hot", "company", "founders", "competitors"),
    "scam": ("victims", "legal_note", "y2026_hot"),
}
_GATE_ARR_FIELDS = {
    "model": ("keys", "risks", "example"),
    "journey": ("turning_points", "failures", "keys", "lessons"),
    "scam": ("how_it_works", "red_flags", "protection"),
}


def _gate_text(m: dict, kind: str = "model") -> bool:
    """②病句/机翻检测：正文字段出现残句特征即拒收（拉丁专名 youtube/substack 等豁免）。"""
    for f in _GATE_STR_FIELDS.get(kind, _GATE_STR_FIELDS["model"]):
        t = str(m.get(f, ""))
        if _GLITCH_RE.search(t):
            return False
    for arr in _GATE_ARR_FIELDS.get(kind, _GATE_ARR_FIELDS["model"]):
        for x in m.get(arr, []):
            if _GLITCH_RE.search(str(x)):
                return False
    return True


def _gate_truncation(m: dict, kind: str = "model") -> bool:
    """③字段截断检测：核心字段时间段被截断的特征。

    LLM 不应在核心正文字段末尾留「…」或「...」，任何以省略号结尾都拒收。"""
    for f in _GATE_STR_FIELDS.get(kind, _GATE_STR_FIELDS["model"]):
        t = str(m.get(f, "")).strip()
        if len(t) >= 2 and t.endswith(("…", "...", "。。", "。。。")):
            return False
    return True


def quality_gate(m: dict, kind: str = "model") -> bool:
    """写入前总闸：来源探活 + 病句 + 截断，任一不过拒收整条。"""
    if not _gate_sources(m):
        return False
    if not _gate_text(m, kind):
        return False
    if not _gate_truncation(m, kind):
        return False
    return True


def _locked() -> bool:
    """锁文件存在且 pid 存活 → 判重叠中；否则接管锁。"""
    if LOCK_PATH.exists():
        try:
            pid = int(LOCK_PATH.read_text().strip() or "0")
            os.kill(pid, 0)
            return True  # 上一轮仍在跑（10m 周期防重叠）
        except (ValueError, ProcessLookupError, PermissionError):
            pass
    LOCK_PATH.write_text(str(os.getpid()))
    return False


def _release() -> None:
    try:
        LOCK_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def notify(text: str) -> None:
    """单气泡 Telegram 通知：发新消息 + 删旧消息，state 存 NOTIFY_STATE。"""
    try:
        ensure_intel_state_dir()
    except Exception:
        return
    state = load_json(NOTIFY_STATE, {})
    if not isinstance(state, dict):
        state = {}
    try:
        resp = send_telegram_json(NOTIFY_ACCOUNT, text, chat_id=NOTIFY_CHAT_ID)
        rotate_telegram_message(state, state_key=NOTIFY_STATE_KEY,
                                account_id=NOTIFY_ACCOUNT, response=resp)
        state["lastRunAt"] = now_iso()
        save_json(NOTIFY_STATE, state)
    except Exception as e:
        print(f"[notify] 发送失败: {e}")


def _fail_count() -> int:
    """读本轮之前累计的连续失败次数。"""
    st = load_json(FAIL_STATE, {})
    if not isinstance(st, dict):
        return 0
    return int(st.get("consecutive", 0))


def _notify_fail(text: str, infra_noise: bool = False) -> None:
    """失败静默化：记录连续失败到 FAIL_STATE，仅当达到阈值才 notify 一次并重置计数。

    上游基建抖动（LLM timeout/连接异常/搜索超时）是常态——每抖一次都 TG 会持续骚扰，
    反复把用户拉回处理「不是我能修」的基建问题。改为：连续 3 轮全失败才告警一次，
    中间任何一轮成功即清零。成功新增仍走 notify（有价值的正向消息）。

    infra_noise=True 表示本轮失败属基建抖（read timeout / 连接异常 / 搜索 MCP 抖），
    与本脚本逻辑、数据质量无关——只记 FAIL_STATE 的时间戳与原因，不递增 consecutive，
    不触发告警，避免上游慢/抖让「真无产出」告警被「基建抖」噪音淹没。"""
    if infra_noise:
        save_json(FAIL_STATE, {"consecutive": _fail_count(),  # 保留计数不递增
                               "lastReason": f"[infra] {text[:180]}", "lastAt": now_iso()})
        return
    n = _fail_count() + 1
    save_json(FAIL_STATE, {"consecutive": n, "lastReason": text[:200], "lastAt": now_iso()})
    if n >= FAIL_THRESHOLD:
        notify(f"❌ biz 采集连续 {n} 轮失败（最近：{text[:150]}），已静默 {n - 1} 轮")
        save_json(FAIL_STATE, {"consecutive": 0, "reportedAt": now_iso()})


def _notify_success() -> None:
    """成功（新增条目）清零失败计数——不想让旧抖动告警冲掉真实进展信号。"""
    if _fail_count() > 0:
        save_json(FAIL_STATE, {"consecutive": 0, "clearedAt": now_iso()})

def audit_log(topic_id: str, topic_desc: str, queries: list, raw: list,
               llm_raw: str, accepted: list, dropped: list) -> None:
    """一轮一文件审计日志：选题/query/LLM 原始输出/accept/drop 原因，可回溯。"""
    AUDIT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = AUDIT_DIR / f"collect-audit-{stamp}-{topic_id}.json"
    payload = {
        "at": now_iso(),
        "topic": {"id": topic_id, "desc": topic_desc},
        "queries": queries,
        "searchResults": raw[:200],
        "llmRaw": llm_raw[:20000] if llm_raw else "",
        "accepted": [a.get("id", "?") for a in accepted],
        "dropped": dropped,
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"[audit] 写日志失败: {e}")

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--topic", help="指定选题 id（默认轮换）")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                    help=f"条目总数达此值自动停（默认 {DEFAULT_LIMIT}，0=禁用）")
    ap.add_argument("--no-publish", action="store_true",
                    help="仅采集写 data，跳过站点重建/markdown/发布（供并发多 topic 采集，全部跑完统一重建）")
    args = ap.parse_args()
    import atexit
    # 锁：上一轮仍在跑 → 跳过（防止 cron 重叠）。并发 --no-publish 场景禁用锁
    if not args.no_publish and _locked():
        print("[skip] 上一轮仍在运行，本轮跳过")
        return 0
    atexit.register(_release)
    # 停止条件：达到上限 → 首次 notify 一次，之后静默跳过（避免 cron 每轮刷通知）
    cur_count = len(existing_records()["ids"])
    if args.limit > 0 and cur_count >= args.limit:
        st = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
        if not isinstance(st, dict):
            st = {}
        if st.get("goalReached"):
            return 0  # 已通知过，静默跳过
        st["goalReached"] = True
        STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
        msg = f"🛑 采集已达上限 {args.limit} 条（当前 {cur_count}），自动停止，后续轮次静默跳过。"
        print(msg)
        notify(msg)
        return 0

    kind = "model"
    if args.topic:
        topics = json.loads((DATA / "topics.json").read_text(encoding="utf-8"))["topics"]
        t = next((x for x in topics if x["id"] == args.topic), None)
        if not t:
            print(f"[err] 无此选题: {args.topic}")
            return 1
        topic_desc = t["desc"]
        topic_id = t["id"]
        kind = t.get("kind", "model")
    else:
        topic_id, topic_desc, kind = load_topic()

    print(f"[1/5] 选题：{topic_id} ({kind}) — {topic_desc}")
    # queries 按 kind 用不同模板
    if kind == "journey":
        queries = [f"2026 {topic_desc} 创业 发家 转型 失败 访谈",
                   f"2026 {topic_desc} 公司 创始人 发展历程 用户增长"]
    elif kind == "scam":
        queries = [f"2026 {topic_desc} 骗局 坑 起底 官方提示",
                   f"2026 {topic_desc} 受骗 案例 警方 网信办 央视"]
    else:
        queries = [f"2026 商业模式 {topic_desc}", f"2026 盈利模式 案例 {topic_desc}"]
    raw = []
    for q in queries:
        try:
            raw.extend(search(q))
            print(f"      搜索 '{q[:40]}…' → {len(raw)} 条候选")
        except Exception as e:
            print(f"      [warn] 搜索失败: {e}")

    if not raw:
        print("[2/5] 无搜索结果，跳过本轮")
        return 0

    existing = existing_records()
    existing_note = "\n".join(sorted(existing["ids"]))[:1500]
    prompt = (f"选题：{topic_desc}\n\n已有条目 id 清单（跳过重复/换皮，禁止换名同义重写）：\n{existing_note}\n\n"
              f"搜索结果：\n{json.dumps(raw, ensure_ascii=False)[:12000]}\n\n"
              f"直接输出 1 个合法 JSON 数组，不要任何思考过程/草稿/字段注释，全部正文字段用简体中文。")
    instructions = LLM_INSTRUCTIONS_BY_KIND.get(kind, LLM_INSTRUCTIONS_MODEL)
    # fallback 链：主模型(glm-5.2) → 实测可用的快模型
    # 2026-08-06 12:31+ 修正：原链 hermes 写的 deepseek-ai/deepseek-v4-flash 与
    # grok-3-mini-fast 在 cliproxy 不存在（502 unknown provider）。后用户删除
    # deepseek-ai/deepseek-v4-pro（快下架）。现链首为稳定的 z-ai/glm-5.2，
    # 其余为 2026-08-06 带凭证实测能直接出 JSON 的快模型（200 token 短测秒回）。
    _FALLBACK_CHAIN = [
        ("cliproxyapi", "z-ai/glm-5.2", 600),   # journey/scam 新标准输出更长(8500t)，240s 超时率极高
        ("cliproxyapi", "deepseek-v4-flash-free", 120),
        ("cliproxyapi", "big-pickle", 120),
        ("cliproxyapi", "openai/gpt-oss-20b", 120),
        ("cliproxyapi", "stepfun-ai/step-3.7-flash", 90),
        ("cliproxyapi", "mimo-v2.5-free", 90),
    ]
    text = ""
    llm_errors: list[str] = []
    # journey/scam 条目字段多、LLM 输出长，4500 上限曾把候选截断在思考过程（audit
    # 20260806-153120 cursor 候选 llmRaw 止于字段草稿、最终 JSON 未完成被质量闸拒）。
    # 放大到 6500 并提示直接输出 JSON（禁思考过程草稿）。
    # 2026-08-06 晚间：prompt 下限上调（journey milestones≥5/keys≥4/lessons≥4/metrics≥5键，
    # scam how_it_works≥5/red_flags≥5/cases≥3），输出更长 → 8500 防截断。
    max_tokens = 8500 if kind != "model" else 4500
    _primary = ("cliproxyapi", "z-ai/glm-5.2")  # 主模型始终是链首
    tried: set[tuple[str, str]] = set()
    for _provider, _model, _timeout in _FALLBACK_CHAIN:
        if (_provider, _model) in tried:
            continue
        tried.add((_provider, _model))
        try:
            text, _ = call_direct_chat_completions_model(
                prompt=prompt, instructions=instructions,
                provider_key=_provider, model=_model,
                max_output_tokens=max_tokens, timeout=_timeout)
            if text.strip():
                break
        except Exception as e:
            err = str(e)
            llm_errors.append(f"{_model}: {err}")
            print(f"[2/5] LLM 失败 ({_model}): {err}")
            text = ""
            continue
    if not text.strip():
        err = "; ".join(llm_errors) or "all LLM models returned empty"
        err_l = err.lower()
        # 基建抖（网络/超时/上游不可达）vs 真坏（配置错/模型名漂移/鉴权失败）：
        # reviewer catch 2026-08-06：原词表含 "502" 会把 "502 unknown provider" 这类配置错
        # 静默（正是 hermes 编造模型名导致全链 502 的同款 bug 类）。改为：只判网络/超时类
        # 信号为 infra；显式 unknown provider/model + 401/400/鉴权失败归真坏计数告警。
        is_infra = any(s in err_l for s in ("timed out", "timeout", "connection",
                                            "unreachable", "refused", "reset", "eof"))
        is_config_err = any(s in err_l for s in ("unknown provider", "unknown model",
                                                  "unauthorized", "401", "400"))
        is_infra = is_infra and not is_config_err  # 配置错优先，不静默
        print(f"[2/5] LLM 全链失败: {err}")
        _notify_fail(f"LLM 无响应（{err}）· 选题「{topic_desc}」", infra_noise=is_infra)
        audit_log(topic_id, topic_desc, queries, raw, "", [], [("llm-error", err)])
        return 1

    # 容错解析：剥 ```json 围栏
    def _parse(text: str):
        """解析 LLM 输出。支持：纯JSON / json围栏 / 思维链后提取 / 截断修复。"""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            obj = json.loads(text)
            if isinstance(obj, list):
                return obj
            return None
        except Exception:
            pass
        # 从思维链/长文本里提取第一个合法 JSON 数组
        m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.S)
        if not m:
            return None
        seg = m.group(0)
        try:
            return json.loads(seg)
        except Exception:
            # 截断修复：从右往左找合法 ]
            for cut in range(len(seg), 0, -1):
                if seg[cut - 1] == "]":
                    try:
                        return json.loads(seg[:cut])
                    except Exception:
                        continue
        return None
    candidates = _parse(text)
    if candidates is None:
        # 用 fallback 链里的下一个模型重试（tried 已包含主模型）
        retry_errors: list[str] = []
        for (_rp, _rm, _rt) in _FALLBACK_CHAIN:
            if (_rp, _rm) in tried:
                continue
            tried.add((_rp, _rm))
            try:
                r2, _ = call_direct_chat_completions_model(
                    prompt=prompt + "\n\n注意：上次 JSON 语法损坏。请只输出 1 条、用合法 JSON（所有字符串用双引号，逗号齐全，不要省略号/注释，直接输出 JSON 不要任何思考草稿）。",
                    instructions=instructions, provider_key=_rp, model=_rm,
                    max_output_tokens=max_tokens, timeout=_rt)
                candidates = _parse(r2)
                if candidates is not None:
                    break
            except Exception as e2:
                retry_errors.append(f"{_rm}: {e2}")
                continue
        if candidates is None:
            fail_detail = "LLM 输出非 JSON（重试也失败）"
            if retry_errors:
                fail_detail += f" · 重试错误：{'; '.join(retry_errors[:2])}"
            if llm_errors:
                fail_detail += f" · 原错误：{'; '.join(llm_errors[:2])}"
            print(f"[2/5] {fail_detail}\n---\n", text[:600])
            _notify_fail(f"{fail_detail}· 选题「{topic_desc}」")
            audit_log(topic_id, topic_desc, queries, raw, text, [], [("json-bad", fail_detail)])
            return 1

    DRAFTS.mkdir(exist_ok=True)
    accepted, dropped = [], []
    for c in candidates:
        if not isinstance(c, dict):
            dropped.append((str(c)[:40], "候选非对象（LLM 输出 schema 漂移）"))
            continue
        nm = normalize(c, kind)
        if nm is None:
            dropped.append((c.get("id", "?"), "字段不完整/来源不足"))
            continue
        if not quality_gate(nm, kind):
            dropped.append((c.get("id", "?"), "质量闸：来源死链/病句/截断"))
            continue
        dup, why = is_duplicate(nm, existing)
        if dup:
            dropped.append((nm["id"], why))
            continue
        (DRAFTS / f"{nm['id']}.json").write_text(
            json.dumps(nm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        accepted.append(nm)
        existing["ids"].add(nm["id"])
        existing["names"].append(_norm_name(nm["name"]))
        ss = tuple(sorted(set(nm.get("sources", []))))
        if ss:
            existing["src_fps"].add(ss)

    print(f"[3/5] 候选 {len(candidates)} → 通过 {len(accepted)}，跳过 {len(dropped)}")
    for mid, why in dropped:
        print(f"      - {mid}: {why}")
    if args.dry_run:
        print("[dry-run] 草稿已写到 data/_drafts/，未落正式区")
        audit_log(topic_id, topic_desc, queries, raw, text, [a.get("id", "?") for a in accepted], dropped)
        return 0
    if not accepted:
# 本轮无新增属于正常（非新闻类，多轮空跑），不骚扰用户
        audit_log(topic_id, topic_desc, queries, raw, text, [], dropped)
        return 0
    for nm in accepted:
        (DATA / f"{nm['id']}.json").write_text(
            json.dumps(nm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"      + {nm['id']} — {nm['name']}")
    audit_log(topic_id, topic_desc, queries, raw, text, accepted, dropped)
    if args.no_publish:
        # 并发采集模式：只写 data，站点重建/发布由统一阶段执行
        print(f"[ok] 采集完成（--no-publish，未重建站点）：+{len(accepted)} 条 × {topic_id}")
        return 0

    print("[5/5] 重建站点…")
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_site.py")],
                       capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print("[err] generate_site 失败:\n", r.stderr[-800:])
        _notify_fail(f"新增 {len(accepted)} 条但重建站点失败· 选题「{topic_desc}」· stderr={r.stderr[-200:]}")
        audit_log(topic_id, topic_desc, queries, raw, text, accepted, dropped)
        return 1
    # 同步导出 markdown 文档版（与 site 同源，避免漂移）
    rm = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_md.py")],
                        capture_output=True, text=True, timeout=300)
    if rm.returncode != 0:
        print("[warn] generate_md 失败（不影响站点）:\n", rm.stderr[-400:])
    # 自动发布到 GitHub 公开仓（干净快照：只 data(无bak)/markdown/scripts，推 deploy key）
    pub = subprocess.run([str(ROOT / "scripts" / "publish.sh")],
                         capture_output=True, text=True, timeout=120)
    if pub.returncode != 0:
        print("[warn] publish 到公开仓失败（不影响本站）:\n", pub.stderr[-400:])
    subprocess.run(["git", "-C", str(ROOT), "add", "-A", "data/", "site/", "markdown/"],
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(ROOT), "-c", "user.email=hermes@biz",
                    "-c", "user.name=biz-collect", "commit", "-qm",
                    f"collect: {topic_id} +{len(accepted)} models"],
                   capture_output=True, text=True)
    print(f"[ok] 本轮新增 {len(accepted)} 条 → http://biz.saaaai.com")
    names = "、".join(nm["name"] for nm in accepted[:3])
    notify(f"✅ 选题「{topic_desc}」新增 {len(accepted)} 条 · {names}{'…' if len(accepted)>3 else ''} → biz.saaaai.com")
    _notify_success()
    audit_log(topic_id, topic_desc, queries, raw, text, accepted, dropped)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
