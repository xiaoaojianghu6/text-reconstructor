# 文本重构系统 -- 详细布局手册

**版本**: 3.0
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
  |
  v
SentenceSplitter (分句)
  |
  v
Tagger (LLM Mini-Batch 流式标注) --- 10 字段: role/intent/relation/argument_role/argument_relation/scope/dependency/thread_id/anchor_type + cue_phrase
  |
  v
GraphUpdater (增量图谱构建)
  +-- DecayEngine (Ebbinghaus 衰减 + 时空胶囊)
  +-- AdversaryScanner (7 项扫描)
  +-- SemanticAdversaryRouter (双轨混合对抗: 拓扑粗筛 + LLM审计)
  +-- Prosecutor (起诉构建)
  +-- Defender (辩护搜索, 11 策略)
  +-- ConfidenceManager (正反方辩论, 最多 2 轮)
  +-- ActiveBuffer (激活/衰减/驱逐/打捞)
  |
  v
LLMRefiner (结构化输出) --- 13条规则 + 边关系描述 + 前缀去噪
  +-- FCR 事实覆盖率验证
  +-- DetailAnchor 细节锚定
  |
  v
输出 1: 结构化纯文本 (stdout)
输出 2: 改进建议 (stderr)
```

### 1.3 LLM 后端

| 后端 | 实现 | 模型 | 速率限制 |
|------|------|------|----------|
| Ollama (本地) | `OllamaClient` | qwen3.5:0.8b | 无 |
| NVIDIA (云端) | `NVIDIAClient` | deepseek-v4-flash/pro | 40 req/min |
| DeepSeek (官网) | `NVIDIAClient` (不同 base_url) | deepseek-chat | 不限速 |

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

- 端点: `{base_url}/chat/completions`
- 格式: OpenAI 兼容 (model, messages, temperature, max_tokens)
- 认证: `Authorization: Bearer {api_key}`
- 速率限制: 内置令牌桶 (40 req/min)
- 响应映射: `choices[0].message.content` -> LLMResponse
- DeepSeek 官网: base_url=`https://api.deepseek.com/v1`, 使用同一 NVIDIAClient

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
2. 按中文句末标点 `[。!?...?]` 分句
3. 合并 <2 字符的片段

### 3.2 Tagger

#### 3.2.1 工作流

**默认模式**: Mini-Batch 流式标注 (`batch_tag_streaming`)
- 8 句一批，携带 ActiveBuffer Top-3 历史节点作为上下文
- 每批一次 LLM 调用

**回退模式**: 全量 Batch 标注 (`batch_tag`) -- 使用 `--no-streaming` 启用

后处理管线: signal_corrections -> intent_corrections -> validate -> rst_role -> infer_scope -> check_pronouns

#### 3.2.2 Batch Prompt 格式 (10 字段)

输入: 编号句子列表
输出: 每行 `编号||role||intent||relation||argument_role||argument_relation||scope||dependency||thread_id||anchor_type`

**BATCH_SYSTEM_PROMPT 完整原文**:
```
You are a Chinese text annotation assistant specializing in rhetorical structure theory (RST) and speech act theory.
Given a list of Chinese sentences, annotate each with role (nucleus/satellite), intent, rhetorical relation, argument structure, scope, and dependency.
Follow the output format strictly. Pay special attention to pronoun resolution: when a sentence contains pronouns, you must resolve them in the scope or dependency field.
```

