from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64, time

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ len={len(GEMINI_API_KEY)}")

SYSTEM_PROMPT = """
You are LC Sir - HK DSE Math Tutor.
Step 0 - OCR what student wrote line by line.
Step 1 - 判斷題目
Step 2 - 👍 做得好: 2-3 points
Step 3 - 👎 做得唔好: explain in HK Cantonese
Step 4 - 正確解法 Step with LaTeX
Step 5 - 建議 1 tip
Language: HK Cantonese. If graph: GRAPH_EQUATION: <eq>
"""

MODELS = ["gemini-3.8-flash","gemini-3.5-flash-lite","gemini-3.5-flash"]

def clean_b64(b64):
    if not b64: return None
    b64 = b64.strip()
    if "," in b64: b64 = b64.split(",")[-1]
    b64 = b64.replace("\n","").replace("\r","").replace(" ","")
    b64 += "=" * (-len(b64) % 4)
    return b64

def get_file_base64(data, is_pdf=False):
    print(f"=== START get_file is_pdf={is_pdf} ===")
    # 一開始等 3 秒，等 Evolution 落盤
    print("Initial wait 3s for Evolution to save media...")
    time.sleep(3)
    
    for attempt in range(5): # 試 5 次
        print(f"Attempt {attempt+1}/5")
        try:
            payload = {"message": data}
            url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            r = requests.post(url, json=payload, headers=headers, timeout=60)
            print(f"[M1] {r.status_code} len={len(r.text)} {r.text[:1200]}")
            if r.status_code == 200:
                j = r.json()
                raw = j.get("base64") or j.get("data") or j.get("base64String") or j.get("result",{}).get("base64") or j.get("result",{}).get("base64String")
                if not raw and isinstance(j.get("result"), str) and len(j.get("result"))>1000:
                    raw = j.get("result")
                b64 = clean_b64(raw) if raw else None
                if b64 and len(b64)>1000:
                    dec = base64.b64decode(b64)
                    print(f"[M1] SUCCESS {len(dec)} bytes")
                    mt = "application/pdf" if is_pdf or dec[:4]==b'%PDF' else "image/jpeg"
                    return b64, mt
        except Exception as e:
            print(f"[M1] err {e}")
        if attempt < 4:
            wait = 8 # 你要求嘅多 5 秒版：8 秒
            print(f"Sleep {wait}s waiting Evolution download... (attempt {attempt+1})")
            time.sleep(wait)
    print("ALL FAILED after 5 tries")
    return None, None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    prompt = SYSTEM_PROMPT + f"\n學生: {question}"
    last = ""
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts = [{"text": prompt}]
        if file_b64:
            parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.2}}
        try:
            r = requests.post(url, json=body, headers=headers, timeout=90)
            print(f"TRY {model} -> {r.status_code}")
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                print(f"OK {model}")
                return txt, "ok"
            last = r.text[:2000]
            print(f"FAIL {model} {last[:500]}")
        except Exception as e:
            last = str(e)
    return f"❌ {last}", "error"

def send_text(jid, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        for i in range(0, len(text), 3500):
            requests.post(url, json={"number": jid, "text": text[i:i+3500]}, headers=headers, timeout=20)
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
        text = text or "幫我批改PDF"
        mime = "application/pdf"
    if not text and not b64:
        text = "Hello"
    print(f"Incoming has_file={bool(b64)} mime={mime}")
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
    return f"LC Sir Live 8s-Retry MODEL={MODELS[0]}", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
