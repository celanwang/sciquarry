# 问答样本：助手初步领域审核

日期：2026-10-31。

**这是助手对 55 条待审问答样本作出的初步建议，身份是 `assistant_preliminary_domain_review_pending`。专家尚未签字。** 本文件不是医学正确性结论，不能开始 SFT 或 DPO，也不能把建议抄进正式审核表当作已完成的专家审核。正式表 `data/local/domain-review/qa-v6/reviews.csv` 仍全部为 `pending`。

机器可读记录见 [assistant_domain_review_v1.jsonl](../data/biomedical_qa/assistant_domain_review_v1.jsonl)。本机对照表 `data/local/domain-review/qa-v6/assistant-recommendations.csv` 只供和空白专家表并排查看，列里的 `recommended_decision` 是助手建议，不是专家 `decision`。

## 范围与做法

优先核对最新草稿，再看既有候选和开发题：P06 7 条、P08 6 条、P09 8 条、P05 12 条、P02 22 条。每题只对照该题列出的索引段落，检查所需事实、答案可得性、对象、干预、对照、时间、浓度、单位和重复次数，并标出临床外推、范围扩大、遗漏条件和原文内部不一致。

索引来自 JATS 正文，上标可能被压平。对集落实验的细胞数，另外查看了本地 `PMC8257498.xml` 中的 `<sup>`；该核对写在对应理由里，不能代替专家看 PDF，也不属于题目已经提供的证据正文。

建议只使用这四个值：

| 建议 | 含义 |
| --- | --- |
| `approve_for_expert_confirmation` | 指定段落支持现有事实和范围，可以交给专家确认 |
| `revise` | 在交给专家确认前应先改问题、答案或限制 |
| `exclude` | 建议整题不进入后续专家确认 |
| `uncertain` | 指定材料不足以在修改和确认之间作选择 |

本次没有使用 `exclude` 或 `uncertain`。证据薄、数字是推算出来的，或原文句子有歧义时，使用 `revise`。

## 计数

| 建议 | 条数 |
| --- | ---: |
| `approve_for_expert_confirmation` | 45 |
| `revise` | 10 |
| `exclude` | 0 |
| `uncertain` | 0 |
| 合计 | 55 |

| 来源 | 条数 | 建议修改 |
| --- | ---: | --- |
| P06 | 7 | `candidate-p06-006` |
| P08 | 6 | `candidate-p08-001`、`002`、`003` |
| P09 | 8 | `candidate-p09-001`、`002`、`003`、`006` |
| P05 | 12 | `candidate-p05-008` |
| P02 | 22 | `dev-p02-019` |

## 优先交给专家的问题

1. **`candidate-p08-003`**：问题问每份样品接种多少细胞。索引写的是 “2.5 × 103 cells were re-suspended”，随后 1.1 ml 一式三份铺板，14 天后计数。本地 JATS 的 Colony forming assay 含 `10<sup>3</sup>`，所以上标还原与 XML 一致，但段落没有写出每皿细胞数。建议改写问题或答案，把重悬细胞数、铺板体积和 14 天计数分开。
2. **`candidate-p09-002`**：培养段印出 `100 μg/ml penicillin` 和 `100 U/ml streptomycin`。这一单位分配与常见写法相反，也与 P08 同项目里 Ba/f3 的 `100 U/mL penicillin`、`100 μg/mL streptomycin` 不同。答案只写了抗生素名称。若补浓度，应照段落原文抄，并由专家对照 PDF，不要自行对调。
3. **`candidate-p09-003` 与 `candidate-p09-001`**：方法段是 3 μM 含药维持 2 个月，并称无药条件下表型至少稳定 1 年。结果段只说 6 个月内递增浓度后，以 3 μM 维持和传代。`001` 还多写了原文没有的“约”。两题不能合成成一个未标注的时长。
4. **`candidate-p06-006`**：72 小时后的 FDA 8 µg/mL、PI 20 µg/mL 和 5 µM 与段落一致。染料名按原文作 Hoechst33324，旁边货号为 62249。这是印刷文本，不是索引误写。专家核对货号和 PDF 之前，不要把它改成别的染料名，也不要当成已经规范化的名称进入训练。
5. **`candidate-p05-008`**：句子是 “Cleaved caspase-3 and PARP … were measured by western blotting.” `cleaved` 紧贴 caspase-3，没有写成 cleaved PARP。图 4c 不在指定正文里。建议先收窄措辞，再由专家看图。
6. **`dev-p02-015`**：本题答案中的 203、重复三次和 87 与筛选段一致，因此仍建议交专家确认。同段后文写保留 13 个化合物，其中增加竞争力的 4 个、降低的 8 个。助手没有把 13 改成 12，也没有让答案使用 13。专家需要决定如何处理这一原文内部数目。
7. **`dev-p02-019`**：不能从该段推出“对所有 CML 耐药细胞有效”，这一边界是对的。该段比较的是对伊马替尼更敏感的 BCR–Abl 转化 Ba/F3 和野生型 Ba/F3，不是耐药细胞面板。答案需要写明实验对象。
8. **`candidate-p08-002`**：段落写出 156 个已批准药物和 372 个临床前及研究性化合物。528 是二者相加，原文没有合计；“或”也改变了 and。同段 HPC-LSK 另有 65 个化合物的文库，不能并入 Ba/f3 的文库规模。

