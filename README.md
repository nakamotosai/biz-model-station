# 商业模式情报站 · Business Model Station 📈

2026 各行业盈利模式 / 发家路径 / 避坑指南的**可读文档版**，网页版见 [biz.saaaai.com](http://biz.saaaai.com/)。

共 **212 篇**（`data/*.json` 为机器可读源，`markdown/*.md` 为文档版镜像）：

| 板块 | 类型 | 数量 | 说明 |
|---|---|---|---|
| 💰 赚钱模式 | model | 199 | 盈利模式拆解：背景/客户/盈利点/成本/护城河/SWOT |
| 🛤 发家路径 | journey | 8 | 企业成长史：里程碑/转折/失败/成功要素/教训/数据 |
| ⚠️ 避坑指南 | scam | 5 | 骗局拆解：运作机制/红旗信号/真实案例/官方警示/防护 |

## 目录

- [`markdown/README.md`](markdown/README.md) — 全部 214 篇文档索引（按板块）
- [`markdown/*.md`](markdown/) — 每篇的 markdown 文档（GitHub 直接渲染可读）
- [`data/`](data/) — 结构化源数据（`data/SCHEMA.md` 为字段规范）
- [`scripts/`](scripts/) — 采集器 `collect.py` / 站点生成器 `generate_site.py` / 文档导出器 `generate_md.py`

## 内容示例

| 板块 | 条目 |
|---|---|
| 发家路径 | [Perplexity 答案引擎](markdown/ai-answer-engine-perplexity.md)、[Cursor IDE](markdown/ai-native-cursor-ide.md)、[Liblib AI 绘图](markdown/ai-image-liblib-evoken-survival.md) |
| 避坑指南 | [AI 数据标注兼职骗局](markdown/ai-data-annotation-part-time-scam.md)、[AI 换脸杀猪盘](markdown/ai-deepfake-romance-scam.md)、[AI 中转站骗局](markdown/ai-relay-station-scam.md) |

## 数据口径

- **自动采集**：cron 每 10 分钟搜新线索 → LLM 提炼 → 质量闸校验 → 重建 → 上线，无限轮转
- **质量下限**：journey 每篇 ≥5 里程碑（含失败/拐点）、≥4 关键要素、≥4 教训、≥5 数据点；scam 每篇 ≥5 运作步骤、≥5 红旗信号、≥3 真实案例、≥3 官方警示
- **合规**：scam 案例人员一律脱敏（甲某/乙某/A某），只引公开报道与官方通报，不点名未定罪主体

## 生成与维护

```bash
python3 scripts/generate_site.py   # 重建网页版
python3 scripts/generate_md.py     # 重新导出 markdown 文档版
```

数据新条目由 vps 采集器自动写入 `data/`，`markdown/` 由 `generate_md.py` 同步导出。欢迎用上方 link 浏览，自带一份离线可读副本。

---

*由 biz.saaaai.com 商业模式情报站导出 · 自动更新*