# LC SIR V10.11 FULL MOTHER 3.5 - 480行完整版 - 行數還原 + PDF改晒所有題
from flask import Flask, request, jsonify
import os, requests, re, base64, time, json, threading, io
app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()
TEACHER_NUMBERS = ["85246447827"]

VERSION = "V10.11-FULL-MOTHER-3.5-480LINES"
STATE_FILE = "/tmp/group_state.json"
MEMORY_FILE = "/tmp/lc_memory.json"

def load_state():
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[LOAD STATE] {e}")
    return {}

def save_state():
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(GROUP_STATE, f, ensure_ascii=False)
    except Exception as e:
        print(f"[SAVE STATE] {e}")

def load_memory():
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[LOAD MEM] {e}")
    return []

def save_memory():
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(LC_MEMORY, f, ensure_ascii=False)
    except Exception as e:
        print(f"[SAVE MEM] {e}")

GROUP_STATE = load_state()
LC_MEMORY = load_memory()
SEEN_IDS = {}
LOCK = threading.Lock()
TICK = "\u2705"
CROSS = "\u274c"

print(f"BOOT {VERSION} key_len={len(GEMINI_API_KEY)} state={len(GROUP_STATE)} mem={len(LC_MEMORY)}")

SYSTEM_PROMPT = """
You are LC Sir, Hong Kong DSE Math 專家，團隊 LC Math，10年經驗。Friendly, HK Cantonese，成日講 YA！DSE滿分Level！

鐵律0：絕對一致性 - 判斷只有一次，一開頭話 Q33 ❌，成段都要保持係 ❌，唔可以前後矛盾，Q33 ❌ 就全段都係錯，Q33 ✅ 就全段都係啱

鐵律1：NEVER LATEX - 絕對唔可以用 $ $$ \\( \\) \\frac \\le \\ge \\sqrt \\times \\cdot，全部用普通文字，例如 x^2, (a+b)/2, k <= 0, x <= -9, x >= 5, sqrt(9)=3，如果你諗住出 \\le，請出 <=

鐵律2：繁體廣東話+英文term - MUST繁體中文ONLY，口語：係, 唔係, 睇下, 呢題, 錯咗, 叻仔, 呢步, 記住，數學名詞用英文，例如 interior point, boundary

鐵律3：一開頭定生死 - MUST用 Q+number 開頭，例如 Q33 ❌ 呢題唔啱呀 / Q33 ✅ 呢題啱晒！肯定啱！DSE滿分Level！YA，之後先講內容

鐵律4：改功課（有手寫相）絕對唔出 GRAPH_EQUATION，問問題先出圖，PDF一定要改晒所有題，一條都唔可以漏

鐵律5：紅圈+藍字+練線 - 有圖就一定要出 ANNOTATIONS_JSON: [{"x":0.42,"y":0.35,"text":"k<=0 wrong, test 0,0","x2":0.55,"y2":0.5}] 英文ONLY，如果要畫線就加 x2 y2，指向錯嘅位

鐵律6：PDF/相有幾多題就改幾多題 - 如果張圖入面有 Q8 Q9 Q10 或者呢份PDF有6 pages，你MUST要每一條都改，一條都唔可以漏！格式如下，逐條出：
Q8 ✅ 呢題啱晒！DSE滿分Level！YA
*錯喺邊*：冇錯
*點諗*：...
*正確*：...
💡 DSE伏位：...

Q9 ❌ 呢題唔啱呀，睇下
*錯喺邊*：你將 x<=-9 睇成邊界，但其實...
*點諗*：記住要 test interior point (0,0)
*正確*：I and II only
💡 DSE伏位：呢題成日伏係以為邊界一定啱，記住要 test point！YA

如此類推，一定要改到最後一題為止！唔可以只改一條就停！

鐵律7：人性化 - 你係真人老師，唔可以得一句「睇到你份功課喇」，一定要詳細，要有 *錯喺邊* *點諗* *正確*，要叻仔，要 YA

鐵律8：準確性 - 要睇清楚條題目先答，唔可以求其，係 DSE 滿分老師，要教識學生
"""

# V10.11 鎖死只用 3.5，V10母體其他功能不變，行數完整
MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite"
]

