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

MODELS = [
    "gemini-3.5-flash-lite",
    "gemini-3-flash-preview",
    "gemini-2.5-flash",
    "gemini-2.5-pro"
]

# ===== 新增：拎圖功能 (Fix 你而家睇唔到圖) =====
def get_image_base64(data):
    import base64
    msg = data.get("message", {})
    im = msg.get("imageMessage", {}) or {}
    
    # Debug: 睇吓 webhook 入面到底有咩
    print(f"DEBUG imageMessage keys: {list(im.keys())}")
    print(f"DEBUG data keys: {list(data.keys())}")
    
    # 方法1: Evolution 新版 endpoint (你嗰個版本多數用呢個)
    try:
        # 有啲版本要用 /chat/getBase64FromMediaMessage
        # 有啲要用 /message/getBase64FromMediaMessage
        for endpoint in ["/chat/getBase64FromMediaMessage", "/message/getBase64FromMediaMessage"]:
            url = f"{EVOLUTION_API_URL}{endpoint}/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            # payload 要成個 data
            r = requests.post(url, json=data, headers=headers, timeout=30)
            print(f"TRY {endpoint} -> {r.status_code} {r.text[:500]}")
            if r.status_code == 200:
                j = r.json()
                b64 = j.get("base64") or j.get("data") or j.get("base64String") or j.get("result", {}).get("base64")
                if b64 and len(b64) > 1000:
                    if "," in b64: b64 = b64.split(",")[-1]
                    print(f"SUCCESS Method1 len={len(b64)}")
                    return b64
    except Exception as e:
        print(f"Method1 error {e}")

    # 方法2: 直接用 WhatsApp CDN url download (最原始但最work)
    try:
        media_url = im.get("url") or im.get("mediaUrl")
        if media_url:
            print(f"Method2 downloading {media_url[:150]}")
            r = requests.get(media_url, timeout=30)
            if r.status_code == 200 and len(r.content) > 1000:
                b64 = base64.b64encode(r.content).decode()
                print(f"SUCCESS Method2 len={len(b64)}")
                return b64
    except Exception as e:
        print(f"Method2 error {e}")

    print("ALL Methods FAILED - no b64")
    return None
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
            print(f"TRY {model} -> {r.status_code}")
            if r.status_code in [401, 403]:
                r = requests.post(f"{url}?key={GEMINI_API_KEY}", json=body, headers={"Content-Type":"application/json"}, timeout=90)
            if r.status_code == 200:
                j = r.json()
                text = j["candidates"][0]["content"]["parts"][0]["text"]
                return text, "ok", ""
            last_error = r.text
        except Exception as e:
            last_error = str(e)
            continue

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
    # ===== 修改位：用 get_image_base64 =====
    if "imageMessage" in msg:
        b64 = get_image_base64(data)
        caption = msg["imageMessage"].get("caption") or ""
        text = caption or text or "幫我逐步計呢題"
        print(f"Image b64 len={len(b64) if b64 else 0}")

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
