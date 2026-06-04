# 论证框架与因果图模型学习笔记

## 1. 理论概述

本笔记涵盖三个紧密关联的理论领域，它们共同为增量语义图谱的边类型设计和对抗机的逻辑检测提供形式化基础：

| 理论 | 核心关注 | 对本项目的价值 |
|------|----------|---------------|
| **Dung 抽象论证框架** | 论证之间的攻击/支持关系、可接受性语义 | 图谱边类型（ATTACK/SUPPORT）的定义、矛盾检测策略 |
| **论证挖掘 (Argumentation Mining)** | 从文本自动提取 Premise/Claim 和 Support/Attack 关系 | 小模型标注维度、图谱建边方法 |
| **因果图与时序逻辑** | 事件因果依赖 vs 时序依赖的区分 | EdgeType.CAUSE vs SEQUENCE 的设计、对抗机依赖检测 |

---

## 2. Dung 的抽象论证框架

### 2.1 基本定义

Dung (1995) 定义的抽象论证框架（Abstract Argumentation Framework, AAF）是最简洁的论证形式化模型：

**定义**：一个论证框架 `AF = (Args, Attack)`，其中：
- `Args` 是论证的有限集合（节点）
- `Attack ⊆ Args × Args` 是攻击关系（有向边）
- `(A, B) ∈ Attack` 表示 **A 攻击 B**

**关键特点**：论证的内部结构被完全抽象——只关心"谁攻击谁"，无论论证的内容是什么。

### 2.2 示例

```
        攻击
    A ──────→ B
    ↑         |
    | 攻击    | 攻击
    |         ↓
    D ←────── C
         攻击
```

在这个框架中：
- A 攻击 B
- B 攻击 C
- C 攻击 D
- D 攻击 A

### 2.3 可接受性语义

Dung 定义了一系列语义来确定哪些论证可以"被接受"。

#### 2.3.1 基本概念

| 概念 | 定义 | 直观理解 |
|------|------|----------|
| **Conflict-free（无冲突）** | 集合内没有任何论证相互攻击 | "不自相矛盾" |
| **Defended（被辩护）** | 对于攻击 S 中论证的每个攻击者，S 中都有论证反击之 | "能反驳所有反对意见" |
| **Admissible（可接受的）** | 集合是 Conflict-free 的，且每个成员都被辩护 | "站得住脚的立场" |

#### 2.3.2 主要语义

| 语义 | 定义 | 数量 | 直观理解 |
|------|------|------|----------|
| **Admissible（可接受）** | Conflict-free + Defended | 多个（空集总是） | 可辩护的立场 |
| **Complete（完备）** | Admissible + 包含所有它辩护的论证 | 多个 | 封闭的完备立场 |
| **Preferred（优先）** | 极大 Complete（按包含关系） | 至少一个 | 最大可辩护立场 |
| **Grounded（基础）** | 极小 Complete（按包含关系） | **唯一** | 最保守——无可争议的结论 |
| **Stable（稳定）** | Preferred + 攻击所有不在集合中的论证 | 零或多个 | 最激进——没有未决争议 |

#### 2.3.3 逐步示例

考虑框架：`A → B → C → D`（A 攻击 B，B 攻击 C，C 攻击 D）

```
Grounded 扩展的计算（迭代过程）:

第 1 轮:
- A 无攻击者 ← A 被接受
- A 攻击 B → B 被排除

第 2 轮:
- B 被排除后，C 不再被 B 攻击，但 C 是否被接受？
- C 是 A → B → C 链中的 B 被排除后再评估...
  实际上 C 的攻击者 B 被 A 击败了，所以 C 无攻击者 → C 被接受
- C 攻击 D → D 被排除

结果: Grounded = {A, C}
```

**对比各语义的结果**：

| 语义 | 扩展 | 含义 |
|------|------|------|
| **Grounded** | {A, C} | 最保守——只接受无可争议的 |
| **Preferred** | {A, C} | 最大可辩护 |
| **Stable** | {A, C} | 此时唯一 |

如果攻击关系更复杂，多个 Preferred 扩展可能共存（表示合理的意见分歧）。

### 2.4 支持关系的处理

原始 Dung 框架只定义了 Attack。后来的研究（如 ABA、Bipolar AF）加入了 **Support** 关系：

**Bipolar Argumentation Framework (BAF)**：`AF = (Args, Attack, Support)`
- Support 表示一个论证支持另一个
- 支持关系可以用来反驳攻击（"我的朋友支持我，所以你的攻击无效"）

