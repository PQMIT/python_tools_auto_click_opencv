import subprocess
import cv2
import numpy as np
import time
import threading

try:
    import pytesseract
except ImportError:
    pytesseract = None
try:
    import easyocr
except ImportError:
    easyocr = None

MAX_SIZE = 1024
TARGET_TEXT = "OK"  # doi thanh text ban can click
TESSERACT_CMD = None  # vi du: r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe"
SCRCPY_PATH = r"C:\\scrcpy-win64-v3.3.4\\scrcpy.exe"
MODE = "color"  # "color" hoac "ocr"
CLICK_COOLDOWN_SEC = 1.0
DEBUG_VIEW = False
DEBUG_LOG_EVERY = 30
CAPTURE_MODE = "screencap"  # "screencap", "adb", hoac "scrcpy"
CALIBRATION_TAP = True
CALIBRATION_OUTPUT = "last_click.png"

# ROI tuong doi (top-right), giam nhieu va tap trung nut Luu
ROI_X_MIN = 0.78
ROI_X_MAX = 0.95
ROI_Y_MIN = 0.16
ROI_Y_MAX = 0.36

SCRCPY_MAX_FPS = 60
SCRCPY_VIDEO_BIT_RATE = "4M"
ADB_VIDEO_BIT_RATE = "4M"

# Orange range (tinh tu button_click.png)
LOWER_ORANGE = np.array([2, 90, 140])
UPPER_ORANGE = np.array([8, 255, 255])
MIN_ORANGE_AREA = 60
MORPH_KERNEL = np.ones((3, 3), np.uint8)


def adb_tap(x, y):
    subprocess.run(f"adb shell input tap {x} {y}", shell=True, check=False)


