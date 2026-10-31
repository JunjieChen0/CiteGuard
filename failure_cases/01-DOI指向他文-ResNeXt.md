# 案例 01：DOI 指向其他论文（ResNeXt）

- **错误类型**：DOI 指向他文
- **来源**：第 1 步冒烟测试（`experiments/agent_runner.py`，DeepSeek 后端的隔离 Claude Code，无工具）
- **核查日期**：2026-10-31（Crossref）

## 提示词

冒烟测试时要求 Agent 简介 ResNet 系列并附参考文献（热门主题）。

## Agent 原文（相关条目摘录）

> *Aggregated Residual Transformations for Deep Neural Networks.* CVPR 2017. DOI: 10.1109/CVPR.2017.174

> 注：冒烟测试的原始 JSON 未保存，以上仅为交接文档记录的要点（标题、会议、年份、DOI），作者字段未记录。当时记录为"格式、会议、年份全对"，只有 DOI 错误。

## 真实情况

| 项 | Agent 给出 | 实际 |
|---|---|---|
| DOI | `10.1109/CVPR.2017.174` | `10.1109/cvpr.2017.634` |
| 该 DOI 指向 | — | *Interspecies Knowledge Transfer for Facial Keypoint Detection*（Rashid, Gu, Lee），CVPR 2017 |

- Agent 给的 DOI：<https://api.crossref.org/works/10.1109/CVPR.2017.174> · <https://doi.org/10.1109/CVPR.2017.174>
- 正确 DOI：<https://api.crossref.org/works/10.1109/cvpr.2017.634> · <https://doi.org/10.1109/cvpr.2017.634>（CVPR 2017，pp. 5987–5995）

## 为什么难发现

格式合法，前缀 `10.1109/CVPR.2017.` 与会议、年份完全吻合，**DOI 也能正常解析**。读者不点开就不会发现；即使只校验"DOI 是否存在"的工具也会判为正确。

## 根因分析

1. **DOI 是无语义的编号**：模型能从训练数据中学到 IEEE CVPR 2017 的 DOI 前缀模式，但后缀数字（`.174` / `.634`）与论文没有可推断的对应关系，只能死记；记忆不牢时就生成一个"格式正确"的数字。
2. **生成目标是"看起来完整"**：提示词要求每条都带 DOI，模型倾向于补全字段而不是承认不知道。
3. **无检索能力**：DeepSeek 后端不支持 WebSearch，Agent 无法核对。

## 对 CiteGuard 的启示

- 不能只验证 DOI 可解析，必须取回 DOI 对应元数据，**比对标题相似度**；
- 不一致时用标题检索找到正确 DOI，作为修正建议交回 Agent。
