# Mistral AI：三人从谷歌Meta出走，靠开源权重做成欧洲140亿AI旗手

> 🛤 发家路径 | **AI/大模型** · 欧 · 独角兽 · ToB

## 🚀 起步缘由

三人都是法国顶级工程师：Mensch 在巴黎综合理工学院（École Polytechnique）读书时与 Lample 结识，Lample 2016 年入 Meta AI 研究院，与 Lacroix 共事并参与打造 2023 年 2 月发布的 LLaMA；Mensch 博士后进 Google 巴黎办公室做 DeepMind，写过一篇证明大语言模型可以用远低于 OpenAI 成本训练的论文。LLaMA 一发布就在学术圈和创业圈炸开，三人觉得欧洲必须有自己的 AI 模型，几个月内先后辞职，2023 年 4 月 28 日在巴黎创立 Mistral AI，取名自南法冬季席卷地中海的寒冷强风 mistral，要做旧金山之外的另一种 AI

**创办人**：Arthur Mensch（CEO，前 Google DeepMind），Guillaume Lample（首席科学家，前 Meta AI），Timothée Lacroix（CTO，前 Meta AI） · **公司**：Mistral AI SAS

## 📈 发家里程碑

- **2023 年 4 月** 出走创立（启动）
  - Mensch 离开 Google DeepMind，拉着 Meta AI 出身的老同事 Lample 和 Lacroix 一起辞职，四月底在巴黎第十区一间小办公室创立 Mistral AI。三人判断欧洲大陆需要本土 AI 模型，政府与工业巨头愿意为此买单，而且欧洲对数据不出境的合规诉求正好是他们区别于硅谷封闭模型的天然卖点。起步只有寥寥几人，手里没有产品也没有客户，只有三家美国大实验室的履历和一篇成本革命的论文
- **2023 年 6 月** 史上最大种子（拐点）
  - 成立刚满四周年就拿到 1.05 亿欧元（约 1.17 亿美元）种子轮，Lightspeed 领投，Eric Schmidt、法国电信大亨 Xavier Niel、广告巨头 JCDecaux 等参投，估值约 2.4 亿欧元，是当时欧洲有史以来最大一笔种子轮。一家连模型都还没有发布、仅成立一个月的公司就拿到这个量级的资金，被视为欧洲对 AI 主权的急切信号
- **2023 年 9 月** 首发开源（增长）
  - 9 月 27 日用磁力链接在推特放出首个模型 Mistral 7B，随后挂上 HuggingFace，采用 Apache 2.0 完整开源许可，参数仅 73 亿，声称在所有测过的基准上超越 LLaMA 2 13B，多项指标打平 LLaMA 34B。用种子链接首发开源模型在当时极为罕见，瞬间在开发者社区炸开，把一家月龄不到半年的欧洲公司推上全球 AI 圈头条
- **2023 年 12 月** 独角兽MoE（增长）
  - 12 月 10 日宣布 3.85 亿欧元（约 4.28 亿美元）A 轮，a16z、BNP Paribas、Salesforce 参投，估值冲过 20 亿欧元跻身独角兽。同月 9 日放出的 Mixtral 8x7B 采用稀疏专家混合（MoE）架构，总参数 46.7 亿但每 token 仅激活 12.9 亿，推理速度与成本接近 13B 模型，声称在多数基准上击败 LLaMA 70B 和 GPT-3.5，把开源权重的性能故事推到新高度
- **2024 年 2 月** 微软联姻（转折）
  - 2 月 26 日 Microsoft 宣布 1600 万美元投资并接入 Azure，同日 Mistral 发布首个闭源旗舰 Mistral Large 与对话产品 Le Chat。这次合作引来欧盟监管审查，质疑 Microsoft 是否借绑定欧洲冠军来绕开 AI 法案审查；同时开源社区开始警觉，因为 Large 从一开始就是专有许可，不再是 Apache 2.0。对一家以开源旗号起身的公司而言，这笔交易既是规模跳板，也是立场稀释的第一道裂缝
