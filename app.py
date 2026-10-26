# LC SIR V10.22 FULL - FIX CROSS-CHAT + USE √ + LID + BOX2D + TEXT OVERFLOW
from flask import Flask, request, jsonify
import os, requests, re, base64, time, json, threading, io

app = Flask(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

VERSION = "V10.22-FIX-CROSS-CHAT-AND-SQRT-SYMBOL"
STATE_FILE = "/tmp/group_state.json"

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: pass
    return {}
def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(GROUP_STATE, f, ensure_ascii=False, indent=2)
    except: pass

GROUP_STATE = load_state()
SEEN_IDS = {}
LOCK = threading.Lock()
GROUP_LOCKS = {}
TICK = "✅"
CROSS = "❌"
print(f"BOOT {VERSION}")

def get_group_lock(jid):
    with LOCK:
        if jid not in GROUP_LOCKS:
            GROUP_LOCKS[jid] = threading.Lock()
        return GROUP_LOCKS[jid]

SYSTEM_PROMPT = """
You are LC Sir, HK DSE Math 專家，10年經驗，Friendly HK Cantonese，成日講 YA！DSE滿分Level！

鐵律0：絕對一致性 - 判斷只有一次

鐵律1：符號規定 - MUST用開方符號 √，例如 √9=3, √(x+3), √25=5, √(x^2+2x+1)，唔可以用 sqrt, \\sqrt, $，不等於用 ≤ ≥ ≠，乘用 ×，唔可以用 \\le \\ge \\sqrt \\frac $，MUST用靚符號，開方用 √9=3, √(x+3)，次方用 x², x³, x⁴，分數用 ½ ¼ ¾ 或 (x+1)/2，唔可以用 sqrt, ^2, \\sqrt, \\frac, $，用 ≤ ≥ ≠ ×分數

鐵律2：繁體廣東話+英文term - MUST繁體中文ONLY，口語：係, 唔係, 睇下, 呢題, 錯咗, 叻仔, 呢步, 記住，數學名詞用英文：interior point, boundary, vertex, region

鐵律3：一開頭定生死 - MUST用 Q+number 開頭，Q33 ❌ 呢題唔啱呀 / Q33 ✅ 呢題啱晒！YA

鐵律4：改功課有圖絕對唔出 GRAPH_EQUATION，PDF改晒所有題

鐵律5：紅圈 - 最後一行 MUST出 ANNOTATIONS_JSON: [{"x":0.42,"y":0.35,"text":"check region III"}] 英文ONLY短句

鐵律6：格式 Q33 ❌ *錯喺邊* *點諗* *正確* I and II only 💡 DSE伏位 YA

鐵律7：人性化 - 唔可以得一句「睇到你份功課喇」，要詳細
鐵律8：精簡鐵律 - 每題最多4行：Q32 ✅/❌ 一句總結，*錯喺邊* 一句，*正確* 一至兩步，💡DSE伏位 一句。總字數每題唔過120字，唔准講廢話，唔准講「你整份功課全對」「運算過程好清晰」呢啲空話。
鐵律9：PDF改功課 - 逐題用 Q30 ✅ Q31 ❌ 格式，錯嘅先俾3行，啱嘅只出一行 Q32 ✅ 呢題啱晒！YA 唔使再解釋。
鐵律10：格式 Q32 ❌ / Q32 ✅ 開頭，禁止用 ###, ##, ***, 禁止用 Markdown 標題，唔准有 ###Q32，淨係可以 Q32
"""

MODELS = ["gemini-3.5-flash","gemini-3.5-flash-lite"]

def clean_b64(b64):
    if not b64: return None
    b64=b64.strip()
    if "," in b64: b64=b64.split(",")[-1]
    b64=b64.replace("\n","").replace("\r","").replace(" ","").replace("\t","")
    b64+="="*(-len(b64)%4)
    return b64

def clean_latex(txt):
    if not txt: return txt
    txt = re.sub(r'\\sqrt\s*\{\s*([^}]+?)\s*\}', r'√(\1)', txt)
    txt = re.sub(r'\\sqrt\s*\(\s*([^)]+?)\s*\)', r'√(\1)', txt)
    txt = re.sub(r'\\sqrt\s+([a-zA-Z0-9]+)', r'√\1', txt)
    txt = re.sub(r'sqrt\s*\(\s*([^)]+?)\s*\)', r'√(\1)', txt, flags=re.IGNORECASE)
    txt = txt.replace("\\le", "≤").replace("\\leq", "≤").replace("\\ge", "≥").replace("\\geq", "≥")
    txt = txt.replace("\\ne", "≠").replace("\\neq", "≠")
    txt = txt.replace("\\times", "×").replace("\\cdot", "·").replace("\\div", "÷").replace("\\pm", "±")
    txt = txt.replace("\\left", "").replace("\\right", "").replace("\\frac", "/")
    txt = txt.replace("\\", "").replace("$$", "").replace("$", "")
    txt = re.sub(r'√\(\s*([0-9]+)\s*\)', r'√\1', txt)
    txt = re.sub(r'√\(\s*\(([^)]+)\)\s*\)', r'√(\1)', txt)
    return txt

def get_file_base64(data, is_pdf=False):
    time.sleep(1.2)
    for _ in range(10):
        try:
            payload={"message": data}
            url=f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
            headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            r=requests.post(url, json=payload, headers=headers, timeout=130)
            if r.status_code in [200,201]:
                m=re.search(r'"base64"\s*:\s*"([^"]{1000,})"', r.text)
                raw=m.group(1) if m else None
                if not raw:
                    try: j=r.json(); raw=j.get("base64") or (j.get("data",{}).get("base64") if isinstance(j.get("data"),dict) else j.get("data"))
                    except: pass
                b64=clean_b64(raw) if raw else None
                if b64 and len(b64)>1000: return b64, "application/pdf" if is_pdf else "image/jpeg"
        except: pass
        time.sleep(3)
    return None,None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    prompt=SYSTEM_PROMPT+f"\n\n學生：{question}\n最後一行出 ANNOTATIONS_JSON，開方用 √9=3"
    for model in MODELS:
        for _ in range(3):
            url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
            parts=[{"text": prompt}]
            if file_b64: parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
            body={"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.28, "maxOutputTokens": 7000}}
            try:
                r=requests.post(url, json=body, headers=headers, timeout=130)
                if r.status_code==200:
                    txt=r.json()["candidates"][0]["content"]["parts"][0].get("text","").strip()
                    if len(txt)<60: continue
                    txt=clean_latex(txt)
                    return txt, "ok"
            except: pass
    return "", "empty"

def send_typing(jid, stop_event):
    url=f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE}"
    headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload={"number": jid, "presence": "composing", "delay": 25000}
    while not stop_event.is_set():
        try: requests.post(url, json=payload, headers=headers, timeout=10)
        except: pass
        time.sleep(1)

def send_text(jid, text):
    url=f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        text=re.sub(r'```json.*?```', '', text, flags=re.DOTALL)
        text=re.sub(r'"box_2d":\s*\[.*?\]', '', text, flags=re.DOTALL)
        text=clean_latex(text).strip()
        if not text or len(text)<20: text="收到喇，LC Sir 睇緊先 YA～"
        for i in range(0, len(text), 2500):
            r=requests.post(url, json={"number": jid, "text": text[i:i+2500]}, headers=headers, timeout=20)
            print(f"[SEND TEXT] to={jid[-10:]} status {r.status_code} len={len(text)}")
            time.sleep(0.6)
    except Exception as e: print(f"Send fail {e} jid={jid}")

def parse_annotations(answer):
    annotations=[]
    m_ann=re.search(r"ANNOTATIONS_JSON:\s*(\[.*?\])", answer, re.DOTALL)
    if m_ann:
        try: annotations=json.loads(m_ann.group(1))
        except: annotations=[]
    if not annotations:
        matches=re.findall(r'"box_2d"\s*:\s*\[([^\]]+)\].*?"text_content"\s*:\s*"([^"]+)"', answer, re.DOTALL)
        for coords_str, txt in matches:
            try:
                coords=[float(x.strip()) for x in coords_str.split(',')]
                if len(coords)>=4:
                    y1,x1,y2,x2=coords[0],coords[1],coords[2],coords[3]
                    if max(coords)>10: x=(x1+x2)/2/1000; y=(y1+y2)/2/1000
                    else: x=(x1+x2)/2; y=(y1+y2)/2
                    annotations.append({"x":max(0.05,min(0.95,x)), "y":max(0.05,min(0.95,y)), "text":txt[:30]})
            except: continue
    clean=[]
    for ann in annotations[:5]:
        try:
            x=float(ann.get("x",0.5)); y=float(ann.get("y",0.5))
            txt=''.join(c for c in str(ann.get("text","")) if ord(c)<128)[:30]
            if not (0.05<x<0.95 and 0.05<y<0.95): continue
            clean.append({"x":x,"y":y,"text":txt or "check here"})
        except: continue
    return clean

def create_annotated_image(original_b64, annotations):
    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap
        img_data=base64.b64decode(clean_b64(original_b64))
        img=Image.open(io.BytesIO(img_data)).convert("RGB")
        draw=ImageDraw.Draw(img); w,h=img.size
        print(f"[ANNOTATE] size {w}x{h} count {len(annotations)}")
        if not annotations: return None
        try:
            fp="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            font=ImageFont.truetype(fp, max(13, int(h*0.020)))
            font_bold=ImageFont.truetype(fp, max(14, int(h*0.023)))
        except: font=ImageFont.load_default(); font_bold=font
        for ann in annotations[:5]:
            try:
                x=float(ann.get("x",0.5)); y=float(ann.get("y",0.5))
                cx,cy=int(w*x),int(h*y); r=int(min(w,h)*0.036)
                draw.ellipse([cx-r-4,cy-r-4,cx+r+4,cy+r+4], outline=(255,230,0), width=4)
                draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline=(210,0,0), width=4)
                raw_txt=ann.get("text","").strip()
                if raw_txt:
                    txt='\n'.join(textwrap.wrap(raw_txt[:28], width=14))
                    bbox=draw.multiline_textbbox((0,0), txt, font=font, spacing=2)
                    text_w=bbox[2]-bbox[0]; text_h=bbox[3]-bbox[1]; pad=8
                    tx=cx+r+10; ty=cy - text_h//2
                    if tx + text_w + pad*2 > w - 5: tx=cx - r - text_w - pad*2 -10
                    if tx <5: tx=5
                    if ty <5: ty=5
                    if ty + text_h + pad*2 > h -5: ty=h - text_h - pad*2 -5
                    draw.rounded_rectangle([tx-pad, ty-pad, tx+text_w+pad, ty+text_h+pad], radius=8, fill=(255,255,255), outline=(50,100,200), width=2)
                    draw.multiline_text((tx, ty), txt, fill=(20,60,160), font=font_bold, spacing=2)
            except: continue
        buf=io.BytesIO(); img.save(buf,"JPEG",quality=92); return base64.b64encode(buf.getvalue()).decode()
    except Exception as e: print(f"[ANNOTATE FAIL] {e}"); return None

