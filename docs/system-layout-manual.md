# 文本重构系统 -- 详细布局手册

**版本**: 0.2.0
**更新日期**: 2026-06-04
**目的**: 供领域专家审核，验证理论到实现的映射是否科学准确

---

## 1. 系统概述

### 1.1 项目目标

将混乱的、口语化的长段中文文本重构为清晰、结构化的输出，同时：
- 保留原文全部信息和意图（绝不压缩/总结）
- 显式化前后逻辑关联和潜在联系
- 实时发掘模糊概念、逻辑矛盾、遗漏信息

### 1.2 架构总览

```
输入文本
  │
  ▼
SentenceSplitter (分句)
  │
  ▼
Tagger (LLM 批量标注) ─── 8 字段: role/intent/relation/scope/argument_role/argument_relation/dependency/cue_phrase
  │
  ▼
GraphUpdater (增量图谱构建)
  ├── DecayEngine (Ebbinghaus 衰减)
  ├── AdversaryScanner (7 项扫描)
  ├── Prosecutor (起诉构建)
  ├── Defender (辩护搜索, 11 策略)
  └── ConfidenceManager (正反方辩论, 最多 2 轮)
  │
  ▼
LLMRefiner (结构化输出) ─── 按 scope 分段 + 分点阐述
  │
  ▼
输出 1: 结构化纯文本 (stdout)
输出 2: 改进建议 (stderr)
```

### 1.3 LLM 后端

| 后端 | 实现 | 模型 | 速率限制 |
|------|------|------|----------|
| Ollama (本地) | `OllamaClient` | qwen3.5:0.8b | 无 |
| NVIDIA (云端) | `NVIDIAClient` | deepseek-v4-flash/pro | 40 req/min |

工厂函数 `create_client(config)` 根据配置分发。

---

## 2. LLM 适配器层 (`src/text_reconstructor/llm/`)

### 2.1 LLMConfig

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| model | str | qwen3.5:0.8b | 模型标识 |
| base_url | str | http://localhost:11434 | API 地址 |
| timeout | float | 30.0 | 超时秒数 |
| temperature | float | 0.1 | 采样温度 |
| max_tokens | int | 2048 | 最大输出 token |
| top_p | float | 0.9 | Top-P 采样 |
| think | bool | False | Qwen 思考模式 |
| backend | str | ollama | 后端选择 |
| api_key | str | "" | API 密钥 |

### 2.2 OllamaClient

- 端点: `/api/chat`
- 格式: Ollama 原生 (model, messages, stream, think, options)
- JSON mode: `body.format = "json"`
- 流式: NDJSON 逐行拼接 `message.content`，回退 `message.thinking`
- 无代理: `httpx.HTTPTransport(proxy=None)`

### 2.3 NVIDIAClient

- 端点: `https://integrate.api.nvidia.com/v1/chat/completions`
- 格式: OpenAI 兼容 (model, messages, temperature, max_tokens)
- 认证: `Authorization: Bearer {api_key}`
- 速率限制: 内置令牌桶 (40 req/min)
- 响应映射: `choices[0].message.content` -> LLMResponse

### 2.4 工厂函数

```python
create_client(config) -> OllamaClient | NVIDIAClient
```

### 2.5 LLMResponse

| 字段 | 说明 |
|------|------|
| content | LLM 输出文本 |
| model | 模型标识 |
| prompt_eval_count | 输入 token 数 |
| eval_count | 输出 token 数 |

---

## 3. 处理器模块 (`src/text_reconstructor/processor/`)

### 3.1 SentenceSplitter

纯规则分句:
1. 按 `\n\n` 分段
2. 按中文句末标点 `[。！？...?]` 分句
3. 合并 <2 字符的片段

### 3.2 Tagger

#### 3.2.1 工作流 (batch_tag)

1. 一次 LLM 调用标注所有句子
2. 解析 `||` 分隔的 8 字段输出
3. 后处理管线: signal_corrections -> intent_corrections -> validate -> rst_role -> infer_scope -> check_pronouns
4. 可选: 二次 scope LLM 调用 (仅当唯一 scope <= 2 种时)

#### 3.2.2 Batch Prompt 格式

输入: 编号句子列表
输出: 每行 `编号||role||intent||relation||argument_role||argument_relation||scope||dependency`

Prompt 包含:
- 完整字段枚举说明
- 间接言语行为(ISA)检测说明
- 6 个多样化示例 (覆盖 commissive/expressive/directive/assertive + premise/claim + attack/support + concession)

#### 3.2.3 后处理管线

