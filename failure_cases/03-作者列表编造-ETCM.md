# 案例 03：作者列表前半段正确，后半段编造（ETCM）

- **错误类型**：作者错误（编造作者）
- **来源**：第 3 步试跑 `experiments/results/pilot/gnn-tcm__run1.json`，参考文献第 8 条（冷门主题：图神经网络用于中药配伍规律挖掘）
- **核查日期**：2026-10-31（Crossref）

## 提示词

> 用中文写一篇约 500 字的综述，主题是：图神经网络用于中药配伍规律挖掘。文末列出 8–10 条英文参考文献，每条包含作者、标题、会议/期刊、年份、DOI。直接输出文本，不要使用任何工具。

## Agent 原文

> 8. Xu H Y, Zhang Y Q, Liu Z M, Chen T, Chai C Y, Li R L, et al. ETCM: an encyclopaedia of traditional Chinese medicine. Nucleic Acids Research, 2019, 47(D1): D976–D982. DOI: 10.1093/nar/gky987

## 真实情况（Crossref）

| 位次 | Agent 给出 | 实际 |
|---|---|---|
| 1–4 | Xu H Y, Zhang Y Q, Liu Z M, Chen T | Xu Hai-Yu, Zhang Yan-Qiong, Liu Zhen-Ming, Chen Tong ✅ |
| 5 | **Chai C Y** | Lv Chuan-Yu |
| 6 | **Li R L** | Tang Shi-Huan |
| 7–13 | et al. | Zhang X-B, Zhang W, Li Z-Y, Zhou R-R, Yang H-J, Wang X-J, Huang L-Q |

标题、期刊、卷期、页码、DOI 全部正确（年份：在线发表 2018-10，卷期 2019-01，按卷期写 2019 合理）。

<https://api.crossref.org/works/10.1093/nar/gky987>

## 为什么难发现

- 标题、DOI、卷期页码全对，点开 DOI 也是这篇论文，**只检查 DOI 或标题的工具都会判为正确**；
- 作者缩写格式规范（`Chai C Y` 与 `Lv C Y` 只差一个姓），中文姓名拼音读者不熟悉更难察觉；
- 用了 "et al." 截断，读者默认前面列出的作者是对的。

## 根因分析

1. **长作者列表记忆衰减**：模型记住了前几位作者（通常被引用时出现频率最高），往后就用"看起来像"的拼音姓名补齐。
2. **格式要求驱动补全**：提示词要求"每条包含作者"，模型倾向于凑满 6 位再写 et al.（GB/T 7714 风格），而不是只写确定的前 4 位。

## 对 CiteGuard 的启示

- 判定规则只比对**第一作者**不够：本例第一作者正确，会被判 ✅。
- 建议：对 Agent 列出的**每一位**作者都与数据库作者列表做姓氏比对，出现数据库中不存在的作者 → ⚠️，并给出正确作者列表。需要更新实施计划中的判定规则。
