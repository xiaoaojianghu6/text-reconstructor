# RST 修辞结构理论学习笔记

## 1. 理论概述

修辞结构理论（Rhetorical Structure Theory, RST）由 William C. Mann、Sandra A. Thompson 和 Christian Matthiessen 于 1980 年代在南加州大学信息科学研究所提出。RST 为分析自然语言文本的连贯性与组织结构提供了一个功能主义框架。

**核心命题**：连贯文本中的每一部分都有其存在的合理理由——每个单元都承担特定的功能角色，共同服务于作者的总体意图。

RST 的核心输出是一棵**层级化的修辞结构树**，覆盖整个文本。

---

## 2. 核心概念

### 2.1 Text Span（文本跨度）

文本被递归分割为**跨度（Span）**。最小分析单位称为 **EDU（Elementary Discourse Unit，基本话语单元）**，通常对应一个子句或一个命题。相邻的 EDU 通过修辞关系组合成更大的跨度，直到覆盖整篇文本。

EDU 的分割原则：
- 一般以子句（clause）为边界
- 关系从句、状语从句通常独立成 EDU
- 主语从句、宾语从句一般保留在母句内

### 2.2 Nucleus（核心）与 Satellite（辅助）

这是 RST 最基础的概念。当两个文本跨度通过修辞关系连接时：

| 角色 | 定义 | 删除测试 |
|------|------|----------|
| **Nucleus (N)** | 更核心、更重要的跨度——作者的主要传达点 | 删除后文本失去核心信息 |
| **Satellite (S)** | 支持性、次要的跨度——提供额外信息/上下文/证据 | 删除后文本仍然连贯（但信息量减少） |

大多数 RST 关系是**不对称的**（一个核心 + 一个辅助），反映了文本单元重要性不均等的经验观察。

### 2.3 关系类型的两条分类轴

**轴一：单核 vs 多核**

| 类型 | 描述 | 示例关系 |
|------|------|----------|
| **单核（Nucleus-Satellite）** | 一个核心 + 一个辅助，不对称 | Evidence, Elaboration, Cause, Condition |
| **多核（Multinuclear）** | 所有跨度同等重要，对称 | Contrast, List, Sequence, Joint |

**轴二：主题性 vs 呈现性**

| 类型 | 效果 | 示例关系 |
|------|------|----------|
| **主题性（Subject Matter）** | 读者识别出文本间的真实世界关系（语义层面）| Cause, Elaboration, Condition |
| **呈现性（Presentational）** | 增加读者的某种倾向（信念/欲望/接受度），语用层面 | Evidence, Concession, Motivation |

### 2.4 Schema（模式）

Schema 定义了多个 Span 如何组合成更大的 Span。常见模式包括：
- **N-S 模式**：一个核心 + 一个辅助
- **N-S-S 模式**：一个核心 + 多个辅助
- **多核模式**：多个同等重要的核心并列

---

## 3. 修辞关系完全分类

以下为 Mann & Thompson (1988) 定义的经典 RST 关系集（约 25-30 种）。

### 3.1 呈现性关系（Presentational Relations, 单核）

这些关系的目的是影响读者的态度或行为。

| 关系 | 核心 (N) | 辅助 (S) | 作者的意图 |
|------|----------|----------|------------|
| **Antithesis（对比论证）** | 作者赞同的观点 | 作者不赞同的观点 | 增加读者对 N 的正面评价 |
| **Background（背景）** | 需要被理解的内容 | 帮助理解的内容 | 提高读者理解 N 的能力 |
| **Concession（让步）** | 作者肯定的情况 | 表面矛盾但也被肯定的情况 | 增加读者对 N 的正面评价 |
| **Enablement（促能）** | 一个行动 | 帮助读者执行该行动的信息 | 提高读者执行 N 的能力 |
| **Evidence（证据）** | 一个论断 | 支持该论断的信息 | 增加读者对 N 的相信程度 |
| **Justify（正当化）** | 文本内容 | 支持作者表达 N 的正当性的信息 | 增加读者对作者表达权的接受 |
| **Motivation（动机）** | 一个行动 | 激发读者行动意愿的信息 | 增加读者执行 N 的欲望 |
| **Preparation（预备）** | 要呈现的文本 | 为 N 做准备的文本 | 让读者对 N 更感兴趣/有准备 |
| **Restatement（重述）** | 一个情况 | N 的另一种表达 | 读者识别 S 为 N 的重述 |
| **Summary（总结）** | 多个单元的文本 | N 的较短重述 | 读者识别 S 为 N 的简短总结 |

### 3.2 主题性关系（Subject Matter Relations, 单核）

这些关系描述文本之间在真实世界的语义联系。

