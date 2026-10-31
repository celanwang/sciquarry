# 基于证据的医学问答 SFT

本阶段实现 MLX-LM 的 LoRA 训练及其数据审核、适配器加载、留出集对照和人工复核链路。模型保持 Qwen3-4B 原始 BF16 权重，训练只保存 LoRA 适配器；没有实现或启动 DPO。仓库中的虚构样本仅用于工程冒烟，不是医学训练数据。现有 P02/P05 开发与候选样本尚未经领域审核，也不能充当独立盲测。

## 样本及审核

输入是 UTF-8 JSONL，每行一个对象。可从 [待填模板](../data/sft/review_template.jsonl) 复制并逐项替换；模板不是已审核数据。`kind` 为 `reviewed` 的正式样本包含：

- `id`：唯一 ID；`split`：`train`、`valid` 或 `test`；`group_id`：同一论文、关联研究或主题的隔离组。
- `question`、`answer`：问题和有证据的目标回答；`answerability`：`answerable` 或 `insufficient_evidence`。可回答样本需在回答中引用所给段落，例如 `[P06:1.1:p1]`；证据不足样本应明确说明不足。
- `evidence`：非空数组，每条包含 `source_id`、与来源对应的 `id`（如 `P06:1.1:p1`）、`text`、`source_url`、`locator`、原始来源文件 `source_sha256`、`license` 与布尔值 `training_use_permitted`。请按**实际用途**核对版权和许可，保留依据。
- `review`：`status: "approved"`、`reviewer_kind: "human_domain_expert"`、`reviewer`、`reviewed_at` 及 `content_sha256`。由领域审核人核对问题、证据、目标回答、引用、实验条件、风险和许可记录后填写；不得把助手初审冒充专家审批。

先整理完整样本内容，然后计算内容摘要，交由审核人核对并填写到对应的 `review.content_sha256`：

```bash
python3 -m sciquarry.sft review-hash --samples data/local/sft/reviewed.jsonl
```

摘要覆盖除 `review` 以外的全部字段，内容修改后必须重新审核。程序会检查三个切分非空、ID/问题不重复、组与来源 ID 不跨切分、相同来源摘要及相同证据文本不跨切分、来源许可声明、审核字段、摘要和引用编号。P02/P05 已用于既有开发评估，其来源 ID 或已登记的原文文件摘要不允许进入正式训练切分。基于文本的检查不能发现所有近重复、派生研究、来源别名或伪造的审核声明，也不会验证来源内容与正文一致；必须人工核实。字段格式正确不等于内容医学正确或许可真实有效。

在启动前按来源及关联研究确定划分、核对近重复，保留真正未用于开发、样本选择和训练的独立测试集及其原始基线。验证集供训练期间监控；测试集用于最终评估，避免反复选择模型。新数据和输出应放在 `data/local/` 与 `runs/`，不会进入 Git。

## 准备与训练

```bash
# 三条完全虚构的样本：只验证工程链路
python3 -m sciquarry.sft prepare \
  --samples data/sft/synthetic_smoke.jsonl --kind synthetic \
  --output runs/sft-example-data

# 示例为两步冒烟测试，并非有效的训练配置或医学模型
python3 -m sciquarry.sft train \
  --data runs/sft-example-data --model models/Qwen3-4B \
  --output runs/sft-example-run --iters 2 --num-layers 2 \
  --max-seq-length 512 --save-every 1 --eval-every 1
```

`prepare` 固定样本快照、聊天格式和文件摘要；训练前重新核对样本和转换结果。`train` 使用 `uvx`、Python 3.11 和 `mlx-lm[train]==0.32.2`，创建新目录，不覆盖旧实验。正式样本准备时改为 `--kind reviewed` 与实际审核文件。训练前使用所选模型分词器验证 MLX 的聊天模板及 prompt mask，检查所有训练和验证样本都不被截断；随后将训练和验证文件复制到独立目录，测试文件不交给训练器。训练时固定 `--mask-prompt` 和梯度检查点，只有最终助手回答部分参与损失。Qwen3 聊天模板会包含空 thinking 标记；推理和评估使用 `enable_thinking=False`。底座和分词器文件、数据、代码、命令、适配器和配置的摘要保存在 `run.json`，运行环境的实际版本和损失在 `training.log`。只固定了 MLX-LM 主版本，间接依赖未锁定；日志可用于核对环境，但不能保证将来完全复现。MLX-LM 的聊天数据格式及掩码行为参考[官方 LoRA 文档](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)。

