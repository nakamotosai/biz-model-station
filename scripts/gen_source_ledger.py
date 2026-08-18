#!/usr/bin/env python3
"""gen_source_ledger.py — 生成数据来源台账（每条：id/name/type/sources URLs/时间/LICENSE）

背景：商业化 runbook G1/G2 要求「CC BY 4.0 授权先于数据来源台账落定=顺序颠倒」，
故挂 CC BY 前必须先生成台账：400 条精选数据的来源 URL 全量列出，证明授权范围有据可查。

用法：
  python3 gen_source_ledger.py [--data PATH] [--out PATH]
默认：data=当前目录 data/，out=./docs/source-ledger.md

时间列说明：JSON 无逐条抓取时间戳（agent 类 time 字段是内容非时间），
台账时间列 = git 仓库首个数据提交日期（采集基线），逐条抓取时间不可回溯。
LICENSE 列：原页面许可未逐条核验，统一标 '未逐条核验（源站页面许可待人工抽验）'。

输出：markdown 表格，按 type 分组（model/journey/scam/agent）。
"""
import argparse
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

TYPE_LABEL = {"model": "model 盈利模式", "journey": "journey 发家路径",
              "scam": "scam 避坑指南", "agent": "agent AI 创业案例"}


def git_first_commit_date(repo: Path) -> str:
    """取 git 仓库首个 data/ 提交日期作为采集基线。"""
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "log", "--reverse", "--format=%ci", "--", "data/"],
            capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip().splitlines()[0][:10]
    except Exception:
        pass
    return "2026-08-17"  # 兜底：公开仓精选 400 条导入日


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default="docs/source-ledger.md")
    args = ap.parse_args()

    data_dir = Path(args.data)
    repo = data_dir.parent
    base_date = git_first_commit_date(repo)

    rows = []
    by_type: dict[str, int] = {}
    no_src = []
    for f in sorted(data_dir.glob("*.json")):
        if f.name.startswith("."):
            continue
        try:
            m = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[warn] {f.name} 解析失败: {e}")
            continue
        tid = m.get("type") or ""  # 键缺失或空串统一处理
        if tid not in TYPE_LABEL:
            tid = "model"  # 旧数据无 type 字段 → model（向后兼容）
        by_type[tid] = by_type.get(tid, 0) + 1
        srcs = m.get("sources") or []
        if not isinstance(srcs, list):
            srcs = [srcs] if srcs else []
        srcs = [str(s).strip() for s in srcs if str(s).strip()]
        if not srcs:
            no_src.append(m.get("id", f.name))
        # 用第一个 source 作主 URL，其余并入「其他来源」
        primary = srcs[0] if srcs else "（无来源）"
        others = "；".join(srcs[1:]) if len(srcs) > 1 else ""
        rows.append({
            "id": m.get("id", f.stem),
            "name": str(m.get("name", ""))[:40],
            "type": tid,
            "url": primary,
            "others": others,
            "date": base_date,
        })

    rows.sort(key=lambda r: (r["type"], r["id"]))
    total = len(rows)

    out = [
        f"# 数据来源台账（{total} 条）",
        "",
        f"> 生成：{datetime.now().strftime('%Y-%m-%d %H:%M')} · 用途：CC BY 4.0 授权前的来源核验（runbook G1/G2）",
        f"> 时间列 = git 仓库首个 data/ 提交日期（{base_date}），作为采集基线；逐条抓取时间不在 JSON 内，不可回溯。",
        "> LICENSE 列：原页面许可未逐条核验，统一标注，挂 CC BY 前应人工抽验高风险源（个人博客/站内转载）。",
        "",
    ]
    if no_src:
        out.append(f"> **⚠️ {len(no_src)} 条无 sources 字段：**{', '.join(no_src[:10])}{'…' if len(no_src) > 10 else ''}")
        out.append("")
    for tid in ("model", "journey", "scam", "agent"):
        group = [r for r in rows if r["type"] == tid]
        if not group:
            continue
        out.append(f"## {TYPE_LABEL.get(tid, tid)}（{len(group)} 条）")
        out.append("")
        out.append("| id | 名称 | 来源 URL | 其他来源 | 采集时间基线 | LICENSE |")
        out.append("|---|---|---|---|---|---|")
        for r in group:
            name = r["name"].replace("|", "｜")
            url = r["url"].replace("|", "｜")
            others = r["others"].replace("|", "｜")
            out.append(f"| {r['id']} | {name} | {url} | {others} | {r['date']} | 未逐条核验 |")
        out.append("")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out), encoding="utf-8")
    print(f"[ok] 台账 {total} 条 → {out_path}")
    print(f"    分型: {dict(sorted(by_type.items()))}")
    if no_src:
        print(f"    ⚠️ {len(no_src)} 条无 sources: {no_src[:8]}")


if __name__ == "__main__":
    main()