| 关系 | 核心 (N) | 辅助 (S) | 意图 |
|------|----------|----------|------|
| **Circumstance（环境）** | 待解释的事件/观点 | 解释性上下文（时间/地点） | 读者在 S 框架中理解 N |
| **Condition（条件）** | 依赖于 S 的情况 | 假设/未实现的条件 | 读者识别 N 对 S 的依赖 |
| **Elaboration（阐述）** | 基本信息 | 额外细节 | 读者识别 S 为 N 的附加细节 |
| **Evaluation（评价）** | 一个情况 | 对 N 的评价性评论 | 读者识别 S 评估 N |
| **Interpretation（解读）** | 一个情况 | 将 N 与其他观点关联的解读 | 读者识别 S 将 N 关联到其他框架 |
| **Means（方式）** | 一个活动 | 实现 N 的方法/工具 | 读者识别 S 使 N 更可能实现 |
| **Non-volitional Cause（非意志因果）** | 一个情况（非意志） | 导致 N 的另一个情况（无意） | 读者识别 S 是 N 的原因 |
| **Non-volitional Result（非意志结果）** | 一个情况 | 由 N 导致的另一个情况（无意） | 读者识别 N 可能导致了 S |
| **Volitional Cause（意志因果）** | 一个意志行动 | 该行动的原因（有意图） | 读者识别 S 是 N 中行动的原因 |
| **Volitional Result（意志结果）** | 一个情况 | 由 N 中的意志行动导致的情况 | 读者识别 N 可能导致了 S |
| **Purpose（目的）** | 一个意图中的情况 | N 背后的意图 | 读者识别 N 是为了实现 S |
| **Solutionhood（解决方案）** | 一个解决方案 | 一个问题/需求 | 读者识别 N 是 S 中问题的解决方案 |
| **Otherwise（否则/反条件）** | 被 S 阻止的情况 | 未实现的情况 | 读者识别 N 的实现阻止了 S |
| **Unconditional（无条件）** | N 不依赖 S | 可能影响 N 的情况 | 读者识别 N 不依赖 S |
| **Unless（除非）** | 当 S 不成立时 N 实现 | 影响 N 的情况 | 读者识别 S 不成立时 N 实现 |

### 3.3 多核关系（Multinuclear, 对称）

| 关系 | 描述 |
|------|------|
| **Contrast（对比）** | 两个核心在很多方面可比，但在某些方面不同 |
| **Conjunction（并列）** | 项目以可比角色被连接在一起 |
| **Disjunction（析取）** | 项目提供相互替代的选择 |
| **Joint（联合）** | 没有特定约束的协调关系 |
| **List（列举）** | 可比项目被列举在一起 |
| **Multinuclear Restatement（多核重述）** | 一个项目主要是另一个的重述 |
| **Sequence（序列）** | 情况之间的连续关系 |

### 3.4 eRST 扩展关系

增强版 RST（eRST）在经典关系基础上增加/细化了以下内容：

| 扩展关系 | 类型 | 描述 |
|----------|------|------|
| **Attribution（归因）** | 主题性单核 | S 是（或不是）N 中信息的来源（如"张三说"） |
| **Elaboration-additional（附加阐述）** | 主题性单核 | S 提供关于 N 的额外信息 |
| **Elaboration-attribute（属性阐述）** | 主题性单核 | S 提供 N 中某短语的属性信息 |
| **Manner（方式）** | 主题性单核 | S 描述了 N 发生的方式 |
| **Purpose-attribute（目的属性）** | 主题性单核 | S 是 N 中某短语的目的 |
| **Organization-heading（标题组织）** | 呈现性 | S 作为标题为 N 做准备 |

eRST 的两大改进：

1. **次级边（Secondary Edges）**：在原始树结构基础上叠加非邻接关系边，允许跨越远距离的修辞连接
2. **信号标注（Signals）**：明确标注哪些词汇/结构触发了修辞关系，包括话语标记词（因为/但是/因此）、词汇信号（同义词链）、图表信号（冒号/破折号）、语法信号（时态序列）等

---

## 4. 层级结构与树表示

RST 分析的过程是从小到大递归构建树：

```
                   Elaboration
                  /           \
             Nucleus         Satellite
                |               |
      [基本信息: 我们没怎么徒步]  [额外细节: 因为云量不多]
```

**表示惯例**：
- 水平线连接**多核关系**中的核心
- 曲线箭头从**辅助**指向**核心**（单核关系）
- 关系名称标注在连接线上

**分析步骤**：
1. **分割**：将文本切分为 EDU
2. **识别关系**：连接相邻 EDU，确定修辞关系，分配核心/辅助角色
3. **递归构建**：将连接后的跨度持续组合，直到覆盖整篇文本
4. **验证**：用"删除测试"检验每个核心-辅助对