另外两项需要专家看见、但当前答案已经把界限写清楚：`candidate-p08-004` 是四例 p190-CML 的一线伊马替尼和原发耐药描述，限制中已禁止外推到全部患者；`dev-p02-011` 与 `dev-p02-022` 把每板 16 个阳性对照孔和独立生物学重复分开。P05 增殖段把 ZFN 写成 ZNF-L/R，`candidate-p05-009` 没有沿用这个拼写。

索引上标压平出现在已核对的位置：P06 共培养密度在 JATS 中为 `1.2 × 10<sup>5</sup>`，索引为 “1.2 × 105”；P08 集落实验为 `10<sup>3</sup>`。`candidate-p06-002` 没有把这个密度写进答案。

## 逐题记录

五项检查的顺序是：问题范围、证据支持、条件与数字、引用对应、风险与局限。`P` = pass，`C` = needs_change，`U` = uncertain。完整理由和原文锚点在 JSONL 中。

| 样本 | 助手建议 | 五项 | 理由摘要 |
| --- | --- | --- | --- |
| `candidate-p06-001` | 建议交专家确认 | PPPPP | HS-5 的 DMEM、10% 胎牛血清、1 mM 谷氨酰胺和 1% 青霉素–链霉素与培养段一致。 |
| `candidate-p06-002` | 建议交专家确认 | PPPPP | 共培养前 24 小时接种于胶原包被 12 孔板；未使用索引里被压平的接种密度。 |
| `candidate-p06-003` | 建议交专家确认 | PPPPP | 共培养中 MSC 用抗 CD73-PE、K562 用抗 CD235A-APC，且在凋亡染色之前。 |
| `candidate-p06-004` | 建议交专家确认 | PPPPP | MSC 球体用 2.5 mg/mL 胶原酶 D 分散成单细胞。 |
| `candidate-p06-005` | 建议交专家确认 | PPPPP | 细胞分裂分析用 CellTrace Violet 标记正常和 CP-CML 的 CD34+ 细胞。 |
| `candidate-p06-006` | 建议修改 | PPUPC | 浓度与 72 小时一致；Hoechst33324（货号 62249）需专家核对后再作为标准名称。 |
| `candidate-p06-007` | 建议交专家确认 | PPPPP | 流式方法段不能确定患者临床缓解；可得性标签用了 insufficient_evidence。 |
| `candidate-p08-001` | 建议修改 | PPCPP | Ba/f3 的 RPMI-1640、10% FBS 和 2 mM L-谷氨酰胺正确，抗生素浓度 100 U/mL 与 100 μg/mL 被省略。 |
| `candidate-p08-002` | 建议修改 | PCPPP | 156 与 372 有原文；528 和“或”需要改，且不要并入 HPC-LSK 的 65 个化合物。 |
| `candidate-p08-003` | 建议修改 | CCCPP | 2.5×10³ 是重悬细胞数的上标还原；段落未给出每皿接种细胞数，14 天计数有依据。 |
| `candidate-p08-004` | 建议交专家确认 | PPPPP | 四例患者一线伊马替尼及原发耐药的例外与结果段一致，并已限制外推。 |
| `candidate-p08-005` | 建议交专家确认 | PPPPP | Ba/f3 与 HPC-LSK 的联合药敏不能确定患者长期缓解。 |
| `candidate-p08-006` | 建议交专家确认 | PPPPP | 细胞系段有 Ba/f3 培养基，没有患者每日伊马替尼剂量。 |
| `candidate-p09-001` | 建议修改 | PCPPP | 6 个月递增和 3 μM 维持有依据；删去“约”，且不要写入方法段的 2 个月或 1 年。 |
| `candidate-p09-002` | 建议修改 | PPCPC | 培养基成分名称有依据；段落印出的青霉素/链霉素单位需按原文标注并请专家核对。 |
| `candidate-p09-003` | 建议修改 | PPCPC | 剂量加倍和 3 μM 培养 2 个月有依据；需同时写明至少 1 年的无药稳定性。 |
| `candidate-p09-004` | 建议交专家确认 | PPPPP | 氨基酸 45–524 的 PCR-SSCP 和 25 个位点的 Invader 均未检出 ABL1 突变。 |
| `candidate-p09-005` | 建议交专家确认 | PPPPP | MET、WNT2、BRAF、EZH2 的扩增描述有依据，且未把“可能重要”写成已证实机制。 |
| `candidate-p09-006` | 建议修改 | PCPCP | 联合诱导死亡和单药未抑制增殖来自两个段落，需分开引用并收紧“不敏感”。 |
| `candidate-p09-007` | 建议交专家确认 | PPPPP | 培养方法段没有患者每日毫克剂量。 |
| `candidate-p09-008` | 建议交专家确认 | PPPPP | K562/IR 细胞实验不能确定 MET 抑制剂带来患者长期缓解。 |
| `candidate-p05-001` | 建议交专家确认 | PPPPP | K562/G01 由 K562 经数月递增伊马替尼筛选；细节在引用文献 42。 |
| `candidate-p05-002` | 建议交专家确认 | PPPPP | 32D 额外补充 1 ng/ml 小鼠 IL-3，没有套到 K562/G01。 |
| `candidate-p05-003` | 建议交专家确认 | PPPPP | CCK-8 吸光度读数为 450 nm。 |
| `candidate-p05-004` | 建议交专家确认 | PPPPP | 处理过的细胞按每孔 2000 个接种于 96 孔板。 |
| `candidate-p05-005` | 建议交专家确认 | PPPPP | 检测重复五次有原文，段落没有说明这是独立生物学重复。 |
| `candidate-p05-006` | 建议交专家确认 | PPPPP | ZFN 凋亡实验使用 K562 和 K562/G01。 |
| `candidate-p05-007` | 建议交专家确认 | PPPPP | 凋亡用流式细胞术，核形态用 DAPI。 |
| `candidate-p05-008` | 建议修改 | PCUPP | western blot 句是 Cleaved caspase-3 and PARP，不能直接把 PARP 也定为切割形式。 |
| `candidate-p05-009` | 建议交专家确认 | PPPPP | 增殖评估为 CCK-8 和集落形成；同段 ZNF 拼写未写入答案。 |
| `candidate-p05-010` | 建议交专家确认 | PPPPP | 培养段只说数月递增，没有 K562/G01 的最终筛选浓度。 |
| `candidate-p05-011` | 建议交专家确认 | PPPPP | 指定细胞实验不能确定 ZFN 联合供体使患者获得长期缓解。 |
| `candidate-p05-012` | 建议交专家确认 | PPPPP | 凋亡与增殖的检测方法分别对应两个结果段；凋亡段另有 DAPI 和 western blot。 |
| `dev-p02-001` | 建议交专家确认 | PPPPP | 比较并混合的是表达 BCR–Abl 的 Ba/F3 与野生型 Ba/F3。 |
| `dev-p02-002` | 建议交专家确认 | PPPPP | 伊马替尼处理 72 小时后，用流式细胞术测量两类细胞比例。 |
| `dev-p02-003` | 建议交专家确认 | PPPPP | 竞争劣势的主体是 BCR–Abl 细胞，读数相对野生型比例。 |
| `dev-p02-004` | 建议交专家确认 | PPPPP | 该细胞竞争段不能确定患者长期缓解。 |
| `dev-p02-005` | 建议交专家确认 | PPPPP | 该段不能确定患者每日毫克剂量。 |
| `dev-p02-006` | 建议交专家确认 | PPPPP | 增强型 GFP 对应 BCR–Abl 细胞，mCherry 对应野生型细胞。 |
| `dev-p02-007` | 建议交专家确认 | PPPPP | 除非另有说明，涉及野生型细胞的实验在有 IL3 的条件下进行。 |
| `dev-p02-008` | 建议交专家确认 | PPPPP | 初始比例为 1.3:1，顺序是 BCR–Abl 比野生型。 |
| `dev-p02-009` | 建议交专家确认 | PPPPP | 初始比例对应生长较慢；1:1 出现在 DMSO 处理 72 小时之后。 |
| `dev-p02-010` | 建议交专家确认 | PPPPP | 竞争筛选的阳性对照伊马替尼为 5 μM。 |
| `dev-p02-011` | 建议交专家确认 | PPPPP | 每块 384 孔板 16 个阳性对照孔，答案没有把孔数当成生物学重复。 |
| `dev-p02-012` | 建议交专家确认 | PPPPP | BCR–Abl 转化细胞对伊马替尼显著更敏感于野生型细胞。 |
| `dev-p02-013` | 建议交专家确认 | PPPPP | 竞争法被描述为显著灵敏于 CellTiter-Glo，段落没有给出倍数。 |
| `dev-p02-014` | 建议交专家确认 | PPPPP | 初筛化合物数为 17,962。 |
| `dev-p02-015` | 建议交专家确认 | PPPPP | 203、三次重复和 87 有依据；同段 13 与 4+8 不一致，答案没有使用 13。 |
| `dev-p02-016` | 建议交专家确认 | PPPPP | 分化分析中伊马替尼 10 μM、DJ34 20 μM。 |
| `dev-p02-017` | 建议交专家确认 | PPPPP | 竞争筛选方法段没有凋亡百分比。 |
| `dev-p02-018` | 建议交专家确认 | PPPPP | 该段给出体外阳性对照 5 μM，没有患者每日剂量。 |
| `dev-p02-019` | 建议修改 | CCPPP | 拒答方向正确，但应写明该段是敏感的 BCR–Abl Ba/F3 对野生型，不是耐药细胞面板。 |
| `dev-p02-020` | 建议交专家确认 | PPPPP | 竞争筛选 5 μM 与分化分析 10 μM 属于不同实验。 |
| `dev-p02-021` | 建议交专家确认 | PPPPP | 有竞争劣势的定性结果；指定段落没有下降百分比。 |
| `dev-p02-022` | 建议交专家确认 | PPPPP | 初始比例 1.3:1 有依据；段落没有独立生物学重复次数。 |

