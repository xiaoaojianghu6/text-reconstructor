# 文本重构项目 - 总体架构设计

> 版本: 2.0
> 日期: 2026-06-04
> 状态: 已评审通过

## 1. 核心设计原则

### 1.1 双后端架构

系统支持两种 LLM 后端，通过工厂函数自动分发：

| 后端 | 模型 | 用途 | 速率 |
|------|------|------|------|
| Ollama (本地) | qwen3.5:0.8B | 离线标注/推理 | 无限制 |
| NVIDIA (云端) | deepseek-v4-flash/pro | 科学性验证/评估 | 40 req/min |

**小模型时**: 后处理规则修正 (regex 覆盖 LLM 错误)、零 LLM 纯规则模块（图谱、对抗机）补偿能力不足。
**强模型时**: 关闭规则覆盖 (`override_with_rules=False`)，信任 LLM 判断。

### 1.2 模块独立

每个模块通过明确的 Dict 协议通信，不直接耦合。可以独立开发、测试、替换。

### 1.3 双输出通道

- **输出 1**: LLMRefiner 结构化输出（按 scope 分段、分点阐述、保留全部信息）
- **输出 2**: 改进建议（AlertBuffer 格式化输出到 stderr）
- **回退**: LLM 失败时 TextOutput 按 scope 分组输出原句

### 1.4 科学有效性优先

- 绝不压缩/省略/总结原文信息
- 模糊概念明确标注 [疑点]
- 发现的问题单独列出
- 所有实现有理论映射 (RST / Speech Act / Dung AF / Ebbinghaus / AGM)

---

## 2. 整体数据流

```
输入文本 (CLI 参数/文件/stdin)
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│  Processor (标注处理器)                                        │
│                                                                │
│  SentenceSplitter ──→ Tagger (LLM 批量标注 8 字段)                │
│   (分句)               │                                         │
│                        ├─ apply_signal_corrections (可关闭)       │
│                        ├─ apply_intent_corrections (可关闭)       │
│                        ├─ validate_chunk (枚举校验+默认值)         │
│                        ├─ apply_rst_role (RST 规则)               │
│                        ├─ infer_scope (dependency 回退)           │
│                        └─ check_pronouns (代词检测)               │
│                        │                                         │
│                        └─ 输出: list[ChunkDict] (8 字段)          │
│                                                                │
│  ActiveBuffer (跨距离上下文, DecayEngine 驱动)                   │
│   ├─ add_node / tick / reference / get_top_k / scavenge         │
│   └─ Ebbinghaus 对数衰减: w / (1 + rate * log(1 + age))        │
└────────────────────┬─────────────────────────────────────────┘
                     │ Chunk 数组
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Graph (增量语义图谱)                                          │
│                                                                │
│  ChunkDict ──→ GraphNode ──→ GraphUpdater ──→ DecayEngine     │
│   (标注数据)    (转节点)       (入图+建边)     (Ebbinghaus衰减) │
│                                                                │
│  建边规则 (纯映射，无 LLM):                                     │
│   规则1. relation 直映 EdgeType                                 │
│          - contrast/concession 优先同 scope nucleus            │
│          - 其他连最近 nucleus/前序节点                          │
│   规则2. argument_relation 直映 ATTACK/SUPPORT                  │
│          - 优先同 scope assertive/directive 节点                │
│   规则3. 同 scope 且距离<5 → CO_SCOPE 双向弱连接               │
│   规则4. dependency 非空 → BACKGROUND 边 + reactivate          │
└────────────────────┬─────────────────────────────────────────┘
                     │ 节点/边
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Adversary (对抗机)                                            │
│                                                                │
│  AdversaryScanner (7 项扫描):                                   │
│   ① conf < 0.5 → 模糊概念                                      │
│   ② degree==0 → 孤立节点                                       │
│   ③ ATTACK 入边 > SUPPORT 入边 → 逻辑冲突                      │
│   ④ directive 无 CAUSE 入边 → 悬空指令                         │
│   ⑤ 同 scope 内 ATTACK+CONTRAST ≥ 3 → 结构混乱                │
│   ⑥ UNRESOLVED_PRONOUN → 代词未消解                            │
│   ⑦ ARGUMENT_GAP → claim 无 premise 支持                       │
│                                                                │
│  Prosecutor ──→ Defender (最多 2 轮) ──→ ConfidenceManager     │
│   (起诉构建)      (11 策略搜索)    (0.5/0.7 阈值)              │
│                                        │                       │
│                                        ▼                       │
│                                   AlertBuffer                  │
│                                 (去重+优先级排序)              │
└────────────────────┬─────────────────────────────────────────┘
                     │ alerts
                     ▼
┌──────────────────────────────────────────────────────────────┐
│  Output (输出模块)                                             │
│                                                                │
│  LLMRefiner (主力) ──→ 按 scope 分组 → 分段分点 → 结构化文本    │
│     ├─ 绝不压缩/省略                                            │
│     ├─ 模糊概念标注 [疑点]                                      │
│     └─ 矛盾/遗漏列在 [发现的问题]                               │
│                                                                │
│  TextOutput (回退) ──→ 拓扑排序 → 按 scope 分组输出原句         │
│  Suggestions ──→ AlertBuffer → 改进建议到 stderr               │
└──────────────────────────────────────────────────────────────┘
```

