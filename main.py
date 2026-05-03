import os
import requests
import time
import urllib3
import threading
import http.server
import socketserver
# Tambahkan timezone dan timedelta dari datetime
from datetime import datetime, timezone, timedelta

# menonaktifkan peringatan sertifikat untuk request ke api
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- KONFIGURASI DARI VARIABLES (ENV) ---
# Kode sekarang akan mencoba membaca dari panel "Variables" di hosting Anda (Railway/Render)
# Jika tidak ditemukan di Variables, baru menggunakan nilai default di bawah ini.
tele_token_env = os.environ.get("TELE_TOKEN", "8682695455:AAEPyjoF9wioGM1_OhdbeawRdPCKZfUc4a8")
chat_ids_env = os.environ.get("CHAT_IDS", "1871805510, 1631662935")
interval_scan = int(os.environ.get("INTERVAL_SCAN", 30))

base_url_telegram = "https://api.telegram.org" 

# --- PENGATURAN ZONA WAKTU ---
# Mengatur zona waktu ke WIB (UTC+7). 
TZ_WIB = timezone(timedelta(hours=7))

class RadarHongbao:
    def __init__(self, token, chat_ids_str, interval):
        self.history_envelope = []
        self.pesan_aktif = {}
        self.is_running = False
        self.token = token
        # Memisahkan ID chat berdasarkan koma dan membersihkan spasi
        self.chat_ids = [cid.strip() for cid in chat_ids_str.split(",") if cid.strip()]
        self.interval = interval
        
        self.headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
        }
        # pastikan token api di bawah ini masih aktif
        self.url_target = "https://newapi.goodnight.io/api/professions/hot_streamer_ranking?use_favor_languages=true&plan_id=3&exclude_pin_streamers=true&country_code=ID&token=3850be5d-9b21-4358-9a74-4c2e83fad98d&device_model=SM-N976N&device_system_name=Android&device_system_version=9&app_version=1.339.0&build_number=628&locale=en-US&device_token=9f26fcb650475342&code_push_version=4"

    def tambah_log(self, teks):
        # Menggunakan TZ_WIB agar log di server juga sesuai waktu Indonesia
        timestamp = datetime.now(TZ_WIB).strftime("%H:%M:%S")
        print(f"[{timestamp}] {teks}", flush=True)

    def kirim_tele(self, pesan, chat_id, maks_percobaan=2):
        url = f"{base_url_telegram}/bot{self.token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": pesan,
            "parse_mode": "HTML",
        }
        
        for percobaan in range(maks_percobaan):
            try:
                res = requests.post(url, json=payload, timeout=10)
                if res.status_code == 200:
                    return res.json().get("result", {}).get("message_id")
                else:
                    self.tambah_log(f"Error Telegram {chat_id}: {res.text}")
                    return None
            except requests.exceptions.Timeout:
                self.tambah_log(f"Timeout Telegram ke {chat_id}, mencoba ulang ({percobaan + 1}/{maks_percobaan})...")
                time.sleep(1)
            except Exception as e:
                self.tambah_log(f"Gagal kirim Telegram ke {chat_id}: {e}")
                return None
        return None

    def edit_tele(self, chat_id, message_id, pesan_baru, maks_percobaan=2):
        url = f"{base_url_telegram}/bot{self.token}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": pesan_baru,
            "parse_mode": "HTML",
        }
        
        for percobaan in range(maks_percobaan):
            try:
                res = requests.post(url, json=payload, timeout=10)
                if res.status_code == 200:
                    return True
                break
            except Exception:
                time.sleep(1)
        return False

    def test_koneksi(self):
        self.tambah_log(f"Mengirim pesan uji ke {len(self.chat_ids)} chat ID...")
        msg = "<b>Test Radar Hongbao (Multi-ID Aktif)</b>"
        for chat_id in self.chat_ids:
            msg_id = self.kirim_tele(msg, chat_id)
            if msg_id:
                self.tambah_log(f"Pesan tes berhasil dikirim ke {chat_id}")
            else:
                self.tambah_log(f"Gagal mengirim pesan tes ke {chat_id}")

    def mulai(self):
        self.is_running = True
        self.tambah_log(f"Radar mulai memantau untuk {len(self.chat_ids)} chat ID.")
        
        while self.is_running:
            try:
                res = requests.get(self.url_target, headers=self.headers, timeout=15, verify=False)
                
                if res.status_code == 200:
                    data = res.json()
                    users = data.get("users", data.get("data", {}).get("users", []))
                    
                    hongbao_saat_ini = []

                    for streamer in users:
                        status_hongbao = streamer.get("has_red_envelope")
                        if status_hongbao in [True, 1, "true", "True"]:
                            nama = streamer.get("name")
                            rid = streamer.get("peep_room_history_id")
                            env_name = streamer.get("peep_roomname")
                            penonton = streamer.get("room_concurrent_users", 0)

                            if env_name:
                                hongbao_saat_ini.append(env_name)

                                if env_name not in self.history_envelope:
                                    aman_nama = str(nama).replace("<", "&lt;").replace(">", "&gt;")
                                    aman_env = str(env_name).replace("<", "&lt;").replace(">", "&gt;")
                                    
                                    waktu_sekarang = datetime.now(TZ_WIB).strftime('%H:%M:%S WIB')
                                    
                                    msg = (
                                        f"🧧 <b>Hongbao Baru Rilis</b>\n\n"
                                        f" <b>Nama:</b> <code>{aman_nama}</code>\n"
                                        f" <b>Env:</b> <code>{aman_env}</code>\n"
                                        f" <b>History ID:</b> <code>{rid}</code>\n"
                                        f" <b>Views:</b> <code>{penonton} orang</code>\n"
                                        f" <b>Waktu:</b> <code>{waktu_sekarang}</code>\n"
                                    )

                                    self.tambah_log(f"Menemukan Hongbao baru: {env_name}")
                                    
                                    id_pesan_terkirim = []
                                    for chat_id in self.chat_ids:
                                        msg_id = self.kirim_tele(msg, chat_id)
                                        if msg_id:
                                            id_pesan_terkirim.append({"chat_id": chat_id, "message_id": msg_id})

                                    if id_pesan_terkirim:
                                        self.pesan_aktif[env_name] = {
                                            "pesan": id_pesan_terkirim,
                                            "nama": aman_nama,
                                            "waktu": waktu_sekarang
                                        }
                                    
                                    self.history_envelope.append(env_name)
                                    if len(self.history_envelope) > 200:
                                        self.history_envelope.pop(0)

                    hongbao_kedaluwarsa = []
                    for env_aktif, data_hb in list(self.pesan_aktif.items()):
                        if env_aktif not in hongbao_saat_ini:
                            self.tambah_log(f"Hongbao {env_aktif} selesai, mengubah status pesan")
                            
                            msg_selesai = (
                                f"<s>🧧 <b>Hongbao Selesai</b>\n\n"
                                f" <b>Nama:</b> {data_hb['nama']}\n"
                                f" <b>Env:</b> {env_aktif}\n"
                                f" <b>Waktu Rilis:</b> {data_hb['waktu']}</s>"
                            )
                            
                            for p in data_hb["pesan"]:
                                self.edit_tele(p["chat_id"], p["message_id"], msg_selesai)
                            hongbao_kedaluwarsa.append(env_aktif)

                    for item in hongbao_kedaluwarsa:
                        if item in self.pesan_aktif:
                            del self.pesan_aktif[item]
                        # perbaikan ditambahkan di sini: menghapus nama dari history jika sudah selesai
                        if item in self.history_envelope:
                            self.history_envelope.remove(item)

                elif res.status_code == 401:
                    self.tambah_log("Token API Goodnight kedaluwarsa, silakan perbarui token")
                    break

            except Exception as e:
                self.tambah_log(f"Kesalahan sistem: {e}")
            
            time.sleep(self.interval)

def jalankan_server_dummy():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass 

    port = int(os.environ.get("PORT", 10000))
    try:
        with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
            print(f"Server health check aktif di port {port}", flush=True)
            httpd.serve_forever()
    except Exception as e:
        print(f"Gagal memulai server dummy: {e}", flush=True)

if __name__ == "__main__":
    threading.Thread(target=jalankan_server_dummy, daemon=True).start()
    # Menggunakan variabel yang diambil dari Environment atau Default
    radar = RadarHongbao(tele_token_env, chat_ids_env, interval_scan)
    radar.test_koneksi()
    
    try:
        radar.mulai()
    except KeyboardInterrupt:
        radar.is_running = False
        print("\nRadar dihentikan.", flush=True)