**对本项目的意义**：我们的图谱需要同时支持 Attack 和 Support 两种有向边，再加上因果/时序等其他关系类型。

---

## 3. 论证挖掘（Argumentation Mining）

### 3.1 核心任务

论证挖掘是将非结构化文本自动转化为论证结构的 NLP 子领域，包含四个子任务：

```
原始文本 → [分割] → Argument Components → [分类] → Premise / Claim
                                                     ↓
                              Support/Attack ← [关系分类] ← 成对组件
```

| 子任务 | 缩写 | 描述 |
|--------|------|------|
| Argument Component Identification | ACI | 识别文本中的论证片段 |
| Argument Component Classification | ACC | 将片段分类为 Premise 或 Claim |
| Argument Relation Identification | ARI | 确定哪些片段之间存在论证关系 |
| Argument Relation Classification | ARC | 将关系分类为 Support 或 Attack |

### 3.2 主要方法 (2024-2025)

| 方法 | 性能 | 特点 |
|------|------|------|
| **FSP-ARC** (FrameNet + Siamese RoBERTa) | SOTA 跨 6 数据集 | 基于语义框架的关系分类 |
| **AASP** (自回归结构预测) | AAE: 62.69 ARC F1 | 端到端联合预测所有子任务 |
| **图结构知识 + LM** (Graph Embedding + RoBERTa) | 政治辩论显著提升 | 利用全局论证图结构增强关系预测 |
| **BERT + ChatGPT-4 Ensemble** | 比纯 Transformer 高 >10% | 大模型辅助论证组件分类 |
| **Chain-of-Thought + 事实验证** | LIARArg 数据 SOTA | 论证挖掘与事实验证联合 |

### 3.3 数据集

| 数据集 | 规模 | 领域 |
|--------|------|------|
| **AAE** | 多来源 | 通用 |
| **AAE-FG** | 精细化标注 | 通用 |
| **CDCP** | — | 英语议论文 |
| **Args.me** | 大规模 | 网络辩论 |
| **UKP** | — | 学术论证 |
| **US2016** | — | 政治辩论 |
| **LIARArg** | 2,832 | 假新闻检测 |

### 3.4 关键发现

- **Compact LMs 在论证分类上已足够**：基于 BERT 的模型在 Premise/Claim 分类上可达 85-90% 准确率，适合小模型部署
- **图结构信息提升关系分类**：全局论证图的结构（不仅仅是局部文本）能显著提升 Support/Attack 关系预测——这直接支持了我们"增量语义图谱"的设计思路
- **隐式论证（Enthymemes）是难点**：许多论证的前提或结论未在文本中显式表述，需要推理补全——这与我们的"对抗机打捞上下文"策略一致

---

## 4. 因果图模型与时序逻辑

### 4.1 因果图基本结构

因果图（Causal Graph）是一个有向无环图（DAG），其中：

- **节点** = 事件、实体、动作
- **有向边** = 因果关系（A → B 表示 A 导致 B）

```
         ┌──────┐
         │ 下雨 │
         └──┬───┘
            │ Cause
            ↓
    ┌───────┴────────┐
    │ 路面湿滑        │
    └───────┬────────┘
            │ Cause
            ↓
    ┌───────┴────────┐
    │ 车速减慢        │
    └───────┬────────┘
            │ Cause
            ↓
    ┌───────┴────────┐
    │ 到达时间延迟     │
    └────────────────┘
```

### 4.2 因果 vs 时序：核心区分

这是 NLP 中最容易混淆的问题之一：

| 关系 | 定义 | 示例 | 形式化 |
|------|------|------|--------|
| **时序依赖 (Temporal)** | A 在时间上先于 B | 我吃了饭，然后去散步 | `Before(A, B)` |
| **因果依赖 (Causal)** | A 的发生导致 B 的发生 | 因为下雨，所以路滑 | `Cause(A, B) ⇒ Before(A, B)` |

**关键规则**：因果蕴含时序（如果 A 导致 B，则 A 必然先于 B），但时序不蕴含因果（A 在 B 之前不代表 A 导致 B）。这是对抗机检测"虚假因果"的逻辑基础。

### 4.3 事件逻辑图（Event Logic Graph）

事件逻辑图是专门用于文本事件的因果/时序图：

