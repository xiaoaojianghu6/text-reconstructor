# 信念修正与衰减算法学习笔记

## 1. 理论概述

本笔记涵盖三个相互关联的理论领域，它们共同为增量语义图谱的节点生命周期管理、Active Buffer 的激活/衰减策略、以及对抗机的置信度评估提供理论基础：

| 理论 | 核心关注 | 对本项目的价值 |
|------|----------|---------------|
| **AGM 信念修正** | 收到矛盾新信息时如何调整信念集 | 图谱节点置信度更新、矛盾消解策略 |
| **Ebbinghaus 遗忘曲线** | 记忆随时间衰减、通过重复唤醒的规律 | 对数衰减函数设计、节点唤醒机制 |
| **置信度动态评估** | 多来源信息的可信度聚合与评分 | 抗机策略：正反方辩论后的置信度加权 |

---

## 2. AGM 信念修正理论

### 2.1 基本框架

AGM 理论（Alchourron, Gardenfors, Makinson, 1985）是研究理性主体如何在接收到新信息时改变信念的基础框架。

**核心假设**：信念状态被表示为一个**信念集** K（逻辑封闭的语句集合），即 K 包含其所有逻辑后承。

**三个认知态度**：

| 态度 | 定义 |
|------|------|
| **接受 (Accepted)** | α ∈ K |
| **拒绝 (Rejected)** | ¬α ∈ K |
| **未定 (Undetermined)** | α ∉ K 且 ¬α ∉ K |

**两条指导原则**：
1. **新信息优先 (Primacy of New Information)**：新输入总是被接受
2. **信息经济原则 (Principle of Informational Economy)**：改变时尽可能保留原有信念集

### 2.2 三种基本操作

```
操作         符号       描述            一致性风险
──────────────────────────────────────────────────────
扩展 (Expansion)     K + α     直接添加新信念       可能不一致（含矛盾）
收缩 (Contraction)   K - α     移除某个信念         安全（但不新增）
修正 (Revision)      K * α     添加新信念并消解矛盾  一致（关键操作）
```

#### 2.2.1 扩展 (Expansion)

**定义**：`K + α = Cn(K ∪ {α})`

直接将 α 加入信念集。这是最简单、成本最低的操作。

**问题**：如果 α 与 K 中的现有信念矛盾，扩展会导致不一致。

**在项目中的对应**：图谱新增节点（默认操作，无矛盾时直接添加）。

#### 2.2.2 收缩 (Contraction)

**定义**：从信念集 K 中移除 α，不添加任何新信念。难点在于决定同时移除哪些其他信念——如果 α 被其他信念逻辑蕴含，则至少必须舍弃其中之一。

**Recovery 公设**（最有争议）：`K ⊆ (K - α) + α` ——收缩可通过重新添加 α 完全恢复。

**在项目中的对应**：当节点衰减到阈值以下时，从 Active Buffer 移除。

#### 2.2.3 修正 (Revision) — 核心操作

**定义**：`K * α = (K - ¬α) + α`

**Levi 恒等式**：修正 = 先收缩掉 ¬α，再扩展 α。

两步过程：
1. 先移除非 α（即去掉与 α 矛盾的信念）
2. 再添加 α

**在项目中的对应**：
- 当图谱收到与现有节点矛盾的新信息时，触发修正
- 反方检测到矛盾 → 正方辩护 → 若正方胜则保留原节点，若反方胜则收缩原节点 + 扩展新节点

### 2.3 信念等级化 (Epistemic Entrenchment)

AGM 的核心洞见：**并非所有信念都同等重要**。有些信念更难被放弃，即它们具有更高的**认识论牢固度 (Epistemic Entrenchment)**。

**定义**：α 比 β 更牢固（β < α），意味着如果被迫放弃一个，智能体更可能放弃 β 而不是 α。

**性质**：

| 性质 | 表述 | 含义 |
|------|------|------|
| 传递性 | α ≤ β 且 β ≤ γ ⇒ α ≤ γ | 牢固度是全序 |
| 支配性 | α ⊢ β ⇒ α ≤ β | 逻辑上更强的信念至少同样牢固 |
| 合取性 | α ≤ α∧β 或 β ≤ α∧β | 合取的牢固度等于较不牢固者 |
| 最小性 | ⊢ ¬α ⇒ α 最小 | 矛盾最容易被放弃 |
| 最大性 | ⊢ α ⇒ α 最大 | 重言式永不被放弃 |

