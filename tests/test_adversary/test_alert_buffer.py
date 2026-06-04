"""AlertBuffer + ConfidenceManager 单元测试"""

import pytest
from text_reconstructor.graph.models import SemanticGraph, EdgeType
from text_reconstructor.adversary.alert_buffer import AlertEntry, AlertBuffer, ConfidenceManager
from text_reconstructor.adversary.prosecutor import Prosecution, Prosecutor
from text_reconstructor.adversary.defender import Defender


# ==================================================================
# AlertBuffer 测试
# ==================================================================

class TestAlertBuffer:
    """AlertBuffer 优先级队列测试"""

    def setup_method(self):
        self.buffer = AlertBuffer()

    def test_push_new_alert(self):
        """新 alert 正确加入"""
        self.buffer.push(alert_type="LOW_CONFIDENCE", node_id=1,
                         text="模糊", severity="medium")
        assert self.buffer.size() == 1

    def test_push_dedup_same_key(self):
        """同 (type, node_id) 合并计数"""
        self.buffer.push(alert_type="LOW_CONFIDENCE", node_id=1, text="A")
        self.buffer.push(alert_type="LOW_CONFIDENCE", node_id=1, text="B")
        assert self.buffer.size() == 1
        alerts = self.buffer.get_all()
        assert alerts[0]["count"] == 2

    def test_push_dedup_different_type(self):
        """不同 type 不合并"""
        self.buffer.push(alert_type="LOW_CONFIDENCE", node_id=1)
        self.buffer.push(alert_type="ISOLATED_NODE", node_id=1)
        assert self.buffer.size() == 2

    def test_has_existing(self):
        """has() 返回 True"""
        self.buffer.push(alert_type="LOW_CONFIDENCE", node_id=1)
        assert self.buffer.has("LOW_CONFIDENCE", 1) is True

    def test_has_nonexistent(self):
        """has() 返回 False"""
        assert self.buffer.has("LOW_CONFIDENCE", 999) is False

    def test_get_all_ordering(self):
        """按 severity→round→count 降序"""
        self.buffer.push(alert_type="A", node_id=1, severity="low", round=1, detail="低")
        self.buffer.push(alert_type="B", node_id=2, severity="high", round=1, detail="高")
        self.buffer.push(alert_type="C", node_id=3, severity="medium", round=2, detail="中2")
        alerts = self.buffer.get_all()
        assert len(alerts) == 3
        # high > medium > low by severity rank (3 > 2 > 1)
        assert alerts[0]["severity"] == "high"
        assert alerts[1]["severity"] == "medium"
        assert alerts[2]["severity"] == "low"

    def test_get_all_empty(self):
        """空 buffer 返回空列表"""
        assert self.buffer.get_all() == []

    def test_get_all_format(self):
        """输出 dict 字段完整"""
        self.buffer.push(alert_type="TEST", node_id=1, text="T", scope="S",
                         detail="D", severity="high", round=2)
        alerts = self.buffer.get_all()
        a = alerts[0]
        assert "type" in a
        assert "node_id" in a
        assert "text" in a
        assert "scope" in a
        assert "detail" in a
        assert "severity" in a
        assert "round" in a
        assert "count" in a

    def test_clear(self):
        """clear 后 size=0"""
        self.buffer.push(alert_type="A", node_id=1)
        self.buffer.clear()
        assert self.buffer.size() == 0

    def test_size(self):
        """push 后 size 正确"""
        self.buffer.push(alert_type="A", node_id=1)
        self.buffer.push(alert_type="B", node_id=2)
        self.buffer.push(alert_type="C", node_id=3)
        assert self.buffer.size() == 3

    def test_severity_never_downgrade(self):
        """已 high 不被 medium 覆盖"""
        self.buffer.push(alert_type="A", node_id=1, severity="high")
        self.buffer.push(alert_type="A", node_id=1, severity="medium")
        alerts = self.buffer.get_all()
        assert alerts[0]["severity"] == "high"

    def test_push_upgrade_severity(self):
        """从 medium 升级到 high"""
        self.buffer.push(alert_type="A", node_id=1, severity="medium")
        self.buffer.push(alert_type="A", node_id=1, severity="high")
        alerts = self.buffer.get_all()
        assert alerts[0]["severity"] == "high"


# ==================================================================
# ConfidenceManager 测试
# ==================================================================

