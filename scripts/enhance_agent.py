#!/usr/bin/env python3
"""enhance_agent.py — 一次性补全 21 条薄 agent 条目（2026-08-13 用户指令：内容是少了，
提升质量、丰富内容。21 条老的用户亲自跑，hermes 继续跑新的）。
用法: python3 /home/ubuntu/biz-research/scripts/enhance_agent.py
行为: 对每条 搜索新素材 → LLM 按增强标准重写（保持 id/name/type）→ normalize
      → quality_gate（含 sources 探活）→ 备份 .bak → 覆盖写。任一闸不过保留原文件。
"""
import json
import sys
from pathlib import Path
ROOT = Path("/home/ubuntu/biz-research")
sys.path.insert(0, str(ROOT / "scripts"))
from collect import (  # noqa: E402 复用生产采集链（search/LLM/normalize/质量闸）
    search, normalize, quality_gate, LLM_INSTRUCTIONS_BY_KIND,
    call_direct_chat_completions_model,
)
DATA = ROOT / "data"

DSL = "用简体中文，数字用具体数值（禁'很多/较多/高'），每一段要有操作细节、工具名、流程顺序或收入/成本实数。"

# 21 条薄 agent 条目（ai-n8n-affiliate-content-cluster-monthly-4500 达标，跳过）
IDS = [
    "ai-digital-anchor-matrix-factory",
    "ai-ebook-kdp-self-publishing-pipeline",
    "ai-etsy-pod-zero-inventory-design-automation",
    "ai-foreign-trade-agent-outsourcing-commission",
    "ai-ghostwriting-agency",
    "ai-linkedin-personal-brand-operation",
    "ai-long-video-clipping-matrix-distribution",
    "ai-micro-saas-matrix-marc-lou",
    "ai-receptionist-b2b-inbound-phone-outsource",
    "ai-renovation-outbound-lead-grading-service",
    "ai-substack-newsletter-agent-monetization",
    "ai-voice-clone-audiobook-narration",
    "coze-course-knowledge-payment-agent",
    "faceless-youtube-ai",
    "foreign-trade-whatsapp-ai-agent-service",
    "n8n-aitoearn-multichannel-content-agency",
    "n8n-dify-custom-workflow-resale",
    "n8n-openai-cold-email-sdr-system",
    "reddit-lead-mining",
    "tiktok-shop-ai-affiliate-picking-agent",
    "wechat-enterprise-ai-private-domain-funnel",
]

_FALLBACK_CHAIN = [
    ("cliproxyapi", "z-ai/glm-5.2", 600),   # 主链 GLM-5.2（补全 prompt 大，输出长更稳）
    ("cliproxyapi", "openai/gpt-oss-120b", 300),
    ("cliproxyapi", "stepfun-ai/step-3.7-flash", 240),
]


