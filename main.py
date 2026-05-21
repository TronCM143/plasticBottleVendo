from ultralytics import YOLO
import cv2
import requests
import time
import serial
import uuid
from collections import deque

# ================= CONFIG =================
SERVER_URL = "http://172.20.10.2:8080/api/detect"

HOLD_SECONDS = 3.0          # ✅ fixed to 3 seconds as intended
CENTER_TOLERANCE = 60
CONF_WINDOW = 10
COOLDOWN = 3.0
SERVO_COOLDOWN = 6.0

# ✅ Class-specific thresholds
ALLOWED_CLASSES = {
    "plastic_bottle": 0.30,
    "other": 0.75
}

# ================= DEVICE INFO =================
def get_mac():
    mac = uuid.UUID(int=uuid.getnode()).hex[-12:]
    return ':'.join(mac[i:i+2] for i in range(0, 12, 2))

DEVICE_MAC = get_mac()
print(f"📟 Device MAC: {DEVICE_MAC}")

# ================= SERIAL =================
try:
    esp = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
    time.sleep(2)
    print("✅ ESP8266 connected")
except Exception as e:
    print(f"❌ ESP8266 error: {e}")
    esp = None

def move_left():
    if esp and esp.is_open:
        esp.write(b"LEFT\n")
        print("🔄 Servo triggered")

# ================= MODEL =================
model = YOLO("best.pt")
print("📦 Model classes:", model.names)

cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("❌ Camera error")
    exit()

# ================= STATE =================
tracking = False
start_time = None
last_sent = 0
last_servo_time = 0
bottle_count = 0
conf_history = deque(maxlen=CONF_WINDOW)
tracked_class = None        # ✅ NEW: lock class during tracking
miss_count = 0              # ✅ NEW: tolerate brief misses
MAX_MISS = 5                # ✅ allow up to 5 missed frames before reset

# ================= API =================
def send_to_api(count, avg_conf, cls_name):
    try:
        res = requests.post(SERVER_URL, json={
            "result": "ACCEPT",
            "type": cls_name,
            "bottle_count": count,
            "avg_confidence": round(avg_conf, 3),
            "mac": DEVICE_MAC
        }, timeout=2)
        print(f"✅ API: {res.status_code} {res.text}")
    except Exception as e:
        print(f"❌ API error: {e}")

def reset_tracking():
    """Full reset of tracking state"""
    global tracking, start_time, conf_history, tracked_class, miss_count
    tracking = False
    start_time = None
    conf_history.clear()
    tracked_class = None
    miss_count = 0

