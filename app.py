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

print(f"BOOT FINAL-IMAGE-ONLY len={len(GEMINI_API_KEY)}")

SYSTEM_PROMPT = """
You are LC Sir, Hong Kong DSE Math 專家，團隊 LC Math，10年經驗。Friendly, HK Cantonese。
=== 鐵律0：絕對一致性 ===
- 判斷只有一次，一開頭話 ❌，成段都要保持係 ❌，唔可以中途話其實啱
- 一開頭話 ✅，成段都要讚，唔可以後面又話錯
- 禁止出現「等等...」「哎呀」「其實又啱」「不過」呢類自我推翻字眼
- 計數前先諗好，計啱 11.1% 就係 11.1%，唔好一陣話錯一陣話啱

鐵律2.5：分數寫法
- 如果答案係 11又1/9% 或 11.1% 都當 ✅，唔好挑剔格式，除非真係計錯數 
=== 鐵律1：NEVER LATEX ===
- NEVER用 $ $ $$ $$ \\( \\) \\[ \\] \\frac \\text \\sqrt \\^
- 只能用靚Unicode：² ³ √ ½ ¼ ¾ × ÷
- y = (x+9)/2, h² = 100 - 9 = 91, h = √91

=== 鐵律2：繁體廣東話 ===
- MUST繁體中文ONLY，口語：係, 唔係, 睇下, 呢題
- NEVER簡體

=== 鐵律3：一開頭定生死 ===
- 改功課模式，每條Q第一行必須直接講結果
- 錯：Q1 ❌ 呢題唔啱，答錯咗！
- 啱：Q1 ✅ 呢題啱晒！肯定啱！DSE滿分Level！YA

=== 鐵律4：分題出圖，標明Q ===
- 只要見到 x,y 方程，直線，二次，必須標明Q
- 格式：GRAPH_EQUATION Q1: y=x+1
- 有兩條同Q： GRAPH_EQUATION Q1: y=x+1 和 GRAPH_EQUATION Q1: y=-2x+4 會合併
- 唔同Q分開出，禁止大拼圖

=== 鐵律5：紅圈標記 ===
- 有錯就出：ANNOTATIONS_JSON: [{"x":0.5,"y":0.4}]

=== 鐵律6：PDF一定要改晒所有題，死命令 ===
- 如果收到PDF有5頁，入面有Q1 Q2 Q3 Q4 Q5，你必須由Q1改到Q5，一題都唔可以漏！
- 淨係改Q4 Q5係嚴重失敗！
- 格式：一定要每題獨立一段，Q1... Q2... Q3...
- 就算啱晒都要寫 Q1 ✅ 呢題啱晒！唔可以skip
- 如果真係有10題，每題簡短啲都要寫晒

分兩個模式：
模式A - 問問題 (冇手寫)：
*題目拆解*：DSE咩課題
*DSE概念*：考咩
*技巧*：點諗
*點做*：1. 2.
*答案*：...
💡 DSE伏位
GRAPH_EQUATION Q1: ...

模式B - 改功課 (有手寫) - 必須改晒所有題：
- PDF有幾多題，就要由Q1改到最後一題，一題都唔可以漏！
- 如果見到 Q1,Q2,Q3,Q4,Q5，就要逐條出：
Q1 ✅ ...
Q2 ❌ ...
Q3 ✅ ...
- 絕對唔可以淨係改一題，就算其他啱晒都要講 Q1 ✅ 啱晒
- 如果真係太多題(超過8題)，至少講：Q1 ✅, Q2 ✅, Q3 ❌ ... 最後加 💡 DSE總結
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
    prompt=SYSTEM_PROMPT+f"\n\n學生: {question}"
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
    return f"暫時連唔到", "error"

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

def create_annotated_image(original_b64, annotations):
    try:
        from PIL import Image, ImageDraw
        img_data=base64.b64decode(clean_b64(original_b64))
        img=Image.open(io.BytesIO(img_data)).convert("RGB")
        draw=ImageDraw.Draw(img)
        w,h=img.size
        if not annotations:
            draw.ellipse([w*0.15,h*0.3,w*0.85,h*0.6], outline="red", width=8)
        else:
            for ann in annotations[:6]:
                try:
                    cx,cy=int(w*float(ann.get("x",0.5))),int(h*float(ann.get("y",0.5)))
                    r=int(min(w,h)*0.08)
                    draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline="red", width=6)
                except: continue
        buf=io.BytesIO()
        img.save(buf,"JPEG",quality=92)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[ANNOTATE] {e}")
        return None

def send_image(jid, image_input, caption):
    try:
        if isinstance(image_input, str) and os.path.exists(image_input):
            b64_data=base64.b64encode(open(image_input,"rb").read()).decode()
        else:
            b64_data=clean_b64(image_input)
        if not b64_data or len(b64_data)<1000: return False
        url=f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
        headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload={"number": jid, "mediatype": "image", "media": b64_data, "caption": caption, "fileName": "marked.jpg"}
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
        if msg_id in SEEN_IDS: return
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
            GROUP_STATE[jid]=True; save_state()
        low=text.lower().strip()
        open_keys = ["開放提問","開放發問","開始發問","開始提問","開放功課","/open","開始"]
        close_keys = ["關閉提問","關閉發問","結束提問","結束發問","/close","停止發問","收工","關閉","結束"]
        if any(k in text for k in open_keys) or low in ["open","開始","開放"]:
            if not is_teacher_user(): 
                stop_typing.set(); return
            GROUP_STATE[jid]=True; save_state()
            stop_typing.set()
            send_text(jid, f"{TICK} \n老師已開放提問！依家同學可以問 LC Sir 喇～")
            return
        if any(k in text for k in close_keys) or low in ["close","關閉","結束"]:
            if not is_teacher_user():
                stop_typing.set(); return
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
        stop_typing.set(); return
    if from_me and "@g.us" in jid:
        if not any(k in text for k in ["開放","開始","關閉","結束","/open","/close","open","close","lc","阿sir","老師"]):
            stop_typing.set(); return
    if "@g.us" in jid:
        low=text.lower()
        if not any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
            if not msg.get("imageMessage", {}).get("caption"):
                stop_typing.set(); return
        text=f"[{push_name} 問]: {text}"

    b64,mime=None,"image/jpeg"
    is_image_msg = "imageMessage" in msg
    is_pdf_msg = "documentMessage" in msg
    if is_image_msg:
        b64,mime=get_file_base64(data, is_pdf=False)
        cap=msg["imageMessage"].get("caption") or ""
        text=(cap or text or "幫我睇下呢份功課").strip()
    elif is_pdf_msg:
        b64,mime=get_file_base64(data, is_pdf=True)
        text=(text or "幫我睇下呢份PDF功課").strip()
        mime="application/pdf"
    if not text and not b64:
        stop_typing.set(); return
    if (is_image_msg or is_pdf_msg) and not b64:
        stop_typing.set()
        send_text(jid, "張圖仲 load 緊，麻煩 send 多次新相，唔好 forward 舊相 🙏")
        return

    answer,_=call_gemini(text, b64, mime)
    stop_typing.set()

    annotations=[]
    m_ann=re.search(r"ANNOTATIONS_JSON:\s*(\[.*?\])", answer, re.DOTALL)
    if m_ann:
        try: annotations=json.loads(m_ann.group(1))
        except: pass

    graphs=re.findall(r"GRAPH_EQUATION(?:\s+Q\d+)?:\s*(.+)", answer)
    # 兼容新格式 Q1: y=x+1
    full_q_graphs=re.findall(r"GRAPH_EQUATION\s+(Q\d+):\s*(.+)", answer, re.I)
    
    clean_answer=re.sub(r"GRAPH_EQUATION.*", "", answer).strip()
    clean_answer=re.sub(r"ANNOTATIONS_JSON:.*", "", clean_answer, flags=re.DOTALL).strip()
    if "@g.us" in jid and push_name: clean_answer=f"@{push_name} {clean_answer}"
    
    send_text(jid, clean_answer)

    # === 紅圈 + 合併圖 只限相片功課 ===
    is_image_homework = is_image_msg

    if is_image_homework:
        # 1. 紅圈
        if b64 and mime!="application/pdf" and CROSS in clean_answer:
            img_b64=create_annotated_image(b64, annotations)
            if img_b64:
                time.sleep(0.6)
                send_image(jid, img_b64, f"{CROSS} 睇圖，紅圈就係錯嘅位")

        # 2. 合併圖 - 分Q出圖
        if graphs or full_q_graphs:
            from collections import defaultdict
            q_map = defaultdict(list)
            # 處理 Q1: y=x+1 格式
            for q_label, eq in full_q_graphs:
                q_map[q_label.upper()].append(eq.strip())
            # 處理舊格式但冇Q的，當 Q1
            if graphs and not full_q_graphs:
                for eq in graphs:
                    eq=eq.strip().split("|")[0].strip()
                    if len(eq)>2:
                        q_map["Q1"].append(eq)

            for q_label, eq_list in q_map.items():
                uniq=[]
                seen=set()
                for e in eq_list:
                    k=e.replace(" ","")
                    if k not in seen and len(e)>2:
                        seen.add(k); uniq.append(e)
                if not uniq: continue
                path=download_combined_graph(uniq, out_path=f"/tmp/{q_label}.jpg")
                if path:
                    time.sleep(0.5)
                    send_image(jid, path, f"📊 {q_label} 視像化: {', '.join(uniq)}")
                    expr_list=[{"latex": e} for e in uniq]
                    desmos_url=f"https://www.desmos.com/calculator?expressions_list={urllib.parse.quote(json.dumps(expr_list))}"
                    send_text(jid, f"{q_label} 互動版:\n{desmos_url}")
    else:
        if graphs or full_q_graphs:
            print(f"[SKIP GRAPH+ANNOTATION] PDF/文字功課，唔出圖，避免大拼圖")

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
def home(): return f"LC Sir FINAL-IMAGE-ONLY {TICK} len={len(GEMINI_API_KEY)}", 200
@app.route("/health", methods=["GET"])
def health(): return "ok", 200
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
