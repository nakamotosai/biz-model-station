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

# 2026-08-09 撤限：默认不设上限，持续采集（用户明令撤掉 500 上限；--limit N 可覆盖，0=禁用）
DEFAULT_LIMIT = 0
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
    "agent": ["id", "name", "industry", "region", "scale", "channel", "workflow", "setup", "tools", "revenue", "cost", "time", "entry", "keys", "risks", "example", "sources"],
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
    "2) 每条字段必填：id(英文短横线slug)、name(≤40字中文名)、industry(只能从这14个里选一个：AI/大模型 / SaaS/企业软件 / 云计算 / 金融科技 / 内容/创作者经济 / 电商/零售 / 本地生活 / 餐饮/茶饮 / 教育/知识付费 / 医疗/养老 / 营销/广告 / 旅游 / 宠物 / 其他；必须按条目的业务落点推断（如AI+风控→金融科技、AI+内容创作→内容/创作者经济、AI+获客→营销/广告），禁偷懒一律写「其他」，确实无合适类才写「其他」，禁自创新词)、"
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
    "milestones(数组≥5·每项含 time/stage/outcome(失败|拐点|转折|PMF|增长)/detail·每项detail≥60字且含具体年份营收/人物/事件等事实·禁『取得进展』『遇到技术问题』类空话·至少2个失败或拐点)、"
    "turning_points(纯字符串数组≥3·每个元素一句话·禁止对象)、"
    "failures(纯字符串数组≥3·每个元素一句话·禁止对象)、"
    "keys(纯字符串数组≥4·每个元素一句话)、lessons(纯字符串数组≥4·每个元素一句话)、"
    "metrics(对象≥5键·核心数据如ARR/营收/毛利/付费率/团队规模/融资额/市值/门店数/用户数等·每键必带具体数字·禁『未披露』『数十亿』类虚数·至少3键带真实可查数字·禁整整5键全空)、"
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
    "industry(14大类同model，按业务落点推断禁偷懒写其他)、region(同model)、scale(灰产或小企)、channel(同model)、"
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
LLM_INSTRUCTIONS_AGENT = (
    "你是「商业模式情报站」AI实干家板块的调研编辑。根据用户搜索结果，"
    "提炼 1 条真实、可验证的个人AI变现系统条目（type=\"agent\"）。\n"
    "硬性要求：\n"
    "1) 只输出一个 JSON 数组（单条），不要解释文字/代码块标记；\n"
    "2) 每条必含字段：type=\"agent\"、id(英文slug)、name(≤40字·含收入金额吸引点击)、"
    "industry(14大类同model，按业务落点推断禁偷懒写其他)、region(同model)、scale(个人|小企)、channel(线上)、"
    "y2026_hot(为何2026值得看·2-3行)、"
    "workflow(工作流一句话描述·每天怎么跑·输入什么输出什么·2-3行)、"
    "setup(搭建需要什么·技术能力/工具/时间·2-3行)、"
    "tools(数组≥2·必需工具)、"
    "revenue(收入·多少/月·含具体数字)、"
    "cost(成本·工具订阅/API费用·1-2行)、"
    "time(每天/每周投入时间)、"
    "entry(新手怎么入行·第一步做什么·2-3行)、"
    "keys(数组≥2·成功关键)、risks(数组≥1·风险)、"
    "example(数组≥1·真实案例带名称和数字)、"
    "sources(数组≥2真实URL·从搜索结果挑·禁编造)；\n"
    "灵魂：系统可复利+人类做裁判+AI接触真实世界，禁编造；\n"
    + _COMMON_TAIL.replace("5) 与已有条目", "5) 与已有条目（agent版）")
)

LLM_INSTRUCTIONS_BY_KIND = {
    "model": LLM_INSTRUCTIONS_MODEL,
    "journey": LLM_INSTRUCTIONS_JOURNEY,
    "scam": LLM_INSTRUCTIONS_SCAM,
    "agent": LLM_INSTRUCTIONS_AGENT,
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


def search(query: str, engine: str = "auto") -> list[dict]:
    """搜 8091 search-mcp。engine=auto（默认多引擎链）| grok | exa | searxng | duckduckgo。
    2026-08-17 纪律化：client=biz-collect 上报审计；auto 链空结果 → 显式 searxng 第二通道重试（双引擎）。"""
    init = mcp_call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                     "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                "clientInfo": {"name": "biz-collect", "version": "1.0"}}})
    sid = init.get("sid")
    if not sid:
        return []
    results = _mcp_search(query, engine, sid)
    if not results and engine == "auto":
        results = _mcp_search(query, "searxng", sid)
    return results


def _mcp_search(query: str, engine: str, sid: str) -> list[dict]:
    res = mcp_call({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": "search",
                               "arguments": {"query": query, "synthesize": False,
                                             "engine": engine, "client": "biz-collect"}}}, sid)
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


def _count_online() -> dict[str, int]:
    """扫 data/ 各板块已落盘条目数，返 {model,journey,scam,agent}。
    2026-08-14 修：agent 板块加入 topics.json 后未在此登记 → online.get('agent')=0 恒最小 →
    agent 永远被优先选（动态均衡失效，其他板块停摆）。"""
    counts = {"model": 0, "journey": 0, "scam": 0, "agent": 0}
    for p in DATA.glob("*.json"):
        if p.name in ("topics.json", "index.json") or p.name.startswith("."):
            continue
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        k = m.get("type", "model")
        if k in counts:
            counts[k] += 1
    return counts

def load_topic() -> tuple[str, str, str]:
    """动态均衡选题，返回 (topic_id, topic_desc, kind)。kind 缺省=model。

    2026-08-09 用户指令：固化轮盘 _QUOTA 废止，改「扫三池现有在线条目数，选最少的板块采；
    三池同等则随机」。三板块自动追平后长期均衡无限跑。池不够时先补池再选（见 _replenish_pool）。
    """
    import random
    state = {}
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    topics = json.loads((DATA / "topics.json").read_text(encoding="utf-8"))["topics"]
    by_kind: dict = {}
    for t in topics:
        by_kind.setdefault(t.get("kind", "model"), []).append(t)
    # 池不够先补（三板块都补，去重供复用）
    by_kind = _replenish_if_needed(by_kind)
    # 动态均衡：扫现有在线条目数，选最少板块；同等则随机
    online = _count_online()
    produced = _produced_counts(state)
    # 板块可选性（2026-08-14）：仅「存在未产满 topic」的板块可采。全产满板块不可选——
    # 否则 fresh 为空时绕回旧坑继续换皮（etsy 2 天 8 条实证）。
    avail = {k: v for k, v in by_kind.items()
             if v and any(produced.get(t.get("id", ""), 0) < _TOPIC_CAP for t in v)}
    if not avail:
        # 全部板块产满且补池（已在 _replenish_if_needed 尝试）也未增加未产满 topic：
        # 本轮无可采新话题，跳过（不绕回旧坑换皮）
        raise RuntimeError("所有板块 topic 均已产满且补池无新话题，本轮无可采选题")
    online_in_avail = {k: online.get(k, 0) for k in avail}
    min_count = min(online_in_avail.values())
    candidates = [k for k, c in online_in_avail.items() if c == min_count]
    kind = random.choice(candidates)
    pool = avail[kind]
    # 2026-08-14 修正（用户拍板）：fresh 判定改用 state.produced 计数——原用
    # `t.id not in ids_online`（topic id vs 落盘文件 id 两套命名体系永不相等 → fresh 永真 →
    # 每轮无限换皮重采，agent 35 topic 平均 7 条）。现在「该 topic 已产出 < _TOPIC_CAP 条」才算 fresh。
    fresh = [t for t in pool if produced.get(t.get("id", ""), 0) < _TOPIC_CAP]
    if fresh:
        pool = fresh
    # 旧版全局 idx 迁移：旧 idx 即 model 池位置（journey/scam 追加在末尾）
    if "idx_model" not in state and "idx" in state:
        state["idx_model"] = state["idx"] % max(len(by_kind.get("model", [1])), 1)
    idx = state.get("idx_%s" % kind, 0) % max(len(pool), 1)
    topic = pool[idx]
    state["idx_%s" % kind] = idx + 1
    state["round"] = state.get("round", 0) + 1
    state["last_run"] = datetime.now().isoformat(timespec="seconds")
    state["last_kind"] = kind
    state["last_topic_id"] = topic["id"]
    state["last_online"] = online
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    return topic["id"], topic["desc"], topic.get("kind", "model")


