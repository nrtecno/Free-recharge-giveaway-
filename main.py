
import os
import re
import sqlite3
import secrets
import threading
import logging
from datetime import datetime, timezone
from functools import wraps

import telebot
from flask import Flask, request, jsonify, render_template, abort

# ---------------- CONFIGURATION ----------------

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "").rstrip("/")
DB = os.getenv("DATABASE_PATH", "campaign.db")

OPERATORS = {"Jio", "Airtel", "Vi", "BSNL"}

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN or not ADMIN_ID or not PUBLIC_URL:
    raise RuntimeError(
        "BOT_TOKEN, ADMIN_ID and PUBLIC_URL are required"
    )

bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

# ---------------- DATABASE ----------------

def get_db():
    os.makedirs(os.path.dirname(DB) or ".", exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    with get_db() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)

        con.execute("""
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id TEXT NOT NULL,
                phone TEXT NOT NULL UNIQUE,
                operator TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)


init_db()

# ---------------- HELPERS ----------------

def is_admin(message):
    return message.from_user.id == ADMIN_ID


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def notify_admin(text):
    try:
        bot.send_message(ADMIN_ID, text)
    except Exception:
        logger.exception("Admin notification failed")


def admin_only(func):
    @wraps(func)
    def wrapper(message, *args, **kwargs):
        if not is_admin(message):
            bot.reply_to(message, "⛔ Access denied.")
            return
        return func(message, *args, **kwargs)
    return wrapper


def get_registration(reg_id):
    with get_db() as con:
        return con.execute(
            "SELECT * FROM registrations WHERE id=?",
            (reg_id,)
        ).fetchone()


# ---------------- TELEGRAM BOT ----------------

@bot.message_handler(commands=["start"])
@admin_only
def start(message):
    campaign_id = secrets.token_urlsafe(12)

    with get_db() as con:
        con.execute(
            "INSERT INTO campaigns (id, created_at) VALUES (?, ?)",
            (campaign_id, timestamp())
        )

    link = f"{PUBLIC_URL}/c/{campaign_id}"

    bot.send_message(
        message.chat.id,
        "🪔 DIWALI GIVEAWAY ADMIN PANEL\n\n"
        "✅ नया Campaign तैयार है!\n\n"
        f"🔗 Campaign Link:\n{link}\n\n"
        "Commands:\n"
        "/start - नया Campaign\n"
        "/stats - Statistics\n"
        "/recent - Recent Applications\n"
        "/help - Help"
    )


@bot.message_handler(commands=["help"])
@admin_only
def help_command(message):
    bot.send_message(
        message.chat.id,
        "ADMIN COMMANDS\n\n"
        "/start - Create campaign\n"
        "/stats - View statistics\n"
        "/recent - Recent registrations\n"
        "/approve ID - Approve application\n"
        "/done ID - Mark recharge completed\n"
        "/reject ID - Reject application"
    )


@bot.message_handler(commands=["stats"])
@admin_only
def stats(message):
    with get_db() as con:
        total = con.execute(
            "SELECT COUNT(*) FROM registrations"
        ).fetchone()[0]

        pending = con.execute(
            "SELECT COUNT(*) FROM registrations WHERE status='Pending'"
        ).fetchone()[0]

        approved = con.execute(
            "SELECT COUNT(*) FROM registrations WHERE status='Approved'"
        ).fetchone()[0]

        completed = con.execute(
            "SELECT COUNT(*) FROM registrations WHERE status='Recharged'"
        ).fetchone()[0]

        rejected = con.execute(
            "SELECT COUNT(*) FROM registrations WHERE status='Rejected'"
        ).fetchone()[0]

    bot.send_message(
        message.chat.id,
        "📊 GIVEAWAY STATISTICS\n\n"
        f"Total: {total}\n"
        f"Pending: {pending}\n"
        f"Approved: {approved}\n"
        f"Recharged: {completed}\n"
        f"Rejected: {rejected}"
    )


@bot.message_handler(commands=["recent"])
@admin_only
def recent(message):
    with get_db() as con:
        rows = con.execute("""
            SELECT id, phone, operator, status
            FROM registrations
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

    if not rows:
        bot.send_message(message.chat.id, "No registrations found.")
        return

    output = ["📋 RECENT APPLICATIONS\n"]

    for row in rows:
        output.append(
            f"ID: {row['id']}\n"
            f"Mobile: {row['phone']}\n"
            f"Operator: {row['operator']}\n"
            f"Status: {row['status']}\n"
        )

    bot.send_message(message.chat.id, "\n".join(output))


def change_status(message, status):
    if not is_admin(message):
        return

    parts = message.text.split()

    if len(parts) != 2 or not parts[1].isdigit():
        bot.reply_to(message, "Usage: /command ID")
        return

    reg_id = int(parts[1])

    with get_db() as con:
        cur = con.execute("""
            UPDATE registrations
            SET status=?, updated_at=?
            WHERE id=?
        """, (status, timestamp(), reg_id))

    if cur.rowcount == 0:
        bot.reply_to(message, "Application not found.")
        return

    row = get_registration(reg_id)

    bot.send_message(
        ADMIN_ID,
        f"✅ Application #{reg_id} updated\n"
        f"Mobile: {row['phone']}\n"
        f"Operator: {row['operator']}\n"
        f"Status: {status}"
    )


@bot.message_handler(commands=["approve"])
def approve(message):
    change_status(message, "Approved")


@bot.message_handler(commands=["done"])
def done(message):
    change_status(message, "Recharged")


@bot.message_handler(commands=["reject"])
def reject(message):
    change_status(message, "Rejected")


# ---------------- WEBSITE ----------------

@app.get("/")
def home():
    return """
    <h2>🪔 Narendra Kumar Diwali Giveaway</h2>
    <p>Campaign service is running.</p>
    """


@app.get("/c/<campaign_id>")
def campaign(campaign_id):
    with get_db() as con:
        row = con.execute(
            "SELECT id FROM campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()

    if not row:
        abort(404)

    return render_template(
        "index.html",
        campaign_id=campaign_id
    )


@app.get("/register/<campaign_id>")
def registration_page(campaign_id):
    with get_db() as con:
        row = con.execute(
            "SELECT id FROM campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()

    if not row:
        abort(404)

    return render_template(
        "register.html",
        campaign_id=campaign_id
    )


# ---------------- REGISTRATION API ----------------

@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}

    phone = str(data.get("phone", "")).strip()
    operator = str(data.get("operator", "")).strip()
    campaign_id = str(data.get("campaign_id", "")).strip()
    consent = data.get("consent") is True

    if not re.fullmatch(r"[6-9]\d{9}", phone):
        return jsonify(error="Invalid mobile number"), 400

    if operator not in OPERATORS:
        return jsonify(error="Invalid operator"), 400

    if not consent:
        return jsonify(error="Consent required"), 400

    with get_db() as con:
        campaign = con.execute(
            "SELECT id FROM campaigns WHERE id=?",
            (campaign_id,)
        ).fetchone()

        if not campaign:
            return jsonify(error="Invalid campaign"), 404

        try:
            cur = con.execute("""
                INSERT INTO registrations
                (campaign_id, phone, operator, status, created_at)
                VALUES (?, ?, ?, 'Pending', ?)
            """, (
                campaign_id,
                phone,
                operator,
                timestamp()
            ))

            reg_id = cur.lastrowid

        except sqlite3.IntegrityError:
            return jsonify(
                error="This mobile number is already registered."
            ), 409

    notify_admin(
        "🪔 NEW GIVEAWAY APPLICATION\n\n"
        f"Registration ID: {reg_id}\n"
        f"Mobile: {phone}\n"
        f"Operator: {operator}\n"
        "Status: Pending\n\n"
        f"Approve: /approve {reg_id}\n"
        f"Recharge Done: /done {reg_id}\n"
        f"Reject: /reject {reg_id}"
    )

    return jsonify(
        success=True,
        registration_id=reg_id,
        message="Application submitted successfully."
    )


# ---------------- ADMIN STATUS API ----------------

@app.get("/api/status/<int:reg_id>")
def application_status(reg_id):
    row = get_registration(reg_id)

    if not row:
        return jsonify(error="Application not found"), 404

    return jsonify(
        registration_id=row["id"],
        status=row["status"]
    )


# ---------------- HEALTH CHECK ----------------

@app.get("/health")
def health():
    return jsonify(
        status="running",
        database="connected"
    )


# ---------------- START BOT ----------------

def run_bot():
    logger.info("Telegram bot starting")

    bot.infinity_polling(
        skip_pending=True,
        timeout=30,
        long_polling_timeout=30
    )


if __name__ == "__main__":
    threading.Thread(
        target=run_bot,
        daemon=True
    ).start()

    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000"))
    )