def _parse(text: str) -> list | None:
    """容错解析 LLM 输出。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, list) else None
    except Exception:
        pass
    import re
    m = re.search(r"\[\s*\{.*?\}\s*\]", text, re.S)
    if not m:
        return None
    seg = m.group(0)
    try:
        return json.loads(seg)
    except Exception:
        for cut in range(len(seg), 0, -1):
            if seg[cut - 1] == "]":
                try:
                    return json.loads(seg[:cut])
                except Exception:
                    continue
    return None


def _llm(prompt: str, instructions: str) -> list | None:
    for prov, model, to in _FALLBACK_CHAIN:
        try:
            text, _ = call_direct_chat_completions_model(
                prompt=prompt, instructions=instructions,
                provider_key=prov, model=model,
                max_output_tokens=8000, timeout=to)
            if text.strip():
                cand = _parse(text)
                if cand:
                    return cand
        except Exception as e:
            print(f"      [llm {model} 失败] {e}")
    return None


def _queries(name: str) -> list[str]:
    return [f"{name} AI 赚钱 案例 收入 工作流",
            f"{name} 副业 变现 自动化 工具 步骤",
            f"{name} indie hacker AI agent 收入 workflow"]


def enhance(m: dict) -> dict:
    kind = "agent"
    oid = m["id"]
    report = {"id": oid, "status": "ok", "before": {}, "after": {}}
    for k in ("workflow", "setup", "revenue", "cost", "time", "entry",
              "tools", "keys", "risks", "example", "sources"):
        v = m.get(k)
        if isinstance(v, list):
            report["before"][k] = len(v)
        elif isinstance(v, str):
            report["before"][k] = len(v)

    # 1. 搜索新素材
    raw: list = []
    for q in _queries(m.get("name", "")):
        try:
            raw.extend(search(q))
        except Exception:
            pass
    s_ctx = json.dumps(raw, ensure_ascii=False)[:8000] if raw else "(无搜索结果，用已有内容扩展)"

    # 2. 组装增强 prompt：现有条目 + 搜索结果 → LLM 重写（保持 id/name/type/industry/region/scale/channel）
    old_json = json.dumps(m, ensure_ascii=False, indent=1)
    prompt = (
        f"这是「AI实干家」板块一条现有条目，内容太少太单薄，需要你按新标准重写丰富：\n"
        f"=== 现有条目 ===\n{old_json}\n\n"
        f"=== 补充搜索素材 ===\n{s_ctx}\n\n"
        f"重写要求：\n"
        f"1) 保持 id、name、type、industry、region、scale、channel 原值不变；\n"
        f"2) 每个文字字段（workflow/setup/revenue/cost/time/entry/y2026_hot）扩写到至少 3-5 行，"
        f"含具体工具名、操作步骤、数字（收入数字/成本数字/时间投入/转化率）；\n"
        f"3) tools 至少 4 个具体工具名；keys 至少 4 条一句话成功关键；"
        f"risks 至少 3 条风险；example 至少 3 个真实案例（每个 ≥60 字，含名称+数字）；\n"
        f"4) sources 至少 4 个真实 URL（从搜索素材挑，禁编造）；\n"
        f"5) 只输出单条 JSON（数组包 1 个对象），禁解释文字；\n"
        f"6) {DSL}"
    )
    instructions = LLM_INSTRUCTIONS_BY_KIND.get("agent", "")
    cands = _llm(prompt, instructions)
    if not cands:
        report["status"] = "llm_fail"
        return report
    cand = cands[0] if isinstance(cands, list) else cands

    # 保留身份字段 + 合并 sources
    cand["id"] = oid
    cand["name"] = m.get("name", "")
    cand["type"] = "agent"
    for k in ("industry", "region", "scale", "channel"):
        cand[k] = m.get(k, "")
    old_src = [u for u in m.get("sources", []) if isinstance(u, str)]
    new_src = [u for u in cand.get("sources", []) if isinstance(u, str)]
    seen, merged = set(), []
    for u in old_src + new_src:
        if u not in seen:
            seen.add(u)
            merged.append(u)
    cand["sources"] = merged

    # 3. normalize + quality_gate
    norm = normalize(cand, kind)
    if norm is None:
        report["status"] = "normalize_fail"
        return report
    if not quality_gate(norm, kind):
        report["status"] = "quality_gate_fail"
        return report

    # 4. 备份 → 覆盖
    fp = DATA / f"{oid}.json"
    bak = DATA / f"{oid}.json.bak-20260813"
    if not bak.exists():
        bak.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    fp.write_text(json.dumps(norm, ensure_ascii=False, indent=1), encoding="utf-8")

    for k in ("workflow", "setup", "revenue", "cost", "time", "entry",
              "tools", "keys", "risks", "example", "sources"):
        v = norm.get(k)
        if isinstance(v, list):
            report["after"][k] = len(v)
        elif isinstance(v, str):
            report["after"][k] = len(v)
    return report


def main() -> int:
    ids = sys.argv[1:] or IDS
    print(f"待补全 {len(ids)} 条 agent 条目: {ids}")
    results = []
    for oid in ids:
        fp = DATA / f"{oid}.json"
        if not fp.exists():
            print(f"[skip] {oid} 文件不存在")
            continue
        m = json.loads(fp.read_text(encoding="utf-8"))
        print(f"==> 补全 {oid}")
        r = enhance(m)
        results.append(r)
        print(f"    状态: {r['status']}")
        for k in r["before"]:
            a = r["after"].get(k, "-")
            print(f"      {k}: {r['before'][k]} → {a}")
    ok = [r for r in results if r["status"] == "ok"]
    print(f"\n完成: {len(ok)}/{len(results)} 成功")
    for r in results:
        if r["status"] != "ok":
            print(f"  ✗ {r['id']}: {r['status']}")
    return 0 if not ids or True else 1


if __name__ == "__main__":
    sys.exit(main())