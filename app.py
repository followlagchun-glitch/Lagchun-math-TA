from flask import Flask, request, jsonify
import os, requests, base64
from openai import OpenAI

app = Flask(__name__)

# Render env vars you will set later
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
TOKEN = os.getenv("WHATSAPP_TOKEN")

usage = {} # phone: count

def send_whatsapp(to, text):
    url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}"}
    data = {
        "messaging_product": "whatsapp",
        "to": to,
        "text": {"body": text[:3800]}
    }
    requests.post(url, headers=headers, json=data)

def check_math_with_gemini(image_bytes):
    b64 = base64.b64encode(image_bytes).decode()
    resp = client.chat.completions.create(
        model="google/gemini-2.0-flash-exp:free",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "You are Lagchun Math TA. Check this HK primary math homework. List wrong questions, correct answer, short explanation in Traditional Chinese. Keep short."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}}
            ]
        }]
    )
    return resp.choices[0].message.content

@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get("hub.verify_token") == "sketchmath123":
        return request.args.get("hub.challenge")
    return "ok"

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data = request.json
        msg = data['entry'][0]['changes'][0]['value']['messages'][0]
        frm = msg['from']
        
        # 20 pages limit
        if usage.get(frm, 0) >= 20:
            send_whatsapp(frm, "今日已check 20頁，聽日再嚟啦！💪 HK$55/m 無限check")
            return jsonify({"limit": True})

        # if image
        if msg['type'] == 'image':
            image_id = msg['image']['id']
            # download from WhatsApp
            meta_url = f"https://graph.facebook.com/v19.0/{image_id}"
            headers = {"Authorization": f"Bearer {TOKEN}"}
            meta_resp = requests.get(meta_url, headers=headers).json()
            img_url = meta_resp['url']
            img_bytes = requests.get(img_url, headers=headers).content
            
            send_whatsapp(frm, "收到功課，Gemini睇緊... 30秒搞掂")
            result = check_math_with_gemini(img_bytes)
            usage[frm] = usage.get(frm, 0) + 1
            left = 20 - usage[frm]
            send_whatsapp(frm, f"{result}\n\n---\n已用 {usage[frm]}/20 今日，剩{left}頁")
        else:
            send_whatsapp(frm, "請影相傳功課，我幫你check數！")

    except Exception as e:
        print(e)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
