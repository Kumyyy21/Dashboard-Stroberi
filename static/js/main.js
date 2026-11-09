/* =============================================================================
   Stroberi Vision Dashboard — JavaScript
   ============================================================================= */

// ── State ───────────────────────────────────────────────────────────────────
let isDetecting = false;
let statsInterval = null;
let timeChart = null;
let donutChart = null;

// ── DOM References ──────────────────────────────────────────────────────────
const pageTitle = document.getElementById("pageTitle");
const systemStatus = document.getElementById("systemStatus");

// ── Navigation ──────────────────────────────────────────────────────────────
const sectionTitles = {
    dashboard: "Dashboard Overview",
    detection: "Deteksi Live",
    esp32: "Kontrol ESP32",
    settings: "Pengaturan",
};

document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", (e) => {
        e.preventDefault();
        const section = item.dataset.section;

        // Update active nav
        document.querySelectorAll(".nav-item").forEach((n) => n.classList.remove("active"));
        item.classList.add("active");

        // Show section
        document.querySelectorAll(".content-section").forEach((s) => s.classList.remove("active"));
        document.getElementById(`section-${section}`).classList.add("active");

        // Update title
        pageTitle.textContent = sectionTitles[section] || "Dashboard";

        // Close mobile sidebar
        document.getElementById("sidebar").classList.remove("open");
    });
});

// Mobile menu toggle
document.getElementById("menuToggle").addEventListener("click", () => {
    document.getElementById("sidebar").classList.toggle("open");
});

// ── Clock ───────────────────────────────────────────────────────────────────
function updateClock() {
    const now = new Date();
    const options = {
        weekday: "long",
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
    };
    document.getElementById("clock").textContent = now.toLocaleDateString("id-ID", options);
}
updateClock();
setInterval(updateClock, 1000);