**BATCH_TAGGING_TEMPLATE 完整原文**:
```
为以下每句话标注 role/intent/relation/scope/论证角色/主张关系/依赖关系/叙事线程/锚定类型。

每行格式（严格遵循，不要额外文字）：
编号||role||intent||relation||argument_role||argument_relation||scope||dependency||thread_id||anchor_type

role: nucleus(核心) 或 satellite(辅助)
intent: assertive(陈述) 或 directive(指令) 或 commissive(承诺) 或 expressive(情感) 或 declaration(宣告)
relation: cause(原因) 或 result(结果) 或 evidence(举例) 或 elaboration(说明) 或 background(背景) 或 condition(条件) 或 purpose(目的) 或 summary(总结) 或 contrast(转折) 或 concession(让步) 或 sequence(顺序) 或 evaluation(评价) 或 none(无)
argument_role: premise(论据) 或 claim(主张) 或 none(无)
argument_relation: support(支持) 或 attack(反驳) 或 none(无)
scope: 当前句的主题域/话题（如"定价策略"），用短语概括
dependency: 依赖的前文内容（可为空）
thread_id: 叙事线程标识 - main(主线/主要叙述) 或 sub(副线/穿插叙述) 或 latent(暗线/隐含线索)
anchor_type: 叙事锚定类型 - none(无特殊锚定) 或 foreshadow(伏笔/埋下的线索) 或 reveal(照应/揭示/呼应前文伏笔)

注意间接言语行为：
- "你能...吗？" "是不是应该..." 实际是指令(directive)，不是疑问
- "我觉得可能需要..." "建议..." 实际是指令或建议
- "我打算/准备..." 是承诺(commissive)

多线叙事标注规则：
- 绝大部分句子属于主线(main)，除非明确切换话题或插入回忆/旁白
- 伏笔(foreshadow): 暗示后续发展的句子，如"当时我并没有在意这个细节"、"谁也没想到后来..."
- 照应(reveal): 呼应前文伏笔的句子，如"现在我明白了为什么..."、"果然不出所料..."

代词消解约束（必须遵守）：
- 如果句子包含代词(他/她/它/他们/这/那/这个/那个/这里/那里)，必须在 scope 或 dependency 中写出真实指代对象
- 禁止在 scope 和 dependency 中使用代词本身
- 例如："它很贵" -> scope 应该写"产品定价"而不是"它"

示例：
0||nucleus||commissive||none||none||none||定价策略||main||none
1||satellite||assertive||cause||premise||support||市场分析||价格敏感度||main||none
2||nucleus||expressive||contrast||claim||none||产品评价||main||none
3||satellite||directive||condition||none||none||技术方案||预算限制||main||none
4||satellite||assertive||concession||premise||support||竞争分析||对手优势||sub||none
5||nucleus||assertive||result||claim||none||项目进展||阶段一完成||main||none

共 {count} 句：

{numbered_sentences}
```

#### 3.2.3 Mini-Batch Prompt

**MINI_BATCH_TEMPLATE 完整原文**:
```
## 当前上下文记忆（前文关键信息）

{active_context}

## 当前批次句子（全局编号从 {offset} 开始，共 {count} 句）

{numbered_sentences}

## 标注任务

每行格式（严格遵循，不要额外文字）：
编号||role||intent||relation||argument_role||argument_relation||scope||dependency||thread_id||anchor_type

（字段说明同 BATCH_TAGGING_TEMPLATE，此处省略重复）

代词消解约束（必须遵守）：
- 如果句子包含代词(他/她/它/他们/这/那/这个/那个/这里/那里)，必须在 scope 或 dependency 中写出真实指代对象
- 禁止在 scope 和 dependency 中使用代词本身
- 结合上下文记忆中的信息进行代词消解
```

#### 3.2.4 Scope 推理 Prompt

**SCOPE_SYSTEM_PROMPT**: `Group the sentences by topic. Sentences discussing the same subject get the same topic label.`

**SCOPE_TEMPLATE**:
```
为以下每句话分配一个主题域(scope)。

规则：
1. 讨论同一主题的句子使用完全相同的 scope 名称
2. scope 用短语概括（2-5字），如"市场需求""技术方案""可行性分析"
3. 相邻句子如果讨论不同方面，分配不同的 scope
4. 每行格式：编号||scope

{numbered_sentences}
```

触发条件: 当首批标注中存在低质量 scope (`""`, `"REFERENCE_MISSING"`, `"none"`, `"(无)"`) 时触发二次 LLM 调用。