**收缩与牢固度的关系**：收缩 α 时，移除 α 以及所有比 α 更不牢固的信念。

**在项目中的对应——多级衰减速率**：

```
节点类型   →  认识论牢固度  →  衰减速率   →  对应 AGM
────────────────────────────────────────────────────
Nucleus         高            慢          高牢固度信念
Satellite       中            中          中等牢固度
Directive(Action) 高          慢          高牢固度（待兑现）
Expressive      低            快          低牢固度（即时情感）
```

### 2.4 Grove 球面模型（语义对应）

Grove 的球面模型（Systems of Spheres）提供了 AGM 的语义解释：

- 以当前信念集 K 为中心，同心球层向外辐射
- 每个球层代表一个可能世界集合，离中心越远与当前信念差异越大
- 修正 α：取最小的与 α 一致的球层中的可能世界

**对图谱的启示**：语义距离计算——新节点入图时，计算与现有节点的距离，距离最近（最相似）的球层中的节点最先被关联。

---

## 3. 衰减算法与遗忘曲线

### 3.1 Ebbinghaus 遗忘曲线

Hermann Ebbinghaus (1885) 通过实验发现了人类记忆随时间的衰减规律：

**原始公式**：
```
b = 100k / ((log t)^c + k)
```
- b = 保留率（百分比）
- t = 时间（分钟）
- c = 1.25, k = 1.84（拟合常数）

**核心发现**：
1. 遗忘在**最初阶段最快**，随后逐渐放缓（对数衰减）
2. **间隔效应 (Spacing Effect)**：每次主动回忆都会延长下一次回忆的最优间隔
3. **节省 (Savings)**：即使无法有意识回忆，之前的接触仍然降低了重新学习的成本

### 3.2 对数衰减函数设计

借鉴 Ebbinghaus 曲线，结合项目特征（Token 计数而非时间），设计衰减函数：

```
f(age) = initial_weight / (1 + decay_rate * log(1 + age))

其中:
- age = 当前 Token 计数 - 节点创建时的 Token 计数
- initial_weight = 节点初始权重（基于 role/intent 决定）
- decay_rate = 衰减速率（基于角色类型决定）
```

**衰减曲线示例**：

| age (Token) | Nucleus (decay_rate=0.3) | Satellite (decay_rate=0.6) | Expressive (decay_rate=1.0) |
|-------------|--------------------------|----------------------------|------------------------------|
| 0 | 1.00 | 1.00 | 1.00 |
| 50 | 0.85 | 0.74 | 0.63 |
| 200 | 0.78 | 0.64 | 0.52 |
| 1000 | 0.70 | 0.54 | 0.42 |
| 5000 | 0.63 | 0.46 | 0.35 |

### 3.3 唤醒机制 (Reactivation)

当节点被当前处理的信息引用或关联时，触发唤醒：

```
def reactivate(node, current_token_pos):
    # 重置节点的衰减时钟
    node.last_active_token = current_token_pos
    # 恢复权重（可能部分恢复）
    node.current_weight = node.initial_weight * refresh_factor
    
    # refresh_factor < 1.0：多次唤醒后恢复比例递减
    # 避免"过度活跃"节点永久占据缓冲区
    refresh_factor = max(0.7, 1.0 - 0.05 * node.reactivation_count)
    node.reactivation_count += 1
```

**唤醒触发器**：
1. 新 Chunk 的 `dependency` 或 `scope` 字段引用该节点
2. 新 Chunk 的 `relation` 边指向该节点
3. 新 Chunk 的文本包含该节点核心实体的同义词/指代词
4. 正方在衰减池中成功打捞该节点

### 3.4 Active Buffer 的淘汰策略