def _rollback_topic(kind: str) -> None:
    """2026-08-09 修正（P1-4）：全拒/空收轮回滚 idx——失败轮不再永久消耗 topic slot。
    读 state，若 last_kind 匹配且 idx>0，回退 1，使下轮重试同一选题（质量差≠基建问题，值得重试）。
    2026-08-12 补丁：连续回滚达 MAX_RETRIES 次则不再回滚（防 agent 等新板块同 topic 死循环）。"""
    _MAX_RETRIES = 3
    try:
        if not STATE_PATH.exists():
            return
        st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(st, dict):
            return
        if st.get("last_kind") != kind:
            return
        # 连续回滚计数
        retry_key = "retry_%s" % kind
        retries = int(st.get(retry_key, 0))
        if retries >= _MAX_RETRIES:
            # 超限：不再回滚，下一轮进新 topic
            st[retry_key] = 0
            STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
            return
        k = "idx_%s" % kind
        cur = int(st.get(k, 0))
        if cur > 0:
            st[k] = cur - 1
            st[retry_key] = retries + 1
            STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass

# ── 选题池自动补充机制（2026-08-09 用户指令：池不够要自动搜索新话题补进去，去重供复用，三板块都补）
_POOL_MIN = 25  # 池剩未采(batch)条数低于此则补；batch = 池里「已产出 < _TOPIC_CAP」的 topic 数（2026-08-14 改，见 _replenish_if_needed）
_POOL_REPLENISH_BATCH = 15  # 每次补池目标新增条数
_TOPIC_CAP = 4  # 2026-08-14（用户拍板）：每 topic 产出上限。fresh 判定 = 该 topic 已产出 < cap；达 cap 不再选（防换皮无限产出）
_TOPIC_NAME_DUP = 0.55  # 2026-08-14：同 topic 内 name 相似度闸（换皮标题实测两两最高 0.58；跨 topic 不受此闸影响）
# 2026-08-14（用户「更高质量目标搜索与语义去重」）：补池三硬闸
_TOPIC_DESC_DUP = 0.50   # 补池候选 desc 与池内已有 desc 相似 ≥ 此值拒（实测池内近义对 0.48-0.75，正常 <0.40）
_TOPIC_CARD_DUP = 0.70   # 候选 desc 与已落盘卡 name 相似 ≥ 此值拒（该主题已做过卡，不重复进池）
_TOPIC_QUERY_SCORE = 0.5 # 补池搜索结果 score 下限（MCP search 返回质量分，低分结果不喂 LLM）
# 补池候选 desc 空泛词（去停用词后实义太短 = 空泛线索，拒）
_TOPIC_BAN_TOKENS = ("ai", "aigc", "赚钱", "模式", "平台", "系统", "服务", "行业", "变现", "自动化",
                     "工作流", "收益", "副业", "案例", "工具", "应用", "方案", "2026", "生意",
                     "玩法", "风口", "赛道", "项目", "agent", "llm", "数字人", "网红", "直播")
_TOPIC_MIN_SUBSTANCE = 4  # desc 去空泛词后剩余字符数下限

_REPLENISH_INSTR = {
    "model": (
        "你是商业模式情报站的选题编辑。给出 15 个 2026 年值得关注的「商业模式」全新选题方向，"
        "禁与已给清单重复或近义换皮。每条一行 JSON：{id,desc}，id=英文slug短横线，"
        "desc=一句话行业线索（例『AI Agent 代运营/外包服务 2026 新形态』『跨境供应链金融 SaaS』），"
        "具体到细分赛道+热门变现路径，禁空泛只写『AI』『电商』。只输出 [{id,desc},...] JSON 数组。"
    ),
    "journey": (
        "你是商业模式情报站发家路径板块的选题编辑。给出 15 个 2026 年值得拆解发家历程的真实公司，"
        "优先高知名度+中文资料充足者（中国大公司/上市企业/全球知名独角兽均可），禁与已给清单重复。"
        "每条一行 JSON：{id,desc}，id=英文slug短横线，desc=一句话线索（例『星巴克——咖啡帝国如何从西雅图一家店扩张全球』『Shein——柔性供应链快时尚颠覆者』）。"
        "只输出 [{id,desc},...] JSON 数组。"
    ),
    "agent": (
        "你是商业模式情报站AI实干家板块的选题编辑。给出 15 个 2026 年赚钱的AI实干家系统选题，"
        "个人/小团队用AI搭建可重复运行的赚钱系统，禁与已给清单重复。每条一行JSON：{id,desc}，id=英文slug，"
        "desc=一句话线索（例『AI代写经纪：个人品牌内容代运营』『不露脸YouTube频道AI自动化』『Reddit情报→SaaS线索挖掘』）。"
        "只输出 [{id,desc},...] JSON 数组。"
    ),
    "scam": (
        "你是商业模式情报站避坑指南板块的选题编辑。给出 15 个 2026 年新型骗局/灰产选题，"
        "优先近期高发且能起底讲解的（AI 类、跨境、加密、直播带货、养老金融等），禁与已给清单重复。"
        "每条一行 JSON：{id,desc}，id=英文slug短横线，desc=一句话线索（例『AI 换脸视频勒索骗局』『直播带货虚假发货卷款跑路』）。"
        "只输出 [{id,desc},...] JSON 数组。"
    ),
}

# 板块对应的「搜新线索」query 模板（复用 search MCP）
# 2026-08-14：每板块 2→4 路（用户拍板「拓宽思路搜索更多话题」）——覆盖更细分赛道，避免题材面收敛
# 2026-08-14 二次：每板块 4 固定 → 12 路池 + 每轮随机抽 _POOL_QUERY_BREADTH 路（单次耗时不变，
#   但轮间组合不同 → 话题面持续扩散，不会固定收敛到同一批 query 轮回，防止题材跑完）
_REPLENISH_QUERIES = {
    "model": ['2026 新兴商业模式 赛道 案例 盈利', '2026 年创业风口 商业模式 新形态 盈利路径',
              '2026 蓝海市场 细分行业 怎么赚钱 案例', '2026 传统行业数字化 转型 盈利模式 新玩法',
              '2026 订阅制 会员制 商业模式 案例 盈利', '2026 出海 跨境电商 本地化 商业模式 案例',
              '2026 平台经济 双边市场 中介 佣金 商业模式', '2026 新消费 细分品牌 DTC 直营 盈利模式',
              '2026 ToB SaaS 工具 服务 订阅 盈利 案例', '2026 硬件软件 服务化 商业模式 案例',
              '2026 本地生活 民生服务 数字化 商业 机会', '2026 回收 二手 循环经济 商业模式 赚钱'],
    "journey": ['2026 知名企业 发家史 初创失败 上市 转折', '2026 独角兽 创业历程 创始人 发展 转型 失败',
                '2026 白手起家 草根创业 逆袭 案例 复盘', '2026 传统品牌 第二增长曲线 转型 成功 故事',
                '2026 海外 DTC 品牌 创业故事 增长 复盘', '2026 独立开发者 一人公司 创业 历程 收入 复盘',
                '2026 内容创作者 网红 商业化 转型 创业 故事', '2026 家族企业 接班 转型 成败 案例',
                '2026 大厂 离职 创业 失败 教训 复盘', '2026 小众行业 隐形冠军 创业 历程 案例',
                '2026 出海品牌 全球化 创业 历程 里程碑', '2026 跨界转型 传统老板 拥抱新业态 案例'],
    "scam": ['2026 最新骗局 起底 官方警示 案例', '2026 新型诈骗 民警 提醒 灰产 打击',
             '2026 电信诈骗 养老诈骗 AI诈骗 新手法 曝光', '2026 骗局揭秘 上当 维权 官方通报 案例',
             '2026 投资理财 诈骗 荐股 杀猪盘 起底', '2026 刷单 兼职 诈骗 套路 曝光 案例',
             '2026 虚拟货币 数字藏品 诈骗 骗局 曝光', '2026 加盟 招商 骗局 起底 维权 案例',
             '2026 求职 培训贷 骗局 曝光 官方提醒', '2026 保健品 养生 骗局 老年人 起底 案例',
             '2026 冒充 公检法 客服 退款 诈骗 手法', '2026 博彩 跑分 帮信 诈骗 灰产 案例'],
    "agent": ['2026 AI 赚钱 个人 副业 系统 工作流 收入', '2026 AI agent 变现 自动化 代写 获客 案例',
              '2026 一人公司 AI工具 自动化 被动收入 案例', '2026 数字人 内容自动化 跨境 独立站 变现 系统',
              '2026 AI 绘画 设计 变现 接单 副业 案例', '2026 AI 编程 接单 外包 副业 收入 流程',
              '2026 AI 写作 自媒体 内容矩阵 变现 案例', '2026 AI 视频 剪辑 批量 制作 变现 副业',
              '2026 AI 客服 私域 运营 自动化 变现 案例', '2026 AI 数据分析 电商 选品 自动化 副业',
              '2026 AI 音频 播客 配音 TTS 变现 副业', '2026 AI 教育 培训 知识付费 自动化 系统'],
}
# 单次补池实际执行的路数（从上面池里随机抽）——保持每次 4 路耗时不变
_POOL_QUERY_BREADTH = 4


