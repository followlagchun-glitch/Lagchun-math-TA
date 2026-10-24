from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64

app = Flask(__name__)

# ===== ENV =====
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ len={len(GEMINI_API_KEY)}")

# ===== 手寫批改 + OCR Prompt =====
SYSTEM_PROMPT = """
You are LC Sir - Hong Kong DSE Math Tutor, expert in marking handwritten work.

TASK:

Step 0 - OCR (MUST DO FIRST):
- Carefully read ALL handwritten + printed text in image/PDF.
- List exactly what student wrote, line by line.
- If unclear, mark [unclear: maybe X].

Step 1 - 判斷:
- Topic? What is question asking?

Step 2 - 👍 做得好:
- Point 2-3 good points: method correct, steps clear, concept good.

Step 3 - 👎 做得唔好 / 錯咗:
- List errors: 計算錯, 概念錯, 漏步驟, 格式錯.
- Explain WHY wrong in simple Cantonese.

Step 4 - 正確解法:
- Show full correct solution Step 1,2,3 with LaTeX.

Step 5 - 建議:
- 1 tip to avoid same mistake.

Language: HK Cantonese 口語, friendly. Formulas in English/LaTeX.
If only printed question, skip Step 2/3.

If need graph, end with: GRAPH_EQUATION: <equation>
"""

# ===== 最新可用 Models =====
MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-2.5-flash",
    "gemini-2.0-flash"
]

# ===== 拎圖+PDF - Fix 400 版 =====
def get_file_base64(data, is_pdf=False):
    print(f"=== START get_file is_pdf={is_pdf} ===")
    # M1: 正確 v2.3.7 格式
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

    # M2: 試舊 endpoint
    try:
        payload = {"message": data}
        url = f"{EVOLUTION_API_URL}/message/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        r = requests.post(url, json=payload, headers=headers, timeout=40)
        print(f"[M2] {r.status_code} {r.text[:1000]}")
        if r.status_code == 200:
            j = r.json()
            b64 = j.get("base64") or j.get("data")
            if b64 and len(b64) > 1000:
                if "," in b64: b64 = b64.split(",")[-1]
                print(f"[M2] SUCCESS len={len(b64)}")
                return b64, "application/pdf" if is_pdf else "image/jpeg"
    except Exception as e:
        print(f"[M2] error {e}")

    # M3: 直接 CDN download
    try:
        msg = data.get("message", {})
        im = msg.get("imageMessage") or msg.get("documentMessage") or {}
        media_url = im.get("url") or im.get("mediaUrl")
        if media_url:
            print(f"[M3] CDN {media_url[:150]}")
            r2 = requests.get(media_url, timeout=30)
            print(f"[M3] status {r2.status_code} size {len(r2.content)}")
            if r2.status_code == 200 and len(r2.content) > 1000:
                b64 = base64.b64encode(r2.content).decode()
                print(f"[M3] SUCCESS len={len(b64)}")
                return b64, "application/pdf" if is_pdf else "image/jpeg"
    except Exception as e:
        print(f"[M3] error {e}")

    print("=== ALL FAILED ===")
    return None, None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    if len(GEMINI_API_KEY) < 20:
        return f"❌ KEY empty len={len(GEMINI_API_KEY)}", "no_key"
    prompt = SYSTEM_PROMPT + f"\n\n學生傳來: {question}"
    last_error = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts = [{"text": prompt}]
        if file_b64:
            parts.append({"inline_data": {"mime_type": mime_type, "data": file_b64}})
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.3}}
        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            print(f"TRY {model} -> {r.status_code}")
            if r.status_code == 200:
                j = r.json()
                return j["candidates"][0]["content"]["parts"][0]["text"], "ok"
            last_error = r.text
            if r.status_code == 404:
                continue
        except Exception as e:
            last_error = str(e)
            continue
    return f"❌ Error: {last_error[:2000]}", "error"

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
        text = caption or text or "幫我批改呢份手寫功課，做得好同唔好都要講"
    elif "documentMessage" in msg:
        b64, mime = get_file_base64(data, is_pdf=True)
        fname = msg["documentMessage"].get("fileName") or "功課.pdf"
        text = text or f"幫我批改呢個PDF {fname}"
        mime = "application/pdf"

    if not text and not b64:
        text = "Hello"

    print(f"Incoming {jid} has_file={bool(b64)} mime={mime} text={text[:80]}")
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

@app.route("/test", methods=["GET"])
def test():
    q = request.args.get("q", "1+3")
    ans, st = call_gemini(q)
    return jsonify({"status": st, "answer": ans})

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir Super Final Live MODELS={MODELS[0]} OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