默认配置是工程起点而非推荐的医学训练超参数。批量大小不得超过训练集和验证集各自的样本数；训练会生成检查点，但本封装暂未实现恢复优化器状态，不应将重新运行视为无损续训。若训练中断或失败，保留失败日志并使用新的输出目录。MLX 服务、模型和训练共享统一内存，正式训练前根据可用内存、序列长度和日志调整参数。

## 基础模型和适配器对照

下面的示例仅对虚构测试题进行端到端验证。正式实验应在训练和选型前先运行并锁定基础模型结果，再用独立测试集完成最终对照：

```bash
python3 -m sciquarry.sft_evaluate run \
  --data runs/sft-example-data --model models/Qwen3-4B \
  --output runs/sft-example-run/base-test.jsonl
python3 -m sciquarry.sft_evaluate run \
  --data runs/sft-example-data --model models/Qwen3-4B \
  --adapter-run runs/sft-example-run --output runs/sft-example-run/adapter-test.jsonl
python3 -m sciquarry.sft_evaluate compare \
  --before runs/sft-example-run/base-test.jsonl \
  --after runs/sft-example-run/adapter-test.jsonl \
  --output runs/sft-example-run/comparison.json
```

评估直接通过 MLX 加载基础模型或已记录的适配器，不依赖用户正在运行的服务。比较时校验数据、底座、模型生成参数和运行包版本；不匹配或不完整的结果会被拒绝。`comparison.json` 记录原始答案、引用检查与逐题复核项，不自动判定医学事实是否正确，也不计算可靠性分数。需由专业人员评估事实、数字、实验条件、引用支持、拒答和风险错误，并另行评估检索表现；测试集表现不能作为临床可用性证明。

## 用已训练适配器启动本地服务

例如，在独立终端和空闲端口上启动服务：

```bash
uvx --python 3.11 --from 'mlx-lm[train]==0.32.2' mlx_lm.server \
  --model ./models/Qwen3-4B \
  --adapter-path ./runs/sft-example-run/adapter --port 18081
```

服务使用 `--adapter-path` 指定的适配器时，问答请求的 `--model` 应使用 `default_model`，使 MLX-LM 映射到启动时的模型和适配器，而不是直接传基础模型路径：

```bash
python3 -m sciquarry.ask data/local/index/P02.jsonl \
  '伊马替尼处理混合细胞多久，通过什么方法测量细胞比例？' \
  --model default_model --base-url http://127.0.0.1:18081/v1 --no-thinking
```

请只在确认目标实验的适配器、底座和数据状态后使用；上述虚构训练产生的适配器只用于验证接口，不是医学模型。新服务是独立进程，不会自动替换现有 8080 服务。

## 本机冒烟记录（2026-10-31）

在 M4 Max / 48 GB 上，Qwen3-4B BF16、Python 3.11.17、MLX-LM 0.32.2、MLX 0.32.4；三个切分各一条虚构题。两层 LoRA、rank 8、两步、批量 1、最大长度 512。训练完成并保存适配器，训练集和验证集分词均为 157 tokens；直接加载适配器完成虚构测试集对照，另以 `default_model` 在独立 18081 服务上调用现有问答接口并正常返回。记录位于 Git 忽略目录 `runs/sft-smoke-run-06/`，服务接口的额外验证位于 `runs/sft-smoke-run-04/server-smoke.json`。这些结果仅验证流程，不代表训练收敛、医学改善或生产可用。
