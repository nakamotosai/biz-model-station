# Wiz：四人军中密友从微软出走，5年做到320亿被谷歌吞下的云安全独角兽

> 🛤 发家路径 | **SaaS/企业软件** · 跨地区 · 独角兽 · ToB

## 🚀 起步缘由

拉帕波特2001年入伍，进以色列国防军Talpiot尖子项目与Unit 81尖刀技侦单位，再升任Unit 8200（以色列版NSA）上尉。在军中他遇到Roy Reznik、Ami Luttwak、Yinon Costica——四人日后成为终身创业伙伴。2012年他们第一次合体创立Adallom，专注SaaS数据安全，三年后被微软以约3.2亿美元收购。在微软的5年他们做Azure安全栈，学到Adallom时代绝对没有的纪律：照单全收客户需求会堆出庞大技术债，他们曾在微软从Adallom身上砍掉75%功能才换来可扩展。2020年1月四人决定从微软出走，想做一个支持AWS、Azure、GCP多云的『瑞士』式安全扫描平台——这是Adallom没做过、微软内部也做不出的中立产品。

**创办人**：Assaf Rappaport（CEO）、Ami Luttwak（CTO）、Roy Reznik（工程 VP）、Yinon Costica（产品 VP）——四人以色列军中密友，曾共同创立 Adallom 并一起进微软 · **公司**：Wiz, Inc.（以色列—美国云安全公司，2026年3月起并入 Google Cloud）

## 📈 发家里程碑

- **2012-2015** 首次合体（PMF）
  - 四人军中退役后首次合体创业，创立Adallom做云访问安全代理（CASB），保护SaaS应用数据。他们当时信奉『对客户每个需求都答应』，快速堆功能也快速堆技术债。2015年7月微软以约3.2亿美元收购Adallom，四人一起进微软。这笔规模不大的退出为他们埋下第二次创业的弹药：团队完整保留、一起进大厂学打法、掌握了企业级可扩展的内部视角。
- **2015-2019** 微软学纪律（转折）
  - 拉帕波特34岁被任命为微软以色列研发中心负责人，掌管约1500人，并领导云安全事业部。四人在这5年从『照单全收』转向『不为了短期客户砍掉可扩展性』，亲手从Adallom遗产中删掉75%功能。Luttwak后来总结：『工程师不必听产品的——给客户想要的，但若没法规模就不做。』这是Wiz产品能在18个月内跑出1亿美元ARR的底层基因。
- **2020年初** 方向试错（失败）
  - 2020年1月四人离开微软，公司最初取名 Beyond Networks，定位云端网络安全。几周后他们发现方向太窄：客户CISO访谈里反复说，真正的痛点不是网络层，而是多云环境里多种工具没法让非安全专家用、没法跨云看全貌。他们果断改方向、改名Wiz（『越通用越好，万一再改方向IRS那边也不至于太痛苦』），从网络层升到多云风险扫描。这是Wiz创业史上最关键的一次舍得，也是初期最痛苦的一次自我否定。
- **2020年3月-2021年** 疫情逆势（转折）
  - 疫情爆发、全球经济停滞，团队全员远程起步。拉帕波特事后坦承最初几个月一直在质疑自己是否该离开微软，团队成员家人也在劝退。但疫情反向助攻：全球CISO暂停一切本地项目，全力转向云端，Wiz首日即跨国远程的产品反而跑得比集中办公还快。拉帕波特说：『如果让我在历史上任意挑一个时点去创立一家云端安全公司，我会选2020年3月。』
- **2020年12月-2022年8月** 破亿ARR（PMF）
  - 2020年12月Wiz从隐身出来即完成1亿美元A轮（Index、Sequoia、Insight、Cyberstarts）。2022年8月，Wiz宣布ARR从2021年2月的约100万美元做到1亿——18个月，史上最快达到1亿美元ARR的软件公司。9个月后ARR再翻倍至2亿。Fortune 100中45%成为客户。Agentless（无代理）跨云扫描是技术差异点：不需要装agent即可一次性看穿AWS、Azure、GCP、OCI与Kubernetes里的风险组合。