def _replenish_pool(kind: str, by_kind: dict) -> list[dict]:
    """对一个板块搜新话题→LLM 提炼→去重→返回新增候选 [{id,desc,kind}]。

    2026-08-14（用户「更高质量目标搜索与语义去重」）：
    - 搜索结果：score ≥ _TOPIC_QUERY_SCORE 过滤 + URL 去重 + 标题非空（低质量结果不喂 LLM）
    - LLM prompt：注入池内已有 id:desc 对（此前只注入 id，LLM 看不到语义 → 必近义换皮）
    - 代码硬闸：id 去重 + desc 与池内已有 desc 相似 ≥0.50 拒 + desc 与已落盘卡 name 相似 ≥0.70 拒
      + desc 空泛词过滤（去停用词后实义 <4 字符拒）
    """
    queries = _REPLENISH_QUERIES.get(kind, _REPLENISH_QUERIES["model"])
    # 2026-08-14 二次：从 12 路池随机抽 4 路——轮间组合不同，话题面持续扩散防题材跑完
    import random
    queries = random.sample(queries, min(_POOL_QUERY_BREADTH, len(queries)))
    seen_urls: set[str] = set()
    raw: list[dict] = []
    for q in queries:
        try:
            for r in search(q):
                if not isinstance(r, dict):
                    continue
                title = str(r.get("title", "")).strip()
                url = str(r.get("url", "")).strip()
                if not title or not url or url in seen_urls:
                    continue
                try:
                    sc = float(r.get("score", 0) or 0)
                except (TypeError, ValueError):
                    sc = 0.0
                if sc < _TOPIC_QUERY_SCORE:
                    continue
                seen_urls.add(url)
                raw.append(r)
        except Exception:
            pass
    if not raw:
        return []
    instr = _REPLENISH_INSTR.get(kind, _REPLENISH_INSTR["model"])
    # 已有 id+desc 清单（池中），供 LLM 语义去重（禁近义换皮）
    existing_notes = sorted({f"{t.get('id','')}: {t.get('desc','')}" for t in by_kind.get(kind, [])})
    existing_note = existing_notes[:_POOL_REPLENISH_BATCH * 20]  # 池大截前 300
    prompt = (f"搜索结果摘要：\n{json.dumps(raw, ensure_ascii=False)[:8000]}\n\n"
              f"已给选题 id: 描述 清单（严禁重复或近义换皮，desc 必须与下面清单语义可区分）:\n{chr(10).join(existing_note)}\n\n"
              f"{instr}\n\n"
              f"【硬性要求】直接输出 JSON 数组，首字符必须是 [，禁止任何分析/思考/解释/编号文字；"
              f"格式为 [{{\"id\":\"scam-xxx\",\"desc\":\"一句话线索\"}},...] 这样。")
    text = ""
    for _provider, _model, _timeout in [
        # 2026-08-09 对齐 hermes 全局链（nvidia/vps-us 系）：glm-5.2 → gpt-oss-120b → step-3.7
        # glm 首位：补池=快任务（200~300t JSON），reasoning 模型（120b）会拖慢；切片解析兜底 glm 思考链
        ("cliproxyapi", "z-ai/glm-5.2", 300),
        ("cliproxyapi", "openai/gpt-oss-120b", 200),
        ("cliproxyapi", "stepfun-ai/step-3.7-flash", 200),
    ]:
        try:
            text, _ = call_direct_chat_completions_model(
                prompt=prompt, instructions=instr, provider_key=_provider,
                model=_model, max_output_tokens=4000, timeout=_timeout)
            if text.strip():
                break
        except Exception:
            continue
    if not text.strip():
        return []
    # 解析 LLM 输出为 [{id,desc},...]：优先整体 json.loads；否则取首个 [ 到末个 ] 的切片
    # （glm 常前置「1. 分析请求…」思考链，纯 slice 更稳，零 regex 脆点）
    cands = None
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean)
    try:
        j = json.loads(clean)
        if isinstance(j, list):
            cands = j
    except Exception:
        s = clean[clean.find("["): clean.rfind("]") + 1]
        if s.startswith("[") and s.endswith("]"):
            try:
                cands = json.loads(s)
                if not isinstance(cands, list):
                    cands = None
            except Exception:
                cands = None
    # 查重：池中已 id + 已落盘 data/ id 集合
    ids_in_pool = {t.get("id","") for t in by_kind.get(kind, [])}
    existing = existing_records()
    existing_ids = ids_in_pool | existing["ids"]
    # 池内已有 desc 归一化清单（供候选 desc 近义硬闸）
    pool_descs = [_norm_name(t.get("desc","")) for t in by_kind.get(kind, []) if t.get("desc")]
    added: list[dict] = []
    for c in (cands or []):
        if not isinstance(c, dict): continue
        cid = c.get("id","")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", cid) or cid in existing_ids: continue
        desc = str(c.get("desc","")).strip()
        if len(desc) < 6 or len(desc) > 120: continue
        # 空泛词闸：去停用词后实义过短 = 空泛线索，拒
        dnorm = _norm_name(desc)
        substance = dnorm
        for tok in _TOPIC_BAN_TOKENS:
            substance = substance.replace(tok, "")
        if len(substance) < _TOPIC_MIN_SUBSTANCE:
            continue
        # desc 与池内已有 desc 近义硬闸（≥0.50 拒，防 LLM 换皮重提）
        if dnorm and pool_descs:
            if any(difflib.SequenceMatcher(None, dnorm, pd).ratio() >= _TOPIC_DESC_DUP
                   for pd in pool_descs if pd):
                continue
        # 与已落盘卡 name 高度重合（≥0.70 = 该主题已做过卡，不重复进池）
        if dnorm and existing["names"]:
            if any(difflib.SequenceMatcher(None, dnorm, en).ratio() >= _TOPIC_CARD_DUP
                   for en in existing["names"] if en):
                continue
        added.append({"id": cid, "desc": desc, "kind": kind})
        existing_ids.add(cid)
    return added[:_POOL_REPLENISH_BATCH]


