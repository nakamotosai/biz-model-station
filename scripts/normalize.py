#!/usr/bin/env python3
"""normalize.py — 把 raw/*.json 调研结果归一化进 data/<id>.json

- 读取 raw/ 下所有 JSON 数组
- 修正字段别名（行业→industry、gej→industry、ris/risk→risks、why→how、evidence→keys 等）
- 校验必填字段；缺失/非法丢弃并报告
- 按 id 去重；写 data/<id>.json + data/index.json 摘要
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
DATA = ROOT / "data"
REQUIRED = ["id", "name", "industry", "region", "scale", "channel", "y2026_hot", "how", "keys", "risks", "sources"]

FIELD_ALIASES = {
    "行业": "industry", "gej": "industry", "indust": "industry",
    "ris": "risks", "risk": "risks", "风险": "risks",
    "why": "how", "instead": "how",
    "evidence": "keys", "evidence_text": "keys", "关键": "keys",
    "example": "example", "案例": "example",
    "region": "region", "渠道": "channel", "规模": "scale",
}
CHANNEL_NORM = {
    "线上": "线上", "线下": "线下", "实体": "实体", "混合": "混合",
    "线上线下混合": "混合", "线上+线下": "混合", "实体+线上": "混合",
    "オンライン": "线上", "オフライン": "线下",
}


def norm_field(m: dict, aliases: dict) -> dict:
    out = {}
    for k, v in m.items():
        k2 = aliases.get(k, k)
        if k2 not in out or out[k2] in (None, ""):
            out[k2] = v
    return out


def clean_text(s) -> str:
    if not isinstance(s, str):
        return str(s)
    s = s.replace("\n", " ").replace("\r", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def as_list(v, max_items: int = 6) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        # 可能整条 JSON 串被塞进字段（上游 yield 异常）→ 尝试解析
        if v.lstrip().startswith("["):
            try:
                v = json.loads(v)
            except Exception:
                return []
        else:
            return [clean_text(v)[:120]] if clean_text(v) else []
    if isinstance(v, list):
        out = []
        for it in v:
            if isinstance(it, str):
                t = clean_text(it)
                if t and t not in out:
                    out.append(t[:120])
            elif isinstance(it, dict):
                t = clean_text(it.get("label") or it.get("name") or it.get("title") or "")
                if t and t not in out:
                    out.append(t[:120])
            if len(out) >= max_items:
                break
        return out
    return []


def normalize(m: dict) -> dict | None:
    m = norm_field(m, FIELD_ALIASES)
    out = {}
    for k in REQUIRED:
        v = m.get(k)
        if k in ("keys", "risks"):
            out[k] = as_list(v)
        elif k == "sources":
            out[k] = as_list(v, max_items=8)
        elif k == "example":
            out[k] = as_list(v, max_items=5)
        else:
            out[k] = clean_text(v)
    out["example"] = as_list(m.get("example"), max_items=5)
    # 校验
    for k in REQUIRED:
        v = out[k]
        if k in ("keys", "risks", "sources"):
            if not v:
                return None
        elif not v:
            return None
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", out["id"]):
        return None
    ch = out["channel"]
    out["channel"] = CHANNEL_NORM.get(ch, "混合" if "线" in ch or "实体" in ch else ch)
    # 清洗 sources 为合法 URL 列表
    out["sources"] = [u for u in out["sources"] if u.startswith(("http://", "https://"))]
    if len(out["sources"]) < 1:
        return None
    return out


def main() -> int:
    merged: dict[str, dict] = {}
    for f in sorted(RAW.glob("*.json")):
        try:
            arr = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[skip] {f.name}: {e}")
            continue
        if not isinstance(arr, list):
            continue
        for m in arr:
            if not isinstance(m, dict):
                continue
            nm = normalize(m)
            if nm is None:
                print(f"[drop] {f.name} :: {m.get('id', '?')}")
                continue
            if nm["id"] in merged:
                print(f"[dup] {nm['id']} 保留先出现")
                continue
            merged[nm["id"]] = nm
    DATA.mkdir(exist_ok=True)
    for mid, m in merged.items():
        (DATA / f"{mid}.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    idx = {"count": len(merged), "ids": sorted(merged)}
    (DATA / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[ok] {len(merged)} 条入库 data/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