# ================= MAIN LOOP =================
while True:
    ret, frame = cap.read()
    if not ret:
        break

    h, w, _ = frame.shape
    cx = w // 2
    now = time.time()

    results = model(frame)
    annotated = results[0].plot()

    # center guides
    cv2.line(annotated, (cx, 0), (cx, h), (255, 100, 0), 2)
    cv2.rectangle(annotated,
                  (cx - CENTER_TOLERANCE, 0),
                  (cx + CENTER_TOLERANCE, h),
                  (255, 200, 0), 1)

    best_conf = 0
    best_box = None
    best_class = None

    # ===== DETECTION LOOP =====
    for box in results[0].boxes:
        cls_id = int(box.cls[0])
        cls_name = model.names[cls_id]

        if cls_name not in ALLOWED_CLASSES:
            continue

        conf = float(box.conf[0])
        min_conf_required = ALLOWED_CLASSES[cls_name]

        if conf < min_conf_required:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        box_cx = (x1 + x2) // 2

        if abs(box_cx - cx) > CENTER_TOLERANCE:
            continue

        if conf > best_conf:
            best_conf = conf
            best_box = (x1, y1, x2, y2)
            best_class = cls_name

    detected = best_box is not None

    # ===== TRACKING LOGIC =====
    if detected:
        miss_count = 0  # ✅ reset miss counter when something detected

        # ✅ If a different class appears mid-track, reset
        if tracking and tracked_class and best_class != tracked_class:
            print(f"⚠️ Class changed {tracked_class} → {best_class}, resetting")
            reset_tracking()

        # ✅ Start tracking fresh — clear old history for new object
        if not tracking:
            conf_history.clear()    # ✅ BUG FIX: clear stale history
            tracking = True
            start_time = now
            tracked_class = best_class
            print(f"🎯 Started tracking: {best_class}")

        conf_history.append(best_conf)
        avg_conf = sum(conf_history) / len(conf_history)
        elapsed = now - start_time
        required_conf = ALLOWED_CLASSES[best_class]

        x1, y1, x2, y2 = best_box
        color = (0, 255, 0) if elapsed >= HOLD_SECONDS else (0, 200, 255)
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 3)

        # label with class + conf + elapsed
        label = f"{best_class} {avg_conf:.0%}"
        cv2.putText(annotated, label,
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                    (0, 255, 0), 2)

        # progress bar
        bar_w = int((elapsed / HOLD_SECONDS) * (CENTER_TOLERANCE * 2))
        bar_w = min(bar_w, CENTER_TOLERANCE * 2)
        cv2.rectangle(annotated,
                      (cx - CENTER_TOLERANCE, h - 20),
                      (cx - CENTER_TOLERANCE + bar_w, h - 5),
                      (0, 255, 255), -1)

        # hold timer text
        cv2.putText(annotated,
                    f"VERIFYING... {elapsed:.1f}/{HOLD_SECONDS:.0f}s  {avg_conf:.0%}",
                    (20, 100),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.8,
                    (0, 255, 255),
                    2)

        # ===== ACCEPT after HOLD_SECONDS =====
        if elapsed >= HOLD_SECONDS and (now - last_sent) >= COOLDOWN:
            # ✅ final confidence check at moment of acceptance
            if avg_conf >= required_conf:
                bottle_count += 1
                print(f"✅ ACCEPTED: {best_class} | conf: {avg_conf:.0%} | total: {bottle_count}")

                send_to_api(bottle_count, avg_conf, best_class)

                if (now - last_servo_time) >= SERVO_COOLDOWN:
                    move_left()
                    last_servo_time = now

                last_sent = now

            else:
                print(f"❌ REJECTED at acceptance: avg_conf {avg_conf:.0%} too low")

            reset_tracking()    # ✅ always reset after acceptance attempt

    else:
        # ✅ BUG FIX: don't reset immediately — tolerate brief misses
        if tracking:
            miss_count += 1
            print(f"⚠️ Miss {miss_count}/{MAX_MISS}")

            if miss_count >= MAX_MISS:
                print("🔄 Too many misses — resetting")
                reset_tracking()
        # if not tracking, nothing to do

    # ===== UI =====
    cv2.putText(annotated, f"Bottles: {bottle_count}",
                (20, 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.2,
                (0, 255, 0),
                3)

    status = "VERIFYING" if tracking else "WAITING"
    cv2.putText(annotated, status,
                (w - 160, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255) if tracking else (100, 100, 100),
                2)

    servo_active = (now - last_servo_time) < SERVO_COOLDOWN and last_servo_time > 0
    cv2.putText(annotated,
                "SERVO: MOVING" if servo_active else "SERVO: READY",
                (20, h - 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 165, 255) if servo_active else (0, 255, 0),
                2)

    esp_ok = (esp and esp.is_open)
    cv2.putText(annotated,
                "ESP: OK" if esp_ok else "ESP: NO SIGNAL",
                (20, h - 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0) if esp_ok else (0, 0, 255),
                2)

    cv2.imshow("Bottle Detection", annotated)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# ================= CLEANUP =================
cap.release()
cv2.destroyAllWindows()
if esp and esp.is_open:
    esp.close()
    print("🔌 ESP disconnected")


    