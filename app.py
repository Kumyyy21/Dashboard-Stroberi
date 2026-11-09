"""
=============================================================================
 Sistem Deteksi Kematangan Stroberi - Web Dashboard
 Backend Flask + YOLO11n + Webcam Streaming + Serial ESP32
 
 Jalankan: py app.py
 Buka   : http://localhost:5000
=============================================================================
"""

import cv2
import time
import threading
from datetime import datetime

from flask import Flask, render_template, Response, jsonify, request
from ultralytics import YOLO

# ── Coba impor pyserial (opsional, untuk ESP32) ─────────────────────────────
try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False
    print("[WARNING] pyserial belum terinstal. Fitur ESP32 tidak aktif.")
    print("          Install dengan: py -m pip install pyserial\n")

app = Flask(__name__)


# =============================================================================
# KELAS UTAMA: DetectionSystem
# =============================================================================
class DetectionSystem:
    """Mengelola kamera, inferensi YOLO, statistik, dan komunikasi serial."""

    COLORS_BGR = {
        "matang": (0, 200, 0),      # Hijau
        "mentah": (0, 220, 255),     # Kuning
        "busuk":  (0, 0, 220),       # Merah
    }

    def __init__(self, model_path="best.pt"):
        # ── Model ────────────────────────────────────────────────────────
        print("[INFO] Memuat model YOLO dari:", model_path)
        self.model = YOLO(model_path)
        self.class_names = self.model.names
        print(f"[INFO] Model dimuat. Kelas: {self.class_names}")

        # ── Kamera ───────────────────────────────────────────────────────
        self.camera = None
        self.is_running = False
        self.camera_index = 0
        self.current_frame = None
        self.frame_lock = threading.Lock()

        # ── Pengaturan ───────────────────────────────────────────────────
        self.confidence = 0.75
        self.max_box_ratio = 0.25       # Maks 25% dari luas frame (stroberi itu kecil)
        self.color_filter = True        # Aktifkan filter warna stroberi
        self.imgsz = 320                # Resolusi inferensi (lebih kecil = lebih cepat)
        self.skip_frames = 2            # Deteksi setiap N frame (1=semua, 2=selang-seling)

        # ── Statistik ────────────────────────────────────────────────────
        self.fps = 0.0
        self.frame_count = 0
        self.session_start = None
        self.session_counts = {"matang": 0, "mentah": 0, "busuk": 0}
        self.current_counts = {"matang": 0, "mentah": 0, "busuk": 0}
        self.detection_log = []       # Riwayat deteksi terbaru
        self.chart_history = []       # Data untuk chart time-series

        # ── Serial / ESP32 ───────────────────────────────────────────────
        self.serial_conn = None
        self.serial_log = []
        self.auto_send_serial = True  # Otomatis kirim hasil ke ESP32

    # ─────────────────────────────────────────────────────────────────────
    # FILTER: Validasi apakah objek benar-benar stroberi
    # ─────────────────────────────────────────────────────────────────────
    def _is_strawberry(self, frame, x1, y1, x2, y2):
        """
        Filter ketat: hanya loloskan objek yang benar-benar stroberi.
        Stroberi di webcam berukuran kecil-sedang dan berwarna sangat jenuh.
        """
        frame_h, frame_w = frame.shape[:2]
        box_w = x2 - x1
        box_h = y2 - y1
        box_area = box_w * box_h
        frame_area = frame_w * frame_h

        # ── Filter 1: Ukuran relatif — maks 8% area frame ───────────
        if box_area / frame_area > 0.08:
            return False

        # ── Filter 2: Ukuran absolut terlalu besar (bukan stroberi) ──
        if box_w > 180 or box_h > 180:
            return False

        # ── Filter 3: Terlalu kecil (noise) ──────────────────────────
        if box_w < 20 or box_h < 20:
            return False

        # ── Filter 4: Warna — stroberi HARUS berwarna jenuh ──────────
        crop = frame[max(0, y1):min(frame_h, y2), max(0, x1):min(frame_w, x2)]
        if crop.size == 0:
            return False

        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        total_pixels = hsv.shape[0] * hsv.shape[1]
        if total_pixels == 0:
            return False

        # Cek saturasi rata-rata — kulit manusia ~30-50, stroberi ~80-150+
        avg_saturation = float(hsv[:, :, 1].mean())
        if avg_saturation < 75:
            return False

        # Merah vivid (matang/busuk)
        mask_r1 = cv2.inRange(hsv, (0, 100, 60), (10, 255, 255))
        mask_r2 = cv2.inRange(hsv, (168, 100, 60), (180, 255, 255))
        # Hijau vivid (mentah)
        mask_g = cv2.inRange(hsv, (30, 70, 50), (85, 255, 255))

        strawberry_px = cv2.countNonZero(mask_r1) + cv2.countNonZero(mask_r2) + cv2.countNonZero(mask_g)
        ratio = strawberry_px / total_pixels

        # Minimal 25% piksel harus berwarna stroberi vivid
        return ratio >= 0.25

    # ─────────────────────────────────────────────────────────────────────
    # KAMERA & DETEKSI
    # ─────────────────────────────────────────────────────────────────────
    def start_detection(self):
        """Mulai webcam dan loop deteksi di thread terpisah."""
        if self.is_running:
            return {"status": "already_running", "message": "Deteksi sudah berjalan"}

        self.camera = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        if not self.camera.isOpened():
            # Coba lagi tanpa DirectShow
            self.camera = cv2.VideoCapture(self.camera_index)
        if not self.camera.isOpened():
            return {"status": "error", "message": "Gagal membuka webcam. Periksa koneksi kamera."}

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        # Reset statistik sesi
        self.is_running = True
        self.session_counts = {"matang": 0, "mentah": 0, "busuk": 0}
        self.current_counts = {"matang": 0, "mentah": 0, "busuk": 0}
        self.frame_count = 0
        self.fps = 0.0
        self.session_start = datetime.now()
        self.detection_log = []
        self.chart_history = []

        thread = threading.Thread(target=self._detection_loop, daemon=True)
        thread.start()

        w = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return {"status": "started", "message": f"Deteksi dimulai ({w}x{h})"}

    def stop_detection(self):
        """Hentikan deteksi dan lepas kamera."""
        self.is_running = False
        time.sleep(0.3)
        if self.camera:
            self.camera.release()
            self.camera = None
        with self.frame_lock:
            self.current_frame = None
        return {"status": "stopped", "message": "Deteksi dihentikan"}

    def _detection_loop(self):
        """Loop utama deteksi — berjalan di thread terpisah."""
        prev_time = time.time()
        chart_interval = time.time()
        last_boxes = []  # Simpan hasil deteksi terakhir untuk frame yang di-skip

        while self.is_running:
            ret, frame = self.camera.read()
            if not ret:
                print("[WARNING] Gagal membaca frame.")
                break

            self.frame_count += 1
            run_inference = (self.frame_count % self.skip_frames == 0)

            if run_inference:
                # ── Inferensi YOLO (hanya setiap N frame) ────────────────
                results = self.model.predict(
                    source=frame,
                    conf=self.confidence,
                    imgsz=self.imgsz,
                    verbose=False,
                )

                # ── Proses Hasil Deteksi ─────────────────────────────────
                frame_counts = {"matang": 0, "mentah": 0, "busuk": 0}
                dominant_class = None
                max_conf = 0.0
                last_boxes = []

                for result in results:
                    if result.boxes is None:
                        continue
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                        conf = float(box.conf[0])
                        cls_id = int(box.cls[0])
                        cls_name = self.class_names.get(cls_id, "unknown")

                        # ── Filter: abaikan jika bukan stroberi ──────────
                        is_valid = self._is_strawberry(frame, x1, y1, x2, y2)
                        if not is_valid:
                            continue

                        if cls_name in frame_counts:
                            frame_counts[cls_name] += 1
                            self.session_counts[cls_name] += 1

                        if conf > max_conf:
                            max_conf = conf
                            dominant_class = cls_name

                        # Simpan box untuk digambar di frame yang di-skip
                        last_boxes.append((x1, y1, x2, y2, cls_name, conf))

                # ── Update stats per-frame ───────────────────────────────
                self.current_counts = dict(frame_counts)

                # ── Log deteksi (setiap 15 frame) ────────────────────────
                total_in_frame = sum(frame_counts.values())
                if total_in_frame > 0 and self.frame_count % 15 == 0:
                    entry = {
                        "waktu": datetime.now().strftime("%H:%M:%S"),
                        "matang": frame_counts["matang"],
                        "mentah": frame_counts["mentah"],
                        "busuk": frame_counts["busuk"],
                        "total": total_in_frame,
                        "dominan": dominant_class,
                        "confidence": round(max_conf, 2),
                    }
                    self.detection_log.insert(0, entry)
                    if len(self.detection_log) > 100:
                        self.detection_log = self.detection_log[:100]

                    # Kirim ke ESP32 jika terhubung
                    if self.auto_send_serial and self.serial_conn and dominant_class:
                        self._send_serial(dominant_class)

            # ── Gambar bounding box (dari hasil terakhir) ────────────────
            for (x1, y1, x2, y2, cls_name, conf) in last_boxes:
                color = self.COLORS_BGR.get(cls_name, (200, 200, 200))
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"{cls_name} {conf:.0%}"
                (lw, lh), _ = cv2.getTextSize(
                    label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                )
                cv2.rectangle(
                    frame, (x1, y1 - lh - 8), (x1 + lw + 4, y1), color, -1
                )
                cv2.putText(
                    frame, label, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2,
                )

            # ── Hitung FPS ───────────────────────────────────────────────
            curr_time = time.time()
            dt = curr_time - prev_time
            self.fps = 1.0 / dt if dt > 0 else 0
            prev_time = curr_time

            # ── Data chart (setiap 3 detik) ──────────────────────────────
            if curr_time - chart_interval >= 3.0:
                chart_interval = curr_time
                self.chart_history.append({
                    "waktu": datetime.now().strftime("%H:%M:%S"),
                    "matang": self.session_counts["matang"],
                    "mentah": self.session_counts["mentah"],
                    "busuk": self.session_counts["busuk"],
                })
                if len(self.chart_history) > 40:
                    self.chart_history = self.chart_history[-40:]

            # ── Encode frame ke JPEG ─────────────────────────────────────
            _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            with self.frame_lock:
                self.current_frame = buffer.tobytes()

        # Loop selesai
        self.is_running = False

    def generate_frames(self):
        """Generator MJPEG untuk streaming ke browser."""
        # Tunggu frame pertama tersedia
        for _ in range(50):
            with self.frame_lock:
                if self.current_frame is not None:
                    break
            time.sleep(0.1)

        while self.is_running:
            with self.frame_lock:
                frame = self.current_frame
            if frame is not None:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
            time.sleep(0.033)  # ~30 FPS maks

    # ─────────────────────────────────────────────────────────────────────
    # STATISTIK
    # ─────────────────────────────────────────────────────────────────────
    def get_stats(self):
        """Ambil semua statistik untuk dikirim ke frontend."""
        total = sum(self.session_counts.values())

        elapsed = ""
        if self.session_start and self.is_running:
            delta = datetime.now() - self.session_start
            secs = int(delta.total_seconds())
            hours, remainder = divmod(secs, 3600)
            minutes, seconds = divmod(remainder, 60)
            elapsed = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return {
            "is_running": self.is_running,
            "fps": round(self.fps, 1),
            "total": total,
            "matang": self.session_counts["matang"],
            "mentah": self.session_counts["mentah"],
            "busuk": self.session_counts["busuk"],
            "current": self.current_counts,
            "elapsed": elapsed,
            "confidence": self.confidence,
            "frame_count": self.frame_count,
            "log": self.detection_log[:25],
            "chart_history": self.chart_history[-20:],
            "serial_connected": self.serial_conn is not None,
        }

    # ─────────────────────────────────────────────────────────────────────
    # SERIAL / ESP32
    # ─────────────────────────────────────────────────────────────────────
    def list_serial_ports(self):
        """Daftar port serial yang tersedia."""
        if not SERIAL_AVAILABLE:
            return []
        ports = serial.tools.list_ports.comports()
        return [{"port": p.device, "desc": p.description} for p in ports]

    def connect_serial(self, port, baudrate=115200):
        """Hubungkan ke port serial ESP32."""
        if not SERIAL_AVAILABLE:
            return {"status": "error", "message": "pyserial belum terinstal"}
        try:
            self.serial_conn = serial.Serial(port, baudrate, timeout=1)
            time.sleep(2)  # Tunggu ESP32 reset
            msg = f"Terhubung ke {port} @ {baudrate} baud"
            self._log_serial(msg, "success")
            return {"status": "connected", "message": msg}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def disconnect_serial(self):
        """Putuskan koneksi serial."""
        if self.serial_conn:
            self.serial_conn.close()
            self.serial_conn = None
            self._log_serial("Koneksi diputus", "info")
        return {"status": "disconnected"}

    def _send_serial(self, data):
        """Kirim data ke ESP32 via serial."""
        try:
            command = data.strip() + "\n"
            self.serial_conn.write(command.encode("utf-8"))
            self._log_serial(f"TX → {data}", "sent")
        except Exception as e:
            self._log_serial(f"Error kirim: {e}", "error")

    def send_manual_serial(self, command):
        """Kirim perintah manual ke ESP32."""
        if not self.serial_conn:
            return {"status": "error", "message": "Tidak terhubung ke ESP32"}
        self._send_serial(command)
        return {"status": "sent", "message": f"Terkirim: {command}"}

    def _log_serial(self, message, msg_type="info"):
        entry = {
            "waktu": datetime.now().strftime("%H:%M:%S"),
            "pesan": message,
            "tipe": msg_type,
        }
        self.serial_log.insert(0, entry)
        if len(self.serial_log) > 50:
            self.serial_log = self.serial_log[:50]


