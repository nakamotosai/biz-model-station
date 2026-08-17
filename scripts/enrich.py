#!/usr/bin/env python3
"""enrich.py — v1 → v2 条目扩写（加背景/SWOT/护城河/盈利点/成本/目标客户 + 全中文）

用法（vps 上跑，走 intel_hub LLM）：
  python3 scripts/enrich.py --ids <id1,id2,...>   # 只扩指定
  python3 scripts/enrich.py --all --workers 4     # 全部（并行 4 线程）
  python3 scripts/enrich.py --all --dry-run       # 只打印不写

输出：data/<id>.json 原地替换为 v2 schema。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(Path.home() / ".hermes" / "local" / "intel_hub"))
from common import call_direct_chat_completions_model  # noqa: E402

LLM_INSTRUCTIONS = (
    "你是商业模式研究编辑。用户给出一条已调研的 2026 商业模式条目（v1），"
    "你把它扩写为完整版（v2），要求：\n"
    "1) 只输出一个 JSON 对象，不要任何解释/代码块标记；\n"
    "background(背景：行业现状2-3行)、target(目标客户：谁付钱什么场景)、"
    "revenue(盈利点：钱从哪几路来、按什么机制收，3-4行列出收入流，必须非空且有具体机制)、"
    "cost(成本结构：主要花销)、moat(护城河：凭什么抢不走)、"
    "y2026_hot(为何2026热)、keys(数组2-3个成功关键)、risks(数组1-3个风险)、"
    "example(数组1-3个真实案例)、swot(对象：s/w/o/t 各数组≥1项)、"
    "sources(数组，原样保留用户给的真实URL)；\n"
    "3) 全部正文必须用简体中文：把原来日文/英文描述先翻译成简体中文再扩写，"
    "任何字段禁止残留日文假名；"
    "4) 不得编造：background/revenue/moat 基于原条目的 how/y2026_hot 等已有事实扩写，"
    "不得引入原条目没有的数字或案例；sources 原样返回；"
    "5) 若原条目是日文，先翻译成简体中文再扩写。"
)


def expand_one(m: dict, dry_run: bool) -> tuple[str, bool, str]:
    v1 = json.dumps(m, ensure_ascii=False, indent=1)
    last_err = ""
    for attempt in range(2):
        try:
            text, _ = call_direct_chat_completions_model(
                prompt=f"原条目：\n{v1}", instructions=LLM_INSTRUCTIONS,
                max_output_tokens=3500, timeout=180)
        except Exception as e:
            last_err = f"LLM失败: {e}"
            continue
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        try:
            v2 = json.loads(text)
            break
        except Exception:
            mm = re.search(r"\{.*\}", text, re.S)
            if not mm:
                last_err = "输出非JSON"
                continue
            try:
                v2 = json.loads(mm.group(0))
                break
            except Exception:
                last_err = "JSON解析失败"
                continue
    else:
        return m["id"], False, last_err
    # 合并：保留 v1 必填 + 覆盖 v2 新增；v2 用 revenue 取代 v1 的 how
    merged = dict(m)
    for k in ("name", "background", "target", "revenue", "cost", "moat",
              "y2026_hot", "keys", "risks", "example", "swot", "sources", "industry"):
        if k in v2 and v2[k] not in (None, "", [], {}):
            merged[k] = v2[k]
    merged.pop("how", None)  # v1 字段，v2 用 revenue 取代
    # 成功判定：五个扩展字段必须全非空
    for k in ("background", "target", "revenue", "cost", "moat"):
        v = merged.get(k)
        if not (isinstance(v, str) and v.strip()):
            return m["id"], False, f"{k} 为空"
    # 校验 swot 四维
    sw = merged.get("swot")
    if not isinstance(sw, dict) or not all(isinstance(sw.get(x), list) and sw.get(x) for x in "swo"):
        return m["id"], False, "swot 不完整"
    merged["swot"] = {x: [str(i) for i in (sw.get(x) or [])][:3] for x in "swot"}
    for x in "swot":
        if not merged["swot"][x]:
            return m["id"], False, f"swot.{x} 为空"
    if not isinstance(merged.get("sources"), list) or len(merged["sources"]) < 2:
        return m["id"], False, "sources <2"
    # 禁日文正文（专名除外：检测整段含日文假名的描述字段）
    import unicodedata as _ud
    def _has_jp(s: str) -> bool:
        return any("\u3040" <= ch <= "\u30ff" for ch in s)  # 平假名+片假名
    for k in ("background", "target", "revenue", "cost", "moat", "y2026_hot"):
        if _has_jp(merged.get(k, "")):
            return m["id"], False, f"{k} 含日文正文"
    if not dry_run:
        (DATA / f"{m['id']}.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return m["id"], True, "ok"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="逗号分隔 id 列表")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    models = []
    for f in sorted(DATA.glob("*.json")):
        if f.name in ("topics.json", "index.json"):
            continue
        models.append(json.loads(f.read_text(encoding="utf-8")))
    if args.ids:
        want = set(args.ids.split(","))
        models = [m for m in models if m["id"] in want]
    print(f"待扩写 {len(models)} 条（workers={args.workers}, dry_run={args.dry_run}）")
    ok = fail = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(expand_one, m, args.dry_run): m["id"] for m in models}
        for fut in as_completed(futs):
            mid, succ, msg = fut.result()
            if succ:
                ok += 1
                print(f"  [ok] {mid}")
            else:
                fail += 1
                print(f"  [fail] {mid}: {msg}")
    print(f"完成：ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
