#!/usr/bin/env python3
import sys
import os
import json
import urllib.request
import urllib.error

LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://192.168.0.50:1234/v1/chat/completions")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

def call_ai(system_prompt, user_prompt, model="default", temperature=0.2, max_tokens=1500):
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    # 1. Try LM Studio first (Primary)
    try:
        payload = {
            "model": model,  # uses currently loaded model in LM Studio
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        req = urllib.request.Request(
            LM_STUDIO_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"]
            if content and content.strip():
                return {"text": content.strip(), "provider": "lm_studio", "error": None}
    except Exception:
        pass

    # 2. Fallback to OpenRouter (Secondary)
    if OPENROUTER_API_KEY:
        try:
            payload = {
                "model": "openai/gpt-oss-20b:free",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            req = urllib.request.Request(
                OPENROUTER_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}"
                }
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                content = res_data["choices"][0]["message"]["content"]
                if content and content.strip():
                    return {"text": content.strip(), "provider": "openrouter_fallback", "error": None}
        except Exception as or_err:
            return {"text": "", "provider": "failed", "error": f"LM Studio and OpenRouter both failed: {str(or_err)}"}

    return {"text": "", "provider": "failed", "error": "No response returned"}

if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys_p = sys.argv[1]
        usr_p = sys.argv[2]
        res = call_ai(sys_p, usr_p)
        print(json.dumps(res))
    elif len(sys.argv) > 1:
        usr_p = sys.argv[1]
        res = call_ai("", usr_p)
        print(json.dumps(res))
    else:
        print(json.dumps({"error": "No prompt provided"}))
