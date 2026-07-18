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
import sqlite3
import uuid
import hashlib
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

app = Flask(__name__)
CORS(app)

groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
GOOGLE_CLIENT_ID = "331389023208-qplu0ond5tsc9m96l4fa84a951j7dar6.apps.googleusercontent.com"

DB_PATH = "/app/data/chat_data.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE,
            password_hash TEXT,
            name TEXT,
            auth_provider TEXT,
            created_at TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("Database ready ✅")

init_db()

def save_message(chat_id, user_id, role, content):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM chats WHERE id = ?", (chat_id,))
    exists = cursor.fetchone()
    if not exists:
        title = content[:40] if role == "user" else "New Chat"
        cursor.execute(
            "INSERT INTO chats (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, user_id, title, datetime.now().isoformat())
        )
    cursor.execute(
        "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def generate_token():
    return str(uuid.uuid4())

@app.route("/auth/signup", methods=["POST"])
def signup():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    name = data.get("name", "")

    if not email or not password:
        return jsonify({"error": "Email aur password zaroori hain"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if cursor.fetchone():
        conn.close()
        return jsonify({"error": "Ye email pehle se registered hai"}), 400

    user_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO users (id, email, password_hash, name, auth_provider, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, email, hash_password(password), name, "email", datetime.now().isoformat())
    )

    token = generate_token()
    cursor.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"token": token, "user_id": user_id, "name": name, "email": email})

@app.route("/auth/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, password_hash, name FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()

    if not row or row[1] != hash_password(password):
        conn.close()
        return jsonify({"error": "Email ya password ghalat hai"}), 401

    user_id, _, name = row
    token = generate_token()
    cursor.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"token": token, "user_id": user_id, "name": name, "email": email})

@app.route("/auth/google", methods=["POST"])
def google_login():
    data = request.json
    google_token = data.get("token", "")

    try:
        idinfo = id_token.verify_oauth2_token(
            google_token, google_requests.Request(), GOOGLE_CLIENT_ID
        )
        email = idinfo["email"]
        name = idinfo.get("name", "")
    except Exception as e:
        return jsonify({"error": "Google login fail ho gaya"}), 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM users WHERE email = ?", (email,))
    row = cursor.fetchone()

    if row:
        user_id, name = row
    else:
        user_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO users (id, email, password_hash, name, auth_provider, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, email, "", name, "google", datetime.now().isoformat())
        )

    token = generate_token()
    cursor.execute(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?, ?, ?)",
        (token, user_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()

    return jsonify({"token": token, "user_id": user_id, "name": name, "email": email})

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme123")

def check_admin(req):
    pwd = req.headers.get("X-Admin-Password", "")
    return pwd == ADMIN_PASSWORD

@app.route("/admin/chats", methods=["GET"])
def get_all_chats():
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT chats.id, chats.user_id, chats.title, chats.created_at,
               COUNT(messages.id) as message_count
        FROM chats
        LEFT JOIN messages ON chats.id = messages.chat_id
        GROUP BY chats.id
        ORDER BY chats.created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()

    chats = []
    for row in rows:
        chats.append({
            "id": row[0],
            "user_id": row[1],
            "title": row[2],
            "created_at": row[3],
            "message_count": row[4]
        })
    return jsonify({"chats": chats})

@app.route("/admin/chat/<chat_id>", methods=["GET"])
def get_chat_messages(chat_id):
    if not check_admin(request):
        return jsonify({"error": "Unauthorized"}), 401

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT role, content, created_at FROM messages
        WHERE chat_id = ?
        ORDER BY created_at ASC
    ''', (chat_id,))
    rows = cursor.fetchall()
    conn.close()

    messages = []
    for row in rows:
        messages.append({
            "role": row[0],
            "content": row[1],
            "created_at": row[2]
        })
    return jsonify({"messages": messages})

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
    chat_id = data.get("chat_id")
    user_id = data.get("user_id", chat_id)

    if not check_limit(user_ip):
        def limit_stream():
            yield f"data: {json.dumps({'type': 'chunk', 'content': 'Aaj ki limit khatam ho gayi hai. Kal try karein 🙏'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return Response(limit_stream(), mimetype="text/event-stream")

    if chat_id and user_message:
        save_message(chat_id, user_id, "user", user_message)

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
                    {"role": "system", "content": "Tum ek helpful Pakistani AI assistant ho. Jis language mein user baat kare, usi language mein jawab do - agar Roman Urdu mein pocha jaye to"
                    " Roman Urdu mein jawab do. Jawab ki length usual mutabiq rakho - chota sawal, chota jawab, agar user tafseeli poocha jaye to poori detail. Kabhi tables"
                    " ya pipe symbols {|} use mat karo. Agar list dena zaroori ho to sirf simple bullet points use karo, har point '- ' (dash space) se shuru karo."
                    " Bold ke liye **text** wala tareeqa use karo. Formatting hamesha saaf aur neat rakho."}
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

        if chat_id and full_reply:
            save_message(chat_id, user_id, "assistant", full_reply)

        if want_voice and full_reply:
            try:
                clean_text = re.sub(r'[\*\|#_`\->]', '', full_reply)
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