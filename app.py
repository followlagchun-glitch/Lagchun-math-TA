from flask import Flask, request, jsonify
import os, requests, random, re, urllib.parse

app = Flask(__name__)

# --- ENV ---
# Support 1 key or 3 keys rotation
_raw_keys = [
    os.getenv("GEMINI_API_KEY"),
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
]
GEMINI_KEYS = [k.strip() for k in _raw_keys if k and k.strip().startswith("AIza")]
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT: Found {len(GEMINI_KEYS)} Gemini keys, Evolution={bool(EVOLUTION_API_URL)}")

# SketchMath Teacher style
SYSTEM_PROMPT = """
You are LC Sir, a Hong Kong math teacher (SketchMath style).
Rules:
1. Use Step 1, Step 2, Step 3 format like SketchMath.
2. Explain in Hong Kong Cantonese口語 (唔好用書面語，要似老師講嘢)，but keep math formulas in English.
3. If graph needed (circle, quadratic), at very end add line: GRAPH_EQUATION: <equation>
Example: GRAPH_EQUATION: x^2 + y^2 + 9x - 5y = 0
"""

# High quota models (1500/day each, not 20/day)
MODELS = ["gemini-1.5-flash-8b", "gemini-1.5-flash", "gemini-2.0-flash-lite"]

def call_gemini(question, image_b64=None):
    if not GEMINI_KEYS:
        return None, "no_key"

    full_prompt = SYSTEM_PROMPT + f"\n\n學生問題: {question}"
    
    # Shuffle keys to spread quota
    keys_to_try = GEMINI_KEYS[:]
    random.shuffle(keys_to_try)

    for api_key in keys_to_try:
        for model in MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            
            parts = [{"text": full_prompt}]
            if image_b64:
                # Evolution sends base64 without data: prefix
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})

            try:
                r = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=45)
                print(f"Try {model} key..{api_key[-4:]}: {r.status_code}")

                if r.status_code == 429:
                    print(f"Quota hit for {model}, trying next...")
                    continue # try next model/key
                if r.status_code == 200:
                    try:
                        txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                        return txt, "ok"
                    except Exception as e:
                        print(f"Parse error {e} body {r.text[:500]}")
                        continue
                else:
                    print(f"Gemini {r.status_code}: {r.text[:500]}")
                    # 404 = model not found, try next
                    if r.status_code in [404, 403]:
                        continue
            except Exception as e:
                print(f"Request exception {e}")
                continue

    return None, "quota"

def send_text(jid, text):
    if not EVOLUTION_API_URL or not EVOLUTION_INSTANCE:
        print("Evolution not configured")
        return
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        r = requests.post(url, json={"number": jid, "text": text}, headers=headers, timeout=20)
        print(f"SendText {r.status_code}")
    except Exception as e:
        print(f"SendText error {e}")

def send_graph_link(jid, equation):
    # NO MATPLOTLIB - uses external link, 0 RAM -> No SIGKILL
    try:
        # Desmos link - student can click and see interactive graph
        encoded = urllib.parse.quote(equation)
        desmos_url = f"https://www.desmos.com/calculator?expressions={encoded}"
        # Also QuickChart static image (Evolution can fetch URL)
        quickchart_url = f"https://quickchart.io/chart?c={{type:'scatter',data:{{datasets:[{{label:'{equation}',data:[{{x:-5,y:0}}]}}]}}}}"
        
        msg = f"📈 圖解：{equation}\n👉 撳入去睇互動圖：{desmos_url}"
        send_text(jid, msg)
    except Exception as e:
        print(f"Graph link error {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json or {}
    try:
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
            text = msg["imageMessage"].get("caption") or text or "幫我逐步解釋點樣計呢題，要用Step 1, Step 2。"

        if not text:
            text = "What is 2+1"

        print(f"IN from {jid}: {text[:100]} img={bool(b64)}")
        answer, status = call_gemini(text, b64)

        if status == "no_key":
            answer = f"❌ 未設定GEMINI_API_KEY！去Render>Environment檢查。見到 {len(GEMINI_KEYS)} 條key。記得用AIza開頭，無空格。"
        elif status == "quota":
            answer = f"今日問得太多喇！{len(GEMINI_KEYS)}條key嘅 {','.join(MODELS)} 額度都爆咗(429)。\n\n解決：1) 去 https://aistudio.google.com/app/apikey 用多個Gmail開多2條key，加到Render叫 GEMINI_API_KEY_2, _3。\n2) 或者開Billing升級Tier 1 (有$300免費)，每1000次先 $0.0375。\n頭先你問 {text[:20]}，我聽日再答你！"
        elif not answer:
            answer = f"Gemini暫時連唔到 ({status})，試下再問一次 2+1=3 呀！"

        # Check for graph
        m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
        if m:
            eq = m.group(1).strip()
            clean_ans = answer.replace(m.group(0), "").strip()
            send_text(jid, clean_ans)
            send_graph_link(jid, eq)
        else:
            send_text(jid, answer)

    except Exception as e:
        print(f"WEBHOOK ERR {e}")
        import traceback; traceback.print_exc()
    return jsonify({"ok": True}), 200

@app.route("/test", methods=["GET"])
def test():
    # Test without WhatsApp: https://your-bot.onrender.com/test?q=What+is+2%2B1
    q = request.args.get("q", "What is 2+1, explain in Cantonese")
    ans, status = call_gemini(q)
    return jsonify({
        "status": status,
        "keys_found": len(GEMINI_KEYS),
        "models_tried": MODELS,
        "question": q,
        "answer": ans
    })

@app.route("/", methods=["GET"])
def home():
    return f"LC Bot Live - Keys:{len(GEMINI_KEYS)} - No SIGKILL - Test /test?q=2%2B1", 200
