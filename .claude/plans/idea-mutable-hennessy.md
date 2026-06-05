# 文本重构项目 - 施工规划

**状态**: Phases A-E + Phase 13 全面整改 + Phase 8 全部完成 (2026-06-04)

## Phase 8: 启用增强模块 + 手册重写 + 评估 (已完成)

### 8.0 启用全部增强模块
- Mini-Batch streaming: 默认启用 (--no-streaming 可关闭)
- 多线叙事 Prompt: BATCH_TAGGING_TEMPLATE 新增 thread_id/anchor_type (10字段)
- 双轨混合对抗: SemanticAdversaryRouter 接入 GraphUpdater (llm_config 参数)
- SemanticGraph: 新增 has_edge() 方法

### 8.1 系统布局手册 v3.0
- docs/system-layout-manual.md: 648行完整重写
- 包含全部 19 种 EdgeType、所有 Prompt 原文、所有正则、所有参数

### 8.2 首次全增强评估 (deepseek-chat, 3个真实测试文本)
- 测试文本1 (短): 系统疑点识别+2优于基线，其余维度基线优
- 测试文本2 (长): 基线全面优于系统
- 测试文本3 (大长文): 基线全面优于系统
- 结论: 管线在疑点识别上有优势，但细节保留和结构清晰度弱于直接LLM梳理

## 已完成的修复与功能

### Phase A: 云端 LLM 集成 (已完成)
- NVIDIAClient: OpenAI 兼容格式, 令牌桶速率限制
- DeepSeekClient: 通过 NVIDIAClient + 不同 base_url 实现
- 工厂函数: create_client(config) -> OllamaClient | NVIDIAClient
- CLI: --backend ollama/nvidia/deepseek

### Phase B: 科学有效性修复 (已完成)
1. Batch 标注恢复 8 字段 + 6 示例 + ISA 说明
2. DecayEngine: Ebbinghaus 对数衰减, role-based 速率
3. ActiveBuffer: 激活/衰减/驱逐/打捞完整实现
4. 图边改进: contrast 优先同 scope, argument 优先 claim
5. 信号词规则可配置: override_with_rules 参数
6. 对抗机新增: UNRESOLVED_PRONOUN + ARGUMENT_GAP
7. infer_scope: dependency 回退逻辑
8. Defender: 虚词过滤 + 优先同 scope 匹配
9. LLMRefiner: 结构化输出 prompt (绝不压缩, 分段分点, 疑点标注)

### Phase C: 对比评估机制 (已完成)
- Evaluator: baseline vs pipeline 对比
- 4 维度评分: detail_preservation/doubt_identification/fuzzy_concept_handling/structure_clarity
- 报告生成: 评估报告.md
- CLI: text-reconstructor evaluate

### Phase D: 系统布局手册 (已完成)
- docs/system-layout-manual.md: 10 章节完整文档

### Phase E: 文档更新 (已完成)
- system-design.md 更新至 v2.0
- CLAUDE.md 添加三个后端说明
- pyproject.toml 依赖更新

## 首次评估结果总结

使用 DeepSeek-chat 评估 3 个测试文本:

| 测试文本 | 基线 vs 管线 |
|----------|-------------|
| 文本1 (短文本) | 基线全面胜出 (细节+2, 疑点+2, 模糊+3, 结构+1) |
| 文本2 (长文) | 管线全面胜出 (细节+1, 疑点+2, 模糊+2, 结构+2) |
| 文本3 (大长文) | 管线细节+1 结构+2, 基线疑点+2 模糊+3 |

**结论**: 管线在长文本的细节保留和结构清晰度上优势明显，但在疑点识别和模糊概念处理上弱于直接 LLM 梳理。需要优化对抗机到 LLMRefiner 的信息传递。

## 下一步计划

1. 优化 LLMRefiner prompt: 传递更多对抗机发现的疑点/模糊信息
2. 增加 scope 合并/去噪，减少过细分段
3. 调整 system-design.md 中 `_make_config` 的 timeout 处理方式（已修复）
4. 测试 CLI main 命令的 deepseek 后端

## 全面整改 Phase 13 (2026-06-04)

基于外部大佬审核 + 独立代码审查的全面整改，246/246测试通过。

### 阶段0: 死代码清理
- 删除chunker.py不可达代码
- 标记prompts.py预备代码供Mini-Batch使用

### 阶段1: RST过度修正与Scope推理修复
- 删除relation=none强制降级satellite (尊重LLM判断)
- scope推理触发改为质量检查 (检查空/REFERENCE_MISSING而非数量)
- scope回退长度4->8字符 + 代词过滤
- check_pronouns不再污染scope字段 (改为_pronoun_needs_resolution标记)
- BATCH_TAGGING_TEMPLATE添加代词消解约束指令
- BATCH_SYSTEM_PROMPT增强为RST/言语行为领域说明

### 阶段2: 对抗机警报过滤 + 前缀去噪
- Suggestions只输出DANGLING_DIRECTIVE和LOGIC_CONFLICT (severity>=medium)
- 新增prefix_pruner.py: 移除序数词脚手架 (第X[个/点/部分/步]、其次、再然后等)

### 阶段3: FCR + 细节锚定 + Refiner增强 (核心)
- 新增detail_anchor.py: URL/数据/比喻/引号术语自动提取
- 新增fcr.py: String Match验证重构输出保留关键实体
- LLMRefiner: _build_prompt()传入图谱边关系描述+前缀去噪
- STRUCTURING_PROMPT: 13条规则, 强调梳理复述非概括
- temperature降至0.15 (高保真重构)
- CLI: Refiner输出后FCR日志记录

### 阶段4: ActiveBuffer接入 + 代词图谱消解
- GraphUpdater中初始化和更新ActiveBuffer
- _resolve_pronoun_via_graph(): CO_SCOPE边回溯 + 时间轴反向5步
- process()返回active_summary

### 阶段5: Mini-Batch流式标注 (默认关闭)
- batch_tag_streaming(): 8句一批+ActiveBuffer Top-3上下文
- MINI_BATCH_TEMPLATE和build_mini_batch_prompt()
- CLI --streaming flag

### 阶段6: 多线叙事支持
- EdgeType新增THREAD_BRIDGE和REVEAL (共19种)
- GraphNode新增thread_id(main/sub/latent)和anchor_type(foreshadow/reveal/none)
- 时空胶囊衰减: foreshadow衰减率0.01, thread_id差异化
- 多线建边: THREAD_BRIDGE(副线->主线), REVEAL(照应->伏笔)

### 阶段7: 双轨混合对抗 + FCR客观评估
- 新增semantic_router.py: 拓扑粗筛(3种检测) + LLM审计(最多5对)
- Evaluator新增compute_fcr_scores(): 客观FCR补充LLM主观评分
