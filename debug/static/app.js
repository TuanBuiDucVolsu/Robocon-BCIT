// ============================================
// Robot Debug UI — JavaScript
// ============================================

const API = {
    move:       (action, speed) => apiPost("/api/move", { action, speed }),
    lift:       (action, shelf) => apiPost("/api/lift", { action, shelf }),
    classify:   ()              => apiPost("/api/vision/classify"),
    lineSensor: ()              => apiGet("/api/line_sensor"),
    status:     ()              => apiGet("/api/status"),
    shutdown:   ()              => apiPost("/api/shutdown"),
};

function apiPost(url, data = {}) {
    return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
    }).then(r => {
        if (!r.ok && r.headers.get("content-type")?.includes("text/html")) {
            throw new Error(`Server trả về lỗi ${r.status}`);
        }
        return r.json();
    });
}

function apiGet(url) {
    return fetch(url).then(r => {
        if (!r.ok && r.headers.get("content-type")?.includes("text/html")) {
            throw new Error(`Server trả về lỗi ${r.status}`);
        }
        return r.json();
    });
}

// ============================================
// Logging
// ============================================

const logEl = document.getElementById("log-output");

function log(msg, level = "info") {
    const time = new Date().toLocaleTimeString("vi-VN");
    const div = document.createElement("div");
    div.className = `log-entry ${level}`;
    div.textContent = `[${time}] ${msg}`;
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
    while (logEl.children.length > 200) {
        logEl.removeChild(logEl.firstChild);
    }
}

document.getElementById("btn-clear-log").addEventListener("click", () => {
    logEl.innerHTML = "";
});

// ============================================
// Tốc độ
// ============================================

const speedSlider = document.getElementById("speed-slider");
const speedValue = document.getElementById("speed-value");

speedSlider.addEventListener("input", () => {
    speedValue.textContent = speedSlider.value;
});

function getSpeed() {
    return parseInt(speedSlider.value, 10);
}

// ============================================
// Điều khiển di chuyển — nhấn giữ
// ============================================

let currentMoveAction = null;

function startMove(action) {
    if (currentMoveAction === action) return;
    currentMoveAction = action;
    const speed = getSpeed();
    API.move(action, speed).then(data => {
        if (data.ok) {
            log(`Di chuyển: ${action} (${speed}%)`);
        } else {
            log(`Di chuyển: ${data.error}`, "warn");
        }
    }).catch(e => log(`Lỗi: ${e.message}`, "error"));

    document.querySelectorAll(".btn-move").forEach(b => b.classList.remove("active"));
    const btn = document.querySelector(`.btn-move[data-action="${action}"]`);
    if (btn) btn.classList.add("active");
}

function stopMove() {
    if (currentMoveAction === null || currentMoveAction === "stop") return;
    currentMoveAction = null;
    API.move("stop", 0).catch(() => {});
    document.querySelectorAll(".btn-move").forEach(b => b.classList.remove("active"));
}

// Nút bấm — nhấn giữ (mouse + touch)
document.querySelectorAll(".btn-move").forEach(btn => {
    const action = btn.dataset.action;

    if (action === "stop") {
        btn.addEventListener("mousedown", () => stopMove());
        btn.addEventListener("touchstart", (e) => { e.preventDefault(); stopMove(); });
        return;
    }

    btn.addEventListener("mousedown", () => startMove(action));
    btn.addEventListener("mouseup", stopMove);
    btn.addEventListener("mouseleave", stopMove);
    btn.addEventListener("touchstart", (e) => { e.preventDefault(); startMove(action); });
    btn.addEventListener("touchend", (e) => { e.preventDefault(); stopMove(); });
    btn.addEventListener("touchcancel", stopMove);
});

// Phím tắt bàn phím
const KEY_MAP = {
    "w": "forward", "arrowup": "forward",
    "s": "backward", "arrowdown": "backward",
    "a": "left", "arrowleft": "left",
    "d": "right", "arrowright": "right",
    " ": "stop",
};

const pressedKeys = new Set();

document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT") return;
    const key = e.key.toLowerCase();
    const action = KEY_MAP[key];
    if (!action) return;
    e.preventDefault();

    if (action === "stop") {
        stopMove();
        return;
    }

    pressedKeys.add(key);
    startMove(action);
});

document.addEventListener("keyup", (e) => {
    const key = e.key.toLowerCase();
    pressedKeys.delete(key);
    if (KEY_MAP[key] && KEY_MAP[key] !== "stop" && pressedKeys.size === 0) {
        stopMove();
    }
});

// ============================================
// Điều khiển nâng/hạ
// ============================================

