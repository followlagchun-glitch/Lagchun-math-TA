from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64, time

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ len={len(GEMINI_API_KEY)}")

# ===== LC SIR - 最終靚仔口語版 =====
SYSTEM_PROMPT = """
You are LC Sir, Hong Kong DSE Math tutor. You talk like a real friendly tutor, not a robot.

RULES - VERY IMPORTANT:
1. WhatsApp CANNOT show LaTeX. NEVER use $ $ or \\frac \\text \\because \\therefore. If you use it, student cannot read.
   - Use plain math: a = -1 < 0, y = (34/5), x^2, (x,y) = (1,6), sqrt(2)
2. Talk SIMPLE and SHORT. Like a real person.
   - Bad: "題目問 Direction of opening / 開口方向, 你寫「$a = -1 < 0$」只係*原因*, 並唔係*方向*。標準答案必須寫出「Downwards / 向下」。"
   - Good: "開口方向呢，你寫咗 a = -1 < 0，呢個係原因啫，未係答案。記得要寫埋 Downwards 向下 先攞足分。"
3. Format for WhatsApp:
   - Use *粗體* for important words
   - Use short lines, 1-2 sentences per point
   - Use emoji: 👍 👎 💡 ✅
   - No long ### headers, use simple titles
4. Language: HK Cantonese 口語, 親切，好似真人改簿咁。

OUTPUT STRUCTURE (keep simple):
你寫咗咩: (list 1-2 lines what student wrote)

👍 做得好:
- 1-2 points, short

👎 要留意:
- 講錯咩, 點解錯, 用口語。例如 "呢度爭少，計到 y = 34/5 就停咗，記得要寫埋個點 (x,y) 呀"

💡 點樣寫先啱:
(a) y = -2x^2 + x
- 開口: x^2 前面係 -2 < 0, 所以向下 Downwards
- 計法: (simple steps, 1 line 1 step)

No LaTeX. If need graph: GRAPH_EQUATION: y = -2*x^2 + x
"""

MODELS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash"
]

def clean_b64(b64):
    if not b64: return None
    b64 = b64.strip()
    if "," in b64: b64 = b64.split(",")[-1]
    b64 = b64.replace("\n","").replace("\r","").replace(" ","")
    b64 += "=" * (-len(b64) % 4)
    return b64

def get_file_base64(data, is_pdf=False):
    print("Initial wait 3s...")
    time.sleep(3)
    for attempt in range(5):
        try:
            payload = {"message": data}
            url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            print(f"[M1] {r.status_code} len={len(r.text)} Attempt {attempt+1}/5")
            if r.status_code in [200, 201]:
                m = re.search(r'"base64"\s*:\s*"([^"]{1000,})"', r.text)
                raw = m.group(1) if m else None
                if not raw:
                    try:
                        j = r.json()
                        raw = j.get("base64") or j.get("data")
                    except: pass
                b64 = clean_b64(raw) if raw else None
                if b64 and len(b64) > 1000:
                    try:
                        dec = base64.b64decode(b64, validate=False)
                        mt = "application/pdf" if is_pdf or dec[:4]==b'%PDF' else "image/jpeg"
                        print(f"[M1] SUCCESS {len(dec)} bytes")
                        return b64, mt
                    except: pass
        except Exception as e:
            print(f"[M1] err {e}")
        if attempt < 4: time.sleep(8)
    return None, None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    prompt = SYSTEM_PROMPT + f"\n\n學生: {question}"
    last_error = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts = [{"text": prompt}]
        if file_b64:
            parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.3}}
        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            print(f"TRY {model} -> {r.status_code}")
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return txt, "ok"
            last_error = r.text[:1000]
        except Exception as e:
            last_error = str(e)
    return f"Error: {last_error}", "error"

def send_text(jid, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        for i in range(0, len(text), 3000):
            requests.post(url, json={"number": jid, "text": text[i:i+3000]}, headers=headers, timeout=20)
            time.sleep(0.5)
    except Exception as e:
        print(f"Send fail {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json or {}
    data = body.get("data", {})
    key = data.get("key", {})
    msg = data.get("message", {})
    jid = key.get("remoteJid")
    push_name = data.get("pushName") or ""
    
    if not jid or key.get("fromMe"): 
        return jsonify({"ok": True}), 200

    is_group = "@g.us" in jid
    text = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    
    # 群組防洗版: 只有叫佢先覆
    if is_group:
        low = text.lower()
        if not any(k in low for k in ["lc", "阿sir", "阿 sir", "sir", "老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
            # 如果冇文字但有相，都覆 (方便交功課)
            if not msg.get("imageMessage", {}).get("caption"):
                return jsonify({"ok": True}), 200
        text = f"[{push_name} 問]: {text}"

    b64, mime = None, "image/jpeg"
    if "imageMessage" in msg:
        b64, mime = get_file_base64(data, is_pdf=False)
        cap = msg["imageMessage"].get("caption") or ""
        text = (cap or text or "幫我睇下呢份功課").strip()
    elif "documentMessage" in msg:
        b64, mime = get_file_base64(data, is_pdf=True)
        text = (text or "幫我睇下呢份PDF功課").strip()
        mime = "application/pdf"

    if not text and not b64: 
        return jsonify({"ok": True}), 200

    print(f"Incoming group={is_group} has_file={bool(b64)} text={text[:60]}")
    
    if ("imageMessage" in msg or "documentMessage" in msg) and not b64:
        send_text(jid, "張圖仲 load 緊，麻煩 send 多次新相試試，唔好 forward 舊相 🙏")
        return jsonify({"ok": True}), 200

    answer, _ = call_gemini(text, b64, mime)
    
    m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
    if m:
        eq = m.group(1).strip()
        clean = answer.replace(m.group(0), "").strip()
        send_text(jid, clean)
        link = f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}"
        send_text(jid, f"📈 互動圖: {eq}\n{link}")
    else:
        if is_group and push_name:
            answer = f"@{push_name} {answer}"
        send_text(jid, answer)
    
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir FINAL v5 Group+Simple len={len(GEMINI_API_KEY)}", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
