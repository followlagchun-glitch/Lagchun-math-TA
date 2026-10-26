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
            with open(STATE_FILE, "r") as f: return json.load(f)
    except: pass
    return {}
def save_state():
    try:
        with open(STATE_FILE, "w") as f: json.dump(GROUP_STATE, f)
    except: pass
GROUP_STATE = load_state()
SEEN_IDS = {}
LOCK = threading.Lock()
TICK = "\u2705"
CROSS = "\u274c"
print(f"BOOT FINAL-ACCURATE-CIRCLE len={len(GEMINI_API_KEY)}")

SYSTEM_PROMPT = """
You are LC Sir, HK DSE Math 專家。繁體廣東話，NEVER LATEX。

鐵律1：NEVER LATEX 用 y=(x+9)/2, √, ² × ÷
鐵律2：每題第一行定生死 Q1 ❌ 呢題肯定唔啱 / Q1 ✅ 啱晒
鐵律3：PDF一定要改晒所有題 Q1到最後一題，唔可以淨改兩題

鐵律4：分題出圖
無論相定PDF，只要有方程必須出 TAG： GRAPH_EQUATION Q1: y=x+1
後台會決定相片先畫，PDF唔畫，避免大拼圖

鐵律5：紅圈坐標極準，唔準寧願唔出
- 格式：ANNOTATIONS_JSON: [{"x":0.52,"y":0.63,"label":"20"}]
- x=0最左 x=1最右 y=0最頂 y=1最底，必須圈住學生手寫錯嘅數字本身，例如圈住 "20" "-3" "-1" "3.0625"
- 絕對唔可以圈空白、圈邊位、圈成行
- 要報埋 label 即係錯咗咩字，例如 "20" 
- 如果睇唔準，唔好出ANNOTATIONS_JSON

模式A - 純問：
*題目拆解* *概念* *點做* *答案* 💡 伏位 + GRAPH_EQUATION Q1: ...

模式B - 改功課：
---
Q1 ✅/❌ 定生死
DSE課題...
✅ 啱嘅...
❌ 錯嘅... 精準指出錯邊個數
💬 評語
💡 點寫啱
---
最後 💡 總結 + GRAPH_EQUATION（如有）
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
    prompt=SYSTEM_PROMPT+f"\n\n學生: {question}\n\n死命令：1.PDF改晒所有題 2.紅圈x,y一定要圈住手寫錯字本身，唔係空白！"
    for model in MODELS:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts=[{"text": prompt}]
        if file_b64: parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
        body={"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.2, "maxOutputTokens": 8192}}
        try:
            r=requests.post(url, json=body, headers=headers, timeout=120)
            if r.status_code==200:
                txt=r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return txt.replace("对","對"), "ok"
        except Exception as e: print(e)
    return "暫時連唔到", "error"

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
    url=f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}" if False else f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        text = re.sub(r"\$+.*?\$+", "", text)
        for i in range(0, len(text), 3500):
            requests.post(url, json={"number": jid, "text": text[i:i+3500]}, headers=headers, timeout=20)
            time.sleep(0.4)
    except Exception as e: print(f"Send fail {e}")

def create_annotated_image(original_b64, annotations):
    # FIX: 冇坐標就唔圈，唔再圈中間空白
    if not annotations:
        print("[ANNOTATE] No coords, skip to avoid empty spot")
        return None
    try:
        from PIL import Image, ImageDraw
        img_data=base64.b64decode(clean_b64(original_b64))
        img=Image.open(io.BytesIO(img_data)).convert("RGB")
        draw=ImageDraw.Draw(img, "RGBA")
        w,h=img.size
        for ann in annotations[:3]:
            try:
                x=float(ann.get("x",0.5)); y=float(ann.get("y",0.5))
                if not (0.05 < x < 0.95 and 0.05 < y < 0.95):
                    continue
                cx,cy=int(w*x),int(h*y)
                r=int(min(w,h)*0.08)
                # 黃底紅圈，乜背景都見到
                draw.ellipse([cx-r-6,cy-r-6,cx+r+6,cy+r+6], fill=(255,255,0,90), outline="yellow", width=4)
                draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline=(255,0,0), width=7)
                label=ann.get("label","")
                if label:
                    draw.text((cx+r+5, cy-r-10), str(label), fill="red")
            except Exception as e:
                print(f"ann err {e}")
                continue
        buf=io.BytesIO()
        img.save(buf,"JPEG",quality=95)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[ANNOTATE] {e}")
        return None

def download_combined_graph(equations_list, out_path="/tmp/combined.jpg"):
    try:
        import numpy as np, sympy as sp
        colors=["rgb(225,29,72)","rgb(45,112,179)"]
        datasets=[]
        x,y=sp.symbols('x y')
        for idx, eq in enumerate(equations_list):
            eq_sym=eq.replace("²","**2").replace("³","**3").replace("^","**")
            try:
                if "=" in eq_sym:
                    left,right=eq_sym.split("=",1)
                    expr=sp.sympify(left)-sp.sympify(right)
                    for sol in sp.solve(expr, y)[:2]:
                        pts=[]
                        for xv in np.linspace(-12,12,350):
                            try:
                                yv=float(sol.subs(x,xv))
                                if abs(yv)<18: pts.append({"x":float(xv),"y":float(yv)})
                            except: pass
                        if pts:
                            datasets.append({"label":eq,"data":pts,"showLine":True,"fill":False,"borderColor":colors[idx%len(colors)],"borderWidth":3,"pointRadius":0})
            except: pass
        if not datasets: return None
        chart_config={"type":"scatter","data":{"datasets":datasets},"options":{"scales":{"xAxes":[{"type":"linear","position":"bottom"}]},"title":{"display":True,"text":" + ".join(equations_list)[:80]}}}
        url=f"https://quickchart.io/chart?c={urllib.parse.quote(json.dumps(chart_config))}&width=800&height=600&backgroundColor=white&format=jpg"
        r=requests.get(url,timeout=25)
        if r.status_code==200 and len(r.content)>1500:
            open(out_path,"wb").write(r.content)
            return out_path
    except Exception as e: print(f"[GRAPH] {e}")
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
        if jid not in GROUP_STATE: GROUP_STATE[jid]=True; save_state()
        low=text.lower().strip()
        open_keys = ["開放提問","開放發問","開始發問","開始提問","開放功課","/open","開始"]
        close_keys = ["關閉提問","關閉發問","結束提問","結束發問","/close","停止發問","收工","關閉","結束"]
        if any(k in text for k in open_keys) or low in ["open","開始","開放"]:
            if not is_teacher_user(): stop_typing.set(); return
            GROUP_STATE[jid]=True; save_state(); stop_typing.set(); send_text(jid, f"{TICK} \n老師已開放提問！"); return
        if any(k in text for k in close_keys) or low in ["close","關閉","結束"]:
            if not is_teacher_user(): stop_typing.set(); return
            GROUP_STATE[jid]=False; save_state(); stop_typing.set(); send_text(jid, "🔒 \n老師已關閉提問"); return
        if not GROUP_STATE[jid]:
            if any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) or "imageMessage" in msg or "documentMessage" in msg:
                if not is_teacher_user():
                    stop_typing.set()
                    if any(k in low for k in ["lc","sir","老師"]): send_text(jid, "⏳ 而家未開放提問")
                    return
    if from_me and not is_group: stop_typing.set(); return
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
        stop_typing.set(); send_text(jid, "張圖仲 load 緊，麻煩 send 多次新相"); return
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
    is_image_homework = is_image_msg
    if is_image_homework:
        if b64 and CROSS in clean_answer:
            img_b64=create_annotated_image(b64, annotations)
            if img_b64:
                time.sleep(0.6)
                send_image(jid, img_b64, f"{CROSS} 睇圖，紅圈就係錯嘅位")
        if graphs or full_q_graphs:
            from collections import defaultdict
            q_map = defaultdict(list)
            for q_label, eq in full_q_graphs: q_map[q_label.upper()].append(eq.strip())
            if graphs and not full_q_graphs:
                for eq in graphs:
                    eq=eq.strip().split("|")[0].strip()
                    if len(eq)>2: q_map["Q1"].append(eq)
            for q_label, eq_list in q_map.items():
                uniq=[]; seen=set()
                for e in eq_list:
                    k=e.replace(" ","")
                    if k not in seen and len(e)>2: seen.add(k); uniq.append(e)
                if not uniq: continue
                path=download_combined_graph(uniq, out_path=f"/tmp/{q_label}.jpg")
                if path:
                    time.sleep(0.5)
                    send_image(jid, path, f"📊 {q_label} 視像化: {', '.join(uniq)}")
                    import json as js2
                    expr_list=[{"latex": e} for e in uniq]
                    desmos_url=f"https://www.desmos.com/calculator?expressions_list={urllib.parse.quote(js2.dumps(expr_list))}"
                    send_text(jid, f"{q_label} 互動版:\n{desmos_url}")

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
def home(): return f"LC Sir FINAL-ACCURATE-CIRCLE {TICK} len={len(GEMINI_API_KEY)}", 200
@app.route("/health", methods=["GET"])
def health(): return "ok", 200
if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
