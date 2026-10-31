# 医学问答领域审核与 SFT 数据准备

状态：审核工作包已准备，**尚无领域专家审核记录**；当前没有正式医学 SFT 训练数据。本文件面向项目负责人和参与审核的专业人员，记录如何交接、填写、检查和处理审核结果。

## 本批材料与范围

本机工作包 `data/local/domain-review/qa-v7/` 包含：

- `packet.md`：55 道问题、草拟回答及对应的原文段落。P02 开发题 22 条、P05 既有候选题 12 条、P06 新训练候选草稿 7 条、P08 草稿 6 条、P09 草稿 8 条。所有内容均待领域审核。
- `reviews.csv`：每题一行的空白审核表，供审核人填写。`sample_id` 必须与审核包一致。
- `review-form.html`：同屏展示问题、草拟答案与证据的本地填写页；可离线打开并下载更新后的 `reviews.csv`，也可用本机 `serve` 直接写回表格。
- `cases.jsonl`：与审核包绑定的原始题目、参考答案和证据快照。
- `manifest.json`：样本、索引和快照摘要；用于发现文件变化，不是防篡改签名。
- `reviewer-instructions.md`：可随包交付的专家填写说明。
- `source-attribution.md`：本包文献的作者、来源、许可链接和修改说明。分享前仍需核实版本、第三方材料和具体用途。

P02/P05 已用于公开开发或探索；P06/P08/P09 草稿也已进入审核包。它们都不是全新盲测题。P02/P05 来源受现有训练准入保护；新增草稿也不是已审核样本。该包是**审核工作包，不是训练数据**。其中 10 条已按助手初审建议修订，说明见 [样本修订记录](biomedical-sample-revision-v1.md)。

P02 的模型回答事实断言另有本机材料 `data/local/evaluations/claim-review-packet-v1.md`。这与本包的参考答案审阅是两个工作：前者审核模型已经输出的具体断言，后者审核样本问题、证据与参考答案。不要将某一项通过视为另一项通过；事实断言记录方法见 [事实审核方案](biomedical-fact-review-design.md)。

## 专家分工与校准

1. 推荐由熟悉血液肿瘤研究、细胞培养与药物实验方法的专业人员，先独立审核每篇少量样题，核对实验对象、组别、对照、终点、时间、浓度、单位、重复次数、检测方法和引用对应。
2. 再讨论分歧并记录规则后，继续逐题审核。涉及临床解释或患者疗效的问题，还需具备相应临床背景的人员评估。高风险或存在分歧的项目适合由第二位专业人员复核。
3. 判断仅限指定证据；需要额外文献、图表或补充材料时，在审核表中记录来源、位置及其与答案的关系。不能把索引未覆盖的图表或全文外知识默认作为已给证据。
4. 原文可能存在笔误、缺失或研究限制。区分“证据未说明”和“证据证明相反”，不根据猜测修正。细胞实验结论不能直接表述为患者疗效。

专家的人选和资质由项目方确认。工具中的姓名、背景和结论均为人工声明；本地脚本不会认证身份，也不会判断专业结论是否正确。

## 审核表填写

推荐使用本地填写页（问题、证据与表单同屏）：

```bash
python3 -m sciquarry.domain_review serve \
  --packet data/local/domain-review/qa-v7
```

浏览器打开终端打印的本机地址（默认 `http://127.0.0.1:8765/`）。顶部填写审核人、背景与日期后，逐题选择判断并点“保存本题”，结果直接写入该工作包的 `reviews.csv`。“检查整表”会运行与 CLI 相同的字段一致性校验。此服务默认只监听本机，不认证身份，也不判断专业结论。

也可直接打开包内 `review-form.html`（离线）。离线保存会下载完整 `reviews.csv`，请用该文件替换工作包中的同名文件。仍可用表格软件编辑 `reviews.csv`；保持 UTF-8、列名和 `sample_id` 不变。按填写页、`packet.md` 或表格中的对应 ID 阅读问题、草拟回答与证据，填写：