### LLM 调用流程

```
对话中最多 2-3 次 LLM 调用（非每句）:

LLM #1: Tagger.batch_tag() — 一次调用批量标注所有句子
LLM #2: Tagger 条件触发 — 仅当 scope ≤ 2 种时推理 scope
LLM #3: LLMRefiner.refine() — 结构化分段输出
```

---

## 3. 核心数据结构

### 3.1 Chunk JSON Schema

每句经 LLM 标注后输出的 8 字段标准格式——整个系统的核心数据交换格式。

```python
CHUNK_SCHEMA = {
    "type": "object",
    "required": [
        "text", "role", "intent", "relation",
        "argument_role", "argument_relation", "scope", "dependency"
    ],
    "properties": {
        # ── 文本 ──
        "text":             {"type": "string"},   # 原文

        # ── RST 角色 ──
        "role": {
            "type": "string",
            "enum": ["nucleus", "satellite"],
            "description": "核心信息/辅助信息"
        },

        # ── 言语行为意图 ──
        "intent": {
            "type": "string",
            "enum": ["assertive", "directive", "commissive", "expressive", "declaration"],
            "description": "陈述事实/发出指令/做出承诺/表达情感/宣告声明"
        },

        # ── RST 修辞关系 ──
        "relation": {
            "type": "string",
            "enum": [
                "cause", "result", "evidence", "elaboration",
                "background", "condition", "purpose", "summary",
                "contrast", "concession", "sequence", "attribution",
                "evaluation", "restatement", "none"
            ],
            "description": "因果/结果/证据/阐述/背景/条件/目的/总结/对比/让步/时序/归因/评价/重述/无"
        },

        # ── 论证分析 ──
        "argument_role": {
            "type": "string",
            "enum": ["premise", "claim", "none"],
            "description": "论据/结论/无"
        },
        "argument_relation": {
            "type": "string",
            "enum": ["support", "attack", "none"],
            "description": "支持/反驳/无"
        },

        # ── 指代/依赖 ──
        "scope":        {"type": "string"},   # 所属主题域
        "dependency":   {"type": "string"},   # 依赖的节点 text

        # ── 信号词证据 ──
        "cue_phrase":   {"type": "string"},   # 触发 relation 判断的关键词
    }
}
```

### 3.2 Node 数据结构

```python
@dataclass
class GraphNode:
    id: int                    # 自增 ID
    text: str                  # 文本内容
    role: str                  # nucleus / satellite
    intent: str                # assertive / directive / ...
    relation: str              # cause / contrast / ...
    scope: str                 # 主题域
    chunk_index: int           # 在原始文本中的位置序号
    confidence: float          # 置信度 [0, 1]，默认 0.6
    weight: float              # 衰减权重 [0, 1]（Ebbinghaus 衰减后变化）
    token_count: int           # 字符数
    created_at: int            # 创建时的全局步数
    last_referenced_at: int    # 最后被引用时的步数
```

