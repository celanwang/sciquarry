# 医学问答定向回归：微调前开发检查

日期：2026-10-31。本记录是开发对照，**不是独立测试或领域专家审核**。案例取自同一篇 P02 论文及已参与调试的公开样本，问题判断来自[助手事实初审](biomedical-assistant-fact-review.md)，均待领域复核。

## 目的和输入

将初审中需要关注的问题整理为 10 个[定向回归案例](../data/biomedical_qa/regression_cases.jsonl)，每个案例引用原样本、助手初审 finding、指定证据及待人工核对的要点；案例不是训练数据、专家标签或自动通过条件。

本轮使用同一个 P02 索引和 22 个开发问题，让本机 MLX-LM 上的 Qwen3-4B 再次在每题指定证据范围内作答；对照 `answer-v4` 基线和 `answer-v5-pretraining`。模型标识、服务地址、思考开关、temperature、输出上限、样本/索引摘要及 10 条案例的服务 fingerprint 均一致。两次运行的代码摘要分别记录在对照文件中；摘要不同不自动意味着输入或模型变化。

本次检查了本机模型配置、分词器和三个权重分片的 SHA-256，均与此前本地记录一致；但上游 ModelScope commit 未记录，仅凭本机文件及服务 fingerprint 不能证明完整上游版本或服务进程内部状态。

完整回答保存在本地 `data/local/evaluations/answer-v5-pretraining.jsonl`；逐题对照保存在 `data/local/evaluations/targeted-regression-v1.jsonl`。这些文件、原文和模型权重不进入 Git，若本机文件丢失，仓库中的摘要不能重新构造历史回答。

## 本轮结果

22 个问题均成功结束。定向比较覆盖 10 个案例，**10 个案例的新回答与原基线逐字相同**；由于没有对模型、提示词做新的调整，这一轮用于验证流程和保留现有问题，不表明问答质量提升。引用或复核提示只检查格式或特定表达，不能自动验证事实。

| 回归案例 | 待人工复核重点 | 本次对照 |
| --- | --- | --- |
| reg-p02-004 | 区分药物与细胞的竞争劣势主体；缺失临床结论时只限定到所给片段 | 回答与基线一致；语义待人工复核 |
| reg-p02-005 | 未提供患者剂量时限定为指定片段内未知；不编造患者用药剂量 | 回答与基线一致；语义待人工复核 |
| reg-p02-006 | 区分 GFP 与 mCherry 对应细胞；mCherry 中文术语需领域人员核对 | 回答与基线一致；语义待人工复核 |
| reg-p02-009 | 1:1 的 72 小时条件须明确 DMSO；不把作者解释扩大为保证所有药效评估准确 | 回答与基线一致；语义待人工复核 |
| reg-p02-013 | 按指定实验范围比较检测方法；不扩大为所有药物和实验条件 | 回答与基线一致；语义待人工复核 |
| reg-p02-015 | 引用编号应包含完整来源前缀；原文的 13 与分类数目不一致须人工核对，不自动判定模型错误 | 回答与基线一致；语义待人工复核 |
| reg-p02-018 | 正确区分体外浓度与患者剂量；不可把片段未知扩大为全文未知 | 回答与基线一致；语义待人工复核 |
| reg-p02-019 | 区分竞争劣势主体；实验既涉及转化细胞也涉及 WT 细胞；不外推到所有耐药细胞 | 回答与基线一致；语义待人工复核 |
| reg-p02-021 | 下降百分比只在指定段落范围内判断；不把片段未知断言为全文未知 | 回答与基线一致；语义待人工复核 |
| reg-p02-022 | 不把阳性对照孔数等同独立生物学重复；无据时明确说明片段没有给出独立重复次数 | 回答与基线一致；语义待人工复核 |

其中 `015` 的引用仍被标记为 `malformed_citation`；原文数量表述存在待澄清的不一致，不能直接把原文问题判成模型事实错误。`022` 仍出现有关独立生物学重复次数的断言，程序给出 `verify_biological_replicate_count` 人工复核提示；该提示不判断对错、不阻止输出。其余案例中仍有助手初审标出的范围、术语、条件或实验组问题，不能因为引用编号被识别就视为解决。

## 复现与边界

以下命令假设本机已保留基线、后续回答、案例、原样本及 P02 索引。对照输出必须使用新文件名，已有文件不会被覆盖：

```bash
python3 -m sciquarry.regression \
  --cases data/biomedical_qa/regression_cases.jsonl \
  --samples data/biomedical_qa/dev_examples.jsonl \
  --reviews data/biomedical_qa/assistant_fact_review_v1.jsonl \
  --index data/local/index/P02.jsonl \
  --before data/local/evaluations/answer-v4.jsonl \
  --after data/local/evaluations/answer-v5-pretraining.jsonl \
  --output data/local/evaluations/targeted-regression-new.jsonl
```

程序会检查案例与助手初审的绑定、样本和证据一致性、模型参数、输入摘要及可用的服务 fingerprint；fingerprint 缺失时标为未验证，不能证明权重一致。程序只保存前后回答及待审清单，不自动给事实正确性打分。比较完成后仍需要人工逐项核对，必要时由领域人员对照原文和图表。