```
节点：事件 (Subject, Predicate, Object) 三元组
边类型：
├── SEQUENCE (时序) — A 之后 B
├── CAUSE (因果) — A 导致 B
├── CONDITION (条件) — 如果 A 则 B
└── HIERARCHY (层级) — A 包含 B 子事件
```

**构建方法**：
- **监督方法**：BERT/BiLSTM + CRF 序列标注提取事件，分类边类型
- **无监督方法**：PMI（点间互信息）、规则模式匹配
- **LLM 方法**：多轮对话生成因果图（如 Chambers 2025 的协作多专家方法）

### 4.4 时序逻辑与推理

Allen 的区间代数（Interval Algebra）定义了 13 种时间关系，对文本时序推理至关重要：

| 关系 | 符号 | 直观含义 | 示例 |
|------|------|----------|------|
| Before | A < B | A 在 B 之前 | 吃饭 < 散步 |
| After | A > B | A 在 B 之后 | 散步 > 吃饭 |
| During | A ⊂ B | A 在 B 期间 | 讨论在会议期间 |
| Overlaps | A ⋈ B | A 与 B 重叠 | 聊天与吃饭重叠 |
| Meets | A m B | A 结束后 B 立即开始 | 演奏结束，掌声开始 |

---

## 5. 本项目映射分析  ★

### 5.1 Dung 框架到图谱边类型的映射

Dung 的 Attack 和 Support 关系直接对应于我们的语义图谱核心边类型：

```python
# 在 graph/models.py 中扩展 EdgeType 枚举
class EdgeType(Enum):
    # RST 来源
    CAUSE = "cause"           # 因果 (Cause/Result)
    ELABORATION = "elaboration" # 阐述
    BACKGROUND = "background"   # 背景
    SEQUENCE = "sequence"      # 时序
    PURPOSE = "purpose"        # 目的
    SUMMARY = "summary"        # 总结

    # 论证框架来源  ← 新增
    ATTACK = "attack"          # 反驳/矛盾 (Dung 框架核心)
    SUPPORT = "support"        # 支持/论证 (论证挖掘核心)

    # 其他
    CONDITION = "condition"    # 条件
    EVALUATION = "evaluation"  # 评价
    ATTRIBUTION = "attribution" # 归因
    CONTRAST = "contrast"      # 对比
```

**方向语义**：

```
ATTACK:   Node_A ──反驳──→ Node_B    (A 否定/反驳 B)
SUPPORT:  Node_A ──支持──→ Node_B    (A 为 B 提供支持)
CAUSE:    Node_A ──导致──→ Node_B    (A 导致 B)
SEQUENCE: Node_A ──之后──→ Node_B    (A 在 B 之前发生)
```

### 5.2 论证挖掘到 Chunk 标注的映射

```
Chunk JSON 扩展字段：
{
    "text": "因为时间不够，我们取消了会议。",
    "role": "nucleus",
    "intent": "assertive",
    "relation": "non_volitional_cause",
    "argument_role": "premise",       # ← 新增 (premise / claim / none)
    "argument_relation": "support",    # ← 新增 (support / attack / none)
    "argument_target": "取消会议"      # ← 新增 (论证指向的节点)
}
```

**在 Tagger Prompt 中的约束**：
```
如果当前句是为某个论断提供理由/证据 → argument_role = "premise"
如果当前句是做出一个论断/结论 → argument_role = "claim"
如果当前句反驳/否定前面的某个观点 → argument_relation = "attack"
如果当前句支持/补充前面的某个观点 → argument_relation = "support"
```

### 5.3 对抗机中的论证与因果检查

#### 5.3.1 基于 Dung 框架的矛盾检测

反方（Prosecutor）利用 Attack 关系检测矛盾：

```
# 反方扫描逻辑
for node in graph.active_nodes():
    # 检查 ATTACK 边是否存在被攻击但未辩护的节点
    attacked = graph.get_incoming_edges(node, EdgeType.ATTACK)
    defended = graph.get_outgoing_edges(node, EdgeType.SUPPORT)
    
    if len(attacked) > len(defended):
        # 被攻击多、辩护少的节点 → 可能是逻辑漏洞
        prosecutor.add_alert("逻辑矛盾", node,
            f"节点 '{node.text}' 被 {len(attacked)} 个论证攻击，"
            f"但只有 {len(defended)} 个辩护")
    
    # Grounded 语义检查：无攻击者且未被反驳 = 可靠节点
    if len(attacked) == 0 and node.role == "nucleus":
        node.confidence = min(1.0, node.confidence + 0.1)  # 增加置信度
```

