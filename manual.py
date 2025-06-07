import requests

def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload)
        print(f"[DEBUG] Kirim pesan ke Telegram: {message}")
        print(f"[DEBUG] Response Telegram: {response.status_code} {response.text}")
        if response.status_code == 200:
            print("[✅] Notifikasi Telegram terkirim")
        else:
            print(f"[❌] Gagal kirim notifikasi: {response.text}")
    except Exception as e:
        print(f"[❌] Error kirim notifikasi: {e}")

# Panggil fungsi test notifikasi manual
send_telegram_message(
    "7977346644:AAFuNX7T8RAkR1Um-2YCAxWJ1tNzi_N-vPs",
    "5037016522",
    "🚀 Test notifikasi manual dari sistem jemuran, apakah masuk?"
)