document.querySelectorAll(".btn-lift").forEach(btn => {
    btn.addEventListener("click", () => {
        const action = btn.dataset.action;
        const shelf = btn.dataset.shelf || 1;
        API.lift(action, parseInt(shelf)).then(data => {
            if (data.ok) {
                updateLiftDisplay(data.level);
                log(`Nâng/hạ: ${action} → tầng ${data.level}`);
            } else {
                log(`Nâng/hạ: ${data.error}`, "warn");
            }
        }).catch(e => log(`Lỗi nâng/hạ: ${e.message}`, "error"));
    });
});

function updateLiftDisplay(level) {
    document.getElementById("lift-level-text").textContent = level;
    const pct = (level / 2) * 100;
    document.getElementById("lift-bar").style.height = `${pct}%`;
}

// ============================================
// Nhận diện kiện hàng
// ============================================

const btnClassify = document.getElementById("btn-classify");
const resultBox = document.getElementById("vision-result");
const resultLabel = document.getElementById("result-label-text");
const resultConf = document.getElementById("result-confidence");
const resultFactory = document.getElementById("result-factory");

btnClassify.addEventListener("click", () => {
    btnClassify.disabled = true;
    btnClassify.textContent = "Đang quét...";
    log("Bắt đầu nhận diện kiện hàng...");

    API.classify().then(data => {
        resultBox.classList.remove("hidden");
        if (data.ok) {
            resultLabel.textContent = data.label.toUpperCase();
            resultConf.textContent = `${data.confidence}%`;
            resultConf.className = "confidence" +
                (data.confidence >= 70 ? "" : data.confidence >= 50 ? " low" : " very-low");
            resultFactory.textContent = `→ Nhà máy: ${data.factory}`;
            log(`Nhận diện: ${data.label} (${data.confidence}%) → ${data.factory}`);
        } else {
            resultLabel.textContent = "KHÔNG NHẬN DIỆN ĐƯỢC";
            resultConf.textContent = "";
            resultFactory.textContent = data.error || "";
            log(data.error || "Không nhận diện được kiện hàng", "warn");
        }
    }).catch(e => {
        log(`Lỗi nhận diện: ${e.message}`, "error");
    }).finally(() => {
        btnClassify.disabled = false;
        btnClassify.textContent = "Nhận diện kiện hàng";
    });
});

// ============================================
// Cập nhật cảm biến dò line (polling)
// ============================================

const sensorDots = document.querySelectorAll(".sensor-dot");
const sensorError = document.getElementById("sensor-error");
const sensorActive = document.getElementById("sensor-active");
const sensorIntersection = document.getElementById("sensor-intersection");

function updateLineSensor() {
    API.lineSensor().then(data => {
        data.values.forEach((val, i) => {
            if (sensorDots[i]) {
                sensorDots[i].classList.toggle("active", val === 1);
            }
        });
        sensorError.textContent = data.error.toFixed(2);
        sensorActive.textContent = data.active;
        if (data.is_intersection) {
            sensorIntersection.className = "badge badge-on";
        } else {
            sensorIntersection.className = "badge badge-off";
        }
    }).catch(() => {});
}

// ============================================
// Trạng thái phần cứng (polling)
// ============================================

let hwLogged = false;

function updateStatus() {
    API.status().then(data => {
        // Trạng thái phần cứng
        const hwBadge = document.getElementById("status-hw");
        if (data.hw_ok) {
            hwBadge.textContent = "Phần cứng OK";
            hwBadge.className = "badge badge-on";
        } else {
            hwBadge.textContent = "Không có phần cứng";
            hwBadge.className = "badge badge-wait";
            if (!hwLogged && data.hw_error) {
                log(`Phần cứng: ${data.hw_error} (giao diện vẫn hoạt động bình thường)`, "warn");
                hwLogged = true;
            }
        }

        // Camera
        const camBadge = document.getElementById("status-cam");
        camBadge.className = data.camera_ready ? "badge badge-on" : "badge badge-off";
        camBadge.textContent = data.camera_ready ? "Camera OK" : "Camera OFF";

        // Phương pháp nhận diện
        const modelBadge = document.getElementById("status-model");
        modelBadge.className = "badge badge-on";
        modelBadge.textContent = "HSV Color";

        updateLiftDisplay(data.lift_level);
    }).catch(() => {
        document.getElementById("status-hw").textContent = "Mất kết nối";
        document.getElementById("status-hw").className = "badge badge-off";
    });
}

// ============================================
// Khởi động
// ============================================

log("Giao diện debug đã sẵn sàng.");
updateStatus();

// Polling cảm biến mỗi 300ms
setInterval(updateLineSensor, 300);

// Polling trạng thái mỗi 3s
setInterval(updateStatus, 3000);

// Cleanup khi đóng tab
window.addEventListener("beforeunload", () => {
    if (currentMoveAction) {
        navigator.sendBeacon("/api/move", JSON.stringify({ action: "stop", speed: 0 }));
    }
});