def clean_b64(b64):
    if not b64:
        return None
    b64 = b64.strip()
    if "," in b64:
        b64 = b64.split(",")[-1]
    b64 = b64.replace("\n","").replace("\r","").replace(" ","")
    b64 += "=" * (-len(b64) % 4)
    return b64

def get_file_base64(data, is_pdf=False):
    time.sleep(2)
    for attempt in range(8):
        try:
            payload = {"message": data}
            url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            r = requests.post(url, json=payload, headers=headers, timeout=120)
            print(f"[M1 TRY] {attempt} status {r.status_code}")
            if r.status_code in [200,201]:
                m = re.search(r'"base64"\s*:\s*"([^"]{1000,})"', r.text)
                raw = m.group(1) if m else None
                if not raw:
                    try:
                        j = r.json()
                        raw = j.get("base64") or (j.get("data",{}).get("base64") if isinstance(j.get("data"),dict) else j.get("data"))
                    except:
                        pass
                b64 = clean_b64(raw) if raw else None
                if b64 and len(b64) > 1000:
                    try:
                        dec = base64.b64decode(b64, validate=False)
                        if len(dec) > 18*1024*1024:
                            print(f"[M1] too big {len(dec)}")
                            return None, None
                    except Exception as e:
                        print(f"[M1] decode check {e}")
                    mt = "application/pdf" if is_pdf else "image/jpeg"
                    print(f"[M1 OK] len={len(b64)} mt={mt}")
                    return b64, mt
        except Exception as e:
            print(f"[M1] try {attempt} err {e}")
        time.sleep(5)
    print("[M1 FAIL] no b64")
    return None, None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    prompt = SYSTEM_PROMPT + f"\n\n學生功課: {question}\n\n重要：呢份有幾多題就改幾多題，如果係PDF 6 pages就要由P1改到P6，逐條Q出，唔可以只改一條！記住唔可以用 $ \\le"
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
        parts = [{"text": prompt}]
        if file_b64:
            parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
        body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": {"temperature": 0.28, "maxOutputTokens": 6000}}
        try:
            r = requests.post(url, json=body, headers=headers, timeout=120)
            print(f"[GEMINI TRY] {model} {r.status_code}")
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                # V10.11 溫和洗LaTeX，唔會洗走英文，保留人性化
                txt = txt.replace("\\le","<=").replace("\\ge",">=").replace("\\leq","<=").replace("\\geq",">=").replace("\\ne","!=").replace("\\times","x").replace("\\cdot","*").replace("\\sqrt","sqrt")
                txt = txt.replace("\\","")
                txt = txt.replace("$","")
                txt = txt.replace("$$","")
                print(f"[GEMINI OK] {model} len={len(txt)}")
                return txt, "ok"
            else:
                print(f"[GEMINI FAIL] {model} {r.text[:800]}")
        except Exception as e:
            print(f"[GEMINI EXC] {model} {e}")
    return f"Q1 ❌ 暫時睇唔到，麻煩影清楚啲再send，唔好超過10MB", "error"

def send_typing(jid, stop_event):
    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": jid, "presence": "composing", "delay": 25000}
    while not stop_event.is_set():
        try:
            requests.post(url, json=payload, headers=headers, timeout=10)
        except:
            pass
        for _ in range(25):
            if stop_event.is_set():
                break
            time.sleep(0.1)