def _produced_counts(state: dict) -> dict:
    """2026-08-14：返回 {topic_id: 已产出条数}。数据源 = 历史回填(data/.topic_produced.json) + 运行时增量(state.produced)。
    原 fresh 判定用 topic id vs 落盘文件 id（两套命名体系永不相等）→ fresh 永真 → 无限换皮。"""
    counts: dict = {}
    hist_path = DATA / ".topic_produced.json"
    try:
        if hist_path.exists():
            h = json.loads(hist_path.read_text(encoding="utf-8"))
            for tid, e in (h or {}).items():
                if isinstance(e, dict):
                    counts[tid] = int(e.get("count", 0))
                elif isinstance(e, (int, float)):
                    counts[tid] = int(e)
    except Exception:
        pass
    prod = state.get("produced", {}) if isinstance(state, dict) else {}
    for tid, e in (prod or {}).items():
        if isinstance(e, dict):
            counts[tid] = counts.get(tid, 0) + int(e.get("count", 0))
        elif isinstance(e, (int, float)):
            counts[tid] = counts.get(tid, 0) + int(e)
    return counts


def _produced_names(topic_id: str) -> list[str]:
    """2026-08-14：该 topic 已产出的卡 name 清单（历史回填 + 运行时增量），供同 topic 语义去重闸。"""
    names: list[str] = []
    hist_path = DATA / ".topic_produced.json"
    try:
        if hist_path.exists():
            h = json.loads(hist_path.read_text(encoding="utf-8"))
            e = (h or {}).get(topic_id, {})
            if isinstance(e, dict):
                names.extend(e.get("names", []) or [])
    except Exception:
        pass
    try:
        if STATE_PATH.exists():
            st = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            e = (st.get("produced", {}) or {}).get(topic_id, {})
            if isinstance(e, dict):
                names.extend(e.get("names", []) or [])
    except Exception:
        pass
    return names


def _replenish_if_needed(by_kind: dict) -> dict:
    """三池剩余未采条数低于 _POOL_MIN 则自动补。耗时但只在低谷触发，不影响采集频率体验。"""
    online = _count_online()
    state = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    produced = _produced_counts(state)
    for kind, pool in by_kind.items():
        # batch = 池中「已产出 < _TOPIC_CAP」的 topic 数（2026-08-14 改：原用
        # `id not in ids_online` 两套 id 体系永不匹配 → batch 恒 = 池大小 → 永不补池 →
        # 话题永远不够 → 只能换皮。改后池产满即补新话题。）
        batch = sum(1 for t in pool if produced.get(t.get("id", ""), 0) < _TOPIC_CAP)
        if batch >= _POOL_MIN:
            continue
        # 空池（batch==0 且 pool 空）也要补：否则板块永久停采（audit 2026-08-09 修正）
        # 补池上限保护：池已 300 条以上不再无限扩（避免一次话题太多轮采不完都搜，池冗余）
        if len(pool) >= 300 and batch >= _POOL_MIN // 2:
            continue
        print(f"[pool] 选题池 {kind} 剩未采 {batch} 条 < {_POOL_MIN}，自动补池…")
        try:
            added = _replenish_pool(kind, by_kind)
            if added:
                by_kind[kind] = by_kind.get(kind, []) + added
                # 持久化追加到 topics.json
                tp = DATA / "topics.json"
                tdata = json.loads(tp.read_text(encoding="utf-8"))
                tdata.setdefault("topics", []).extend(added)
                tp.write_text(json.dumps(tdata, ensure_ascii=False, indent=1), encoding="utf-8")
                print(f"[pool] {kind} 池补 +{len(added)} 条（去重供复用）")
        except Exception as e:
            print(f"[pool] {kind} 补池失败: {e}")
    return by_kind

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


