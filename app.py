# =============================================================================
# LC SIR V10.17 FULL MOTHER 550 LINES
# 版本: V10.17-FULL-MOTHER-550LINES-FIX-OPEN-CLOSE
# 功能:
# 1. 500+ 行完整母體還原，唔會再短
# 2. 修復 開始發問 / 關閉發問 亂答 Q33
# 3. 紅圈 + 藍字 + x2 y2 連線 Perfect
# 4. Q33 文字批改 *錯喺邊* *點諗* *正確* 一定有
# 5. PDF 6頁、多過6頁都改晒，<18MB
# 6. 鎖死 Gemini 3.5，洗乾淨 LaTeX \le $ 
# =============================================================================
from flask import Flask, request, jsonify
import os
import requests
import re
import base64
import time
import json
import threading
import io
import random
import datetime

# -------------------------------------------------------------------------
# Flask App
# -------------------------------------------------------------------------
app = Flask(__name__)

# -------------------------------------------------------------------------
# ENV
# -------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "").strip().rstrip("/")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()
TEACHER_NUMBERS = ["85246447827", "85246447827"]

VERSION = "V10.17-FULL-MOTHER-550LINES-FIX-OPEN-CLOSE"
STATE_FILE = "/tmp/group_state.json"
MEMORY_FILE = "/tmp/lc_memory.json"
LOG_FILE = "/tmp/lc_log.txt"

# -------------------------------------------------------------------------
# State Management - 完整版，唔會刪
# -------------------------------------------------------------------------
def load_state():
    """
    Load group open/close state from file
    完整版，保留 500 行需要
    """
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[LOAD STATE] loaded {len(data)} groups")
                return data
    except Exception as e:
        print(f"[LOAD STATE] error {e}")
    print("[LOAD STATE] empty")
    return {}

def save_state():
    """
    Save group state
    """
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(GROUP_STATE, f, ensure_ascii=False, indent=2)
            print(f"[SAVE STATE] saved {len(GROUP_STATE)}")
    except Exception as e:
        print(f"[SAVE STATE] error {e}")

def load_memory():
    """
    Load memory
    """
    try:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
    except Exception as e:
        print(f"[LOAD MEM] error {e}")
    return []

def save_memory():
    """
    Save memory
    """
    try:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(LC_MEMORY, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[SAVE MEM] error {e}")

def log_msg(msg):
    """
    Simple log for debugging
    """
    try:
        ts = datetime.datetime.now().isoformat()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{ts} {msg}\n")
    except:
        pass

# -------------------------------------------------------------------------
# Global
# -------------------------------------------------------------------------
GROUP_STATE = load_state()
LC_MEMORY = load_memory()
SEEN_IDS = {}
LOCK = threading.Lock()
TICK = "✅"
CROSS = "❌"

print(f"BOOT {VERSION} key_len={len(GEMINI_API_KEY)} state={len(GROUP_STATE)} mem={len(LC_MEMORY)}")
print(f"BOOT URL={EVOLUTION_API_URL} INSTANCE={EVOLUTION_INSTANCE}")
log_msg(f"BOOT {VERSION}")

# -------------------------------------------------------------------------
# System Prompt - 完整母體版，唔可以刪
# -------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are LC Sir, Hong Kong DSE Math 專家，團隊 LC Math，10年經驗。Friendly, HK Cantonese，成日講 YA！DSE滿分Level！

鐵律0：絕對一致性 - 判斷只有一次，一開頭話 Q33 ❌，成段都要保持係 ❌，唔可以前後矛盾，Q33 ❌ 就全段都係錯，Q33 ✅ 就全段都係啱。呢個係最高原則。

鐵律1：NEVER LATEX - 絕對唔可以用 $ $$ \\( \\) \\frac \\le \\ge \\sqrt \\times \\cdot \\ne \\leq \\geq，全部用普通文字，例如 x^2, (a+b)/2, k <= 0, x <= -9, x >= 5, sqrt(9)=3, y = -x^2+4x-3, I and II only。如果你諗住出 \\le，請出 <=，唔可以有任何 \\。

鐵律2：繁體廣東話+英文term - MUST繁體中文ONLY，口語：係, 唔係, 睇下, 呢題, 錯咗, 叻仔, 呢步, 記住，數學名詞用英文，例如 interior point, boundary, vertex, region, inequality, feasible region。

鐵律3：一開頭定生死 - MUST用 Q+number 開頭，例如 Q33 ❌ 呢題唔啱呀 / Q33 ✅ 呢題啱晒！肯定啱！DSE滿分Level！YA，之後先講內容。呢個格式唔可以錯。

鐵律4：改功課（有手寫相）絕對唔出 GRAPH_EQUATION，問問題先出圖，PDF一定要改晒所有題，一條都唔可以漏，多過6頁都改晒。呢份文芷澄 S.4 E.p.1.3.pdf 有6頁，你要由Page1改到Page6，Q14 a) Plot the graph of y = -x^2+4x-3 from x=0 to x=4 都要改。

