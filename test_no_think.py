"""测试关闭 Qwen3.5 思考链的方法"""
import time
import json
import re
import httpx

BASE = "http://localhost:11434"
TRANS = httpx.HTTPTransport(proxy=None)


def chat(body, label="", timeout=120):
    start = time.time()
    with httpx.Client(transport=TRANS, timeout=timeout) as c:
        r = c.post(f"{BASE}/api/chat", json=body)
    elapsed = time.time() - start
    data = r.json()
    msg = data.get("message", {})
    content = msg.get("content", "") or msg.get("thinking", "")
    # 提取 JSON
    json_match = re.search(r"\{.*\}", content, re.DOTALL)
    return {
        "label": label,
        "elapsed": round(elapsed, 1),
        "content_len": len(content),
        "eval_count": data.get("eval_count", 0),
        "has_thinking": content.startswith("Thinking") or content.startswith("好的"),
        "has_json": json_match is not None,
        "json_extracted": json_match.group(0)[:100] if json_match else None,
        "preview": content[:80],
    }


results = []

# === 方法1: 默认行为（对照）===
results.append(chat({
    "model": "qwen3.5:0.8b",
    "messages": [{"role": "user", "content": "句子：因为市场需求很大。输出json：role,intent,relation。"}],
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 512},
}, label="1-对照：默认行为"))

# === 方法2: stop 参数截断思考 ===
results.append(chat({
    "model": "qwen3.5:0.8b",
    "messages": [{"role": "user", "content": "句子：因为市场需求很大。输出 JSON。"}],
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 512,
                "stop": ["\n\n", "Thought", "think"]},
}, label="2-stop截断"))

# === 方法3: 强制 JSON format（Ollama 的 format）===
results.append(chat({
    "model": "qwen3.5:0.8b",
    "messages": [{"role": "user", "content": '{"role": "nucleus/satellite", "intent": "assertive/directive/commissive", "relation": "cause/contrast/evidence/none"} 句子：因为市场需求很大。'}],
    "stream": False,
    "format": "json",
    "options": {"temperature": 0.1, "num_predict": 512},
}, label="3-json format"))

# === 方法4: 极短 prompt ===
results.append(chat({
    "model": "qwen3.5:0.8b",
    "messages": [{"role": "user", "content": "JSON: 因为市场需求很大。"}],
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 200},
}, label="4-极短prompt"))

# === 方法5: system 强约束 ===
results.append(chat({
    "model": "qwen3.5:0.8b",
    "messages": [
        {"role": "system", "content": "CRITICAL: You MUST NOT output any thinking process. Output ONLY a JSON object."},
        {"role": "user", "content": "句子：因为市场需求很大。输出 JSON。"},
    ],
    "stream": False,
    "options": {"temperature": 0.1, "num_predict": 200},
}, label="5-system强约束"))

# 结果汇总
print(f"\n{'='*60}")
print(f"{'方法':<20} {'耗时':>6} {'长度':>6} {'思考链':>6} {'有JSON':>8}")
print(f"{'-'*60}")
for r in results:
    print(f"{r['label']:<20} {r['elapsed']:>5.1f}s {r['content_len']:>6} {str(r['has_thinking']):>6} {str(r['has_json']):>8}")
    if r['has_json']:
        print(f"  → {r['json_extracted']}")
    print(f"  首80字: {r['preview']}")
