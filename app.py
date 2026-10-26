# LC SIR V10.2-REAL-HANDWRITE-NO-DESMOS - V10.1 進化版
# Fix: 批改功課唔出Desmos + 真手寫斜體 + 廣東話+英文
from flask import Flask, request, jsonify
import os, requests, re, urllib.parse, base64, time, json, threading, io, random
app = Flask(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()
TEACHER_NUMBERS = ["85246447827"]

VERSION = "V10.2-CANTONESE-HANDWRITE-NODESMOS"
STATE_FILE = "/tmp/group_state.json"
MEMORY_FILE = "/tmp/lc_memory.json"
ENABLE_GRAPH_FOR_HOMEWORK = False  # 力 Sir 要求：改功課唔出 Desmos

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

def load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
    except: pass
    return []
def save_memory(mem):
    try:
        with open(MEMORY_FILE, "w") as f:
            json.dump(mem[-100:], f)
    except: pass

GROUP_STATE = load_state()
LC_MEMORY = load_memory()
SEEN_IDS = {}
LOCK = threading.Lock()

TICK = "\u2705"
CROSS = "\u274c"
ENABLE_COMMENTS = True

print(f"BOOT {VERSION} len={len(GEMINI_API_KEY)} mem={len(LC_MEMORY)}")

SYSTEM_PROMPT = """
You are LC Sir, Hong Kong DSE Math 專家，團隊 LC Math，10年經驗。Friendly, HK Cantonese + English term。
=== 鐵律0：絕對一致性 ===
- 判斷只有一次，一開頭話 ❌，成段都要保持係 ❌
- 禁止「等等...」「其實又啱」「不過」

鐵律2.5：分數寫法
- 11又1/9% 或 11.1% 都當 ✅

=== 鐵律1：NEVER LATEX ===
- NEVER用 $ $ $$ $$ \\( \\) \\[ \\] \\frac \\text \\sqrt \\^
- 只能用靚Unicode：² ³ √ ½ ¼ ¾ × ÷

=== 鐵律2：廣東話+英文術語 ===
- MUST繁體廣東話為主，technical term用英文：vertex, inequality, region, boundary, k value
- 例：呢度k≤0 錯咗，check vertex (0,0) 就知
- NEVER簡體

=== 鐵律3：一開頭定生死 ===
- 改功課模式，每條Q第一行必須直接講結果
- 錯：Q33 ❌ 呢題唔啱，k≤0錯咗
- 啱：Q33 ✅ 呢題啱晒！

=== 鐵律4：分題出圖，標明Q ===
- 問問題模式先可以出 GRAPH_EQUATION，改功課模式唔出圖
- 格式：GRAPH_EQUATION Q1: y=x+1

=== 鐵律5：紅圈+藍字批改 - 真手寫廣東話 ===
- 有錯就出：ANNOTATIONS_JSON: [{"x":0.52,"y":0.41,"text":"k<=0 錯，x=0 check vertex"}]
- text必須係 廣東話+英文term，15字內，越短越好，ASCII為主
- 例子：k<=8 錯，試 (0,0) / II, III 錯，region睇錯邊

=== 鐵律6：PDF一定要改晒所有題 ===
- 有幾多題改幾多題，唔可以skip
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
                return txt.replace("对","對").replace("错","錯"), "ok"
        except: pass
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
        from PIL import Image, ImageDraw, ImageFont
        img_data=base64.b64decode(clean_b64(original_b64))
        img=Image.open(io.BytesIO(img_data)).convert("RGB")
        draw=ImageDraw.Draw(img)
        w,h=img.size
        if not annotations: return None
        try:
            # 搵斜體，似手寫
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            ]
            font_path = None
            for p in candidates:
                if os.path.exists(p):
                    font_path = p; break
            font_size = int(h*0.022)  # 再細啲，唔遮圖
            font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        except:
            font = ImageFont.load_default()
            font_size = 20

        def draw_handwrite(x, y, text):
            # 真手寫：藍色原子筆 + 抖動 + 輕微斜
            cur_x = x
            for ch in text:
                jx = random.randint(-1,1)
                jy = random.randint(-1,1)
                # 筆壓深淺
                draw.text((cur_x+jx, y+jy), ch, fill=(20,60,160), font=font)
                bw = draw.textbbox((0,0), ch, font=font)
                cur_x += (bw[2]-bw[0]) * 0.92

        for ann in annotations[:3]:
            try:
                x=float(ann.get("x",0.5)); y=float(ann.get("y",0.5))
                raw_txt=ann.get("text","").strip()
                if not (0.02 < x < 0.98 and 0.02 < y < 0.98): continue
                cx,cy=int(w*x),int(h*y)
                r=int(min(w,h)*0.038)  # 更準更細
                # 手畫紅圈，唔係完美圓
                for i in range(2):
                    ox = random.randint(-2,2); oy = random.randint(-2,2)
                    draw.ellipse([cx-r+ox,cy-r+oy,cx+r+ox,cy+r+oy], outline=(220,0,0), width=3)

                if raw_txt and ENABLE_COMMENTS:
                    txt = raw_txt.replace("√","sqrt").replace("²","^2")[:35].strip()
                    txt = ''.join(c for c in txt if ord(c) < 128 or '\u4e00' <= c <= '\u9fff')[:35]
                    if not txt: continue
                    tx = cx + r + 8
                    ty = cy - 5
                    if tx + 180 > w: tx = max(5, cx - r - 160)
                    if ty < 5: ty = cy + r + 5
                    bbox = draw.textbbox((tx,ty), txt, font=font)
                    pad=5
                    # 白底，唔搶眼
                    draw.rounded_rectangle([bbox[0]-pad, bbox[1]-pad-1, bbox[2]+pad, bbox[3]+pad+1], radius=5, fill=(255,255,255,230), outline=(80,120,200), width=1)
                    draw_handwrite(tx, ty, txt)
            except: continue

        buf=io.BytesIO()
        img.save(buf,"JPEG",quality=92)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[ANNOTATE] {e}"); return None

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
    global LC_MEMORY
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
            if not is_teacher_user(): stop_typing.set(); return
            GROUP_STATE[jid]=True; save_state(); stop_typing.set()
            send_text(jid, f"{TICK} \n老師已開放提問！依家同學可以問 LC Sir 喇～"); return
        if any(k in text for k in close_keys) or low in ["close","關閉","結束"]:
            if not is_teacher_user(): stop_typing.set(); return
            GROUP_STATE[jid]=False; save_state(); stop_typing.set()
            send_text(jid, "🔒 \n老師已關閉提問，LC Sir 休息中～"); return
        if not GROUP_STATE[jid]:
            if any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) or "imageMessage" in msg or "documentMessage" in msg:
                if not is_teacher_user():
                    stop_typing.set()
                    if any(k in low for k in ["lc","sir","老師"]):
                        send_text(jid, "⏳ 而家未開放提問，等老師講「開始提問」先可以問 LC Sir 呀～")
                    return
    if from_me and not is_group: stop_typing.set(); return
    if from_me and "@g.us" in jid:
        if not any(k in text for k in ["開放","開始","關閉","結束","/open","/close","open","close","lc","阿sir","老師"]):
            stop_typing.set(); return
    if "@g.us" in jid:
        low=text.lower()
        if not any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
            if not msg.get("imageMessage", {}).get("caption"): stop_typing.set(); return
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
    if not text and not b64: stop_typing.set(); return
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
    full_q_graphs=re.findall(r"GRAPH_EQUATION\s+(Q\d+):\s*(.+)", answer, re.I)
    clean_answer=re.sub(r"GRAPH_EQUATION.*", "", answer).strip()
    clean_answer=re.sub(r"ANNOTATIONS_JSON:.*", "", clean_answer, flags=re.DOTALL).strip()
    if "@g.us" in jid and push_name: clean_answer=f"@{push_name} {clean_answer}"
    send_text(jid, clean_answer)
    try:
        with LOCK:
            LC_MEMORY.append({"t":int(time.time()), "q":text[:200], "a":clean_answer[:300], "jid":jid})
            save_memory(LC_MEMORY)
    except: pass

    is_image_homework = is_image_msg
    if is_image_homework:
        # V10.2: 改功課唔出 Desmos
        if not ENABLE_GRAPH_FOR_HOMEWORK:
            print(f"[SKIP DESMOS] Homework mode, no graph")
        if b64 and mime!="application/pdf" and CROSS in clean_answer:
            img_b64=create_annotated_image(b64, annotations)
            if img_b64:
                time.sleep(0.6)
                send_image(jid, img_b64, f"{CROSS} 睇圖，紅圈就係錯嘅位")
        # 只有問問題先出圖，改功課唔出
        if ENABLE_GRAPH_FOR_HOMEWORK and (graphs or full_q_graphs):
            from collections import defaultdict
            q_map = defaultdict(list)
            for q_label, eq in full_q_graphs:
                q_map[q_label.upper()].append(eq.strip())
            if graphs and not full_q_graphs:
                for eq in graphs:
                    eq=eq.strip().split("|")[0].strip()
                    if len(eq)>2: q_map["Q1"].append(eq)
            for q_label, eq_list in q_map.items():
                uniq=[]; seen=set()
                for e in eq_list:
                    k=e.replace(" ","")
                    if k not in seen and len(e)>2:
                        seen.add(k); uniq.append(e)
                if not uniq: continue
                path=download_combined_graph(uniq, out_path=f"/tmp/{q_label}.jpg")
                if path:
                    time.sleep(0.5)
                    send_image(jid, path, f"📊 {q_label} 視像化: {', '.join(uniq)}")
    else:
        # 文字問問題先出 Desmos
        if graphs or full_q_graphs:
            from collections import defaultdict
            q_map = defaultdict(list)
            for q_label, eq in full_q_graphs:
                q_map[q_label.upper()].append(eq.strip())
            if graphs and not full_q_graphs:
                for eq in graphs:
                    eq=eq.strip().split("|")[0].strip()
                    if len(eq)>2: q_map["Q1"].append(eq)
            for q_label, eq_list in q_map.items():
                uniq=[]; seen=set()
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
def home(): return f"LC Sir {VERSION} {TICK} mem={len(LC_MEMORY)}", 200
@app.route("/health", methods=["GET"])
def health(): return "ok", 200
@app.route("/memory", methods=["GET"])
def memory_view(): return jsonify({"version":VERSION, "count":len(LC_MEMORY), "last":LC_MEMORY[-5:]}), 200
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
