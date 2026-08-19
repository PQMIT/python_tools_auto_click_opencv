import random
import subprocess
import time

import cv2
import numpy as np
from pathlib import Path

from dump_ui_xml import dump_ui_xml, find_node_by_resource_id, parse_bounds
import xml.etree.ElementTree as ET

CAPTURE_DELAY_SEC = 15
CLICK_COOLDOWN_SEC = 15
CLICK_DELAY_MIN_SEC = 4.0  # chờ tối thiểu sau khi click, tránh bị phát hiện là bot
CLICK_DELAY_MAX_SEC = 9.0  # chờ tối đa sau khi click
SAVE_DEBUG_IMAGE = True
DEBUG_IMAGE_PATH = "last_click.png"

TARGET_RESOURCE_ID = "com.shopee.vn.dfpluginshopee7:id/tv_state_btn"

CLICK_TARGETS = [
    # (915, 460),
    # (915, 510),
    # (915, 610),
    # (915, 635),
    # (915, 735),
    # (915, 860),
]
TARGET_REGION_RADIUS = 30
MIN_ORANGE_PIXELS_IN_REGION = 50
MAX_CENTROID_DISTANCE = 20  # centroid phải cách target tối đa 20px

LOWER_ORANGE = np.array([5, 63, 153])
UPPER_ORANGE = np.array([14, 255, 255])
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
def find_save_button(frame, target_x, target_y):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_ORANGE, UPPER_ORANGE)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, MORPH_KERNEL, iterations=1)
    mask = cv2.dilate(mask, MORPH_KERNEL, iterations=1)

    height, width = mask.shape[:2]
    x1 = max(0, target_x - TARGET_REGION_RADIUS)
    x2 = min(width, target_x + TARGET_REGION_RADIUS)
    y1 = max(0, target_y - TARGET_REGION_RADIUS)
    y2 = min(height, target_y + TARGET_REGION_RADIUS)

    region_mask = mask[y1:y2, x1:x2]
    orange_pixels = int(np.count_nonzero(region_mask))

    cy_idx = min(target_y, height - 1)
    cx_idx = min(target_x, width - 1)
    actual_hsv = hsv[cy_idx, cx_idx].tolist()

    if orange_pixels < MIN_ORANGE_PIXELS_IN_REGION:
        return None, orange_pixels, actual_hsv

    # tính centroid của các pixel cam trong vùng
    ys, xs = np.where(region_mask > 0)
    centroid_x = int(xs.mean()) + x1
    centroid_y = int(ys.mean()) + y1
    dist = np.hypot(centroid_x - target_x, centroid_y - target_y)

    if dist <= MAX_CENTROID_DISTANCE:
        return (target_x, target_y), orange_pixels, actual_hsv
    else:
        print(f"  Reject ({target_x},{target_y}): centroid cam tại ({centroid_x},{centroid_y}), cách target {dist:.1f}px > {MAX_CENTROID_DISTANCE}px")
        return None, orange_pixels, actual_hsv


# lấy toạ độ nút từ XML dump (uiautomator) theo resource-id
def get_xml_target():
    xml_path = dump_ui_xml()
    if xml_path is None:
        return None
    return find_node_by_resource_id(xml_path, TARGET_RESOURCE_ID)

def get_xml_target_2():
    # Run test_appium.py to generate ui.xml, then parse it.
    ui_path = Path("ui.xml")

    try:
        print("Running test_appium.py to generate ui.xml...")
        proc = subprocess.run(
            ["py", "test_appium.py"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
        if proc.returncode != 0:
            print("test_appium.py exited with code", proc.returncode)
            print(proc.stdout)
            print(proc.stderr)
        else:
            # print minimal output from test_appium.py for visibility
            out = (proc.stdout or "").strip()
            if out:
                print(out.splitlines()[-5:])
    except Exception as e:
        print("Không thể chạy test_appium.py:", e)

    # If ui.xml exists now, parse it and return center coords
    if ui_path.exists():
        try:
            tree = ET.parse(str(ui_path))
            root = tree.getroot()
            for elem in root.iter():
                rid = elem.get('resource-id')
                if rid == TARGET_RESOURCE_ID:
                    bounds = parse_bounds(elem.get('bounds', ''))
                    if bounds:
                        _, _, _, _, cx, cy = bounds
                        return cx, cy
        except Exception as e:
            print("Lỗi khi phân tích ui.xml:", e)

    # Fallback to performing an ADB dump if ui.xml not present or parse failed
    xml_path = dump_ui_xml()
    if xml_path is None:
        return None
    return find_node_by_resource_id(xml_path, TARGET_RESOURCE_ID)

def main():
    last_click_at = 0.0
    frame_count = 0

    print(f"[START] Auto-click đang chạy | Targets: {CLICK_TARGETS} | Delay: {CAPTURE_DELAY_SEC}s")

    while True:
        frame = capture_screen()
        if frame is None:
            print("[WARN] Không chụp được màn hình (ADB lỗi?), thử lại sau...")
            time.sleep(CAPTURE_DELAY_SEC)
            continue

        candidates = []
        # xml_target = get_xml_target()
        xml_target = get_xml_target_2()
        print(f"xml_target: {xml_target}")

        if xml_target is not None:
            candidates.append(xml_target)
        candidates.extend(CLICK_TARGETS)

        frame_count += 1
        # print(f"[Frame {frame_count}] Đang quét {len(candidates)} vị trí...")
        print(f".")

        # thực hiện click vào nút Lưu đã tìm thấy theo khoảng thời gian không cố định tránh bị phát hiện
        # sau khi thực hiện click xong thì lưu lại ảnh màn hình để kiểm tra
        # found_center = candidates[0] if candidates else None

        found_center = None
        found_pixels = 0
        found_hsv = None
        if candidates:
            tx, ty = candidates[0]
            center, orange_pixels, actual_hsv = find_save_button(frame, tx, ty)
            if orange_pixels > 0:
                print(f"  ({tx},{ty})| Orange pixels: {orange_pixels}| HSV: {actual_hsv}")
            if center is not None:
                found_center = center
                found_pixels = orange_pixels
                found_hsv = actual_hsv

        if found_center is not None:
            cx, cy = found_center
            now = time.time()
            if now - last_click_at >= CLICK_COOLDOWN_SEC:
                print(f"Click nút Lưu tại: ({cx}, {cy})")
                adb_tap(cx, cy)
                last_click_at = now

                delay = random.uniform(CLICK_DELAY_MIN_SEC, CLICK_DELAY_MAX_SEC)
                print(f"Đã click, chờ {delay:.1f} giây trước khi tiếp tục...")
                time.sleep(delay)

                if SAVE_DEBUG_IMAGE:
                    frame = capture_screen()
                    if frame is not None:
                        overlay = frame.copy()
                        cv2.circle(overlay, (cx, cy), 18, (0, 255, 255), 3)
                        cv2.imwrite(DEBUG_IMAGE_PATH, overlay)
                        print(f"Đã lưu ảnh kiểm tra tại: {DEBUG_IMAGE_PATH}")

        time.sleep(CAPTURE_DELAY_SEC)

if __name__ == "__main__":
    main()