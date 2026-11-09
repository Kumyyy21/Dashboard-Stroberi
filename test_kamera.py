"""
=============================================================================
 Sistem Deteksi Kematangan Stroberi - Pengujian Webcam Real-Time
 Model  : YOLO11n (best.pt)
 Kelas  : matang, mentah, busuk
 Kontrol: Tekan 'q' untuk keluar
=============================================================================
"""

import cv2
import time
from ultralytics import YOLO

# ── Konfigurasi ──────────────────────────────────────────────────────────────
MODEL_PATH = "best.pt"              # Path ke bobot model YOLO
CAMERA_INDEX = 0                    # Indeks webcam (0 = default)
CONFIDENCE_THRESHOLD = 0.5          # Ambang batas confidence minimum
WINDOW_NAME = "Deteksi Stroberi - YOLO11n"

# Warna BGR per kelas (untuk bounding box & label)
WARNA_KELAS = {
    "matang": (0, 200, 0),       # Hijau
    "mentah": (0, 220, 255),     # Kuning/Oranye
    "busuk":  (0, 0, 220),       # Merah
}

# ── Muat Model ──────────────────────────────────────────────────────────────
print("[INFO] Memuat model YOLO dari:", MODEL_PATH)
model = YOLO(MODEL_PATH)
class_names = model.names  # Mapping indeks -> nama kelas
print(f"[INFO] Model berhasil dimuat. Kelas terdeteksi: {class_names}")

# ── Buka Webcam ──────────────────────────────────────────────────────────────
print(f"[INFO] Membuka webcam (index={CAMERA_INDEX})...")
cap = cv2.VideoCapture(CAMERA_INDEX)

if not cap.isOpened():
    print("[ERROR] Gagal membuka webcam! Periksa koneksi kamera.")
    exit(1)

# Atur resolusi webcam (opsional, sesuaikan dengan kamera)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
print(f"[INFO] Webcam aktif — Resolusi: {actual_w}x{actual_h}")
print("[INFO] Tekan 'q' untuk keluar.\n")

# ── Variabel FPS ─────────────────────────────────────────────────────────────
prev_time = time.time()
fps = 0.0

# ── Loop Utama ───────────────────────────────────────────────────────────────
try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("[WARNING] Gagal membaca frame dari webcam.")
            break

        # -- Hitung FPS --
        curr_time = time.time()
        fps = 1.0 / (curr_time - prev_time) if (curr_time - prev_time) > 0 else 0
        prev_time = curr_time

        # -- Jalankan Inferensi YOLO --
        results = model.predict(
            source=frame,
            conf=CONFIDENCE_THRESHOLD,
            verbose=False,     # Matikan log per-frame agar terminal bersih
        )

        # -- Hitung deteksi per kelas --
        count = {"matang": 0, "mentah": 0, "busuk": 0}

        # -- Proses hasil deteksi --
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            for box in boxes:
                # Ambil koordinat, confidence, dan kelas
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                cls_id = int(box.cls[0])
                cls_name = class_names.get(cls_id, "unknown")

                # Hitung jumlah per kelas
                if cls_name in count:
                    count[cls_name] += 1

                # Ambil warna sesuai kelas
                color = WARNA_KELAS.get(cls_name, (200, 200, 200))

                # Gambar bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                # Label: nama kelas + confidence
                label = f"{cls_name} {conf:.0%}"
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                label_w, label_h = label_size

                # Background label
                cv2.rectangle(frame, (x1, y1 - label_h - 8), (x1 + label_w + 4, y1), color, -1)
                cv2.putText(frame, label, (x1 + 2, y1 - 4),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # -- Tampilkan Info Overlay (FPS & jumlah deteksi) --
        # Background semi-transparan untuk info panel
        overlay = frame.copy()
        cv2.rectangle(overlay, (5, 5), (250, 110), (40, 40, 40), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)

        # Teks info
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
        y_offset = 55
        for kelas, jumlah in count.items():
            warna = WARNA_KELAS[kelas]
            cv2.putText(frame, f"{kelas}: {jumlah}", (10, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, warna, 2)
            y_offset += 25

        # -- Tampilkan Frame --
        cv2.imshow(WINDOW_NAME, frame)

        # -- Cek tombol keluar --
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("\n[INFO] Keluar dari deteksi.")
            break

except KeyboardInterrupt:
    print("\n[INFO] Dihentikan oleh pengguna (Ctrl+C).")

finally:
    cap.release()
    cv2.destroyAllWindows()
    print("[INFO] Webcam dan jendela ditutup. Selesai.")

