"""综合优化测试：prompt 语言 + intent 后处理 + 速度"""

import time
import httpx
import json
import re

TRANS = httpx.HTTPTransport(proxy=None)
BASE = "http://localhost:11434"

SENTENCES = [
    ("我们计划开发一个新产品。", "commissive", "none"),
    ("因为市场需求很大。", "assertive", "cause"),
    ("所以需要谨慎规划。", "directive", "result"),
    ("但是预算有限。", "assertive", "contrast"),
    ("例如苹果手表投入了大量资源。", "assertive", "evidence"),
    ("总之这是一款好产品。", "assertive", "summary"),
    ("如果定价超过2000元会失去用户。", "assertive", "condition"),
    ("我们承诺在年底前交付。", "commissive", "none"),
    ("我觉得这个方案可行。", "assertive", "evaluation"),
    ("请立即执行这个计划。", "directive", "none"),
    ("说到品牌定位，我们的目标用户是年轻白领。", "assertive", "elaboration"),
    ("同时也要关注竞品动态。", "directive", "sequence"),
]


def chat_fast(prompt, system="", label="", max_tokens=200):
    """快速测试：纯 JSON 输出"""
    body = {
        "model": "qwen3.5:0.8b",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": max_tokens},
    }
    start = time.time()
    with httpx.Client(transport=TRANS, timeout=30) as c:
        r = c.post(f"{BASE}/api/chat", json=body)
    elapsed = time.time() - start
    data = r.json()
    content = data.get("message", {}).get("content", "")

    parsed = None
    try:
        parsed = json.loads(content)
    except:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        if m:
            try:
                parsed = json.loads(m.group(0))
            except:
                pass
    return parsed, elapsed, content


# ====================================================================
# 测试 1: 中英文 prompt 对比
# ====================================================================
print("=" * 60)
print("测试 1: 中英文 prompt 对比（12 句）")
print("=" * 60)

results_cn = []
results_en = []

# 中文 system
system_cn = """你是一个中文文本标注助手。分析句子并输出 JSON：
- role: "nucleus" 或 "satellite"
- intent: "assertive"(陈述事实/观点) | "directive"(请求/命令/建议) | "commissive"(承诺/保证/计划) | "expressive"(表达情感) | "declaration"(宣告)
- relation: "cause" | "result" | "evidence" | "elaboration" | "background" | "condition" | "purpose" | "summary" | "contrast" | "concession" | "sequence" | "attribution" | "evaluation" | "restatement" | "none"

只输出 JSON，不要其他内容。"""

# 英文 system（原版）
system_en = """You are a Chinese text annotation assistant. Given a Chinese sentence, output JSON with:
- role: "nucleus" or "satellite"
- intent: "assertive" | "directive" | "commissive" | "expressive" | "declaration"
- relation: "cause" | "result" | "evidence" | "elaboration" | "background" | "condition" | "purpose" | "summary" | "contrast" | "concession" | "sequence" | "attribution" | "evaluation" | "restatement" | "none"

Output ONLY the JSON object."""

for text, exp_intent, exp_rel in SENTENCES:
    # 中文 prompt
    p, t, _ = chat_fast(text, system_cn, max_tokens=150)
    intent_cn = p.get("intent", "?") if p else "?"
    rel_cn = p.get("relation", "?") if p else "?"
    results_cn.append((intent_cn, rel_cn, t))

    # 英文 prompt
    p, t, _ = chat_fast(text, system_en, max_tokens=150)
    intent_en = p.get("intent", "?") if p else "?"
    rel_en = p.get("relation", "?") if p else "?"
    results_en.append((intent_en, rel_en, t))

# 打印对比
print(f"{'句子':<30} {'期望intent':<14} {'EN-intent':<14} {'CN-intent':<14} {'EN-rel':<12} {'CN-rel':<12}")
print("-" * 96)
for i, (text, exp_intent, _) in enumerate(SENTENCES):
    en_i, en_r, t_en = results_en[i]
    cn_i, cn_r, t_cn = results_cn[i]
    print(f"{text[:28]:<30} {exp_intent:<14} {en_i:<14} {cn_i:<14} {en_r:<12} {cn_r:<12}")

avg_cn = sum(r[2] for r in results_cn) / len(results_cn)
avg_en = sum(r[2] for r in results_en) / len(results_en)
print(f"\n平均耗时: 中文 {avg_cn:.1f}s  英文 {avg_en:.1f}s")


# ====================================================================
# 测试 2: Intent 代码后处理规则
# ====================================================================
print("\n" + "=" * 60)
print("测试 2: Intent 代码后处理规则")
print("=" * 60)

# 定义 intent 推断规则
INTENT_RULES = [
    # 承诺/计划
    (re.compile(r"(计划|打算|准备|将要|承诺|保证|目标)"), "commissive"),
    (re.compile(r"(将|会)在.*(前|内)"), "commissive"),
    (re.compile(r"(我们|我).*(计划|目标|愿景)"), "commissive"),
    # 指令/建议
    (re.compile(r"^(请|需要|必须|应该|应当|建议|推荐)"), "directive"),
    (re.compile(r"(需要|应该|必须|得)"), "directive"),
    (re.compile(r"(请|让|要求)"), "directive"),
    # 表达情感
    (re.compile(r"(遗憾|高兴|担心|希望|失望|满意)"), "expressive"),
    # 宣告
    (re.compile(r"(宣布|宣告|任命)"), "declaration"),
]

def infer_intent_by_rules(text: str) -> str | None:
    """从信号词推断 intent"""
    for pattern, intent in INTENT_RULES:
        if pattern.search(text):
            return intent
    return None

# 对英文 prompt 的结果应用后处理
corrected = 0
for i, (text, exp_intent, _) in enumerate(SENTENCES):
    en_i = results_en[i][0]
    rule_i = infer_intent_by_rules(text)

    # 如果 LLM 输出不对且规则能推断
    if en_i != exp_intent and rule_i == exp_intent:
        corrected += 1
        marker = " ← 规则修正 ✓"
    elif en_i == exp_intent:
        marker = " LLM 正确 ✓"
    else:
        marker = f" (LLM={en_i})"

    print(f"  {text[:28]:<30} 期望={exp_intent:<12}{marker}")

print(f"\n规则修正能挽回 {corrected}/{len(SENTENCES)} 句的 intent")


# ====================================================================
# 测试 3: 缩短 prompt 对速度的影响
# ====================================================================
print("\n" + "=" * 60)
print("测试 3: prompt 长度 vs 速度")
print("=" * 60)

configs = [
    ("全量(8字段) max=512", system_en, 512),
    ("全量(8字段) max=128", system_en, 128),
    ("精简(3字段) max=64", "Classify sentence: role, intent, relation. Output JSON.", 64),
]

for label, sys_p, max_tok in configs:
    total_time = 0
    successes = 0
    for text, _, _ in SENTENCES[:6]:  # 只测前 6 句
        parsed, elapsed, content = chat_fast(text, sys_p, max_tokens=max_tok)
        total_time += elapsed
        if parsed:
            successes += 1
    avg = total_time / 6
    print(f"  {label:<25} 平均 {avg:.1f}s/句  成功率 {successes}/6")