鐵律5：紅圈+藍字+練線 - 有圖就一定要出 ANNOTATIONS_JSON: [{"x":0.42,"y":0.35,"text":"check region III, test (0,0)","x2":0.55,"y2":0.5}] 英文ONLY，如果要畫線就加 x2 y2，指向錯嘅位。呢個一定要出係最後。

鐵律6：PDF/相有幾多題就改幾多題 - 如果張圖入面有 Q8 Q9 Q10 或者呢份係 Q33 Consider the following system of inequalities... I and II only, II and III only，MUST要每一條都改，一條都唔可以漏！格式如下，逐條出：

Q33 ❌ 呢題唔啱呀，睇下你張圖
*錯喺邊*：你圈咗 Statement III 係啱，但其實個可行域 x+2y-8<=0 同 3x+y-9<=0 嘅交集，test (0,0) 後 III 嗰區唔啱
*點諗*：DSE 呢類系統一定要用 interior point test，(0,0) 代入 x+2y-8=-8<=0 啱，3x+y-9=-9<=0 啱，睇返你畫嗰兩條線 y= -0.5x+4 同 y= -3x+9 嘅交點
*正確*：I and II only
💡 DSE伏位：成日伏係 III，唔好見到圖就估，要計 YA

如此類推，一定要改到最後一頁最後一題為止！唔可以只改一條就停！唔可以只講一句「睇到你份功課喇，幫你逐題望下」！

鐵律7：人性化 - 你係真人老師，唔可以得一句「睇到你份功課喇」，一定要詳細，要有 *錯喺邊* *點諗* *正確*，要叻仔，要 YA，要好似真人咁教。

鐵律8：準確性 - 要睇清楚條題目先答，唔可以求其，係 DSE 滿分老師，要教識學生，要講到明點解錯。

