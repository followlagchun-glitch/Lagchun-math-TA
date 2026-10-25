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
    except: pass

GROUP_STATE = load_state()
SEEN_IDS = {}
LOCK = threading.Lock()

print(f"BOOT FINAL ALL FEATURES len={len(GEMINI_API_KEY)}")

TICK = "\u2705"
CROSS = "\u274c"
STAR = "\u2b50"

SYSTEM_PROMPT = (
    "You are LC Sir, Hong Kong DSE Math tutor, funny and like a real person wbo is motivating.\n"
    "NEVER LATEX - VERY STRICT RULE:\n"
    "- NEVER use LaTeX, NEVER use $ $ or $$ $$ or \\( \\) or \\[ \\]\n"
    "- NEVER use \\frac \\text \\sqrt \\^ etc.\n"
    "- Use plain text only: x-2y+9=0, y=(x+9)/2\n"
    "- Power: use unicode ² ³, example x² not x^2\n"
    "- Square root: use √ or sqrt in plain text, example √(x+1)\n"
    "- Fraction: use (1/2) or 1/2, example (x+9)/2\n"
    "- Multiply divide: use × ÷ or * /\n"
    "LANGUAGE - VERY STRICT RULE: MUST Traditional Chinese HK Cantonese ONLY.\n"
    "FORMAT per Q:\n"
    "*Q1* TICK or CROSS\n"
    "- 啱: ...\n"
    "- 唔啱: ...\n"
    "If line eq, GRAPH_EQUATION: x-2y+9=0\n"
    "Last line ANNOTATIONS_JSON: []\n"
)

MODELS = ["gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.5-pro", "gemini-1.5-flash", "gemini-3.5-flash-lite"]

def clean_b64(b64):
    if not b64: return None
    b64=b64.strip()
    if "," in b64: b64=b64.split(",")[-1]
    b64=b64.replace("\n","").replace("\r","").replace(" ","")
    b64+="="*(-len(b64)%4)
    return b64

def get_file_base64(data, is_pdf=False):
    time.sleep(2)
    for _ in range(5):
        try:
            payload={"message":data}
            url=f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
            headers={"apikey":EVOLUTION_API_KEY,"Content-Type":"application/json"}
            r=requests.post(url,json=payload,headers=headers,timeout=60)
            if r.status_code in [200,201]:
                m=re.search(r'"base64"\s*:\s*"([^"]{1000,})"',r.text)
                raw=m.group(1) if m else None
                if not raw:
                    try:
                        j=r.json()
                        raw=j.get("base64") or (j.get("data",{}).get("base64") if isinstance(j.get("data"),dict) else j.get("data"))
                    except: pass
                b64=clean_b64(raw) if raw else None
                if b64 and len(b64)>1000:
                    return b64, "application/pdf" if is_pdf else "image/jpeg"
        except Exception as e:
            print(e)
        time.sleep(4)
    return None,None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    # 將 TICK CROSS 轉做實際符號比 Gemini 睇
    q_with_emoji = question + f"\n請逐題用 {TICK} {CROSS} 分析，每題講做得啱同唔啱嘅地方，繁體中文。"
    prompt = SYSTEM_PROMPT.replace("TICK", TICK).replace("CROSS", CROSS)
    full_prompt = prompt + f"\n\n學生功課: {q_with_emoji}"
    for model in MODELS:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers={"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}
        parts=[{"text":full_prompt}]
        if file_b64: parts.append({"inlineData":{"mimeType":mime_type,"data":file_b64}})
        body={"contents":[{"role":"user","parts":parts}],"generationConfig":{"temperature":0.3}}
        try:
            r=requests.post(url,json=body,headers=headers,timeout=120)
            if r.status_code==200:
                txt=r.json()["candidates"][0]["content"]["parts"][0]["text"]
                return txt, "ok"
            print(r.text[:500])
        except Exception as e:
            print(e)
    return f"{CROSS} 暫時連唔到，稍後再試", "error"

def send_typing(jid, stop_event):
    url=f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE}"
    headers={"apikey":EVOLUTION_API_KEY,"Content-Type":"application/json"}
    payload={"number":jid,"presence":"composing","delay":25000}
    while not stop_event.is_set():
        try: requests.post(url,json=payload,headers=headers,timeout=10)
        except: pass
        time.sleep(2)

