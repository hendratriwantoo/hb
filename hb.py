import os
import requests
import time
import urllib3
import threading
import http.server
import socketserver
from datetime import datetime

# menonaktifkan peringatan sertifikat untuk request ke api
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# konfigurasi default
tele_token_default = "8682695455:AAEPyjoF9wioGM1_OhdbeawRdPCKZfUc4a8"
chat_ids_default = "1871805510, 1631662935"
interval_scan = 30  # interval pengecekan dalam detik

# render umumnya tidak memblokir telegram, jadi bisa pakai url asli
base_url_telegram = "https://api.telegram.org" 

class RadarHongbao:
    def __init__(self, token, chat_ids_str, interval):
        self.history_envelope = []
        self.pesan_aktif = {}
        self.is_running = False
        self.token = token
        self.chat_ids = [cid.strip() for cid in chat_ids_str.split(",") if cid.strip()]
        self.interval = interval
        
        self.headers = {
            "user-agent": "okhttp/4.11.0",
            "accept": "application/json",
        }
        self.url_target = "https://newapi.goodnight.io/api/professions/hot_streamer_ranking?use_favor_languages=true&plan_id=3&exclude_pin_streamers=true&country_code=ID&token=2d769006-63ca-4646-8f18-72fa2ba0dffc&device_model=PJJ110&device_system_name=Android&device_system_version=9&app_version=1.339.0&build_number=628&locale=en-US&device_token=1c82ded23024ebd6&code_push_version=2"

    def tambah_log(self, teks):
        timestamp = datetime.now().strftime("%H:%M:%S")
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
                    self.tambah_log(f"error telegram {chat_id}: {res.text}")
                    return None
            except requests.exceptions.Timeout:
                self.tambah_log(f"timeout telegram ke {chat_id}, mencoba ulang ({percobaan + 1}/{maks_percobaan})...")
                time.sleep(1)
            except Exception as e:
                self.tambah_log(f"gagal kirim telegram ke {chat_id}: {e}")
                return None
        
        self.tambah_log(f"gagal kirim telegram ke {chat_id} setelah {maks_percobaan} percobaan")
        return None

    def hapus_tele(self, chat_id, message_id, maks_percobaan=2):
        url = f"{base_url_telegram}/bot{self.token}/deleteMessage"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        
        for percobaan in range(maks_percobaan):
            try:
                requests.post(url, json=payload, timeout=10)
                break
            except requests.exceptions.Timeout:
                time.sleep(1)
            except Exception:
                break

    def test_koneksi(self):
        self.tambah_log("mengirim pesan uji coba ke telegram...")
        msg = (
            f"<b>test radar hongbao</b>\n\n"
        )
        for chat_id in self.chat_ids:
            msg_id = self.kirim_tele(msg, chat_id)
            if msg_id:
                self.tambah_log(f"pesan tes berhasil dikirim ke {chat_id}")
            else:
                self.tambah_log(f"gagal mengirim pesan tes ke {chat_id}")

    def mulai(self):
        self.is_running = True
        self.tambah_log("radar mulai memantau.")
        
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
                                    
                                    msg = (
                                        f"🧧 <b>hongbao baru rilis</b>\n\n"
                                        f" <b>nama:</b> <code>{aman_nama}</code>\n"
                                        f" <b>env:</b> <code>{aman_env}</code>\n"
                                        f" <b>history id:</b> <code>{rid}</code>\n"
                                        f" <b>views:</b> <code>{penonton} orang</code>\n"
                                        f" <b>waktu:</b> <code>{datetime.now().strftime('%H:%M:%S')}</code>\n"
                                    )

                                    self.tambah_log(f"menemukan hongbao baru: {env_name}")
                                    
                                    id_pesan_terkirim = []
                                    for chat_id in self.chat_ids:
                                        msg_id = self.kirim_tele(msg, chat_id)
                                        if msg_id:
                                            id_pesan_terkirim.append({"chat_id": chat_id, "message_id": msg_id})

                                    self.pesan_aktif[env_name] = id_pesan_terkirim
                                    self.history_envelope.append(env_name)
                                    
                                    if len(self.history_envelope) > 200:
                                        self.history_envelope.pop(0)

                    hongbao_kedaluwarsa = []
                    for env_aktif, daftar_pesan in list(self.pesan_aktif.items()):
                        if env_aktif not in hongbao_saat_ini:
                            self.tambah_log(f"hongbao {env_aktif} selesai, menghapus pesan telegram")
                            for p in daftar_pesan:
                                self.hapus_tele(p["chat_id"], p["message_id"])
                            hongbao_kedaluwarsa.append(env_aktif)

                    for item in hongbao_kedaluwarsa:
                        if item in self.pesan_aktif:
                            del self.pesan_aktif[item]

                elif res.status_code == 401:
                    self.tambah_log("token api kedaluwarsa")
                    break
                else:
                    self.tambah_log(f"masalah server: {res.status_code}")

            except Exception as e:
                self.tambah_log(f"kesalahan sistem: {e}")
            
            for _ in range(self.interval):
                if not self.is_running:
                    break
                time.sleep(1)

def jalankan_server_dummy():
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass 

    # menggunakan port dinamis dari environment variable render
    port = int(os.environ.get("PORT", 10000))
    try:
        with socketserver.TCPServer(("0.0.0.0", port), Handler) as httpd:
            print(f"server port {port} aktif untuk health check render", flush=True)
            httpd.serve_forever()
    except Exception as e:
        print(f"gagal memulai server dummy: {e}", flush=True)

if __name__ == "__main__":
    threading.Thread(target=jalankan_server_dummy, daemon=True).start()
    
    radar = RadarHongbao(tele_token_default, chat_ids_default, interval_scan)
    
    radar.test_koneksi()
    
    try:
        radar.mulai()
    except KeyboardInterrupt:
        radar.is_running = False
        print("\nradar dihentikan.", flush=True)