def send_text(jid, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        text = text.strip()
        if not text:
            text = "收到你份功課喇，幫你逐題睇下～"
        # 保留人性化格式，唔洗走 *錯喺邊*
        for i in range(0, len(text), 2800):
            chunk = text[i:i+2800]
            requests.post(url, json={"number": jid, "text": chunk}, headers=headers, timeout=20)
            time.sleep(0.7)
    except Exception as e:
        print(f"Send fail {e}")

def create_annotated_image(original_b64, annotations):
    try:
        from PIL import Image, ImageDraw, ImageFont
        img_data = base64.b64decode(clean_b64(original_b64))
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size
        if not annotations:
            print("[ANNOTATE] no annotations")
            return None
        try:
            fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            font = ImageFont.truetype(fp, max(14, int(h*0.024)))
            font_bold = ImageFont.truetype(fp, max(15, int(h*0.028)))
        except:
            font = ImageFont.load_default()
            font_bold = font
        for ann in annotations[:6]:
            try:
                x = float(ann.get("x",0.5))
                y = float(ann.get("y",0.5))
                x2 = ann.get("x2")
                y2 = ann.get("y2")
                raw_txt = ann.get("text","").strip()
                if not (0.02 < x < 0.98 and 0.02 < y < 0.98):
                    continue
                cx, cy = int(w*x), int(h*y)
                if x2 is not None and y2 is not None:
                    try:
                        x2f = float(x2); y2f = float(y2)
                        if 0.02 < x2f < 0.98 and 0.02 < y2f < 0.98:
                            cx2, cy2 = int(w*x2f), int(h*y2f)
                            draw.line([cx,cy,cx2,cy2], fill=(210,0,0), width=max(3,int(min(w,h)*0.008)))
                            draw.ellipse([cx2-7,cy2-7,cx2+7,cy2+7], fill=(210,0,0))
                    except:
                        pass
                r = int(min(w,h)*0.042)
                draw.ellipse([cx-r-4,cy-r-4,cx+r+4,cy+r+4], outline=(255,230,0), width=4)
                draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline=(210,0,0), width=4)
                if raw_txt:
                    txt = ''.join(c for c in raw_txt if ord(c) < 128)[:35].strip()
                    if not txt:
                        continue
                    tx = cx + r + 14; ty = cy - 8
                    if tx + 200 > w: tx = max(8, cx - r - 180)
                    if ty < 10: ty = cy + r + 8
                    bbox = draw.textbbox((tx,ty), txt, font=font)
                    pad=6
                    draw.rounded_rectangle([bbox[0]-pad, bbox[1]-pad, bbox[2]+pad, bbox[3]+pad], radius=8, fill=(255,255,255), outline=(50,100,200), width=2)
                    draw.text((tx,ty), txt, fill=(20,60,160), font=font_bold)
            except Exception as e:
                print(f"ann err {e}")
                continue
        buf = io.BytesIO()
        img.save(buf,"JPEG",quality=93)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[ANNOTATE] {e}")
        return None

def send_image(jid, image_input, caption):
    for attempt in range(3):
        try:
            if isinstance(image_input, str) and len(image_input) > 1000 and "/" not in image_input[:100]:
                b64_data = clean_b64(image_input)
            else:
                b64_data = base64.b64encode(open(image_input,"rb").read()).decode() if os.path.exists(str(image_input)) else clean_b64(image_input)
            if not b64_data or len(b64_data) < 1000:
                print("[SEND IMAGE] bad b64")
                return False
            url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            payload = {"number": jid, "mediatype": "image", "media": b64_data, "caption": caption, "fileName": f"marked_{int(time.time())}.jpg"}
            r = requests.post(url, json=payload, headers=headers, timeout=40)
            print(f"[SEND IMAGE] {r.status_code}")
            if r.status_code in [200,201]:
                return True
        except Exception as e:
            print(f"sendImage exc {e}")
        time.sleep(2)
    return False

