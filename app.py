from flask import Flask, request, jsonify
import os, requests, re, urllib.parse

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ len={len(GEMINI_API_KEY)}")

# ===== 手寫批改專用 Prompt =====
SYSTEM_PROMPT = """
You are LC Sir - Hong Kong DSE Math Tutor, expert in marking handwritten work.

You will receive IMAGE or PDF that may be:
1. Printed question
2. Student handwritten solution
3. Both

TASK:

Step 0 - OCR (must do first):
- Carefully read ALL handwritten text and math in image/PDF.
- List exactly what student wrote, line by line.
- If unclear, mark [unclear: maybe X].
- Keep original steps.

Step 1 - 判斷題目:
- What topic? (e.g. Surds, Equation, Factorize)
- What is the question asking?

Step 2 - 批改 - 做得好 👍:
- Point out 2-3 good points: method correct, steps clear, correct concept, good handwriting structure.
- Use Cantonese 讚賞.

Step 3 - 批改 - 做得唔好 / 錯咗 👎:
- List errors:
    * 計算錯 (e.g. 4*10=40 not 160)
    * 概念錯 (e.g. sqrt(a+b) != sqrt(a)+sqrt(b))
    * 漏步驟 / 跳步
    * 格式 / 單位 / 約簡錯
- Explain WHY wrong, in simple Cantonese.

Step 4 - 正確解法:
- Show full correct solution with Step 1, Step 2, Step 3.
- Use LaTeX for final answer.

Step 5 - 建議:
- Give 1 tip to avoid same mistake next time.

Language: All in HK Cantonese 口語, friendly like a private tutor. Formulas in English/LaTeX.

If image is only printed question (no handwritten solution), skip Step 2/3, just do correct solution.

If need graph, end with: GRAPH_EQUATION: <equation>
"""

MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-pro"
]

def get_file_base64(data, is_pdf=False):
    try:
        url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        r = requests.post(url, json=data, headers=headers, timeout=40)
        print(f"getBase64 is_pdf={is_pdf} -> {r.status_code}")
        if r.status_code == 200:
            j = r.json()
            b64 = j.get("base64") or j.get("data") or j.get("result", {}).get("base64")
            if b64:
                if "," in b64: b64 = b64.split(",")[-1]
                if len(b64) > 1000:
                    return b64, "application/pdf" if is_pdf or "pdf" in str(j.get("mimetype","")).lower() else "image/jpeg"
    except Exception as e:
        print(f"getFile fail {e}")
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
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.3}}
        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            print(f"TRY {model} -> {r.status_code}")
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"], "ok"
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
        # WhatsApp 限制 3500 字，分段 send
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
        text = text or f"幫我批改呢份手寫PDF {fname}"
        mime = "application/pdf"

    if not text and not b64:
        text = "Hello"

    print(f"Incoming {jid} has_file={bool(b64)}")
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
    return f"LC Sir Marking Bot Live - Handwriting Support OK", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
