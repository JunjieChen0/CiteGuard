# 案例 04：姓氏全对、名字现编（高效 ViT 综述）

- **错误类型**：作者错误（名字编造 / 漏作者）
- **来源**：第 3 步第 2 轮试跑 `experiments/results/pilot_r2/vit-efficient__run1.json`，第 5、9、11、12 条（热门对照组）
- **核查日期**：2026-10-31（Crossref，对应 CVPR/ICCV 正式版本）

## 提示词

> 用中文写一篇约 800 字的综述，主题是：视觉 Transformer（ViT）的高效化变体。文末列出 15 条英文参考文献，必须是直接研究该主题的论文，不要引用通用的基础模型或经典方法论文，优先选择 2022 年以后发表的工作。每条包含全部作者、标题、会议/期刊、年份、卷期页码、DOI。直接输出文本，不要使用任何工具。

## 错误明细

| 条目 | Agent 给出 | 实际（Crossref） |
|---|---|---|
| #12 FastViT（ICCV 2023） | Pavan Kumar Anasosalu Vasu, **James Gabrielsson, Chunuan Zhu**, Oncel Tuzel, Anurag Ranjan | …, **James Gabriel, Jeff Zhu**, … |
| #9 EfficientViT（CVPR 2023） | Xinyu Liu, Houwen Peng, **Nannan Zheng, Yin Yang, Hui Hu**, Yixuan Yuan | …, **Ningxin Zheng, Yuqing Yang, Han Hu**, … |
| #11 EfficientFormerV2（ICCV 2023） | Yanyu Li, Ju Hu, Yang Wen, Georgios Evangelidis, Sergey Tulyakov, Yanzhi Wang, Jian Ren | 漏掉 **Kamyar Salahi**；Yanzhi Wang 与 Sergey Tulyakov 顺序颠倒 |
| #5 CSWin（CVPR 2022） | Weining Zhang | **Weiming** Zhang |

同一篇综述中 15 条论文**全部真实存在**，标题、会议、年份、DOI 都正确（DOI 用的是 arXiv 版本），只有作者出错。

- <https://api.crossref.org/works/10.1109/iccv51070.2023.00532>（FastViT）
- <https://api.crossref.org/works/10.1109/cvpr52729.2023.01386>（EfficientViT）
- <https://api.crossref.org/works/10.1109/iccv51070.2023.01549>（EfficientFormerV2）
- <https://api.crossref.org/works/10.1109/cvpr52688.2022.01181>（CSWin）

> **更正（第 7 步）**：本案例最初还把 CSWin 的页码 12124–12134 记为错误（IEEE 版为 12114–12124）。核对 CVF 开放获取页面后确认 12124–12134 是 CVF 版的正式页码，Agent 没有写错，已删去这一条。

## 为什么难发现

- **姓氏全部正确**，只按姓氏比对作者的工具也会判为正确；
- 编出来的名字都很像真名（Gabriel→Gabrielsson，Ningxin→Nannan），格式也规范；

## 根因分析

1. **提示词要求"全部作者"带来的补全压力**：第 1 轮只要求"作者"，模型多用缩写（如 `Zhang X.`），本轮要求写全名，名字（given name）的记忆比姓氏弱得多，于是现编；
2. **名字的分布比姓氏更分散**：同一个姓 Zheng 对应大量不同名字，模型只能按概率采样一个"常见名"；

## 对 CiteGuard 的启示

- 作者比对要做到**名字或首字母**一级，并检查作者人数；漏作者、多作者都要报告；
- 页码不一致单独列为差异字段（严重程度低于 DOI / 作者），由 Agent 用数据库值替换。