| 字段 | 可填写内容 |
| --- | --- |
| `decision` | `approve` 通过、`revise` 需修改、`exclude` 排除；尚未完成整题时保留 `pending` 和空白字段。 |
| `check_question_scope` | 问题是否明确、是否限定在证据范围。 |
| `check_evidence_support` | 每项事实是否被相应证据支持。 |
| `check_conditions_and_numbers` | 对象、组别、时间、数字、单位和实验条件是否正确。 |
| `check_citation_alignment` | 证据定位及各项事实的引用是否对应。 |
| `check_risk_and_limits` | 不确定性、拒答和研究局限是否适当。 |
| 以上五项取值 | `pass`、`needs_change`、`uncertain` 或 `not_applicable`；未完成保持 `pending`。`not_applicable` 需在理由中说明。 |
| `reviewer` / `reviewer_background` | 实际审核人及相关专业背景。 |
| `reviewed_at` | 审核日期，格式 `YYYY-MM-DD`。 |
| `rationale` | 具体判断理由；通过时也说明核对范围，不适用项目应解释。 |
| `proposed_changes` / `corrected_answer` | 需修改时至少填写一项；可以分别提出问题、证据或答案的修改。 |
| `additional_evidence` | 如使用了指定片段之外的材料，记录来源、定位和用途。 |

`approve` 要求五项均为 `pass` 或 `not_applicable`。`revise`/`exclude` 也需完成五项检查、审核人、背景、日期与理由；无法判断时使用 `uncertain` 并说明。保持 `pending` 的行需全部保留初始值；如要保存未完成的工作，可另存草稿，完成后再填写正式审核表。

仅修改 `reviews.csv`；不要修改 `cases.jsonl` 或 `packet.md`。每位审核人使用一份独立的完整工作包，保留各自结果；合并结论或处理分歧时保留原表，不能覆盖其他人的记录。此文件工作流不提供认证、电子签名、并发编辑锁或自动分歧裁决。

## 工作包生成及检查

重新生成时使用新的输出目录，避免覆盖既有审核结果：

```bash
python3 -m sciquarry.domain_review export \
  --samples data/biomedical_qa/dev_examples.jsonl \
  --samples data/biomedical_qa/review_candidates_p05.jsonl \
  --samples data/biomedical_qa/sft_candidates_p06.jsonl \
  --samples data/biomedical_qa/sft_candidates_p08.jsonl \
  --samples data/biomedical_qa/sft_candidates_p09.jsonl \
  --index data/local/index/P02.jsonl --index data/local/index/P05.jsonl \
  --index data/local/index/P06.jsonl --index data/local/index/P08.jsonl \
  --index data/local/index/P09.jsonl \
  --output data/local/domain-review/qa-new

python3 -m sciquarry.domain_review check \
  --packet data/local/domain-review/qa-new

python3 -m sciquarry.domain_review form \
  --packet data/local/domain-review/qa-new

python3 -m sciquarry.domain_review serve \
  --packet data/local/domain-review/qa-new
```

`export` 会同时生成空白 `reviews.csv` 与离线 `review-form.html`。`form` 可在不重建工作包的情况下刷新填写页。导出前会校验问题所指证据与来源摘要是否匹配；检查会确认快照完整、审核 ID 一一对应、表格字段和结论一致，并汇总各状态。该工具不读取专家身份凭证、不比对外部论文原文与索引、也不判断事实真伪。每份工作包的 `source-attribution.md` 应根据实际来源另行准备，并在分享前复核；此文件不属于自动生成或自动校验的内容。

## 新来源与正式 SFT 待办

- **P06**：[Busch 等，2023](https://pmc.ncbi.nlm.nih.gov/articles/PMC10685629/)，DOI `10.1186/s12964-023-01363-2`。已有 7 条仅限正文段落的训练候选草稿，尚未审定来源许可的具体训练用途或医学内容。
- **P07**：[Troadec 等，2015](https://pmc.ncbi.nlm.nih.gov/articles/PMC4504225/)，DOI `10.1186/s12929-015-0163-x`。已建立本地索引，暂未编题或确定用途。
- **P08**：[Adnan Awad 等，2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8257498/)，DOI `10.1038/s41375-020-01082-4`。已有 6 条训练候选草稿；含患者样本与细胞模型，回答须区分证据层级。
- **P09**：[Tsubaki 等，2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5503566/)，DOI `10.18632/oncotarget.16314`。已有 8 条训练候选草稿；以 K562/IR 耐药亚系为主，许可线索为 CC BY 3.0。
- 对已索引来源的自动关联信号检查见 [研究关联审计](biomedical-source-relationship-audit.md)。自动未命中不能证明独立；共享细胞系仍需人工审核。
- 审核后的修改必须形成新版本并重新绑定审阅，不能只修改 `decision` 直接导入训练。准备更多合适来源并完成训练、验证、独立测试的关联分组、近重复排查、权限记录和专家审核后，再固定基线及评估规则。

当前交接包也可使用本机压缩文件 `data/local/domain-review/expert-qa-v7.zip`；分享前请核对许可与署名材料。
