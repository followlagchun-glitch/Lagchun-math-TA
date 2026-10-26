# LC SIR V10.17 - FINAL FIX 開始關閉 LID + 紅圈字出界
from flask import Flask, request, jsonify
import os, requests, re, base64, time, json, threading, io, random
app = Flask(__name__)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()
TEACHER_NUMBERS = ["85246447827", "46447827"]
VERSION = "V10.17-FIX-LID-OPEN-CLOSE-TEXT-OVERFLOW"
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
SEEN_IDS = {}; LOCK = threading.Lock()
TICK = "✅"; CROSS = "❌"
print(f"BOOT {VERSION}")

SYSTEM_PROMPT = """
You are LC Sir, HK DSE Math 專家，YA！DSE滿分Level！
鐵律1：NEVER LATEX，寫 x <= -9, y = -x^2+4x-3
鐵律2：繁體廣東話
鐵律3：MUST Q+number 開頭 Q33 ❌/✅
鐵律4：PDF多過6頁都改晒
鐵律5：紅圈 ANNOTATIONS_JSON 英文ONLY 最後先出，text要短 15字內，例如 "check region III"
鐵律6：Q33 ❌ *錯喺邊* *點諗* *正確* I and II only 💡 YA
"""

MODELS = ["gemini-3.5-flash","gemini-3.5-flash-lite"]

def clean_b64(b64):
    if not b64: return None
    b64=b64.strip()
    if "," in b64: b64=b64.split(",")[-1]
    b64=b64.replace("\n","").replace("\r","").replace(" ","").replace("\t","")
    b64+="="*(-len(b64)%4)
    return b64

def get_file_base64(data, is_pdf=False):
    time.sleep(1.5)
    for attempt in range(10):
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
    prompt=SYSTEM_PROMPT+f"\n\n學生：{question}\n先出 Q33 文字批改，後出 ANNOTATIONS_JSON，text短，英文"
    for model in MODELS:
        for retry in range(3):
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
                    txt=txt.replace("\\le","<=").replace("\\ge",">=").replace("\\","").replace("$","")
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
        text=text.strip()
        is_system = any(k in text for k in ["老師已開放提問","老師已關閉提問","只有老師","LC Sir 休息中"])
        if not is_system and (not text or len(text)<20): text="收到喇，LC Sir 睇緊先 YA～"
        for i in range(0, len(text), 2500):
            r=requests.post(url, json={"number": jid, "text": text[i:i+2500]}, headers=headers, timeout=20)
            print(f"[SEND TEXT] status {r.status_code} len={len(text)} is_system={is_system}")
            time.sleep(0.7)
    except Exception as e: print(f"Send fail {e}")

def create_annotated_image(original_b64, annotations):
    try:
        from PIL import Image, ImageDraw, ImageFont
        import textwrap
        img_data=base64.b64decode(clean_b64(original_b64))
        img=Image.open(io.BytesIO(img_data)).convert("RGB")
        draw=ImageDraw.Draw(img); w,h=img.size
        if not annotations: return None
        try:
            fp="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            font=ImageFont.truetype(fp, max(13, int(h*0.020)))
            font_bold=ImageFont.truetype(fp, max(14, int(h*0.023)))
        except:
            font=ImageFont.load_default(); font_bold=font
        for ann in annotations[:5]:
            try:
                x=float(ann.get("x",0.5)); y=float(ann.get("y",0.5))
                raw_txt=ann.get("text","").strip()
                if not (0.02<x<0.98 and 0.02<y<0.98): continue
                cx,cy=int(w*x),int(h*y)
                r=int(min(w,h)*0.036)
                draw.ellipse([cx-r-4,cy-r-4,cx+r+4,cy+r+4], outline=(255,230,0), width=4)
                draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline=(210,0,0), width=4)
                if raw_txt:
                    txt=''.join(c for c in raw_txt if ord(c)<128).strip()[:28]
                    txt='\n'.join(textwrap.wrap(txt, width=16))
                    bbox=draw.multiline_textbbox((0,0), txt, font=font, spacing=2)
                    text_w=bbox[2]-bbox[0]; text_h=bbox[3]-bbox[1]
                    pad=8
                    tx=cx+r+10; ty=cy - text_h//2
                    if tx + text_w + pad*2 > w - 5:
                        tx=cx - r - text_w - pad*2 - 10
                    if tx < 5: tx=5
                    if ty < 5: ty=5
                    if ty + text_h + pad*2 > h - 5: ty=h - text_h - pad*2 -5
                    draw.rounded_rectangle([tx-pad, ty-pad, tx+text_w+pad, ty+text_h+pad], radius=8, fill=(255,255,255), outline=(50,100,200), width=2)
                    draw.multiline_text((tx, ty), txt, fill=(20,60,160), font=font_bold, spacing=2)
            except: continue
        buf=io.BytesIO(); img.save(buf,"JPEG",quality=92); return base64.b64encode(buf.getvalue()).decode()
    except Exception as e: print(f"[ANNOTATE] {e}"); return None