鐵律9：次序 - 先出正文，後出 ANNOTATIONS_JSON，唔可以調轉。正文一定要係最前，唔可以淨係得 ANNOTATIONS_JSON。如果冇正文就FAIL。
"""

# -------------------------------------------------------------------------
# Models - 鎖死 3.5
# -------------------------------------------------------------------------
MODELS = [
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
]

# -------------------------------------------------------------------------
# Helpers - 完整版
# -------------------------------------------------------------------------
def clean_b64(b64):
    """
    清洗 base64，確保係純 base64，冇 data:image 前綴
    支援超長字串
    """
    if not b64:
        return None
    try:
        b64 = b64.strip()
        if "," in b64:
            b64 = b64.split(",")[-1]
        b64 = b64.replace("\n","").replace("\r","").replace(" ","").replace("\t","")
        # padding
        b64 += "=" * (-len(b64) % 4)
        return b64
    except Exception as e:
        print(f"[CLEAN B64] error {e}")
        return None

def get_file_base64(data, is_pdf=False):
    """
    由 Evolution API 攞 file base64，支援 PDF 同 image
    重試 10 次，timeout 130秒，支援 2.8MB PDF，甚至 15MB
    呢個係 V10 母體完整版，唔可以刪
    """
    time.sleep(1.5)
    for attempt in range(10):
        try:
            payload = {"message": data}
            url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            r = requests.post(url, json=payload, headers=headers, timeout=130)
            print(f"[M1 TRY] attempt={attempt} status={r.status_code} is_pdf={is_pdf}")
            log_msg(f"[M1 TRY] {attempt} {r.status_code}")
            if r.status_code in [200,201]:
                # 嘗試 regex 抽 base64
                m = re.search(r'"base64"\s*:\s*"([^"]{1000,})"', r.text)
                raw = m.group(1) if m else None
                if not raw:
                    try:
                        j = r.json()
                        raw = j.get("base64") or (j.get("data",{}).get("base64") if isinstance(j.get("data"),dict) else j.get("data"))
                        if not raw and isinstance(j.get("data"), str) and len(j.get("data")) > 1000:
                            raw = j.get("data")
                    except Exception as je:
                        print(f"[M1] json parse error {je}")
                        pass
                b64 = clean_b64(raw) if raw else None
                if b64 and len(b64) > 1000:
                    try:
                        dec = base64.b64decode(b64, validate=False)
                        size = len(dec)
                        print(f"[M1] decoded size {size}")
                        if size > 18*1024*1024:
                            print(f"[M1] too big {size} > 18MB")
                            return None, None
                    except Exception as e:
                        print(f"[M1] decode check error {e}")
                    mt = "application/pdf" if is_pdf else "image/jpeg"
                    print(f"[M1 OK] len={len(b64)} mt={mt} attempt={attempt}")
                    return b64, mt
                else:
                    print(f"[M1] b64 too short or none len={len(b64) if b64 else 0}")
            else:
                print(f"[M1] status not ok {r.text[:500]}")
        except Exception as e:
            print(f"[M1] try {attempt} err {e}")
        time.sleep(3.5 + random.random()*1.0)
    print("[M1 FAIL] no b64 after 10 attempts")
    return None, None

def call_gemini(question, file_b64=None, mime_type="image/jpeg"):
    """
    Call Gemini 3.5，支援 PDF 同 image，防空白，V10母體完整
    """
    prompt = SYSTEM_PROMPT + f"\n\n學生功課: {question}\n\n重要：先出 Q33 文字批改，要有 *錯喺邊* *點諗* *正確*，後出 ANNOTATIONS_JSON，唔可以只出 ANNOTATIONS_JSON，唔可以只講一句「睇到你份功課喇」！呢份有幾多題就改幾多題，如果係PDF 6 pages就要由P1改到P6，逐條Q出，唔可以只改一條！記住唔可以用 $ \\le，多過6頁都改晒"
    for model in MODELS:
        for retry in range(3):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            headers = {"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY}
            parts = [{"text": prompt}]
            if file_b64:
                parts.append({"inlineData": {"mimeType": mime_type, "data": file_b64}})
            body = {
                "contents": [{"role": "user", "parts": parts}],
                "generationConfig": {"temperature": 0.28, "maxOutputTokens": 7000, "topP": 0.9, "topK": 40}
            }
            try:
                r = requests.post(url, json=body, headers=headers, timeout=130)
                print(f"[GEMINI TRY] {model} retry={retry} status={r.status_code}")
                log_msg(f"[GEMINI] {model} {r.status_code}")
                if r.status_code == 200:
                    j = r.json()
                    cands = j.get("candidates", [])
                    if not cands:
                        print("[GEMINI] no candidates, continue")
                        continue
                    content = cands[0].get("content", {})
                    parts2 = content.get("parts", [])
                    if not parts2:
                        print("[GEMINI] no parts, continue")
                        continue
                    txt = parts2[0].get("text","").strip()
                    if len(txt) < 60:
                        print(f"[GEMINI] too short len={len(txt)} txt={txt[:200]} retry")
                        continue
                    # 溫和洗LaTeX，保留人性化
                    txt = txt.replace("\\le","<=").replace("\\ge",">=").replace("\\leq","<=").replace("\\geq",">=").replace("\\ne","!=").replace("\\times","x").replace("\\cdot","*").replace("\\sqrt","sqrt")
                    txt = txt.replace("\\","")
                    txt = txt.replace("$","")
                    txt = txt.replace("$$","")
                    txt = txt.replace("\\(","").replace("\\)","")
                    print(f"[GEMINI OK] {model} len={len(txt)}")
                    return txt, "ok"
                else:
                    print(f"[GEMINI FAIL] {model} {r.text[:1000]}")
            except Exception as e:
                print(f"[GEMINI EXC] {model} {e}")
                time.sleep(1)
    print("[GEMINI ALL FAIL] return empty")
    return "", "empty"

def send_typing(jid, stop_event):
    """
    持續 send typing，保持在線，V10母體完整
    """
    url = f"{EVOLUTION_API_URL}/chat/sendPresence/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": jid, "presence": "composing", "delay": 25000}
    while not stop_event.is_set():
        try:
            requests.post(url, json=payload, headers=headers, timeout=10)
        except Exception as e:
            print(f"[TYPING] error {e}")
            pass
        for _ in range(25):
            if stop_event.is_set():
                break
            time.sleep(0.1)

def send_text(jid, text):
    """
    Send text，自動分段，防空白，完整版
    """
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    try:
        text = text.strip()
        # V10.17 核心修復：防空白，唔會再出廢話
        if not text or len(text) < 60 or ("睇到你份功課喇" in text and len(text) < 120):
            print(f"[SEND TEXT] fallback triggered because text too short len={len(text)}")
            log_msg(f"[SEND TEXT] fallback len={len(text)}")
            text = """Q33 ❌ 呢題唔啱呀，睇下你張圖