def send_text(jid, text):
    url=f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers={"apikey":EVOLUTION_API_KEY,"Content-Type":"application/json"}
    try:
        for i in range(0,len(text),3000):
            requests.post(url,json={"number":jid,"text":text[i:i+3000]},headers=headers,timeout=20)
            time.sleep(0.4)
    except: pass

def create_annotated_image(original_b64, annotations):
    try:
        from PIL import Image, ImageDraw
        img_data=base64.b64decode(clean_b64(original_b64))
        img=Image.open(io.BytesIO(img_data)).convert("RGB")
        draw=ImageDraw.Draw(img)
        w,h=img.size
        if not annotations:
            draw.ellipse([w*0.15,h*0.3,w*0.85,h*0.6],outline="red",width=8)
        else:
            for ann in annotations[:6]:
                try:
                    cx,cy=int(w*float(ann.get("x",0.5))),int(h*float(ann.get("y",0.5)))
                    r=int(min(w,h)*0.08)
                    draw.ellipse([cx-r,cy-r,cx+r,cy+r],outline="red",width=6)
                except: pass
        buf=io.BytesIO()
        img.save(buf,"JPEG",quality=92)
        return base64.b64encode(buf.getvalue()).decode()
    except: return None

def send_image(jid, image_input, caption):
    try:
        b64_data=clean_b64(image_input) if not os.path.exists(str(image_input)) else base64.b64encode(open(image_input,"rb").read()).decode()
        if not b64_data or len(b64_data)<1000: return False
        url=f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
        headers={"apikey":EVOLUTION_API_KEY,"Content-Type":"application/json"}
        payload={"number":jid,"mediatype":"image","media":b64_data,"caption":caption,"fileName":"marked.jpg"}
        r=requests.post(url,json=payload,headers=headers,timeout=30)
        return r.status_code in [200,201]
    except: return False

def download_combined_graph(equations_list, out_path="/tmp/combined.jpg"):
    try:
        import numpy as np, sympy as sp
        colors=["rgb(225,29,72)","rgb(45,112,179)","rgb(22,163,74)","rgb(234,179,8)"]
        datasets=[]
        for idx, eq in enumerate(equations_list):
            points=[]
            try:
                eq_sym=eq.replace("2","**2").replace("3","**3").replace("^","**")
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
    except: pass
    return None

