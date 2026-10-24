from flask import Flask, request, jsonify
import os
import requests
import google.generativeai as genai

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL")
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE")
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("models/gemini-3.8-flash")

def solve_with_gemini(user_msg):
    prompt = f"你是LC math的小助手，用繁體中文，簡潔解答數學問題：{user_msg}"
    response = model.generate_content(prompt)
    return response.text

def send_text(to_number, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {"number": to_number, "text": text}
    r = requests.post(url, json=payload, headers=headers)
    print(f"Send result: {r.status_code} {r.text}")
    return r

@app.route("/", methods=["GET"])
def home():
    return "LC math bot is Live!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    try:
        message_data = data.get("data", {})
        key = message_data.get("key", {})
        msg = message_data.get("message", {})
        
        user_msg = msg.get("conversation") or msg.get("extendedTextMessage", {}).get("text")
        remote_jid = key.get("remoteJid")

        if not user_msg or not remote_jid:
            return jsonify({"status": "ignored"}), 200
        if "@g.us" in remote_jid or key.get("fromMe"):
            return jsonify({"status": "ignored"}), 200

        print(f"Received from {remote_jid}: {user_msg}")
        reply = solve_with_gemini(user_msg)
        send_text(remote_jid, reply)

    except Exception as e:
        print(f"Error: {e}")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
