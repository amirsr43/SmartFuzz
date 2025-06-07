import paho.mqtt.client as mqtt
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import os
from dotenv import load_dotenv

# === MQTT CONFIG ===
BROKER = "192.168.244.254"
PORT = 1884
TOPIC_DATA = "jemuran/data"
TOPIC_CONTROL = "jemuran/control"

# Simpan data dari ESP32
latest_data = {"suhu": "-", "ldr": "-", "jam": "-"}

load_dotenv()

# === MQTT Callback ===
def on_connect(client, userdata, flags, rc):
    print("Terhubung ke MQTT Broker!")
    client.subscribe(TOPIC_DATA)

def on_message(client, userdata, msg):
    if msg.topic == TOPIC_DATA:
        try:
            payload = msg.payload.decode()
            print("Data dari ESP32:", payload)
            parts = dict(item.split(":") for item in payload.split(","))
            latest_data.update(parts)
        except Exception as e:
            print("Format data salah:", e)

# === MQTT Client ===
mqtt_client = mqtt.Client()
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.connect(BROKER, PORT, 60)
mqtt_client.loop_start()

# === Fuzzy Logic Setup ===
cahaya = ctrl.Antecedent(np.arange(0, 1024, 1), 'cahaya')
jam = ctrl.Antecedent(np.arange(0, 24, 1), 'jam')
rekomendasi = ctrl.Consequent(np.arange(0, 101, 1), 'rekomendasi')

cahaya['gelap'] = fuzz.trimf(cahaya.universe, [0, 0, 300])
cahaya['sedang'] = fuzz.trimf(cahaya.universe, [200, 500, 800])
cahaya['terang'] = fuzz.trimf(cahaya.universe, [600, 1023, 1023])

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

# === Telegram Bot Commands ===
def info(update: Update, context: CallbackContext):
    try:
        ldr = int(latest_data["ldr"])
        j = int(latest_data["jam"])
        s = latest_data["suhu"]
    except:
        update.message.reply_text("❌ Belum ada data valid dari jemuran.")
        return

    rekom_simulasi.input['cahaya'] = ldr
    rekom_simulasi.input['jam'] = j
    rekom_simulasi.compute()
    hasil = rekom_simulasi.output['rekomendasi']

    if hasil >= 70:
        teks = "✅ Cuaca sangat cocok untuk menjemur."
    elif hasil >= 40:
        teks = "⚠️ Cuaca mungkin cocok untuk menjemur."
    else:
        teks = "❌ Tidak disarankan menjemur sekarang."

    update.message.reply_text(
        f"🌡️ Suhu: {s}°C\n🔆 LDR: {ldr}\n🕒 Jam: {j}\n\n{teks}"
    )

def buka(update: Update, context: CallbackContext):
    mqtt_client.publish(TOPIC_CONTROL, "BUKA")
    update.message.reply_text("📂 Jemuran dibuka.")

def tutup(update: Update, context: CallbackContext):
    mqtt_client.publish(TOPIC_CONTROL, "TUTUP")
    update.message.reply_text("📁 Jemuran ditutup.")

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        "Halo! Aku adalah bot smart jemuran 🌞\n"
        "Perintah yang tersedia:\n"
        "/info - Info kondisi jemuran \n"
        "/buka - Buka jemuran\n"
        "/tutup - Tutup jemuran"
    )

# === Setup Telegram Bot ===
def main():
    TOKEN = os.getenv("TELEGRAM_TOKEN")  # Ambil token dari env

    if not TOKEN:
        print("❌ TOKEN tidak ditemukan. Pastikan .env sudah benar.")
        return

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("info", info))
    dp.add_handler(CommandHandler("buka", buka))
    dp.add_handler(CommandHandler("tutup", tutup))

    updater.start_polling()
    print("Bot Telegram aktif...")
    updater.idle()

if __name__ == '__main__':
    main()
