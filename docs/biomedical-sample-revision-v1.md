# 问答样本修订记录（助手初审后）

日期：2026-10-31。本记录根据 [助手领域初审](biomedical-assistant-domain-review.md) 对 10 条建议修订的样本做了证据对齐修改。**这不是领域专家审核通过**，官方专家表仍全部待填。

## 修订范围

| 样本 ID | 主要修改 |
| --- | --- |
| `candidate-p06-006` | 保留段落印刷的 Hoechst33324 与货号 62249，并要求专家核对后再视为标准名称。 |
| `candidate-p08-001` | 补全 100 U/mL 青霉素与 100 μg/mL 链霉素，并限定为 cytokine-independent Ba/f3。 |
| `candidate-p08-002` | 按原文写 156 与 372（and），去掉未印刷的合计 528；区分 HPC-LSK 的 65 化合物库。 |
| `candidate-p08-003` | 改问重悬与铺板过程；区分 `2.5 × 103` 重悬数与未给出的每皿细胞数；保留 14 天计数。 |
| `candidate-p09-001` | 删除“约 6 个月”；避免写入方法段的 2 个月 / 1 年时长。 |
| `candidate-p09-002` | 按段落印刷单位写入 100 μg/ml 青霉素与 100 U/ml 链霉素，并提示勿自行对调。 |
| `candidate-p09-003` | 区分 3 μM 含药 2 个月与无药至少 1 年稳定；注明本段无具体 IC50 数值。 |
| `candidate-p09-006` | 分段落表述联合诱导死亡与单药未抑制增殖，避免笼统“不敏感”。 |
| `candidate-p05-008` | 按原文 “Cleaved caspase-3 and PARP” 限定 cleaved 修饰范围，不单独断言 cleaved PARP。 |
| `dev-p02-019` | 明确实验对象是 BCR–Abl 转化相对野生型 Ba/F3，不是耐药细胞面板。 |

修订后的样本仍标记 `pending_domain_review`；`assistant_review.status` 为 `revised_after_assistant_domain_review`。

## 新的专家交接包

本机已生成 `data/local/domain-review/qa-v7/` 与 `expert-qa-v7.zip`，覆盖全部 55 条（含上述修订）。`reviews.csv` 仍为 55/55 pending。旧包 `qa-v6` 可保留对照，新交接请使用 v7。

## 后续

1. 将 `expert-qa-v7.zip` 交给领域专家独立填写。
2. 专家确认后再决定是否纳入正式 SFT 数据准入流程；助手修订不能跳过专家审核。
3. 若专家要求再改，应形成新版本并重新绑定审阅，不要只改结论字段。
