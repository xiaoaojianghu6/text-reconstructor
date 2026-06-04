# 文本重构项目 - 施工规划

**状态**: Phases A-E 全部完成 (2026-06-04)

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
