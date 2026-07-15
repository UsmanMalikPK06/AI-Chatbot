import os
from dotenv import load_dotenv
load_dotenv()


from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq
from datetime import datetime

import base64

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

DAILY_LIMIT = 100
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
    image_data = data.get("image", None)
    want_voice = data.get("voice", False)

    if not check_limit(user_ip):
        return jsonify({"reply": "Aaj ki limit khatam ho gayi hai. Kal try karein! 🙏"})

    try:
        if image_data:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_message or "Is tasveer mein kya hai batao"},
                        {"type": "image_url", "image_url": {"url": image_data}}
                    ]
                }
            ]
            completion = groq_client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=messages
            )
        else:
            messages = [
                {"role": "system", "content": "Tum ek helpful Pakistani AI assistant ho. Roman Urdu aur English mix mein jawab do."}
            ] + history + [{"role": "user", "content": user_message}]

            completion = groq_client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages
            )

        reply = completion.choices[0].message.content
    except Exception as e:
        reply = "Kuch masla ho gaya. Dobara try karo."
        print(e)

    audio_base64 = None
    if want_voice:
        try:
            speech = groq_client.audio.speech.create(
                model="canopylabs/orpheus-v1-english",
                voice="hannah",
                input=reply,
                response_format="wav"
            )
            audio_bytes = speech.read()
            audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
        except Exception as e:
            print("Voice error:", e)

    return jsonify({"reply": reply, "audio": audio_base64})

if __name__ == "__main__":
    app.run(debug=True, port=5000)