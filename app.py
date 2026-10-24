from flask import Flask, request, jsonify
import os, requests, re, urllib.parse

app = Flask(__name__)

# --- ROBUST KEY FINDER (fixes your case bug) ---
def get_gemini_key():
    # 1. Try exact names first
    for name in ["GEMINI_API_KEY", "GEMINI_API_KEY_1", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
        v = os.getenv(name)
        if v and "AIza" in v:
            print(f"Found key via {name}")
            return v.strip()
    
    # 2. If not found, search ALL env vars case-insensitively (fixes Gemini_ApI_key)
    for k, v in os.environ.items():
        if "GEMINI" in k.upper() and v and "AIza" in v:
            print(f"Found key via fuzzy search: {k}")
            return v.strip()
    
    return ""

GEMINI_API_KEY = get_gemini_key()
EVOLUTION_API_URL = (os.getenv("EVOLUTION_API_URL") or "").strip().rstrip("/")
EVOLUTION_INSTANCE = (os.getenv("EVOLUTION_INSTANCE") or "").strip()
EVOLUTION_API_KEY = (os.getenv("EVOLUTION_API_KEY") or "").strip()

print(f"BOOT: GEMINI key found={bool(GEMINI_API_KEY)} len={len(GEMINI_API_KEY) if GEMINI_API_KEY else 0}")

SYSTEM_PROMPT = """
You are LC Sir + SketchMath Teacher.
- Use Step 1, Step 2, Step 3 format
- Hong Kong Cantonese口語, formulas in English
- If graph needed, end with: GRAPH_EQUATION: <equation>
"""

MODELS = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

def call_gemini(question, image_b64=None):
    if not GEMINI_API_KEY:
        print("NO KEY FOUND - checking env:")
        for k in os.environ.keys():
            if "GEMINI" in k.upper():
                print(f"  Found env var: {k}")
        return None, "no_key"

    prompt = SYSTEM_PROMPT + f"\n學生問題: {question}"
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        parts = [{"text": prompt}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
        try:
            r = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=60)
            print(f"Gemini {model}: {r.status_code}")
            if r.status_code == 200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"], "ok"
            elif r.status_code == 429:
                continue
            else:
                print(r.text[:800])
        except Exception as e:
            print(f"Err {e}")
    return None, "quota"

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
        b64 = msg["imageMessage"].get("base64") or data.get("message", {}).get("base64")
        text = msg["imageMessage"].get("caption") or text or "幫我逐步計呢題"

    if not text:
        text = "2+1"

    answer, status = call_gemini(text, b64)

    if status == "no_key":
        # Show debug to help you
        env_list = [k for k in os.environ.keys() if "GEMINI" in k.upper()]
        answer = f"❌ 搵唔到Key！我見到嘅ENV係：{env_list}。請去Render>Environment 確保有 GEMINI_API_KEY=AIza開頭。依家長度：{len(GEMINI_API_KEY)}"
    elif not answer:
        answer = "Tier1忙，試多一次"

    m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
    if m:
        eq = m.group(1).strip()
        send_text(jid, answer.replace(m.group(0),"").strip())
        link = f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}"
        send_text(jid, f"圖：{eq}\n{link}")
    else:
        send_text(jid, answer)

    return jsonify({"ok": True}), 200

@app.route("/test", methods=["GET"])
def test():
    q = request.args.get("q", "2+1")
    env_debug = [k for k in os.environ.keys() if "GEMINI" in k.upper()]
    ans, st = call_gemini(q)
    return jsonify({"status": st, "env_vars_found": env_debug, "key_len": len(GEMINI_API_KEY), "ans": ans})

@app.route("/", methods=["GET"])
def home():
    return f"Bot Live key_len={len(GEMINI_API_KEY)} - /test?q=2%2B1", 200
