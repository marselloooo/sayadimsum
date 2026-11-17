# Saya Dimsum — Website + MQTT + ESP32 Wokwi

Project ini mengikuti alur PPT: Order Input → In Progress → tombol Done → panggilan ESP32 melalui MQTT → Daily Sales.

## 1. Jalankan website

Disarankan Python 3.10 atau lebih baru.

```bash
cd saya_dimsum_iot
python -m venv .venv
```

Aktifkan virtual environment:

Windows:
```bash
.venv\Scripts\activate
```

Mac/Linux:
```bash
source .venv/bin/activate
```

Install dan jalankan:

```bash
pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5000`.

Database SQLite `saya_dimsum.db` dibuat otomatis di folder project.

## 2. Jalankan simulasi Wokwi

1. Buka https://wokwi.com/projects/new/esp32
2. Salin isi `wokwi/sketch.ino` ke editor `sketch.ino`.
3. Atur diagram rangkaian sesuai `wokwi/diagram.json` (ESP32 GPIO18 ke buzzer +, GND ke buzzer -).
4. Tambahkan library `PubSubClient` melalui `wokwi/libraries.txt` jika belum terpasang.
5. Mulai simulasi dan buka Serial Monitor. Tunggu sampai ESP32 terhubung ke WiFi dan MQTT.

Jika membuat project Wokwi dari awal, gunakan komponen ESP32 DevKit V1 dan buzzer. Pastikan pin positif buzzer terhubung ke GPIO18 dan pin negatif ke GND.

## 3. Hubungkan website dengan Wokwi

Website (Flask) dan ESP32 harus memakai broker serta topic yang sama.

Default:
- Broker: `broker.hivemq.com`
- Port: `1883`
- Topic: `saya-dimsum/group3/queue/call`

Topic ini bersifat publik untuk demo. Untuk mengurangi kemungkinan pesan tertukar, ganti topic dengan nama unik milik kelompok, misalnya `saya-dimsum/kelompok3/namakalian/queue/call`. Ganti di DUA tempat:
- `MQTT_TOPIC` di `app.py`
- `MQTT_TOPIC` di `wokwi/sketch.ino`

Jalankan website di komputer dan simulasi Wokwi secara bersamaan. Ketika seller menekan tombol **Done**, backend mengirim payload seperti:

```json
{"nomor": 5}
```

ESP32 menerima pesan tersebut, menampilkan `Memanggil antrian 5` di Serial Monitor, lalu membunyikan buzzer.

## 4. Catatan penting tentang koneksi

- Wokwi memakai WiFi simulasi `Wokwi-GUEST`.
- Website perlu koneksi internet agar dapat mengakses broker MQTT publik.
- Simulasi Wokwi juga perlu dapat mengakses broker publik.
- Jangan gunakan topic demo ini untuk data sensitif atau penggunaan produksi. Broker publik tidak memakai autentikasi pada konfigurasi contoh ini.
- Website tetap menyimpan pesanan selesai meskipun publish MQTT gagal. Periksa pesan notifikasi website dan Serial Monitor.
- Untuk deployment sungguhan, gunakan broker MQTT dengan autentikasi/TLS dan topic khusus.

## 5. Aturan stok dan harga

Harga contoh pada website adalah Rp15.000 per porsi untuk kedua menu. Ubah `MENU_PRICES` di `app.py` jika harga kelompok berbeda. Stok tersisa dihitung dari stok awal dikurangi seluruh porsi pesanan hari itu (pesanan berjalan dan selesai).