- **2021-2024** 漏洞扬名（增长）
  - Wiz研究团队连续披露高影响云漏洞：ChaosDB（Azure Cosmos DB可下载删除他库数据，波及数千Azure客户）、OMIGOD（Azure服务内嵌OMI代理远程未授权执行）、NotLegit（Azure App Service源码暴露）、ExtraReplica（Azure PostgreSQL提权跨库访问）、AttachMe（Oracle Cloud卷隔离失效）、BingBang（Azure AD配置错误改动Bing搜索结果可盗Office365凭据）、以及2025年披露DeepSeek敏感数据库外网暴露。每次披露都给云厂商上眼药、同时把Wiz钉上行业议程——研究即营销，成了Wiz最便宜也最贵的一路护城河。
- **2024年5月** 尽调告吹（失败）
  - 2024年4月Wiz完成对Cloud检测响应初创公司Gem Security约3.5亿美元的收购，紧接着传出将收购另一家云安全公司Lacework。但尽调进入5月后交易崩盘。Lacework最终被卖给Fortra。这是Wiz在高速并购扩张里第一次明面上的踩坑——『不是所有想吃的都能咽下』，为后续更克制的收购纪律埋下伏笔。
- **2024年3月-7月** 婉拒23亿（拐点）
  - 2024年3月谷歌CEO Sundar Pichai发邮件给拉帕波特表达收购兴趣，拉帕波特忙到完全漏看，数月后才在一次安全会议后被点醒『查一下收件箱』。5月拉帕波特与Costica去Googleplex见Pichai与Google Cloud CEO Thomas Kurian，谷歌随后开出230亿美元邀约——约为当时估值的2倍。团队拉了高盛等顾问算账，7月底拉帕波特决定婉拒，坚持走IPO。当时被指『目光分歧』『放走十年级大单』，但事实证明这是史上回报最高的一次拒绝。
- **2025年3月18日** 加码320亿（转折）
  - IPO市场转冷、特朗普新政府对并购更友好，谷歌重返谈判桌。2025年3月18日谷歌宣布以320亿美元全现金收购Wiz，另附35亿美元反向分手费——如果交易被监管否决谷歌仍付钱。这是科技史上十大并购之一、史上最大网络安全收购、谷歌130年历史上最贵并购。拉帕波特说：『第二次因为已经熟了团队和文化，say yes自然得多。』
- **2026年2-3月** 并入谷歌（增长）
  - 2026年2月10日欧盟反垄断机构无条件批准收购，扫除最后重大监管障碍。2026年3月11日收购正式完成，Wiz约2000员工并入Google Cloud，团队保留相对独立运营。Wiz创始人们每人预计套现超30亿美元，以色列科技史上最大并购案画上句号。

## 🔀 转折点

- Beyond Networks方向太窄，四人靠CISO访谈果断舍网络层改做多云风险扫描并更名Wiz—— 这是创业史上最关键的一次舍得
- 微软5年把『照单全收』的Adallom纪律改成『不为短期砍可扩展性』，奠定了Wiz 18个月破亿ARR的产品底层
- 拉帕波特漏看Pichai邮件数月才碰面，反而促成首轮23亿、次轮32亿——『不赴会、不回信』成了Wiz最大的幸运符号
- 2024年7月婉拒谷歌23亿坚持IPO，9个月后谷歌加码至320亿全现金含35亿分手费回报
- 疫情爆发全员远程起步，反被CISO暂停本地项目全转云端的风口精准接住

## 🕳️ 失败与踩坑

- Beyond Networks初创定位为云端网络安全，几周内发现方向太窄，被迫第二个月就自我否定、改方向、更名
- Lacework收购进入尽调后于2024年5月崩盘，是Wiz高速并购扩张中第一次明面踩坑
- Wiz成立头几个月拉帕波特一直在后悔离开微软，团队成员家人都劝退，险些在公司还没跑出来就集体撤退
- 3年内走马3任CMO，包括从Okta来的资深CMO仅9个月即离任，反映出超高速增长团队的治理张力
- 拉帕波特漏看Sundar Pichai的收购意向邮件数月，若非有第三方在会议间提醒点醒，几乎错失整轮谈判窗口

## 🔑 关键成功要素

