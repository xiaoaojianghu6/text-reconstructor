# Argdown 参考分析笔记

> 分析日期: 2026-06-03
> 来源: https://github.com/christianvoigt/argdown (commit 拉取当日版)

## 1. 项目概况

Argdown 是一个基于纯文本的论证图定义语言，类似于 Markdown 但面向逻辑论证。用户用简单语法定义"论点(Statement)"和"论证(Argument)"之间的支持/反驳关系，系统自动生成可视化论证图。

**技术栈**: TypeScript + Chevrotain (JS 解析器工具库) + D3.js (图可视化)
**架构**: Lerna monorepo，14 个 packages

---

## 2. 语法设计 (最有价值的部分)

### 2.1 基本语法元素

```argdown
# 这是一个标题（用于分组）

[Statement 标题]: 论点内容.
    + <Argument 标题>: 论证内容支持此论点
    - <Another Argument>: 另一论证反驳此论点
```

### 2.2 关系符号

| 符号 | 含义 | 示例 |
|------|------|------|
| `+` | 支持 (Support) | `+ <Arg>` 缩进表示 Arg 在支持上层 |
| `-` | 攻击/反驳 (Attack) | `- <Arg>` 缩进表示 Arg 在反驳上层 |
| `<_` | Undercut (拆解前提) | `<` 表示攻击推理前提而非结论 |
| `->` | 结论出边 | `-> [Statement]` 从推理结论引出关系 |

### 2.3 缩进规则 (关键设计)

缩进定义 **关系层级**，这是 Argdown 最优雅的设计：

```
[中央论点]
    + <支持论证>        ← 缩进 4 格，表示支持中央论点
        - <反驳者>      ← 再缩进 4 格，表示反驳前一论证
            + <再支持>  ← 再缩进，支持反驳者
```

缩进自动推导出 ATTACK/SUPPORT 关系——用户不需要显式声明关系类型。

### 2.4 推理重构

```argdown
<Argument 1>

(1) 前提一
(2) 前提二
--
推理规则 (Modus Ponens)
--
(3) 结论
  -> [相关论点]     ← 结论的出边被视为整个 Argument 的出边
```

双横线 `--` 分隔前提和结论。推理规则行用于显式声明逻辑规则。

### 2.5 标签与元数据

```argdown
#tag            ← 标签（用于着色/过滤）
// 行注释       ← 注释
/* 块注释 */    ← 块注释
===
title: ...
author: ...
===
                ← YAML 前置元数据
```

---

## 3. 解析器实现

### 3.1 Lexer

- 使用 **Chevrotain** (JS 解析器工具库，类似 ANTLR)
- 词法分析器定义 token 类型：`Newline`, `Emptyline`, `Indent`, `Dedent`, `StatementTitle`, `ArgumentTitle` 等
- 缩进处理：维护 `indentStack`，类似 Python 的缩进管理

```typescript
// argdown-core/src/lexer.ts
let indentStack: number[] = [0];  // 缩进栈
// Detach token：识别缩进变化
// INDENT / DEDENT token 的产生逻辑类似 Python 词法
```

### 3.2 Parser

- 继承 `chevrotain.EmbeddedActionsParser`
- 使用 `EmbeddedActionsParser` 模式：在解析规则中直接构建 AST
- 规则递归：
  `argdown → sections → heading | statement | pcs | argument`
- 错误恢复：启用 `recoveryEnabled: true`，解析容错

### 3.3 Tree Walker

- `ArgdownTreeWalker` 类遍历 AST
- 在 walker 中触发插件的处理函数
- 支持 `IRuleNodeHandler` 和 `ITokenNodeHandler` 两种回调

---

## 4. 插件架构

Argdown 的处理流程由插件链构成：

```typescript
// ArgdownApplication.ts
application.addPlugin(new ParserPlugin());     // 1. 解析 → AST
application.addPlugin(new ModelPlugin());       // 2. 构建数据模型
application.addPlugin(new ColorPlugin());       // 3. 着色
application.addPlugin(new GroupPlugin());       // 4. 分组
application.addPlugin(new ArgumentSelectionPlugin()); // 5. 筛选
application.addPlugin(new MapPlugin());         // 6. 生成可视化图
application.addPlugin(new DotExportPlugin());   // 7. 导出 Graphviz
```

每个插件实现 `IArgdownPlugin` 接口，在 `run()` 中读写 `IArgdownRequest` / `IArgdownResponse`。

---

## 5. 关系推导逻辑

关键函数 `deriveImplicitRelations.ts` 负责从语法缩进推导 ATTACK/SUPPORT：

```typescript
// 遍历所有参数，检查它们的父子关系
// parent-child 关系来源于缩进层级对应的 AST 树
// 如果 A 出现在 B 的子树中且用 +，则 A SUPPORT B
// 如果 A 出现在 B 的子树中且用 -，则 A ATTACK B
```

这种设计使 **用户只需关注缩进层级，系统自动推导关系类型**。

---

## 6. 我们的可借鉴点

### 6.1 输出 1 (结构化文本) 的语法设计

Argdown 的缩进-关系映射可以直接用于我们的结构化文本输出：

```text
[中央论点] 我们应该采用方案A
    + [支持论据] 方案A成本最低
        - [反驳] 但方案A质量不稳定
            + [再支持] 我们有质检流程保障
    + [支持论据] 方案A实现最快
    - [反驳] 方案A不符合长期规划
```

**优势**：人类可直接阅读，缩进直观表达层级和正反关系。

### 6.2 与我们的 ATTACK/SUPPORT 边类型对照

Argdown 的 `+` `-` 直接对应于我们 EdgeType.ATTACK / EdgeType.SUPPORT。语法设计的一致性验证了我们的理论映射正确。

### 6.3 插件架构参考

虽然我们不直接用 JS 插件架构，但分层处理的思想（解析→模型构建→验证→输出）可以用于我们的 Processor→Graph→Adversary→Output 管线设计。

### 6.4 缩进即关系的核心思想

**对我们最重要的一点**：在输出 1 中，用缩进代替显式关系声明，用户不需要学习任何额外语法就能理解文本中的逻辑结构。

### 6.5 不借鉴的部分

- Argdown 的推理重构（前提-推理规则-结论）过于学术化，不适合我们面向普通用户的场景
- Chevrotain 解析器（JS 生态）不适合 Python 项目，我们会用 Python 原生方式（plur 或手写递归下降）

---

## 7. 与我们的关系类型对比

| Argdown | 本项目 |
|---------|--------|
| SUPPORT (+) | EdgeType.SUPPORT |
| ATTACK (-) | EdgeType.ATTACK |
| UNDERCUT (<_) | EdgeType.ATTACK (不细分) |
| ENTAILS | 无直接对应 |
| 缩进层级 + 关系符号 | 通过 Tagger 标注的 relation 字段入图 |

---

## 8. 总结

Argdown 最有价值的设计是 **"缩进即关系"**——通过纯文本缩进来表达逻辑层级和正反关系，这个思路可以直接用于我们的输出 1（结构化纯文本）。其插件架构的"管线化"处理思想也与我们的模块接口契约设计一致。

Argdown 更偏向学术逻辑学的严谨论证（前提-推理规则-结论），而本项目的核心差异在于：我们通过 AI 标注自动完成关系识别，用户不需要自己写语法。
