"""验证 think=false 是否能关闭思考链"""
import time
import httpx
import json
import re

TRANS = httpx.HTTPTransport(proxy=None)

# 测试 1: 不加 think 参数（对照）
# 测试 2: 加 think=false

for label, body_extra in [
    ("对照（无think参数）", {}),
    ("think=false", {"think": False}),
]:
    body = {
        "model": "qwen3.5:0.8b",
        "messages": [{"role": "user", "content": "句子：因为市场需求很大。输出 JSON 格式的 role/intent/relation。"}],
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512},
    }
    body.update(body_extra)

    start = time.time()
    with httpx.Client(transport=TRANS, timeout=120) as c:
        r = c.post("http://localhost:11434/api/chat", json=body)
    elapsed = time.time() - start
    data = r.json()
    msg = data.get("message", {})
    content = msg.get("content", "") or msg.get("thinking", "")

    has_thinking = "Thinking Process" in content or "分析" in content[:200]
    json_match = re.search(r"\{.*\}", content, re.DOTALL)

    print(f"\n{'='*50}")
    print(f"[{label}] 耗时 {elapsed:.1f}s")
    print(f"  输出长度: {len(content)} chars")
    print(f"  有思考链: {has_thinking}")
    print(f"  有JSON: {json_match is not None}")
    if json_match:
        print(f"  JSON: {json_match.group(0)[:120]}")
    print(f"  前100字: {content[:100]}")
    print(f"  eval_count: {data.get('eval_count')}")
    if data.get('eval_duration'):
        tok_s = data['eval_count'] / (data['eval_duration'] / 1e9)
        print(f"  速度: {tok_s:.1f} tok/s")