#### 3.2.5 后处理管线

**apply_signal_corrections** (可配置, `override_with_rules` 参数):

8 条信号词正则规则，按优先级覆盖 relation:

| 信号词 | relation | 优先级 |
|--------|----------|--------|
| 因为/所以/因此/从而/导致/由于/因而/于是 | cause | 8 |
| 但是/然而/不过/却/虽然/尽管/可是/但 | contrast | 10 |
| 然后/接着/随后/之后/此后/先 | sequence | 6 |
| 例如/比如/比方说/譬如/举例 | evidence | 9 |
| 总之/综上所述/总的来说/概括/简而言之 | summary | 9 |
| 如果/假如/一旦/除非/只有/只要 | condition | 4 |
| 为了/以便/以免/以期 | purpose | 7 |
| 也就是说/换句话说/具体来说/即 | elaboration | 7 |

优先级越高越优先。仅在小模型 `override_with_rules=True` 时生效。

**apply_intent_corrections** (可配置):

强信号词匹配覆盖 intent:
- 承诺: 计划/打算/准备/将要/承诺/保证/目标/愿景/争取
- 指令: 请/必须/应当/建议/推荐/务必
- 表达: 遗憾/高兴/担心/希望/失望/满意/庆幸/可惜
- 宣告: 宣布/宣告/任命

LLM 标了 directive 但无强信号时降级为 assertive。

**validate_chunk**:
- 补充 10 个默认字段 (`role`, `intent`, `relation`, `argument_role`, `argument_relation`, `scope`, `dependency`, `cue_phrase`, `thread_id`, `anchor_type`)
- 枚举值校验:
  - role: nucleus/satellite
  - intent: assertive/directive/commissive/expressive/declaration
  - relation: cause/result/evidence/elaboration/background/condition/purpose/summary/contrast/concession/sequence/attribution/evaluation/restatement/none
  - thread_id: main/sub/latent
  - anchor_type: none/foreshadow/reveal

**apply_rst_role** (RST 理论规则):
- 多核关系 (contrast/sequence/summary/restatement) -> nucleus
- 单核卫星关系 (evidence/elaboration/background/condition/purpose/concession) -> satellite
- 因果: "因为/由于" -> satellite, "所以/因此" -> nucleus
- relation="none" 时尊重 LLM 的原始 role 判断

**infer_scope**:
- 保留 LLM 输出
- 空值时从 dependency 提取前 8 字符作为回退（跳过代词）

**check_pronouns**:
- 检测代词 (他/她/它/他们/她们/它们/这/那/这个/那个/这里/那里/这些/那些)
- 代词存在但 scope 和 dependency 都空 -> 设置 `_pronoun_needs_resolution = True` 标记
- 不再污染 scope 字段，代词消解在 GraphUpdater 中通过图谱回溯完成

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
- `get_active_summary()`: 返回激活节点摘要列表

### 3.4 前缀去噪 (`prefix_pruner.py`)

正则模式完整原文:
```python
_PREFIX_PATTERN = re.compile(
    r"^("
    r"第[一二三四五六七八九十]+(?:个|点|部分|步)?\s*[,，、]?\s*"
    r"|其次\s*[,，、]?\s*"
    r"|再然后\s*[,，、]?\s*"
    r"|我发现[啊]?[,，、]?\s*"
    r"|就是说\s*[,，、]?\s*"
    r"|还有就是\s*[,，、]?\s*"
    r"|哦对了\s*[,，、]?\s*"
    r"|然后呢\s*[,，、]?\s*"
    r"|还有[啊]?[,，、]?\s*"
    r"|另外[啊]?[,，、]?\s*"
    r")"
)
```

匹配 10 种口语前缀脚手架: 第X(个/点/部分/步)、其次、再然后、我发现(啊)、就是说、还有就是、哦对了、然后呢、还有(啊)、另外(啊)。

