"""TextOutput — 结构化纯文本输出

将 GraphUpdater 产出的 graph snapshot 转化为带缩进和关系标记的结构化文本。
算法: Kahn 拓扑排序 → scope 分组 → 关系标记 + 缩进。
"""

from __future__ import annotations


class TextOutput:
    """结构化纯文本输出

    输入: graph snapshot dict (GraphUpdater.process 的输出)
    输出: 格式化的纯文本字符串

    标记规则:
      (无前缀) — nucleus / 根节点
      +        — SUPPORT / EVIDENCE / ELABORATION / BACKGROUND
      -        — ATTACK / CONTRAST / CONCESSION
      →        — RESULT / SEQUENCE / PURPOSE / CAUSE
    """

    _SUPPORTIVE = {"support", "evidence", "elaboration", "background"}
    _ADVERSARIAL = {"attack", "contrast", "concession"}
    _PROGRESSIVE = {"result", "sequence", "purpose", "cause"}

    def format(self, snapshot: dict) -> str:
        """入口: snapshot → 结构化纯文本"""
        nodes = snapshot.get("nodes", [])
        edges = snapshot.get("edges", [])
        if not nodes:
            return ""

        sorted_nodes = self._topological_sort(nodes, edges)
        groups = self._group_by_scope(sorted_nodes)
        indents, prefixes = self._compute_format(sorted_nodes, edges)

        lines: list[str] = []
        for scope_name, group_nodes in groups.items():
            if scope_name:
                lines.append(f"## {scope_name}")
                lines.append("")
            for node in group_nodes:
                nid = node["id"]
                prefix = prefixes.get(nid, "")
                indent = indents.get(nid, 0)
                marker = f"{prefix} " if prefix else ""
                lines.append(" " * indent + marker + node["text"])
            lines.append("")

        return "\n".join(lines).rstrip()

    def format_simple(self, snapshot: dict) -> str:
        """简化版输出：按 scope 分组输出原句，无前缀标记

        作为 LLMRefiner 的 fallback，LLM 失败时使用。
        """
        nodes = snapshot.get("nodes", [])
        if not nodes:
            return ""

        sorted_nodes = self._topological_sort(nodes, snapshot.get("edges", []))
        groups = self._group_by_scope(sorted_nodes)

        lines: list[str] = []
        for scope_name, group_nodes in groups.items():
            if scope_name:
                lines.append(f"## {scope_name}")
                lines.append("")
            for node in group_nodes:
                lines.append(node["text"])
            lines.append("")

        return "\n".join(lines).rstrip()

    # ── 拓扑排序 ──

    def _topological_sort(
        self, nodes: list[dict], edges: list[dict]
    ) -> list[dict]:
        """Kahn 拓扑排序，排除 CO_SCOPE 双向边"""
        dig_edges = [e for e in edges if e["edge_type"] != "co_scope"]

        adj: dict[int, list[int]] = {}
        in_degree: dict[int, int] = {}
        for n in nodes:
            nid = n["id"]
            adj.setdefault(nid, [])
            in_degree.setdefault(nid, 0)
        for e in dig_edges:
            adj.setdefault(e["source_id"], []).append(e["target_id"])
            in_degree[e["target_id"]] = in_degree.get(e["target_id"], 0) + 1

        node_map = {n["id"]: n for n in nodes}
        queue = sorted(
            (nid for nid, deg in in_degree.items() if deg == 0),
            key=lambda nid: node_map[nid]["chunk_index"],
        )

        sorted_ids: list[int] = []
        while queue:
            nid = queue.pop(0)
            sorted_ids.append(nid)
            for target in adj.get(nid, []):
                in_degree[target] -= 1
                if in_degree[target] == 0:
                    queue.append(target)
            queue.sort(key=lambda nid: node_map[nid]["chunk_index"])

        # 有环时补上剩余节点
        remaining = sorted(
            (n for n in nodes if n["id"] not in sorted_ids),
            key=lambda n: n["chunk_index"],
        )
        sorted_ids.extend(n["id"] for n in remaining)

        return [node_map[nid] for nid in sorted_ids]

    # ── scope 分组 ──

    _RELATION_LABELS = {
        "cause": "原因",
        "result": "结果",
        "evidence": "举例",
        "elaboration": "说明",
        "background": "背景",
        "condition": "条件",
        "purpose": "目的",
        "summary": "总结",
        "contrast": "转折",
        "concession": "让步",
        "sequence": "顺序",
        "attribution": "引用",
        "evaluation": "评价",
        "restatement": "重申",
    }

    @staticmethod
    def _group_by_scope(
        nodes: list[dict],
    ) -> dict[str, list[dict]]:
        """按 scope 分组，空 scope 的节点按 relation 分组"""
        groups: dict[str, list[dict]] = {}
        for n in nodes:
            scope = n.get("scope", "") or ""
            if not scope:
                # 空 scope → 按 relation 分组
                rel = n.get("relation", "none")
                label = TextOutput._RELATION_LABELS.get(rel, "")
                scope = f"[{label}]" if label else "(其他)"
            groups.setdefault(scope, []).append(n)
        return groups

    # ── 计算缩进和前缀 ──

    def _compute_format(
        self, sorted_nodes: list[dict], edges: list[dict]
    ) -> tuple[dict[int, int], dict[int, str]]:
        """按拓扑序计算每个节点的缩进层级和前缀标记

        策略: 对每个节点，找到拓扑序中最接近的入边，
        根据边类型确定前缀，缩进继承源节点层级 + 2。
        """
        node_pos = {n["id"]: i for i, n in enumerate(sorted_nodes)}
        indent: dict[int, int] = {}
        prefix: dict[int, str] = {}

        # 按 source 组织边
        from_edges: dict[int, list[dict]] = {}
        for e in edges:
            from_edges.setdefault(e["target_id"], []).append(e)

        for n in sorted_nodes:
            nid = n["id"]
            incoming = from_edges.get(nid, [])

            # 筛选来自前序节点的边
            best_pos = -1
            best_edge = None
            for e in incoming:
                sid = e["source_id"]
                if sid in node_pos and node_pos[sid] < node_pos[nid]:
                    if node_pos[sid] > best_pos:
                        best_pos = node_pos[sid]
                        best_edge = e

            if best_edge is None:
                indent[nid] = 0
                prefix[nid] = ""
            else:
                sid = best_edge["source_id"]
                et = best_edge["edge_type"]
                base = indent.get(sid, 0)
                if et in self._SUPPORTIVE:
                    prefix[nid] = "+"
                    indent[nid] = base + 2
                elif et in self._ADVERSARIAL:
                    prefix[nid] = "-"
                    indent[nid] = base + 2
                elif et in self._PROGRESSIVE:
                    prefix[nid] = "→"
                    indent[nid] = base + 2
                else:
                    prefix[nid] = ""
                    indent[nid] = base

        return indent, prefix
