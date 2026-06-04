import subprocess
import time

import cv2
import numpy as np

CAPTURE_DELAY = 1
CLICK_COOLDOWN = 5

TARGET = (920, 715)
# TARGET = (920, 593)
RADIUS = 5
MIN_ORANGE_PIXELS = 50

LOWER_ORANGE = np.array([2, 90, 140])
UPPER_ORANGE = np.array([8, 255, 255])
KERNEL = np.ones((3, 3), np.uint8)


def adb_tap(x, y):
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)], check=False)

def capture_screen():
    result = subprocess.run(["adb", "exec-out", "screencap", "-p"], capture_output=True, check=False)

    if result.returncode != 0 or not result.stdout:
        return None

    return cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)

def count_orange_near_target(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_ORANGE, UPPER_ORANGE)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, KERNEL)
    mask = cv2.dilate(mask, KERNEL)

    x, y = TARGET
    h, w = mask.shape[:2]

    x1, x2 = max(0, x - RADIUS), min(w, x + RADIUS)
    y1, y2 = max(0, y - RADIUS), min(h, y + RADIUS)

    return int(np.count_nonzero(mask[y1:y2, x1:x2]))

def main():
    last_click = 0
    frame_count = 0

    while True:
        frame = capture_screen()
        if frame is None:
            time.sleep(CAPTURE_DELAY)
            continue

        frame_count += 1
        orange_pixels = count_orange_near_target(frame)

        if frame_count % 30 == 0:
            print(f"Orange pixels: {orange_pixels}")

        if orange_pixels >= MIN_ORANGE_PIXELS:
            now = time.time()

            if now - last_click >= CLICK_COOLDOWN:
                print(f"Click nút Lưu tại: {TARGET}")
                adb_tap(*TARGET)
                last_click = now

        time.sleep(CAPTURE_DELAY)

if __name__ == "__main__":
    main()