```
          ┌──────────────────────────┐
          │      新 Chunk 入图        │
          └────────┬─────────────────┘
                   │
                   ▼
          ┌──────────────────────────┐
          │  更新所有 Active 节点的   │
          │  权重: weight = f(age)   │
          └────────┬─────────────────┘
                   │
                   ▼
          ┌──────────────────────────┐
          │  权重 < 淘汰阈值?         │
          │  (threshold = 0.4)       │
          └────────┬─────────────────┘
                   │
          ┌────────┴─────────┐
          ▼                  ▼
   ┌──────────────┐   ┌──────────────┐
   │ 移出 Active  │   │ 保留在 Active│
   │ 放入衰减池   │   │ 缓冲池中     │
   └──────────────┘   └──────────────┘
```

**衰减池 (Decay Pool)**：被淘汰的节点不删除，而是移入衰减池，放入词典供正方打捞。衰减池中的节点权重不再更新，但保留原始信息。

---

## 4. 置信度动态评估

### 4.1 置信度 vs 重要度

两个容易混淆的概念：

| 维度 | 置信度 (Confidence) | 重要度 (Importance) |
|------|--------------------|--------------------|
| **含义** | 节点信息的可靠程度 | 节点在当前上下文中的关联程度 |
| **变化因素** | 新证据支持 → 升高；矛盾 → 降低 | 被引用 → 升高；衰减 → 降低 |
| **范围** | [0, 1] | [0, initial_weight] |
| **谁使用** | 对抗机（决定是否推入 AlertBuffer） | Active Buffer（决定是否保留） |
| **示例** | "总统说..." 置信度低（需引证） | 讨论核心话题时重要度高 |

### 4.2 置信度聚合策略

当一个节点收到来自多个来源的信息（新 Chunk、正方辩护、反方质疑）时，需要聚合置信度：

```
def aggregate_confidence(node, new_evidence):
    """
    新证据对节点置信度的影响
    
    参数:
    - new_evidence: {source, type, relation_strength}
    
    策略:
    - SUPPORT 边 → 增加置信度
    - ATTACK 边 → 降低置信度
    - 正反方辩论后，正方胜 → 恢复至原置信度的 90%
    - 正反方辩论后，反方胜 → 降至原置信度的 50%
    """
    if new_evidence.type == "support":
        node.confidence = min(1.0, node.confidence + 0.1 * new_evidence.strength)
    elif new_evidence.type == "attack":
        node.confidence = max(0.0, node.confidence - 0.15 * new_evidence.strength)
    
    # 置信度低于阈值时，标记为"模糊概念"
    if node.confidence < 0.3:
        prosecutor.mark_vague(node)
```

### 4.3 对抗机的双阈值决策

对抗机使用**两个独立阈值**来管理置信度和重要度的联合决策：

```
                     重要度高         重要度低
                    ──────────      ──────────
置信度高     │  (绿色) 直接接受    (蓝色) 保留但低优
            │                     先级
置信度中     │  (黄色) 正方辩护     (灰色) 静态度量
            │  后决定
置信度低     │  (红色) 推入 Alert   (删除) 直接淘汰
            │  Buffer 提示人类
```

**硬性规则**：
- **最多 2 轮辩论**：对抗机正反方最多辩论 2 轮。2 轮后正方仍无法说服反方（置信度未回升到安全线），直接挂起并推入 AlertBuffer
- **置信度安全线**: `confidence >= 0.7`
- **重要度淘汰线**: `importance < 0.4`

---

## 5. 本项目映射分析  ★

### 5.1 AGM 三操作到图谱更新的映射

```
AGM 操作      项目对应                   触发条件
────────────────────────────────────────────────────────
扩展 (Expansion)   新增节点加入图谱              默认操作（无矛盾时）
修正 (Revision)    矛盾信息处理：基于置信度      反方检测到矛盾
                   决策保留/替换
收缩 (Contraction) 从 Active Buffer 移除        衰减后权重低于阈值
恢复 (Recovery)    从衰减池打捞（正方操作）      正方搜索历史上下文
```

### 5.2 对数衰减函数的具体设计

在 `graph/decay.py` 中实现：