def is_duplicate(cand: dict, ex: dict, topic_id: str = "", topic_names: list | None = None) -> tuple[bool, str]:
    """判决候选条目是否与已有重复。返回 (是否重复, 原因)。
    2026-08-14：新增同 topic 语义去重闸（换皮绕过三闸的纵深补救）——候选 name 与本 topic 已产出
    卡 name 相似度 ≥ _TOPIC_NAME_DUP 拒。仅同 topic 内部比对，跨 topic 不受影响（不误杀正常不同卡）。"""
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
    # 同 topic 语义去重闸：本 topic 已产出卡 name 相似（换皮闸，阈值低于全局 0.72）
    if cn and topic_names:
        for tn in topic_names:
            tnn = _norm_name(tn)
            if not tnn:
                continue
            r = difflib.SequenceMatcher(None, cn, tnn).ratio()
            if r >= _TOPIC_NAME_DUP:
                return True, f"同topic换皮 name 相似 {r:.2f}（topic={topic_id}）"
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
    if kind in ("journey", "scam", "agent"):
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
        if not isinstance(m.get("metrics"), dict) or len(m["metrics"]) < 5:
            return None
    # --- agent 专属校验 ---
    elif kind == "agent":
        for s_k in ("workflow", "setup", "revenue", "cost", "time", "entry"):
            if not isinstance(m.get(s_k), str) or not m[s_k].strip():
                return None
        for arr_k in ("tools", "keys", "risks", "example", "sources"):
            if not isinstance(m.get(arr_k), list) or not m.get(arr_k):
                return None
        if len(m["tools"]) < 4 or len(m["keys"]) < 4 or len(m["risks"]) < 3 or len(m["example"]) < 3:
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
    # 2026-08-13 补丁：过滤 LLM 输出污染的单字 key（你/是/商/业/模/式...共 120 个）
    for k in list(m):
        if len(k) == 1:
            del m[k]
    # journey/scam 的字符串数组字段可能被 LLM 偶发输出为对象/字典数组
    # （如 turning_points=[{time,desc}]、real_cases=[{case,detail}]），先规整回纯字符串数组再走后续闸
    _ARR_FIELDS = ("turning_points", "failures", "keys", "lessons",
                   "how_it_works", "red_flags", "real_cases", "official_alerts", "protection")
    for arr_k in _ARR_FIELDS:
        v = m.get(arr_k)
        if not isinstance(v, list):
            continue
        fixed = []
        for x in v:
            if isinstance(x, str):
                fixed.append(x)
            elif isinstance(x, dict):
                # 官方告警型 {date,agency,message,url}：拼 date agency: message
                d, ag, msg = x.get("date"), x.get("agency"), x.get("message")
                if isinstance(d, str) and d.strip() and isinstance(msg, str) and msg.strip():
                    head = d.strip()
                    if isinstance(ag, str) and ag.strip():
                        head += f" {ag.strip()}"
                    fixed.append(f"{head}：{msg.strip()}")
                    continue
                # 其余 dict：优先键序取正文（detail/desc/case/...），无正文键时取第一个非空字符串
                # 2026-08-09 修正：键集补 alert（official_alerts 常带 {date,agency,alert}，漏 alert 取到机构名/日期）
                picked = None
                for k in ("detail", "desc", "content", "text", "time", "case", "title", "name", "message", "alert", "agency", "date"):
                    if isinstance(x.get(k), str) and x[k].strip():
                        picked = x[k].strip()
                        break
                if picked is None:
                    for val in x.values():
                        if isinstance(val, str) and val.strip():
                            picked = val.strip()
                            break
                if picked is not None:
                    fixed.append(picked)
        if not fixed:
            # 规整后为空=LLM 输出结构异常（如 real_cases=[{...}] 但无任何可提取字符串），拒收
            return None
        m[arr_k] = fixed
    # 规整后复查数组长度下限（防字典数组被规整成空壳落盘 → 重建站点缺必填字段连环失败）
    if kind == "agent":
        core = sum(len(str(m.get(k, ""))) for k in ("workflow", "setup", "revenue", "entry", "tools"))
        if core < 500:
            return None
    if kind == "journey":
        core = sum(len(str(m.get(k, ""))) for k in ("milestones", "turning_points", "failures", "keys", "lessons"))
        if core < 500:
            return None
    if kind == "scam":
        if (len(m["how_it_works"]) < 3 or len(m["red_flags"]) < 3
                or len(m["real_cases"]) < 2 or len(m["official_alerts"]) < 1
                or len(m["sources"]) < 2):
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
    elif kind == "scam":
        text_fields = ["name", "industry", "region", "scale", "channel", "victims", "legal_note"]
        arr_text_fields = ("how_it_works", "red_flags", "real_cases", "official_alerts", "protection")
    else:  # agent
        text_fields = ["name", "industry", "region", "scale", "channel", "workflow", "setup", "revenue", "cost", "time", "entry"]
        arr_text_fields = ("tools", "keys", "risks", "example")
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
                   "agent": (
        "你是商业模式情报站AI实干家板块的选题编辑。给出 15 个 2026 年赚钱的AI实干家系统选题，"
        "个人/小团队用AI搭建可重复运行的赚钱系统，禁与已给清单重复。每条一行JSON：{id,desc}，id=英文slug，"
        "desc=一句话线索（例『AI代写经纪：个人品牌内容代运营』『不露脸YouTube频道AI自动化』『Reddit情报→SaaS线索挖掘』）。"
        "只输出 [{id,desc},...] JSON 数组。"
    ),
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
        # 排序：金融/营销/电商等精确域优先于宽泛 AI，防 email 含"ai"式误判
        ("金融科技", ["金融科技", "支付", "碳交易", "金融", "投资", "理财", "股票", "基金", "信贷", "保险",
                      "报税", "税务", "财务", "审计", "风控", "对账", "票据", "虚拟币", "加密货币", "挖矿",
                      "量化", "套利", "资金盘", "传销", "庞氏", "刷单", "返佣", "薅羊毛", "空气币", "ico",
                      "defi", "质押", "非法集资", "币圈", "洗钱", "假币", "冒牌交易所", "高收益"]),
        ("营销/广告", ["营销", "广告", "it服务", "it咨询", "dx咨询", "系统集成", "代运营", "it・", "自动化/流程",
                      "企业服务咨询", "seo", "推广", "获客", "文案", "引流", "商机", "线索", "落地页",
                      "landing page", "白标", "转售", "品牌", "矩阵号", "网络营销", "霸屏", "弹窗", "劫持"]),
        ("电商/零售", ["电商", "零售", "即时零售", "跨境电商", "社交电商", "数字商品", "数字服务", "消费电子",
                      "店铺", "商品", "选品", "亚马逊", "独立站", "上架", "出售", "代购", "门店", "假货",
                      "退款", "退货", "返利", "秒杀", "抢购"]),
        ("内容/创作者经济", ["内容", "创作者", "短剧", "漫画", "影视", "流媒体", "自媒体", "会员媒体", "法人媒体",
                          "会员经济/媒体", "修图", "老照片", "照片", "视频", "剪辑", "图片", "设计", "绘画",
                          "音乐", "音频", "配音", "字幕", "游戏", "3d", "ugc", "动漫", "深度伪造", "换脸",
                          "杀猪盘", "裸聊", "色情", "网红", "明星", "婚恋", "交友", "约会", "粉丝", "打赏",
                          "情感", "社交", "小红书", "抖音", "youtube", "快手"]),
        ("教育/知识付费", ["教育", "知识付费", "知识变现", "母婴", "简历", "求职", "培训", "课程", "学习", "考试",
                          "辅导", "家教", "论文", "专利", "代投", "面试", "考证", "兼职", "押金", "学费", "留学",
                          "代写", "代考", "毕业"]),
        ("本地生活", ["本地生活", "本地服务", "o2o", "到店", "房产", "租房", "中介", "家政", "维修", "搬家", "本地",
                      "外卖", "美容", "美发", "上门", "宠物服务"]),
        ("医疗/养老", ["医疗", "数字医疗", "养老", "慢病", "健身", "饮食", "健康", "养生", "心理", "康复", "营养",
                      "瘦身", "体重", "陪诊", "保健品", "药品", "医院", "看病", "体检", "社保"]),
        ("SaaS/企业软件", ["saas", "企业软件", "软件订阅", "软件投资", "定价与变现", "独立saas", "独立开发",
                          "工具软件", "效率工具", "虚拟产品", "合同", "合规", "系统", "erp", "crm", "管理系统",
                          "办公", "协作", "私有化部署", "定制开发", "订阅", "授权", "企业版"]),
        ("AI/大模型", ["大模型", "智能体", "生成式", "人工智能", "aigc", "agent", "llm", "gpt", "rag", "微调",
                      "开源软件", "半导体", "开源自建", "知识库"]),
        ("云计算", ["云计算", "云服务", "基础设施"]),
        ("餐饮/茶饮", ["餐饮", "茶饮", "咖啡", "食品加工", "餐饮供应链", "奶茶", "蛋糕", "烘焙", "零食"]),
        ("旅游", ["旅游", "体验经济", "旅行", "行程", "酒店", "民宿", "机票", "导游", "景点", "门票"]),
        ("宠物", ["宠物"]),
    ]
    ind = m.get("industry", "").strip()
    if ind in _IND_CAT and ind != "其他":
        # 已命中目录且非"其他"→直接用（LLM 给了正确分类）
        return m
    t = m.get("type", "model")
    if t in ("agent", "scam"):
        # agent/scam：未命中目录或"其他"→用名称+内容关键词反推（防 LLM 偷懒写"其他"）
        fields = ["name"]
        if t == "agent":
            fields += ["workflow", "revenue"]
        else:
            fields += ["how_it_works", "red_flags", "victims"]
        text = " ".join(str(m.get(k, "")) for k in fields).lower()
        hit = next((c for c, ks in _IND_KEYS if any(k in text for k in ks)), "其他")
        m["industry"] = hit
        return m
    # model/journey：保持原逻辑，只扫原值（内容噪声大，禁名称反推）
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
    """①来源探活：删除 404/不可达 URL，<2 条则拒收整条。

    2026-08-09 修正：串行 15s×N 探活把慢轮拉满 timeout，改 ThreadPool 并发（每 URL 仍 15s 上限，
    但 N 条来源总耗时≈15s 而非 15s×N）。"""
    urls = [u for u in (m.get("sources") or [])]
    if not urls:
        m["sources"] = []
        return False
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as ex:
        live_flags = list(ex.map(_probe_url, urls))
    live = [u for u, ok in zip(urls, live_flags) if ok]
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
    "agent": (
        "你是商业模式情报站AI实干家板块的选题编辑。给出 15 个 2026 年赚钱的AI实干家系统选题，"
        "个人/小团队用AI搭建可重复运行的赚钱系统，禁与已给清单重复。每条一行JSON：{id,desc}，id=英文slug，"
        "desc=一句话线索（例『AI代写经纪：个人品牌内容代运营』『不露脸YouTube频道AI自动化』『Reddit情报→SaaS线索挖掘』）。"
        "只输出 [{id,desc},...] JSON 数组。"
    ),
    "scam": ("victims", "legal_note", "y2026_hot"),
}
_GATE_ARR_FIELDS = {
    "model": ("keys", "risks", "example"),
    "journey": ("turning_points", "failures", "keys", "lessons"),
    "agent": (
        "你是商业模式情报站AI实干家板块的选题编辑。给出 15 个 2026 年赚钱的AI实干家系统选题，"
        "个人/小团队用AI搭建可重复运行的赚钱系统，禁与已给清单重复。每条一行JSON：{id,desc}，id=英文slug，"
        "desc=一句话线索（例『AI代写经纪：个人品牌内容代运营』『不露脸YouTube频道AI自动化』『Reddit情报→SaaS线索挖掘』）。"
        "只输出 [{id,desc},...] JSON 数组。"
    ),
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



def _diagnose_fail(m: dict, kind: str = "model") -> list[str]:
    """返回候选条目被 normalize/quality_gate 拒的具体原因列表（为修复 LLM 提供反馈）。"""
    reasons = []
    if kind == "agent":
        for s_k in ("workflow", "setup", "revenue", "cost", "time", "entry"):
            v = m.get(s_k, "")
            if not isinstance(v, str) or not v.strip():
                reasons.append(f"「{s_k}」字段为空，需要至少 1 行具体内容")
        for arr_k, min_n in (("tools", 4), ("keys", 4), ("risks", 3), ("example", 3), ("sources", 4)):
            arr = m.get(arr_k, [])
            if not isinstance(arr, list) or not arr:
                reasons.append(f"「{arr_k}」数组为空，需要至少 {min_n} 项")
            elif len(arr) < min_n:
                reasons.append(f"「{arr_k}」只有 {len(arr)} 项，需要至少 {min_n} 项")
        core = sum(len(str(m.get(k, ""))) for k in ("workflow", "setup", "revenue", "entry", "tools"))
        if core < 500:
            reasons.append(f"核心字段合计密度不足（{core} 字 < 500 字），每个字段需要至少 3-5 行详细内容")
        # 来源探活
        sources = [u for u in m.get("sources", []) if isinstance(u, str) and u.startswith(("http://", "https://"))]
        if len(sources) < 4:
            reasons.append(f"有效来源 URL 不足（{len(sources)} 个 < 4），需从搜索结果挑真实 URL")
    elif kind == "model":
        for arr_k, min_n in (("keys", 4), ("risks", 3), ("example", 3), ("sources", 4)):
            arr = m.get(arr_k, [])
            if not isinstance(arr, list) or not arr:
                reasons.append(f"「{arr_k}」数组为空，需要至少 {min_n} 项")
            elif len(arr) < min_n:
                reasons.append(f"「{arr_k}」只有 {len(arr)} 项，需要至少 {min_n} 项")
        swot = m.get("swot", {})
        for dim in ("s", "w", "o", "t"):
            items = swot.get(dim, []) if isinstance(swot, dict) else []
            if not isinstance(items, list) or len(items) < 2:
                reasons.append(f"SWOT「{dim}」只有 {len(items)} 项，需要至少 2 项（每项 ≥40 字）")
        core = sum(len(str(m.get(k, ""))) for k in ("background", "target", "revenue", "cost", "moat"))
        if core < 300:
            reasons.append(f"核心字段合计密度不足（{core} 字 < 300 字）")
    elif kind == "journey":
        ms = m.get("milestones", [])
        if not isinstance(ms, list) or len(ms) < 3:
            reasons.append(f"milestones 只有 {len(ms)} 项，需要至少 3 项（每项 detail≥60 字）")
        for arr_k, min_n in (("turning_points", 3), ("failures", 3), ("keys", 4), ("lessons", 4), ("sources", 4)):
            arr = m.get(arr_k, [])
            if not isinstance(arr, list) or not arr:
                reasons.append(f"「{arr_k}」数组为空，需要至少 {min_n} 项")
            elif len(arr) < min_n:
                reasons.append(f"「{arr_k}」只有 {len(arr)} 项，需要至少 {min_n} 项")
    elif kind == "scam":
        for arr_k, min_n in (("how_it_works", 5), ("red_flags", 5), ("real_cases", 3),
                             ("official_alerts", 3), ("protection", 4), ("sources", 4)):
            arr = m.get(arr_k, [])
            if not isinstance(arr, list) or not arr:
                reasons.append(f"「{arr_k}」数组为空，需要至少 {min_n} 项")
            elif len(arr) < min_n:
                reasons.append(f"「{arr_k}」只有 {len(arr)} 项，需要至少 {min_n} 项")
    return reasons

def quality_gate(m: dict, kind: str = "model") -> tuple[bool, str]:
    """写入前总闸：来源探活 + 病句 + 截断 + 密度（2026-08-09 加第④道根治空壳），任一不过拒收整条。

    2026-08-09 修正（P1-11）：返回 (ok, 具体闸名)——此前 473 audit 里 114 条被拒
    「质量闸：来源死链/病句/截断」统一文案，无法定位哪道闸拦的、无法调阈值。"""
    if not _gate_sources(m):
        return False, "质量闸①来源探活（URL 死链/不可达 <2 条）"
    if not _gate_text(m, kind):
        return False, "质量闸②病句/机翻特征"
    if not _gate_truncation(m, kind):
        return False, "质量闸③字段截断（…结尾）"
    if not _gate_density(m, kind):
        return False, "质量闸④内容密度不足（空壳）"
    return True, ""

# ④内容密度闸（2026-08-09 新增根治空壳）：LLM 摆烂吐一句话里程碑能过前 3 道，加密度闸拦。
# 病灶：08-08 全天 cron 产 26 条空壳（totalLen<1100、avgDetail<50、detail 全「重力与轨道控制问题」类废话）。
# 真实数据回测定阈值：126 条 journey 中 avgDetail<50 的 25/26 都是空壳（唯一漏的 elevenlabs 因 totalLen<1500 兜底）。
# journey 正常样本 avgDetail 最低 51.4（broken-shell-robot）与 52.0（atlassian），故 <50 零误伤正常条。
def _gate_density(m: dict, kind: str = "model") -> bool:
    """④内容密度闸：journey milestones detail 均值<50 或 整条 JSON 序列化<1500 字 → 拒收（根治空壳）。"""
    if kind == "journey":
        # 整条 JSON 太短直接拒（兜底 elevenlabs 这类 avgDetail 偏高但总内容极少的空壳）
        if len(json.dumps(m, ensure_ascii=False)) < 1500:
            return False
        ms = m.get("milestones", [])
        if not isinstance(ms, list) or not ms:
            return False
        details = [len(str(s.get("detail", ""))) for s in ms if isinstance(s, dict)]
        if not details or sum(details) / len(details) < 50:
            return False
    elif kind == "model":
        # model 短条本就简练（最短 470 字但有干货），core<100 才拒
        core = sum(len(str(m.get(k, ""))) for k in ("background", "target", "revenue", "cost", "moat"))
        if core < 100:
            return False
    elif kind == "agent":
        core = sum(len(str(m.get(k, ""))) for k in ("workflow", "setup", "revenue", "entry", "tools"))
        if core < 200:
            return False
    if kind == "scam":
        # scam 最短 1663 字，core<400 才拒
        core = sum(sum(len(str(x)) for x in m.get(k, [])) for k in ("how_it_works", "red_flags", "real_cases"))
        if core < 400:
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
               llm_raw: str, accepted: list, dropped: list,
               llm_provider: str = "", llm_model: str = "") -> None:
    """一轮一文件审计日志：选题/query/LLM 原始输出/accept/drop 原因，可回溯。

    2026-08-09 修正（P1-9）：记录 llmProvider/llmModel——此前成功轮无法溯源
    是哪条 fallback 链输出的，模型问题（换模型/超时）无从复盘。"""
    AUDIT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = AUDIT_DIR / f"collect-audit-{stamp}-{topic_id}.json"
    payload = {
        "at": now_iso(),
        "topic": {"id": topic_id, "desc": topic_desc},
        "queries": queries,
        "searchResults": raw[:200],
        "llmProvider": llm_provider,
        "llmModel": llm_model,
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
    elif kind == "agent":
        queries = [f"2026 {topic_desc} AI 赚钱 工作流 收入 案例",
                   f"2026 {topic_desc} 个人 副业 自动化 变现 系统"]
    elif kind == "scam":
        queries = [f"2026 {topic_desc} 骗局 坑 起底 官方提示",
                   f"2026 {topic_desc} 受骗 案例 警方 网信办 央视"]
    else:
        queries = [f"2026 商业模式 {topic_desc}", f"2026 盈利模式 案例 {topic_desc}"]
    raw = []
    raw_errors: list[str] = []
    for q in queries:
        try:
            raw.extend(search(q))
            print(f"      搜索 '{q[:40]}…' → {len(raw)} 条候选")
        except Exception as e:
            print(f"      [warn] 搜索失败: {e}")
            raw_errors.append(str(e))

    if not raw:
        # 2026-08-09 修正（P0-3）：搜索空/全失败轮不能完全静默——无 audit 无失败计数，
        # searxng 基建连续抖数天也无感知。写 audit + 递增失败计数（阈值内不 TG 骚扰，超阈值告警）。
        # 注：非新闻类板块正常空跑也走这里——audit 记录 reason=search-empty 供复盘，失败计数
        # 用 infra_noise 语义（不递增 consecutive，避免正常空跑把计数推过阈值误告警）。
        reason = "搜索无结果（query 全空/搜索失败）"
        if raw_errors:
            reason = "搜索异常：" + "; ".join(raw_errors[:2])
        print(f"[2/5] {reason}，跳过本轮")
        _notify_fail(reason, infra_noise=True)
        audit_log(topic_id, topic_desc, queries, raw, "", [], [("search-empty", reason)])
        return 0

    existing = existing_records()
    # 2026-08-09 修正（P1-5）：1500 截断只给 LLM 44/441 个已有 id，去重提示 90% 失效；
    # 全量给（440 个 slug ≈ 12KB，在 prompt 预算内），用 chunk 防单字符串过长
    ids_sorted = sorted(existing["ids"])
    existing_note = "\n".join(ids_sorted)
    # 若超长（未来条目>1500），按 id 长度分批截断并标注总数，保证 LLM 至少看到全量 id 的摘要
    if len(existing_note) > 12000:
        existing_note = existing_note[:12000] + f"\n...（共 {len(ids_sorted)} 个已有 id，截断展示）"
    prompt = (f"选题：{topic_desc}\n\n已有条目 id 清单（跳过重复/换皮，禁止换名同义重写）：\n{existing_note}\n\n"
              f"搜索结果：\n{json.dumps(raw, ensure_ascii=False)[:12000]}\n\n"
              f"直接输出 1 个合法 JSON 数组，不要任何思考过程/草稿/字段注释，全部正文字段用简体中文。")
    # 2026-08-14：注入「本 topic 已产出 name 清单」，LLM 侧拦截换皮重写（选题层语义去重）
    _tnames = _produced_names(args.topic or topic_id)
    if _tnames:
        prompt += ("\n\n⚠️ 本选题（同一 topic）已产出以下条目 name，禁止与它们语义重复/换皮改名重写"
                   f"（已有 {len(_tnames)} 条）：\n" + "\n".join(str(n) for n in _tnames[:15]) + "\n")
    instructions = LLM_INSTRUCTIONS_BY_KIND.get(kind, LLM_INSTRUCTIONS_MODEL)
    # fallback 链：主模型(glm-5.2) → 实测可用的快模型
    # 2026-08-06 12:31+ 修正：原链 hermes 写的 deepseek-ai/deepseek-v4-flash 与
    # grok-3-mini-fast 在 cliproxy 不存在（502 unknown provider）。后用户删除
    # deepseek-ai/deepseek-v4-pro（快下架）。2026-08-15 深测重排：链首 deepseek-v4-flash-free（实测秒回），
    # 其余为 2026-08-06 带凭证实测能直接出 JSON 的快模型（200 token 短测秒回）。
    # 2026-08-09 对齐 hermes 全局链（nvidia/vps-us 系）；2026-08-15 深测后重排：
    # deepseek-v4-flash-free 实测通（1.1s 秒回）→ 升主模型；glm-5.2 空响应频发 → 降 fallback 第二位
    # 120b 是 reasoning 模型，主链 max_tokens 4500/8500 已留推理预算（实测 120b 单测 2000 token 出 50 完整）
    _FALLBACK_CHAIN = [
        ("cliproxyapi", "deepseek-v4-flash-free", 240),
        ("cliproxyapi", "z-ai/glm-5.2", 240),
        ("cliproxyapi", "openai/gpt-oss-120b", 180),
        ("cliproxyapi", "nvidia/nemotron-3-super-120b-a12b", 180),
        ("cliproxyapi", "stepfun-ai/step-3.7-flash", 90),
        ("cliproxyapi", "sensenova-deepseek-v4-flash", 90),
    ]
    text = ""
    llm_errors: list[str] = []
    used_provider, used_model = "", ""
    # journey/scam 条目字段多、LLM 输出长，4500 上限曾把候选截断在思考过程（audit
    # 20260806-153120 cursor 候选 llmRaw 止于字段草稿、最终 JSON 未完成被质量闸拒）。
    # 放大到 6500 并提示直接输出 JSON（禁思考过程草稿）。
    # 2026-08-06 晚间：prompt 下限上调（journey milestones≥5/keys≥4/lessons≥4/metrics≥5键，
    # scam how_it_works≥5/red_flags≥5/cases≥3），输出更长 → 8500 防截断。
    # 2026-08-13 修复循环专用快链：跳过 glm-5.2（空响应 240s 烧时间），修复轮只给快模型
    _REPAIR_CHAIN = [
        ("cliproxyapi", "nvidia/nemotron-3-super-120b-a12b", 120),
        ("cliproxyapi", "stepfun-ai/step-3.7-flash", 60),
    ]
    max_tokens = 8500 if kind != "model" else 4500
    _primary_provider, _primary_model, _ = _FALLBACK_CHAIN[0]  # 主模型 = 链首（2026-08-15 起 deepseek-v4-flash-free）
    # 2026-08-14 修复（P1a，泛化 2026-08-15）：主模型空响应频发（glm 实测 111 次/2 天、deepseek 待观察）
    # 主模型每轮空响应白烧 240s 超时。策略：连续 ≥2 次空响应 → 本轮跳过主模型直走 fallback
    # （省 240s/轮）；fallback 成功冷却递减计数 → 自动恢复探测主模型（不永久放弃）。
    _GLM_STRIKE_FILE = DATA / ".llm_glm_strikes"
    try:
        _strikes = int(_GLM_STRIKE_FILE.read_text(encoding="utf-8").strip() or "0") if _GLM_STRIKE_FILE.exists() else 0
    except Exception:
        _strikes = 0
    if _strikes >= 2:
        _FALLBACK_CHAIN = [m for m in _FALLBACK_CHAIN if m[1] != _primary_model]
        print(f"[2/5] {_primary_model} 已连续 {_strikes} 次空响应，本轮跳过主模型直走 fallback")
    tried: set[tuple[str, str]] = set()
    _glm_hit_strike = False
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
                used_provider, used_model = _provider, _model
                break
            # 空响应：主模型空响应计一次 strike（超时内无内容）
            if _model == _primary_model:
                _glm_hit_strike = True
        except Exception as e:
            err = str(e)
            llm_errors.append(f"{_model}: {err}")
            print(f"[2/5] LLM 失败 ({_model}): {err}")
            if _model == _primary_model:
                _glm_hit_strike = True
            text = ""
            continue
    # 更新主模型连续空响应计数：主模型这次成功 → 清零；主模型空响应/失败 → +1。
    # 主模型被跳过且 fallback 成功 → 冷却递减（每轮 fallback 成功 -1，3 轮后恢复探测）。
    try:
        _next = 0
        if _glm_hit_strike:
            _next = _strikes + 1
        elif used_model == _primary_model:
            _next = 0
        else:
            _next = max(0, _strikes - 1)
        _GLM_STRIKE_FILE.write_text(str(_next), encoding="utf-8")
    except Exception:
        pass
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
            audit_log(topic_id, topic_desc, queries, raw, text, [], [("json-bad", fail_detail)], used_provider, used_model)
            return 1

    DRAFTS.mkdir(exist_ok=True)
    accepted, dropped = [], []
    for c in candidates:
        if not isinstance(c, dict):
            dropped.append((str(c)[:40], "候选非对象（LLM 输出 schema 漂移）"))
            continue
        nm = normalize(c, kind)
        if nm is None:
            # 2026-08-13 修复：失败续改——把具体原因反馈 LLM 修补后再校验，最多 3 轮
            feedback = "\n".join(_diagnose_fail(c, kind))
            repair_data = c
            repaired = False
            for _repair_round in range(3):
                repair_prompt = (f"选题：{topic_desc}\n\n已有条目 id 清单：\n{existing_note}\n"
                                 f"\n搜索结果：\n{json.dumps(raw, ensure_ascii=False)[:8000]}\n\n"
                                 f"上次候选被拒，原因如下，请修改已存在的候选而非重写，只补全不足的字段，保持已有内容不变：\n"
                                 f"{feedback}\n"
                                 f"上次候选 JSON：\n{json.dumps(repair_data, ensure_ascii=False, indent=1)}\n"
                                 f"\n直接输出 1 个合法 JSON 数组（只含修复后的单条），不要任何思考过程/草稿。")
                repair_text = ""
                repair_llm_errors = []
                for (_rp, _rm, _rt) in _REPAIR_CHAIN:
                    try:
                        repair_text, _ = call_direct_chat_completions_model(
                            prompt=repair_prompt, instructions=instructions,
                            provider_key=_rp, model=_rm,
                            max_output_tokens=max_tokens, timeout=_rt)
                        if repair_text.strip():
                            break
                    except Exception as e:
                        repair_llm_errors.append(f"{_rm}: {e}")
                        continue
                if not repair_text.strip():
                    break
                repair_parsed = _parse(repair_text)
                if not repair_parsed or not isinstance(repair_parsed, list):
                    feedback = f"修复后 JSON 解析失败\n{feedback}"
                    continue
                repair_data = repair_parsed[0]
                # 保留身份字段
                repair_data["id"] = c.get("id", repair_data.get("id", ""))
                for kk in ("name", "type", "industry", "region", "scale", "channel"):
                    repair_data[kk] = c.get(kk, repair_data.get(kk, ""))
                nm = normalize(repair_data, kind)
                if nm is not None:
                    repaired = True
                    break
                feedback = "\n".join(_diagnose_fail(repair_data, kind))
            if nm is None:
                dropped.append((c.get("id", "?"), "字段不完整/来源不足（修复" + str(_repair_round + 1) + "轮后仍不达标）"))
                continue
        qok, qwhy = quality_gate(nm, kind)
        if not qok:
            # 质量闸失败也续改（最多 2 轮）
            q_feedback = qwhy
            q_repair_data = nm
            q_repaired = False
            for _q_round in range(2):
                q_prompt = (f"选题：{topic_desc}\n\n已有条目 id 清单：\n{existing_note}\n"
                           f"\n搜索结果：\n{json.dumps(raw, ensure_ascii=False)[:8000]}\n"
                           f"\n上次候选通过了字段校验，但被质量闸拒，原因如下：\n"
                           f"{q_feedback}\n"
                           f"候选 JSON：\n{json.dumps(q_repair_data, ensure_ascii=False, indent=1)}\n"
                           f"\n请修改而非重写，只修复质量闸指出的问题，保持已有内容不变。直接输出 1 个合法 JSON 数组。")
                q_text = ""
                for (_rp, _rm, _rt) in _REPAIR_CHAIN:
                    try:
                        q_text, _ = call_direct_chat_completions_model(
                            prompt=q_prompt, instructions=instructions,
                            provider_key=_rp, model=_rm,
                            max_output_tokens=max_tokens, timeout=_rt)
                        if q_text.strip():
                            break
                    except Exception:
                        continue
                if not q_text.strip():
                    break
                q_parsed = _parse(q_text)
                if not q_parsed or not isinstance(q_parsed, list):
                    break
                q_repair_data = q_parsed[0]
                q_repair_data["id"] = nm.get("id", q_repair_data.get("id", ""))
                for kk in ("name", "type", "industry", "region", "scale", "channel"):
                    q_repair_data[kk] = nm.get(kk, q_repair_data.get(kk, ""))
                nm2 = normalize(q_repair_data, kind)
                if nm2 is None:
                    break
                qok2, qwhy2 = quality_gate(nm2, kind)
                if qok2:
                    nm = nm2
                    q_repaired = True
                    break
                q_feedback = qwhy2
            if not q_repaired:
                dropped.append((c.get("id", "?"), "质量闸:" + qwhy + "（修复后仍不达标）"))
                continue
        dup, why = is_duplicate(nm, existing, topic_id=args.topic or topic_id,
                                topic_names=_produced_names(args.topic or topic_id))
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
        audit_log(topic_id, topic_desc, queries, raw, text, [a.get("id", "?") for a in accepted], dropped, used_provider, used_model)
        return 0
    if not accepted:
# 本轮无新增属于正常（非新闻类，多轮空跑），不骚扰用户
        # 2026-08-09 修正（P1-4）：全拒（候选被质量闸拦）≠ 基建坏，选题内容差值得重试——
        # 回滚 idx 让下一轮回到该 topic（搜索空/LLM 全败的轮次不在此分支，保持推进防死循环）
        if candidates and dropped:
            _rollback_topic(kind)
        audit_log(topic_id, topic_desc, queries, raw, text, [], dropped, used_provider, used_model)
        return 0
    for nm in accepted:
        (DATA / f"{nm['id']}.json").write_text(
            json.dumps(nm, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"      + {nm['id']} — {nm['name']}")
    # 2026-08-14：落盘成功后把本轮成果记入 state.produced（fresh 判定 + 同 topic 语义去重闸数据源）
    try:
        st = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}
        if not isinstance(st, dict):
            st = {}
        prod = st.setdefault("produced", {})
        tid = args.topic or topic_id
        ent = prod.setdefault(tid, {"count": 0, "names": []})
        if not isinstance(ent, dict):
            ent = {"count": int(ent) if str(ent).isdigit() else 0, "names": []}
            prod[tid] = ent
        ent["count"] = int(ent.get("count", 0)) + len(accepted)
        ent.setdefault("names", []).extend(nm.get("name", "") for nm in accepted)
        STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception as e:
        print(f"[warn] produced 计数更新失败: {e}")
    if args.no_publish:
        # 并发采集模式：只写 data，站点重建/发布由统一阶段执行
        audit_log(topic_id, topic_desc, queries, raw, text, accepted, dropped, used_provider, used_model)
        print(f"[ok] 采集完成（--no-publish，未重建站点）：+{len(accepted)} 条 × {topic_id}")
        return 0

    print("[5/5] 重建站点…")
    # 2026-08-09 修：全量重建 240+ 页实测 5-9min，600s 恰好卡边界；放宽到 900s 防半程超时
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_site.py")],
                       capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        print("[err] generate_site 失败:\n", r.stderr[-800:])
        _notify_fail(f"新增 {len(accepted)} 条但重建站点失败· 选题「{topic_desc}」· stderr={r.stderr[-200:]}")
        audit_log(topic_id, topic_desc, queries, raw, text, accepted, dropped, used_provider, used_model)
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
        # 2026-08-09 修正（S5 P1-1）：publish 失败此前只 [warn] 无 TG——公开仓静默停更，没人知道。
        # 现在告警并记 audit（audit 保留 dirty 状态不影响后续轮）
        print("[warn] publish 到公开仓失败（不影响本站）:\n", pub.stderr[-400:])
        _notify_fail(f"publish 公开仓失败· 选题「{topic_desc}」· {pub.stderr[-150:]}")
    # 2026-08-09 修正（P2-3）：-- 与 :(exclude) 明确排除 data/_drafts——草稿不属 SSOT 正式内容
    subprocess.run(["git", "-C", str(ROOT), "add", "-A", "data/", "site/", "markdown/",
                    "--", ":(exclude)data/_drafts"],
                   capture_output=True, text=True)
    subprocess.run(["git", "-C", str(ROOT), "-c", "user.email=hermes@biz",
                    "-c", "user.name=biz-collect", "commit", "-qm",
                    f"collect: {topic_id} +{len(accepted)} models"],
                   capture_output=True, text=True)
    print(f"[ok] 本轮新增 {len(accepted)} 条 → http://biz.saaaai.com")
    names = "、".join(nm["name"] for nm in accepted[:3])
    notify(f"✅ 选题「{topic_desc}」新增 {len(accepted)} 条 · {names}{'…' if len(accepted)>3 else ''} → biz.saaaai.com")
    _notify_success()
    audit_log(topic_id, topic_desc, queries, raw, text, accepted, dropped, used_provider, used_model)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
