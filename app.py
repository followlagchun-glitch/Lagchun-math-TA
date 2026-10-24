from flask import Flask, request, jsonify
import os, requests, re, urllib.parse

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT Final: GEMINI_API_KEY present={bool(GEMINI_API_KEY)}")

SYSTEM_PROMPT = """
You are LC Sir + SketchMath Teacher.
- Use Step 1, Step 2, Step 3 format
- Hong Kong Cantonese口語, formulas in English
- If graph needed, end with: GRAPH_EQUATION: <equation>
"""

MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

def call_gemini(question, image_b64=None):
    if not GEMINI_API_KEY or not GEMINI_API_KEY.startswith("AIza"):
        return "❌ Render未有GEMINI_API_KEY，請去Environment檢查。", "no_key"

    prompt = SYSTEM_PROMPT + f"\n學生問題: {question}"

    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        parts = [{"text": prompt}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})

        try:
            r = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=60)
            print(f"{model} -> {r.status_code}")

            if r.status_code == 200:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return text, "ok"
                except Exception as e:
                    print(f"Parse err {e}")
                    continue
            else:
                # This will show you the real problem
                print(f"Error {r.status_code}: {r.text[:1000]}")
                if r.status_code in [400, 403]:
                    return f"❌ API Key錯誤 {r.status_code}: {r.text[:500]}\n去 https://aistudio.google.com/app/apikey 開一個NEW key (舊key升級後可能無效)", "error"
                if r.status_code == 404:
                    continue # try next model
        except Exception as e:
            print(f"Req err {e}")
            continue

    return "❌ Gemini暫時忙碌，Tier 1應該唔會429，檢查Billing係咪Enable咗。", "quota"

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
        text = "2+1"

    answer, status = call_gemini(text, b64)

    # Graph support
    m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
    if m:
        eq = m.group(1).strip()
        clean = answer.replace(m.group(0), "").strip()
        send_text(jid, clean)
        desmos = f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}"
        send_text(jid, f"📈 圖：{eq}\n👉 {desmos}")
    else:
        send_text(jid, answer)

    return jsonify({"ok": True}), 200

@app.route("/test", methods=["GET"])
def test():
    q = request.args.get("q", "1+3")
    ans, st = call_gemini(q)
    return jsonify({"status": st, "key_len": len(GEMINI_API_KEY), "question": q, "answer": ans})

@app.route("/", methods=["GET"])
def home():
    return f"Final Tier1 Bot - key_len={len(GEMINI_API_KEY)} - OK", 200