- **2024 全年** 性能商业双困（失败）
  - Forbes 报道 Mistral 2024 年营收远低于 5000 万美元，与 OpenAI 同年约百亿美元收入形成量级鸿沟。模型性能也持续被甩开：到 2026 年其最佳模型在一项流行基准上仍会输给 Anthropic 九个月前发布的 Claude 版本，更被中国 DeepSeek 和阿里巴巴的开源权重模型反超。Menlo Ventures 对 500 名美国企业高管的调查显示 Anthropic 市占 40%、OpenAI 27%、Mistral 仅 2%。Mensch 后来坦承创始团队来自研究实验室没有商业化经验，几乎是边做边学
- **2024 年 6 月** 62亿估值（增长）
  - 拿到 6 亿欧元（约 6.45 亿美元）融资，估值升至 58 亿欧元（约 62 亿美元），按估值排到全球 AI 行业第四、旧金山湾区之外第一。资本仍愿为开源叙事和欧洲冠军身份投票，但这次把估值推到 60 亿的代价是对营收兑现的更高压力，公司被锁定在最贵软件公司之列，业绩跟不上叙事的张力开始累积
- **2025 年 5 至 9 月** 转身驻场（拐点）
  - 5 月发布可在企业本地部署的 Mistral Medium 3，4 月与全球第三大航运公司 CMA CGM 签 1 亿欧元合作，开始借鉴 Palantir 的 forward-deployed engineers 模式，派高阶工程师驻场客户 offices 解决业务问题，用开放权重模型帮 HSBC、Tesco 等蓝筹把敏感数据留在自己地理范围内。9 月 ASML 领投约 20 亿欧元 C 轮估值 120 亿欧元（约 140 亿美元），持有 11% 成第一大股东，三位创始人各持 13% 身家 18 亿美元成为法国首批 AI 亿万富翁。公司内部开始把竞争对手对标 Palantir，办公室里挂着把 Palantir 改成 Poulet 用鸡头替 Karp 的恶搞海报
- **2025 年 12 月** 开源回归（增长）
  - 12 月 2 日开源 Mistral Large 3，稀疏 MoE 架构总参数 675 亿、活跃参数 41 亿，采用 Apache 2.0 许可，同期发布 Ministral 3 三款 3B/8B/14B 小模型与 Devstral 2 编程模型。把旗舰重新放回完全开源，被解读为在闭源路线试水后重新回到开源差异化的主线，也是对社区关于许可策略漂移质疑的一次回应
- **2026 年 2 至 5 月** 收购建云基建（转折）
  - 2 月 17 日完成首笔收购，买下巴黎 AI 云初创 Koyeb 支撑自营云基建，同月 26 日与 Accenture 签署战略协议把企业 AI 部署铺到全球咨询网络。3 月再以 8.3 亿美元债务融资建巴黎与瑞典数据中心，目标 2027 年底 200 兆瓦，由法国国有核电站供电，总造价估计 50 亿美元，并转向阿布扎比寻求资金。5 月 19 日收购奥地利工业仿真 AI 公司 Emmi AI，把工业仿真从数小时压到数秒，瞄准欧洲工业巨头客户
- **2026 年 5 至 7 月** 主权变现金牛（PMF）
  - Forbes 2026 年 4 月披露 Mistral 2025 年营收约 2 亿美元，Mensch 称到 12 月月营收可达 8000 万美元但公司仍未盈利。5 月底把对话产品 Le Chat 更名为 Vibe 并加入远程 Agent 能力。7 月 21 日扩大与 Microsoft 合作签数十亿美元协议，把 Mistral Medium 3.5 与 OCR 4 接入 Microsoft Foundry 和 Copilot Studio。不过同期社区调查显示 Mistral 在常见 AI 基准上的落后差距仍在拉大，靠主权和企业驻场服务而非模型性能挣钱的 Palantir 化路线已经是其能否守住的唯一护城河

## 🔀 转折点

- 2023 年 6 月仅成立四周就拿到 Lightspeed 领投 1.05 亿欧元欧洲史上最大种子轮，把一家没有产品的公司推到欧洲 AI 主权叙事的台前
- 2024 年 2 月与 Microsoft 的 1600 万美元联姻是把闭源旗舰 Large 与对话产品 Le Chat 推向市场的规模跳板，但也是开源立场第一次被稀释的裂缝
- 2025 年 9 月 ASML 领投 20 亿欧元 C 轮估值 120 亿欧元，欧洲最有价值的科技公司把筹码压在又一家欧洲冠军身上，三位创始人瞬间成法国首批 AI 亿万富翁
- 2026 年 2 月首笔收购 Koyeb 后开始建自营数据中心并转向 Palantir 式 forward-deployed 驻场工程师模式，把研究团队转型企业服务商

