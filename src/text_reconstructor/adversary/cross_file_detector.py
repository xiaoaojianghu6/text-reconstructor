"""CrossFileConflictDetector -- 第四轨: LLM 驱动的跨文件冲突检测

用正则提取数值 (可靠)，但所有矛盾判断全部交给 LLM (避免查表法)。
含漏检回溯: LLM 发现缺关键实体时从图谱二次搜索。

仅在 persist_path 模式 (打开文件夹) 下触发。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from ..graph.models import SemanticGraph
from ..graph.numeric_extractor import (
    ConflictCluster,
    extract_numerics_from_graph,
    group_into_clusters,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一个跨文件一致性审计员。你会收到多组来自不同文件的陈述，你的任务是找出它们之间的矛盾。
你必须仔细检查数值、逻辑和语义上的一致性。你不应该遗漏任何可能的矛盾。
对每组回复一行JSON，格式: {"cluster": 编号, "conflict": true或false, "detail": "矛盾说明或空", "missing_entities": ["实体1"]}"""

_BATCH_AUDIT_PROMPT = """请逐簇审计以下陈述组，找出跨文件矛盾：

{clusters_text}

对每簇回复一行JSON（不要包含其他内容）:
{{"cluster": 编号, "conflict": true或false, "detail": "详细说明矛盾内容，或空字符串", "missing_entities": ["需要但缺失的实体"]}}"""


@dataclass
class AuditResult:
    conflict: bool
    detail: str
    missing_entities: list[str]


