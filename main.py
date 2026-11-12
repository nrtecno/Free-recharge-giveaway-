
import os
import re
import sqlite3
import secrets
import threading
from datetime import datetime, timezone

import telebot
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")

if not BOT_TOKEN or not ADMIN_ID:
    raise RuntimeError("BOT_TOKEN and ADMIN_ID environment variables required")

bot = telebot.TeleBot(BOT_TOKEN)
DB = "campaign.db"


def db():
    con = sqlite3.connect(DB, timeout=20)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                created_at TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT,
                phone TEXT,
                operator TEXT,
                status TEXT DEFAULT 'Pending',
                created_at TEXT,
                UNIQUE(phone)
            )
        """)


init_db()


@bot.message_handler(commands=["start"])
def start(message):
    if message.chat.id != ADMIN_ID:
        bot.send_message(message.chat.id, "Access denied.")
        return

    campaign_id = secrets.token_urlsafe(10)

    with db() as con:
        con.execute(
            "INSERT INTO campaigns VALUES (?, ?)",
            (campaign_id, datetime.now(timezone.utc).isoformat())
        )

    link = f"{PUBLIC_URL}/c/{campaign_id}"

    bot.send_message(
        message.chat.id,
        f"🪔 आपका नया Diwali Campaign तैयार है!\n\n"
        f"Campaign Link:\n{link}\n\n"
        f"इस लिंक को शेयर कर सकते हैं।"
    )


@bot.message_handler(commands=["stats"])
def stats(message):
    if message.chat.id != ADMIN_ID:
        return

    with db() as con:
        total = con.execute(
            "SELECT COUNT(*) FROM registrations"
        ).fetchone()[0]

        pending = con.execute(
            "SELECT COUNT(*) FROM registrations WHERE status='Pending'"
        ).fetchone()[0]

        done = con.execute(
            "SELECT COUNT(*) FROM registrations WHERE status='Recharged'"
        ).fetchone()[0]

    bot.send_message(
        ADMIN_ID,
        f"📊 Campaign Statistics\n\n"
        f"Total: {total}\n"
        f"Pending: {pending}\n"
        f"Recharged: {done}"
    )


@app.get("/")
def home():
    return "🪔 Narendra Kumar Diwali Giveaway"


@app.get("/c/<campaign_id>")
def campaign(campaign_id):
    with db() as con:
        exists = con.execute(
            "SELECT id FROM campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()

    if not exists:
        return "Campaign not found", 404

    return render_template(
        "index.html",
        campaign_id=campaign_id
    )


@app.get("/register/<campaign_id>")
def registration_page(campaign_id):
    with db() as con:
        exists = con.execute(
            "SELECT id FROM campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()

    if not exists:
        return "Campaign not found", 404

    return render_template(
        "register.html",
        campaign_id=campaign_id
    )


@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}

    phone = str(data.get("phone", "")).strip()
    operator = str(data.get("operator", "")).strip()
    campaign_id = str(data.get("campaign_id", "")).strip()
    consent = data.get("consent") is True

    if not re.fullmatch(r"[6-9]\d{9}", phone):
        return jsonify(error="Invalid mobile number"), 400

    if operator not in ["Jio", "Airtel", "Vi", "BSNL"]:
        return jsonify(error="Invalid operator"), 400

    if not consent:
        return jsonify(error="Consent is required"), 400

    with db() as con:
        campaign = con.execute(
            "SELECT id FROM campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()

        if not campaign:
            return jsonify(error="Invalid campaign"), 404

        try:
            con.execute("""
                INSERT INTO registrations
                (campaign_id, phone, operator, created_at)
                VALUES (?, ?, ?, ?)
            """, (
                campaign_id,
                phone,
                operator,
                datetime.now(timezone.utc).isoformat()
            ))
        except sqlite3.IntegrityError:
            return jsonify(error="Number already registered"), 409

        reg_id = con.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

    bot.send_message(
        ADMIN_ID,
        f"🪔 NEW REGISTRATION\n\n"
        f"ID: {reg_id}\n"
        f"Mobile: {phone}\n"
        f"Operator: {operator}\n"
        f"Status: Pending"
    )

    return jsonify(
        success=True,
        message="Registration submitted successfully",
        registration_id=reg_id
    )


@app.get("/health")
def health():
    return jsonify(status="running")


def run_bot():
    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )


threading.Thread(
    target=run_bot,
    daemon=True
).start()
