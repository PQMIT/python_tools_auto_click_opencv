import subprocess
import time

import cv2
import numpy as np


CAPTURE_DELAY_SEC = 1
CLICK_COOLDOWN_SEC = 5
SAVE_DEBUG_IMAGE = True
DEBUG_IMAGE_PATH = "last_click.png"

CLICK_TARGET_X = 915
CLICK_TARGET_Y = 590
# CLICK_TARGET_Y = 730
TARGET_REGION_RADIUS = 5
MIN_ORANGE_PIXELS_IN_REGION = 50

LOWER_ORANGE = np.array([2, 90, 140])
UPPER_ORANGE = np.array([8, 255, 255])
MORPH_KERNEL = np.ones((3, 3), np.uint8)

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

    frame = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        return None

    return frame

# tìm nút Lưu bằng cách phân tích màu sắc trong khu vực mục tiêu
def find_save_button(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_ORANGE, UPPER_ORANGE)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, MORPH_KERNEL, iterations=1)
    mask = cv2.dilate(mask, MORPH_KERNEL, iterations=1)

    height, width = mask.shape[:2]
    x1 = max(0, CLICK_TARGET_X - TARGET_REGION_RADIUS)
    x2 = min(width, CLICK_TARGET_X + TARGET_REGION_RADIUS)
    y1 = max(0, CLICK_TARGET_Y - TARGET_REGION_RADIUS)
    y2 = min(height, CLICK_TARGET_Y + TARGET_REGION_RADIUS)

    region_mask = mask[y1:y2, x1:x2]
    orange_pixels = int(np.count_nonzero(region_mask))

    if orange_pixels >= MIN_ORANGE_PIXELS_IN_REGION:
        return (CLICK_TARGET_X, CLICK_TARGET_Y), orange_pixels
    else:
        return None, orange_pixels


def main():
    last_click_at = 0.0
    frame_count = 0

    while True:
        frame = capture_screen()
        if frame is None:
            time.sleep(CAPTURE_DELAY_SEC)
            continue

        frame_count += 1
        center, orange_pixels = find_save_button(frame)

        if frame_count % 30 == 0:
            print(f"Orange pixels (region): {orange_pixels}")

        if center is not None:
            cx, cy = center
            now = time.time()
            if now - last_click_at >= CLICK_COOLDOWN_SEC:
                print(f"Click nut Luu tai: {cx}, {cy}")
                adb_tap(cx, cy)
                last_click_at = now

                if SAVE_DEBUG_IMAGE:
                    overlay = frame.copy()
                    cv2.circle(overlay, (cx, cy), 18, (0, 255, 255), 3)
                    cv2.imwrite(DEBUG_IMAGE_PATH, overlay)
                    print(f"Da luu anh kiem tra tai: {DEBUG_IMAGE_PATH}")

        time.sleep(CAPTURE_DELAY_SEC)


if __name__ == "__main__":
    main()