```python
import math

class DecayEngine:
    def __init__(self, decay_rate: float = 0.3):
        self.decay_rate = decay_rate   # 基础衰减率
    
    def compute_weight(self, token_age: int, initial_weight: float,
                       role: str = "satellite") -> float:
        """
        计算当前权重:
        
        weight = initial_weight / (1 + decay_base * log(1 + token_age))
        
        其中 decay_base 由 role 决定:
        - nucleus:   0.3 (慢衰减)
        - satellite: 0.6 (中等衰减)
        - expressive: 1.0 (快速衰减)
        """
        decay_base = self._decay_base_for_role(role)
        return initial_weight / (1.0 + decay_base * math.log(1.0 + token_age))
    
    def _decay_base_for_role(self, role: str) -> float:
        return {
            "nucleus": 0.3,
            "satellite": 0.6,
            "expressive": 1.0,
            "action": 0.3,       # Directive 节点
            "commitment": 0.4,   # Commissive 节点
        }.get(role, 0.5)
    
    def reactivate(self, node, current_token_pos: int) -> None:
        """唤醒节点：重置其最后活跃位置，恢复部分初始权重"""
        age = current_token_pos - node.last_active_token
        node.last_active_token = current_token_pos
        # 权重恢复：基于初始权重的 80%（避免永久活跃）
        node.current_weight = min(
            node.initial_weight * 0.8,
            node.current_weight + node.initial_weight * 0.3
        )
        node.reactivation_count += 1
```

### 5.3 与 Active Buffer 的集成

在 `processor/buffer.py` 中：

```python
class ActiveBuffer:
    def __init__(self, max_size: int = 20, eviction_threshold: float = 0.4):
        self.nodes = []            # 活跃节点列表（按权重排序）
        self.decay_pool = {}       # 衰减池 {node_id: node}
        self.max_size = max_size
        self.eviction_threshold = eviction_threshold
        self.token_counter = 0
        self.decay_engine = DecayEngine()
    
    def add_node(self, node) -> None:
        """新增节点到缓冲区"""
        node.initial_weight = self._initial_weight(node)
        node.current_weight = node.initial_weight
        node.last_active_token = self.token_counter
        node.reactivation_count = 0
        self.nodes.append(node)
        self._trim()
    
    def tick(self, tokens: int = 1) -> None:
        """每处理一定数量 Token，更新所有节点权重"""
        self.token_counter += tokens
        for node in self.nodes[:]:  # 遍历副本
            age = self.token_counter - node.last_active_token
            node.current_weight = self.decay_engine.compute_weight(
                age, node.initial_weight, node.role
            )
            if node.current_weight < self.eviction_threshold:
                self._evict(node)
    
    def reference(self, node_id: str) -> None:
        """节点被引用时唤醒"""
        node = self._find(node_id)
        if node:
            self.decay_engine.reactivate(node, self.token_counter)
    
    def get_top_k(self, k: int = 3) -> list:
        """获取 Top-K 最活跃节点（用于 Tagger Prompt）"""
        sorted_nodes = sorted(self.nodes, 
                             key=lambda n: n.current_weight, reverse=True)
        return sorted_nodes[:k]
    
    def scavenge(self, query: str, relation_types: list = None) -> list:
        """正方从衰减池中打捞节点"""
        candidates = []
        for nid, node in self.decay_pool.items():
            score = self._semantic_similarity(query, node.text)
            candidates.append((score, node))
        candidates.sort(reverse=True)
        return [node for score, node in candidates[:5]]
    
    def _evict(self, node) -> None:
        """淘汰节点：移入衰减池"""
        self.nodes.remove(node)
        self.decay_pool[node.id] = node  # 保留在衰减池中供打捞
    
    def _initial_weight(self, node) -> float:
        """根据角色决定初始权重"""
        base = {
            "nucleus": 1.0,
            "satellite": 0.7,
            "action": 1.0,
            "expressive": 0.5,
        }.get(node.role, 0.7)
        # Intent 调整
        if node.intent == "directive":
            base *= 1.1  # 指令更高权重
        return min(1.0, base)
```

### 5.4 PL/pgSQL 中的置信度与对抗机集成

对抗机中置信度管理：