def send_image(jid, image_input, caption):
    try:
        b64=clean_b64(image_input); url=f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"; headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload={"number": jid, "mediatype": "image", "media": b64, "caption": caption, "fileName": f"marked_{int(time.time())}.jpg"}
        r=requests.post(url, json=payload, headers=headers, timeout=40)
        print(f"[SEND IMG] to={jid[-10:]} status {r.status_code}")
        return r.status_code in [200,201]
    except Exception as e: print(f"[SEND IMG FAIL] {e}"); return False

def do_work(jid, text, push_name, participant, from_me, msg, data, msg_id):
    my_jid = str(jid).strip()  # 鎖死自己個 jid，唔會串台
    my_msg_id = str(msg_id)
    try:
        print(f"[WORK START] jid={my_jid[-15:]} msg_id={my_msg_id} push={push_name}")
        with LOCK:
            now=time.time()
            for k in list(SEEN_IDS.keys()):
                if now-SEEN_IDS[k]>300: del SEEN_IDS[k]
            seen_key = f"{my_jid}_{my_msg_id}"  # 每個聊天室獨立 dedup
            if seen_key in SEEN_IDS:
                print(f"[WORK DUP] skip {seen_key}")
                return
            SEEN_IDS[seen_key]=now
        
        group_lock = get_group_lock(my_jid)
        with group_lock:  # 同一個學生/Group，排隊做，唔會調亂
            stop_typing=threading.Event()
            threading.Thread(target=send_typing, args=(my_jid, stop_typing), daemon=True).start()

            def is_teacher_user():
                if from_me: return True
                check_str = f"{participant} {data.get('participant','')} {my_jid}"
                digits = re.sub(r'\D','', check_str)
                if "46447827" in digits: return True
                return False

            is_group="@g.us" in my_jid
            if is_group:
                if my_jid not in GROUP_STATE: GROUP_STATE[my_jid]=True; save_state()
                pure_text=(msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or text or "").strip()
                open_keys=["開始發問","開放提問","開始","開放","開始問書","開放問書","/open","open"]
                close_keys=["關閉發問","結束發問","關閉","結束","收工","/close","close","停止發問"]
                lower_pure=pure_text.lower()
                is_open=any(k in pure_text for k in open_keys) or lower_pure in ["開始","開放","open"]
                is_close=any(k in pure_text for k in close_keys) or lower_pure in ["關閉","結束","close","收工"]
                if pure_text in ["開始","關閉","開放","結束","收工","open","close"]:
                    is_open=pure_text in ["開始","開放","open","開始發問","開放提問"]
                    is_close=pure_text in ["關閉","結束","收工","close"]
                if is_open or is_close:
                    if not is_teacher_user():
                        print(f"[OPEN/CLOSE] BLOCKED student {pure_text} jid={my_jid[-10:]}")
                        stop_typing.set(); return
                    if is_open:
                        GROUP_STATE[my_jid]=True; save_state(); stop_typing.set()
                        send_text(my_jid, f"{TICK} 老師已開放提問！依家同學可以問 LC Sir 喇～")
                        return
                    else:
                        GROUP_STATE[my_jid]=False; save_state(); stop_typing.set()
                        send_text(my_jid, f"🔒 老師已關閉提問，LC Sir 休息中～")
                        return
                if not GROUP_STATE.get(my_jid, True):
                    if not any(k in text.lower() for k in ["lc","阿sir","老師"]):
                        stop_typing.set(); return
            
            if from_me and not is_group: stop_typing.set(); return

            b64,mime=None,"image/jpeg"; is_image="imageMessage" in msg; is_pdf="documentMessage" in msg
            if is_image:
                b64,mime=get_file_base64(data, False); cap=msg["imageMessage"].get("caption") or ""; text=(cap or text or "幫我睇下呢份功課").strip()
            elif is_pdf:
                b64,mime=get_file_base64(data, True); text=(text or "呢份PDF逐題改晒").strip(); mime="application/pdf"
            
            if not text and not b64: stop_typing.set(); return
            if (is_image or is_pdf) and not b64: stop_typing.set(); send_text(my_jid, "份file仲 load 緊，麻煩再send多次 🙏"); return

            answer,status=call_gemini(text, b64, mime); stop_typing.set()
            if not answer or len(answer.strip())<50: answer="收到喇，LC Sir 幫你睇緊先 YA～"

            annotations=parse_annotations(answer)
            temp_clean=re.sub(r"ANNOTATIONS_JSON:.*", "", answer, flags=re.DOTALL)
            temp_clean=re.sub(r"```json.*?```", "", temp_clean, flags=re.DOTALL)
            temp_clean=clean_latex(temp_clean).strip()
            clean_answer=temp_clean if len(temp_clean)>=20 else answer.split("ANNOTATIONS_JSON")[0].strip()
            clean_answer=clean_latex(clean_answer).replace("$","")
            if "@g.us" in my_jid and push_name and not clean_answer.startswith(f"@{push_name}"): clean_answer=f"@{push_name} {clean_answer}"

            print(f"[WORK SEND] to={my_jid[-15:]} len={len(clean_answer)}")
            send_text(my_jid, clean_answer)
            
            if is_image and b64 and annotations:
                time.sleep(1)
                img_b64=create_annotated_image(b64, annotations)
                if img_b64:
                    try: send_image(my_jid, img_b64, f"{TICK} 睇下圖，圈咗俾你留意下嘅位 ya")
                    except Exception as e: print(f"[IMG FAIL] {e}")
            
            print(f"[{VERSION}] done jid={my_jid[-10:]} len={len(clean_answer)} ann={len(annotations)}")
    
    except Exception as e:
        print(f"[DO_WORK CRASH] jid={jid} err={e}")
        import traceback; traceback.print_exc()
        try: stop_typing.set()
        except: pass

@app.route("/webhook", methods=["POST"])
def webhook():
    body=request.json or {}; data=body.get("data", {}); key=data.get("key", {}); msg=data.get("message", {}); jid=key.get("remoteJid"); push_name=data.get("pushName") or ""; participant=key.get("participant") or data.get("participant") or ""; from_me=key.get("fromMe", False)
    if not jid: return jsonify({"ok": True}), 200
    text=msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    if not text and "imageMessage" in msg: text=msg["imageMessage"].get("caption") or ""
    msg_id=key.get("id") or f"no-id-{int(time.time()*1000)}"
    threading.Thread(target=do_work, args=(jid, text, push_name, participant, from_me, msg, data, msg_id), daemon=True).start()
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home(): return f"LC Sir {VERSION} {TICK}", 200
@app.route("/health", methods=["GET"])
def health(): return "ok", 200

if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