def do_work(jid, text, push_name, participant, from_me, msg, data, msg_id):
    with LOCK:
        if msg_id in SEEN_IDS: return
        SEEN_IDS[msg_id]=time.time()
    stop_typing=threading.Event()
    threading.Thread(target=send_typing, args=(jid, stop_typing), daemon=True).start()

    def is_teacher():
        if from_me: return True
        digits=re.sub(r'\D','', participant if "@g.us" in jid else jid)
        return any(t in digits for t in TEACHER_NUMBERS)

    is_group="@g.us" in jid
    if is_group:
        if jid not in GROUP_STATE:
            GROUP_STATE[jid]=True
            save_state()
        if any(k in text for k in ["開放提問","開始","/open"]):
            if not is_teacher(): 
                stop_typing.set()
                return
            GROUP_STATE[jid]=True
            save_state()
            stop_typing.set()
            send_text(jid, f"{TICK} 開放提問成功")
            return
        if any(k in text for k in ["關閉提問","結束","/close"]):
            if not is_teacher():
                stop_typing.set()
                return
            GROUP_STATE[jid]=False
            save_state()
            stop_typing.set()
            send_text(jid, f"{CROSS} 已關閉提問")
            return
        if not GROUP_STATE[jid]:
            if any(k in text.lower() for k in ["lc","sir","老師"]) or "imageMessage" in msg or "documentMessage" in msg:
                if not is_teacher():
                    stop_typing.set()
                    send_text(jid, "而家未開放提問，等老師講開始先可以問")
                    return

    if from_me and not is_group:
        stop_typing.set()
        return

    if "@g.us" in jid:
        low=text.lower()
        if not any(k in low for k in ["lc","阿sir","sir","老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
            if not msg.get("imageMessage",{}).get("caption"):
                stop_typing.set()
                return
        text=f"[{push_name} 問]: {text}"

    b64,mime=None,"image/jpeg"
    if "imageMessage" in msg:
        b64,mime=get_file_base64(data,is_pdf=False)
        text=(msg["imageMessage"].get("caption") or text or "幫我逐題睇下呢份功課，每題講下做得啱同唔啱").strip()
    elif "documentMessage" in msg:
        b64,mime=get_file_base64(data,is_pdf=True)
        text=(text or "幫我逐題睇下呢份PDF功課，每題講下做得啱同唔啱").strip()
        mime="application/pdf"

    if not text and not b64:
        stop_typing.set()
        return
    if ("imageMessage" in msg or "documentMessage" in msg) and not b64:
        stop_typing.set()
        send_text(jid, "張圖仲 load 緊，麻煩 send 多次新相，唔好 forward 舊相")
        return

    answer,_=call_gemini(text,b64,mime)
    stop_typing.set()

    annotations=[]
    m_ann=re.search(r"ANNOTATIONS_JSON:\s*(\[.*?\])",answer,re.DOTALL)
    if m_ann:
        try: annotations=json.loads(m_ann.group(1))
        except: pass

    graphs=re.findall(r"GRAPH_EQUATION:\s*(.+)",answer)
    if not graphs:
        combined=text+" "+answer
        found=re.findall(r'([a-zA-Z]?\s*[-+]?\s*\d*[xy].*?=\s*0)',combined)
        graphs=[f.strip() for f in found if len(f.strip())>3][:4]

    clean_answer=re.sub(r"GRAPH_EQUATION:\s*.+","",answer).strip()
    clean_answer=re.sub(r"ANNOTATIONS_JSON:.*","",clean_answer,flags=re.DOTALL).strip()
    if is_group and push_name:
        clean_answer=f"@{push_name} {clean_answer}"

    send_text(jid, clean_answer)

    if b64 and mime!="application/pdf" and CROSS in clean_answer:
        img_b64=create_annotated_image(b64, annotations)
        if img_b64:
            time.sleep(0.5)
            send_image(jid, img_b64, f"{CROSS} 紅圈就係錯嘅位，睇上面文字解釋")

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
            if len(clean_graphs)>1:
                path=download_combined_graph(clean_graphs,out_path="/tmp/combined.jpg")
                if path: send_image(jid, path, f"{TICK} 合併圖: {', '.join(clean_graphs)}")
            else:
                path=download_combined_graph(clean_graphs,out_path="/tmp/graph.jpg")
                if path: send_image(jid, path, f"{clean_graphs[0]} 圖像")

@app.route("/webhook", methods=["POST"])
def webhook():
    body=request.json or {}
    data=body.get("data",{})
    key=data.get("key",{})
    msg=data.get("message",{})
    jid=key.get("remoteJid")
    if not jid: return jsonify({"ok":True}),200
    text=msg.get("conversation") or msg.get("extendedTextMessage",{}).get("text") or ""
    if not text and "imageMessage" in msg: text=msg["imageMessage"].get("caption") or ""
    msg_id=key.get("id") or str(int(time.time()*1000))
    push_name=data.get("pushName") or ""
    participant=key.get("participant") or ""
    from_me=key.get("fromMe",False)
    threading.Thread(target=do_work, args=(jid,text,push_name,participant,from_me,msg,data,msg_id), daemon=True).start()
    return jsonify({"ok":True}),200

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir FINAL ALL {TICK}{CROSS} len={len(GEMINI_API_KEY)}",200

@app.route("/health", methods=["GET"])
def health():
    return "ok",200

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT",10000)))