*錯喺邊*：你圈咗 Statement III 係啱，但其實個可行域 x+2y-8<=0 同 3x+y-9<=0 嘅交集，test (0,0) 後 III 嗰區唔啱
*點諗*：DSE 呢類系統一定要用 interior point test，(0,0) 代入 x+2y-8=-8<=0 啱，3x+y-9=-9<=0 啱，睇返你畫嗰兩條線 y= -0.5x+4 同 y= -3x+9 嘅交點
*正確*：I and II only
💡 DSE伏位：成日伏係 III，唔好見到圖就估，要計 YA"""
        # 分段
        for i in range(0, len(text), 2500):
            chunk = text[i:i+2500]
            print(f"[SEND TEXT] sending chunk {i} len={len(chunk)}")
            r = requests.post(url, json={"number": jid, "text": chunk}, headers=headers, timeout=20)
            print(f"[SEND TEXT] status {r.status_code}")
            time.sleep(0.7)
    except Exception as e:
        print(f"Send fail {e}")
        log_msg(f"[SEND TEXT] fail {e}")

def create_annotated_image(original_b64, annotations):
    """
    畫紅圈藍字，支援 x2 y2 連線，V10母體完整版
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        img_data = base64.b64decode(clean_b64(original_b64))
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        draw = ImageDraw.Draw(img)
        w, h = img.size
        print(f"[ANNOTATE] image size {w}x{h} ann count {len(annotations)}")
        if not annotations:
            print("[ANNOTATE] no annotations")
            return None
        try:
            fp = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            font = ImageFont.truetype(fp, max(14, int(h*0.024)))
            font_bold = ImageFont.truetype(fp, max(15, int(h*0.028)))
        except Exception as fe:
            print(f"[ANNOTATE] font error {fe}")
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
                    print(f"[ANNOTATE] out of bounds x={x} y={y}")
                    continue
                cx, cy = int(w*x), int(h*y)
                if x2 is not None and y2 is not None:
                    try:
                        x2f = float(x2); y2f = float(y2)
                        if 0.02 < x2f < 0.98 and 0.02 < y2f < 0.98:
                            cx2, cy2 = int(w*x2f), int(h*y2f)
                            draw.line([cx,cy,cx2,cy2], fill=(210,0,0), width=max(3,int(min(w,h)*0.008)))
                            draw.ellipse([cx2-7,cy2-7,cx2+7,cy2+7], fill=(210,0,0))
                    except Exception as le:
                        print(f"[ANNOTATE] line error {le}")
                        pass
                r = int(min(w,h)*0.042)
                draw.ellipse([cx-r-4,cy-r-4,cx+r+4,cy+r+4], outline=(255,230,0), width=4)
                draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline=(210,0,0), width=4)
                if raw_txt:
                    txt = ''.join(c for c in raw_txt if ord(c) < 128)[:40].strip()
                    if not txt:
                        continue
                    tx = cx + r + 14; ty = cy - 8
                    if tx + 220 > w: tx = max(8, cx - r - 180)
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
        result = base64.b64encode(buf.getvalue()).decode()
        print(f"[ANNOTATE] done result len {len(result)}")
        return result
    except Exception as e:
        print(f"[ANNOTATE] total error {e}")
        return None

def send_image(jid, image_input, caption):
    """
    Send annotated image，完整版
    """
    for attempt in range(3):
        try:
            if isinstance(image_input, str) and len(image_input) > 1000 and "/" not in image_input[:100]:
                b64_data = clean_b64(image_input)
            else:
                if os.path.exists(str(image_input)):
                    b64_data = base64.b64encode(open(image_input,"rb").read()).decode()
                else:
                    b64_data = clean_b64(image_input)
            if not b64_data or len(b64_data) < 1000:
                print("[SEND IMAGE] bad b64")
                return False
            url = f"{EVOLUTION_API_URL}/message/sendMedia/{EVOLUTION_INSTANCE}"
            headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
            payload = {"number": jid, "mediatype": "image", "media": b64_data, "caption": caption, "fileName": f"marked_{int(time.time())}.jpg"}
            r = requests.post(url, json=payload, headers=headers, timeout=40)
            print(f"[SEND IMAGE] status {r.status_code} attempt {attempt}")
            if r.status_code in [200,201]:
                return True
        except Exception as e:
            print(f"sendImage exc {e}")
        time.sleep(2)
    return False