函数:
- `clean_sentence_prefix(text)`: 单句去噪
- `clean_batch(texts)`: 批量去噪

---

## 4. 图谱模块 (`src/text_reconstructor/graph/`)

### 4.1 EdgeType 枚举 (19 种)

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
| RESTATEMENT | RST | 重申关系 |
| ATTACK | Dung AF | 反驳关系 |
| SUPPORT | Dung AF | 支持关系 |
| CO_SCOPE | 工程 | 同域弱连接 |
| THREAD_BRIDGE | 多线叙事 | 跨线程桥接 |
| REVEAL | 多线叙事 | 伏笔照应 |

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
| thread_id | str | main | 叙事线程 (main/sub/latent) |
| anchor_type | str | none | 锚定类型 (none/foreshadow/reveal) |

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

**规则 5 -- 多线叙事建边**:
- THREAD_BRIDGE: 副线节点 (thread_id != "main") 且 scope 与主线节点匹配时，副线 -> 主线
- REVEAL: anchor_type == "reveal" 的节点与 anchor_type == "foreshadow" 的节点通过 bigram 重叠匹配，满权激活

Bigram 重叠检测:
```python
for i in range(len(text_a) - 1):
    bigram = text_a[i:i+2]
    if bigram in text_b:
        return True
```

**规则 6 -- 代词图谱回溯消解**:
- 策略 1: 沿 CO_SCOPE 边反向寻找最近的 nucleus，隐式绑定 scope
- 策略 2: 时间轴反向，最多 5 步，找到最近的有效 scope nucleus
- 5 步都找不到时保留 `_pronoun_needs_resolution` 标记

**规则 7 -- ActiveBuffer 更新**:
- 每处理一个节点后: `active_buffer.add_node(node)` + `active_buffer.tick(tokens=len(text))`
- process() 返回值加入 `active_summary` 字段

**衰减**:
- 每处理一个 chunk 后对所有节点应用 Ebbinghaus 衰减

### 4.4 DecayEngine

Ebbinghaus 对数衰减公式:
```
weight = initial_weight / (1 + rate * log(1 + age))
```

rate 的确定逻辑:
1. 若 `anchor_type == "foreshadow"` (伏笔): `rate = 0.01` (时空胶囊，几乎不衰减)
2. 否则: `rate = min(role_rate, thread_rate)`

role-based 衰减速率:

| role | rate | 理由 |
|------|------|------|
| nucleus | 0.3 | 核心信息衰减最慢 |
| action | 0.3 | 动作信息同样重要 |
| commitment | 0.4 | 承诺/计划次之 |
| satellite | 0.6 | 辅助信息中等 |
| expressive | 1.0 | 情感表达最快遗忘 |

thread-based 衰减速率:

| thread_id | rate | 理由 |
|-----------|------|------|
| main | 0.3 | 主线最重要 |
| sub | 0.6 | 副线衰减较快 |
| latent | 0.05 | 暗线需要长期记忆 |

唤醒机制: `reactivate(node, step)` -> `weight = min(1.0, weight + 0.3)`

### 4.5 AdversaryScanner (7 项扫描)

| 编号 | 类型 | 检测条件 | severity |
|------|------|----------|----------|
| 1 | LOW_CONFIDENCE | confidence < 0.5 | medium |
| 2 | ISOLATED_NODE | degree == 0 | low |
| 3 | LOGIC_CONFLICT | ATTACK 入边 > SUPPORT 入边 | medium |
| 4 | DANGLING_DIRECTIVE | directive 无 CAUSE 入边 | medium |
| 5 | STRUCTURE_CHAOS | 同 scope 内 ATTACK+CONTRAST >= 3 | medium/high |
| 6 | UNRESOLVED_PRONOUN | 代词存在但无 BACKGROUND 入边消解 | medium |
| 7 | ARGUMENT_GAP | nucleus assertive 无 SUPPORT/EVIDENCE 入边 | medium |

