# app.py
"""
CareLink v1 - reminders + reply logging + alerts + simple dashboard
Run: python app.py
Requires: Twilio credentials in .env, ngrok public URL set in Twilio sandbox incoming webhook -> /webhook
"""

import os
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template_string
from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
import atexit
# --- TIMEZONE FIX IMPORTS ---
from pytz import timezone
# ----------------------------

load_dotenv()

# === Config from env ===
TW_SID = os.getenv("TWILIO_ACCOUNT_SID")
TW_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TW_WHATSAPP = os.getenv("TWILIO_WHATSAPP_NUMBER")  # 'whatsapp:+14155238886'
ADMIN_PHONE = os.getenv("ADMIN_PHONE")             # '+91...'
BROTHER_PHONE = os.getenv("BROTHER_PHONE")         # '+91...'
REPLY_MATCH_WINDOW_MIN = int(os.getenv("REPLY_MATCH_WINDOW_MIN", "30"))
ALERT_IF_NO_YES_MINUTES = int(os.getenv("ALERT_IF_NO_YES_MINUTES", REPLY_MATCH_WINDOW_MIN))
MISS_THRESHOLD = int(os.getenv("MISS_THRESHOLD", "1"))

# Timezone setting for scheduling (using IST)
TIMEZONE = timezone('Asia/Kolkata')

if not (TW_SID and TW_TOKEN and TW_WHATSAPP):
    print("Warning:Missing Twilio env vars. Fill .env before running.")
client = Client(TW_SID, TW_TOKEN) if TW_SID and TW_TOKEN else None

# === App & DB ===
app = Flask(__name__)
DB_FILE = "medi_ping.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                phone TEXT UNIQUE,
                active INTEGER DEFAULT 1
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS sent_reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT,
                reminder_tag TEXT,
                timestamp TEXT,
                message_sid TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_phone TEXT,
                timestamp TEXT,
                reminder_tag TEXT,
                response TEXT,
                raw_message TEXT
            )
        """)
        conn.commit()

init_db()

def add_user(name, phone):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (name, phone) VALUES (?, ?)", (name, phone))
        conn.commit()

def get_users():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT name, phone FROM users WHERE active=1")
        return c.fetchall()

def store_sent_reminder(user_phone, reminder_tag, timestamp, message_sid):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO sent_reminders (user_phone, reminder_tag, timestamp, message_sid) VALUES (?, ?, ?, ?)",
                  (user_phone, reminder_tag, timestamp.isoformat(), message_sid))
        conn.commit()

def log_response(user_phone, reminder_tag, response, raw_message):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO responses (user_phone, timestamp, reminder_tag, response, raw_message) VALUES (?, ?, ?, ?, ?)",
                  (user_phone, datetime.utcnow().isoformat(), reminder_tag, response, raw_message))
        conn.commit()

def find_recent_sent_reminder(user_phone, within_minutes=REPLY_MATCH_WINDOW_MIN):
    cutoff = datetime.utcnow() - timedelta(minutes=within_minutes)
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT id, reminder_tag, timestamp FROM sent_reminders
            WHERE user_phone=? AND timestamp >= ?
            ORDER BY timestamp DESC LIMIT 1
        """, (user_phone, cutoff.isoformat()))
        row = c.fetchone()
        if row:
            return {"id": row[0], "tag": row[1], "timestamp": row[2]}
        return None

def recent_yes_count_for_sent(user_phone, reminder_tag, since_timestamp):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM responses
            WHERE user_phone=? AND reminder_tag=? AND response='yes' AND timestamp >= ?
        """, (user_phone, reminder_tag, since_timestamp))
        r = c.fetchone()
        return r[0] if r else 0

# === Twilio send helper ===
def send_whatsapp(phone, text):
    if not client:
        print("Twilio client not configured.")
        return None
    try:
        msg = client.messages.create(body=text, from_=TW_WHATSAPP, to=f"whatsapp:{phone}")
        return getattr(msg, "sid", None)
    except Exception as e:
        print("Twilio send error:", e)
        return None

# === Reminder templates (you can change language per number) ===
REMINDERS = {
    "breakfast": {"time":"09:00", "text":"{name}, ಬೆಳಗ್ಗೆ ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳಿ. (ಹೌದು/ಇಲ್ಲ)"},
    "lunch": {"time":"14:00", "text":"{name}, ಮಧ್ಯಾಹ್ನ ಊಟದ ನಂತರ ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳಿ. (ಹೌದು/ಇಲ್ಲ)"},
    "dinner": {"time":"20:00", "text":"{name}, ರಾತ್ರಿ ಊಟದ ನಂತರ ಔಷಧಿ ತೆಗೆದುಕೊಳ್ಳಿ. (ಹೌದು/ಇಲ್ಲ)"}
}

# === Personalized mapping example (phone->name). You can expand for meds per meal later.
def load_recipients_from_db():
    rows = get_users()
    # returns list of (name, phone)
    return rows

def send_reminder_to_all(reminder_tag):
    rows = load_recipients_from_db()
    template = REMINDERS[reminder_tag]['text']
    sent_time = datetime.utcnow()
    for name, phone in rows:
        text = template.format(name=name)
        sid = send_whatsapp(phone, text)
        store_sent_reminder(phone, reminder_tag, sent_time, sid)
        print(f"Sent {reminder_tag} -> {name} ({phone}) SID={sid}")

# === After-send check: run after ALERT_IF_NO_YES_MINUTES to alert admin if no yes ===
def check_and_alert_for_tag(reminder_tag):
    rows = load_recipients_from_db()
    for name, phone in rows:
        # find the last sent reminder for this phone & tag (limit to recent window)
        cutoff_dt = datetime.utcnow() - timedelta(minutes=ALERT_IF_NO_YES_MINUTES + 5)
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, timestamp FROM sent_reminders
                WHERE user_phone=? AND reminder_tag=? AND timestamp >= ?
                ORDER BY timestamp DESC LIMIT 1
            """, (phone, reminder_tag, cutoff_dt.isoformat()))
            row = c.fetchone()
        if not row:
            continue
        sent_id, sent_ts = row[0], row[1]
        yes_count = recent_yes_count_for_sent(phone, reminder_tag, sent_ts)
        
        # --- Indentation Corrected ---
        if yes_count < 1:
            # missed -> send alert
            alert_text = f"ALERT: {name} may have missed {reminder_tag} reminder sent at {sent_ts} (no YES received)."
            # send to admin and brother
            if ADMIN_PHONE:
                send_whatsapp(ADMIN_PHONE, alert_text)
            if BROTHER_PHONE:
                send_whatsapp(BROTHER_PHONE, alert_text)
            print("Alert sent for", phone)
        # --- Indentation Corrected ---


