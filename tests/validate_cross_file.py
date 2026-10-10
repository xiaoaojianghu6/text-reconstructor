"""真实 LLM 验证脚本: 用 3 份矛盾文件测试跨文件冲突检测

用法: python tests/validate_cross_file.py

预期检测出 3 类矛盾:
1. 数值矛盾: 每人每天20元 x 12人 x 90天 = 21600 vs 总开销30000
2. 人数矛盾: "10人以内" vs "12名成员"
3. 开发模式矛盾: "敏捷开发模式" vs "瀑布模型"
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from text_reconstructor.graph.models import SemanticGraph
from text_reconstructor.graph.numeric_extractor import (
    extract_numerics_from_graph,
    group_into_clusters,
)
from text_reconstructor.adversary.cross_file_detector import CrossFileConflictDetector
from text_reconstructor.llm import create_client, LLMConfig


def build_test_graph():
    """模拟 Tagger 处理 3 份文件后的图谱状态"""
    g = SemanticGraph()

    # 文件1: 预算 -- 分为两个 chunk (模拟 Tagger 输出)
    g.add_node(
        text="项目预算非常紧张，开销必须维持在每人每天20元以内。",
        scope="项目预算", role="nucleus", confidence=0.85,
        file_id="文件1", file_path="文件1_预算.md",
    )
    g.add_node(
        text="团队总人数控制在10人以内。开发周期预计3个月。",
        scope="项目预算", role="satellite", confidence=0.8,
        file_id="文件1", file_path="文件1_预算.md",
    )

    # 文件2: 团队 -- 两个 chunk
    g.add_node(
        text="目前团队共有12名成员，包括3名前端开发、3名后端开发、2名测试、2名产品经理、1名设计师和1名项目经理。",
        scope="团队构成", role="nucleus", confidence=0.9,
        file_id="文件2", file_path="文件2_团队.md",
    )
    g.add_node(
        text="大家采用敏捷开发模式，每两周一个迭代。",
        scope="开发模式", role="nucleus", confidence=0.85,
        file_id="文件2", file_path="文件2_团队.md",
    )

    # 文件3: 费用 -- 两个 chunk
    g.add_node(
        text="本季度项目总开销为30000元，其中餐饮支出占大头。",
        scope="项目预算", role="nucleus", confidence=0.9,
        file_id="文件3", file_path="文件3_费用.md",
    )
    g.add_node(
        text="开发模式我们决定采用瀑布模型，需求分析阶段已经完成。",
        scope="开发模式", role="nucleus", confidence=0.85,
        file_id="文件3", file_path="文件3_费用.md",
    )

    return g


def main():
    print("=" * 60)
    print(" 跨文件冲突检测 -- 真实 LLM 验证")
    print("=" * 60)

    # 构建图谱
    graph = build_test_graph()
    print(f"\n图谱: {graph.node_count()} 个节点")
    for n in graph.get_nodes():
        print(f"  [{n.file_id}] scope={n.scope}: {n.text[:40]}...")

    # 提取数值
    numerics = extract_numerics_from_graph(graph)
    print(f"\n提取数值: {len(numerics)} 个")
    for num in numerics:
        print(f"  node={num.node_id}: {num.value:g} (上下文: {num.context_window[:30]}...)")

    # 分簇
    clusters = group_into_clusters(graph, numerics)
    print(f"\n冲突簇: {len(clusters)} 个")
    for c in clusters:
        print(f"  {c.cluster_id}: scope={c.scope}, nodes={len(c.nodes)}, "
              f"cross_file={c.cross_file}, numerics={len(c.numerics)}")

    # 初始化 LLM (不传 config，让 NVIDIAClient 用自己的默认值)
    print("\n初始化 NVIDIA LLM...")
    from text_reconstructor.llm.nvidia_client import NVIDIAClient
    from text_reconstructor.llm.adapter import LLMConfig
    nvidia_config = LLMConfig(
        backend="nvidia",
        model="deepseek-ai/deepseek-v4-flash",
        base_url="https://integrate.api.nvidia.com/v1",
        timeout=120.0,
        max_tokens=1024,
    )
    client = NVIDIAClient(config=nvidia_config)

    # 运行检测
    print("运行跨文件冲突检测 (真实 LLM)...")
    detector = CrossFileConflictDetector(llm_client=client, max_llm_calls=5)
    alerts = detector.scan(graph)

    # 输出结果
    print(f"\n{'=' * 60}")
    print(f" 检出 alerts: {len(alerts)} 个")
    print(f"{'=' * 60}")

    for i, alert in enumerate(alerts, 1):
        print(f"\n[{i}] type={alert['type']}, severity={alert['severity']}")
        print(f"    detail: {alert['detail']}")
        print(f"    node_ids: {alert.get('node_ids', [])}")

    # 验证 3 类矛盾
    print(f"\n{'=' * 60}")
    print(" 验证结果")
    print(f"{'=' * 60}")

    all_details = " ".join(a["detail"] for a in alerts if a["type"] == "CROSS_FILE_CONFLICT")
    all_details_lower = all_details.lower()

    checks = [
        ("数值矛盾 (20*12*90 vs 30000)", any(kw in all_details for kw in ["21600", "30000", "30000元", "不一致", "超出", "算术", "计算", "预算", "矛盾"])),
        ("人数矛盾 (10人 vs 12人)", any(kw in all_details for kw in ["10", "12", "人数", "成员", "人数矛盾", "不一致"])),
        ("方法矛盾 (敏捷 vs 瀑布)", any(kw in all_details for kw in ["敏捷", "瀑布", "开发模式", "不一致", "矛盾", "冲突"])),
    ]

    passed = 0
    for name, result in checks:
        status = "PASS" if result else "FAIL"
        print(f"  [{status}] {name}")
        if result:
            passed += 1

    print(f"\n通过: {passed}/3")

    if passed == 3:
        print("\n全部检出! 可以更新软件。")
    else:
        print("\n未全部检出，需要继续迭代调整策略。")
        sys.exit(1)


if __name__ == "__main__":
    main()