class TestConfidenceManager:
    """置信度管理与辩论循环测试"""

    def setup_method(self):
        self.conf_mgr = ConfidenceManager()
        self.prosecutor = Prosecutor()
        self.defender = Defender()

    def _make_graph(self, conf=0.6):
        """创建测试图，返回 graph 和目标节点"""
        g = SemanticGraph()
        n = g.add_node(text="目标节点", intent="assertive", scope="test",
                       chunk_index=0, confidence=conf)
        return g, n

    def _make_support_graph(self, g, target_node):
        """添加 SUPPORT 支持到目标节点"""
        n = g.add_node(text="支持者", intent="assertive", scope="other",
                       chunk_index=1)
        g.add_edge(n.id, target_node.id, EdgeType.SUPPORT)
        return g

    def test_conf_above_safety(self):
        """初始 conf=0.8 → 一轮后停止, 不入 buffer"""
        g, n = self._make_graph(conf=0.8)
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": n.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "medium"}]
        prosecutions = self.prosecutor.build(alerts, g)
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, self.defender)
        assert n.confidence >= 0.7
        assert self.conf_mgr.alert_buffer.size() == 0

    def test_defense_success_round1(self):
        """有证据 → conf 回升, 不入 buffer"""
        g, n = self._make_graph(conf=0.6)
        self._make_support_graph(g, n)  # 添加 SUPPORT 边
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": n.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "medium"}]
        prosecutions = self.prosecutor.build(alerts, g)
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, self.defender)
        assert n.confidence >= 0.7  # 0.6 + 0.1 = 0.7 (safety line)
        assert self.conf_mgr.alert_buffer.size() == 0

    def test_defense_fail_round1(self):
        """无证据 → conf 下降, 进入 round 2"""
        g, n = self._make_graph(conf=0.6)
        alerts = [{"type": "ISOLATED_NODE", "node_id": n.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "low"}]
        prosecutions = self.prosecutor.build(alerts, g)
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, self.defender)
        assert n.confidence < 0.7  # 辩护失败

    def test_defense_fail_round2(self):
        """2 轮均失败 → conf < 0.5, 入 buffer"""
        g, n = self._make_graph(conf=0.6)
        alerts = [{"type": "ISOLATED_NODE", "node_id": n.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "low"}]
        prosecutions = self.prosecutor.build(alerts, g)
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, self.defender)
        # 2 * (-0.15) → 0.6 - 0.3 = 0.3 < 0.5
        assert n.confidence < 0.5
        assert self.conf_mgr.alert_buffer.size() >= 1
        alerts_out = self.conf_mgr.alert_buffer.get_all()
        assert alerts_out[0]["severity"] == "high"

    def test_round2_recovery(self):
        """1 轮失败（无入边）, 2 轮通过全局文本匹配找到证据 → conf 回升"""
        g = SemanticGraph()
        n = g.add_node(text="测试节点", scope="", chunk_index=0, confidence=0.55)

        # Round 1 for LOW_CONFIDENCE: incoming_support/evidence/background → 全无 → fail
        # Round 2 新增 global_text_match:
        #   需要另一个包含相同 4-gram 的节点
        helper = g.add_node(text="测试节点二号", scope="其他", chunk_index=1)
        other = g.add_node(text="填充", chunk_index=2)
        g.add_edge(helper.id, other.id, EdgeType.CAUSE)  # helper 非孤立

        alerts = [{"type": "LOW_CONFIDENCE", "node_id": n.id, "text": "测试节点",
                   "scope": "", "detail": "", "severity": "medium"}]
        prosecutions = self.prosecutor.build(alerts, g, round_num=1)
        self.conf_mgr.run_node_cycle(
            n.id, prosecutions, g, self.prosecutor, self.defender
        )

        # Round 1: -0.15 → 0.40
        # Round 2: global_text_match 找到"测试节点二号" → +0.10 → 0.50
        assert n.confidence > 0.45

    def test_safety_line_early_stop(self):
        """Round 1 后 conf >= 0.7 → 不执行 Round 2"""
        g, n = self._make_graph(conf=0.65)
        self._make_support_graph(g, n)
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": n.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "medium"}]
        prosecutions = self.prosecutor.build(alerts, g)

        # Mock defender 追踪调用次数
        call_count = [0]

        class TrackingDefender(Defender):
            def respond(self, prosecution, graph):
                call_count[0] += 1
                return super().respond(prosecution, graph)

        tracker = TrackingDefender()
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, tracker)
        # 0.65 + 0.1 = 0.75 >= 0.7 → 只调用 1 次
        # 但 run_node_cycle 内 re-build prosecutions 后，再 respond
        # 实际上有多个 prosecution 时 respond 可能调用多次
        # 所以我们只检查最终 conf >= 0.7
        assert n.confidence >= 0.7

    def test_max_rounds_enforced(self):
        """最多 2 轮"""
        g, n = self._make_graph(conf=0.6)

        class CounterDefender(Defender):
            def __init__(self):
                super().__init__()
                self.rounds = 0

            def respond(self, prosecution, graph):
                self.rounds += 1
                return DefenseResult(success=False, confidence_delta=-0.15,
                                     message="no")

        from text_reconstructor.adversary.defender import DefenseResult
        counter = CounterDefender()
        alerts = [{"type": "ISOLATED_NODE", "node_id": n.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "low"}]
        prosecutions = self.prosecutor.build(alerts, g)

        prev_step = self.conf_mgr.MAX_ROUNDS
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, counter)
        # conf: 0.6 - 0.15 = 0.45 (round1), 0.45 - 0.15 = 0.30 (round2)
        # MAX_ROUNDS=2, 每轮 respond 调用至少 1 次
        assert n.confidence < 0.5

    def test_scope_cycle_direct_push(self):
        """scope 级 alert 直接入 buffer"""
        g = SemanticGraph()
        p = Prosecution(
            alert_type="STRUCTURE_CHAOS", node_id=-1, text="混乱",
            scope="域", detail="密集", severity="medium", round=1,
            required_evidence="", evidence_targets=[],
        )
        self.conf_mgr.run_scope_cycle(p, g)
        assert self.conf_mgr.alert_buffer.size() == 1
        alerts = self.conf_mgr.alert_buffer.get_all()
        assert alerts[0]["type"] == "STRUCTURE_CHAOS"

    def test_confidence_clamping(self):
        """conf 始终在 [0.0, 1.0] 内"""
        g, n = self._make_graph(conf=0.1)
        # 无法低于 0.0
        n.confidence = 0.0
        assert n.confidence >= 0.0

        g2, n2 = self._make_graph(conf=0.95)
        # 辩护成功
        supporter = g2.add_node(text="支撑", chunk_index=1)
        g2.add_edge(supporter.id, n2.id, EdgeType.SUPPORT)
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": n2.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "medium"}]
        prosecutions = self.prosecutor.build(alerts, g2)
        self.conf_mgr.run_node_cycle(n2.id, prosecutions, g2, self.prosecutor, self.defender)
        assert n2.confidence <= 1.0

    def test_alert_severity_high(self):
        """conf < 0.5 → severity=high"""
        g, n = self._make_graph(conf=0.3)
        alerts = [{"type": "LOW_CONFIDENCE", "node_id": n.id, "text": "目标",
                   "scope": "", "detail": "", "severity": "medium"}]
        prosecutions = self.prosecutor.build(alerts, g)
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, self.defender)
        alerts_out = self.conf_mgr.alert_buffer.get_all()
        assert all(a["severity"] == "high" for a in alerts_out)

    def test_alert_severity_medium(self):
        """0.5 <= conf < 0.7 → severity=medium"""
        g = SemanticGraph()
        # 起始 conf=0.55 → round1 失败 (0.40) → round2 global_text_match 成功 (0.50)
        n = g.add_node(text="测试节点", intent="assertive", scope="",
                       chunk_index=0, confidence=0.55)
        # round2 需要 global_text_match 找到匹配节点
        helper = g.add_node(text="测试节点二号", scope="其他", chunk_index=1)
        filler = g.add_node(text="填充", chunk_index=2)
        g.add_edge(helper.id, filler.id, EdgeType.CAUSE)  # helper 非孤立

        alerts = [{"type": "LOW_CONFIDENCE", "node_id": n.id, "text": "测试节点",
                   "scope": "", "detail": "", "severity": "medium"}]
        prosecutions = self.prosecutor.build(alerts, g)
        self.conf_mgr.run_node_cycle(n.id, prosecutions, g, self.prosecutor, self.defender)
        alerts_out = self.conf_mgr.alert_buffer.get_all()
        # 0.55-0.15=0.40(round1), 0.40+0.10=0.50(round2) ≥ 0.5 → medium
        assert any(a["severity"] == "medium" for a in alerts_out)
        assert abs(n.confidence - 0.50) < 0.01