### 3.3 Edge 数据结构

```python
@dataclass
class GraphEdge:
    source_id: int
    target_id: int
    edge_type: EdgeType
    confidence: float
```

### 3.4 EdgeType 枚举（17 种）

```python
class EdgeType(Enum):
    # RST 来源
    CAUSE        = "cause"
    RESULT       = "result"
    EVIDENCE     = "evidence"
    ELABORATION  = "elaboration"
    BACKGROUND   = "background"
    SEQUENCE     = "sequence"
    CONDITION    = "condition"
    PURPOSE      = "purpose"
    CONTRAST     = "contrast"
    CONCESSION   = "concession"
    SUMMARY      = "summary"
    ATTRIBUTION  = "attribution"
    EVALUATION   = "evaluation"
    RESTATEMENT  = "restatement"

    # 论证框架来源
    ATTACK       = "attack"
    SUPPORT      = "support"

    # 弱连接（scope 共享）
    CO_SCOPE     = "co_scope"
```

### 3.5 LLMConfig

```python
@dataclass
class LLMConfig:
    model: str = "qwen3.5:0.8b"
    base_url: str = "http://localhost:11434"
    timeout: float = 30.0
    temperature: float = 0.1
    max_tokens: int = 2048
    top_p: float = 0.9
    think: bool = False
    backend: str = "ollama"      # "ollama" / "nvidia"
    api_key: str = ""            # NVIDIA API 密钥
```

---

## 4. 模块接口契约

所有模块通过 dict 协议通信，不直接引用彼此的内部类：

```
InputLayer (CLI)
  输入: raw_text: str
  输出: raw_text: str

Processor (SentenceSplitter + Tagger)
  输入: raw_text: str
  输出: chunks: list[ChunkDict]    ← 8 字段标注数组

Graph (NodeFactory + Updater + DecayEngine + AdversaryScanner)
  输入: chunks: list[ChunkDict]
  输出: {
    "nodes": list[NodeDict],       ← 含 id/text/role/confidence/weight
    "edges": list[EdgeDict],       ← 含 source_id/target_id/edge_type
    "alerts": list[AlertDict]      ← 对抗机产出的提示
  }

Adversary (Prosecutor + Defender + ConfidenceManager)
  输入: {"nodes": ..., "edges": ...}
  输出: alerts: list[AlertDict]    ← confidence < 0.7 的 alert

Output (LLMRefiner / TextOutput + Suggestions)
  输入: {
    "nodes": list[NodeDict],
    "edges": list[EdgeDict],
    "alerts": list[AlertDict]
  }
  输出: {
    "text_output": str,             ← 结构化文本（输出 1）
    "suggestions": list[str]        ← 改进建议列表（输出 2）
  }
```

---

## 5. 小模型 (0.8B) 缓解策略矩阵

