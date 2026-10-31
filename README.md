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

在本机启动一个支持 OpenAI Chat Completions 接口的模型服务，并确认服务地址和模型标识。以下示例假设其 API 地址为 `http://127.0.0.1:8001/v1`；这里的 `YOUR_MODEL_NAME` 应替换为服务实际提供的模型名称。项目本身不会下载、启动或训练模型。

```bash
python3 -m sciquarry.ask data/local/index/P02.jsonl \
  '伊马替尼处理混合细胞多久，通过什么方法测量细胞比例？' \
  --model YOUR_MODEL_NAME --base-url http://127.0.0.1:8001/v1
```

问答入口向本机模型服务发送问题与检索出的段落，要求回答附带段落编号，并返回原始回答、候选来源和 `citation_status`。只有匹配 `[P02:1.1:p1]` 这一格式（方括号内允许空格）的编号会被检查：`recognized` 表示至少出现一个已检索编号且未检测到该格式的未知编号，`unknown_citation` 表示发现未知编号，`missing` 表示没有检测到该格式的编号。**这些状态只检查编号，不证明引用支持结论，也不能发现所有格式错误或漏引。** 没有检索结果时程序不会调用模型；检索到结果也不代表足以回答，仍需人工核对。当前不会自动将开发样本限定到它标注的证据范围，所以不能直接用该入口计算样本的正式评估指标。

使用本地 MLX-LM 与 Qwen3 时，可添加 `--no-thinking` 来关闭思考模式，避免思考内容占满生成额度：

```bash
python3 -m sciquarry.ask data/local/index/P02.jsonl \
  '伊马替尼处理混合细胞多久，通过什么方法测量细胞比例？' \
  --model ./models/Qwen3-4B --base-url http://127.0.0.1:8080/v1 \
  --no-thinking
```

该选项通过 `chat_template_kwargs` 控制 Qwen 的聊天模板，需要服务端支持。输出的 `finish_reason` 为 `length` 时表示生成达到长度限制，回答可能不完整；`stop` 只表示正常结束，并不保证事实正确。当前生成上限为 1024 tokens。

为避免意外发送文献和问题，当前问答入口只支持本机 loopback 地址，并禁用 HTTP 重定向。它不提供认证、流式输出、联网搜索、临床安全审核或自动事实核验。

运行基础检查：

```bash
python3 -m unittest discover -s tests -v
```

项目方案、文献整理和待审核样本分别见 [试点方案](docs/biomedical-qa-pilot.md)、[文献档案](docs/biomedical-literature-catalog.md) 和 [医学问答数据说明](data/biomedical_qa/README.md)。