**关键原则**：
- **邻接性**：相关跨度几乎总是相邻的（但 eRST 通过次级边允许例外）
- **穷尽性**：连贯文本中的每个单元应有一个修辞角色
- **允许多解**：同一文本可能有多个有效分析（歧义被认可）
- **语言独立性**：关系通过功能和语义判断，而非形态/句法信号——使 RST 跨语言适用

---

## 5. NLP 应用现状

### 5.1 RST 解析器

| 解析器 | 类型 | 特点 |
|--------|------|------|
| **SPADE** | 句级解析 | 经典的句子级 RST 解析器 |
| **HILDA** | 文档级解析 | 高准确率文档级解析 |
| **DMRST** | 神经解析器 | 基于 Transformer，当前 SOTA |
| **LLM 方法** (Maekawa 2024) | 基于 Llama 2 + QLoRA | 将 top-down/bottom-up 解析策略转化为 prompt，获得 SOTA 结果 |

### 5.2 主要语料库

| 语料库 | 语言 | 说明 |
|--------|------|------|
| **RST-DT** | 英语 | RST 语篇树库，约 78 种细粒度关系 |
| **GUM / eRST** | 英语 | 多体裁，约 30+ 关系，含信号标注 |
| **Potsdam Commentary Corpus** | 德语 | 新闻评论语料库 |
| **Russian RST Treebank** | 俄语 | 俄语 RST 树库 |

### 5.3 主要应用方向

| 应用 | 原理 |
|------|------|
| **文本摘要** | 核心提取：约 70% 的摘要句子来自核心（Nucleus）；利用核心理念筛选重要内容 |
| **情感分析** | 区分核心/辅助的极性权重，改善情感分类 |
| **可控文本生成** | 使用 RST parser 在解码时重新排序 token 概率，强制维持特定修辞关系 |
| **文本结构规划** | 在生成多句文本时显式规划修辞结构序列，提高连贯性 |

### 5.4 RST + LLM 的最新发现

- **LLM 做 RST 解析可行**：通过 prompt 策略 + QLoRA 微调，Llama 2 70B 在 RST 解析上达到 SOTA
- **但 LLM 天然不擅长层级结构**：ChatGPT 倾向于将 RST 树解析为线性而非层级结构，CoT 提示改进有限
- **RST 作为 Prompt 设计框架**：修辞情境理论（exigence/audience/purpose/context）可以为 prompt 设计提供结构化方法
- **EDU 作为自然分块边界**：RST 的 EDU 是语义上有意义的自然分块单元

---

## 6. 本项目映射分析  ★

### 6.1 RST 到 Chunk 标签的映射

在我们的动态滑动窗口处理器中，每个 Chunk 需要携带结构化标签。RST 提供了以下直接映射：

```
Chunk JSON Schema  ←  RST 概念
─────────────────────────────────────
chunk.role         ←  Nucleus | Satellite
chunk.rst_relation ←  修辞关系 (Cause/Evidence/Elaboration/etc.)
chunk.scope        ←  修辞关系作用域 (局部/全局)
chunk.depth        ←  树深度 (层级位置)
chunk.signal_words ←  话语标记词 (因为/但是/所以/etc.)
```

**具体设计建议**：

| 字段 | RST 来源 | 说明 |
|------|----------|------|
| `role: "nucleus" / "satellite" / "multinuclear"` | 核心/辅助区分 | 最重要的标签，决定信息权重 |
| `relation: "Cause" / "Evidence" / "Elaboration" / ...` | 修辞关系 | 决定后续图谱边类型 |
| `relation_type: "subject_matter" / "presentational"` | 关系轴分类 | 用于区分语义关系 vs 语用意图 |
| `span_level: int` | 树深度 | 深度越浅越重要，用于衰减算法 |
| `nucleus_text: str (可选)` | 对应的核心文本 | 辅助指向核心的引用，用于图谱建边 |

### 6.2 修辞关系到图谱边类型的映射

RST 的修辞关系直接对应于语义图谱的**边类型**：

| RST 关系 | 图谱边类型 | 方向 |
|----------|------------|------|
| Cause (因果) | `CAUSE` / `RESULT` | 辅助→核心 或 核心→辅助 |
| Evidence (证据) | `SUPPORT` | 辅助→核心 |
| Elaboration (阐述) | `ELABORATION` | 辅助→核心 |
| Background (背景) | `BACKGROUND` | 辅助→核心 |
| Concession (让步) | `CONCESSION` | 双向（对比关系） |
| Condition (条件) | `CONDITION` | 辅助→核心（条件依赖） |
| Sequence (序列) | `SEQUENCE` | 多核之间（时序） |
| Contrast (对比) | `CONTRAST` | 多核之间（对称） |
| Purpose (目的) | `PURPOSE` | 核心→辅助 |
| Summary (总结) | `SUMMARY` | 辅助→核心 |
| Solutionhood (解决方案) | `SOLUTION` | 核心→辅助 |
| Evaluation (评价) | `EVALUATION` | 辅助→核心 |