- 四人军中密友三次长期共事（Unit 8200→Adallom→微软→Wiz），团队血缘与共同作战比任何个人履历都更定输赢
- Agentless无代理跨云扫描技术：不装agent即可一次看穿AWS、Azure、GCP、OCI与K8s的风险组合，技术差异点直接锁定Fortune 100顶级客户
- 研究即营销：Wiz研究团队连续披露ChaosDB、OMIGOD、BingBang、DeepSeek外泄等高影响云漏洞，把每一次披露都变成行业议程与客户信任资产
- 微软5年学到的可扩展纪律：『工程师不必听产品的』，给客户想要的，但若没法规模就不做
- 多云中立『瑞士』定位：AWS、Azure、GCP、OCI一视同仁，避免被任一云厂绑架
- 聚焦Fortune 100顶级客户从第一天起就做大单，而不是从中小客户卷起
- 2024年7月敢对23亿美元邀约说不——团队对自身商业基础仍在加速有强烈判断，敢于委屈短期最大值换取更多势能

## 📚 经验教训

- 二次创业的可扩展纪律比一次创业的照单全收值钱得多——Adallom被砍掉75%功能反而是Wiz破亿ARR的底层基因
- 错过一封CEO邮件、错过一次会议不等于丢客户，反可能成为下次更高价邀约的留白——拉帕波特本人也说『我最大的机会多半从我漏赴某个会议开始』
- 拒绝史上最大软件并购邀约若商业基础仍在加速，就可能把委屈价格换成更高估值——从23亿到320亿仅9个月
- 研究即营销是云安全最便宜也最贵的护城河：不烧钱也能把公司钉上行业议程，但需要顶级研究血液持续供给
- 团队血缘+长期共事年限比个人单一履历更能定输赢，Unit 8200系出合伙人制是Wiz能5年长成300亿的关键单一变量
- 疫情风口不是所有公司都能接——首日即全员远程、首日即跨国的产品形态自我筛选出了能在此中加速的基因

## 📊 核心数据

- **2022年8月ARR**：1亿美元（史上最快破亿ARR的软件公司，18个月达成）
- **2023年ARR**：3.5亿美元
- **2024年ARR**：约5亿美元
- **Fortune 100 客户占比**：45%
- **以色列科技并购史上**：涉及以色列初创公司最大的科技并购案
- **估值时间线**：2021年10月60亿 → 2023年2月100亿 → 2024年5月120亿 → 2025年3月被谷歌320亿美元收购
- **员工规模 2025年**：约2000人
- **收购对价**：320亿美元全现金，另附35亿美元反向分手费
- **融资总额**：约19亿美元

## ⚔️ 竞争对手 / 同行

Wiz在云安全赛道正面对手包括CrowdStrike、Palo Alto Networks（Prisma Cloud）、Orca Security、Lacework（后卖给Fortra）、Check Point、Zscaler等。其中Orca Security与Lacework是路径最像的直接竞争者，同样做Agentless云安全扫描；Palo Alto Networks凭借Prisma Cloud云安全组合与威胁情报网络做平台级压制。并入Google Cloud后，Wiz一边继续服务AWS、Azure客户保持多云中立承诺，一边成为谷歌云对抗AWS和Azure安全生态的王牌——这既是护城河也是利益冲突风险点。

## 🔗 来源

- [https://en.wikipedia.org/wiki/Wiz_(company)](https://en.wikipedia.org/wiki/Wiz_(company))
- [https://en.wikipedia.org/wiki/Assaf_Rappaport](https://en.wikipedia.org/wiki/Assaf_Rappaport)
- [https://fortune.com/article/wiz-cloud-security-ceo-assaf-rappaport-google-sundar-pichai/](https://fortune.com/article/wiz-cloud-security-ceo-assaf-rappaport-google-sundar-pichai/)
- [https://www.indexventures.com/perspectives/cloud-captains-how-assaf-rappaport-and-his-extraordinary-co-founders-built-the-worlds-fastest-growing-company/](https://www.indexventures.com/perspectives/cloud-captains-how-assaf-rappaport-and-his-extraordinary-co-founders-built-the-worlds-fastest-growing-company/)
- [https://www.forbes.com/sites/alexkonrad/2023/08/08/nobody-beats-wiz-meet-the-aggressive-10-billion-startup-shaking-up-cloud-security/](https://www.forbes.com/sites/alexkonrad/2023/08/08/nobody-beats-wiz-meet-the-aggressive-10-billion-startup-shaking-up-cloud-security/)

---
*由 biz.saaaai.com 商业模式情报站自动生成 · 2026-08-09*