```python
class ConfidenceManager:
    def __init__(self, debate_rounds_limit: int = 2):
        self.debate_rounds_limit = debate_rounds_limit
        self.confidence_safety_line = 0.7
    
    def evaluate(self, node, graph, prosecutor, defender):
        """
        对抗机主流程：反复方→正方→评估→决定
        
        返回: (最终置信度, 是否推入 AlertBuffer)
        """
        for round in range(self.debate_rounds_limit):
            # 反方提出质疑
            attacks = prosecutor.scan(node, graph)
            if not attacks:
                # 无质疑 → 节点安全
                return (node.confidence, False)
            
            # 正方辩护
            for attack in attacks:
                defense = defender.respond(attack, graph)
                if defense:
                    # 正方成功辩护
                    node.confidence = min(1.0, node.confidence + 0.1)
                else:
                    # 正方辩护失败
                    node.confidence = max(0.0, node.confidence - 0.2)
            
            # 检查是否已达到安全线
            if node.confidence >= self.confidence_safety_line:
                return (node.confidence, False)
        
        # 两轮后仍未达到安全线 → 推入 AlertBuffer
        return (node.confidence, True)
```

### 5.5 五种理论的全局融合回顾

至此，Phase 1 的五种理论调研全部完成。它们在项目中的融合关系：

```
输入文本
    │
    ▼
┌────────────────────────────────────────────────────┐
│  动态滑动窗口处理器 (Phase 4)                       │
│  ├─ Chunker: 句级分割 + 滑动窗口                     │
│  ├─ Tagger:                                        │
│  │   ├─ 言语行为理论 → IntentType (assert/direct/…) │
│  │   ├─ RST → role (nucleus/satellite) + relation   │
│  │   └─ 论证挖掘 → argument_role (premise/claim)    │
│  └─ Buffer: 衰减算法 → Active Buffer 管理            │
└──────────────────────┬─────────────────────────────┘
                       │ Chunk JSON
                       ▼
┌────────────────────────────────────────────────────┐
│  增量语义图谱 (Phase 5)                             │
│  ├─ Graph: Node/Edge 数据结构                       │
│  │   ├─ RST 关系 → CAUSE/ELABORATION/SEQUENCE/…    │
│  │   └─ Dung 框架 → ATTACK/SUPPORT                  │
│  ├─ Decay: 对数衰减 + 唤醒机制                       │
│  │   └─ Ebbinghaus 遗忘曲线 → 衰减函数设计            │
│  └─ AGM 信念修正 → 矛盾信息处理策略                   │
└──────────────────────┬─────────────────────────────┘
                       │ 图谱 + AlertBuffer
                       ▼
┌────────────────────────────────────────────────────┐
│  对抗机 (Phase 6)                                  │
│  ├─ 反方: Dung 可接受性语义 + 因果图 + 置信度阈值    │
│  ├─ 正方: 衰减池打捞 (AGM Recovery)                 │
│  └─ 决策: 置信度聚合 + 2 轮限制                      │
└──────────────────────┬─────────────────────────────┘
                       │ 结构化纯文本 + 建议
                       ▼
┌────────────────────────────────────────────────────┐
│  输出模块 (Phase 7)                                 │
└────────────────────────────────────────────────────┘
```

---

## 6. 参考文献

1. Alchourron, C. E., Gardenfors, P., & Makinson, D. (1985). On the Logic of Theory Change: Partial Meet Contraction and Revision Functions. *Journal of Symbolic Logic*, 50(2), 510-530. — AGM 奠基之作
2. Gardenfors, P. (1988). *Knowledge in Flux: Modeling the Dynamics of Epistemic States*. MIT Press. — AGM 经典教材
3. Hansson, S. O. (1999). *A Textbook of Belief Dynamics*. Kluwer Academic Publishers. — 信念修正入门教材
4. Ebbinghaus, H. (1885/1913). *Memory: A Contribution to Experimental Psychology*. — 遗忘曲线原始研究
5. Grove, A. (1988). Two modellings for theory change. *Journal of Philosophical Logic*, 17(2), 157-170. — Grove 球面模型
6. Ferme, E. & Hansson, S. O. (2011). AGM 25 years: Twenty-five years of research in belief change. *Journal of Philosophical Logic*, 40(2), 295-331. — AGM 25 年综述
7. Darwiche, A. & Pearl, J. (1997). On the logic of iterated belief revision. *Artificial Intelligence*, 89(1-2), 1-29. — 迭代信念修正
