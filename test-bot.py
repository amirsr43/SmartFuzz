import os
import re
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import paho.mqtt.client as mqtt

# === MQTT CONFIG ===
BROKER = "192.168.2.254"
PORT = 1884
TOPIC_DATA = "jemuran/data"
TOPIC_CONTROL = "jemuran/control"

# === Global Data ===
latest_data = {"suhu": "-", "ldr": "-", "jam": "-", "tanggal": "-", "hujan": "0"}
last_hujan_status = "0"
user_chat_id = None

# === Load Telegram Token ===
load_dotenv()

# === Fuzzy Logic Setup ===
cahaya = ctrl.Antecedent(np.arange(0, 4096, 1), 'cahaya')
jam = ctrl.Antecedent(np.arange(0, 24, 1), 'jam')
rekomendasi = ctrl.Consequent(np.arange(0, 101, 1), 'rekomendasi')

cahaya['gelap'] = fuzz.trimf(cahaya.universe, [3000, 4095, 4095])
cahaya['sedang'] = fuzz.trimf(cahaya.universe, [2000, 3000, 3500])
cahaya['terang'] = fuzz.trimf(cahaya.universe, [0, 1000, 2000])

jam['pagi'] = fuzz.trimf(jam.universe, [5, 8, 11])
jam['siang'] = fuzz.trimf(jam.universe, [10, 13, 16])
jam['sore'] = fuzz.trimf(jam.universe, [15, 18, 20])

rekomendasi['tidak'] = fuzz.trimf(rekomendasi.universe, [0, 0, 40])
rekomendasi['mungkin'] = fuzz.trimf(rekomendasi.universe, [30, 50, 70])
rekomendasi['ya'] = fuzz.trimf(rekomendasi.universe, [60, 80, 100])

rule1 = ctrl.Rule(cahaya['terang'] & jam['siang'], rekomendasi['ya'])
rule2 = ctrl.Rule(cahaya['sedang'] & jam['pagi'], rekomendasi['mungkin'])
rule3 = ctrl.Rule(cahaya['sedang'] & jam['sore'], rekomendasi['mungkin'])
rule4 = ctrl.Rule(cahaya['gelap'], rekomendasi['tidak'])

rekom_ctrl = ctrl.ControlSystem([rule1, rule2, rule3, rule4])
rekom_simulasi = ctrl.ControlSystemSimulation(rekom_ctrl)

# === MQTT Callbacks ===
def on_connect(client, userdata, flags, rc):
    print("✅ Terhubung ke MQTT Broker!")
    client.subscribe(TOPIC_DATA)

def on_message(client, userdata, msg):
    global last_hujan_status, user_chat_id, telegram_bot
    if msg.topic == TOPIC_DATA:
        try:
            payload = msg.payload.decode()
            print("📡 Payload dari ESP32:\n", payload)

            suhu_match = re.search(r"suhu:([\d.]+)", payload)
            ldr_match = re.search(r"cahaya_analog:(\d+)", payload)
            waktu_match = re.search(r"waktu:(\d{2}):(\d{2}):\d{2}\s+(\d{2})/(\d{2})/(\d{4})", payload)
            hujan_match = re.search(r"hujan:([^\s,]+)", payload)

            if not (suhu_match and ldr_match and waktu_match and hujan_match):
                print("⚠️ Data tidak lengkap:", payload)
                return

            latest_data["suhu"] = suhu_match.group(1)
            latest_data["ldr"] = ldr_match.group(1)
            latest_data["jam"] = f"{waktu_match.group(1)}:{waktu_match.group(2)}"
            latest_data["tanggal"] = f"{waktu_match.group(3)}/{waktu_match.group(4)}/{waktu_match.group(5)}"

            # Cek hujan
            rain_raw = hujan_match.group(1).lower()
            if "lebat" in rain_raw:
                latest_data["hujan"] = "3"
                rain_label = "🌧️ Hujan Lebat!"
            elif "sedang" in rain_raw:
                latest_data["hujan"] = "2"
                rain_label = "🌦️ Hujan Sedang."
            elif "gerimis" in rain_raw:
                latest_data["hujan"] = "1"
                rain_label = "🌂 Gerimis turun."
            else:
                latest_data["hujan"] = "0"
                rain_label = "☀️ Tidak hujan."

            print("✅ Data berhasil di-parse:", latest_data)

            jam_int = int(waktu_match.group(1))
            ldr = int(latest_data["ldr"])
            suhu = float(latest_data["suhu"])

            # Notifikasi jika status hujan berubah
            if last_hujan_status != latest_data["hujan"] and latest_data["hujan"] != "0":
                if user_chat_id and telegram_bot:
                    telegram_bot.send_message(chat_id=user_chat_id, text=f"{rain_label} Segera tutup jemuran!")


            # Prediksi mendung
            if latest_data["hujan"] == "0" and ldr > 3500 and suhu < 28 and (jam_int >= 15 or jam_int <= 6):
                if user_chat_id and telegram_bot:
                    telegram_bot.send_message(chat_id=user_chat_id, text="⛈️ Cuaca mendung. Kemungkinan akan hujan.")


            last_hujan_status = latest_data["hujan"]

        except Exception as e:
            print("❌ Error parsing MQTT payload:", e)