去重: 相同 `(type, text)` 或 `(type, scope)` 的 alert 合并计数。

---

## 5. 对抗机模块 (`src/text_reconstructor/adversary/`)

### 5.1 双轨混合对抗 (`semantic_router.py`)

**轨道 1 -- Python 拓扑粗筛** (`scan_topology`):

3 种可疑模式:
1. same_scope_no_logical_edge: 同 scope 内两个活跃节点之间无逻辑边
2. dangling_directive: directive 节点缺少 CAUSE/CONDITION/BACKGROUND 入边，与前一句组成可疑对

**轨道 2 -- LLM 精准语义审计** (`audit_pair`):

LLM System Prompt 完整原文:
```
You are a precise logic auditor. You analyze pairs of statements to detect contradictions, vague concepts, or missing logical chains.
Reply concisely in Chinese. If no issue exists, reply exactly "SAFE".
```

LLM User Prompt 模板:
```
判断以下两句话是否存在逻辑矛盾、资源冲突或概念模糊：

语句A：{node_a_text}
语句B：{node_b_text}

如果不冲突，直接回复 SAFE。
如果存在冲突或模糊，用一句话指出问题核心并给出建议。
```

成本控制: 最多审计前 5 对可疑节点。

输出 alert 格式:
```python
{"type": "SEMANTIC_CONFLICT", "node_id": ..., "text": ..., "detail": finding,
 "severity": "high", "related_node_id": ...}
```

接入方式: GraphUpdater 构造函数传入 `llm_config` 参数，自动创建 SemanticAdversaryRouter 实例，在对抗机周期末尾调用。

### 5.2 Prosecutor (起诉构建)

每种 alert 类型有预定义的:
- required_evidence: 需要什么证据
- evidence_targets: 搜索方法优先级列表

言语行为增强:
- assertive -> 搜索 incoming_evidence
- directive -> 搜索 incoming_background
- commissive -> 搜索 future_reference
- expressive -> 搜索 incoming_cause + same_scope

第 2 轮扩展搜索范围 (增加 same_scope + global_text_match)。

### 5.3 Defender (11 种搜索策略)

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

### 5.4 ConfidenceManager

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

### 5.5 AlertBuffer

- 去重键: (alert_type, node_id)
- 排序: severity (high > medium > low) -> 轮次 -> 计数

---

## 6. 输出模块 (`src/text_reconstructor/output/`)

### 6.1 LLMRefiner (主力)

temperature = 0.15 (高保真重构而非创造性写作)

**STRUCTURING_PROMPT 完整原文**:
```
你是一个文本重构专家。请将以下标注好的散句组织为结构清晰、逻辑连贯的段落。

核心原则 -- 必须遵守：
1. 保留原文所有细节、数据、专有名词、URL -- 不允许任何信息丢失
2. 保留每个句子的主谓宾结构和实质内容，不得缩写或合并
3. 绝不能概括、总结或精简 -- 是"梳理复述"而非"概括摘要"
4. 删除无意义的填充词（啊、呢、嗯、对吧、是不是）
5. 区分口语化填充词和语言特点/文本细节 -- 前者可删，后者必留

结构和表达：
6. 按主题分组，用 ## 话题名 作为二级标题
7. 话题内用清晰的分段和分点阐述，逻辑层次鲜明
8. 添加恰当的逻辑过渡词（然而、具体而言、在此背景下、与此相反、例如）
9. 行文流畅清晰，表达得体，方便人与AI阅读

硬性约束：
10. 原文中出现的关键数据、URL、强特征比喻必须原样保留
11. 对原文中模糊、未定义的概念标注为 [疑点]
12. 发现的逻辑矛盾或遗漏单独列在 [发现的问题] 下
13. 下方列出的逻辑关系必须在输出中通过过渡词或结构安排体现
```

