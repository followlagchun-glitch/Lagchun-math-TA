from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

SYSTEM_PROMPT = """
You are LC Sir - Hong Kong DSE Math Tutor.
Answer in HK Cantonese 口語, formulas in English.
Use Step 1, Step 2, Step 3 format, short and clear.
"""

# ===== 最新可用 Models (Fix 404) =====
MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-pro"
]

def get_image_base64(data):
    print(f"DEBUG get_image_base64 called")
    try:
        url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        r = requests.post(url, json=data, headers=headers, timeout=30)
        print(f"getBase64 -> {r.status_code} {r.text[:800]}")
        if r.status_code == 200:
            j = r.json()
            b64 = j.get("base64") or j.get("data") or j.get("result", {}).get("base64")
            if b64:
                if "," in b64: b64 = b64.split(",")[-1]
                if len(b64) > 1000:
                    return b64
    except Exception as e:
        print(f"getBase64 error {e}")
    return None

def call_gemini(question, image_b64=None):
    prompt = SYSTEM_PROMPT + f"\n學生問題: {question}"
    last_error = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts = [{"text": prompt}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
        body = {"contents": [{"role": "user", "parts": parts}]}
        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            print(f"TRY {model} -> {r.status_code}")
            if r.status_code == 200:
                j = r.json()
                return j["candidates"][0]["content"]["parts"][0]["text"], "ok", ""
            last_error = r.text
            if r.status_code != 404: # 如果唔係 404，就唔好試下一個，係真 error
                print(f"Error {r.text[:500]}")
        except Exception as e:
            last_error = str(e)
            continue
    return f"❌ Real error: {last_error[:1500]}", "error", last_error

def send_text(jid, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    requests.post(url, json={"number": jid, "text": text}, headers=headers, timeout=20)

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
        b64 = get_image_base64(data)
        caption = msg["imageMessage"].get("caption") or ""
        text = caption or text or "幫我逐步計呢題"
    if not text and not b64: text = "1+3"
    answer, _, _ = call_gemini(text, b64)
    send_text(jid, answer[:3500])
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home():
    return f"Bot Live MODELS={MODELS[0]}", 200
