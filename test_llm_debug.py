"""LLM 输出诊断 — 测试 Qwen3.5:0.8B 的 JSON 输出行为"""

import re
import json
import time
from text_reconstructor.llm import OllamaClient, LLMConfig

client = OllamaClient(LLMConfig(model="qwen3.5:0.8b", max_tokens=512, temperature=0.1))


def test(prompt, system="", label=""):
    print(f"\n{'='*50}")
    print(f"[{label}]")
    start = time.time()
    try:
        # 先试 chat_json
        r = client.chat_json(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=system or "只输出 JSON，不要任何思考过程。",
        )
        elapsed = time.time() - start
        print(f"  chat_json 成功 ({elapsed:.1f}s): {json.dumps(r, ensure_ascii=False)[:100]}")
        return r
    except Exception as e:
        elapsed = time.time() - start
        print(f"  chat_json 失败 ({elapsed:.1f}s): {str(e)[:100]}")
        # 回退: 用 chat + 正则提取
        try:
            resp = client.chat(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system or "只输出 JSON。",
            )
            content = resp.content
            print(f"  原始输出 ({len(content)} chars): {content[:150]}...")
            # 尝试提取 {}
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                print(f"  正则提取成功: {json.dumps(parsed, ensure_ascii=False)[:100]}")
                return parsed
            else:
                print("  无 JSON 可提取")
        except Exception as e2:
            print(f"  回退也失败: {str(e2)[:100]}")


# === 测试 1: 简洁 prompt + 强约束 ===
test(
    prompt='{"role": "...", "intent": "...", "relation": "..."}\n句子：因为市场需求很大。',
    system="只输出 JSON，不要任何思考过程。不要输出除 JSON 外的任何内容。",
    label="简洁 prompt + 强约束",
)

# === 测试 2: 超简洁 prompt (单行) ===
test(
    prompt='JSON: role(intent)(relation) for "因为市场需求很大。"',
    system="Reply with JSON only.",
    label="超简洁单行",
)

# === 测试 3: 把 JSON schema 放 system prompt ===
test(
    prompt='句子：因为市场需求很大。',
    system="""你是一个 JSON 标注器。对于给定的句子，输出 JSON: {"role":"nucleus/satellite","intent":"assertive/directive/commissive","relation":"cause/result/evidence/none"}。只输出 JSON，没有任何其他文字。""",
    label="Schema 放 system prompt",
)

# === 测试 4: 不加 format=json，直接请求 ===
print(f"\n{'='*50}")
print("[测试4: 不加 format=json]")
start = time.time()
try:
    resp = client.chat(
        messages=[{"role": "user", "content": "输出 JSON: 分析句子「因为市场需求很大」的 role/intent/relation"}],
        system_prompt="只输出 JSON 对象，不要任何思考过程。",
    )
    content = resp.content
    elapsed = time.time() - start
    print(f"  耗时 {elapsed:.1f}s")
    print(f"  原始输出: {content[:200]}")
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            print(f"  提取成功: {json.dumps(parsed, ensure_ascii=False)}")
        except:
            print("  JSON 解析失败")
    else:
        print("  无 JSON")
except Exception as e:
    print(f"  失败: {e}")
