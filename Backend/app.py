import os
from dotenv import load_dotenv
load_dotenv()


from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from datetime import datetime

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

DAILY_LIMIT = 15
usage_tracker = {}

def check_limit(ip):
    today = datetime.now().date()
    if ip not in usage_tracker:
        usage_tracker[ip] = {"date": today, "count": 0}
    record = usage_tracker[ip]
    if record["date"] != today:
        record["date"] = today
        record["count"] = 0
    if record["count"] >= DAILY_LIMIT:
        return False
    record["count"] += 1
    return True

@app.route("/chat", methods=["POST"])
def chat():
    user_ip = request.remote_addr
    data = request.json
    user_message = data.get("message", "")
    history = data.get("history", [])

    if not check_limit(user_ip):
        return jsonify({"reply": "Aaj ki limit khatam ho gayi hai. Kal try karein! 🙏"})

    try:
        messages = [
            {"role": "system", "content": "Tum ek helpful Pakistani AI assistant ho. Roman Urdu aur English mix mein jawab do."}
        ] + history + [{"role": "user", "content": user_message}]

        completion = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages
        )
        reply = completion.choices[0].message.content
    except Exception:
        reply = "Kuch masla ho gaya. Dobara try karo."

    return jsonify({"reply": reply})

if __name__ == "__main__":
    app.run(debug=True, port=5000)