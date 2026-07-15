import os
from dotenv import load_dotenv
load_dotenv()


from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from groq import Groq
from datetime import datetime

import base64
import re
import json

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
    history = data.get("history", [])[-10:]
    image_data = data.get("image", None)
    want_voice = data.get("voice", False)

    if not check_limit(user_ip):
        def limit_stream():
            yield f"data: {json.dumps({'type': 'chunk', 'content': 'Aaj ki limit khatam ho gayi hai. Kal try karein 🙏'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return Response(limit_stream(), mimetype="text/event-stream")

    def generate():
        full_reply = ""
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
                    messages=messages,
                    stream=True
                )
            else:
                messages = [
                    {"role": "system", "content": "Tum ek helpful Pakistani AI assistant ho. Jis language mein user baat kare, usi language mein jawab do - agar Roman Urdu"
                    " mein pocha jaye to Roman Urdu mein jawab do. Jawab ki length usual mutabiq rakho - chota sawal, chota jawab, "
                    "agar user tafseeli poocha jaye to poori detail. Kabhi tables ya pipe symbols {|} use mat karo. Agar list dena zaroori ho to sirf simple bullet"
                    " points use karo, har point '- ' (dash space) se shuru karo. Bold ke liye **text** wala tareeqa use karo. Formatting hamesha saaf aur neat rakho."}
                ] + history + [{"role": "user", "content": user_message}]
                completion = groq_client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=messages,
                    stream=True
                )

            for chunk in completion:
                delta = chunk.choices[0].delta.content
                if delta:
                    full_reply += delta
                    yield f"data: {json.dumps({'type': 'chunk', 'content': delta})}\n\n"

        except Exception as e:
            print(e)
            full_reply = "Kuch masla ho gaya. Dobara try karo."
            yield f"data: {json.dumps({'type': 'chunk', 'content': full_reply})}\n\n"

        if want_voice and full_reply:
            try:
                clean_text = re.sub(r'[\*\|#_`->]', '', full_reply)
                clean_text = re.sub(r'\n+', '. ', clean_text)
                clean_text = re.sub(r'-{2,}', '', clean_text)
                speech = groq_client.audio.speech.create(
                    model="canopylabs/orpheus-v1-english",
                    voice="hannah",
                    input=clean_text[:900],
                    response_format="wav"
                )
                audio_bytes = speech.read()
                audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
                yield f"data: {json.dumps({'type': 'audio', 'content': audio_base64})}\n\n"
            except Exception as e:
                print("Voice error:", e)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(generate(), mimetype="text/event-stream")

if __name__ == "__main__":
    app.run(debug=True, port=5000)