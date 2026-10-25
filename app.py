from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64, time, json, threading
app = Flask(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()
TEACHER_NUMBERS = ["85246447827"]

STATE_FILE = "/tmp/group_state.json"
def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
    except: pass
    return {}
def save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(GROUP_STATE, f)
    except Exception as e:
        print(f"[SAVE_STATE] err {e}")

GROUP_STATE = load_state()
SEEN_IDS = {}
LOCK = threading.Lock()

print(f"BOOT TYPING-FIX len={len(GEMINI_API_KEY)} state={GROUP_STATE}")

SYSTEM_PROMPT = """You are LC Sir, Hong Kong DSE Math tutor. Friendly, simple, short, like a real person.
CRITICAL RULES:
- NEVER use $ $ or \\frac \\text or ^ or sqrt().
- MUST use pretty Unicode math only: 次方用 ² ³，開方用 √，分數用 ½ ¼ ¾ 或 ⁄，乘除用 × ÷
- Use *bold* for Q titles, short lines, HK Cantonese口語.
- No LaTeX ever.

OUTPUT FORMAT - PDF功課改卷模式:
如果全對：
---
*Q1* ✅ 全對！做得好靚，繼續保持！
如果有錯：
---
*Q1*
✅ 啱嘅地方：
- ...
❌ 錯 / 漏嘅地方：
- ...
💬 Comment：一句講整體
💡 應該點寫：h² = 100 - 9 = 91，h = √91
GRAPH_EQUATION: 如果有圖就加 y = ...
最後 💡 總結 2行
"""

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

def send_typing(jid, stop_event):
    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": jid, "presence": "composing"}
    while not stop_event.is_set():
        try: 
            requests.post(url, json=payload, headers=headers, timeout=10)
        except: pass
        # 每2.5秒送一次 composing，先可以 keep住 typing...
        for _ in range(25):
            if stop_event.is_set(): break
            time.sleep(0.1)

def send_text(jid, text):
    url=f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        for i in range(0, len(text), 3000):
            requests.post(url, json={"number": jid, "text": text[i:i+3000]}, headers=headers, timeout=20)
            time.sleep(0.5)
    except Exception as e: print(f"Send fail {e}")

def do_work(jid, text, push_name, participant, from_me, msg, data, msg_id):
    with LOCK:
        now=time.time()
        for k in list(SEEN_IDS.keys()):
            if now - SEEN_IDS[k] > 300: del SEEN_IDS[k]
        if msg_id in SEEN_IDS:
            print(f"[SKIP AUTO-DUP] {msg_id}")
            return
        SEEN_IDS[msg_id]=now

    # ===== 重點：typing 一入嚟就開始，唔係等 load 圖先 =====
    stop_typing = threading.Event()
    typing_thread = threading.Thread(target=send_typing, args=(jid, stop_typing), daemon=True)
    typing_thread.start()

    def is_teacher_user():
        if from_me: return True
        digits=re.sub(r'\D','', participant if "@g.us" in jid else jid)
        return any(t in digits for t in TEACHER_NUMBERS)

    is_group="@g.us" in jid
    if is_group:
        if jid not in GROUP_STATE:
            GROUP_STATE[jid]=True
            save_state()
        low=text.lower().strip()
        open_keys = ["開放提問","開放發問","開始發問","開始提問","開放功課","/open","開始"]
        close_keys = ["關閉提問","關閉發問","結束提問","結束發問","/close","停止發問","收工","關閉","結束"]
        if any(k in text for k in open_keys) or low in ["open","開始","開放"]:
            if not is_teacher_user(): 
                stop_typing.set()
                return
            GROUP_STATE[jid]=True; save_state()
            stop_typing.set()
            send_text(jid, "✅ \n老師已開放提問！依家同學可以問 LC Sir 喇～\n👉 打法：LC 幫我睇下呢題 + 相\n(會一直開住，直到老師打「關閉提問」先關)")
            return
        if any(k in text for k in close_keys) or low in ["close","關閉","結束"]:
            if not is_teacher_user():
                stop_typing.set()
                return
            GROUP_STATE[jid]=False; save_state()
            stop_typing.set()
            send_text(jid, "🔒 \n老師已關閉提問，LC Sir 休息中～")
            return
        if not GROUP_STATE[jid]:
            if any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) or "imageMessage" in msg or "documentMessage" in msg:
                if not is_teacher_user():
                    stop_typing.set()
                    if any(k in low for k in ["lc","sir","老師"]):
                        send_text(jid, "⏳ 而家未開放提問，等老師講「開始提問」先可以問 LC Sir 呀～")
                    return

    if from_me and not is_group:
        stop_typing.set()
        return
    if from_me and "@g.us" in jid:
        if not any(k in text for k in ["開放","開始","關閉","結束","/open","/close","open","close","lc","阿sir","老師"]):
            stop_typing.set()
            return
    if "@g.us" in jid:
        low=text.lower()
        if not any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
            if not msg.get("imageMessage", {}).get("caption"):
                stop_typing.set()
                return
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
    if not text and not b64:
        stop_typing.set()
        return
    if ("imageMessage" in msg or "documentMessage" in msg) and not b64:
        stop_typing.set()
        send_text(jid, "張圖仲 load 緊，麻煩 send 多次新相，唔好 forward 舊相 🙏")
        return

    # 呢度唔使再開 typing，因為上面已經開咗
    answer,_=call_gemini(text, b64, mime)
    stop_typing.set()

    graphs=re.findall(r"GRAPH_EQUATION:\s*(.+)", answer)
    clean_answer=re.sub(r"GRAPH_EQUATION:\s*.+", "", answer).strip()
    if "@g.us" in jid and push_name: clean_answer=f"@{push_name} {clean_answer}"
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
    text=msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    if not text and "imageMessage" in msg: text=msg["imageMessage"].get("caption") or ""
    msg_id = key.get("id") or str(data.get("id") or "") or f"no-id-{int(time.time()*1000)}"
    print(f"[IN] id={msg_id} fromMe={from_me} jid={jid} text={text[:80]}")
    threading.Thread(target=do_work, args=(jid, text, push_name, participant, from_me, msg, data, msg_id), daemon=True).start()
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home(): return f"LC Sir TYPING len={len(GEMINI_API_KEY)}", 200
@app.route("/health", methods=["GET"])
def health(): return "ok", 200
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
