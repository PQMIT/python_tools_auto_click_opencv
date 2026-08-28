import subprocess
import time

import cv2
import numpy as np


CAPTURE_DELAY_SEC = 5
CLICK_COOLDOWN_SEC = 5
SAVE_DEBUG_IMAGE = True
DEBUG_IMAGE_PATH = "last_click.png"      # ảnh có vẽ chú thích, để xem bằng mắt
RAW_IMAGE_PATH = "last_capture_raw.png"  # ảnh gốc chưa vẽ gì, để dò lại ngưỡng màu

CLICK_TARGETS = [
    (915, 460),
    (915, 510),
    (915, 610),
    (915, 635),
    (915, 735),
    (915, 860),
]

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


# thực hiện click
def adb_tap(x, y):
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)], check=False)


# chụp màn hình
def capture_screen():
    result = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"],
        check=False,
        capture_output=True,
    )
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


def main():
    last_click_at = 0.0

    print(
        f"[START] Auto-click đang chạy | Targets: {CLICK_TARGETS} | "
        f"Vùng check: hình tròn r={TARGET_REGION_RADIUS}px ({CIRCLE_AREA}px) | "
        f"Ngưỡng: >={MIN_ORANGE_PIXELS}px | Delay: {CAPTURE_DELAY_SEC}s"
    )

    while True:
        frame = capture_screen()
        if frame is None:
            print("[WARN] Không chụp được màn hình (ADB lỗi?), thử lại sau...")
            time.sleep(CAPTURE_DELAY_SEC)
            continue

        print(".", flush=True)

        hsv, mask = build_orange_mask(frame)

        found = None
        results = []
        for tx, ty in CLICK_TARGETS:
            orange_pixels, median_hsv = probe_target(hsv, mask, tx, ty)
            results.append((tx, ty, orange_pixels))
            if orange_pixels > 0:
                print(f"  ({tx},{ty})| Orange pixels: {orange_pixels}/{CIRCLE_AREA}| HSV~ {median_hsv}")
            if orange_pixels >= MIN_ORANGE_PIXELS:
                found = (tx, ty, orange_pixels, median_hsv)
                break

        if found is not None:
            cx, cy, found_pixels, found_hsv = found
            now = time.time()
            if now - last_click_at >= CLICK_COOLDOWN_SEC:
                print(
                    f"Click nút Lưu tại: ({cx}, {cy}) | "
                    f"Orange pixels: {found_pixels}/{CIRCLE_AREA} | HSV~ {found_hsv}"
                )

                if SAVE_DEBUG_IMAGE:
                    # lưu ảnh gốc TRƯỚC khi vẽ: chú thích vẽ đè lên vùng check
                    # sẽ làm sai lệch nếu sau này dùng ảnh đó để dò ngưỡng màu
                    cv2.imwrite(RAW_IMAGE_PATH, frame)
                    cv2.imwrite(DEBUG_IMAGE_PATH, draw_debug(frame, results, (cx, cy)))
                    print(f"Đã lưu ảnh kiểm tra: {DEBUG_IMAGE_PATH} (gốc: {RAW_IMAGE_PATH})")

                adb_tap(cx, cy)
                last_click_at = now

        time.sleep(CAPTURE_DELAY_SEC)


if __name__ == "__main__":
    main()