def do_work(jid, text, push_name, participant, from_me, msg, data, msg_id):
    with LOCK:
        now = time.time()
        for k in list(SEEN_IDS.keys()):
            if now - SEEN_IDS[k] > 300:
                del SEEN_IDS[k]
        if msg_id in SEEN_IDS:
            print(f"[DEDUP] skip {msg_id}")
            return
        SEEN_IDS[msg_id] = now

    stop_typing = threading.Event()
    threading.Thread(target=send_typing, args=(jid, stop_typing), daemon=True).start()

    def is_teacher_user():
        if from_me:
            return True
        digits = re.sub(r'\D','', participant if "@g.us" in jid else jid)
        return any(t in digits for t in TEACHER_NUMBERS)

    is_group = "@g.us" in jid
    if is_group:
        if jid not in GROUP_STATE:
            GROUP_STATE[jid] = True; save_state()
        low = text.lower().strip()
        open_keys = ["開放提問","開放發問","開始發問","開始提問","開放功課","/open","開始"]
        close_keys = ["關閉提問","關閉發問","結束提問","結束發問","/close","停止發問","收工","關閉","結束"]
        if any(k in text for k in open_keys) or low in ["open","開始","開放"]:
            if not is_teacher_user():
                stop_typing.set(); return
            GROUP_STATE[jid] = True; save_state(); stop_typing.set()
            send_text(jid, f"{TICK} \n老師已開放提問！依家同學可以問 LC Sir 喇～")
            return
        if any(k in text for k in close_keys) or low in ["close","關閉","結束"]:
            if not is_teacher_user():
                stop_typing.set(); return
            GROUP_STATE[jid] = False; save_state(); stop_typing.set()
            send_text(jid, "🔒 \n老師已關閉提問，LC Sir 休息中～")
            return
        if not GROUP_STATE.get(jid, True):
            low2 = text.lower()
            if not any(k in low2 for k in ["lc","阿sir","阿 sir","sir","老師"]):
                stop_typing.set(); return

    if from_me and not is_group:
        stop_typing.set(); return

    if "@g.us" in jid:
        low = text.lower()
        if not any(k in low for k in ["lc","阿sir","阿 sir","sir","老師"]) and "imageMessage" not in msg and "documentMessage" not in msg:
            cap = msg.get("imageMessage", {}).get("caption") if "imageMessage" in msg else ""
            if not cap:
                stop_typing.set(); return
        text = f"[{push_name} 問]: {text}"

    b64, mime = None, "image/jpeg"
    is_image_msg = "imageMessage" in msg
    is_pdf_msg = "documentMessage" in msg

    if is_image_msg:
        b64, mime = get_file_base64(data, is_pdf=False)
        cap = msg["imageMessage"].get("caption") or ""
        text = (cap or text or "幫我睇下呢份功課，入面有幾題，要逐題改晒").strip()
    elif is_pdf_msg:
        b64, mime = get_file_base64(data, is_pdf=True)
        text = (text or "幫我睇下呢份PDF功課，6 pages，要逐頁逐題改晒").strip()
        mime = "application/pdf"

    if not text and not b64:
        stop_typing.set(); return
    if (is_image_msg or is_pdf_msg) and not b64:
        stop_typing.set()
        send_text(jid, "張圖/PDF仲 load 緊或者太大(你嗰個2.8MB其實ok，但57.6MB嗰個太大)，麻煩 send 多次新相，唔好 forward 舊相 🙏")
        return

    answer, _ = call_gemini(text, b64, mime)
    stop_typing.set()

    annotations = []
    m_ann = re.search(r"ANNOTATIONS_JSON:\s*(\[.*?\])", answer, re.DOTALL)
    if m_ann:
        try:
            annotations = json.loads(m_ann.group(1))
        except:
            try:
                txt = m_ann.group(1).replace("'","\"")
                annotations = json.loads(txt)
            except:
                annotations = []

    clean_answer = re.sub(r"GRAPH_EQUATION.*", "", answer, flags=re.DOTALL).strip()
    clean_answer = re.sub(r"ANNOTATIONS_JSON:.*", "", clean_answer, flags=re.DOTALL).strip()
    clean_answer = re.sub(r"```.*?```", "", clean_answer, flags=re.DOTALL).strip()
    if not clean_answer or len(clean_answer) < 30:
        clean_answer = answer.split("ANNOTATIONS_JSON")[0].split("GRAPH_EQUATION")[0].strip()
    clean_answer = clean_answer.replace("$","")
    if not clean_answer:
        clean_answer = "睇到你份功課喇，幫你逐題望下～"
    if "@g.us" in jid and push_name and not clean_answer.startswith(f"@{push_name}"):
        clean_answer = f"@{push_name} {clean_answer}"

    send_text(jid, clean_answer)

    if is_image_msg and b64 and mime != "application/pdf" and annotations:
        time.sleep(1)
        img_b64 = create_annotated_image(b64, annotations)
        if img_b64:
            send_image(jid, img_b64, f"{CROSS} 睇圖，紅圈就係錯嘅位")

    print(f"[{VERSION}] done len={len(clean_answer)} ann={len(annotations)}")

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json or {}
    data = body.get("data", {})
    key = data.get("key", {})
    msg = data.get("message", {})
    jid = key.get("remoteJid")
    push_name = data.get("pushName") or ""
    participant = key.get("participant") or data.get("participant") or ""
    from_me = key.get("fromMe", False)
    if not jid:
        return jsonify({"ok": True}), 200
    text = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
    if not text and "imageMessage" in msg:
        text = msg["imageMessage"].get("caption") or ""
    msg_id = key.get("id") or str(data.get("id") or "") or f"no-id-{int(time.time()*1000)}"
    threading.Thread(target=do_work, args=(jid, text, push_name, participant, from_me, msg, data, msg_id), daemon=True).start()
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir {VERSION} {TICK}", 200

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
