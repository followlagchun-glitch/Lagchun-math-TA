from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64, time, json
app = Flask(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()
TEACHER_NUMBERS = ["85246447827", "66838738371"]

# === 新增：持久化 ===
STATE_FILE = "/tmp/group_state.json"
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                print(f"[LOAD_STATE] {data}")
                return data
    except Exception as e: print(f"[LOAD_STATE] err {e}")
    return {}

def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(GROUP_STATE, f)
        print(f"[SAVE_STATE] {GROUP_STATE}")
    except Exception as e: print(f"[SAVE_STATE] err {e}")

GROUP_STATE = load_state()
print(f"BOOT FIX_FROMME FINAL PERSIST len={len(GEMINI_API_KEY)} state={GROUP_STATE}")

SYSTEM_PROMPT = """You are LC Sir, Hong Kong DSE Math tutor. Friendly, simple, short, like a real person.
CRITICAL RULES:
- NEVER use $ $ or \\frac \\text or ^ or sqrt().
- MUST use pretty Unicode math only: 次方用 ² ³，開方用 √，分數用 ½ ¼ ¾ 或 ⁄，乘除用 × ÷
- Use *bold* for Q titles, short lines, HK Cantonese口語.
OUTPUT FORMAT: 見到 Q14... 每題用 --- *Q14* 你寫咗... 睇法... 應該點寫... GRAPH_EQUATION: y = ... 最尾 💡 總結 2行
No LaTeX ever."""
MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
def clean_b64(b64):
    if not b64: return None
    b64=b64.strip()
    if "," in b64: b64=b64.split(",")[-1]
    b64=b64.replace("\n","").replace("\r","").replace(" ","")
    b64+="="*(-len(b64)%4)
    return b64
def get_file_base64(data, is_pdf=False):
    time.sleep(3)
    for attempt in range(5):
        try:
            payload={"message": data}
            url=f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
            headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            r=requests.post(url, json=payload, headers=headers, timeout=60)
            if r.status_code in [200,201]:
                m=re.search(r'"base64"\s*:\s*"([^"]{1000,})"', r.text)
                raw=m.group(1) if m else None
                if not raw:
                    try: raw=r.json().get("base64") or r.json().get("data")
                    except: pass
                b64=clean_b64(raw) if raw else None
                if b64 and len(b64)>1000:
                    dec=base64.b64decode(b64, validate=False)
                    mt="application/pdf" if is_pdf or dec[:4]==b'%PDF' else "image/jpeg"
                    return b64, mt
        except Exception as e: print(f"[M1] err {e}")
        if attempt<4: time.sleep(8)
    return None, None
def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    prompt=SYSTEM_PROMPT+f"\n\n學生: {question}"
    last_error=""
    for model in MODELS:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts=[{"text": prompt}]
        if file_b64: parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
        body={"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.3}}
        try:
            r=requests.post(url, json=body, headers=headers, timeout=90)
            if r.status_code==200:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"], "ok"
            last_error=r.text[:800]
        except Exception as e: last_error=str(e)
    return f"Error: {last_error}", "error"
def send_text(jid, text):
    url=f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        for i in range(0, len(text), 3000):
            requests.post(url, json={"number": jid, "text": text[i:i+3000]}, headers=headers, timeout=20)
            time.sleep(0.5)
    except Exception as e: print(f"Send fail {e}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body=request.json or {}
    data=body.get("data", {})
    key=data.get("key", {})
    msg=data.get("message", {})
    jid=key.get("remoteJid")
    push_name=data.get("pushName") or ""
    participant=key.get("participant") or data.get("participant") or ""
    from_me=key.get("fromMe", False)
    if not jid: return jsonify({"ok": True}), 200
    is_group="@g.us" in jid
    text=msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    if not text and "imageMessage" in msg:
        text=msg["imageMessage"].get("caption") or ""
    print(f"[IN] fromMe={from_me} jid={jid} part={participant} text={text[:80]}")

    def is_teacher_user():
        if from_me: return True
        check_id=participant if is_group else jid
        digits=re.sub(r'\D','', check_id)
        for t in TEACHER_NUMBERS:
            if t in digits: return True
        return False

    if is_group:
        if jid not in GROUP_STATE: GROUP_STATE[jid]=False
        low=text.lower().strip()
        if any(k in text for k in ["開放提問","開放發問","/open","開始發問","開放功課"]) or low=="open":
            print(f"[OPEN] is_teacher={is_teacher_user()} from_me={from_me}")
            GROUP_STATE[jid]=True
            save_state()
            send_text(jid, f"✅ 老師已開放提問，依家同學可以問 LC Sir 喇！\n(會一直開放，直到老師打「關閉提問」先會關)\n打法：LC 幫我睇下呢題")
            return jsonify({"ok": True}), 200
        if any(k in text for k in ["關閉提問","關閉發問","/close","停止發問","收工"]) or low=="close":
            GROUP_STATE[jid]=False
            save_state()
            send_text(jid, "🔒 老師已關閉提問，LC Sir 休息中。")
            return jsonify({"ok": True}), 200
        if not GROUP_STATE[jid]:
            if any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) or "imageMessage" in msg or "documentMessage" in msg:
                if not is_teacher_user():
                    if any(k in low for k in ["lc","sir","老師"]):
                        send_text(jid, "⏳ 而家未開放提問，等老師講「開放提問」先可以問 LC Sir 呀～")
                    return jsonify({"ok": True}), 200

    if from_me and not is_group: return jsonify({"ok": True}), 200
    if from_me and is_group:
        if not any(k in text for k in ["開放提問","關閉提問","/open","/close","open","close"]):
            return jsonify({"ok": True}), 200

    if is_group:
        low=text.lower()
        if not any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
            if not msg.get("imageMessage", {}).get("caption"):
                return jsonify({"ok": True}), 200
        text=f"[{push_name} 問]: {text}"

    b64,mime=None,"image/jpeg"
    if "imageMessage" in msg:
        b64,mime=get_file_base64(data, is_pdf=False)
        cap=msg["imageMessage"].get("caption") or ""
        text=(cap or text or "幫我睇下呢份功課").strip()
    elif "documentMessage" in msg:
        b64,mime=get_file_base64(data, is_pdf=True)
        text=(text or "幫我睇下呢份PDF功課").strip()
        mime="application/pdf"
    if not text and not b64: return jsonify({"ok": True}), 200
    if ("imageMessage" in msg or "documentMessage" in msg) and not b64:
        send_text(jid, "張圖仲 load 緊，麻煩 send 多次新相，唔好 forward 舊相 🙏")
        return jsonify({"ok": True}), 200
    answer,_=call_gemini(text, b64, mime)
    graphs=re.findall(r"GRAPH_EQUATION:\s*(.+)", answer)
    clean_answer=re.sub(r"GRAPH_EQUATION:\s*.+", "", answer).strip()
    if is_group and push_name: clean_answer=f"@{push_name} {clean_answer}"
    send_text(jid, clean_answer)
    if graphs:
        time.sleep(0.8)
        for idx, eq in enumerate(graphs):
            eq=eq.strip().split("|")[0].strip()
            q_label=f"Q{idx+1}" if len(graphs)>1 else "本題"
            desmos=f"https://www.desmos.com/calculator?expressions={urllib.parse.quote(eq)}"
            geogebra=f"https://www.geogebra.org/graphing?lang=en&command={urllib.parse.quote(eq)}"
            send_text(jid, f"📊 {q_label} 視像化：{eq}\n👉 Desmos: {desmos}\n👉 GeoGebra: {geogebra}")
            time.sleep(0.5)
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir FINAL PERSIST len={len(GEMINI_API_KEY)} state={GROUP_STATE}", 200
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
