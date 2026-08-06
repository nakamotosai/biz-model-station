#!/usr/bin/env python3
"""enhance_existing.py — 一次性补全已上线 journey/scam 条目（2026-08-06 用户指令：
自动采集条目比手工示例薄，先补厚已上线的，流程下限已随 collect.py prompt 上调）。

用法: python3 scripts/enhance_existing.py [id...]   # 默认 7 条已知
行为: 对每条 搜索新素材 → LLM 按增强标准重写（保持 id/name/type）→ normalize
      → quality_gate（含 sources 探活）→ 备份 .bak → 覆盖写。任一闸不过保留原文件。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from collect import (  # noqa: E402 复用生产采集链（search/LLM/normalize/质量闸）
    search, normalize, quality_gate, LLM_INSTRUCTIONS_BY_KIND,
    call_direct_chat_completions_model, existing_records,
)

DATA = ROOT / "data"


def _parse(text: str) -> list | None:
    """容错解析 LLM 输出（与 collect.main 内 _parse 同逻辑）：纯 JSON / json 围栏 / 截断修复。"""
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
DEFAULT_IDS = [
    # journey
    "ai-native-cursor-ide", "ai-image-liblib-evoken-survival",
    "luobo-ai-robot", "shandianshuo",
    # scam
    "ai-data-annotation-part-time-scam", "ai-relay-station-scam",
    "fake-ai-crypto-quant-fund-scam",
]
_FALLBACK_CHAIN = [
    ("cliproxyapi", "z-ai/glm-5.2", 600),   # 补全 prompt 大（现有条目+搜索），scam 输出长更慢
    ("cliproxyapi", "deepseek-v4-flash-free", 120),
    ("cliproxyapi", "big-pickle", 120),
    ("cliproxyapi", "openai/gpt-oss-20b", 120),
    ("cliproxyapi", "stepfun-ai/step-3.7-flash", 90),
    ("cliproxyapi", "mimo-v2.5-free", 90),
]


def _queries(kind: str, name: str, desc: str = "") -> list[str]:
    if kind == "journey":
        return [f"{name} 创始人 发展历程 融资 访谈 转型",
                f"{name} 商业模式 用户增长 失败 踩坑 2026",
                f"{name} 竞争 护城河 数据 营收"]
    return [f"{name} 骗局 起底 案例 官方提示",
            f"{name} 受骗 警方 网信办 央视 警示",
            f"{name} 防范 识别 高发 2026"]


def _llm(prompt: str, instructions: str) -> list | None:
    tried: set[tuple[str, str]] = set()
    for prov, model, to in _FALLBACK_CHAIN:
        if (prov, model) in tried:
            continue
        tried.add((prov, model))
        try:
            text, _ = call_direct_chat_completions_model(
                prompt=prompt, instructions=instructions,
                provider_key=prov, model=model,
                max_output_tokens=6000, timeout=to)
            if text.strip():
                cand = _parse(text)
                if cand:
                    return cand
        except Exception as e:
            print(f"      [llm {model} 失败] {e}")
    return None


def enhance(m: dict) -> dict:
    """返回 {id, kind, before:{k:len}, after:{k:len}, status}。"""
    kind = m.get("type", "journey")
    oid = m["id"]
    report = {"id": oid, "kind": kind, "status": "skipped", "before": {}, "after": {}}
    for k in ("milestones", "turning_points", "failures", "keys", "lessons", "sources",
              "how_it_works", "red_flags", "real_cases", "official_alerts", "protection"):
        if isinstance(m.get(k), list):
            report["before"][k] = len(m[k])
    if isinstance(m.get("metrics"), dict):
        report["before"]["metrics"] = len(m["metrics"])
    report["before"]["origin"] = len(m.get("origin", ""))
    report["before"]["victims"] = len(m.get("victims", ""))

    raw: list = []
    for q in _queries(kind, m.get("name", "")):
        try:
            got = search(q)
            raw.extend(got)
            print(f"      搜索 '{q[:36]}…' → {len(got)} 条")
        except Exception as e:
            print(f"      [搜索失败] {e}")
    if not raw:
        report["status"] = "no_search_result"
        return report

    ex = existing_records()
    existing_note = "\n".join(sorted(ex["ids"]))[:1500]
    prompt = (
        f"下面有一条已上线的「{'发家路径' if kind == 'journey' else '避坑指南'}」条目，"
        f"内容偏薄需要扩展补充。\n"
        f"硬性要求：\n"
        f"1) 保持 id=\"{oid}\"、name=\"{m.get('name','')}\"、type=\"{kind}\" 完全不变；\n"
        f"2) 其余字段按板块标准写满写厚（详见 instructions），比下面现有内容更丰富详实，"
        f"可补充新的事实/数据/案例/阶段；\n"
        f"3) sources 从搜索结果里挑（可与现有来源并集），≥4 条真实 URL，禁编造；\n"
        f"4) 只输出一个合法 JSON 数组（单条），不要任何思考过程/草稿/注释。\n\n"
        f"已有条目 id 清单（跳过重复/换皮）：\n{existing_note}\n\n"
        f"现有条目 JSON：\n{json.dumps(m, ensure_ascii=False)[:3000]}\n\n"
        f"搜索结果：\n{json.dumps(raw, ensure_ascii=False)[:7000]}"
    )
    cands = _llm(prompt, LLM_INSTRUCTIONS_BY_KIND.get(kind, LLM_INSTRUCTIONS_BY_KIND["model"]))
    if not cands:
        report["status"] = "llm_failed"
        return report
    cand = cands[0] if isinstance(cands, list) else cands
    if not isinstance(cand, dict):
        report["status"] = "bad_shape"
        return report
    # 强制保留身份字段；sources 合并旧+新（去重保序）
    cand["id"] = oid
    cand["name"] = m.get("name", "")
    cand["type"] = kind
    old_src = [u for u in m.get("sources", []) if isinstance(u, str)]
    new_src = [u for u in cand.get("sources", []) if isinstance(u, str)]
    seen, merged = set(), []
    for u in old_src + new_src:
        if u not in seen:
            seen.add(u)
            merged.append(u)
    cand["sources"] = merged

    norm = normalize(cand, kind)
    if norm is None:
        report["status"] = "normalize_fail"
        print(f"      [normalize 拒] {norm}")
        return report
    if not quality_gate(norm, kind):
        from collect import _gate_sources, _gate_text, _gate_truncation, _GLITCH_RE
        src_ok = _gate_sources(dict(norm))          # 注意：会原地改 sources
        print(f"      [gate] sources_ok={src_ok} 探活后={len(norm.get('sources', []))}条")
        txt_ok = _gate_text(norm, kind)
        if not txt_ok:
            import re
            for f in ("origin", "y2026_hot", "competitors", "victims", "legal_note", "name"):
                t = str(norm.get(f, ""))
                if _GLITCH_RE.search(t):
                    print(f"      [gate] 病句字段 {f}: …{t[max(0,_GLITCH_RE.search(t).start()-12):_GLITCH_RE.search(t).end()+6]!r}")
            for arr in ("turning_points", "failures", "keys", "lessons", "how_it_works", "red_flags", "real_cases", "protection"):
                for x in norm.get(arr, []):
                    mt = _GLITCH_RE.search(str(x))
                    if mt:
                        print(f"      [gate] 病句字段 {arr}: …{str(x)[max(0,mt.start()-12):mt.end()+6]!r}")
                        break
        trun_ok = _gate_truncation(norm, kind)
        print(f"      [gate] text_ok={txt_ok} truncation_ok={trun_ok}")
        report["status"] = "quality_gate_fail"
        return report

    # 备份 → 覆盖
    fp = DATA / f"{oid}.json"
    bak = DATA / f"{oid}.json.bak-20260806"
    if not bak.exists():
        bak.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    fp.write_text(json.dumps(norm, ensure_ascii=False, indent=1), encoding="utf-8")

    report["status"] = "ok"
    for k in ("milestones", "turning_points", "failures", "keys", "lessons", "sources",
              "how_it_works", "red_flags", "real_cases", "official_alerts", "protection"):
        if isinstance(norm.get(k), list):
            report["after"][k] = len(norm[k])
    if isinstance(norm.get("metrics"), dict):
        report["after"]["metrics"] = len(norm["metrics"])
    report["after"]["origin"] = len(norm.get("origin", ""))
    report["after"]["victims"] = len(norm.get("victims", ""))
    return report


def main() -> int:
    ids = sys.argv[1:] or DEFAULT_IDS
    print(f"待补全 {len(ids)} 条: {ids}")
    results = []
    for oid in ids:
        fp = DATA / f"{oid}.json"
        if not fp.exists():
            print(f"[skip] {oid} 文件不存在")
            continue
        m = json.loads(fp.read_text(encoding="utf-8"))
        print(f"==> 补全 {oid} ({m.get('type')})")
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
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
