# text-reconstructor

基于语言学理论的文本逻辑结构化引擎：将结构混乱、逻辑不清的长段文本全自动转化为保留全部细节的结构化文本，同时主动发现矛盾、遗漏与模糊概念，并以非强制方式向作者提问。

## 解决什么问题

长段表述普遍存在四类问题：结构混乱、逻辑顺序不清晰、宕开一笔后遗漏要点、随口提及的重要内容被忽视。现有工具均不能同时处理这些问题：

| 维度 | Obsidian/Heptabase | Argdown | Copilot/Notion AI | 直接 LLM | 本项目 |
|------|-------------------|---------|-------------------|---------|--------|
| 输入 | 手动组织 | 手动转写 | 生成内容 | 自动 | 自动 |
| 理论支撑 | 无 | 论证理论 | 无 | 无 | RST+言语行为+Dung+遗忘曲线+AGM |
| 全量保留 | N/A | N/A | 倾向概括 | 倾向概括 | 硬约束+FCR客观验证 |
| 矛盾检测 | 无 | 手动 | 无 | 偶然 | 四组件系统化 |
| 交互提问 | 无 | 无 | 主动建议 | 无 | 非强制+阈值过滤 |
| 增量状态 | 无 | 无 | 无 | 无 | ActiveBuffer+图谱持久化 |
| 跨文件 | 部分 | 无 | 无 | 无 | 增量图谱+跨文件冲突检测 |

## 理论基础

每项核心机制均有明确的语言学/逻辑学理论支撑，不做教条应用：

| 理论 | 来源 | 实现 |
|------|------|------|
| 修辞结构理论 (RST) | Mann & Thompson 1988 | Tagger 输出 role/relation，映射 19 种 EdgeType 有向边 |
| 言语行为理论 | Searle 1969 | intent 五分类，对抗机按意图差异化搜索证据 |
| Dung 论证框架 | Dung 1995 | SUPPORT/ATTACK 边 + 攻防辩论语义 |
| 艾宾浩斯遗忘曲线 | Ebbinghaus 1885 | 图谱节点按 `exp(-t/S)` 衰减，ActiveBuffer 维护 Top-3 活跃节点，后续引用可"打捞" |
| AGM 信念修正 | Alchourron et al. 1985 | Prosecutor 起诉/Defender 辩护模拟修正请求与抵抗，最小变更原则 |
| 因果图 + Allen 时序逻辑 | Allen 1983 | CAUSE/RESULT 与 SEQUENCE 边 |

## 管线架构

```
输入 -> SentenceSplitter -> Tagger(流式Mini-Batch+ActiveBuffer)
     -> GraphUpdater(增量图谱+四组件对抗)
     -> VPGA Refiner(全局重写) -> FCR验证 -> 输出
```

- **Tagger**：每 8 句一批发送 LLM，每句输出 10 个语言学字段（scope/role/relation/intent/argument_role/thread_id 等），Prompt 注入活跃节点摘要实现跨距离上下文感知
- **增量语义图谱**：7 条纯 Python 建边规则（零 LLM），支持代词图谱回溯消解、多线叙事（THREAD_BRIDGE/REVEAL）、跨文件累积语义状态
- **对抗验证系统**：四组件并行——规则扫描+攻防辩论、SemanticRouter 双轨混合审计（拓扑粗筛 + LLM 精审，代价 O(N^2) 降至 O(5)）、实体对冲扫描（零 LLM）、跨文件冲突检测
- **VPGA 全局重写**：原文 + 14 条约束规则一次性重写，保留全部细节；支持 writer（保留文风）/ developer（精简）双模式
- **FCR 事实覆盖率**：提取 URL/数值/比喻标记/引号术语四类锚定实体做精确字符串匹配，客观量化细节保留度，不依赖 LLM 主观评分

## 安装

要求 Python >= 3.10。

```bash
pip install -e .
```

依赖 LLM 后端（三选一）：NVIDIA NIM、DeepSeek 官网 API、本地 Ollama。

## 使用

### CLI

```bash
# VPGA 全局重写（默认模式）
export NVIDIA_NIM_API_KEY=your_key
text-reconstructor --file input.md

# 可选参数
text-reconstructor --file input.md \
  --mode vpga          # vpga(默认,全局重写) / auto(旧管线)
  --backend deepseek   # nvidia(默认) / deepseek / ollama
  --no-streaming       # 禁用流式标注
```

### 本地 API 服务

```bash
python scripts/api_entry.py
```

FastAPI 服务，提供 `/api/process`（快速 VPGA 输出）与 `/api/audit`（异步管线审查）两个端点。

### 桌面应用（Tauri 2）

```bash
bash scripts/dev.sh      # 开发模式：前端热更新 + Python 后端
bash scripts/rebuild.sh  # 完整打包：PyInstaller + npm build + tauri build
```

React 19 前端 + PyInstaller 捆绑 Python 后端的 .app 桌面应用。

## 测试

```bash
python -m pytest -q
```

## 文档

- [文本重构项目项目说明.md](文本重构项目项目说明.md) -- 完整设计说明（理论映射、管线细节、对抗系统）
- [docs/](docs/) -- 架构文档与理论分析
- [idea.md](idea.md) -- 项目核心意图

## License

[MIT](LICENSE)