## 结构校验

校验只核对覆盖、来源摘要、建议取值和原文锚点是否出现在指定段落中。它不判断医学对错，也不把助手建议升级为专家审核。

```bash
python3 -m sciquarry.validate_assistant_domain_review \
  --reviews data/biomedical_qa/assistant_domain_review_v1.jsonl \
  --samples data/biomedical_qa/sft_candidates_p06.jsonl \
  --samples data/biomedical_qa/sft_candidates_p08.jsonl \
  --samples data/biomedical_qa/sft_candidates_p09.jsonl \
  --samples data/biomedical_qa/review_candidates_p05.jsonl \
  --samples data/biomedical_qa/dev_examples.jsonl \
  --index data/local/index/P06.jsonl \
  --index data/local/index/P08.jsonl \
  --index data/local/index/P09.jsonl \
  --index data/local/index/P05.jsonl \
  --index data/local/index/P02.jsonl
```

## 专家审核仍待完成

领域人员应对照 PDF、图注和必要的补充材料独立填写 `reviews.csv`。临床表述，尤其是 `candidate-p08-004` 的四例患者，需要相应临床背景的人复核。高风险或有原文内部不一致的题目适合第二位专业人员再看。审核后的修改必须形成新版本并重新绑定审阅，不能只改 `decision` 后导入训练。
