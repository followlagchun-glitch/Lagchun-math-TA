from flask import Flask, request, jsonify
import os, requests, re, urllib.parse

app = Flask(__name__)

# Your AQ. key - 53 chars, starts with AQ.
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ: loaded len={len(GEMINI_API_KEY)} prefix={GEMINI_API_KEY[:3] if GEMINI_API_KEY else 'EMPTY'}")

SYSTEM_PROMPT = """
You are LC Sir - Hong Kong DSE Math Tutor.
Answer in HK Cantonese 口語, formulas in English.
Use Step 1, Step 2, Step 3 format, short and clear.
If graph needed, end with: GRAPH_EQUATION: <equation>
"""

# 2.0 is dead (June 2026) - Use 2.5 family only, these work with AQ. keys
MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro"
]

def call_gemini(question, image_b64=None):
    if len(GEMINI_API_KEY) < 20:
        return f"❌ GEMINI_API_KEY empty in Render (len={len(GEMINI_API_KEY)})", "no_key"

    prompt = SYSTEM_PROMPT + f"\n學生問題: {question}"

    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY  # AQ. keys MUST use this header
        }
        
        parts = [{"text": prompt}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
        
        body = {"contents": [{"role": "user", "parts": parts}]}

        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            print(f"TRY {model} -> {r.status_code}")

            # If header fails, try ?key= fallback (also works for AQ.)
            if r.status_code in [401, 403]:
                print(f"Header failed, trying ?key= for {model}")
                r2 = requests.post(
                    f"{url}?key={GEMINI_API_KEY}",
                    json=body,
                    headers={"Content-Type": "application/json"},
                    timeout=90
                )
                print(f"Fallback {model} -> {r2.status_code} {r2.text[:500]}")
                if r2.status_code == 200:
                    r = r2
                else:
                    r = r2  # keep error for logging

            if r.status_code == 200:
                j = r.json()
                text = j["candidates"][0]["content"]["parts"][0]["text"]
                return text, "ok"
            else:
                print(f"FAIL {model}: {r.text[:1000]}")
                if r.status_code == 429:
                    continue
                # Don't return immediately, try next model
                continue

        except Exception as e:
            print(f"EXC {model}: {e}")
            continue

    return "❌ AQ. key rejected. 去 https://aistudio.google.com/ 檢查 Billing 是否已加信用卡，及 https://console.cloud.google.com/apis/library/generativelanguage.googleapis.com 按 Enable", "error"

def send_text(jid, text):
    if not EVOLUTION_API_URL or not EVOLUTION_INSTANCE:
        print("No Evolution config")
        return
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        requests.post(url, json={"number": jid, "text": text}, headers=headers, timeout=20)
    except Exception as e:
        print(f"Send fail: {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json or {}
    data = body.get("data", {})
    key = data.get("key", {})
    msg = data.get("message", {})
    jid = key.get("remoteJid")

    if not jid or "@g.us" in jid or key.get("fromMe"):
        return jsonify({"ok": True}), 200

    text = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    b64 = None
    if "imageMessage" in msg:
        b64 = msg["imageMessage"].get("base64") or data.get("message", {}).get("base64")
        caption = msg["imageMessage"].get("caption") or ""
        text = caption or text or "幫我逐步計呢題"

    if not text and not b64:
        text = "1+3"

    answer, status = call_gemini(text, b64)

    m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
    if m:
        eq = m.group(1).strip()
        clean = answer.replace(m.group(0), "").strip()
        send_text(jid, clean)
        link = f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}"
        send_text(jid, f"📈 互動圖：{eq}\n{link}")
    else:
        send_text(jid, answer)

    return jsonify({"ok": True}), 200

@app.route("/test", methods=["GET"])
def test():
    q = request.args.get("q", "1+3")
    ans, st = call_gemini(q)
    return jsonify({
        "status": st,
        "key_len": len(GEMINI_API_KEY),
        "key_prefix": GEMINI_API_KEY[:4],
        "question": q,
        "answer": ans
    })

@app.route("/", methods=["GET"])
def home():
    return f"AQ Bot Live - len={len(GEMINI_API_KEY)} prefix={GEMINI_API_KEY[:3]} - /test?q=1%2B3", 200
