from flask import Flask, request, jsonify
import os, requests, re, urllib.parse

app = Flask(__name__)

# Accept BOTH AIza and AQ. - no prefix check
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT: key_len={len(GEMINI_API_KEY)} prefix={GEMINI_API_KEY[:3] if GEMINI_API_KEY else 'NONE'}")

SYSTEM_PROMPT = """
You are LC Sir + SketchMath Teacher.
- Use Step 1, Step 2, Step 3 format
- Hong Kong Cantonese口語, formulas in English
- If graph needed, end with: GRAPH_EQUATION: <equation>
"""

MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

def call_gemini(question, image_b64=None):
    if not GEMINI_API_KEY or len(GEMINI_API_KEY) < 20:
        return f"❌ Render GEMINI_API_KEY is empty or too short (len={len(GEMINI_API_KEY)}). Go to Render>Environment paste full key (AQ. or AIza).", "no_key"

    prompt = SYSTEM_PROMPT + f"\n學生問題: {question}"

    for model in MODELS:
        # AQ. keys work with both ?key= and x-goog-api-key header
        # Use header method for better compatibility
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY  # Works for AQ. keys
        }
        parts = [{"text": prompt}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})

        try:
            # Try with header (for AQ.), fallback to ?key= param
            r = requests.post(url, json={"contents": [{"parts": parts}]}, headers=headers, timeout=60)
            
            # If 401, try ?key= method
            if r.status_code == 401:
                print(f"Trying ?key= fallback for {model}")
                url2 = f"{url}?key={GEMINI_API_KEY}"
                r = requests.post(url2, json={"contents": [{"parts": parts}]}, timeout=60)

            print(f"{model} -> {r.status_code} {r.text[:300]}")

            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"], "ok"
            elif r.status_code == 429:
                continue
            else:
                # Show real error
                last_err = f"{model} {r.status_code}: {r.text[:500]}"
                print(last_err)
                if r.status_code in [400, 403, 401]:
                    continue
        except Exception as e:
            print(f"Req err {e}")
            continue

    return f"❌ Gemini error: Check key is valid AQ. key from https://aistudio.google.com/app/apikey . Current len={len(GEMINI_API_KEY)} prefix={GEMINI_API_KEY[:3]}", "error"

def send_text(jid, text):
    if not EVOLUTION_API_URL:
        return
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        requests.post(url, json={"number": jid, "text": text}, headers=headers, timeout=20)
    except Exception as e:
        print(f"Send err {e}")

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
        text = msg["imageMessage"].get("caption") or text or "幫我逐步計呢題"

    if not text:
        text = "1+3"

    answer, status = call_gemini(text, b64)
    m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
    if m:
        eq = m.group(1).strip()
        send_text(jid, answer.replace(m.group(0), "").strip())
        send_text(jid, f"📈 圖：{eq}\nhttps://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}")
    else:
        send_text(jid, answer)

    return jsonify({"ok": True}), 200

@app.route("/test", methods=["GET"])
def test():
    q = request.args.get("q", "1+3")
    ans, st = call_gemini(q)
    return jsonify({"status": st, "key_len": len(GEMINI_API_KEY), "key_prefix": GEMINI_API_KEY[:5] if GEMINI_API_KEY else "", "question": q, "answer": ans})

@app.route("/", methods=["GET"])
def home():
    return f"Final AQ-ready Bot - key_len={len(GEMINI_API_KEY)} - /test?q=1%2B3", 200
