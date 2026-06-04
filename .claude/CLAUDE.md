# 文本重构项目 - 施工指令

## 开工前必读
每次施工前 MUST READ 以下文件：
1. `idea.md` - 项目核心意图
2. `开发流程说明.md` - 开发流程规范
3. `.claude/plans/idea-mutable-hennessy.md` - 主施工规划（查看当前进度和下一组块）
4. `docs/system-layout-manual.md` - 系统详细布局手册（审核参考）

## 施工规范
- **Plan Mode 阻断**: 每个施工组块前必须进入 plan mode，等你批准后方可施工
- **单组块聚焦**: 一次只做一个组块，完成后记录进度，再进入下一个
- **测试先行**: 每个模块实现必须伴随单元测试
- **废弃代码即时删除**: 实验失败/更换方案后立即清理
- **模块化**: 各组块通过明确的接口契约通信，不直接耦合

## Python 项目
- 主包位于 `src/text_reconstructor/`
- CLI 入口: `text_reconstructor.cli:cli` (click group)
- 测试目录: `tests/`
- 虚拟环境: 优先使用 `deep_learning_env` (conda)，含 ML/NLP 库

## 施工阶段速查
- Phase 0-12: 初始开发全部完成 (详见git历史)
- Phase 13: 全面整改 (2026-06-04) ✅
  - RST过度修正修复: relation=none不再强制降级satellite
  - Scope推理: 质量检查触发替代数量检查, 回退长度8字+代词过滤
  - 代词消解: 不再污染scope字段, 图谱回溯隐式绑定
  - 对抗机过滤: 只输出DANGLING_DIRECTIVE和LOGIC_CONFLICT高危alert
  - 前缀去噪: prefix_pruner.py移除序数词脚手架
  - FCR事实覆盖率: detail_anchor.py + fcr.py客观验证
  - LLMRefiner增强: 边关系描述传入Prompt, temperature降至0.15
  - ActiveBuffer接入: GraphUpdater中更新和提供active_summary
  - Mini-Batch流式标注: batch_tag_streaming(), --streaming flag (默认关闭)
  - 多线叙事: thread_id/anchor_type, THREAD_BRIDGE/REVEAL边, 时空胶囊衰减
  - 双轨混合对抗: semantic_router.py Python粗筛+LLM审计
  - FCR客观评估: compute_fcr_scores()补充LLM主观评分
  - Batch Prompt: 新增代词消解约束指令, BATCH_SYSTEM_PROMPT增强
- 246/246 测试通过

## LLM 后端
- **Ollama (本地)**: `--backend ollama` (默认), qwen3.5:0.8b
- **NVIDIA (云端)**: `--backend nvidia`, deepseek-v4-flash, 40 req/min
- **DeepSeek (官网)**: `--backend deepseek`, deepseek-chat (不限速)
- 工厂函数: `create_client(LLMConfig)` 自动分发

## 评估系统
- CLI: `text-reconstructor evaluate --backend deepseek` (默认)
- 对比: 直接 LLM 梳理 vs 完整管线处理
- LLM评分: 4维度 (细节保留/疑点识别/模糊处理/结构清晰)
- FCR客观指标: 锚定实体String Match验证
- 报告输出: `评估报告.md`

## 输出模块说明
- **默认输出**: `LLMRefiner` -- LLM-based，结构化分段分点输出
  - Prompt传入图谱边关系描述，前缀去噪，13条规则约束
  - temperature=0.15 (高保真重构而非创造性写作)
- **回退输出**: `TextOutput.format_simple()` -- LLM失败时按scope分组输出原句
- **调试模式**: CLI `--output-format template` 使用旧版模板输出
- **FCR验证**: Refiner输出后自动检查关键实体是否保留
- **核心原则**: 绝不压缩/省略/总结信息，全还原理解与表达复述，标注疑点和矛盾

## 关键模块索引
- `processor/tagger.py` -- LLM标注+6步后处理+代词标记+Mini-Batch
- `processor/prompts.py` -- 所有Prompt模板集中管理
- `processor/buffer.py` -- ActiveBuffer激活/衰减/驱逐/打捞
- `processor/prefix_pruner.py` -- 序数词脚手架去噪
- `graph/models.py` -- 19种EdgeType + GraphNode(含thread_id/anchor_type)
- `graph/updater.py` -- 6条建边规则 + 代词消解 + 多线建边 + ActiveBuffer
- `graph/decay.py` -- Ebbinghaus对数衰减 + 时空胶囊 + 7项对抗扫描
- `adversary/semantic_router.py` -- 双轨混合对抗(拓扑粗筛+LLM审计)
- `output/llm_refiner.py` -- 增强Prompt+边关系+前缀去噪
- `output/detail_anchor.py` -- URL/数据/比喻自动提取
- `output/fcr.py` -- FCR事实覆盖率String Match验证
- `output/suggestions.py` -- 只输出高危逻辑中断

## 系统布局手册
完整技术文档在 `docs/system-layout-manual.md` v3.0，包含所有Prompt原文、所有正则、所有参数、所有规则，供大佬审核。
