import os
import subprocess
import threading
import time
from datetime import datetime
import cv2
import numpy as np

# command open link shope: 
# adb shell am start -a android.intent.action.VIEW -d "https://vn.shp.ee/b3g639AP" com.shopee.vn

# Mỗi thiết bị ADB (serial, lấy bằng lệnh `adb devices`) có bộ điểm click riêng.
DEVICE_TARGETS = {
    "adb-5aa8d79d-266Dgg._adb-tls-connect._tcp": [
        (915, 460),
        (915, 510),
        (915, 610),
        (915, 635),
        (915, 666),
        (915, 735),
    ],
    # "e1fc4dcc": [
    #     (915, 480),
    #     (915, 610),
    #     (915, 635),
    # ],
}

CAPTURE_DELAY_SEC = 5
CLICK_COOLDOWN_SEC = 5
# Timeout cho mỗi lệnh adb: tránh treo vô hạn nếu thiết bị mất kết nối/lag,
# việc này khiến Ctrl+C không phản hồi khi chạy nhiều giờ.
ADB_TIMEOUT_SEC = 10
SAVE_DEBUG_IMAGE = True
DEBUG_IMAGE_PATH = "./image/last_click_{device}.png"      # ảnh có vẽ chú thích, để xem bằng mắt
RAW_IMAGE_PATH = "./image/last_capture_raw_{device}.png"  # ảnh gốc chưa vẽ gì, để dò lại ngưỡng màu

# Vùng kiểm tra là HÌNH TRÒN bán kính 5px, tâm đúng tại điểm click.
TARGET_REGION_RADIUS = 5
# Tỉ lệ pixel cam tối thiểu trong hình tròn thì mới coi là nút Lưu.
MIN_ORANGE_RATIO = 0.6

# Nút Lưu là màu cam RỰC (H=5, S~229, V~225). Nền gradient cam nhạt phía sau
# popup có cùng hue nhưng tối/nhạt hơn hẳn (S<=189, V<=182) -> dùng S/V để loại.
LOWER_ORANGE = np.array([3, 195, 200])
UPPER_ORANGE = np.array([14, 255, 255])
MORPH_KERNEL = np.ones((3, 3), np.uint8)

# Mặt nạ hình tròn (11x11 cho r=5), dùng lại cho mọi target.
_yy, _xx = np.mgrid[
    -TARGET_REGION_RADIUS : TARGET_REGION_RADIUS + 1,
    -TARGET_REGION_RADIUS : TARGET_REGION_RADIUS + 1,
]
CIRCLE_MASK = (_xx**2 + _yy**2) <= TARGET_REGION_RADIUS**2
CIRCLE_AREA = int(CIRCLE_MASK.sum())
MIN_ORANGE_PIXELS = int(round(CIRCLE_AREA * MIN_ORANGE_RATIO))


# thực hiện click trên thiết bị chỉ định (serial)
def adb_tap(device_id, x, y):
    try:
        subprocess.run(
            ["adb", "-s", device_id, "shell", "input", "tap", str(x), str(y)],
            check=False,
            timeout=ADB_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"[WARN][{device_id}] Lệnh tap quá {ADB_TIMEOUT_SEC}s, bỏ qua lần này.")


# chụp màn hình của thiết bị chỉ định (serial)
def capture_screen(device_id):
    try:
        result = subprocess.run(
            ["adb", "-s", device_id, "exec-out", "screencap", "-p"],
            check=False,
            capture_output=True,
            timeout=ADB_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        print(f"[WARN][{device_id}] Lệnh screencap quá {ADB_TIMEOUT_SEC}s, bỏ qua lần này.")
        return None

    if result.returncode != 0 or not result.stdout:
        return None

    return cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)


# tạo mask cam cho cả frame (chỉ tính 1 lần mỗi frame)
def build_orange_mask(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_ORANGE, UPPER_ORANGE)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, MORPH_KERNEL, iterations=1)
    return hsv, mask


# đếm pixel cam + lấy HSV đại diện trong hình tròn r=TARGET_REGION_RADIUS quanh target
def probe_target(hsv, mask, target_x, target_y):
    height, width = mask.shape[:2]
    r = TARGET_REGION_RADIUS

    x1, x2 = max(0, target_x - r), min(width, target_x + r + 1)
    y1, y2 = max(0, target_y - r), min(height, target_y + r + 1)
    if x1 >= x2 or y1 >= y2:
        return 0, [0, 0, 0]

    # cắt CIRCLE_MASK theo đúng phần đã bị clip ở biên màn hình
    circle = CIRCLE_MASK[
        y1 - (target_y - r) : y2 - (target_y - r),
        x1 - (target_x - r) : x2 - (target_x - r),
    ]
    orange_pixels = int(np.count_nonzero((mask[y1:y2, x1:x2] > 0) & circle))

    # HSV trung vị của cả vùng tròn: đại diện hơn 1 pixel tâm (dễ dính
    # tap-indicator của thiết bị hoặc pixel nhiễu)
    median_hsv = np.median(hsv[y1:y2, x1:x2][circle], axis=0).astype(int).tolist()
    return orange_pixels, median_hsv


