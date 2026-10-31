# 候选文献研究关联审计

日期：2026-10-31。本记录说明如何用本地 JATS 全文做可追溯的研究关联信号检查。**自动命中或不命中都不能证明研究独立或可以用于正式训练。**

## 目的

正式医学 SFT 需要按论文及关联研究隔离训练、验证和独立测试数据。现有文献多涉及 K562、Ba/F3 等常见模型，仅比较标题或 DOI 不够。本工具在本地全文上检查三类可复现信号，并生成人工审核表：

1. 参考文献中是否出现其他候选论文的 DOI、PMID 或 PMCID。
2. 作者姓名经规范化后是否完全相同。
3. 正文、元数据和参考文献之外的部分是否同时提到相同的公开数据集编号。

这些信号只用于提示人工核查，不能替代细胞派生链、共享实验、补充材料或许可用途审查。

## 本机结果

对 [sources.json](../data/biomedical_qa/sources.json) 中已有本地 XML 的 7 篇文献（P02、P03、P05、P06、P07、P08、P09）运行审计后：

| 检查项 | 本轮结果 |
| --- | --- |
| 纳入全文的来源 | 7 |
| 未纳入（无本地全文） | P01、P04 |
| 成对比较数 | 21 |
| 直接互引标识 | 0 |
| 完全相同规范化作者名 | 0 |
| 共享公开数据集编号提及 | 0 |

结果保存在本机 `data/local/domain-review/source-relationships-v3.json`，空白人工审核表为 `source-relationships-review-v1.csv`。两份文件被 Git 忽略；重新运行需使用新的输出文件名。

未检出信号不等于独立。例如 P03、P05、P06、P07、P09 均涉及 K562 相关模型，P02、P07、P08 涉及 Ba/F3 或相近系统；细胞来源、耐药建立过程和数据是否共享仍需专家或熟悉领域的人核对。

## 新增候选来源

| 编号 | 研究 | 许可线索 | 当前状态 |
| --- | --- | --- | --- |
| P08 | [Adnan Awad 等，2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8257498/)，DOI 10.1038/s41375-020-01082-4 | CC BY 4.0 | 已建索引；6 条训练候选草稿待审核 |
| P09 | [Tsubaki 等，2017](https://pmc.ncbi.nlm.nih.gov/articles/PMC5503566/)，DOI 10.18632/oncotarget.16314 | CC BY 3.0 | 已建索引；8 条训练候选草稿待审核 |

两篇均未锁定训练或测试用途。P08 包含患者样本与细胞模型；P09 以 K562/IR 等耐药亚系为主。具体训练、分享用途、署名、版本和第三方材料仍需核实。

## 复现命令

```bash
python3 -m sciquarry.source_audit \
  --catalog data/biomedical_qa/sources.json \
  --output data/local/domain-review/source-relationships-new.json \
  --review-sheet data/local/domain-review/source-relationships-review-new.csv
```

程序会核对登记表中的来源文件 SHA-256、PMCID 和 DOI，拒绝覆盖已有输出。人工审核表中的 `status`、审核人和理由需由实际审核者填写；工具不会认证身份或裁决独立性。

## 与正式 SFT 的关系

关联审计通过或未命中，都不能把样本导入正式训练集。正式训练仍需：

1. 核实具体用途下的许可与署名义务；
2. 领域专家审核问答样本和证据；
3. 按关联组隔离训练、验证和独立测试；
4. 锁定基础模型基线后再训练。

专家审核包与填写说明见 [领域审核工作流](biomedical-domain-review-workflow.md)。
