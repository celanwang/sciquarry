# sciquarry
An evidence-driven AI platform for scientific knowledge, starting with biomedical question answering.

## 文献检索基线

当前项目提供一个基于 Python 标准库的实验性段落检索工具。它从本地 JATS XML 提取正文段落，记录论文、章节、段落位置和源文件 SHA-256，再用 BM25 做词面检索。它使用一组针对本试点的中英文关键词映射协助检索，并非通用翻译或语义检索；词表之外的问题可能无法命中，必要时使用英文关键词。

例如，获取已登记的 P02 文献（下载和使用前请查看 [文献登记表](data/biomedical_qa/sources.json) 中的许可与署名要求）：

```bash
mkdir -p data/local/raw data/local/index
curl -fL 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC7948465/fullTextXML' \
  -o data/local/raw/PMC7948465.xml
python3 -m sciquarry.retrieval ingest data/local/raw/PMC7948465.xml \
  --source-id P02 --pmcid PMC7948465 \
  --source-url https://pmc.ncbi.nlm.nih.gov/articles/PMC7948465/ \
  --output data/local/index/P02.jsonl
python3 -m sciquarry.retrieval search data/local/index/P02.jsonl \
  'imatinib competition BCR Abl Ba F3 cells 72 hours' --top-k 3
```

`ingest` 每次生成单篇论文的索引并覆盖目标输出文件。只提取正文中带章节的段落，不包含图表、图注或补充材料；若证据位于这些内容，需人工另行核对。检索结果是候选证据，分数不是事实正确性判断。原始文献和生成索引保存在已忽略的 `data/local/` 中，重新获取的文献版本可能变化，应保留文件摘要。

## 本地证据问答

在本机启动一个支持 OpenAI Chat Completions 接口的模型服务，并确认服务地址和模型标识。以下示例假设其 API 地址为 `http://127.0.0.1:8001/v1`；这里的 `YOUR_MODEL_NAME` 应替换为服务实际提供的模型名称。该问答入口不会自动下载、启动或训练模型；SFT 训练另有独立入口。

```bash
python3 -m sciquarry.ask data/local/index/P02.jsonl \
  '伊马替尼处理混合细胞多久，通过什么方法测量细胞比例？' \
  --model YOUR_MODEL_NAME --base-url http://127.0.0.1:8001/v1
```

问答入口向本机模型服务发送问题与检索出的段落，要求回答附带段落编号，并返回原始回答、候选来源和 `citation_status`。程序检查方括号内类似 `[P02:1.1:p1]` 的段落编号（方括号内允许空格）：`recognized` 表示至少出现一个已检索编号且未检测到未知或残缺编号，`unknown_citation` 表示发现未知编号，`malformed_citation` 表示发现类似段落编号但格式不完整的引用，`missing` 表示没有检测到此类引用。**这些状态只检查方括号内类似段落编号的引用，不证明引用支持结论，也不能发现其他格式错误或漏引。** 没有检索结果时程序不会调用模型；检索到结果也不代表足以回答，仍需人工核对。`review_flags` 中的 `verify_biological_replicate_count` 是对部分数字形式的生物学重复次数陈述发出的人工核对提示，不代表该陈述有误，也不能识别所有说法。当前不会自动将开发样本限定到它标注的证据范围，所以不能直接用该入口计算样本的正式评估指标。

使用本地 MLX-LM 与 Qwen3 时，可添加 `--no-thinking` 来关闭思考模式，避免思考内容占满生成额度：

```bash
python3 -m sciquarry.ask data/local/index/P02.jsonl \
  '伊马替尼处理混合细胞多久，通过什么方法测量细胞比例？' \
  --model ./models/Qwen3-4B --base-url http://127.0.0.1:8080/v1 \
  --no-thinking
```

该选项通过 `chat_template_kwargs` 控制 Qwen 的聊天模板，需要服务端支持。输出的 `finish_reason` 为 `length` 时表示生成达到长度限制，回答可能不完整；`stop` 只表示正常结束，并不保证事实正确。当前生成上限为 1024 tokens。