| # | 策略 | 模块 | 说明 |
|---|------|------|------|
| 1 | **批量标注** | Tagger | 一次 LLM 调用标注所有句子（非每句调用） |
| 2 | **信号词规则修正** | Tagger 后处理 | regex 检测覆盖 LLM 的 relation 错误（可关闭，强模型下信任 LLM） |
| 3 | **cue_phrase 追踪** | Tagger | LLM 输出触发关键词，后处理交叉验证 |
| 4 | **ActiveBuffer 压缩** | Buffer | 只保留 Top-K 活跃节点，限制 token 量 |
| 5 | **多样化枚举示例** | Tagger Prompt | 6 个示例句覆盖全部 intent/relation/argument 组合 |
| 6 | **零 LLM 图谱建边** | GraphUpdater | relation 字段直接映射 EdgeType，不调用 LLM |
| 7 | **Ebbinghaus 衰减** | DecayEngine | `w = w0 / (1 + rate * log(1 + age))` 纯数学函数 |
| 8 | **零 LLM 对抗机** | Adversary | 纯规则检测：7 项扫描 + 言语行为增强 |
| 9 | **保守默认置信度** | Adversary | 默认 conf=0.6；辩论增减 |
| 10 | **max_tokens=2048** | LLMConfig | 批量标注需更大输出空间 |
| 11 | **temperature=0.1** | LLMConfig | 极低温度，确保可重复性 |
| 12 | **JSON mode 强制** | Ollama | `format: "json"` 确保解析成功率 |
| 13 | **枚举控制在合理范围** | Schema | relation 16 种，intent 5 种 |
| 14 | **后处理默认值填充** | Tagger | 缺字段用默认值，不重试 LLM |
| 15 | **2 轮硬限制** | Adversary | 正反方最多 2 轮 |
| 16 | **Alert 去重** | Adversary | 同类型 alert 合并计数 |
| 17 | **简单中文 Prompt** | Tagger | 短句+列表+例子，避免复杂指令 |
| 18 | **条件触发 scope 推理** | Tagger | 仅当 scope ≤ 2 种时二次 LLM 调用，减少消耗 |

---

## 6. 错误处理矩阵

| 场景 | 检测 | 恢复 | 降级 |
|------|------|------|------|
| Ollama 连接失败 | httpx.ConnectError | 重试 1 次 | 返回空 chunk |
| NVIDIA 连接失败 | httpx.ConnectError | 重试 1 次 | 返回空 chunk |
| NVIDIA 速率限制 | HTTP 429 | 令牌桶等待 | 返回空 chunk |
| LLM JSON 解析失败 | json.JSONDecodeError | regex 提取 | 默认值填充 |
| LLM 超时 | httpx.TimeoutException | 跳过当前 batch | 记录 alert |
| LLM 空 content | `content == ""` | 回退 thinking | 同上 |
| Chunk 缺字段 | jsonschema 校验 | 补充默认值 | warning |
| relation 与信号词矛盾 | regex 检测 | 以信号词为准 | 可配置关闭 |
| 图谱节点冲突 | id 计数器 | 自动自增 | 无影响 |
| 对抗机超 2 轮 | 回合计数 | 强制中断 | 推 AlertBuffer |
| Ollama 非 JSON | format:json | try/except | 跳过本轮 |
| Buffer OOM | token 计数器 | evict 最低权重 | 入衰减池 |
| LLMRefiner 失败 | 空输出 | 回退 TextOutput | stderr 提示 |

---

## 7. LLM 后端适配器

### 7.1 OllamaClient

- 端点: `/api/chat`
- 格式: Ollama 原生 (model, messages, stream, think, options)
- JSON mode: `body.format = "json"`
- 流式: NDJSON 逐行拼接 `message.content`，回退 `message.thinking`
- 无代理: `httpx.HTTPTransport(proxy=None)`

### 7.2 NVIDIAClient

- 端点: `https://integrate.api.nvidia.com/v1/chat/completions`
- 格式: OpenAI 兼容 (model, messages, temperature, max_tokens)
- 认证: `Authorization: Bearer {api_key}`
- 速率限制: 内置令牌桶 (40 req/min)
- 非流式: 一次性返回完整响应
- 响应映射: `choices[0].message.content` → LLMResponse

### 7.3 工厂函数

```python
create_client(config: LLMConfig) -> OllamaClient | NVIDIAClient
```

根据 `config.backend` ("ollama" / "nvidia") 自动分发。

---

## 8. 评估模块

### 8.1 对比方法

- **基线**: 直接发送原文给 LLM, prompt="请梳理以下文本的结构和逻辑，保留所有细节"
- **管线**: 完整 pipeline (splitter → tagger → updater → refiner)
- **评分**: LLM 对比两个输出，4 维度 0-10 分

### 8.2 评分维度

