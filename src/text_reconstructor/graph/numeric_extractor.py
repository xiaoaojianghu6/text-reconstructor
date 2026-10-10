"""NumericExtractor -- 从图谱节点文本中提取结构化数值信息

正则提取数值+单位+上下文窗口，供跨文件冲突检测器使用。
语义角色判断全部交给 LLM，不做查表法。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .models import GraphNode, SemanticGraph


# 只匹配数字本身，单位和语义全交给 LLM 理解
_NUMBER_RE = re.compile(r'\d+(?:\.\d+)?')

# 上下文窗口: 数值前后各 20 字
_CONTEXT_RADIUS = 20


@dataclass
class ExtractedNumeric:
    node_id: int
    raw: str              # 原始匹配文本 "20"
    value: float          # 20.0
    context_window: str   # 前后 20 字，供 LLM 理解语义


@dataclass
class ConflictCluster:
    cluster_id: str
    scope: str
    nodes: list[GraphNode] = field(default_factory=list)
    numerics: list[ExtractedNumeric] = field(default_factory=list)
    cross_file: bool = False


def _extract_from_node(node: GraphNode) -> list[ExtractedNumeric]:
    """从单个节点提取所有数值"""
    results = []
    for m in _NUMBER_RE.finditer(node.text):
        num_str = m.group(0)
        try:
            value = float(num_str)
        except ValueError:
            continue
        start = max(0, m.start() - _CONTEXT_RADIUS)
        end = min(len(node.text), m.end() + _CONTEXT_RADIUS)
        context = node.text[start:end]
        results.append(ExtractedNumeric(
            node_id=node.id,
            raw=num_str,
            value=value,
            context_window=context,
        ))
    return results


def extract_numerics_from_graph(graph: SemanticGraph) -> list[ExtractedNumeric]:
    """从图谱所有活跃节点提取数值"""
    all_nums = []
    for node in graph.get_active_nodes():
        all_nums.extend(_extract_from_node(node))
    return all_nums


def _extract_ngrams(text: str, n: int) -> Counter:
    """提取文本中所有 n 字中文字符串"""
    counter = Counter()
    for i in range(len(text) - n + 1):
        seg = text[i:i + n]
        if all('一' <= c <= '鿿' for c in seg):
            counter[seg] += 1
    return counter


def _extract_cluster_keywords(nodes: list[GraphNode]) -> set[str]:
    """提取一组节点中出现 >= 2 次的 2-3 字中文片段"""
    combined = " ".join(n.text for n in nodes)
    bigrams = _extract_ngrams(combined, 2)
    trigrams = _extract_ngrams(combined, 3)
    keywords = set()
    for phrase, count in bigrams.items():
        if count >= 2:
            keywords.add(phrase)
    for phrase, count in trigrams.items():
        if count >= 2:
            keywords.add(phrase)
    return keywords


def _node_text_phrases(text: str) -> set[str]:
    """提取单个节点文本的所有 2-4 字中文片段"""
    phrases = set()
    for n in range(2, 5):
        for i in range(len(text) - n + 1):
            seg = text[i:i + n]
            if all('一' <= c <= '鿿' for c in seg):
                phrases.add(seg)
    return phrases


def _clusters_share_text(cluster_a: ConflictCluster, cluster_b: ConflictCluster) -> bool:
    """检查两个簇的节点文本是否有共享的中文片段 (跨簇直接对比)"""
    for na in cluster_a.nodes:
        phrases_a = _node_text_phrases(na.text)
        if not phrases_a:
            continue
        for nb in cluster_b.nodes:
            phrases_b = _node_text_phrases(nb.text)
            overlap = phrases_a & phrases_b
            if overlap:
                return True
    return False


def group_into_clusters(
    graph: SemanticGraph,
    numerics: list[ExtractedNumeric],
) -> list[ConflictCluster]:
    """将节点分组为冲突簇 (两轮: scope 精确 + 跨簇文本共享合并)"""
    active_nodes = graph.get_active_nodes()
    if not active_nodes:
        return []

    # 构建 node_id -> numerics 映射
    num_map: dict[int, list[ExtractedNumeric]] = {}
    for num in numerics:
        num_map.setdefault(num.node_id, []).append(num)

    # 第一轮: 按 scope 分组
    scope_groups: dict[str, list[GraphNode]] = {}
    for node in active_nodes:
        scope = node.scope or "__no_scope__"
        scope_groups.setdefault(scope, []).append(node)

    clusters: list[ConflictCluster] = []
    cluster_id = 0
    for scope, nodes in scope_groups.items():
        if len(nodes) < 1:
            continue
        file_ids = set(n.file_id for n in nodes if n.file_id)
        cross_file = len(file_ids) > 1
        cluster_numerics = []
        for n in nodes:
            cluster_numerics.extend(num_map.get(n.id, []))
        clusters.append(ConflictCluster(
            cluster_id=f"c{cluster_id}",
            scope=scope if scope != "__no_scope__" else "",
            nodes=list(nodes),
            numerics=cluster_numerics,
            cross_file=cross_file,
        ))
        cluster_id += 1

    # 第二轮: 跨簇节点文本共享合并
    # 对每对簇，检查是否有节点对共享 2-4 字中文片段
    merged = set()
    for i in range(len(clusters)):
        if i in merged:
            continue
        for j in range(i + 1, len(clusters)):
            if j in merged:
                continue
            if _clusters_share_text(clusters[i], clusters[j]):
                clusters[i].nodes.extend(clusters[j].nodes)
                clusters[i].numerics.extend(clusters[j].numerics)
                file_ids = set(
                    n.file_id for n in clusters[i].nodes if n.file_id
                )
                clusters[i].cross_file = len(file_ids) > 1
                clusters[i].scope = f"{clusters[i].scope}+{clusters[j].scope}"
                merged.add(j)

    return [c for i, c in enumerate(clusters) if i not in merged]