**apply_signal_corrections** (可配置, `override_with_rules` 参数):
- 8 条信号词正则规则，按优先级覆盖 relation
- 优先级: contrast(10) > evidence(9) > summary(9) > cause(8) > purpose(7) > elaboration(7) > sequence(6) > condition(4)
- 仅在 `_override_with_rules=True` 时生效 (强模型下关闭)

**apply_intent_corrections** (可配置):
- 强信号词匹配覆盖 intent
- directive 降级为 assertive (仅小模型 + `_override_with_rules=True`)

**validate_chunk**:
- 补充 8 个默认字段
- 枚举值校验 (role/intent/relation)

**apply_rst_role** (RST 理论规则):
- 多核关系 (contrast/sequence/summary/restatement) -> nucleus
- 单核卫星关系 (evidence/elaboration/background/condition/purpose/concession) -> satellite
- 因果: "因为/由于" -> satellite, "所以/因此" -> nucleus

**infer_scope**:
- 保留 LLM 输出
- 空值时从 dependency 提取前 4 字符作为回退

**check_pronouns**:
- 检测代词 (他/她/它/他们/这/那/...)
- 代词存在但 scope 和 dependency 都空 -> 标记 `REFERENCE_MISSING`

### 3.3 ActiveBuffer (`buffer.py`)

跨距离上下文对齐机制:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_size | 20 | 最大激活节点数 |
| eviction_threshold | 0.4 | 驱逐权重阈值 |

操作:
- `add_node(node)`: 添加到激活列表，超限则驱逐最低权重节点
- `tick(tokens)`: 对所有激活节点应用 Ebbinghaus 衰减
- `get_top_k(k)`: 返回权重最高的 k 个节点
- `reference(node_id)`: 唤醒节点 (重新激活)
- `scavenge(query)`: 从衰减池打捞匹配节点

---

## 4. 图谱模块 (`src/text_reconstructor/graph/`)

### 4.1 EdgeType 枚举 (17 种)

| 边类型 | 理论来源 | 说明 |
|--------|----------|------|
| CAUSE | RST | 因果关系 |
| RESULT | RST | 结果关系 |
| EVIDENCE | RST | 证据关系 |
| ELABORATION | RST | 阐述关系 |
| BACKGROUND | RST | 背景关系 |
| CONDITION | RST | 条件关系 |
| PURPOSE | RST | 目的关系 |
| SUMMARY | RST | 总结关系 |
| CONTRAST | RST | 对比关系 |
| CONCESSION | RST | 让步关系 |
| SEQUENCE | RST | 时序关系 |
| EVALUATION | RST | 评价关系 |
| ATTRIBUTION | RST | 引用关系 |
| ATTACK | Dung AF | 反驳关系 |
| SUPPORT | Dung AF | 支持关系 |
| CO_SCOPE | 工程 | 同域弱连接 |
| RESTATEMENT | RST | 重申关系 |

### 4.2 GraphNode

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| id | int | 自增 | 节点 ID |
| text | str | | 原文 |
| role | str | satellite | RST 角色 |
| intent | str | assertive | 言语行为类型 |
| relation | str | none | 修辞关系 |
| scope | str | "" | 主题域 |
| chunk_index | int | | 句子序号 |
| confidence | float | 0.6 | 置信度 |
| weight | float | 1.0 | 当前权重 (衰减后变化) |
| token_count | int | | 文本长度 |
| created_at | int | | 创建步骤 |
| last_referenced_at | int | | 最近引用步骤 |

### 4.3 GraphUpdater 建边规则

**规则 1 -- relation 直映边**:
- 非 "none" 的 relation -> 对应 EdgeType 边
- target 选择策略:
  - contrast/concession: 优先相同 scope 的 nucleus
  - 其他: 最近 nucleus -> 最近前序节点

**规则 2 -- argument_relation 直映边**:
- "support" -> SUPPORT, "attack" -> ATTACK
- target: 优先同 scope 的 assertive/directive 节点

**规则 3 -- CO_SCOPE 弱连接**:
- scope 相同 + chunk_index 差 < 5 -> 双向 CO_SCOPE 边
- 引用时调用 `decay_engine.reactivate()`

**规则 4 -- DEPENDS 依赖边**:
- dependency 非空时在图中 substring 匹配
- 匹配到 -> BACKGROUND 边 + `reactivate()`

**衰减**:
- 每处理一个 chunk 后对所有节点应用 Ebbinghaus 衰减

### 4.4 DecayEngine

Ebbinghaus 对数衰减公式:
```
weight = initial_weight / (1 + rate * log(1 + age))
```

role-based 衰减速率:

| role | rate | 理由 |
|------|------|------|
| nucleus | 0.3 | 核心信息衰减最慢 |
| action | 0.3 | 动作信息同样重要 |
| commitment | 0.4 | 承诺/计划次之 |
| satellite | 0.6 | 辅助信息中等 |
| expressive | 1.0 | 情感表达最快遗忘 |

