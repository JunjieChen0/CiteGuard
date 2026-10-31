# 案例 02：同一篇论文再次给错 DOI，而且错得不一样（ResNeXt 复现）

- **错误类型**：DOI 指向他文
- **来源**：第 3 步试跑 `experiments/results/pilot/resnet__run1.json`，参考文献第 5 条（热门主题对照组）
- **核查日期**：2026-10-31（doi.org 内容协商 + Crossref）

## 提示词

> 用中文写一篇约 500 字的综述，主题是：深度残差网络（ResNet）及其主要变体。文末列出 8–10 条英文参考文献，每条包含作者、标题、会议/期刊、年份、DOI。直接输出文本，不要使用任何工具。

## Agent 原文

> 5. Xie, S., Girshick, R., Dollár, P., Tu, Z., He, K. Aggregated Residual Transformations for Deep Neural Networks. In: Proceedings of the IEEE Conference on Computer Vision and Pattern Recognition (CVPR), 2017. DOI: 10.1109/CVPR.2017.317

## 真实情况

| 项 | Agent 给出 | 实际 |
|---|---|---|
| 作者、标题、会议、年份 | 如上 | **全部正确** |
| DOI | `10.1109/CVPR.2017.317` | `10.1109/cvpr.2017.634` |
| 该 DOI 指向 | — | *Low-Rank-Sparse Subspace Representation for Robust Regression*（Zhang, Shi, Gao, Cheng），CVPR 2017，pp. 2972–2981 |

- Agent 给的 DOI：<https://api.crossref.org/works/10.1109/CVPR.2017.317>
- 正确 DOI：<https://api.crossref.org/works/10.1109/cvpr.2017.634>

## 与案例 01 对照

| | 冒烟测试（案例 01） | 本次试跑 |
|---|---|---|
| ResNeXt 的 DOI | `10.1109/CVPR.2017.174` | `10.1109/CVPR.2017.317` |
| 指向 | 面部关键点检测论文 | 鲁棒回归论文 |

同一个模型、同一篇论文、两次生成，**给出两个不同的错误 DOI，都能正常解析**。这说明后缀不是"记错了一个固定值"，而是每次现编。同一次输出里另外 8 条 IEEE/Springer/AAAI DOI 全部正确（包括 DenseNet `CVPR.2017.243`），读者更难怀疑这一条。

## 根因分析

1. **DOI 后缀没有语义**：前缀 `10.1109/CVPR.2017.` 能从会议和年份推出来，后缀只能靠记忆，记不住时模型就采样一个格式合法的数字。
2. **"其余都对"带来的信任外溢**：同一列表中 8/9 条完全正确，人工抽查很容易放过这一条。
3. **热门主题同样中招**：错误出在对照组（热门主题），说明问题不只出在冷门领域。

## 对 CiteGuard 的启示

- 必须取回 DOI 指向的元数据并比对标题，不能只检查 DOI 能否解析；
- 修正建议：按标题检索出正确 DOI（本例 Crossref 检索第一条即为原论文，相似度 1.0）。
