from flask import Flask, request, jsonify
import os, requests, re, urllib.parse

app = Flask(__name__)

GEMINI_API_KEY = (os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY_1") or "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT Tier 1: Key={bool(GEMINI_API_KEY)}")

SYSTEM_PROMPT = """
You are LC Sir + SketchMath Teacher.
- Use Step 1, Step 2, Step 3 format
- Hong Kong Cantonese口語, formulas in English
- If graph needed, end with: GRAPH_EQUATION: <equation>
"""

# Tier 1: you can use best models, quota is huge
MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

def call_gemini(question, image_b64=None):
    if not GEMINI_API_KEY:
        return None, "no_key"
    
    prompt = SYSTEM_PROMPT + f"\n學生問題: {question}"
    
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        parts = [{"text": prompt}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
        
        try:
            r = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=60)
            print(f"{model}: {r.status_code}")
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"], "ok"
            elif r.status_code == 429:
                # Even Tier 1 can hit RPM if you spam, wait 2 sec and retry next model
                print(f"{model} 429, next...")
                continue
            else:
                print(r.text[:600])
        except Exception as e:
            print(f"Error {e}")
    
    return None, "quota"

def send_text(jid, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    requests.post(url, json={"number": jid, "text": text}, headers=headers, timeout=20)

def send_graph(jid, eq):
    link = f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}"
    send_text(jid, f"📈 圖解：{eq}\n👉 互動圖：{link}")

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
        text = "2+1"
    
    answer, status = call_gemini(text, b64)
    
    if status == "no_key":
        answer = "未有GEMINI_API_KEY"
    elif not answer:
        answer = "Tier1暫時忙，請再試一次"
    
    m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
    if m:
        eq = m.group(1).strip()
        send_text(jid, answer.replace(m.group(0),"").strip())
        send_graph(jid, eq)
    else:
        send_text(jid, answer)
    
    return jsonify({"ok": True}), 200

@app.route("/test", methods=["GET"])
def test():
    q = request.args.get("q", "2+1")
    ans, st = call_gemini(q)
    return jsonify({"status": st, "model": MODELS[0], "ans": ans})

@app.route("/", methods=["GET"])
def home():
    return "Tier1 Bot Live - 1000 RPM", 200