为避免意外发送文献和问题，当前问答入口只支持本机 loopback 地址，并禁用 HTTP 重定向。它不提供认证、流式输出、联网搜索、临床安全审核或自动事实核验。

## 开发集评估

试点开发样本由助手初审，尚未经领域专家审核；仅可用于诊断，不能作为独立医学能力测试。评估结果写入 Git 忽略的本地目录，使用新的输出文件名以避免覆盖已有结果。

检索评估记录前 3 条候选是否包含人工标注的段落：

```bash
python3 -m sciquarry.evaluate retrieval \
  --samples data/biomedical_qa/dev_examples.jsonl \
  --index data/local/index/P02.jsonl --top-k 3 \
  --output data/local/evaluations/retrieval-new.jsonl
```

回答评估直接向模型提供每题指定的证据，不调用检索。先启动本机 MLX-LM 服务，再运行：

```bash
python3 -m sciquarry.evaluate answer \
  --samples data/biomedical_qa/dev_examples.jsonl \
  --index data/local/index/P02.jsonl \
  --model ./models/Qwen3-4B --base-url http://127.0.0.1:8080/v1 \
  --no-thinking --output data/local/evaluations/answer-new.jsonl
```

每次运行会记录数据与代码摘要、参数、逐题结果及结束状态；回答仍需人工逐题核对。`any_hit` 和 `all_hit` 只表示是否命中已标注的段落，标注并不保证穷尽所有可支持答案的段落。输出文件以独占方式创建，中断时保留已有逐题结果；重新运行需使用新的文件名。

运行基础检查：

```bash
python3 -m unittest discover -s tests -v
```

项目方案、文献整理和待审核样本分别见 [试点方案](docs/biomedical-qa-pilot.md)、[文献档案](docs/biomedical-literature-catalog.md)、[医学问答数据说明](data/biomedical_qa/README.md)、[样本审核记录](docs/biomedical-qa-sample-review.md)、[开发基线报告](docs/biomedical-qa-development-baseline.md) 和 [调整回归报告](docs/biomedical-qa-development-followup.md)。

新论文候选题的 [领域审核材料](docs/biomedical-p05-domain-review.md)、[检索探索](docs/biomedical-external-retrieval-exploration.md) 和 [事实断言核对方案](docs/biomedical-fact-review-design.md) 可用于下一阶段的人工审核；其中包含查看证据、导出审核材料和记录人工判断的命令。

P02 基础模型回答的逐项核对结果见 [助手事实初审报告](docs/biomedical-assistant-fact-review.md)；这些结论尚待领域专家复核。

定向回归和微调前数据条件分别见 [回归报告](docs/biomedical-targeted-regression.md) 与 [准备状态](docs/biomedical-pretraining-readiness.md)。

## SFT 训练与评估

已实现基于证据的 MLX LoRA SFT，包括审核数据校验、训练及适配器加载和基础模型对照。项目中的三条虚构样本仅供冒烟；当前尚无经领域专家审核的医学训练集，也没有完成正式医学微调。数据格式、审核、执行命令与本机验证记录见 [SFT 说明](docs/biomedical-sft.md)。

领域专家的审核材料、本地填写页、可填写审核表及新来源候选见 [审核与数据准备工作流](docs/biomedical-domain-review-workflow.md)。当前最新交接包含 55 条样本，均待审核；可用 `python3 -m sciquarry.domain_review serve --packet data/local/domain-review/qa-v7` 打开本机填写页。助手对这 55 条的初步建议见 [助手领域审核报告](docs/biomedical-assistant-domain-review.md)；专家尚未签字，正式审核表仍全部待填。

候选文献自动关联检查见 [研究关联审计](docs/biomedical-source-relationship-audit.md)。

助手初审后的样本修订见 [样本修订记录](docs/biomedical-sample-revision-v1.md)；最新专家交接包为本机 `data/local/domain-review/expert-qa-v7.zip`。
