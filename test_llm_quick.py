"""快速测试：Ollama 推理链路耗时分布"""
import time
import httpx
import json

# 测试 Ollama 原始延迟（不含模型推理）
start = time.time()
with httpx.Client(transport=httpx.HTTPTransport(proxy=None)) as c:
    r = c.get("http://localhost:11434")
print(f"Ollama 服务 ping: {(time.time()-start)*1000:.0f}ms")

# 测试一次简单 prompt 的各阶段耗时
body = {
    "model": "qwen3.5:0.8b",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": False,
    "options": {"num_predict": 10, "temperature": 0.1},
}
start = time.time()
with httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=30) as c:
    r = c.post("http://localhost:11434/api/chat", json=body)
elapsed = time.time() - start
data = r.json()
msg = data.get("message", {})
print(f"\n最短推理 (生成10 tokens):")
print(f"  总耗时: {elapsed:.2f}s")
print(f"  prompt_eval_count: {data.get('prompt_eval_count')}")
print(f"  eval_count: {data.get('eval_count')}")
print(f"  total_duration: {data.get('total_duration', 0) / 1e9:.2f}s")
print(f"  prompt_eval_duration: {data.get('prompt_eval_duration', 0) / 1e9:.2f}s")
print(f"  eval_duration: {data.get('eval_duration', 0) / 1e9:.2f}s")
if data.get('eval_duration'):
    tok_s = data['eval_count'] / (data['eval_duration'] / 1e9)
    print(f"  生成速度: {tok_s:.1f} tok/s")
print(f"  输出: {msg.get('content', '')[:60]}")

# 测试中等 prompt 的推理速度
body2 = {
    "model": "qwen3.5:0.8b",
    "messages": [
        {"role": "system", "content": "你是一个标注助手。"},
        {"role": "user", "content": "分析句子：因为市场需求很大。输出 JSON 格式的 role/intent/relation。"},
    ],
    "stream": False,
    "options": {"num_predict": 100, "temperature": 0.1},
}
start = time.time()
with httpx.Client(transport=httpx.HTTPTransport(proxy=None), timeout=120) as c:
    r = c.post("http://localhost:11434/api/chat", json=body2)
elapsed = time.time() - start
data = r.json()
print(f"\n带思考链推理 (~100 tokens):")
print(f"  总耗时: {elapsed:.2f}s")
print(f"  prompt_eval_count: {data.get('prompt_eval_count')}")
print(f"  eval_count: {data.get('eval_count')}")
if data.get('eval_duration'):
    tok_s = data['eval_count'] / (data['eval_duration'] / 1e9)
    print(f"  生成速度: {tok_s:.1f} tok/s")
print(f"  total_duration: {data.get('total_duration', 0) / 1e9:.2f}s")
print(f"  prompt_eval_duration: {data.get('prompt_eval_duration', 0) / 1e9:.2f}s")
print(f"  eval_duration: {data.get('eval_duration', 0) / 1e9:.2f}s")
