"""集成测试入口 — 输入文本，观察全流程输出"""
import sys
from text_reconstructor.processor.chunker import SentenceSplitter
from text_reconstructor.processor.tagger import Tagger
from text_reconstructor.graph.updater import GraphUpdater
from text_reconstructor.output.text_output import TextOutput
from text_reconstructor.output.llm_refiner import LLMRefiner
from text_reconstructor.output.suggestions import Suggestions


def show_graph_stats(snapshot):
    nodes = snapshot.get("nodes", [])
    edges = snapshot.get("edges", [])
    scopes = sorted({n.get("scope", "") for n in nodes if n.get("scope")})
    print(f"\n=== 语义图谱统计 ===")
    print(f"  节点数: {len(nodes)}")
    print(f"  边数:   {len(edges)}")
    print(f"  域:     {scopes}")
    for n in nodes:
        e_out = sum(1 for e in edges if e["source_id"] == n["id"])
        e_in = sum(1 for e in edges if e["target_id"] == n["id"])
        print(f"  [{n['id']}] '{n['text'][:20]}'"
              f" conf={n['confidence']:.2f}"
              f" role={n['role']} scope={n['scope']}"
              f" out={e_out} in={e_in}")
    for e in edges:
        s_text = next((n['text'][:15] for n in nodes if n['id'] == e['source_id']), "?")
        t_text = next((n['text'][:15] for n in nodes if n['id'] == e['target_id']), "?")
        print(f"    {s_text} --[{e['edge_type']}]--> {t_text}")


def run_pipeline(text: str, skip_adversary: bool = False):
    print(f"{'='*60}")
    print(f"输入文本: {text}")
    print(f"{'='*60}")

    # Step 1: 句子分割
    splitter = SentenceSplitter()
    sentences = splitter.split(text)
    print(f"\n--- 1. 句子分割 ({len(sentences)} 句) ---")
    for i, s in enumerate(sentences):
        print(f"  [{i}] {s}")

    # Step 2: LLM 标注
    tagger = Tagger()
    print(f"\n--- 2. LLM 标注 (调用 qwen3.5:0.8B) ---")
    chunks = tagger.batch_tag(sentences)
    for i, c in enumerate(chunks):
        extra = ""
        if c.get("_corrected"):
            extra += " [信号纠正]"
        if c.get("_intent_corrected"):
            extra += " [意图纠正]"
        print(f"  [{i}] '{c['text']}':"
              f" role={c['role']} intent={c['intent']}"
              f" rel={c['relation']} scope={c['scope']}"
              f" arg_role={c['argument_role']} arg_rel={c['argument_relation']}"
              f"{extra}")

    # Step 3: 图谱构建
    mode = "含对抗机" if not skip_adversary else "跳过对抗机"
    print(f"\n--- 3. 语义图谱构建 ({mode}) ---")
    updater = GraphUpdater(run_adversary=not skip_adversary)
    snapshot = updater.process(chunks)
    show_graph_stats(snapshot)

    # Step 4: 结构化输出
    print(f"\n--- 4a. LLM 重构输出 (默认) ---")
    try:
        refined = LLMRefiner().refine(snapshot)
        print(refined)
    except Exception as e:
        print(f"  [LLMRefiner 失败: {e}]")

    print(f"\n--- 4b. 模板输出 (对比) ---")
    text_out = TextOutput().format(snapshot)
    print(text_out)

    # Step 5: 改进建议
    alerts = snapshot.get("alerts", [])
    if alerts:
        print(f"--- 5. 改进建议 ({len(alerts)} 条) ---")
        for s in Suggestions().format(alerts):
            print(s)
    else:
        print("--- 5. 改进建议: 无 (结构良好) ---")

    print(f"{'='*60}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
    else:
        text = (
            "因为市场需求很大，所以我们的产品销量在持续增长。"
            "但是预算有限，因此我们只能先聚焦核心功能。"
            "虽然竞争对手也在快速跟进，不过我们有自己的技术优势。"
        )
    run_pipeline(text)
