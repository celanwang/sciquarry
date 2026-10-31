# 医学科研回答的事实断言核对：试点方案

日期：2026-10-31。该方案用于本地科研问答的开发评估，不是自动医疗事实裁决，也未经过领域专家验证。

## 核对目标

对回答中的每个可核查断言，检查其**引用的指定文献片段**是否支持其内容。确认编号存在只是定位检查；即便编号有效，陈述也可能与原文不符、超出证据范围或遗漏限制条件。一次回答可能包含多个独立断言，不能只给整段一个粗略结论。

这一思路借鉴 [FActScore](https://aclanthology.org/2023.emnlp-main.741/) 将长回答拆分为细粒度事实并检查证据支持，以及 [FEVER](https://aclanthology.org/N18-1074/) 使用支持、反驳和证据不足分类；本项目尚未实现这些论文的完整算法或复现其指标。

## 建议的审核流程

1. **保留上下文**：记录原问题、回答、模型和推理配置、全部提供的证据段落及其来源版本。不能只凭孤立短句丢失否定、比较对象或实验条件。
2. **拆分断言**：人工把回答分成最小可核查陈述；一个句子可能包含实验对象、干预和多个结果，必要时拆成多条，同时保留原句位置。标题、引用和礼貌性文本不自动当作事实。
3. **定位证据**：核查模型给出的引用是否存在、属于本次提供的证据、能否定位到支持该断言的具体句子；证据应保留论文、章节、段落、版本摘要。缺图表或数据时标明需复核，不根据记忆补充。
4. **作出范围内判断**：逐条标记 `supported`（指定证据支持）、`contradicted`（指定证据直接相反）、`insufficient_evidence`（指定证据不能确认或反驳）、`out_of_scope`（超出本次限定范围）或 `not_a_claim`（不是事实断言）。`pending` 表示未审核。引用缺失是单独字段，不能直接当作事实错误或正确。
5. **保留审核轨迹**：记录精确证据位置、比较理由、风险类型、审核人、日期和修订；对于药物剂量、实验单位、比较方向及临床外推，优先进行领域复核。证据不充分不等于该断言在现实中为假。

风险标签建议覆盖：实验对象与对照组、模型或干预混淆、比较方向、数值与单位、重复次数、证据范围、过度概括、临床外推和引用位置。若后续统计支持率，应先定义可审核断言分母、排除项及审核者分歧处理方式；当前没有领域审核数据，不计算事实正确率。

## 当前可用的人工审核准备工具

`sciquarry.claim_review`可以将已有证据限定回答按句号、问号等切分成**待人工整理的候选片段**，并保留提供给模型的证据段落定位及引用编号检查结果。它不会判断事实真假，也不保证片段就是单一原子断言；一个片段可能包含多个结论、标题或没有证据对应的句子。所有输出的审核结论、审核者与日期默认留空。

在已有本地 P02 索引和完整回答评估结果时，从仓库根目录执行（请使用新的输出文件名）：

```bash
python3 -m sciquarry.claim_review \\
  --answers data/local/evaluations/answer-v4.jsonl \\
  --index data/local/index/P02.jsonl \\
  --output data/local/evaluations/claim-review-new.jsonl
```

本次处理 `answer-v4` 得到 46 个候选片段，分布于 22 个回答；**46 是自动切分结果，不是 46 个经过确认的独立断言**。本机结果为 `data/local/evaluations/claim-review-candidates-v2.jsonl`，被 Git 忽略。工具会比对原评估所用索引的 SHA-256，拒绝使用不同版本或不完整的回答结果；审核前仍需确认论文内容及许可。

可观察到，`dev-p02-022` 的一个片段把 16 个阳性对照孔称为 16 次独立生物学重复，尽管引用编号存在；所给段落不能支持这一重复次数。应区分“证据未说明”与“证据证明相反”，并交领域专家复核。`dev-p02-009` 则在 72 小时比例的陈述中未明确 DMSO 条件；审核应检查被省略的限定是否改变解释。

## 人工审核工作区

已在本机生成空白审核材料 `data/local/evaluations/claim-review-packet-v1.md`，包含 22 个完整回答、对应原文段落和 46 个候选片段。该文件只是初始快照，不显示后续审核进度；本地文件被 Git 忽略，分享前需核对各文献许可与署名。

本机准备好候选片段后，也可以使用新文件名重新导出空白材料：

```bash
python3 -m sciquarry.review_workspace export \
  --candidates data/local/evaluations/claim-review-candidates-v2.jsonl \
  --answers data/local/evaluations/answer-v4.jsonl \
  --index data/local/index/P02.jsonl \
  --output data/local/evaluations/claim-review-packet-new.md
```

通过工作区可以查看指定候选、原问题、完整回答和提供给模型的证据：

```bash
python3 -m sciquarry.review_workspace show \
  --candidates data/local/evaluations/claim-review-candidates-v2.jsonl \
  --answers data/local/evaluations/answer-v4.jsonl \
  --index data/local/index/P02.jsonl --id dev-p02-022:2
```

查看记录数而不创建审核文件：

```bash
python3 -m sciquarry.review_workspace summary \
  --candidates data/local/evaluations/claim-review-candidates-v2.jsonl \
  --answers data/local/evaluations/answer-v4.jsonl \
  --index data/local/index/P02.jsonl \
  --reviews data/local/evaluations/human-reviews.jsonl
```

经实际审核后，审核者可用 `record` 追加一条记录，指定候选 ID、从候选原文中选取的精确断言、判断、审核者和理由。`supported` 与 `contradicted` 还要求提供本次给模型的段落编号及该段中的精确原文片段；`insufficient_evidence`、`out_of_scope` 和 `not_a_claim` 同样要求理由。以下是**填写格式示例，尚未执行，也不是专家结论**；审核者需根据自己的判断替换占位符：

```bash
python3 -m sciquarry.review_workspace record \
  --candidates data/local/evaluations/claim-review-candidates-v2.jsonl \
  --answers data/local/evaluations/answer-v4.jsonl \
  --index data/local/index/P02.jsonl \
  --reviews data/local/evaluations/human-reviews.jsonl \
  --id dev-p02-022:2 --claim '16次独立生物学重复' \
  --decision insufficient_evidence --reviewer REVIEWER_ID \
  --note '请替换为审核者自己的判断理由'
```

工具校验候选、回答和索引文件的 SHA-256，并检查断言与证据引文是否能在对应文本中精确找到；**它不检查证据是否真的支持判断，也不验证审核者身份或专业资质**。当前每条记录只能绑定一个证据段落和一个引文；需要联合多个段落才能判断的断言应拆分或线下复核，不能视为工具已完整覆盖。不同审核者可分别记录；同一审核者修订同一断言时，需用 `--supersedes` 指向其当前事件 ID。错误记录可用 `withdrawn` 与 `--supersedes` 撤回，再重新记录；原记录保留。

`summary` 只统计有无记录，不代表每个候选中的全部断言已经审核。当前日志采用本地追加写入，不提供多进程并发锁、身份认证或防篡改签名；多人审核时应串行写入，保留原始日志与备份，不把该原型当作生产审核系统。

## 后续验证

将模型裁判或自然语言推断用于辅助排序前，先由领域审核者标注一组覆盖上述风险的独立样本，明确证据和分歧，再与人工判定逐项比较，并报告支持、反驳、证据不足各类的错误以及无法判断比例。多模型一致也不能替代专业审阅；未经验证的自动标签不应作为医学事实或正式评测金标准。