// ── Initialize Charts ───────────────────────────────────────────────────────
function initCharts() {
    // Time series chart
    const timeCtx = document.getElementById("timeChart").getContext("2d");
    timeChart = new Chart(timeCtx, {
        type: "line",
        data: {
            labels: [],
            datasets: [
                {
                    label: "Matang",
                    data: [],
                    borderColor: "#27ae60",
                    backgroundColor: "rgba(39, 174, 96, 0.1)",
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 3,
                },
                {
                    label: "Mentah",
                    data: [],
                    borderColor: "#f39c12",
                    backgroundColor: "rgba(243, 156, 18, 0.1)",
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 3,
                },
                {
                    label: "Busuk",
                    data: [],
                    borderColor: "#e74c3c",
                    backgroundColor: "rgba(231, 76, 60, 0.1)",
                    fill: true,
                    tension: 0.4,
                    borderWidth: 2,
                    pointRadius: 3,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "top",
                    labels: { usePointStyle: true, padding: 16, font: { size: 12 } },
                },
            },
            scales: {
                x: { grid: { display: false } },
                y: { beginAtZero: true, grid: { color: "#f0f2f5" } },
            },
            animation: { duration: 300 },
        },
    });

    // Donut chart
    const donutCtx = document.getElementById("donutChart").getContext("2d");
    donutChart = new Chart(donutCtx, {
        type: "doughnut",
        data: {
            labels: ["Matang", "Mentah", "Busuk"],
            datasets: [
                {
                    data: [0, 0, 0],
                    backgroundColor: ["#27ae60", "#f39c12", "#e74c3c"],
                    borderWidth: 0,
                    hoverOffset: 8,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: "65%",
            plugins: {
                legend: {
                    position: "bottom",
                    labels: { usePointStyle: true, padding: 16, font: { size: 12 } },
                },
            },
            animation: { duration: 300 },
        },
    });
}

// ── Detection Controls ──────────────────────────────────────────────────────
async function startDetection() {
    try {
        const res = await fetch("/api/start", { method: "POST" });
        const data = await res.json();

        if (data.status === "started" || data.status === "already_running") {
            isDetecting = true;
            updateControlState(true);
            showVideoFeed(true);
            startStatsPolling();
        } else {
            alert("Error: " + data.message);
        }
    } catch (err) {
        alert("Gagal menghubungi server: " + err.message);
    }
}

async function stopDetection() {
    try {
        await fetch("/api/stop", { method: "POST" });
        isDetecting = false;
        updateControlState(false);
        showVideoFeed(false);
        stopStatsPolling();
    } catch (err) {
        alert("Gagal menghubungi server: " + err.message);
    }
}

function updateControlState(running) {
    document.getElementById("btnStart").disabled = running;
    document.getElementById("btnStop").disabled = !running;

    const dot = systemStatus.querySelector(".status-dot");
    const text = systemStatus.querySelector(".status-text");

    if (running) {
        dot.className = "status-dot online";
        text.textContent = "Deteksi Aktif";
    } else {
        dot.className = "status-dot offline";
        text.textContent = "Sistem Idle";
    }
}

function showVideoFeed(show) {
    const feed = document.getElementById("videoFeed");
    const placeholder = document.getElementById("videoPlaceholder");

    if (show) {
        // Add timestamp to force reload
        feed.src = "/video_feed?t=" + Date.now();
        feed.style.display = "block";
        placeholder.style.display = "none";
    } else {
        feed.src = "";
        feed.style.display = "none";
        placeholder.style.display = "block";
    }
}

// ── Stats Polling ───────────────────────────────────────────────────────────
function startStatsPolling() {
    if (statsInterval) clearInterval(statsInterval);
    pollStats(); // Immediate first poll
    statsInterval = setInterval(pollStats, 800);
}

function stopStatsPolling() {
    if (statsInterval) {
        clearInterval(statsInterval);
        statsInterval = null;
    }
}

async function pollStats() {
    try {
        const res = await fetch("/api/stats");
        const data = await res.json();
        updateDashboard(data);
    } catch (err) {
        // Silent fail — server mungkin sedang sibuk
    }
}

function updateDashboard(data) {
    // Stat cards
    document.getElementById("statTotal").textContent = data.total.toLocaleString();
    document.getElementById("statMatang").textContent = data.matang.toLocaleString();
    document.getElementById("statMentah").textContent = data.mentah.toLocaleString();
    document.getElementById("statBusuk").textContent = data.busuk.toLocaleString();

    const elapsed = data.elapsed || "Belum dimulai";
    document.getElementById("statElapsed").textContent = elapsed;

    // FPS
    document.getElementById("fpsDisplay").textContent = data.fps + " FPS";
    document.getElementById("liveFps").textContent = "⏱ " + data.fps + " FPS";
    document.getElementById("liveFrames").textContent = "📷 " + data.frame_count + " frame";

    // Live stats panel
    document.getElementById("liveMatang").textContent = data.current.matang || 0;
    document.getElementById("liveMentah").textContent = data.current.mentah || 0;
    document.getElementById("liveBusuk").textContent = data.current.busuk || 0;
    document.getElementById("liveTotal").textContent = data.total;
    document.getElementById("liveElapsed").textContent = elapsed;

    // Donut chart
    if (donutChart) {
        donutChart.data.datasets[0].data = [data.matang, data.mentah, data.busuk];
        donutChart.update();
    }

    // Time chart
    if (timeChart && data.chart_history && data.chart_history.length > 0) {
        const labels = data.chart_history.map((d) => d.waktu);
        const matangData = data.chart_history.map((d) => d.matang);
        const mentahData = data.chart_history.map((d) => d.mentah);
        const busukData = data.chart_history.map((d) => d.busuk);

        timeChart.data.labels = labels;
        timeChart.data.datasets[0].data = matangData;
        timeChart.data.datasets[1].data = mentahData;
        timeChart.data.datasets[2].data = busukData;
        timeChart.update();
    }

    // Detection log table
    updateLogTable(data.log);

    // Update control state (in case page was refreshed while running)
    if (data.is_running && !isDetecting) {
        isDetecting = true;
        updateControlState(true);
        showVideoFeed(true);
    }
}

function updateLogTable(log) {
    const tbody = document.getElementById("logTableBody");

    if (!log || log.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="empty-state">
            Belum ada data deteksi. Mulai deteksi untuk melihat riwayat.
        </td></tr>`;
        document.getElementById("logCount").textContent = "0 entri";
        return;
    }

    document.getElementById("logCount").textContent = log.length + " entri";

    let html = "";
    log.forEach((entry, i) => {
        const dominanClass = entry.dominan || "-";
        html += `<tr>
            <td>${i + 1}</td>
            <td>${entry.waktu}</td>
            <td>${entry.matang}</td>
            <td>${entry.mentah}</td>
            <td>${entry.busuk}</td>
            <td><span class="class-badge ${dominanClass}">${dominanClass}</span></td>
            <td>${(entry.confidence * 100).toFixed(0)}%</td>
        </tr>`;
    });
    tbody.innerHTML = html;
}

// ── Confidence Slider ───────────────────────────────────────────────────────
function updateConfidence(value) {
    document.getElementById("confValue").textContent = parseFloat(value).toFixed(2);
    fetch("/api/confidence", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confidence: value }),
    });
}

// ── Serial / ESP32 ──────────────────────────────────────────────────────────
async function refreshPorts() {
    try {
        const res = await fetch("/api/serial/ports");
        const data = await res.json();
        const select = document.getElementById("serialPort");
        select.innerHTML = '<option value="">-- Pilih Port --</option>';

        if (!data.available) {
            select.innerHTML =
                '<option value="">pyserial belum terinstal</option>';
            return;
        }

        data.ports.forEach((p) => {
            const opt = document.createElement("option");
            opt.value = p.port;
            opt.textContent = `${p.port} — ${p.desc}`;
            select.appendChild(opt);
        });
    } catch (err) {
        console.error("Error refreshing ports:", err);
    }
}

async function connectSerial() {
    const port = document.getElementById("serialPort").value;
    const baudrate = document.getElementById("baudRate").value;

    if (!port) {
        alert("Pilih port serial terlebih dahulu!");
        return;
    }

    try {
        const res = await fetch("/api/serial/connect", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ port, baudrate }),
        });
        const data = await res.json();

        if (data.status === "connected") {
            document.getElementById("serialStatus").textContent = "Terhubung";
            document.getElementById("serialStatus").style.background = "#eafaf1";
            document.getElementById("serialStatus").style.color = "#27ae60";
            document.getElementById("btnSerialConnect").disabled = true;
            document.getElementById("btnSerialDisconnect").disabled = false;
            appendSerialLog(data.message, "success");
        } else {
            alert("Error: " + data.message);
            appendSerialLog("Error: " + data.message, "error");
        }
    } catch (err) {
        alert("Gagal menghubungi server: " + err.message);
    }
}

async function disconnectSerial() {
    try {
        await fetch("/api/serial/disconnect", { method: "POST" });
        document.getElementById("serialStatus").textContent = "Tidak terhubung";
        document.getElementById("serialStatus").style.background = "#eaf2fd";
        document.getElementById("serialStatus").style.color = "#2d8cf0";
        document.getElementById("btnSerialConnect").disabled = false;
        document.getElementById("btnSerialDisconnect").disabled = true;
        appendSerialLog("Koneksi diputus", "info");
    } catch (err) {
        console.error("Error:", err);
    }
}

async function sendSerialCommand() {
    const input = document.getElementById("serialCommand");
    const command = input.value.trim();
    if (!command) return;

    try {
        const res = await fetch("/api/serial/send", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ command }),
        });
        const data = await res.json();

        if (data.status === "sent") {
            appendSerialLog(`TX → ${command}`, "sent");
            input.value = "";
        } else {
            appendSerialLog("Error: " + data.message, "error");
        }
    } catch (err) {
        appendSerialLog("Error: " + err.message, "error");
    }
}

function sendQuick(cmd) {
    document.getElementById("serialCommand").value = cmd;
    sendSerialCommand();
}

function appendSerialLog(message, type = "info") {
    const log = document.getElementById("serialLog");
    const empty = log.querySelector(".log-empty");
    if (empty) empty.remove();

    const now = new Date().toLocaleTimeString("id-ID");
    const entry = document.createElement("div");
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `<span class="time">[${now}]</span> ${message}`;
    log.prepend(entry);

    // Limit entries
    while (log.children.length > 50) {
        log.removeChild(log.lastChild);
    }
}

// ── Init ────────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    initCharts();
    refreshPorts();

    // Check if detection is already running (page refresh scenario)
    fetch("/api/stats")
        .then((res) => res.json())
        .then((data) => {
            if (data.is_running) {
                isDetecting = true;
                updateControlState(true);
                showVideoFeed(true);
                startStatsPolling();
            }
        })
        .catch(() => {});
});

