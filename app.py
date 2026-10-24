from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64, time
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

print(f"BOOT AQ len={len(GEMINI_API_KEY)}")

# ===== LC SIR - 逐題+每題視像化版 =====
SYSTEM_PROMPT = """
You are LC Sir, Hong Kong DSE Math tutor. Friendly, simple, not robotic.

CRITICAL FORMATTING:
- NEVER use $ $ or \\frac \\text. Use plain math: a = -1 < 0, y = 34/5, x^2, (1,6), sqrt(2)
- Use *bold* for titles, short lines, HK Cantonese.
- MUST mark by question order for PDF.

OUTPUT RULE:
1. List questions seen: "見到 Q14, Q15"
2. For EACH question in order:
---
*Q14 (a) 開口方向*
你寫咗： a = -1 < 0
睇法： ❌ 爭少，呢個係原因
應該點寫： 因為 -2 < 0，所以係 向下 Downwards

3. VERY IMPORTANT - VISUALIZATION:
For EVERY question that is a function/graph (quadratic, linear, etc), you MUST add a line at the END of that question block:
GRAPH_EQUATION: y = -2*x^2 + x

Examples:
- If Q14 is y = -x^2 + x + 6, add: GRAPH_EQUATION: y = -x^2 + x + 6
- If Q15 is y = 2x + 3, add: GRAPH_EQUATION: y = 2*x + 3
- If question asks vertex, also add point if needed: GRAPH_EQUATION: y = -2*x^2 + x | POINT: (0.25, 0.125)

You can have MULTIPLE GRAPH_EQUATION lines, one per question. This is required.

4. Final summary: 💡 總結

No LaTeX ever.
"""

MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]

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
            print(f"[M1] {r.status_code} Attempt {attempt+1}/5")
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
                return r.json()["candidates"][0]["content"]["parts"][0]["text"], "ok"
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

def send_graph_image(jid, equation, q_label):
    try:
        # Try to parse y = ... 
        eq = equation.split("|")[0].replace("y =","").replace("y=","").strip()
        # Make it python eval safe: replace ^ with **
        eq_py = eq.replace("^","**")
        x = np.linspace(-5, 5, 400)
        # Safe eval
        y = eval(eq_py, {"x": x, "np": np, "sin": np.sin, "cos": np.cos, "tan": np.tan, "sqrt": np.sqrt})
        plt.figure()
        plt.plot(x, y)
        plt.grid(True, alpha=0.3)
        plt.title(f"{q_label}: {equation}")
        plt.axhline(0, color='black', linewidth=0.5)
        plt.axvline(0, color='black', linewidth=0.5)
        tmp = f"/tmp/graph_{int(time.time())}.png"
        plt.savefig(tmp, dpi=150, bbox_inches='tight')
        plt.close()
        with open(tmp, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload = {"number": jid, "mediatype": "image", "media": b64, "caption": f"📈 {q_label} 視像化: {equation}"}
        requests.post(url, json=payload, headers=headers, timeout=30)
        print(f"Graph sent {q_label}")
    except Exception as e:
        print(f"Graph fail {e}: {equation}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json or {}
    data = body.get("data", {})
    key = data.get("key", {})
    msg = data.get("message", {})
    jid = key.get("remoteJid")
    push_name = data.get("pushName") or ""
    if not jid or key.get("fromMe"): return jsonify({"ok": True}), 200
    is_group = "@g.us" in jid
    text = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    if is_group:
        low = text.lower()
        if not any(k in low for k in ["lc", "阿sir", "阿 sir", "sir", "老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
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
    if not text and not b64: return jsonify({"ok": True}), 200
    if ("imageMessage" in msg or "documentMessage" in msg) and not b64:
        send_text(jid, "張圖仲 load 緊，麻煩 send 多次新相試試，唔好 forward 舊相 🙏")
        return jsonify({"ok": True}), 200
    answer, _ = call_gemini(text, b64, mime)
    
    # 找出所有 GRAPH_EQUATION (支援多題)
    graphs = re.findall(r"GRAPH_EQUATION:\s*(.+)", answer)
    clean_answer = re.sub(r"GRAPH_EQUATION:\s*.+", "", answer).strip()
    
    if is_group and push_name:
        clean_answer = f"@{push_name} {clean_answer}"
    send_text(jid, clean_answer)
    
    # 逐題 send 視像化
    if graphs:
        time.sleep(1)
        for idx, eq in enumerate(graphs):
            eq = eq.strip()
            q_label = f"Q{idx+1}" if len(graphs)>1 else "本題"
            # 提取 Q label 如果 Gemini 有寫
            # Send Desmos + GeoGebra links
            desmos_link = f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq.split('|')[0])}"
            geogebra_link = f"https://www.geogebra.org/graphing?lang=en&command={urllib.parse.quote(eq.split('|')[0])}"
            send_text(jid, f"📊 {q_label} 視像化：{eq}\nDesmos: {desmos_link}\nGeoGebra: {geogebra_link}")
            # Send 圖
            send_graph_image(jid, eq, q_label)
            time.sleep(1)
    
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir FINAL v7 Visual len={len(GEMINI_API_KEY)}", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
