"""测试优化后的 prompt，配合 think=false"""

import time
import httpx
import json
import re

TRANS = httpx.HTTPTransport(proxy=None)
BASE = "http://localhost:11434"

def chat(prompt, system="", label="", format_json=False):
    body = {
        "model": "qwen3.5:0.8b",
        "messages": [],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.1, "num_predict": 256},
    }
    if system:
        body["messages"].append({"role": "system", "content": system})
    body["messages"].append({"role": "user", "content": prompt})
    if format_json:
        body["format"] = "json"

    start = time.time()
    with httpx.Client(transport=TRANS, timeout=60) as c:
        r = c.post(f"{BASE}/api/chat", json=body)
    elapsed = time.time() - start
    data = r.json()
    content = data.get("message", {}).get("content", "")

    # 尝试解析 JSON
    parsed = None
    try:
        parsed = json.loads(content)
    except:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group(0))
            except:
                pass

    print(f"\n{'='*50}")
    print(f"[{label}] {elapsed:.1f}s ({len(content)} chars)")
    if parsed:
        print(f"  JSON: {json.dumps(parsed, ensure_ascii=False, indent=2)}")
    else:
        print(f"  原始: {content[:120]}")

# === 测试 1: 英文 schema（历史原因，Qwen 对英文理解更好）===
chat(
    system="You are a text annotation assistant. Output ONLY valid JSON. No other text.",
    prompt='''Analyze this Chinese sentence and output JSON:
Sentence: "因为市场需求很大。"
{
  "role": "nucleus or satellite",
  "intent": "assertive, directive, commissive, expressive, or declaration",
  "relation": "cause, result, evidence, elaboration, background, condition, purpose, summary, contrast, concession, sequence, attribution, evaluation, restatement, or none"
}''',
    label="英文schema+think=false",
    format_json=True,
)

# === 测试 2: 中文 schema（更直白）===
chat(
    system="只输出 JSON，不要任何其他内容。",
    prompt='''分析句子并输出 JSON：
句子：因为市场需求很大。

可选值：
role: "nucleus"（核心）或 "satellite"（辅助）
intent: "assertive"（陈述）| "directive"（指令）| "commissive"（承诺）| "expressive"（表达）| "declaration"（宣告）
relation: "cause"（原因）| "result"（结果）| "evidence"（证据）| "elaboration"（阐述）| "background"（背景）| "condition"（条件）| "purpose"（目的）| "summary"（总结）| "contrast"（对比）| "concession"（让步）| "sequence"（时序）| "attribution"（归因）| "evaluation"（评价）| "restatement"（重申）| "none"（无）

JSON:
{
  "role": "...",
  "intent": "...",
  "relation": "..."
}''',
    label="中文schema+think=false",
    format_json=True,
)

# === 测试 3: 超简洁 + JSON format ===
chat(
    prompt='''{"role": "nucleus/satellite", "intent": "assertive/directive/commissive", "relation": "cause/contrast/evidence"}
句子：因为市场需求很大。''',
    label="超简洁+format=json",
    format_json=True,
)

# === 测试 4: 多句测试第一句 ===
test_sentences = [
    "我们公司最近在考虑推出一款面向年轻人的智能手表。",
    "因为现在健康管理越来越受重视，特别是25到35岁的上班族。",
    "但是我们的预算其实比较有限，可能只有300万左右。",
    "总之我们需要的是一款功能扎实、价格合理、定位精准的产品。",
]

for i, s in enumerate(test_sentences):
    chat(
        system="你是一个文本标注助手。只输出 JSON。不要思考过程。",
        prompt=f'''句子：{s}
输出 JSON: role(intent)(relation) 三个字段。''',
        label=f"句{i}",
        format_json=True,
    )