**_build_prompt 构造逻辑**:
1. 节点行: `(scope) [role/relation] text`，每个节点 text 经过 `clean_sentence_prefix()` 前缀去噪
2. 边行: `- [标签] 「src_text[:25]」 --> 「tgt_text[:25]」`，跳过 co_scope 类型，最多展示 25 条
3. 关系标签映射 (_RELATION_LABELS):

| EdgeType | 中文标签 |
|----------|----------|
| cause | 因果 |
| result | 结果 |
| evidence | 举例 |
| elaboration | 阐述 |
| background | 背景 |
| condition | 条件 |
| purpose | 目的 |
| contrast | 转折 |
| concession | 让步 |
| sequence | 时序 |
| support | 支持 |
| attack | 反驳 |

### 6.2 细节锚定 (`detail_anchor.py`)

四种提取正则:

| 类型 | 正则 | 说明 |
|------|------|------|
| url | `r'https?://[^\s,，。；;）)、]+'` | URL |
| number | `r'\d+(?:\.\d+)?[%％]'` 等 4 个分支 | 百分比/数量词/范围/带量词数字 |
| metaphor | `r'(?:像\|如同\|好比\|仿佛\|就像\|好似\|犹如\|宛若)'` | 比喻标记词 + 后续 8 字符 |
| quoted_term | `r'[""「」『』](.{2,10})[""「」『』]'` | 引号内 2-10 字符术语 |

### 6.3 FCR 事实覆盖率 (`fcr.py`)

算法: 精确 String Match
```
FCR = preserved / total
```
遍历所有锚点，检查 `anchor.text` 是否为 `reconstructed_text` 的子串。

返回值: `{fcr: float, total: int, preserved: int, missing: list[str]}`

### 6.4 Suggestions (`suggestions.py`)

只输出高危逻辑中断:
- 允许类型: `DANGLING_DIRECTIVE`, `LOGIC_CONFLICT`
- 最低严重级别: medium

格式: `[建议 {idx}/{total}] {优先级标签}: {detail}`

### 6.5 TextOutput (回退/调试)

1. Kahn 算法拓扑排序 (排除 CO_SCOPE 边)
2. 按 scope 分组
3. 基于最近入边类型的缩进: `+` support, `-` attack, `->` 渐进

---

## 7. 评估模块 (`src/text_reconstructor/evaluation/`)

### 7.1 对比方法

- **基线**: 直接发送原文给 LLM, 使用 BASELINE_PROMPT
- **管线**: 完整 pipeline (splitter -> tagger(streaming) -> updater -> refiner)
- **评分**: LLM 对比两个输出, 4 维度 0-10 分
- **FCR**: 客观事实覆盖率补充 LLM 主观评分

### 7.2 基线 Prompt 完整原文

**BASELINE_PROMPT**:
```
请梳理以下文本的结构和逻辑，保留所有细节。

要求：
1. 按话题分段输出
2. 保留原文每一个观点、细节、例子，不压缩不省略
3. 使用恰当的连接词体现逻辑关系
4. 修正口语化表达，但保持原意不变
5. 对模糊/不确定的概念标明

原文：
{text}
```

### 7.3 评分 Prompt 完整原文