def send_image(jid, image_input, caption):
    try:
        b64=clean_b64(image_input); url=f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"; headers={"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload={"number": jid, "mediatype": "image", "media": b64, "caption": caption, "fileName": f"marked_{int(time.time())}.jpg"}
        r=requests.post(url, json=payload, headers=headers, timeout=40); return r.status_code in [200,201]
    except: return False

def do_work(jid, text, push_name, participant, from_me, msg, data, msg_id):
    with LOCK:
        now=time.time()
        for k in list(SEEN_IDS.keys()):
            if now-SEEN_IDS[k]>300: del SEEN_IDS[k]
        if msg_id in SEEN_IDS: return
        SEEN_IDS[msg_id]=now
    stop_typing=threading.Event(); threading.Thread(target=send_typing, args=(jid, stop_typing), daemon=True).start()

    def is_teacher_user():
        # FINAL FIX: fromMe=True 就係老師，唔使睇 LID
        if from_me:
            print(f"[TEACHER] fromMe=True => 老師本人")
            return True
        check_str = f"{participant} {data.get('participant','')} {jid}"
        digits = re.sub(r'\D','', check_str)
        if "46447827" in digits or "85246447827" in check_str:
            print(f"[TEACHER] digits match 46447827 => 老師")
            return True
        print(f"[TEACHER] student LID {participant}")
        return False

    is_group="@g.us" in jid
    if is_group:
        if jid not in GROUP_STATE: GROUP_STATE[jid]=True; save_state()
        pure_text=(msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or text or "").strip()
        print(f"[CMD] pure_text='{pure_text}' fromMe={from_me} participant={participant}")
        # FINAL: 支援單字 開始 / 關閉
        open_keys=["開始發問","開放提問","開始","開放","開始問書","開放問書","/open","open"]
        close_keys=["關閉發問","結束發問","關閉","結束","收工","/close","close","停止發問"]
        # 精確判斷：短指令就係開關
        lower_pure = pure_text.lower()
        is_open = any(k in pure_text for k in open_keys) or lower_pure in ["開始","開放","open"]
        is_close = any(k in pure_text for k in close_keys) or lower_pure in ["關閉","結束","close","收工"]
        # 如果純粹係 開始/關閉 兩個字，100% 當開關
        if pure_text in ["開始","關閉","開放","結束","收工","open","close"]:
            is_open = pure_text in ["開始","開放","open","開始發問","開放提問"]
            is_close = pure_text in ["關閉","結束","收工","close"]

        if is_open or is_close:
            if not is_teacher_user():
                print(f"[OPEN/CLOSE] BLOCKED student {pure_text}")
                stop_typing.set()
                return
            if is_open:
                GROUP_STATE[jid]=True; save_state(); stop_typing.set()
                send_text(jid, f"{TICK} 老師已開放提問！依家同學可以問 LC Sir 喇～\n\n同學直接 Send 功課相就得，LC Sir 會逐題改，包埋紅圈同 *錯喺邊* *點諗* *正確*，DSE滿分Level YA！")
                return
            else:
                GROUP_STATE[jid]=False; save_state(); stop_typing.set()
                send_text(jid, f"🔒 老師已關閉提問，LC Sir 休息中～\n\n暫停期間同學 Send 相唔會回覆，要再開就打「開始」或者「開始發問」")
                return
        if not GROUP_STATE.get(jid, True):
            if not any(k in text.lower() for k in ["lc","阿sir","老師"]):
                stop_typing.set(); return
    if from_me and not is_group: stop_typing.set(); return

    b64,mime=None,"image/jpeg"; is_image="imageMessage" in msg; is_pdf="documentMessage" in msg
    if is_image:
        b64,mime=get_file_base64(data, False); cap=msg["imageMessage"].get("caption") or ""; text=(cap or text or "幫我睇下呢份功課，要改晒所有題").strip()
    elif is_pdf:
        b64,mime=get_file_base64(data, True); text=(text or "呢份PDF 6頁，逐頁逐題改晒").strip(); mime="application/pdf"
    if not text and not b64: stop_typing.set(); return
    if (is_image or is_pdf) and not b64: stop_typing.set(); send_text(jid, "份file仲 load 緊，麻煩再send多次 🙏"); return

    answer,status=call_gemini(text, b64, mime); stop_typing.set()
    if not answer or len(answer.strip())<50: answer="收到喇，LC Sir 幫你睇緊先 YA～"
    annotations=[]; m_ann=re.search(r"ANNOTATIONS_JSON:\s*(\[.*?\])", answer, re.DOTALL)
    if m_ann:
        try: annotations=json.loads(m_ann.group(1))
        except: annotations=[]
    temp_clean=re.sub(r"ANNOTATIONS_JSON:.*", "", answer, flags=re.DOTALL).strip()
    if len(temp_clean)>=20: clean_answer=temp_clean
    else: clean_answer=answer.split("ANNOTATIONS_JSON")[0].strip() if "ANNOTATIONS_JSON" in answer else answer
    clean_answer=clean_answer.replace("$","")
    if "@g.us" in jid and push_name and not clean_answer.startswith(f"@{push_name}"): clean_answer=f"@{push_name} {clean_answer}"
    send_text(jid, clean_answer)
    if is_image and b64 and annotations:
        time.sleep(1); img_b64=create_annotated_image(b64, annotations)
        if img_b64: send_image(jid, img_b64, f"{CROSS} 睇圖，紅圈就係錯嘅位")
    print(f"[{VERSION}] done len={len(clean_answer)} ann={len(annotations)}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body=request.json or {}; data=body.get("data", {}); key=data.get("key", {}); msg=data.get("message", {}); jid=key.get("remoteJid"); push_name=data.get("pushName") or ""; participant=key.get("participant") or data.get("participant") or ""; from_me=key.get("fromMe", False)
    if not jid: return jsonify({"ok": True}), 200
    text=msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    if not text and "imageMessage" in msg: text=msg["imageMessage"].get("caption") or ""
    msg_id=key.get("id") or f"no-id-{int(time.time()*1000)}"
    print(f"[WEBHOOK] jid={jid} text='{text}' participant={participant} fromMe={from_me}")
    threading.Thread(target=do_work, args=(jid, text, push_name, participant, from_me, msg, data, msg_id), daemon=True).start()
    return jsonify({"ok": True}), 200
@app.route("/", methods=["GET"])
def home(): return f"LC Sir {VERSION} {TICK}", 200
@app.route("/health", methods=["GET"])
def health(): return "ok", 200
if __name__=="__main__": app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
