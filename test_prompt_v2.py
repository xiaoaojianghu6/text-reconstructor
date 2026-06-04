"""找最稳定的 prompt 配方 — think=false + 清晰约束"""

import time
import httpx
import json
import re

TRANS = httpx.HTTPTransport(proxy=None)
BASE = "http://localhost:11434"

def chat(messages, label="", format_json=True):
    body = {
        "model": "qwen3.5:0.8b",
        "messages": messages,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.1, "num_predict": 200},
    }
    if format_json:
        body["format"] = "json"

    start = time.time()
    with httpx.Client(transport=TRANS, timeout=60) as c:
        r = c.post(f"{BASE}/api/chat", json=body)
    elapsed = time.time() - start
    data = r.json()
    content = data.get("message", {}).get("content", "")

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

    status = "✓" if parsed else "✗"
    print(f"{status} {label:<30} {elapsed:>4.1f}s  len={len(content):>3}", end="")
    if parsed:
        print(f"  role={parsed.get('role','?')}  intent={parsed.get('intent','?')}  relation={parsed.get('relation','?')}")
    else:
        print(f"  raw={content[:50]}")


sentences = [
    ("因为市场需求很大。", "cause"),    # 应有 relation=cause
    ("但是预算有限。", "contrast"),     # 应有 relation=contrast
    ("我们计划开发新产品。", "commissive"), # 应有 intent=commissive
    ("所以需要谨慎规划。", "directive"),  # 应有 intent=directive
    ("例如苹果手表投入了大量资源。", "evidence"), # 应有 relation=evidence
    ("总之这是一款好产品。", "summary"),  # 应有 relation=summary
]

# 配方 A: 英文 system + JSON format
print("\n--- 配方A: 英文 system + format=json ---")
system_a = "You are a JSON annotator for Chinese text. Output valid JSON with role, intent, relation fields. Only 3 keys."
for text, _ in sentences:
    chat(
        messages=[
            {"role": "system", "content": system_a},
            {"role": "user", "content": f'Sentence: "{text}"\nOutput: {{"role":"", "intent":"", "relation":""}}'},
        ],
        label=f"A: {text[:15]}",
    )

# 配方 B: 极其明确的 system（枚举所有可能值）
print("\n--- 配方B: 枚举所有可能值 ---")
system_b = """As a text annotation assistant, given a Chinese sentence, output:
- role: "nucleus" or "satellite"
- intent: "assertive", "directive", "commissive", "expressive", or "declaration"
- relation: "cause", "result", "evidence", "elaboration", "background", "condition", "purpose", "summary", "contrast", "concession", "sequence", "attribution", "evaluation", "restatement", or "none"

Example: {"role": "satellite", "intent": "assertive", "relation": "cause"}
Output ONLY the JSON."""
for text, _ in sentences:
    chat(
        messages=[
            {"role": "system", "content": system_b},
            {"role": "user", "content": text},
        ],
        label=f"B: {text[:15]}",
    )

# 配方 C: 把 schema 放进 user prompt（五句）
print("\n--- 配方C: schema 放在 user prompt ---")
system_c = "Output valid JSON only."
for text, _ in sentences:
    chat(
        messages=[
            {"role": "system", "content": system_c},
            {"role": "user", "content": f'{text}\n\nJSON: {{"role": "nucleus or satellite", "intent": "assertive/directive/commissive/expressive/declaration", "relation": "cause/result/evidence/elaboration/background/condition/purpose/summary/contrast/concession/sequence/attribution/evaluation/restatement/none"}}'},
        ],
        label=f"C: {text[:15]}",
    )

# 配方 D: 极简英文 prompt
print("\n--- 配方D: 极简英文 ---")
for text, expected in sentences:
    hint = ""
    if "因为" in text: hint = " (this is a reason)"
    elif "但是" in text: hint = " (this is contrast)"
    elif "计划" in text: hint = " (this is a plan/commitment)"
    elif "所以" in text: hint = " (this is a directive)"
    elif "例如" in text: hint = " (this is an example/evidence)"
    elif "总之" in text: hint = " (this is a summary)"
    chat(
        messages=[
            {"role": "user", "content": f'Classify: "{text}"{hint}\nJSON: role, intent, relation'},
        ],
        label=f"D: {text[:15]}",
    )