**SCORING_PROMPT**:
```
你是一个文本评估专家。请对两个"文本梳理"结果进行评分。

评分维度（每个维度 0-10 分）：
1. detail_preservation（细节保留）：是否保留了原文所有细节、观点、例子？有没有遗漏？
2. doubt_identification（疑点识别）：是否识别出模糊概念、不确定的表述、潜在问题？
3. fuzzy_concept_handling（模糊处理）：对原文中模糊/歧义的表达，处理是否合理？是过度猜测还是正确保留？
4. structure_clarity（结构清晰）：逻辑结构是否清晰？分段分点是否合理？是否方便人类和AI阅读？

原文：
{original}

--- 基线输出（直接LLM梳理）---
{baseline}

--- 系统输出（管线处理）---
{pipeline_result}

请输出纯 JSON 格式的评分结果（不要 markdown 代码块，不要 ```json 标记，只输出 JSON 对象本身）：
{
    "baseline": {
        "detail_preservation": X,
        "doubt_identification": X,
        "fuzzy_concept_handling": X,
        "structure_clarity": X
    },
    "pipeline": {
        "detail_preservation": X,
        "doubt_identification": X,
        "fuzzy_concept_handling": X,
        "structure_clarity": X
    },
    "summary": "简要评述两个输出的主要差异"
}
```

### 7.4 FCR 客观指标

`compute_fcr_scores()` 方法同时计算基线和管线的 FCR，返回:
```python
{
    "baseline_fcr": float,
    "pipeline_fcr": float,
    "baseline_missing": list[str],
    "pipeline_missing": list[str],
    "anchor_count": int,
}
```

### 7.5 评估报告

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
| 时空胶囊衰减 | `decay.py: compute_weight()` | foreshadow rate=0.01 |
| 多线叙事衰减 | `decay.py: compute_weight()` | thread_id 差异化 rate |
| AGM 信念修正 | `alert_buffer.py: ConfidenceManager` | confidence 更新 + 矛盾消解 |
| Allen 时序逻辑 | `models.py: SEQUENCE` | 时序关系边 |
| 因果图模型 | `models.py: CAUSE/RESULT` | 因果关系边 |
| 多线叙事 | `updater.py: _add_multithread_edges()` | THREAD_BRIDGE/REVEAL 边 |
| 代词消解 | `updater.py: _resolve_pronoun_via_graph()` | CO_SCOPE 回溯 + 时间轴反向 |
| 双轨对抗 | `semantic_router.py` | 拓扑粗筛 + LLM 审计 |

---

## 9. 科学有效性审查清单

| 编号 | 问题 | 状态 | 修复说明 |
|------|------|------|----------|
| 1 | Batch 标注曾砍到 4 字段 | 已修复 | 恢复 10 字段 + 6 个多样化示例 + ISA 说明 |
| 2 | DecayEngine 未实现 | 已修复 | Ebbinghaus 对数衰减 + role/thread/anchor 三维 rate |
| 3 | ActiveBuffer 是空壳 | 已修复 | 完整实现 + 接入 GraphUpdater + Mini-Batch 上下文 |
| 4 | 图边仅连最近 nucleus | 已修复 | contrast 优先同 scope, argument 优先 claim |
| 5 | 信号词硬编码覆盖 | 已修复 | 可配置 override_with_rules, 强模型下关闭 |
| 6 | 对抗机仅结构检查 | 已修复 | 双轨混合对抗: 拓扑粗筛 + LLM 语义审计 |
| 7 | infer_scope 是空操作 | 已修复 | dependency 回退 8 字符 + 代词过滤 |
| 8 | LLMRefiner Prompt 过于简单 | 已修复 | 13 条规则 + 边关系描述 + 前缀去噪 |
| 9 | 无客观验证 | 已修复 | FCR 事实覆盖率 + DetailAnchor 锚定 |
| 10 | RST 过度修正 | 已修复 | relation=none 不再强制降级 satellite |
| 11 | 代词消解污染 scope | 已修复 | 独立 _pronoun_needs_resolution 标记 |
| 12 | Scope 推理触发不当 | 已修复 | 质量检查触发替代数量检查 |
| 13 | 无多线叙事支持 | 已修复 | thread_id/anchor_type + THREAD_BRIDGE/REVEAL |
| 14 | 对抗机噪音过多 | 已修复 | 只输出 DANGLING_DIRECTIVE + LOGIC_CONFLICT |

---

## 10. 数据流全图

```
输入文本 (CLI 参数/文件/stdin)
    |
    +-- SentenceSplitter.split() --> sentences: list[str]
    |
    +-- Tagger.batch_tag_streaming(sentences)  [默认, 8句一批]
    |   |  每批:
    |   +-- LLM: Mini-Batch 标注 (10 字段, 含 thread_id/anchor_type)
    |   +-- apply_signal_corrections (可关闭)
    |   +-- apply_intent_corrections (可关闭)
    |   +-- validate_chunk (10 字段默认值 + 枚举校验)
    |   +-- apply_rst_role (RST 理论修正)
    |   +-- infer_scope (dependency 回退 8 字符)
    |   +-- check_pronouns (_pronoun_needs_resolution 标记)
    |   +-- 更新 ActiveBuffer context (Top-3)
    |   |
    |   +-- LLM: scope 推理 (质量检查触发, 二次调用)
    |
    +-- GraphUpdater.process(chunks, llm_config=...)
    |   |  对每个 chunk:
    |   |  +-- 创建 GraphNode (weight=1.0, thread_id, anchor_type)
    |   |  +-- 规则1: relation -> EdgeType 边
    |   |  +-- 规则2: argument_relation -> ATTACK/SUPPORT 边
    |   |  +-- 规则3: CO_SCOPE 弱连接 (同 scope, 距离<5)
    |   |  +-- 规则4: DEPENDS -> BACKGROUND 边
    |   |  +-- 规则5: 多线叙事 THREAD_BRIDGE/REVEAL
    |   |  +-- DecayEngine: 对所有节点应用衰减 (含时空胶囊)
    |   |  +-- 规则6: 代词图谱回溯消解 (CO_SCOPE + 时间轴)
    |   |  +-- 规则7: ActiveBuffer.add_node + tick
    |   |  +-- graph.tick()
    |   |
    |   +-- 对抗机周期:
    |       +-- AdversaryScanner.scan() (7 项检查)
    |       +-- Prosecutor.build() (起诉构建 + 言语行为增强)
    |       +-- ConfidenceManager.run_node_cycle() (逐节点)
    |       |   +-- Round 1: Prosecutor -> Defender -> 增量 -> 更新 confidence
    |       |   +-- Round 2: 扩展搜索 -> Defender -> 增量 -> 更新 confidence
    |       +-- AlertBuffer: 收集 confidence < 0.7 的 alert
    |       +-- SemanticAdversaryRouter.run() (双轨混合对抗, 需 llm_config)
    |           +-- 轨道1: scan_topology() (Python 拓扑粗筛)
    |           +-- 轨道2: audit_pair() (LLM 语义审计, 最多 5 对)
    |
    +-- LLMRefiner.refine(snapshot) --> 结构化文本 (LLM #3)
    |   +-- STRUCTURING_PROMPT (13 条规则)
    |   +-- _build_prompt: 节点行(前缀去噪) + 边行(关系标签, 最多25条)
    |   +-- temperature = 0.15
    |   +-- 回退: TextOutput.format_simple() (模板式)
    |
    +-- FCR 验证: extract_from_sentences -> compute_fcr (String Match)
    |   +-- 丢失实体 -> logger.warning
    |
    +-- Suggestions.format(alerts) --> 改进建议 (stderr)
        +-- 只输出 DANGLING_DIRECTIVE + LOGIC_CONFLICT (severity >= medium)
```

---

## 11. CLI 命令

### 11.1 main (文本重构)

```bash
text-reconstructor [OPTIONS] [TEXT]

Options:
  --file, -f          从文件读取输入
  --skip-adversary    跳过对抗机验证
  --output-format     auto(LLM重构,默认) / template(模板式)
  --backend           ollama(默认) / nvidia / deepseek
  --api-key           API Key (或环境变量 NVIDIA_NIM_API_KEY)
  --no-streaming      禁用 Mini-Batch 流式标注 (默认启用)
```

### 11.2 evaluate (对比评估)

```bash
text-reconstructor evaluate [OPTIONS]

Options:
  --backend           ollama / nvidia / deepseek(默认)
  --api-key           API Key
  --output-report     报告输出路径 (默认: 评估报告.md)
```
