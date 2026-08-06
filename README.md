# 商业模式情报站 · Business Model Station 📈

2026 各行业盈利模式 / 发家路径 / 避坑指南的**可读文档版**，网页版见 [biz.saaaai.com](http://biz.saaaai.com/)。

## 这是什么

一个持续自动更新的商业模式图鉴：每篇是一份可读的商业模式拆解，按板块分三类：

| 板块 | 类型 | 关注什么 |
|---|---|---|
| 💰 赚钱模式 | model | 背景 / 目标客户 / 盈利点 / 成本 / 护城河 / SWOT |
| 🛤 发家路径 | journey | 里程碑 / 转折 / 失败 / 成功要素 / 教训 / 数据 |
| ⚠️ 避坑指南 | scam | 骗局运作 / 红旗信号 / 真实案例 / 官方警示 / 防护 |

## 目录

- [`markdown/README.md`](markdown/README.md) — 全部条目文档索引（按板块，随内容自动生成）
- [`markdown/*.md`](markdown/) — 每篇的 markdown 文档（GitHub 直接渲染可读）
- [`data/`](data/) — 结构化源数据（`data/SCHEMA.md` 为字段规范）
- [`scripts/`](scripts/) — 采集器 `collect.py` / 站点生成器 `generate_site.py` / 文档导出器 `generate_md.py`

## 项目运作机制

- **采集**：vps 定时任务每 10 分钟搜新线索 → 大模型提炼 → 质量闸校验（下限/来源/查重/合规归属）→ 写入 `data/<id>.json`
- **生成**：新条目落盘后自动重建网页版（`generate_site.py` → HTTP 站）并导出文档版（`generate_md.py` → 本仓 `markdown/`）
- **发布**：`publish.sh` 把最新内容（data + markdown + scripts）自动推到本 GitHub 公开仓——**每采一条，同步一条**，无需人工维护
- **内容下限**（采集即达标）：
  - journey：≥5 里程碑（含至少 2 个失败/拐点）、≥4 关键要素、≥4 教训、≥5 数据点、≥4 来源
  - scam：≥5 运作步骤、≥5 红旗信号、≥3 真实案例、≥3 官方警示、≥4 防护、≥4 来源
- **合规**：scam 案例人员一律脱敏（甲某/乙某/A某等代称），只引公开报道与官方通报，不点名未定身份主体
- **数据口径**：`data/*.json` 是机器可读真源，`markdown/` 为派生产物，`scripts/` 为生成与发布工具链

## 本地复现

```bash
python3 scripts/generate_site.py   # 重建网页版
python3 scripts/generate_md.py     # 重新导出 markdown 文档版
python3 scripts/publish.sh         # 手动推本公开仓
```

数据新条目由采集器自动写入，网页与文档版同源触发自动生成，仓内容随采集持续演进。

---

*由 biz.saaaai.com 商业模式情报站采集器自动同步 · 内容持续更新*