唤醒机制: `reactivate(node, step)` -> `weight = min(1.0, weight + 0.3)`

### 4.5 AdversaryScanner (7 项扫描)

| 编号 | 类型 | 检测逻辑 |
|------|------|----------|
| 1 | LOW_CONFIDENCE | confidence < 0.5 |
| 2 | ISOLATED_NODE | degree == 0 |
| 3 | LOGIC_CONFLICT | ATTACK 入边 > SUPPORT 入边 |
| 4 | DANGLING_DIRECTIVE | directive 无 CAUSE 入边 |
| 5 | STRUCTURE_CHAOS | 同 scope 内 ATTACK+CONTRAST >= 3 |
| 6 | UNRESOLVED_PRONOUN | 代词存在但无 BACKGROUND 入边消解 |
| 7 | ARGUMENT_GAP | nucleus assertive 无 SUPPORT/EVIDENCE 入边 |

---

## 5. 对抗机模块 (`src/text_reconstructor/adversary/`)

### 5.1 Prosecutor (起诉构建)

每种 alert 类型有预定义的:
- required_evidence: 需要什么证据
- evidence_targets: 搜索方法优先级列表

言语行为增强:
- assertive -> 搜索 incoming_evidence
- directive -> 搜索 incoming_background
- commissive -> 搜索 future_reference
- expressive -> 搜索 incoming_cause + same_scope

第 2 轮扩展搜索范围 (增加 same_scope + global_text_match)。

### 5.2 Defender (11 种搜索策略)

| 策略 | 搜索目标 |
|------|----------|
| incoming_support | SUPPORT 入边 |
| incoming_evidence | EVIDENCE 入边 |
| incoming_background | BACKGROUND 入边 |
| incoming_cause | CAUSE 入边 |
| incoming_condition | CONDITION 入边 |
| co_scope_neighbors | CO_SCOPE 邻居的支持边 |
| same_scope | 同 scope 非孤立节点 |
| text_match | 4 字符关键词匹配 (过滤虚词, 优先同 scope) |
| future_reference | 后续节点引用当前节点 |
| outgoing_support | 出站 SUPPORT 边 |
| same_scope_support | 同 scope >= 3 条 SUPPORT 边 |

成功增量: +0.1, 失败增量: -0.15。

### 5.3 ConfidenceManager

| 参数 | 值 | 说明 |
|------|-----|------|
| MAX_ROUNDS | 2 | 正反方最多辩论 2 轮 |
| SAFETY_LINE | 0.7 | 安全线, 高于此不再辩论 |
| ALERT_THRESHOLD | 0.5 | 低于此直接入 AlertBuffer |

流程:
1. Prosecutor 构建起诉
2. 按 node_id 分组
3. 每节点: 逐起诉辩护 -> 汇总增量 -> 线性更新 confidence
4. 2 轮后 confidence < 0.7 -> 推入 AlertBuffer
5. STRUCTURE_CHAOS 等 scope 级 alert 直接入 buffer

### 5.4 AlertBuffer

- 去重键: (alert_type, node_id)
- 排序: severity (high > medium > low) -> 轮次 -> 计数

---

## 6. 输出模块 (`src/text_reconstructor/output/`)

### 6.1 LLMRefiner (主力)

Prompt 构造:
1. 按 scope 分组
2. 每个节点标注极简标签: `[核心/原因]` / `[辅助/转折]`
3. 附加 10 条重构规则

核心规则:
- 绝不压缩/省略任何信息
- 按话题分段, 用编号列表分点
- 模糊概念标注为 [疑点]
- 逻辑矛盾/遗漏列在 [发现的问题]
- 删除口语填充词但保留实质内容

### 6.2 TextOutput (回退/调试)

1. Kahn 算法拓扑排序 (排除 CO_SCOPE 边)
2. 按 scope 分组
3. 基于最近入边类型的缩进: `+` support, `-` attack, `->` 渐进

### 6.3 Suggestions

5 种 alert 类型的中文模板, 输出到 stderr。

---

## 7. 评估模块 (`src/text_reconstructor/evaluation/`)

### 7.1 对比方法

- **基线**: 直接发送原文给 LLM, prompt="请梳理以下文本的结构和逻辑，保留所有细节"
- **管线**: 完整 pipeline (splitter -> tagger -> updater -> refiner)
- **评分**: LLM 对比两个输出, 4 维度 0-10 分

### 7.2 评分维度

