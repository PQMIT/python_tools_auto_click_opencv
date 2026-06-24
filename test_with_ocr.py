import subprocess
import cv2
import numpy as np
import os
import time

try:
    import pytesseract
except ImportError:
    pytesseract = None

# ================= CONFIG =================
TARGET_TEXT = "Lưu"
OCR_LANG = "eng"

# Optional: set to your Tesseract install path if it's not in PATH.
# Example: r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
TESSERACT_CMD = r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

OUTPUT_DIR = "found_buttons"
PADDING = 8
DEBUG = True
DEBUG_DIR = "ocr_debug"

# ==========================================
def screencap():
    result = subprocess.run(
        ["adb", "exec-out", "screencap", "-p"],
        capture_output=True
    )
    img = cv2.imdecode(np.frombuffer(result.stdout, np.uint8), cv2.IMREAD_COLOR)
    return img


def ensure_tesseract():
    if pytesseract is None:
        print("❌ pytesseract not installed. pip install pytesseract")
        return False

    if TESSERACT_CMD:
        if os.path.isfile(TESSERACT_CMD):
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        else:
            print("❌ Tesseract path not found. Update TESSERACT_CMD.")
            return False

    tessdata_dir = os.path.join(os.path.dirname(TESSERACT_CMD), "tessdata")
    if os.path.isdir(tessdata_dir):
        os.environ.setdefault("TESSDATA_PREFIX", tessdata_dir)

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        print("❌ Tesseract not available. Install it or set TESSERACT_CMD.")
        return False

    return True


def find_text_boxes(frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT, lang=OCR_LANG)

    boxes = []
    for i, text in enumerate(data["text"]):
        if not text:
            continue
        if TARGET_TEXT.lower() in text.lower():
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            boxes.append((x, y, w, h, text))

    return boxes


def save_ocr_debug(frame, data):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    txt_path = os.path.join(DEBUG_DIR, f"ocr_{ts}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        for i, text in enumerate(data["text"]):
            if not text:
                continue
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            f.write(f"{text}\t({x},{y},{w},{h})\n")

    vis = frame.copy()
    for i, text in enumerate(data["text"]):
        if not text:
            continue
        x = int(data["left"][i])
        y = int(data["top"][i])
        w = int(data["width"][i])
        h = int(data["height"][i])
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 1)

    img_path = os.path.join(DEBUG_DIR, f"ocr_{ts}.png")
    cv2.imwrite(img_path, vis)
    print(f"🧾 OCR debug saved: {txt_path}")
    print(f"🖼️ OCR debug image: {img_path}")


def save_crops(frame, boxes):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    h_img, w_img = frame.shape[:2]

    for idx, (x, y, w, h, text) in enumerate(boxes, start=1):
        x1 = max(0, x - PADDING)
        y1 = max(0, y - PADDING)
        x2 = min(w_img, x + w + PADDING)
        y2 = min(h_img, y + h + PADDING)

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        out_path = os.path.join(OUTPUT_DIR, f"luu_{ts}_{idx}.png")
        cv2.imwrite(out_path, crop)
        print(f"✅ Found '{text}' at ({x}, {y}, {w}, {h}) -> {out_path}")


def main():
    if not ensure_tesseract():
        return

    frame = screencap()
    if frame is None:
        print("❌ No frame from adb screencap")
        return

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT, lang=OCR_LANG)
    boxes = []
    for i, text in enumerate(data["text"]):
        if not text:
            continue
        if TARGET_TEXT.lower() in text.lower():
            x = int(data["left"][i])
            y = int(data["top"][i])
            w = int(data["width"][i])
            h = int(data["height"][i])
            boxes.append((x, y, w, h, text))
    if not boxes:
        print("❌ No 'Lưu' text found")
        if DEBUG:
            save_ocr_debug(frame, data)
        return

    save_crops(frame, boxes)


if __name__ == "__main__":
    main()