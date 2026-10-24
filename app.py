from flask import Flask, request, jsonify
import os, requests, re, urllib.parse

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ: loaded len={len(GEMINI_API_KEY)} prefix={GEMINI_API_KEY[:4]}")

SYSTEM_PROMPT = """
You are LC Sir - Hong Kong DSE Math Tutor.
Answer in HK Cantonese 口語, formulas in English.
Use Step 1, Step 2, Step 3 format, short and clear.
If graph needed, end with: GRAPH_EQUATION: <equation>
"""

# NEW models Oct 2026 — 3.1 Pro + 3.8 Flash — these work with AQ keys
MODELS = [
    "gemini-3.1-pro-preview",      # <-- Google told you to use this in screenshot
    "gemini-3.1-pro",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash-lite"        # fallback
]

def call_gemini(question, image_b64=None):
    if len(GEMINI_API_KEY) < 20:
        return f"❌ KEY empty len={len(GEMINI_API_KEY)}", "no_key", "empty"

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
            print(f"TRY {model} header -> {r.status_code} {r.text[:800]}")
            
            # Fallback ?key=
            if r.status_code in [401, 403]:
                r = requests.post(f"{url}?key={GEMINI_API_KEY}", json=body, headers={"Content-Type":"application/json"}, timeout=90)
                print(f"Fallback {model} ?key -> {r.status_code} {r.text[:800]}")

            if r.status_code == 200:
                j = r.json()
                text = j["candidates"][0]["content"]["parts"][0]["text"]
                return text, "ok", ""
            
            last_error = r.text  # Save real Google error
            
            if r.status_code == 429:
                continue
            continue

        except Exception as e:
            last_error = str(e)
            print(f"EXC {model}: {e}")
            continue

    # Return REAL Google error so you can see it
    return f"❌ Real error: {last_error[:1500]}", "error", last_error

def send_text(jid, text):
    if not EVOLUTION_API_URL or not EVOLUTION_INSTANCE: return
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        requests.post(url, json={"number": jid, "text": text}, headers=headers, timeout=20)
    except Exception as e:
        print(f"Send fail: {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json or {}
    data = body.get("data", {}); key = data.get("key", {}); msg = data.get("message", {}); jid = key.get("remoteJid")
    if not jid or "@g.us" in jid or key.get("fromMe"): return jsonify({"ok": True}), 200
    text = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    b64 = None
    if "imageMessage" in msg:
        b64 = msg["imageMessage"].get("base64") or data.get("message", {}).get("base64")
        text = msg["imageMessage"].get("caption") or text or "幫我逐步計呢題"
    if not text and not b64: text = "1+3"
    answer, status, _ = call_gemini(text, b64)
    m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
    if m:
        eq = m.group(1).strip(); clean = answer.replace(m.group(0), "").strip()
        send_text(jid, clean)
        link = f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}"
        send_text(jid, f"📈 互動圖：{eq}\n{link}")
    else:
        send_text(jid, answer[:3000])
    return jsonify({"ok": True}), 200

@app.route("/test", methods=["GET"])
def test():
    q = request.args.get("q", "1+3")
    ans, st, full_err = call_gemini(q)
    return jsonify({"status": st, "key_len": len(GEMINI_API_KEY), "key_prefix": GEMINI_API_KEY[:4], "question": q, "answer": ans, "full_error": full_err[:2000]})

@app.route("/", methods=["GET"])
def home():
    return f"AQ Bot Live len={len(GEMINI_API_KEY)} prefix={GEMINI_API_KEY[:4]} /test?q=1%2B3", 200
