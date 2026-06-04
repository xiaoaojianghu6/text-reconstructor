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
- Phase 0: 项目初始化 ✅
- Phase 1: 理论调研 ✅
- Phase 2: 小模型选型 (qwen3.5:0.8B) ✅
- Phase 3: 架构设计 ✅
- Phase 4: 动态滑动窗口处理器 ✅
- Phase 5: 增量语义图谱 ✅
- Phase 6: 对抗机 ✅
- Phase 7: 输出模块 (LLMRefiner) ✅ [详见 plan]
- Phase 8: 集成与完善 ✅ [详见 plan]
- Phase 9: 云端 LLM 集成 (NVIDIA API) ✅ 2026-06-04
- Phase 10: 科学有效性修复 ✅ 2026-06-04
- Phase 11: 对比评估机制 ✅ 2026-06-04
- Phase 12: 系统布局手册 + 文档更新 ✅ 2026-06-04

## LLM 后端
- **Ollama (本地)**: `--backend ollama` (默认), qwen3.5:0.8b
- **NVIDIA (云端)**: `--backend nvidia`, deepseek-v4-flash, 40 req/min
- **DeepSeek (官网)**: `--backend deepseek`, deepseek-chat (不限速)
- 工厂函数: `create_client(LLMConfig)` 自动分发

## 评估系统
- CLI: `text-reconstructor evaluate --backend deepseek` (默认)
- 对比: 直接 LLM 梳理 vs 完整管线处理
- 4 维度评分: 细节保留/疑点识别/模糊处理/结构清晰
- 报告输出: `评估报告.md`

## 输出模块说明
- **默认输出**: `LLMRefiner` — LLM-based，结构化分段分点输出
- **回退输出**: `TextOutput.format_simple()` — LLM 失败时按 scope 分组输出原句
- **调试模式**: CLI `--output-format template` 使用旧版模板输出
- **核心原则**: 绝不压缩/省略信息，保留全部原意，标注疑点和矛盾

## 科学有效性修复记录 (2026-06-04)
1. Batch 标注恢复 8 字段 + 6 示例 + ISA 说明
2. DecayEngine: Ebbinghaus 对数衰减实现
3. ActiveBuffer: 激活/衰减/驱逐/打捞完整实现
4. 图边改进: contrast 优先同 scope, argument 优先 claim
5. 信号词规则可配置: override_with_rules 参数
6. 对抗机新增: UNRESOLVED_PRONOUN + ARGUMENT_GAP
7. infer_scope: dependency 回退逻辑
8. Defender: 虚词过滤 + 优先同 scope 匹配
9. LLMRefiner: 结构化输出 prompt (分段/分点/疑点标注)

## V3 重构回滚记录 (2026-06-04)
v3 重构（VPGA 协议、Louvain 聚类、Mini-Batch 管线）评估显示管线评分仅为基线一半。已回滚到 pre-v3 状态。

**已删除**: anchoring.py, prefix_pruning.py, pipeline.py, clustering.py, fcr.py, validation.py

**已恢复**: llm_refiner.py, suggestions.py, cli.py, alert_buffer.py, updater.py, tagger.py, prompts.py, comparator.py

**保留的 Phase B 改进**: DecayEngine, ActiveBuffer, override_with_rules, 图边改进, 新增扫描规则, Defender 改进, infer_scope 回退

**验证**: 223/223 测试通过，评估评分模式与 pre-v3 一致
