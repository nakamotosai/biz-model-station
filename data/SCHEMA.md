# 商业模式情报站 · 数据写入规则（SCHEMA v2）

> 本文件是唯一真源（SSOT）。任何写入方（人工 / AI 采集器 / Hermes cron）新增条目前必须先读本文件。
> 站点根目录：`/home/ubuntu/biz-research/`（vps）↔ `F:\个人研究\2026-08-03-商业模式情报站\`（本机镜像）。
> v2 变更：①条目扩为完整信息（背景/SWOT/护城河/盈利点/成本/目标客户）②**全站禁止日文正文**（名称/行业/地区可保留日文专名如 note、Skeb，但描述性文字必须简体中文）③图 = 清晰流程图（workflow），不再用思维导图。

## 1. 文件组织

- 每条商业模式 = `data/<id>.json` 一个文件
- `scripts/generate_site.py` 读取全部条目 → 生成 `site/`（index.html + 每模式一张 archify **workflow 流程图** + 文字解说页 + data.json 清单）
- 禁止把多个模式塞进一个文件；禁止手改 `site/` 生成物（一律由生成器重建）

## 2. 必填字段（缺失即拒收）

```json
{
  "id": "短横线英文 slug，如 wechat-private-domain",
  "name": "模式中文名（≤40字）",
  "industry": "所属行业（中文）",
  "region": "地区：中|美|日|欧洲|东南亚|全球|跨地区",
  "scale": "规模：巨头|中型|小企|个人",
  "channel": "渠道：线上|线下|实体|混合",
  "background": "背景：这个行业为什么存在/现状如何（2-3行，讲清上下文）",
  "target": "目标客户：谁付钱、什么场景（1-2行）",
  "revenue": "盈利点：钱具体从哪几路来、按什么机制收（3-4行，列出收入流）",
  "cost": "成本结构：主要花销在哪些环节（1-2行）",
  "moat": "护城河：凭什么别人抢不走（1-2行）",
  "swot": {
    "s": ["优势1", "优势2"],
    "w": ["劣势1"],
    "o": ["机会1", "机会2"],
    "t": ["威胁1"]
  },
  "keys": ["成功关键1", "关键2"],
  "risks": ["风险1", "风险2"],
  "example": ["真实案例1", "案例2"],
  "sources": ["来源URL 1", "来源URL 2"]
}
```

字段约束：
- `swot` 四维至少各 1 项；`keys` / `risks` / `sources` 数组 ≥1 项；`sources` ≥2 个真实可访问 URL
- `id` 只含 `[a-z0-9-]`，全站唯一，新增前先查重（读 `site/data.json` 或 `grep -rl`）
- **全站正文用简体中文**（日文/英文案例名可保留原文，如「note」「Skeb」「蜜雪冰城」）
- 禁止编造：`sources` 必须是真实 URL；数字必须有来源；没验证就写「未验」

## 3. 写入流程（人工）

1. 读本文件 + `site/data.json` 查重
2. 新建 `data/<id>.json`（严格按 schema）
3. `python3 scripts/generate_site.py` 重建站点
4. 核对 index.html 出现该条目、流程图渲染正常
5. git commit + push

## 4. 写入流程（AI 采集器 / Hermes cron）

见 `scripts/collect.py`。采集器职责：
1. 查重：读 `site/data.json` 已有 id/name，跳过重复
2. 按轮换选题（见 `data/topics.json`）搜索 2026 新线索
3. 生成草稿到 `data/_drafts/<id>.json`（不直接进正式区）
4. 校验通过后 `generate_site.py` 重建 + git commit
5. 写 `logs/collect.log` 一条记录（时间 / 新增 id / 来源数）

草稿区禁止直接上线；`_drafts/` 里的文件不被生成器读取。

## 5. 质量闸（拒收清单）

- `sources` < 2 或 URL 打不开 → 拒
- `revenue` 不含「钱从哪来/怎么收」→ 拒
- `swot` 四维任一为空 → 拒
- `background` 无行业上下文 → 拒
- 与已有条目高度同质（同模式换名）→ 合并/拒
- 编造案例、编造数字 → 拒（写入方自查，违反 = 整条作废）
- **正文出现整段日文**（非专名）→ 拒

## 6. 分类维度（供索引页筛选）

| 维度 | 取值（可扩展） |
|---|---|
| region | 中 / 美 / 日 / 欧洲 / 东南亚 / 全球 / 跨地区 |
| scale | 巨头 / 中型 / 小企 / 个人 / 灰产 |
| channel | 线上 / 线下 / 实体 / 混合 |
| industry | 只能用以下 14 个（新行业先加这里再用）：AI/大模型 / SaaS/企业软件 / 云计算 / 金融科技 / 内容/创作者经济 / 电商/零售 / 本地生活 / 餐饮/茶饮 / 教育/知识付费 / 医疗/养老 / 营销/广告 / 旅游 / 宠物 / 其他 |

**industry 硬规则**（2026-08-04）：
- 只能用上表 14 个值，不能自创新词；找不到合适的写「其他」
- 生成器 `generate_site.py` 的 `IND_CATALOG` 是同一份目录的 SSOT；改动两边同步
- 历史数据存在碎值（如"AI 大模型""AI数据服务"），生成器用 `IND_KEYS` 子串映射一次性收敛；新数据必须直接写规范值，不要依赖子串映射
- 新增大类：先加 `IND_CATALOG` + `IND_KEYS` + SCHEMA 表，再写数据

---

## 7. 条目类型 type（三板块）

每条数据用 `type` 字段区分板块（缺省 = `model` 向后兼容现有 187 条）：

| type | 板块 | 首页 Tab | 图骨架 | 详情页模板 |
|---|---|---|---|---|
| `model` | 💰 赚钱模式 | 现有 | 7 族 workflow | render_model_page |
| `journey` | 🛤 发家路径 | journey | timeline workflow（3 阶段跳排 col 0/2/4）+ 失败/拐点事件带 | render_journey_page |
| `scam` | ⚠️ 避坑指南 | scam | scam workflow（骗子/受害者/防线 3 泳道，3 步跳排 col 0/2/4）+ 红旗信号节点 | render_scam_page |

### 7.1 journey 必填字段（发家路径）
```json
{
  "type": "journey",
  "id": "英文 slug",
  "name": "条目标题（≤40字）",
  "company": "公司/团队全称",
  "founders": "创始人（可多人）",
  "industry": "14 大类同 model",
  "region": "同 model",
  "scale": "同 model（灰产一般不用）",
  "channel": "同 model",
  "y2026_hot": "为何 2026 值得看（1-2 行）",
  "origin": "起步缘由：为什么做这个（2-3 行）",
  "milestones": [{"time":"阶段时间","stage":"阶段名","outcome":"失败|拐点|转折|PMF|增长","detail":"详情"}],
  "turning_points": ["转折点1","转折点2"],
  "failures": ["失败与踩坑1","失败2"],
  "keys": ["关键成功要素1","关键2"],
  "lessons": ["经验教训1","教训2"],
  "metrics": {"指标名":"值"},
  "competitors": "竞争对手/同行一段话",
  "sources": ["URL1","URL2"]
}
```
**灵魂**：阶段 + 转折 + 失败 + 决策 + 数据；失败与踩坑 > 成功叙事。`milestones` ≥3，至少含 1 个失败/拐点。`sources` ≥2 真实 URL。

### 7.2 scam 必填字段（避坑指南）
```json
{
  "type": "scam",
  "id": "英文 slug",
  "name": "骗局/坑标题（≤40字）",
  "industry": "14 大类同 model",
  "region": "同 model",
  "scale": "灰产（或用 小企 兜底）",
  "channel": "同 model",
  "y2026_hot": "为何 2026 值得看（1-2 行）",
  "victims": "骗谁：受骗人群一段话",
  "how_it_works": ["骗局步骤1","步骤2","步骤3"...],
  "red_flags": ["红旗信号1","信号2"...],
  "real_cases": ["真实案例1（带可查证细节）","案例2"],
  "official_alerts": ["官方警示1（带日期与机构）","警示2"],
  "protection": ["防护建议1","建议2"],
  "legal_note": "法律提示一段话（律师观点/法规依据）",
  "sources": ["URL1","URL2"]
}
```
**灵魂**：五段闭环 — 怎么运作 → 怎么识别 → 真实案例 → 官方态度 → 怎么防护。`how_it_works` ≥3 步、`red_flags` ≥3、`real_cases` ≥2 带可查证细节、`official_alerts` ≥1。`sources` ≥2 真实 URL。
**表述边界**：只引用官方警示与已公开报道，不点名未定罪主体，加法律提示块。

### 7.3 质量闸（journey/scam 通用）
- `sources` < 2 或 URL 打不开 → 拒（同 model）
- journey 的 `milestones` < 3 或不含任何失败/拐点 → 拒（无教训价值）
- scam 的 `real_cases` < 2 或无可查证细节 → 拒
- scam 的 `official_alerts` 为空 → 拒（无官方背书，避免编造）
- 编造案例、编造数字 → 拒（同 model）
- 正文出现整段日文（非专名）→ 拒（同 model）
