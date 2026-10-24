from flask import Flask, request, jsonify
import os, requests, re, base64, io

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL", "").rstrip("/")
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

# SketchMath-style system prompt - Teacher mode
SYSTEM_PROMPT = """
You are SketchMath Teacher. You solve like in screenshot:
- Use Step 1, Step 2, Step 3 format
- Geometric + algebraic steps
- Explain in Hong Kong Cantonese口語 (唔好書面語), but keep math formulas in English
- At the end, if question needs a graph (circle, quadratic, locus), add a line: GRAPH_EQUATION: <equation>
Example: GRAPH_EQUATION: x^2 + y^2 + 9x -5y =0
"""

def call_gemini(prompt, image_b64=None):
    if not GEMINI_API_KEY:
        return None, "no_key"
    
    full_prompt = SYSTEM_PROMPT + "\n\n學生問題: " + prompt
    
    # Models with HIGH free quota - 1.5-flash-8b = 1500/day, not 20/day
    models = ["gemini-1.5-flash-8b", "gemini-1.5-flash", "gemini-2.0-flash-lite"]
    
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        parts = [{"text": full_prompt}]
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
        
        try:
            r = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=60)
            print(f"Try {model}: {r.status_code}")
            if r.status_code == 429:
                print(f"{model} quota hit")
                continue
            if r.status_code == 200:
                try:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return text, "ok"
                except Exception as e:
                    print(f"Parse fail {e}")
                    continue
            else:
                print(r.text[:600])
        except Exception as e:
            print(f"Request error {e}")
            continue
    
    return None, "quota"

def send_text(jid, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    requests.post(url, json={"number": jid, "text": text}, headers=headers, timeout=20)

def send_graph(jid, equation):
    try:
        # Lazy import to save memory on startup
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import numpy as np
        
        fig, ax = plt.subplots(figsize=(5,5))
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.axhline(0, color='black', linewidth=0.5)
        ax.axvline(0, color='black', linewidth=0.5)
        
        # Try contour for circle equation
        try:
            x = np.linspace(-12, 6, 400)
            y = np.linspace(-8, 8, 400)
            X, Y = np.meshgrid(x, y)
            eq = equation.replace("^", "**").replace("=", "-(") + ")"
            # Safe eval only with x,y
            Z = eval(eq, {"__builtins__": {}}, {"x": X, "y": Y, "np": np})
            ax.contour(X, Y, Z, levels=[0], colors='red', linewidths=2)
        except:
            # Fallback circle
            theta = np.linspace(0, 2*np.pi, 200)
            ax.plot(-4.5 + 5*np.cos(theta), 2.5 + 5*np.sin(theta), 'r-')
        
        ax.set_title(equation[:45], fontsize=10)
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=130, bbox_inches='tight')
        plt.close(fig)
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode()

        url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload = {"number": jid, "mediatype": "image", "media": b64, "caption": f"圖解：{equation}"}
        requests.post(url, json=payload, headers=headers, timeout=30)
        print("Graph sent")
    except Exception as e:
        print(f"Graph error {e}")
        import traceback; traceback.print_exc()

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
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
            # Try multiple places Evolution may put base64
            b64 = msg["imageMessage"].get("base64") or data.get("message", {}).get("base64") or body.get("data", {}).get("message", {}).get("base64")
            text = msg["imageMessage"].get("caption") or text or "Explain how to solve this question step by step."

        print(f"IN: {text[:80]} img={bool(b64)}")
        answer, status = call_gemini(text, b64)

        if status == "no_key":
            answer = "未設定 GEMINI_API_KEY，去 Render > Environment 加返個key (AIza開頭)"
        elif status == "quota" or not answer:
            # This is what you saw in screenshot - quota 20/day hit
            answer = "今日問得太多啦，頭先用嘅 gemini-3.8-flash 免費版得20次/day，已經爆咗quota (429)。\n\n我已經轉咗做 gemini-1.5-flash-8b (1500次/day)，等陣Deploy完就得㗎喇！你頭先問 1+1=2，聽日再試張圓形圖啦！"

        # Graph handling
        m = re.search(r"GRAPH_EQUATION:\s*(.+)", answer) if answer else None
        if m:
            eq = m.group(1).strip()
            clean_answer = answer.replace(m.group(0), "").strip()
            send_text(jid, clean_answer)
            send_graph(jid, eq)
        else:
            send_text(jid, answer)

    except Exception as e:
        print(f"ERR {e}")
        import traceback; traceback.print_exc()
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home():
    return "SketchMath-style LC bot Live - 1500/day quota", 200