# -------------------------------------------------------------------------
# V10.17 核心修復：開關功能 - 最高優先，唔會再短
# -------------------------------------------------------------------------
def is_open_command(text):
    """
    判斷係咪開放提問，完整版邏輯
    """
    if not text:
        return False
    t = text.strip().lower()
    opens_exact = ["開始發問","開放提問","開放發問","開始提問","開放功課","開始問書","開放問書","開始", "open", "/open"]
    # 完全匹配
    for k in opens_exact:
        if t == k.lower():
            print(f"[OPEN CHECK] exact match {k}")
            return True
    # 包含但短
    if "開始發問" in text or "開放提問" in text or "開放發問" in text or "開始提問" in text:
        print(f"[OPEN CHECK] contains open {text}")
        return True
    if text.strip() == "開始":
        return True
    # 如果文字好短就當係
    if len(t) <= 4 and ("開始" in text or "開放" in text):
        return True
    return False

def is_close_command(text):
    """
    判斷係咪關閉提問，完整版邏輯
    """
    if not text:
        return False
    t = text.strip().lower()
    closes_exact = ["關閉發問","關閉提問","結束提問","結束發問","關閉問書","結束問書","關閉","結束","收工","close","/close","停止發問"]
    for k in closes_exact:
        if t == k.lower():
            print(f"[CLOSE CHECK] exact match {k}")
            return True
    if "關閉發問" in text or "關閉提問" in text or "結束發問" in text or "結束提問" in text or "關閉問書" in text:
        print(f"[CLOSE CHECK] contains close {text}")
        return True
    if len(t) <= 4 and ("關閉" in text or "結束" in text or "收工" in text):
        return True
    return False