**对对抗机的意义**：正反方可以利用这些边类型做各种检查：
- 反方：检测 Action 节点是否缺少必要的原因（Missing Cause parent）或必要条件（Missing Condition）
- 反方：检测 Evidence 节点是否孤立（有 Claim 但无 Evidence）
- 正方：在衰减池中根据关系类型打捞关联节点

### 6.3 边界情况与注意事项

1. **EDU 分割粒度**：中文的 EDU 分割比英文更复杂（缺乏明显的从句标记）。我们的 Chunker 可能需要基于标点+话语标记词做启发式分割，而非严格的语法从句分割。

2. **多核关系的处理**：Sequence/Contrast/List 等关系中，所有跨度都是同等重要的核心。这意味着我们的图谱必须支持**无方向边**（对称关系），而不仅仅是单向的 Nucleus→Satellite。

3. **eRST 次级边**：原始 RST 树要求邻接关系，但我们的系统通过图谱拓扑天然支持非邻接连接。我们不需要 eRST 的"次级边"概念——图谱本身就是解决这个问题的方案。

4. **小模型的局限性**：当前 LLM（包括 ChatGPT）在 RST 层级结构解析上表现不佳。对于我们的 Qwen 3.5 系列小模型，**不应期望它做完整的 RST 树解析**，而应：
   - **简化版**：只要求模型标注当前句的 `role`（核心/辅助）和 `relation`（主要修辞关系）
   - **不要求完整树结构**：树的构建由我们的图谱模块逐步完成（通过 Activate Buffer 和新节点入图时的语义距离计算）
   - **利用话语标记词**：在 Prompt 中明确提示模型注意"因为/但是/所以/然而/例如/总之"等信号词

5. **跨语言适配**：RST 是语言独立的，但中文的话语标记习惯不同于英文。需要在后续测试中收集中文特有的修辞信号词。

### 6.4 对架构的具体建议

```
动态滑动窗口处理器 (Phase 4) 应参考 RST 的设计：

1. Chunker 输出 = [EDU, EDU, ...]  (基于标点 + 话语标记词分割)
2. Tagger 输出 = Chunk{role, relation, text}  (小模型标注)
3. Buffer 输出 = 当前活跃节点摘要 (Top 3, 含 role 和 relation)
4. Graph 建边 = 根据 relation 类型创建有向/无向边

增量语义图谱 (Phase 5) 的边类型枚举：

enum EdgeType {
    CAUSE, RESULT,           // 因果类 (Cause/Result)
    SUPPORT,                 // 支持类 (Evidence)
    ELABORATION,             // 阐述类 (Elaboration)
    BACKGROUND,              // 背景类 (Background)
    CONDITION,               // 条件类 (Condition)
    SEQUENCE,                // 时序类 (Sequence)
    CONTRAST,                // 对比类 (Contrast/Concession)
    PURPOSE,                 // 目的类 (Purpose)
    SUMMARY,                 // 总结类 (Summary)
    SOLUTION,                // 解决方案 (Solutionhood)
    EVALUATION,              // 评价类 (Evaluation)
    ATTRIBUTION,             // 归因类 (Attribution)
}
```

核心/Nucleus 角色应获得更高的**初始权重**，在衰减算法中衰减更慢。辅助/Satellite 角色的权重初始较低且衰减更快。

---

## 7. 参考文献与资源

1. Mann, W.C. & Thompson, S.A. (1988). Rhetorical Structure Theory: Toward a functional theory of text organization. *Text*, 8(3), 243-281. — 经典论文
2. Taboada, M. & Mann, W.C. (2006). Rhetorical Structure Theory: Looking Back and Moving Ahead. *Discourse Studies*, 8(3), 423-459. — 综述
3. Zeldes, A. et al. (2025). eRST: A Signaled Graph Theory of Discourse Relations and Organization. *Computational Linguistics*, 51(1), 23-72. — eRST 扩展
4. Maekawa et al. (2024). Can we obtain significant success in RST discourse parsing by using Large Language Models? *EACL 2024*. — LLM + RST 解析
5. SFU RST 官方网站: https://www.sfu.ca/rst/ — 权威经典 RST 资源
6. eRST / GUM 语料库: https://gucorpling.org/erst/ — 增强版 RST
7. RST Discourse Treebank (RST-DT): 英语新闻语篇树库
