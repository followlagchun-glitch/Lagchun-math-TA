from flask import Flask, request, jsonify
import os, requests, base64

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL")
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

def solve_with_gemini(user_msg, image_b64=None, mime_type="image/jpeg"):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    
    parts = [{"text": f"你是LC math的小助手，繁體中文，專門批改數學功課。如果有圖片，仔細看題目，逐題批改，給分數和改正。問題：{user_msg or '請批改這份功課'}"}]
    
    if image_b64:
        parts.append({"inline_data": {"mime_type": mime_type, "data": image_b64}})

    payload = {"contents": [{"parts": parts}]}
    r = requests.post(url, json=payload, timeout=60)
    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except:
        print(f"Gemini error: {data}")
        return "抱歉，看不到圖片或暫時無法回答，請再傳一次。"

def send_text(to_number, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": to_number, "text": text}
    r = requests.post(url, json=payload, headers=headers)
    print(f"Send: {r.status_code}")
    return r

@app.route("/", methods=["GET"])
def home():
    return "LC math bot Live!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    try:
        d = data.get("data", {})
        key = d.get("key", {})
        msg = d.get("message", {})
        remote_jid = key.get("remoteJid")

        if not remote_jid or "@g.us" in remote_jid or key.get("fromMe"):
            return jsonify({"status": "ignored"}), 200

        user_msg = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text") or ""
        image_b64 = None

        # Check if photo
        if "imageMessage" in msg:
            # Evolution sends image base64 in message
            img = msg["imageMessage"]
            # Try get base64 from webhook payload
            image_b64 = d.get("message", {}).get("base64") or img.get("base64")
            user_msg = img.get("caption") or user_msg
            print("Received PHOTO message")

        if not user_msg and not image_b64:
            return jsonify({"status": "ignored"}), 200

        print(f"Received from {remote_jid}: {user_msg[:100]} photo={bool(image_b64)}")
        reply = solve_with_gemini(user_msg, image_b64)
        send_text(remote_jid, reply)

    except Exception as e:
        print(f"Error: {e}")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