| 维度 | 评估内容 |
|------|----------|
| detail_preservation | 细节保留程度（是否有遗漏） |
| doubt_identification | 疑点/模糊概念识别 |
| fuzzy_concept_handling | 模糊处理合理性（不过度猜测） |
| structure_clarity | 结构逻辑清晰度（分段分点） |

### 8.3 CLI

```bash
text-reconstructor evaluate --backend nvidia
```

生成 `评估报告.md`，含原文摘要、基线输出、管线输出、评分对比。

---

## 9. 理论 → 实现映射表

| 理论概念 | 实现位置 | 具体映射 |
|----------|----------|----------|
| RST nucleus/satellite | `tagger.py: apply_rst_role()` | chunk.role 字段 |
| RST 修辞关系 | `models.py: EdgeType` | chunk.relation → EdgeType 边 |
| Searle 言语行为五分类 | `tagger.py: validate_chunk()` | chunk.intent 字段 |
| 间接言语行为 | `prompts.py: BATCH_TAGGING_TEMPLATE` | Prompt ISA 说明 + 示例 |
| Dung 论证框架 | `models.py: ATTACK/SUPPORT` | argument_relation → 边 |
| 论证挖掘 | `tagger.py: batch_tag()` | argument_role + argument_relation 字段 |
| Ebbinghaus 遗忘曲线 | `decay.py: DecayEngine` | 对数衰减公式 + role-based 速率 |
| AGM 信念修正 | `alert_buffer.py: ConfidenceManager` | confidence 更新 + 矛盾消解 |
| Allen 时序逻辑 | `models.py: SEQUENCE` | 时序关系边 |
| 因果图模型 | `models.py: CAUSE/RESULT` | 因果关系边 |

---

## 10. 10 大设计决策

| # | 决策 | 选择 | 放弃方案 | 理由 |
|---|------|------|---------|------|
| 1 | **主力模型** | qwen3.5:0.8B / NVIDIA deepseek | 4B (太慢) | 双后端适应不同场景 |
| 2 | **LLM 调用频率** | 每对话 2-3 次 | 每句多次 | 批量标注取代每句调用 |
| 3 | **标注方式** | 批量 8 字段 | 逐句标注 | 减少 10x LLM 调用 |
| 4 | **后处理** | Python regex (可关闭) | LLM 自修正 | 小模型补偿，强模型可关 |
| 5 | **图谱建边** | 纯规则 + scope 优先 | 语义相似度 | 确定性 O(1) |
| 6 | **衰减计算** | Ebbinghaus 对数 | 线性衰减 | 更符合认知科学 |
| 7 | **对抗机** | Python 规则 + 7 项扫描 | LLM Agent | 零 LLM 开销 |
| 8 | **输出主力** | LLMRefiner (LLM) | TextOutput | 质量更高，TextOutput 做回退 |
| 9 | **max_tokens** | 2048 | 512 | 批量标注需更大空间 |
| 10 | **上下文窗口** | ActiveBuffer (20 节点) | 固定 3 句 | 跨距离保留，可配置 |

---

## 11. 科学有效性审查清单

| 编号 | 问题 | 状态 | 修复说明 |
|------|------|------|----------|
| 1 | Batch 标注曾砍到 4 字段 | 已修复 | 恢复 8 字段 + 6 个多样化示例 + ISA 说明 |
| 2 | DecayEngine 未实现 | 已修复 | 实现 Ebbinghaus 对数衰减，role-based 速率 |
| 3 | ActiveBuffer 是空壳 | 已修复 | 完整实现激活/衰减/驱逐/打捞 |
| 4 | 图边仅连最近 nucleus | 已修复 | contrast 优先同 scope，argument 优先 claim |
| 5 | 信号词硬编码覆盖 | 已修复 | 可配置 override_with_rules，强模型下关闭 |
| 6 | 对抗机仅结构检查 | 已修复 | 新增 UNRESOLVED_PRONOUN + ARGUMENT_GAP |
| 7 | infer_scope 是空操作 | 已修复 | dependency 回退 + relation+intent 提示 |
