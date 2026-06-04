"""长文本全链路测试 — 模拟用户 700 字输入（Batch 模式）"""

import sys
import time
import json

sys.path.insert(0, "src")

from text_reconstructor.processor import (
    SentenceSplitter, WindowChunker, Tagger, ActiveBuffer,
)
from text_reconstructor.graph.updater import GraphUpdater
from text_reconstructor.llm import OllamaClient, LLMConfig


TEST_TEXT = """
我们公司最近在考虑推出一款面向年轻人的智能手表。因为现在健康管理越来越受重视，特别是25到35岁的上班族。但是我们的预算其实比较有限，可能只有300万左右。所以我们需要精打细算，把资源集中在最关键的功能上。

首先我觉得应该优先开发心率监测和睡眠分析功能。因为这两项是当前智能手表用户最常用的功能。例如苹果手表和华为手环都在这些方面投入了大量资源。而且这些功能的技术相对成熟，开发周期不会太长。

不过在产品定价上我们需要慎重考虑。如果定价超过2000元，可能会失去价格敏感的用户群。但是如果定价太低，又会影响品牌形象和利润空间。所以我觉得1500到1800元是一个比较合理的区间。

说到品牌定位，我认为我们的目标用户是追求性价比的年轻白领。这些人注重产品功能但不盲目追求高端品牌。所以我们的营销策略应该强调"专业健康管理"这个卖点。同时也可以和一些健身KOL合作推广。

但是竞争对手也在快速发展。小米已经推出了类似定位的产品，价格更低。华为的品牌影响力比我们大很多。所以我们的差异化优势应该体现在软件体验和健康数据分析的深度上。

总之我们需要的是一款功能扎实、价格合理、定位精准的产品。这个项目如果顺利的话，我们计划在年底前推出第一版。
"""


def run_pipeline(text: str, model: str = "qwen2.5:1.5b") -> dict:
    """执行全链路处理 (Batch 模式)"""

    # Step 1: 分句
    splitter = SentenceSplitter()
    sentences = splitter.split(text)
    print(f"\n{'='*60}")
    print(f"分句结果: {len(sentences)} 句")
    for i, s in enumerate(sentences):
        print(f"  [{i}] {s[:40]}{'...' if len(s) > 40 else ''}")

    # Step 2: Batch LLM 标注（单次调用处理所有句子）
    llm_client = OllamaClient(LLMConfig(
        model=model, max_tokens=2048, temperature=0.1, think=False,
    ))
    tagger = Tagger(llm_client=llm_client, enable_narrow=False)

    llm_start = time.time()
    chunks = tagger.batch_tag(sentences, timeout=300)
    llm_elapsed = time.time() - llm_start

    # 为 chunks 添加 chunk_index
    for i, c in enumerate(chunks):
        c["chunk_index"] = i

    print(f"\nLLM 标注完成: {len(chunks)} chunks, 耗时 {llm_elapsed:.1f}s")
    for i, c in enumerate(chunks):
        sig = ""
        if c.get("_corrected"):
            sig += " [R]"
        if c.get("_intent_corrected"):
            sig += " [I]"
        if c.get("_scope_inferred"):
            sig += " [S]"
        if c.get("_pronoun_warning"):
            sig += " [P]"
        scope = f" [{c.get('scope','')}]" if c.get("scope") else ""
        print(f"  [{i:2d}] role={c['role']:9s} intent={c['intent']:12s} "
              f"relation={c['relation']:15s}{sig}{scope}")

    # Step 3: Active Buffer（可选 — 用于长文本上下文追踪）
    buffer = ActiveBuffer(max_size=20)
    for c in chunks:
        buffer.add(
            text=c["text"],
            role=c.get("role", "satellite"),
            relation=c.get("relation", "none"),
            scope=c.get("scope", ""),
        )
        dep = c.get("dependency", "")
        if dep and dep not in ("", "REFERENCE_MISSING"):
            buffer.reference(dep)

    # Step 4: GraphUpdater 建图
    updater = GraphUpdater()
    snapshot = updater.process(chunks)

    return {
        "sentences": sentences,
        "chunks": chunks,
        "snapshot": snapshot,
        "buffer_stats": {"buffer_size": buffer.size()},
        "llm_time": llm_elapsed,
    }


def print_results(result: dict):
    """打印测试结果"""
    snap = result["snapshot"]
    nodes = snap["nodes"]
    edges = snap["edges"]
    alerts = snap["alerts"]

    print(f"\n{'='*60}")
    print(f"图谱统计")
    print(f"{'='*60}")
    print(f"  节点数: {len(nodes)}")
    print(f"  边数:   {len(edges)}")
    print(f"  Alerts: {len(alerts)}")

    # 边类型统计
    edge_types = {}
    for e in edges:
        et = e["edge_type"]
        edge_types[et] = edge_types.get(et, 0) + 1
    print(f"\n边类型分布:")
    for et, count in sorted(edge_types.items(), key=lambda x: -x[1]):
        print(f"  {et}: {count}")

    if alerts:
        print(f"\n对抗机警报:")
        for a in alerts:
            print(f"  [{a['severity'].upper()}] {a['type']} "
                  f"(x{a.get('count', 1)})")
            print(f"    节点: [{a.get('node_id', 'N/A')}] {a.get('text', '')[:30]}")
            print(f"    详情: {a.get('detail', '')[:60]}")

    # 节点详情
    if nodes:
        confs = [n["confidence"] for n in nodes]
        low = sum(1 for c in confs if c < 0.5)
        mid = sum(1 for c in confs if 0.5 <= c < 0.7)
        high = sum(1 for c in confs if c >= 0.7)
        print(f"\n节点置信度分布:")
        print(f"  低 (<0.5):  {low}")
        print(f"  中 (0.5-0.7): {mid}")
        print(f"  高 (>=0.7): {high}")

        roles = {}
        for n in nodes:
            r = n.get("role", "unknown")
            roles[r] = roles.get(r, 0) + 1
        print(f"\n角色分布:")
        for r, c in sorted(roles.items()):
            print(f"  {r}: {c}")

        scopes = {}
        for n in nodes:
            s = n.get("scope", "") or "(无)"
            scopes[s] = scopes.get(s, 0) + 1
        print(f"\n主题域(scope)分布:")
        for s, c in sorted(scopes.items(), key=lambda x: -x[1]):
            print(f"  {s}: {c}")

        print(f"\n节点详情:")
        for n in nodes:
            rel = n.get("relation", "none")
            sig = " [R]" if n.get("_corrected") else ""
            sig += " [I]" if n.get("_intent_corrected") else ""
            sig += " [S]" if n.get("_scope_inferred") else ""
            pron = " [P]" if n.get("_pronoun_warning") else ""
            scope = f" [{n.get('scope','')}]" if n.get("scope") else ""
            print(f"  [{n['id']:2d}] {n['text'][:35]:35s} "
                  f"role={n['role']:10s} intent={n['intent']:12s} "
                  f"relation={rel:10s}{sig}{pron}{scope}")


if __name__ == "__main__":
    print(f"输入文本长度: {len(TEST_TEXT)} 字符")
    print(f"{'='*60}")

    result = run_pipeline(TEST_TEXT, model="qwen2.5:1.5b")
    print_results(result)
