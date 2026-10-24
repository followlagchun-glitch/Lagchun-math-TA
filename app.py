from flask import Flask, request, jsonify
import os
import requests
import google.generativeai as genai

app = Flask(__name__)

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EVOLUTION_API_URL = os.environ.get("EVOLUTION_API_URL")  # e.g. https://your-evolution.onrender.com
EVOLUTION_INSTANCE = os.environ.get("EVOLUTION_INSTANCE") # e.g. lc-math-bot
EVOLUTION_API_KEY = os.environ.get("EVOLUTION_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

def solve_with_gemini(user_msg):
    prompt = f"你是LC math的小助手，用繁體中文，簡潔解答數學問題：{user_msg}"
    response = model.generate_content(prompt)
    return response.text

def send_text(to_number, text):
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "number": to_number,
        "text": text
    }
    requests.post(url, json=payload, headers=headers)

@app.route("/", methods=["GET"])
def home():
    return "LC math bot is Live!", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    try:
        # Evolution API format
        message_data = data.get("data", {})
        user_msg = message_data.get("message", {}).get("conversation") or message_data.get("message", {}).get("extendedTextMessage", {}).get("text")
        remote_jid = message_data.get("key", {}).get("remoteJid")  # e.g. 85246447827@s.whatsapp.net

        if not user_msg or not remote_jid:
            return jsonify({"status": "ignored"}), 200

        # Ignore group and own messages
        if "@g.us" in remote_jid or message_data.get("key", {}).get("fromMe"):
            return jsonify({"status": "ignored"}), 200

        print(f"Received from {remote_jid}: {user_msg}")

        # Gemini
        reply = solve_with_gemini(user_msg)
        
        # Send
        send_text(remote_jid, reply)

    except Exception as e:
        print(f"Error: {e}")

    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
