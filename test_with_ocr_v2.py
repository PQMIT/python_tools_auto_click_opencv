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

# QUAN TRỌNG: "Lưu" có dấu -> phải dùng gói ngôn ngữ "vie", không phải "eng".
# Tesseract cần có file vie.traineddata trong thư mục tessdata.
# Tải tại: https://github.com/tesseract-ocr/tessdata/blob/main/vie.traineddata
OCR_LANG = "vie+eng"

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Upscale ảnh trước khi OCR (chữ UI trên màn hình điện thoại thường nhỏ,
# Tesseract đọc chữ nhỏ rất kém nếu không phóng to trước).
UPSCALE_FACTOR = 2.0

# Bỏ qua kết quả có độ tin cậy thấp hơn ngưỡng này (0-100)
MIN_CONFIDENCE = 40

# Chế độ chạy liên tục để dò trong lúc livestream đang thay đổi UI
LOOP_MODE = True
LOOP_INTERVAL_SEC = 1.5
MAX_LOOPS = 20          # None = chạy vô hạn tới khi tìm thấy / Ctrl+C
STOP_ON_FOUND = True    # tìm thấy thì tap và dừng luôn

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
    if not result.stdout:
        return None
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
        vie_path = os.path.join(tessdata_dir, "vie.traineddata")
        if not os.path.isfile(vie_path):
            print(f"⚠️  Không thấy vie.traineddata tại {vie_path}")
            print("    Tải về từ: https://github.com/tesseract-ocr/tessdata/raw/main/vie.traineddata")
            print("    rồi copy vào thư mục tessdata ở trên.")

    try:
        pytesseract.get_tesseract_version()
    except Exception:
        print("❌ Tesseract not available. Install it or set TESSERACT_CMD.")
        return False

    return True


def preprocess_for_ocr(frame):
    """Phóng to + tăng tương phản để Tesseract đọc chữ nhỏ trên UI tốt hơn."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    if UPSCALE_FACTOR != 1.0:
        gray = cv2.resize(
            gray, None,
            fx=UPSCALE_FACTOR, fy=UPSCALE_FACTOR,
            interpolation=cv2.INTER_CUBIC
        )

    # Khử nhiễu nhẹ rồi threshold thích ứng để tách chữ khỏi nền UI/video
    gray = cv2.bilateralFilter(gray, 5, 50, 50)
    thresh = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 10
    )
    return thresh


def find_text_boxes(frame):
    """Trả về list (x, y, w, h, text, conf) theo toạ độ gốc của frame (chưa upscale)."""
    processed = preprocess_for_ocr(frame)
    data = pytesseract.image_to_data(
        processed, output_type=pytesseract.Output.DICT, lang=OCR_LANG
    )

    boxes = []
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text:
            continue

        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1

        if conf < MIN_CONFIDENCE:
            continue

        if TARGET_TEXT.lower() not in text.lower():
            continue

        # Quy đổi toạ độ về ảnh gốc (vì đã upscale trước khi OCR)
        x = int(data["left"][i] / UPSCALE_FACTOR)
        y = int(data["top"][i] / UPSCALE_FACTOR)
        w = int(data["width"][i] / UPSCALE_FACTOR)
        h = int(data["height"][i] / UPSCALE_FACTOR)
        boxes.append((x, y, w, h, text, conf))

    return dedupe_boxes(boxes)


def dedupe_boxes(boxes, dist_thresh=20):
    """Gộp các box trùng/gần nhau (OCR đôi khi trả nhiều box cho cùng 1 chữ)."""
    if not boxes:
        return boxes

    boxes = sorted(boxes, key=lambda b: -b[5])  # ưu tiên confidence cao trước
    kept = []
    for b in boxes:
        bx, by = b[0] + b[2] / 2, b[1] + b[3] / 2
        is_dup = False
        for k in kept:
            kx, ky = k[0] + k[2] / 2, k[1] + k[3] / 2
            if abs(bx - kx) < dist_thresh and abs(by - ky) < dist_thresh:
                is_dup = True
                break
        if not is_dup:
            kept.append(b)
    return kept


def save_ocr_debug(frame, boxes):
    os.makedirs(DEBUG_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    vis = frame.copy()
    for (x, y, w, h, text, conf) in boxes:
        cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(vis, f"{text} ({conf:.0f})", (x, max(0, y - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    img_path = os.path.join(DEBUG_DIR, f"ocr_{ts}.png")
    cv2.imwrite(img_path, vis)
    print(f"🖼️ OCR debug image: {img_path}")


def save_crops(frame, boxes):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    h_img, w_img = frame.shape[:2]

    for idx, (x, y, w, h, text, conf) in enumerate(boxes, start=1):
        x1 = max(0, x - PADDING)
        y1 = max(0, y - PADDING)
        x2 = min(w_img, x + w + PADDING)
        y2 = min(h_img, y + h + PADDING)

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            continue

        out_path = os.path.join(OUTPUT_DIR, f"luu_{ts}_{idx}.png")
        cv2.imwrite(out_path, crop)
        print(f"✅ Found '{text}' (conf={conf:.0f}) at ({x}, {y}, {w}, {h}) -> {out_path}")


def tap(x, y):
    print(f"👆 Tapping at ({x}, {y})")
    subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)])


def tap_box(box):
    x, y, w, h, text, conf = box
    cx = x + w // 2
    cy = y + h // 2
    tap(cx, cy)


def run_once():
    frame = screencap()
    if frame is None:
        print("❌ No frame from adb screencap")
        return None, []

    boxes = find_text_boxes(frame)

    if not boxes:
        print("❌ No 'Lưu' text found this frame")
        # if DEBUG:
        #     save_ocr_debug(frame, boxes)
        # return frame, []

    save_crops(frame, boxes)
    if DEBUG:
        save_ocr_debug(frame, boxes)

    return frame, boxes


def main():
    if not ensure_tesseract():
        return

    if not LOOP_MODE:
        _, boxes = run_once()
        if boxes:
            tap_box(boxes[0])
        return

    loop_count = 0
    while True:
        loop_count += 1
        print(f"\n--- Attempt {loop_count} ---")
        _, boxes = run_once()

        if boxes:
            if STOP_ON_FOUND:
                tap_box(boxes[0])
                print("✅ Done.")
                break

        if MAX_LOOPS is not None and loop_count >= MAX_LOOPS:
            print("⏹️  Reached MAX_LOOPS, dừng lại chưa tìm thấy.")
            break

        time.sleep(LOOP_INTERVAL_SEC)


if __name__ == "__main__":
    main()