# === Flask webhook to receive replies ===
@app.route("/webhook", methods=["POST"])
def webhook():
    from_number = request.values.get("From", "").replace("whatsapp:", "")
    body = request.values.get("Body", "").strip()
    body_norm = body.lower()
    resp = MessagingResponse()

    yes_tokens = {"yes", "y", "1", "ಹೌದು", "ತೊರೆದಿದೆ", "ತಗೊಳಿಸಿದೆ", "took", "taken", "done"}
    no_tokens = {"no", "n", "0", "not yet", "ನೋಟ್", "ಇಲ್ಲ", "later", "missed"}

    matched = find_recent_sent_reminder(from_number, within_minutes=REPLY_MATCH_WINDOW_MIN)
    matched_tag = matched['tag'] if matched else "unknown"

    if any(tok in body_norm for tok in yes_tokens) or body_norm in yes_tokens:
        log_response(from_number, matched_tag or "unknown", "yes", body)
        resp.message("ಧನ್ಯವಾದಗಳು! ನಿರ್ಬಂಧ ಮಾಡಲಾಗಿದೆ. ✅")
    elif any(tok in body_norm for tok in no_tokens) or body_norm in no_tokens:
        log_response(from_number, matched_tag or "unknown", "no", body)
        resp.message("ಸರಿ, ತಿಳಿಸಲಾಗಿದೆ. ದಯವಿಟ್ಟು ಬೇಗ ತಗೊಳ್ಳಿ.")
    else:
        log_response(from_number, matched_tag or "unknown", "unclear", body)
        resp.message("ದಯವಿಟ್ಟು ಹೌದು ಅಥವಾ ಇಲ್ಲ ಎಂದು ಉತ್ತರಿಸಿ (1 = ಹೌದು, 2 = ಇಲ್ಲ).")

    return str(resp)

# === Small dashboard (not secure — local dev only) ===
DASH_TEMPLATE = """
<!doctype html>
<title>CareLink Dashboard</title>
<h2>CareLink - Recent Sent Reminders</h2>
<table border=1 cellpadding=6>
<tr><th>ID</th><th>Phone</th><th>Tag</th><th>Sent at (UTC)</th><th>SID</th></tr>
{% for row in sent %}
<tr><td>{{row[0]}}</td><td>{{row[1]}}</td><td>{{row[2]}}</td><td>{{row[3]}}</td><td>{{row[4]}}</td></tr>
{% endfor %}
</table>

<h2>Recent Responses</h2>
<table border=1 cellpadding=6>
<tr><th>ID</th><th>Phone</th><th>Time (UTC)</th><th>Tag</th><th>Response</th><th>Raw</th></tr>
{% for r in resp %}
<tr><td>{{r[0]}}</td><td>{{r[1]}}</td><td>{{r[2]}}</td><td>{{r[3]}}</td><td>{{r[4]}}</td><td>{{r[5]}}</td></tr>
{% endfor %}
</table>
"""

@app.route("/dashboard")
def dashboard():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_phone, reminder_tag, timestamp, message_sid FROM sent_reminders ORDER BY id DESC LIMIT 50")
        sent = c.fetchall()
        c.execute("SELECT id, user_phone, timestamp, reminder_tag, response, raw_message FROM responses ORDER BY id DESC LIMIT 50")
        resp = c.fetchall()
    return render_template_string(DASH_TEMPLATE, sent=sent, resp=resp)

# === Admin endpoints for adding users and manual trigger ===
@app.route("/add_user", methods=["POST"])
def route_add_user():
    data = request.json or {}
    name = data.get("name")
    phone = data.get("phone")
    if not (name and phone):
        return jsonify({"error":"name and phone required"}), 400
    add_user(name, phone)
    return jsonify({"status":"ok"})

@app.route("/trigger/<reminder_tag>", methods=["POST"])
def trigger(reminder_tag):
    tag = reminder_tag.lower()
    if tag not in REMINDERS:
        return jsonify({"error":"unknown tag"}), 400
    send_reminder_to_all(tag)
    
    # --- TIMEZONE FIX IMPLEMENTATION (Manual Trigger) ---
    # Calculate check time using local timezone (Asia/Kolkata = IST)
    ist = timezone('Asia/Kolkata')
    check_time = datetime.now(ist) + timedelta(minutes=ALERT_IF_NO_YES_MINUTES)
    
    print(f"Alert check scheduled for: {check_time.isoformat()}") # ADDED PRINT
    scheduler.add_job(lambda t=tag: check_and_alert_for_tag(t), 'date', run_date=check_time)
    return jsonify({"status":"sent", "tag":tag})