def get_device_size():
    result = subprocess.run(
        "adb shell wm size",
        shell=True,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        for line in result.stdout.splitlines():
            if "Physical size" in line:
                size_str = line.split(":", 1)[1].strip()
                w_str, h_str = size_str.split("x")
                return int(w_str), int(h_str)
    return 1080, 1920


def make_even(value):
    return value if value % 2 == 0 else value - 1


def calc_stream_size(dev_w, dev_h, max_size):
    longest = max(dev_w, dev_h)
    scale = min(max_size / longest, 1.0)
    stream_w = make_even(int(dev_w * scale))
    stream_h = make_even(int(dev_h * scale))
    return stream_w, stream_h, scale


def read_exact(pipe, size):
    data = bytearray()
    while len(data) < size:
        chunk = pipe.read(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


def pump_scrcpy_to_ffmpeg(scrcpy_stdout, ffmpeg_stdin):
    ebml = b"\x1a\x45\xdf\xa3"
    buffer = b""
    started = False
    max_buffer = 8192

    while True:
        chunk = scrcpy_stdout.read(4096)
        if not chunk:
            break

        if not started:
            buffer += chunk
            if len(buffer) > max_buffer:
                buffer = buffer[-max_buffer:]

            idx = buffer.find(ebml)
            if idx == -1:
                continue

            probe = buffer[idx: idx + 512]
            if b"matroska" not in probe and b"webm" not in probe:
                buffer = buffer[idx + 4:]
                continue

            started = True
            ffmpeg_stdin.write(buffer[idx:])
            ffmpeg_stdin.flush()
            buffer = b""
            continue

        ffmpeg_stdin.write(chunk)
        ffmpeg_stdin.flush()

    try:
        ffmpeg_stdin.close()
    except Exception:
        pass


def pump_h264_to_ffmpeg(adb_stdout, ffmpeg_stdin):
    start_codes = [b"\x00\x00\x00\x01", b"\x00\x00\x01"]
    buffer = b""
    started = False
    max_buffer = 4096

    while True:
        chunk = adb_stdout.read(4096)
        if not chunk:
            break

        if not started:
            buffer += chunk
            if len(buffer) > max_buffer:
                buffer = buffer[-max_buffer:]

            idx = -1
            for sc in start_codes:
                pos = buffer.find(sc)
                if pos != -1:
                    idx = pos
                    break

            if idx == -1:
                continue

            started = True
            ffmpeg_stdin.write(buffer[idx:])
            ffmpeg_stdin.flush()
            buffer = b""
            continue

        ffmpeg_stdin.write(chunk)
        ffmpeg_stdin.flush()

    try:
        ffmpeg_stdin.close()
    except Exception:
        pass


def drain_stderr(pipe, prefix):
    for line in iter(pipe.readline, b""):
        msg = line.decode(errors="ignore").rstrip()
        if msg:
            print(f"{prefix}{msg}")


def init_ocr():
    if pytesseract:
        if TESSERACT_CMD:
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        return "tesseract", None
    if easyocr:
        return "easyocr", easyocr.Reader(["en"], gpu=False)
    return "none", None


def find_text_center(frame, target_text, ocr_backend, ocr_reader):
    if ocr_backend == "tesseract":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

        for i, text in enumerate(data.get("text", [])):
            if target_text.lower() in text.lower():
                x = data["left"][i]
                y = data["top"][i]
                w = data["width"][i]
                h = data["height"][i]
                cx = x + w // 2
                cy = y + h // 2
                return cx, cy
        return None

    if ocr_backend == "easyocr":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        results = ocr_reader.readtext(gray)
        for box, text, _ in results:
            if target_text.lower() in text.lower():
                xs = [point[0] for point in box]
                ys = [point[1] for point in box]
                cx = int(sum(xs) / len(xs))
                cy = int(sum(ys) / len(ys))
                return cx, cy
        return None

    return None


dev_w, dev_h = get_device_size()
stream_w, stream_h, scale = calc_stream_size(dev_w, dev_h, MAX_SIZE)
ocr_backend, ocr_reader = init_ocr()

if CAPTURE_MODE == "screencap":
    ffmpeg_proc = None
elif CAPTURE_MODE == "adb":
    adb_cmd = [
        "adb",
        "exec-out",
        "screenrecord",
        "--output-format=h264",
        "--bit-rate",
        ADB_VIDEO_BIT_RATE,
        "--size",
        f"{stream_w}x{stream_h}",
        "-",
    ]

    ffmpeg_cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-f",
        "h264",
        "-i",
        "pipe:0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "pipe:1",
    ]

    adb_proc = subprocess.Popen(
        adb_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ffmpeg_proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    pump_thread = threading.Thread(
        target=pump_h264_to_ffmpeg,
        args=(adb_proc.stdout, ffmpeg_proc.stdin),
        daemon=True,
    )
    pump_thread.start()

    stderr_thread = threading.Thread(
        target=drain_stderr,
        args=(adb_proc.stderr, "[adb] "),
        daemon=True,
    )
    stderr_thread.start()
else:
    scrcpy_cmd = [
        SCRCPY_PATH,
        "--verbosity=error",
        "--record=-",
        "--record-format=mkv",
        "--max-size",
        str(MAX_SIZE),
        "--max-fps",
        str(SCRCPY_MAX_FPS),
        "--video-bit-rate",
        SCRCPY_VIDEO_BIT_RATE,
        "--no-audio",
    ]

    ffmpeg_cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-f",
        "matroska",
        "-i",
        "pipe:0",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "pipe:1",
    ]

    scrcpy_proc = subprocess.Popen(
        scrcpy_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    ffmpeg_proc = subprocess.Popen(
        ffmpeg_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )

    pump_thread = threading.Thread(
        target=pump_scrcpy_to_ffmpeg,
        args=(scrcpy_proc.stdout, ffmpeg_proc.stdin),
        daemon=True,
    )
    pump_thread.start()

    stderr_thread = threading.Thread(
        target=drain_stderr,
        args=(scrcpy_proc.stderr, "[scrcpy] "),
        daemon=True,
    )
    stderr_thread.start()

frame_size = stream_w * stream_h * 3
last_click_at = 0.0
frame_index = 0
did_calibration = False

while True:
    if CAPTURE_MODE == "screencap":
        result = subprocess.run(
            ["adb", "exec-out", "screencap", "-p"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0 or not result.stdout:
            time.sleep(0.2)
            continue

        np_arr = np.frombuffer(result.stdout, np.uint8)
        frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if frame is None:
            time.sleep(0.2)
            continue

        if frame.shape[1] != stream_w or frame.shape[0] != stream_h:
            frame = cv2.resize(frame, (stream_w, stream_h), interpolation=cv2.INTER_AREA)
    else:
        raw = read_exact(ffmpeg_proc.stdout, frame_size)
        if raw is None:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).reshape((stream_h, stream_w, 3))

    frame_index += 1

    # OCR: tim text can click
    if MODE == "ocr" and ocr_backend != "none":
        center = find_text_center(frame, TARGET_TEXT, ocr_backend, ocr_reader)
        if center:
            cx, cy = center
            tap_x = int(cx / scale)
            tap_y = int(cy / scale)

            now = time.time()
            if now - last_click_at >= CLICK_COOLDOWN_SEC:
                print(f"Click text '{TARGET_TEXT}' tai: {tap_x}, {tap_y}")
                adb_tap(tap_x, tap_y)
                last_click_at = now
            continue
    # Detect mau cam de click nut Luu
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, LOWER_ORANGE, UPPER_ORANGE)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, MORPH_KERNEL, iterations=1)
    mask = cv2.dilate(mask, MORPH_KERNEL, iterations=1)

    h, w = mask.shape[:2]
    x1 = int(w * ROI_X_MIN)
    x2 = int(w * ROI_X_MAX)
    y1 = int(h * ROI_Y_MIN)
    y2 = int(h * ROI_Y_MAX)
    roi_mask = np.zeros_like(mask)
    roi_mask[y1:y2, x1:x2] = mask[y1:y2, x1:x2]

    if DEBUG_VIEW:
        pass

    if frame_index % DEBUG_LOG_EVERY == 0:
        print(
            f"Orange pixels (roi): {int(np.count_nonzero(roi_mask))} "
            f"ROI=({x1},{y1})-({x2},{y2})"
        )

    if CAPTURE_MODE == "screencap":
        time.sleep(0.2)

    contours, _ = cv2.findContours(roi_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        cnt = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        if area >= MIN_ORANGE_AREA:
            x, y, w, h = cv2.boundingRect(cnt)
            cx = x + w // 2
            cy = y + h // 2
            tap_x = int(cx / scale)
            tap_y = int(cy / scale)

            now = time.time()
            if now - last_click_at >= CLICK_COOLDOWN_SEC:
                print(f"Click nut Luu tai: {tap_x}, {tap_y}")
                adb_tap(tap_x, tap_y)
                last_click_at = now
                if CALIBRATION_TAP and not did_calibration:
                    overlay = frame.copy()
                    cv2.circle(overlay, (cx, cy), 18, (0, 255, 255), 3)
                    cv2.imwrite(CALIBRATION_OUTPUT, overlay)
                    print(f"Da luu anh kiem tra tai: {CALIBRATION_OUTPUT}")
                    did_calibration = True