#### 5.3.2 基于因果图的依赖检测

```
# 反方检测悬空 Action
for node in graph.get_nodes_by_intent("directive"):
    # 检查该 Action 是否有前置条件/原因
    has_cause = graph.has_incoming_edge(node.id, EdgeType.CAUSE)
    has_condition = graph.has_incoming_edge(node.id, EdgeType.CONDITION)
    has_background = graph.has_incoming_edge(node.id, EdgeType.BACKGROUND)
    
    if not (has_cause or has_condition or has_background):
        prosecutor.add_alert("悬空指令", node,
            f"指令 '{node.text}' 缺少原因的因果链或背景条件")

# 正方打捞策略
for alert in prosecutor.alerts:
    if alert.type == "悬空指令":
        context = defender.scavenge(
            target=alert.node,
            relation_types=[EdgeType.CAUSE, EdgeType.BACKGROUND],
            decay_pool=graph.get_decay_pool(),
            max_distance=3  # 最多回溯 3 个节点
        )
```

#### 5.3.3 时序 vs 因果的区分策略

```
# 在 Updater 建边时，区分 SEQUENCE 和 CAUSE
if detected_relation == "sequence":
    # 检查是否有明确因果信号词（导致/因为/所以...）
    if has_causal_signal(node_a, node_b):
        graph.add_edge(node_a, node_b, EdgeType.CAUSE)
        graph.add_edge(node_a, node_b, EdgeType.SEQUENCE)  # 时序是因果的子集
    else:
        graph.add_edge(node_a, node_b, EdgeType.SEQUENCE)
    
# 对抗机检测"虚假因果"
for edge in graph.get_edges(EdgeType.CAUSE):
    # 检查因果链中是否有时序违反（原因不早于结果）
    if not temporal_before(edge.source, edge.target):
        prosecutor.add_alert("时序异常", edge,
            f"因果关系的时序违反：{edge.source.text} 不早于 {edge.target.text}")
```

### 5.4 三种理论在项目中的融合

```
                         论证框架 (Dung)
                              │
                    ATTACK / SUPPORT 边类型
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
    Tagger 标注        图谱模型              对抗机
    argument_role      EdgeType.ATTACK     矛盾检测
    argument_relation  EdgeType.SUPPORT    辩护检查
    (论证挖掘)         EdgeType.CAUSE      悬空检测
                       EdgeType.SEQUENCE   因果验证
                              │
                              │
                    因果图 & 时序逻辑
                        (Causal Graph)
```

- **论证挖掘**负责在 Tagger 中标注"Premise/Claim"和"Support/Attack"
- **Dung 框架**为图谱的 ATTACK/SUPPORT 边提供形式化的可接受性语义
- **因果图**提供了 CAUSE/SEQUENCE 边类型的设计依据和区分策略
- **三者汇合于对抗机**——反方利用所有边类型进行矛盾检测、悬空检测、因果验证

---

## 6. 参考文献

1. Dung, P. M. (1995). On the acceptability of arguments and its fundamental role in nonmonotonic reasoning, logic programming and n-person games. *Artificial Intelligence*, 77(2), 321-357. — 奠基之作
2. Caminada, M. (2006). On the issue of reinstatement in argumentation. *JELIA 2006*. — Grounded 语义的标签化方法
3. Mann, W.C. & Thompson, S.A. (1988). *RST basis已在前篇笔记覆盖*
4. Lawrence, J. & Reed, C. (2020). Argument Mining: A Survey. *Computational Linguistics*, 45(4), 765-818. — 论证挖掘综述
5. FSP-ARC (2025). Prompt templates for argument relation classification using frame semantic parsing. *Springer*.
6. AASP (2025). End-to-End Argument Mining through Autoregressive Argumentative Structure Prediction. *IJCNN 2025*.
7. Cayrol, C. & Lagasquie-Schiex, M.-C. (2005). On the acceptability of arguments in bipolar argumentation frameworks. *ECSQARU 2005*. — BAF 支持关系
8. Chambers, N. et al. (2025). Causal Graph based Event Reasoning using Semantic Relation Experts. *ACL 2025*.
9. Sun, Cheng & Qu (2018). Reading Comprehension with Graph-based Temporal-Causal Reasoning. *COLING 2018*.