## 🕳️ 失败与踩坑

- 模型性能持续落后：到 2026 年其最佳模型在一项流行基准上仍会输给 Anthropic 九个月前发布的 Claude，更被中国 DeepSeek 和阿里巴巴的开源权重模型反超，用绩效换主权的叙事始终在被戳穿的边缘
- 2024 年营收远低于 5000 万美元，与 OpenAI 同期约百亿美元收入形成量级鸿沟，Menlo Ventures 调查显示其在美国企业市场市占仅 2%，与 Anthropic 40%、OpenAI 27% 形成残酷对照
- 创始团队来自 Meta AI 和 Google DeepMind 两家纯研究机构，缺乏商业化操盘经验，Mensch 后来承认几乎边做边学，导致从研究到企业服务的转身上手成本极高
- 开源承诺不断稀释：从早期全面 Apache 2.0 起步，2024 年经 Microsoft 联姻后 Large 走专有许可、Codestral 用禁止商业用途的 Mistral Non-Production License，被开源社区质疑是否还是开源旗手，直到 2025 年底 Large 3 才重新放回 Apache 2.0
- 被硅谷同行讥为 Palantir 式系统集成商而非前沿 AI 公司，一大块收入来自驻场咨询而非模型本身，技术差异化的护城河叙事被资本故事稀释

## 🔑 关键成功要素

- 开源权重让客户可定制、可离线运行、数据不必离开办公室，在 Trump 贸易战与欧洲数字主权浪潮下把技术选择重新定义成地缘筹码，是 Mistral 区别于 OpenAI 与 Anthropic 黑盒模型的核心叙事
- 借鉴 Palantir 的 forward-deployed engineers 驻场模式，把研究团队转型企业服务商，帮 HSBC、Tesco、CMA CGM、ASML 等蓝筹在敏感数据不出地理范围的前提下落地 AI，用服务收入弥补模型性能差距
- 法国政府与 ASML 双重背书构成信用链：马克龙称其为 French genius，军方到就业局都在签合同，ASML 领投后用自家光刻产品验证工业场景，把欧洲冠军身份从叙事变成可背书的资产
- 低成本起家基因：Mensch 在 DeepMind 的论文证明大模型可以远低于 OpenAI 成本训练，Lample 和 Lacroix 在 Meta 用这套思路做出 LLaMA，这一成本革命经验让 Mistral 7B 用 73 亿参数打平 LLaMA 34B，把资源劣势转成差异化卖点
- 自营数据中心战略：巴黎与瑞典 200 兆瓦目标 2027 年底建成，由法国国有核电站供电，给担心被 hyperscaler 锁定的客户一条独立 AI 基建路线，也是 ASML 和 Microsoft 愿意长期押注的物理资产

## 📚 经验教训

- 性能不是一切：在主权与控制成为真实购买动机的市场里，不领先九个月的模型配上可定制、可驻场、数据不出境依然能挣 2 亿美元年收，但这条护城河要求服务能力而非模型能力做强
- 开源旗号是差异化护城河更是立场的持续考验：从 Apache 2.0 到专有许可再到 Large 3 重新放开，每一次许可策略漂移都会被社区追究，开源不是一次定性而是长期一致性投资
- 地缘政治制造窗口期但窗口会移动：Trump 贸易战把欧洲数字主权推到台前，但 Microsoft、Google、Amazon 都在加投欧洲 AI 基建，Mistral 的欧洲冠军身份是窗口期资产而非永久护城河
- 研究团队做企业服务要先补 forward-deployed 这条腿：纯研究机构出来的创始团队天然缺商业化操盘，把 Palantir 驻场工程师模式做进产品是 Mistral 能兑现 2 亿美元年收的关键转身而非可选项
- 估值周期与营收周期错配的风险被放大：60 亿估值对应远低于 5000 万美元的年收，140 亿估值对应 2 亿美元年收且尚未盈利，估值大幅领先业绩时市场对增长兑现的容错空间极小，任何一个月数据打脸都会触发大幅调整

