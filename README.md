# 🍓 Sistem Otomasi Sortir Kematangan Stroberi

Sistem sortir kematangan buah stroberi berbasis Computer Vision menggunakan arsitektur **YOLO11n** dan integrasi mikrokontroler **ESP32**.

## 📌 Fitur Utama
- **Deteksi Real-Time**: Klasifikasi 3 kondisi stroberi: `matang`, `mentah`, dan `busuk`.
- **Web Dashboard**: Antarmuka interaktif berbasis Flask untuk pemantauan kamera, statistik real-time, grafik deteksi, dan log riwayat.
- **Komunikasi Serial ESP32**: Pengiriman data hasil klasifikasi via serial USB (`pyserial`) untuk menggerakkan mekanisme servo sortir.
- **Akurasi Model**: Model YOLO11 Nano dilatih 100 epoch dengan mAP50 ~96.6%.

## 🚀 Cara Menjalankan
1. Pastikan dependensi terpasang:
   ```bash
   py -m pip install ultralytics opencv-python flask pyserial
   ```
2. Jalankan dashboard:
   ```bash
   py app.py
   ```
3. Buka browser: `http://localhost:5000`