# === MQTT Setup ===
mqtt_client = mqtt.Client(userdata=None)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, PORT, 60)
mqtt_client.loop_start()

# === Telegram Bot Commands ===
def start(update: Update, context: CallbackContext):
    global user_chat_id, telegram_bot
    user_chat_id = update.effective_chat.id
    telegram_bot = context.bot
    context.bot.send_message(chat_id=user_chat_id, text=
        "👋 Halo! Aku bot smart jemuran 🌞\n"
        "Perintah:\n"
        "/info - Cek kondisi jemuran\n"
        "/buka - Buka jemuran\n"
        "/tutup - Tutup jemuran")

def info(update: Update, context: CallbackContext):
    try:
        ldr = int(latest_data["ldr"])
        jam_str = latest_data["jam"]
        jam_int = int(jam_str.split(":")[0])
        suhu = latest_data["suhu"]
        hujan = latest_data["hujan"]
        tanggal = latest_data["tanggal"]
    except:
        update.message.reply_text("❌ Belum ada data valid dari jemuran.")
        return

    # Label cahaya
    if ldr >= 3500:
        cahaya_label = "Gelap"
    elif ldr >= 2000:
        cahaya_label = "Sedang"
    else:
        cahaya_label = "Terang"

    # Label hujan dan rekomendasi override
    if hujan == "3":
        hujan_text = "🌧️ Hujan Lebat!"
        rekom = "❌ Tidak disarankan menjemur sekarang karena hujan lebat."
    elif hujan == "2":
        hujan_text = "🌦️ Hujan Sedang."
        rekom = "❌ Tidak disarankan menjemur sekarang karena hujan sedang."
    elif hujan == "1":
        hujan_text = "🌂 Gerimis."
        rekom = "❌ Tidak disarankan menjemur sekarang karena gerimis."
    else:
        hujan_text = "☀️ Tidak hujan."
        # Fuzzy logic hanya digunakan jika tidak hujan
        rekom_simulasi.input['cahaya'] = ldr
        rekom_simulasi.input['jam'] = jam_int
        rekom_simulasi.compute()
        hasil = rekom_simulasi.output['rekomendasi']

        if hasil >= 70:
            rekom = "✅ Cuaca sangat cocok untuk menjemur."
        elif hasil >= 40:
            rekom = "⚠️ Cuaca mungkin cocok untuk menjemur."
        else:
            rekom = "❌ Tidak disarankan menjemur sekarang."

    update.message.reply_text(
        f"🌡️ Suhu: {suhu}°C\n🔆 Cahaya: {cahaya_label}\n🕒 Waktu: {jam_str} - {tanggal}\n{hujan_text}\n\n{rekom}"
    )



def buka(update: Update, context: CallbackContext):
    mqtt_client.publish(TOPIC_CONTROL, "buka")
    update.message.reply_text("📂 Jemuran dibuka.")

def tutup(update: Update, context: CallbackContext):
    mqtt_client.publish(TOPIC_CONTROL, "tutup")
    update.message.reply_text("📁 Jemuran ditutup.")

def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TOKEN:
        print("❌ TELEGRAM_TOKEN belum diset di .env")
        return

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("info", info))
    dp.add_handler(CommandHandler("buka", buka))
    dp.add_handler(CommandHandler("tutup", tutup))

    updater.start_polling()
    print("🤖 Bot Telegram aktif...")
    updater.idle()

if __name__ == '__main__':
    main()