# =============================================================================
# INISIALISASI SISTEM
# =============================================================================
system = DetectionSystem("best.pt")


# =============================================================================
# FLASK ROUTES
# =============================================================================

# ── Halaman Utama ────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


# ── Video Stream ─────────────────────────────────────────────────────────────
@app.route("/video_feed")
def video_feed():
    if system.is_running:
        return Response(
            system.generate_frames(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
    return "", 204


# ── API: Statistik ───────────────────────────────────────────────────────────
@app.route("/api/stats")
def api_stats():
    return jsonify(system.get_stats())


# ── API: Kontrol Deteksi ─────────────────────────────────────────────────────
@app.route("/api/start", methods=["POST"])
def api_start():
    result = system.start_detection()
    return jsonify(result)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    result = system.stop_detection()
    return jsonify(result)


# ── API: Pengaturan ──────────────────────────────────────────────────────────
@app.route("/api/confidence", methods=["POST"])
def api_confidence():
    data = request.json
    val = float(data.get("confidence", 0.5))
    system.confidence = max(0.1, min(1.0, val))
    return jsonify({"status": "ok", "confidence": system.confidence})


# ── API: Serial / ESP32 ─────────────────────────────────────────────────────
@app.route("/api/serial/ports")
def api_serial_ports():
    ports = system.list_serial_ports()
    return jsonify({"ports": ports, "available": SERIAL_AVAILABLE})


@app.route("/api/serial/connect", methods=["POST"])
def api_serial_connect():
    data = request.json
    result = system.connect_serial(
        data["port"], int(data.get("baudrate", 115200))
    )
    return jsonify(result)


@app.route("/api/serial/disconnect", methods=["POST"])
def api_serial_disconnect():
    result = system.disconnect_serial()
    return jsonify(result)


@app.route("/api/serial/send", methods=["POST"])
def api_serial_send():
    data = request.json
    command = data.get("command", "")
    result = system.send_manual_serial(command)
    return jsonify(result)


@app.route("/api/serial/log")
def api_serial_log():
    return jsonify({"log": system.serial_log[:30]})


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  🍓 SISTEM DETEKSI KEMATANGAN STROBERI")
    print("  📊 Dashboard : http://localhost:5000")
    print("  🛑 Hentikan  : Ctrl+C")
    print("=" * 60)
    print()
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)