## 📊 核心数据

- **成立时间**：2023 年 4 月 28 日
- **种子轮 2023.06**：1.05 亿欧元，估值 2.4 亿欧元
- **A 轮 2023.12**：3.85 亿欧元，估值超 20 亿欧元
- **Microsoft 投资 2024.02**：1600 万美元
- **B 轮 2024.06**：6 亿欧元，估值 58 亿欧元（约 62 亿美元）
- **CMA CGM 合作 2025.04**：1 亿欧元
- **C 轮 2025.09**：约 20 亿欧元，估值 120 亿欧元（约 140 亿美元）
- **ASML 持股**：11%，投资 15 亿美元
- **创始人各持股**：13%，身家约 18 亿美元
- **累计融资**：约 31 亿美元
- **美国企业市场市占**：2%
- **2025 年营收**：约 2 亿美元（截至 2026 年 4 月 Forbes）
- **2026 年 12 月目标月营收**：约 8000 万美元
- **首次收购 Koyeb 2026.02**：未披露金额
- **数据中心债务融资 2026.03**：8.3 亿美元
- **数据中心目标产能 2027 年底**：200 兆瓦
- **员工数 2026**：约 1000 人

## ⚔️ 竞争对手 / 同行

对标三大封闭巨头 OpenAI、Anthropic、Google DeepMind，但三者两年内融资超 2000 亿美元，Mistral 到 2026 年累计融资仅约 31 亿美元；开源权重赛道正面碰 Meta LLaMA 团队和中国 DeepSeek、阿里巴巴 Qwen，且 Meta 在是否继续做开源 Llama 继任者上出现摇摆给 Mistral 留出空窗；企业服务路线上与 Palantir 的 forward-deployed engineers 模式重叠，办公室海报直接把 Palantir 讽刺为 Poulet 用鸡头替 Alex Karp；背后的投资方 Nvidia 也开始自推开源权重模型，既是股东又是潜在威胁

## 🔗 来源

- [https://en.wikipedia.org/wiki/Mistral_AI](https://en.wikipedia.org/wiki/Mistral_AI)
- [https://www.forbes.com/sites/iainmartin/2026/04/16/how-frances-mistral-built-a-14-billion-ai-empire-by-not-being-american/](https://www.forbes.com/sites/iainmartin/2026/04/16/how-frances-mistral-built-a-14-billion-ai-empire-by-not-being-american/)
- [https://techcrunch.com/2026/07/04/what-is-mistral-ai-everything-to-know-about-the-openai-competitor/](https://techcrunch.com/2026/07/04/what-is-mistral-ai-everything-to-know-about-the-openai-competitor/)
- [https://thenextweb.com/news/mistral-ceo-open-source-enterprise-warning](https://thenextweb.com/news/mistral-ceo-open-source-enterprise-warning)
- [https://www.cnbc.com/2024/06/12/mistral-ai-raises-645-million-at-a-6-billion-valuation.html](https://www.cnbc.com/2024/06/12/mistral-ai-raises-645-million-at-a-6-billion-valuation.html)
- [https://www.polytechnique.edu/en/news/mistral-ai-french-ai-nugget-co-founded-two-x-alumni-raised-eu500-mlns-2023](https://www.polytechnique.edu/en/news/mistral-ai-french-ai-nugget-co-founded-two-x-alumni-raised-eu500-mlns-2023)
- [https://economictimes.indiatimes.com/tech/artificial-intelligence/first-french-ai-billionaires-emerge-after-11-7-billion-mistral-funding-round/articleshow/123829197.cms](https://economictimes.indiatimes.com/tech/artificial-intelligence/first-french-ai-billionaires-emerge-after-11-7-billion-mistral-funding-round/articleshow/123829197.cms)
- [https://aiineurope.co/news/mistral-ai-three-billion-euro-raise-twenty-billion-valuation-2026-06-19](https://aiineurope.co/news/mistral-ai-three-billion-euro-raise-twenty-billion-valuation-2026-06-19)

---
*由 biz.saaaai.com 商业模式情报站自动生成 · 2026-08-09*
