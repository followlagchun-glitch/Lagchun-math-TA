from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ len={len(GEMINI_API_KEY)}")

# ===== 你的永久要求 (我記住咗) =====
# LC SIR: HK Cantonese + 手寫批改 Good/Bad + Image+PDF + Desmos
SYSTEM_PROMPT = """
You are LC Sir - Hong Kong DSE Math Tutor, expert in marking handwritten work.

Step 0 - OCR (MUST):
- Carefully read ALL handwritten + printed text in image/PDF line by line.
- List what student wrote.

Step 1 - 判斷題目
Step 2 - 👍 做得好: 2-3 points
Step 3 - 👎 做得唔好 / 錯咗: explain why in Cantonese
Step 4 - 正確解法: Step 1,2,3 with LaTeX
Step 5 - 建議: 1 tip

Language: HK Cantonese 口語. Formulas English/LaTeX.
If need graph, end with: GRAPH_EQUATION: <equation>
"""

# ===== 2026-10-25 最新可用 (Fix 你張圖 404) =====
MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3-flash-preview"
]

def get_file_base64(data, is_pdf=False):
    print(f"=== START get_file is_pdf={is_pdf} ===")
    try:
        payload = {"message": data}
        url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=40)
        print(f"[M1] {r.status_code} {r.text[:1200]}")
        if r.status_code == 200:
            j = r.json()
            b64 = j.get("base64") or j.get("data") or j.get("base64String") or j.get("result", {}).get("base64") or j.get("result", {}).get("base64String")
            if not b64 and isinstance(j.get("result"), str) and len(j.get("result")) > 1000:
                b64 = j.get("result")
            if b64:
                if "," in b64: b64 = b64.split(",")[-1]
                if len(b64) > 1000:
                    print(f"[M1] SUCCESS len={len(b64)}")
                    return b64, "application/pdf" if is_pdf else "image/jpeg"
    except Exception as e:
        print(f"[M1] error {e}")

    try:
        msg = data.get("message", {})
        im = msg.get("imageMessage") or msg.get("documentMessage") or {}
        media_url = im.get("url") or im.get("mediaUrl")
        if media_url:
            r2 = requests.get(media_url, timeout=30)
            if r2.status_code == 200 and len(r2.content) > 1000:
                b64 = base64.b64encode(r2.content).decode()
                print(f"[M3] CDN SUCCESS len={len(b64)}")
                return b64, "application/pdf" if is_pdf else "image/jpeg"
    except Exception as e:
        print(f"[M3] error {e}")
    print("ALL FAILED")
    return None, None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    prompt = SYSTEM_PROMPT + f"\n\n學生傳來: {question}"
    last_error = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts = [{"text": prompt}]
        if file_b64:
            parts.append({"inline_data": {"mime_type": mime_type, "data": file_b64}})
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.2}}
        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            print(f"TRY {model} -> {r.status_code}")
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                print(f"OK {model}")
                return txt, "ok"
            last_error = r.text[:2000]
            print(f"FAIL {model} {last_error[:400]}")
            continue
        except Exception as e:
            last_error = str(e)
            continue
    return f"❌ Error: {last_error}", "error"

def send_text(jid, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        for i in range(0, len(text), 3000):
            requests.post(url, json={"number": jid, "text": text[i:i+3000]}, headers=headers, timeout=20)
    except Exception as e:
        print(f"Send fail {e}")

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
    mime = "image/jpeg"
    if "imageMessage" in msg:
        b64, mime = get_file_base64(data, is_pdf=False)
        caption = msg["imageMessage"].get("caption") or ""
        text = caption or text or "幫我批改呢份手寫功課"
    elif "documentMessage" in msg:
        b64, mime = get_file_base64(data, is_pdf=True)
        text = text or "幫我批改PDF功課"
        mime = "application/pdf"
    if not text and not b64:
        text = "Hello"
    print(f"Incoming has_file={bool(b64)}")
    answer, _ = call_gemini(text, b64, mime)
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

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir Final Live len={len(GEMINI_API_KEY)} MODEL={MODELS[0]}", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
