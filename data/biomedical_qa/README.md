# 试点文献与开发样本

- `sources.json`：九篇候选文献的来源、许可线索、本地文件摘要、质量标记与尚待完成的关联核查。
- `regression_cases.jsonl`：10 个由助手初审问题整理的定向回归案例，均待领域审核。
- `assistant_fact_review_v1.jsonl`：46 个回答候选片段的助手初审记录，尚待领域审核。
- `assistant_domain_review_v1.jsonl`：55 条问答样本的助手初步领域审核建议。专家尚未签字；说明见 [助手领域审核报告](../../docs/biomedical-assistant-domain-review.md)。该文件不是训练准入。
- `review_candidates_p05.jsonl`：12 条基于 P05 新论文的待领域审核候选题；已参与探索性检索，不能作为未公开盲测。
- `dev_examples.jsonl`：22 条基于 P02 指定证据范围的开发样本草稿，包括可回答、证据边界和不可回答问题。

样本由助手依据指定正文段落构建并初审，尚未经过领域专家审核，也没有逐项复核图像原文；不是训练集、验证集或盲测集，不得用于报告医学能力。人工审核时应对照原文与图注，检查每个事实、范围和出处，并填写审核者、日期及审核结果；需要修改时保留修订记录。

当前受版本管理的文件不包含文献全文。P02、P03 和 P05 的原文与段落索引在已忽略的 `data/local/` 目录；三篇均有 CC BY 4.0 许可线索，第三方材料及具体用途仍需核查。P03 原文存在疑似单位和标题笔误，本地检索尚未自动屏蔽，目前仅供人工阅览，暂不要将 P03 索引接入自动问答或用于训练。P01 两处来源的许可表述冲突，P04 再利用许可不明确，均未入索引。候选分组尚未锁定；不要从这些开发样本派生测试题。

逐篇研究范围、证据位置和许可核查过程见 [文献档案](../../docs/biomedical-literature-catalog.md)。

逐题初审和领域审核要求见 [样本审核记录](../../docs/biomedical-qa-sample-review.md)。

P05 专家审核材料见 [P05 审核表](../../docs/biomedical-p05-domain-review.md)。

P02 回答的 [助手初审报告](../../docs/biomedical-assistant-fact-review.md) 与人类专家审核分开保存。

55 条问答样本的 [助手领域审核报告](../../docs/biomedical-assistant-domain-review.md) 也只是初步建议。专家尚未签字。

P06 新增 7 条训练候选草稿见 [sft_candidates_p06.jsonl](sft_candidates_p06.jsonl)，未经专家审核，不是正式 SFT 数据；P06/P07 来源登记及其未完成的关联、许可核对见 [sources.json](sources.json)。

研究关联自动检查说明见 [研究关联审计](../../docs/biomedical-source-relationship-audit.md)。

10 条样本的助手建议修订见 [样本修订记录](../../docs/biomedical-sample-revision-v1.md)。
