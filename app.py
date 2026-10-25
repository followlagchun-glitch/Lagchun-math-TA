from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64, time, json, threading, io
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

TICK = "\u2705"
CROSS = "\u274c"

print(f"BOOT TYPING-FIX DSE FINAL len={len(GEMINI_API_KEY)} state={GROUP_STATE}")

# 唔用 f-string，避免 DSE課題 NameError
SYSTEM_PROMPT = """
You are LC Sir, Hong Kong DSE Math 專家，團隊 LC Math。Friendly, HK Cantonese。

NEVER LATEX - VERY STRICT:
- NEVER use $ $ or $$ $$ or \\( \\) or \\[ \\] or \\frac \\text \\sqrt \\^
- Use pretty Unicode ONLY: ² ³ √ ½ ¼ ¾ × ÷
- y = (x+9)/2, h² = 100 - 9 = 91, h = √91
- 絕對唔可以用 LaTeX，否則失敗

LANGUAGE - VERY STRICT:
- MUST Traditional Chinese ONLY (繁體中文)
- MUST HK Cantonese口語：係, 唔係, 睇下, 呢度
- NEVER Simplified Chinese

CRITICAL - 每條一開頭定生死：
- 改功課模式，每條第一行必須直接講啱定錯
- 錯：Q1 ❌ 呢題肯定唔啱，答錯咗喎！
- 啱：Q1 ✅ 呢題啱晒！肯定啱！DSE滿分！
- 唔可以先講其他廢話，必須第一行定生死

分兩個模式：

模式A - 問問題模式 (只有題目，冇手寫答案)：
- 絕對唔可以講 啱嘅地方 / 錯嘅地方
- 格式：
*題目拆解*：DSE咩課題...
*DSE概念*：考咩 Concept...
*技巧*：DSE點諗...
*點做*：
1. ...
2. ...
*答案*：...
💡 DSE伏位：...

模式B - 改功課模式 (有學生手寫步驟)：
---
Q1 ❌ 呢題肯定唔啱，DSE會0分喎！
DSE課題：例如 概率
✅ 啱嘅地方：
- 步驟清晰，公式用啱
❌ 錯 / 漏嘅地方：
- 第二行抄錯
💬 DSE評語：一句人性化 + DSE marking角度
💡 應該點寫：h² = 100 - 9 = 91，h = √91
💡 DSE概念重溫：...

Q2 ✅ 呢題啱晒！肯定啱！

最後加：
GRAPH_EQUATION: x-2y+9=0 (如果有直線先加)
最後 💡 DSE總結 2行

判斷：有手寫=模式B，冇=模式A
"""

MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-1.5-flash", "gemini-3.5-flash-lite"]

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
                    try: 
                        j=r.json()
                        raw=j.get("base64") or (j.get("data",{}).get("base64") if isinstance(j.get("data"),dict) else j.get("data"))
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
    prompt=SYSTEM_PROMPT+f"\n\n學生: {question}\n記得：一開頭定生死，繁體，唔用LaTeX，DSE專業"
    last_error=""
    for model in MODELS:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts=[{"text": prompt}]
        if file_b64: parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
        body={"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.4}}
        try:
            r=requests.post(url, json=body, headers=headers, timeout=120)
            if r.status_code==200:
                txt=r.json()["candidates"][0]["content"]["parts"][0]["text"]
                txt=txt.replace("对","對").replace("错","錯")
                return txt, "ok"
            last_error=r.text[:800]
        except Exception as e: last_error=str(e)
    return f"暫時連唔到，稍後再試: {last_error[:200]}", "error"

def send_typing(jid, stop_event):
    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": jid, "presence": "composing", "delay": 25000}
    while not stop_event.is_set():
        try: requests.post(url, json=payload, headers=headers, timeout=10)
        except: pass
        for _ in range(25):
            if stop_event.is_set(): break
            time.sleep(0.1)

def send_text(jid, text):
    url=f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        text = re.sub(r"\$+.*?\$+", "", text)
        text = re.sub(r"\\frac\{.*?\}\{.*?\}", "(a/b)", text)
        text = re.sub(r"\\[a-zA-Z]+", "", text)
        for i in range(0, len(text), 3000):
            requests.post(url, json={"number": jid, "text": text[i:i+3000]}, headers=headers, timeout=20)
            time.sleep(0.5)
    except Exception as e: print(f"Send fail {e}")

def send_image(jid, image_path, caption):
    try:
        b64_data=base64.b64encode(open(image_path,"rb").read()).decode()
        url=f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
        headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload={"number": jid, "mediatype": "image", "media": b64_data, "caption": caption, "fileName": "graph.jpg"}
        r=requests.post(url, json=payload, headers=headers, timeout=30)
        return r.status_code in [200,201]
    except Exception as e:
        print(f"[SEND IMG] {e}")
        return False

def download_combined_graph(equations_list, out_path="/tmp/combined.jpg"):
    try:
        import numpy as np, sympy as sp
        colors=["rgb(225,29,72)","rgb(45,112,179)","rgb(22,163,74)","rgb(234,179,8)"]
        datasets=[]
        for idx, eq in enumerate(equations_list):
            points=[]
            try:
                eq_sym=eq.replace("²","**2").replace("³","**3").replace("^","**")
                x,y=sp.symbols('x y')
                if "=" in eq_sym:
                    left,right=eq_sym.split("=",1)
                    expr=sp.sympify(left)-sp.sympify(right)
                    sol=sp.solve(expr,y)
                    if sol:
                        y_expr=sol[0]
                        for xv in np.linspace(-10,10,300):
                            try:
                                yv=float(y_expr.subs(x,xv))
                                if abs(yv)<15: points.append({"x":float(xv),"y":float(yv)})
                            except: pass
            except: pass
            if points:
                datasets.append({"label":eq,"data":points,"showLine":True,"fill":False,"borderColor":colors[idx%len(colors)],"borderWidth":3,"pointRadius":0})
        if not datasets: return None
        chart_config={"type":"scatter","data":{"datasets":datasets},"options":{"title":{"display":True,"text":" + ".join(equations_list)[:80]}}}
        url=f"https://quickchart.io/chart?c={urllib.parse.quote(json.dumps(chart_config))}&width=800&height=600&backgroundColor=white&format=jpg"
        r=requests.get(url,timeout=25)
        if r.status_code==200 and len(r.content)>1500:
            open(out_path,"wb").write(r.content)
            return out_path
    except Exception as e:
        print(f"[GRAPH] {e}")
    return None

def do_work(jid, text, push_name, participant, from_me, msg, data, msg_id):
    with LOCK:
        now=time.time()
        for k in list(SEEN_IDS.keys()):
            if now - SEEN_IDS[k] > 300: del SEEN_IDS[k]
        if msg_id in SEEN_IDS:
            return
        SEEN_IDS[msg_id]=now

    stop_typing = threading.Event()
    threading.Thread(target=send_typing, args=(jid, stop_typing), daemon=True).start()

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
            send_text(jid, f"{TICK} \n老師已開放提問！依家同學可以問 LC Sir 喇～")
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

    answer,_=call_gemini(text, b64, mime)
    stop_typing.set()

    graphs=re.findall(r"GRAPH_EQUATION:\s*(.+)", answer)
    clean_answer=re.sub(r"GRAPH_EQUATION:\s*.+", "", answer).strip()
    if "@g.us" in jid and push_name: clean_answer=f"@{push_name} {clean_answer}"
    send_text(jid, clean_answer)

    if graphs:
        clean_graphs=[]
        seen=set()
        for eq in graphs:
            eq=eq.strip().split("|")[0].strip()
            k=eq.replace(" ","")
            if k not in seen and len(eq)>2:
                seen.add(k)
                clean_graphs.append(eq)
        if clean_graphs:
            path=download_combined_graph(clean_graphs, out_path="/tmp/combined.jpg")
            if path:
                time.sleep(0.5)
                send_image(jid, path, f"📊 合併圖: {', '.join(clean_graphs)}")
                expr_list=[{"latex": e, "color": "#c82a54" if i==0 else "#2d70b3"} for i,e in enumerate(clean_graphs)]
                desmos_url=f"https://www.desmos.com/calculator?expressions_list={urllib.parse.quote(json.dumps(expr_list))}"
                send_text(jid, f"互動版睇圖:\n{desmos_url}")

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
    threading.Thread(target=do_work, args=(jid, text, push_name, participant, from_me, msg, data, msg_id), daemon=True).start()
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home(): return f"LC Sir DSE FINAL {TICK} len={len(GEMINI_API_KEY)}", 200
@app.route("/health", methods=["GET"])
def health(): return "ok", 200
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
