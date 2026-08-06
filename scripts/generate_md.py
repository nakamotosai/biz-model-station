#!/usr/bin/env python3
"""generate_md.py — 商业模式情报站 markdown 文档版导出器

输入：data/*.json（与 generate_site.py 同一批数据）
输出：markdown/<id>.md（每卡一篇文档版）+ markdown/README.md（索引）
用途：GitHub 仓库文档版分享；wiki 只建索引页指向仓库，不双写正文

用法：
  python3 scripts/generate_md.py            # 全量导出
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MD = ROOT / "markdown"

# 与 generate_site.py 相同的跳过清单与必填校验（保持同源）
SKIP = {"SCHEMA.json", "index.json", "topics.json", "SCHEMA.md"}
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

TYPE_LABEL = {"model": "💰 赚钱模式", "journey": "🛤 发家路径", "scam": "⚠️ 避坑指南"}


def load_cards() -> list[dict]:
    cards = []
    for f in sorted(DATA.glob("*.json")):
        if f.name.startswith(".") or f.name in SKIP:
            continue
        m = json.loads(f.read_text(encoding="utf-8"))
        req = REQUIRED_BY_TYPE.get(m.get("type", "model"), REQUIRED_BY_TYPE["model"])
        missing = [k for k in req if k not in m or m[k] in (None, "", [], {})]
        if missing:
            raise SystemExit(f"[{f.name}] 缺必填字段: {missing}")
        cards.append(m)
    return cards


def ul(items, prefix: str = "") -> str:
    if not items:
        return ""
    return "\n".join(f"{prefix}- {x}" for x in items if str(x).strip())


def fmt(m: dict) -> str:
    t = m.get("type", "model")
    label = TYPE_LABEL.get(t, "💰 赚钱模式")
    dims = f"**{m.get('industry','')}** · {m.get('region','')} · {m.get('scale','')} · {m.get('channel','')}"
    out = [f"# {m['name']}", ""]
    out += [f"> {label} | {dims}", ""]
    if t == "model":
        out += [
            "## 📌 背景", "", str(m["background"]), "",
            "## 👤 目标客户", "", str(m["target"]), "",
            "## 💰 盈利点", "", str(m["revenue"]), "",
            "## 🧮 成本结构", "", str(m["cost"]), "",
            "## 🛡️ 护城河", "", str(m["moat"]), "",
            "## 🔑 成功关键", "", ul(m.get("keys", [])), "",
            "## ⚠️ 风险", "", ul(m.get("risks", [])), "",
        ]
        sw = m.get("swot", {})
        if sw:
            out += ["## SWOT", ""]
            for k, title in (("s", "优势"), ("w", "劣势"), ("o", "机会"), ("t", "威胁")):
                items = sw.get(k) or []
                if isinstance(items, str):
                    items = [items]
                out += [f"### {title}", "", ul(items), ""]
        if m.get("example"):
            out += ["## 🏢 案例", "", ul(m["example"]), ""]
    elif t == "journey":
        out += [
            "## 🚀 起步缘由", "", str(m.get("origin", "")), "",
            f"**创办人**：{m.get('founders','')} · **公司**：{m.get('company','')}", "",
            "## 📈 发家里程碑", "",
        ]
        for x in m.get("milestones", []):
            tag = f"（{x.get('outcome','')}）" if x.get("outcome") else ""
            out += [f"- **{x.get('time','')}** {x.get('stage','')}{tag}", f"  - {x.get('detail','')}"]
        out += ["", "## 🔀 转折点", "", ul(m.get("turning_points", [])), "",
                "## 🕳️ 失败与踩坑", "", ul(m.get("failures", [])), "",
                "## 🔑 关键成功要素", "", ul(m.get("keys", [])), "",
                "## 📚 经验教训", "", ul(m.get("lessons", [])), "",
                "## 📊 核心数据", ""]
        for k, v in (m.get("metrics") or {}).items():
            out += [f"- **{k}**：{v}"]
        out += ["", "## ⚔️ 竞争对手 / 同行", "", str(m.get("competitors", "")), ""]
    else:  # scam
        out += [
            "## 👥 受害人群", "", str(m.get("victims", "")), "",
            "## 🎭 骗局怎么运作", "", ul(m.get("how_it_works", [])), "",
            "## 🚩 红旗信号（别上当）", "", ul(m.get("red_flags", [])), "",
            "## 📋 真实案例", "", ul(m.get("real_cases", [])), "",
            "## 📢 官方警示", "", ul(m.get("official_alerts", [])), "",
            "## 🛡️ 怎么防护", "", ul(m.get("protection", [])), "",
            "## ⚖️ 法律提示", "", str(m.get("legal_note", "")), "",
        ]
    out += ["## 🔗 来源", ""]
    out += [f"- [{u}]({u})" for u in m.get("sources", [])]
    out += ["", "---", f"*由 biz.saaaai.com 商业模式情报站自动生成 · {datetime.now():%Y-%m-%d}*", ""]
    return "\n".join(out)


def main() -> None:
    cards = load_cards()
    MD.mkdir(exist_ok=True)
    (MD / ".gitkeep").write_text("", encoding="utf-8")
    for m in cards:
        (MD / f"{m['id']}.md").write_text(fmt(m), encoding="utf-8")
    # 索引 README：按板块分组
    groups = {"model": [], "journey": [], "scam": []}
    for m in cards:
        groups[m.get("type", "model")].append(m)
    idx = [
        "# 商业模式情报站 · 文档版",
        "",
        "> 2026 各行业盈利模式/发家路径/避坑指南图鉴——每篇 = 一份可读的商业模式拆解。",
        f"> 数据来自 [biz.saaaai.com](http://biz.saaaai.com/)（网页版），本仓库为文档版镜像。",
        "",
        f"共 **{len(cards)}** 篇（model {len(groups['model'])} / journey {len(groups['journey'])} / scam {len(groups['scam'])}）",
        "",
    ]
    for t, label in (("model", "💰 赚钱模式"), ("journey", "🛤 发家路径"), ("scam", "⚠️ 避坑指南")):
        idx += [f"## {label}（{len(groups[t])}）", ""]
        for m in sorted(groups[t], key=lambda x: x["id"]):
            idx += [f"- [{m['name']}]({m['id']}.md) · {m.get('industry','')} · {m.get('region','')}"]
        idx += [""]
    (MD / "README.md").write_text("\n".join(idx), encoding="utf-8")
    print(f"[ok] markdown 文档版导出完成：{len(cards)} 篇 → {MD}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        print(e, file=sys.stderr)
        sys.exit(1)