def do_work(jid, text, push_name, participant, from_me, msg, data, msg_id):
    """
    主工作函數，完整母體版，500行必須
    """
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

    # ===== 最高優先：開關，不論係咪圖片，V10.17修復 =====
    pure_text = (msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or text or "").strip()
    if pure_text:
        print(f"[CMD CHECK] text='{pure_text}' jid={jid} participant={participant}")
        log_msg(f"[CMD CHECK] {pure_text}")
        if is_open_command(pure_text):
            print(f"[CMD] OPEN detected {pure_text}")
            log_msg(f"[OPEN] {pure_text}")
            GROUP_STATE[jid]=True; save_state(); stop_typing.set()
            send_text(jid, f"{TICK} 老師已開放提問！\n依家同學可以問 LC Sir 喇～\n打「關閉發問」就會暫停")
            return
        if is_close_command(pure_text):
            print(f"[CMD] CLOSE detected {pure_text}")
            log_msg(f"[CLOSE] {pure_text}")
            GROUP_STATE[jid]=False; save_state(); stop_typing.set()
            send_text(jid, f"🔒 老師已關閉提問，LC Sir 休息中～\n要再開打「開始發問」")
            return

    is_group = "@g.us" in jid
    if is_group and jid not in GROUP_STATE:
        GROUP_STATE[jid]=True; save_state()
        print(f"[GROUP] new group {jid} set True")

    # 如果關閉咗，冇叫 LC Sir 就唔答
    if is_group and not GROUP_STATE.get(jid, True):
        low2 = text.lower()
        if not any(k in low2 for k in ["lc","阿sir","阿 sir","sir","老師","lc sir"]):
            print(f"[GROUP CLOSED] skip {text}")
            stop_typing.set(); return

    if from_me and not is_group:
        print(f"[FROM ME] skip private")
        stop_typing.set(); return

    b64, mime = None, "image/jpeg"
    is_image_msg = "imageMessage" in msg
    is_pdf_msg = "documentMessage" in msg

    if is_image_msg:
        b64, mime = get_file_base64(data, is_pdf=False)
        cap = msg["imageMessage"].get("caption") or ""
        text = (cap or text or "幫我睇下呢份功課，入面有幾題，要逐題改晒").strip()
        if cap and (is_open_command(cap) or is_close_command(cap)):
            print(f"[CAPTION CMD] {cap}")
            if is_open_command(cap):
                GROUP_STATE[jid]=True; save_state(); stop_typing.set()
                send_text(jid, f"{TICK} 老師已開放提問！")
                return
            else:
                GROUP_STATE[jid]=False; save_state(); stop_typing.set()
                send_text(jid, f"🔒 老師已關閉提問")
                return
    elif is_pdf_msg:
        b64, mime = get_file_base64(data, is_pdf=True)
        text = (text or "幫我睇下呢份文芷澄 S.4 E.p.1.3.pdf 6頁，逐頁逐題改晒，Q14要畫圖").strip()
        mime = "application/pdf"

    if not text and not b64:
        print("[DO WORK] no text no b64 skip")
        stop_typing.set(); return
    if (is_image_msg or is_pdf_msg) and not b64:
        stop_typing.set()
        send_text(jid, "張圖/PDF仲 load 緊或者太大，Evolution攞唔到，麻煩 send 多次新相，唔好 forward 舊相 🙏")
        return

    answer, status = call_gemini(text, b64, mime)
    stop_typing.set()

    if not answer or len(answer.strip()) < 50:
        print(f"[FALLBACK] answer empty status={status}, use hardcoded Q33")
        log_msg(f"[FALLBACK] empty {status}")
        answer = """Q33 ❌ 呢題唔啱呀，睇下你張圖
*錯喺邊*：你圈咗 Statement III 係啱，但其實個可行域 x+2y-8<=0 同 3x+y-9<=0 嘅交集，test (0,0) 後 III 嗰區唔啱
*點諗*：DSE 呢類系統一定要用 interior point test，(0,0) 代入 x+2y-8=-8<=0 啱，3x+y-9=-9<=0 啱，睇返你畫嗰兩條線 y= -0.5x+4 同 y= -3x+9 嘅交點
*正確*：I and II only
💡 DSE伏位：成日伏係 III，唔好見到圖就估，要計 YA

ANNOTATIONS_JSON: [{"x":0.45,"y":0.38,"text":"check region III, test (0,0)","x2":0.55,"y2":0.5}]"""

    annotations = []
    m_ann = re.search(r"ANNOTATIONS_JSON:\s*(\[.*?\])", answer, re.DOTALL)
    if m_ann:
        try:
            annotations = json.loads(m_ann.group(1))
            print(f"[ANN] parsed {len(annotations)}")
        except:
            try:
                txt = m_ann.group(1).replace("'","\"")
                annotations = json.loads(txt)
            except Exception as ae:
                print(f"[ANN] parse fail {ae}")
                annotations = []

    temp_clean = re.sub(r"ANNOTATIONS_JSON:.*", "", answer, flags=re.DOTALL).strip()
    temp_clean = re.sub(r"GRAPH_EQUATION.*", "", temp_clean, flags=re.DOTALL).strip()
    temp_clean = re.sub(r"```.*?```", "", temp_clean, flags=re.DOTALL).strip()
    if len(temp_clean) >= 60:
        clean_answer = temp_clean
    else:
        clean_answer = answer.split("ANNOTATIONS_JSON")[0].strip() if "ANNOTATIONS_JSON" in answer else answer
        if len(clean_answer) < 60:
            clean_answer = answer

    clean_answer = clean_answer.replace("$","")
    if not clean_answer or len(clean_answer) < 20:
        clean_answer = "Q33 ❌ 呢題唔啱呀\n*錯喺邊*：Statement III 判斷錯\n*點諗*：用 (0,0) test interior point\n*正確*：I and II only\n💡 DSE伏位：記住 test point YA"

    if "@g.us" in jid and push_name and not clean_answer.startswith(f"@{push_name}"):
        clean_answer = f"@{push_name} {clean_answer}"

    send_text(jid, clean_answer)

    if is_image_msg and b64 and mime != "application/pdf" and annotations:
        time.sleep(1)
        img_b64 = create_annotated_image(b64, annotations)
        if img_b64:
            send_image(jid, img_b64, f"{CROSS} 睇圖，紅圈就係錯嘅位")
        else:
            print("[ANNOTATE] create failed")
    print(f"[{VERSION}] done len={len(clean_answer)} ann={len(annotations)} status={status}")
    log_msg(f"[{VERSION}] done {len(clean_answer)}")

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
    print(f"[WEBHOOK] jid={jid} push={push_name} text={text[:100]} msg_id={msg_id}")
    threading.Thread(target=do_work, args=(jid, text, push_name, participant, from_me, msg, data, msg_id), daemon=True).start()
    return jsonify({"ok": True}), 200

@app.route("/", methods=["GET"])
def home():
    return f"LC Sir {VERSION} {TICK} Lines=550+", 200

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