# vẽ ảnh debug: vòng định vị to cho dễ tìm + vòng r=5 đúng vùng check thật
def draw_debug(frame, results, clicked):
    overlay = frame.copy()
    r = TARGET_REGION_RADIUS

    for (tx, ty, pixels) in results:
        hit = (tx, ty) == clicked
        color = (0, 255, 255) if hit else (160, 160, 160)

        if hit:
            # vòng định vị lớn + 4 gạch chỉ vào tâm (chừa trống để không che vùng check)
            cv2.circle(overlay, (tx, ty), 40, color, 2)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                cv2.line(overlay, (tx + dx * 38, ty + dy * 38),
                         (tx + dx * 14, ty + dy * 14), color, 2)

        # vùng check thật: hình tròn r=5, vẽ to gấp 4 lần ở khung phóng to bên cạnh
        cv2.circle(overlay, (tx, ty), r, (0, 255, 0) if hit else color, 1)
        cv2.putText(overlay, f"{pixels}/{CIRCLE_AREA}", (tx + 48, ty + 6),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA)

    # khung phóng to 8x quanh điểm được click, dán vào góc trên trái
    if clicked is not None:
        cx, cy = clicked
        pad = 14
        y1, y2 = max(0, cy - pad), min(frame.shape[0], cy + pad + 1)
        x1, x2 = max(0, cx - pad), min(frame.shape[1], cx + pad + 1)
        zoom = cv2.resize(frame[y1:y2, x1:x2], None, fx=8, fy=8,
                          interpolation=cv2.INTER_NEAREST)
        cv2.circle(zoom, ((cx - x1) * 8 + 4, (cy - y1) * 8 + 4), r * 8, (0, 255, 0), 2)
        cv2.rectangle(zoom, (0, 0), (zoom.shape[1] - 1, zoom.shape[0] - 1), (0, 255, 255), 2)
        overlay[20:20 + zoom.shape[0], 20:20 + zoom.shape[1]] = zoom

    return overlay


def run_for_device(device_id, click_targets, stop_event):
    last_click_at = 0.0
    debug_image_path = DEBUG_IMAGE_PATH.format(device=device_id)
    raw_image_path = RAW_IMAGE_PATH.format(device=device_id)

    print(f"[START] Auto-click start | device={device_id} | targets={click_targets}")

    while not stop_event.is_set():
        frame = capture_screen(device_id)
        if frame is None:
            print(f"[WARN][{device_id}] Không chụp được màn hình (ADB lỗi?), thử lại sau...")
            stop_event.wait(CAPTURE_DELAY_SEC)
            continue

        hsv, mask = build_orange_mask(frame)

        found = None
        results = []
        for tx, ty in click_targets:
            orange_pixels, median_hsv = probe_target(hsv, mask, tx, ty)
            results.append((tx, ty, orange_pixels))
            if orange_pixels >= MIN_ORANGE_PIXELS:
                found = (tx, ty, orange_pixels, median_hsv)
                break

        if found is not None:
            cx, cy, found_pixels, found_hsv = found
            now = time.time()
            if now - last_click_at >= CLICK_COOLDOWN_SEC:
                print(
                    f"[{device_id}] Click nút Lưu tại: ({cx}, {cy}) | "
                    f"Orange pixels: {found_pixels}/{CIRCLE_AREA} | HSV~ {found_hsv}"
                )

                if SAVE_DEBUG_IMAGE:
                    # lưu ảnh gốc TRƯỚC khi vẽ: chú thích vẽ đè lên vùng check
                    # sẽ làm sai lệch nếu sau này dùng ảnh đó để dò ngưỡng màu
                    cv2.imwrite(raw_image_path, frame)
                    cv2.imwrite(debug_image_path, draw_debug(frame, results, (cx, cy)))
                    print(f"[{device_id}] ====> Hoàn thành lúc {datetime.now().strftime('%H:%M:%S')}")

                adb_tap(device_id, cx, cy)
                last_click_at = now

        stop_event.wait(CAPTURE_DELAY_SEC)

    print(f"[STOP] Đã dừng | device={device_id}")


def main():
    if not DEVICE_TARGETS:
        print("[ERROR] DEVICE_TARGETS trống, không có thiết bị nào để chạy.")
        return

    stop_event = threading.Event()
    threads = [
        threading.Thread(target=run_for_device, args=(device_id, targets, stop_event), daemon=True)
        for device_id, targets in DEVICE_TARGETS.items()
    ]
    for t in threads:
        t.start()

    try:
        # join có timeout để main thread luôn tỉnh dậy và bắt được Ctrl+C,
        # thay vì bị chặn vô hạn trong join() không tham số.
        while any(t.is_alive() for t in threads):
            for t in threads:
                t.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\n[STOP] Nhận Ctrl+C, đang dừng các thiết bị...")
        stop_event.set()
        for t in threads:
            t.join(timeout=ADB_TIMEOUT_SEC + 2)
        # Nếu có thread vẫn kẹt trong 1 lệnh adb quá thời gian timeout,
        # ép thoát process luôn để terminal không bị treo.
        if any(t.is_alive() for t in threads):
            print("[STOP] Một số thread chưa thoát kịp, ép dừng process.")
            os._exit(1)


if __name__ == "__main__":
    main()
