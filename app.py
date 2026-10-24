from flask import Flask, request, jsonify
import os, requests
import google.generativeai as genai

app = Flask(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PHONE_ID = os.getenv("WHATSAPP_PHONE_ID")
TOKEN = os.getenv("WHATSAPP_TOKEN")

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash")

usage = {}

def send_text(to, txt):
    url = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
    headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
    data = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": txt[:4000]}}
    requests.post(url, headers=headers, json=data)

def solve_with_gemini(question):
    prompt = f"""
你係 Lagchun 數學助教，幫小朋友批改功課。

【重要規則】
1. 一定要用繁體中文，唔可以用簡體字
2. 回覆格式必須係三語對照：
   
   📝 繁體中文（書面語）：
   [用繁體中文解釋正解同步驟]
   
   🗣️ 廣東話（口語）：
   [用香港廣東話口語，好似同小朋友傾偈咁，例如：呢題其實好簡單啫、你睇下呢度錯咗]
   
   🔤 English：
   [Simple English explanation for the same question]

3. 批改模式：
   錯 → ❌ 指出錯邊 + 正確做法
   啱 → ✅ 讚下小朋友 + 鼓勵

題目：{question}
"""
    resp = model.generate_content(prompt)
    return resp.text

@app.route('/')
def home():
    return "Lagchun Math TA - 3 Languages Running!"

@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get("hub.verify_token") == "sketchmath123":
        return request.args.get("hub.challenge")
    return "Invalid token", 403

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        entry = request.json['entry'][0]['changes'][0]['value']
        if 'messages' not in entry:
            return jsonify({"ok": True})
        msg = entry['messages'][0]
        frm = msg['from']

        if usage.get(frm, 0) >= 20:
            send_text(frm, "今日已經幫你睇咗20頁喇，聽日再嚟啦！\n今日已檢查20頁，明日再來！\n20 pages done today, come back tomorrow! HK$55/m 無限任睇")
            return jsonify({"limit": True})

        q = msg['text']['body'] if msg['type'] == 'text' else "請幫我檢查呢份功課"

        send_text(frm, "收到喇～阿Sir睇緊功課... ✏️\n已收到，正在檢查...\nGot it, checking homework...")

        ans = solve_with_gemini(q)
        send_text(frm, ans)
        usage[frm] = usage.get(frm, 0) + 1
    except Exception as e:
        print(e)
    return jsonify({"ok": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