| 维度 | 评估内容 |
|------|----------|
| detail_preservation | 细节保留程度 (是否有遗漏) |
| doubt_identification | 疑点/模糊概念识别 |
| fuzzy_concept_handling | 模糊处理合理性 (不过度猜测) |
| structure_clarity | 结构逻辑清晰度 (分段分点) |

### 7.3 评估报告

格式: markdown 表格, 含原文摘要、两个输出、评分对比、总结评述。

---

## 8. 理论 -> 实现映射表

| 理论概念 | 实现位置 | 具体映射 |
|----------|----------|----------|
| RST nucleus/satellite | `tagger.py: apply_rst_role()` | chunk.role 字段 |
| RST 修辞关系 | `models.py: EdgeType` | chunk.relation -> EdgeType 边 |
| Searle 言语行为五分类 | `tagger.py: validate_chunk()` | chunk.intent 字段 |
| 间接言语行为 | `prompts.py: BATCH_TAGGING_TEMPLATE` | Prompt ISA 说明 |
| Dung 论证框架 | `models.py: ATTACK/SUPPORT` | argument_relation -> 边 |
| 论证挖掘 | `tagger.py: batch_tag()` | argument_role + argument_relation 字段 |
| Ebbinghaus 遗忘曲线 | `decay.py: DecayEngine` | 对数衰减公式 |
| AGM 信念修正 | `alert_buffer.py: ConfidenceManager` | confidence 更新 + 矛盾消解 |
| Allen 时序逻辑 | `models.py: SEQUENCE` | 时序关系边 |
| 因果图模型 | `models.py: CAUSE/RESULT` | 因果关系边 |

---

## 9. 科学有效性审查清单

| 编号 | 问题 | 状态 | 修复说明 |
|------|------|------|----------|
| 1 | Batch 标注曾砍到 4 字段 | 已修复 | 恢复 8 字段 + 6 个多样化示例 + ISA 说明 |
| 2 | DecayEngine 未实现 | 已修复 | 实现 Ebbinghaus 对数衰减, role-based 速率 |
| 3 | ActiveBuffer 是空壳 | 已修复 | 完整实现激活/衰减/驱逐/打捞 |
| 4 | 图边仅连最近 nucleus | 已修复 | contrast 优先同 scope, argument 优先 claim |
| 5 | 信号词硬编码覆盖 | 已修复 | 可配置 override_with_rules, 强模型下关闭 |
| 6 | 对抗机仅结构检查 | 已修复 | 新增 UNRESOLVED_PRONOUN + ARGUMENT_GAP |
| 7 | infer_scope 是空操作 | 已修复 | dependency 回退 + relation+intent 提示 |

---

## 10. 数据流全图

```
输入文本 (CLI 参数/文件/stdin)
    │
    ├─ SentenceSplitter.split() ──> sentences: list[str]
    │
    ├─ Tagger.batch_tag(sentences)
    │   ├─ LLM #1: batch_tag (8 字段标注所有句子)
    │   ├─ apply_signal_corrections (可关闭)
    │   ├─ apply_intent_corrections (可关闭)
    │   ├─ validate_chunk (默认值 + 枚举校验)
    │   ├─ apply_rst_role (RST 理论修正)
    │   ├─ infer_scope (dependency 回退)
    │   ├─ check_pronouns (代词检测)
    │   └─ LLM #2: scope 推理 (条件触发, scope<=2 种时)
    │
    ├─ GraphUpdater.process(chunks)
    │   │  对每个 chunk:
    │   │  ├─ 创建 GraphNode (weight=1.0)
    │   │  ├─ 规则1: relation -> EdgeType 边
    │   │  ├─ 规则2: argument_relation -> ATTACK/SUPPORT 边
    │   │  ├─ 规则3: CO_SCOPE 弱连接 (同 scope, 距离<5)
    │   │  ├─ 规则4: DEPENDS -> BACKGROUND 边
    │   │  └─ DecayEngine: 对所有节点应用衰减
    │   │
    │   └─ 对抗机周期:
    │       ├─ AdversaryScanner.scan() (7 项检查)
    │       ├─ Prosecutor.build() (起诉构建 + 言语行为增强)
    │       ├─ ConfidenceManager.run_node_cycle() (逐节点)
    │       │   ├─ Round 1: Prosecutor -> Defender -> 增量 -> 更新 confidence
    │       │   └─ Round 2: 扩展搜索 -> Defender -> 增量 -> 更新 confidence
    │       └─ AlertBuffer: 收集 confidence < 0.7 的 alert
    │
    ├─ LLMRefiner.refine(snapshot) ──> 结构化文本 (LLM #3)
    │   └─ 回退: TextOutput.format_simple() (模板式)
    │
    └─ Suggestions.format(alerts) ──> 改进建议 (stderr)
```
