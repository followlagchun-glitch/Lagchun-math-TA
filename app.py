from flask import Flask, request, jsonify
import os, requests

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL", "").rstrip("/")
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

def solve_with_gemini(user_msg, image_b64=None):
    # USE 1.5-flash = most stable, works with free API key
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent?key={GEMINI_API_KEY}"
    
    if not image_b64:
        prompt = f"你係LC Math嘅廣東話小助手，一定要用廣東話口語答(唔好用書面語)，好似香港人咁講嘢。答呢條數：{user_msg}"
        parts = [{"text": prompt}]
    else:
        prompt = f"你係LC Math嘅廣東話小助手，用廣東話口語。張相係數學功課，幫手逐題簡化：{user_msg or '幫我計哂佢'}，要列出步驟，最後加油鼓勵下學生。"
        parts = [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}]

    payload = {"contents": [{"parts": parts}]}
    print(f"Calling Gemini: has_image={bool(image_b64)}")
    r = requests.post(url, json=payload, timeout=60)
    print(f"Gemini status {r.status_code}: {r.text[:500]}")
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        print(f"Parse error {e} full {data}")
        return None

def send_text(to_number, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": to_number, "text": text}
    requests.post(url, json=payload, headers=headers, timeout=20)

def get_base64_from_evolution(data_obj):
    try:
        # Evolution v2 can fetch base64 if webhook didn't include it
        msg_id = data_obj.get("key", {}).get("id")
        if not msg_id: return None
        url = f"{EVOLUTION_API_URL}/chat/getBase64FromMediaMessage/{EVOLUTION_INSTANCE}"
        headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload = {"message": {"key": {"id": msg_id}}}
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        j = r.json()
        return j.get("base64") or j.get("data", {}).get("base64")
    except Exception as e:
        print(f"getBase64 error {e}")
        return None

@app.route("/", methods=["GET"])
def home():
    return "LC math bot Live!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    body = request.json
    print(f"WEBHOOK: {str(body)[:2000]}")
    try:
        d = body.get("data", {})
        key = d.get("key", {})
        msg = d.get("message", {})
        remote_jid = key.get("remoteJid") or body.get("sender")

        if not remote_jid or "@g.us" in str(remote_jid) or key.get("fromMe"):
            return jsonify({"status": "ignored"}), 200

        user_msg = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or body.get("pushName", "") or ""
        image_b64 = None

        if "imageMessage" in msg:
            img = msg["imageMessage"]
            user_msg = img.get("caption") or user_msg or "幫我計呢張相嘅數"
            # 1. try direct base64 from webhook
            image_b64 = msg.get("base64") or d.get("message", {}).get("base64") or img.get("base64")
            # 2. if not, fetch from Evolution API
            if not image_b64:
                print("No base64 in webhook, fetching from API...")
                image_b64 = get_base64_from_evolution(d)

        # If still no text and no image, ignore
        if not user_msg and not image_b64:
            user_msg = "1+1"

        reply = solve_with_gemini(user_msg, image_b64)
        if not reply:
            reply = f"API Key有問題呀，Gemini回覆唔到。學生問：{user_msg}，我試下：1+1=2，呢張相係Simplifying Surds，你想計邊題？ (a) √1183 = √(91×13) = 睇下可唔可以再簡化"

        send_text(remote_jid, reply)

    except Exception as e:
        print(f"Webhook error: {e}")
        import traceback; traceback.print_exc()

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