class CrossFileConflictDetector:

    def __init__(self, llm_client=None, max_llm_calls: int = 2):
        self.llm_client = llm_client
        self.max_llm_calls = max_llm_calls

    def scan(self, graph: SemanticGraph) -> list[dict]:
        """执行跨文件冲突检测 (批量审计版)"""
        # Phase 1: 正则提取数值
        numerics = extract_numerics_from_graph(graph)
        if not numerics:
            return []

        # Phase 2: 分组为冲突簇
        clusters = group_into_clusters(graph, numerics)

        # Phase 3: 预过滤 -- 只留跨文件或含数值的簇
        candidates = [
            c for c in clusters
            if c.cross_file or len(c.numerics) >= 2
        ]
        if not candidates:
            return []

        # 优先跨文件簇，其次数值多的簇，取前5个控制prompt长度
        candidates.sort(
            key=lambda c: (c.cross_file, len(c.numerics)),
            reverse=True,
        )
        candidates = [c for c in candidates[:5] if len(c.nodes) >= 2]

        if not candidates:
            return []

        # Phase 4: 一次 LLM 调用审计全部候选簇
        results = self._batch_audit_clusters(candidates)
        alerts: list[dict] = []
        all_missing: list[str] = []

        for i, cluster in enumerate(candidates):
            result = results.get(i)
            if result is None:
                continue
            if result.conflict and result.detail:
                alerts.append({
                    "type": "CROSS_FILE_CONFLICT",
                    "detail": result.detail,
                    "severity": "high",
                    "source": "cross_file_detector",
                    "node_ids": [n.id for n in cluster.nodes],
                })
            if result.missing_entities:
                all_missing.extend(result.missing_entities)

        # Phase 5: 漏检回溯 (一次 LLM 调用处理全部缺失实体)
        if all_missing and alerts:
            backfill = self._backtrack(graph, candidates[0], all_missing)
            alerts.extend(backfill)

        return alerts

    def _batch_audit_clusters(self, clusters: list[ConflictCluster]) -> dict[int, AuditResult | None]:
        """一次 LLM 调用审计全部簇"""
        if not self.llm_client:
            return {}

        parts = []
        for i, cluster in enumerate(clusters, 1):
            entries = self._format_cluster_entries(cluster)
            parts.append(f"簇{i} (主题: {cluster.scope or '(无明确主题)'}):\n{entries}")
        prompt = _BATCH_AUDIT_PROMPT.format(clusters_text="\n\n".join(parts))

        try:
            resp = self.llm_client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=_SYSTEM_PROMPT,
                max_retries=1,
            )
            content = resp.content.strip()
        except Exception as e:
            logger.warning("批量跨文件审计LLM调用失败: %s", e)
            return {}

        results: dict[int, AuditResult | None] = {}
        for line in content.split("\n"):
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            result = self._parse_response(line)
            if result is None:
                continue
            # 从原始行提取 cluster 编号
            try:
                data = json.loads(line)
                cluster_idx = int(data.get("cluster", 1)) - 1
                if 0 <= cluster_idx < len(clusters):
                    results[cluster_idx] = result
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        return results

    def _format_cluster_entries(self, cluster: ConflictCluster) -> str:
        """格式化簇内节点为 LLM 可读的条目列表"""
        lines = []
        for node in cluster.nodes:
            source = node.file_path or node.file_id or f"节点{node.id}"
            # 找该节点的数值
            node_nums = [
                n for n in cluster.numerics if n.node_id == node.id
            ]
            num_info = ""
            if node_nums:
                parts = [f"{n.value:g}" for n in node_nums]
                num_info = f"  [含数值: {', '.join(parts)}]"
            lines.append(f'来源: {source}\n  "{node.text}"{num_info}')
        return "\n".join(lines)

    def _audit_cluster(self, cluster: ConflictCluster) -> AuditResult | None:
        """审计单个簇(供backtrack使用)"""
        results = self._batch_audit_clusters([cluster])
        return results.get(0)

    def _parse_response(self, content: str) -> AuditResult | None:
        """解析 LLM 的 JSON 响应"""
        # 尝试提取 JSON (可能被 markdown 包裹)
        json_str = content
        if "```" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]
        elif "{" in content:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = content[start:end]

        try:
            data = json.loads(json_str)
            return AuditResult(
                conflict=bool(data.get("conflict", False)),
                detail=str(data.get("detail", "")),
                missing_entities=list(data.get("missing_entities", [])),
            )
        except (json.JSONDecodeError, TypeError):
            logger.warning("无法解析LLM响应为JSON: %s", content[:200])
            return None

    def _backtrack(
        self,
        graph: SemanticGraph,
        cluster: ConflictCluster,
        missing_entities: list[str],
    ) -> list[dict]:
        """漏检回溯: 从图谱中搜索缺失实体"""
        alerts = []
        found_nodes = []
        for entity in missing_entities:
            matches = graph.find_by_text(entity)
            if matches:
                found_nodes.extend(matches)

        if not found_nodes:
            # 图谱中没有，提示用户
            entity_str = "、".join(missing_entities)
            alerts.append({
                "type": "MISSING_ENTITY",
                "detail": f"跨文件一致性验证需要但未找到关键信息: {entity_str}",
                "severity": "medium",
                "source": "cross_file_detector",
                "node_ids": [n.id for n in cluster.nodes],
            })
            return alerts

        # 找到了缺失实体，扩展簇后重新审计
        existing_ids = {n.id for n in cluster.nodes}
        new_nodes = [n for n in found_nodes if n.id not in existing_ids]
        if not new_nodes:
            return []

        expanded = ConflictCluster(
            cluster_id=cluster.cluster_id + "_expanded",
            scope=cluster.scope,
            nodes=cluster.nodes + new_nodes,
            numerics=cluster.numerics,
            cross_file=True,
        )
        # 补充新节点的数值
        for node in new_nodes:
            from ..graph.numeric_extractor import _extract_from_node
            expanded.numerics.extend(_extract_from_node(node))

        result = self._audit_cluster(expanded)
        if result and result.conflict and result.detail:
            alerts.append({
                "type": "CROSS_FILE_CONFLICT",
                "detail": result.detail,
                "severity": "high",
                "source": "cross_file_detector",
                "node_ids": [n.id for n in expanded.nodes],
            })

        return alerts
