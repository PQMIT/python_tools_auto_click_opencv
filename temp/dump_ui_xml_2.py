import subprocess
import os
import time
import shutil
import argparse
from datetime import datetime
from pathlib import Path


SNAPSHOT_DIR = Path("snapshots")


def run_adb(args, device_id=None, timeout=10):
    """
    Chạy lệnh adb và trả về CompletedProcess.
    """

    cmd = ["adb"]

    if device_id:
        cmd += ["-s", device_id]

    cmd += args

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

        return result

    except subprocess.TimeoutExpired:
        print(f"[ADB] Timeout: {' '.join(cmd)}")
        return None


def get_device_list():
    """
    Lấy danh sách Android device đang kết nối.
    """

    result = run_adb(["devices"])

    if result is None:
        return []

    devices = []

    output = result.stdout.decode("utf-8", errors="ignore")

    for line in output.splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("List of devices"):
            continue

        parts = line.split()

        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])

    return devices


def capture_screen(output_file, device_id=None):
    """
    Chụp screenshot từ Android.
    """

    result = run_adb(
        ["exec-out", "screencap", "-p"],
        device_id=device_id,
        timeout=10,
    )

    if result is None:
        return False, "ADB timeout"

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="ignore")
        return False, error

    if not result.stdout:
        return False, "Không nhận được dữ liệu screenshot"

    try:
        with open(output_file, "wb") as f:
            f.write(result.stdout)

        return True, None

    except Exception as e:
        return False, str(e)


def dump_uiautomator(output_file, device_id=None):
    """
    Dump UI hierarchy bằng UiAutomator.

    Nếu UI đang không idle thì hàm có thể fail.
    """

    remote_xml = "/sdcard/ui_snapshot.xml"

    # Dump XML trên điện thoại
    result = run_adb(
        [
            "shell",
            "uiautomator",
            "dump",
            "--compressed",
            remote_xml,
        ],
        device_id=device_id,
        timeout=15,
    )

    if result is None:
        return False, "UiAutomator timeout"

    stdout = result.stdout.decode("utf-8", errors="ignore")
    stderr = result.stderr.decode("utf-8", errors="ignore")

    if result.returncode != 0:
        error = stderr or stdout
        return False, error.strip()

    # Pull XML về máy
    result = run_adb(
        [
            "pull",
            remote_xml,
            str(output_file),
        ],
        device_id=device_id,
        timeout=15,
    )

    if result is None:
        return False, "ADB pull timeout"

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="ignore")
        return False, error.strip()

    if not os.path.exists(output_file):
        return False, "Không tìm thấy file XML sau khi pull"

    return True, None


def save_meta(output_file, data):
    """
    Lưu metadata của snapshot.
    """

    with open(output_file, "w", encoding="utf-8") as f:
        for key, value in data.items():
            f.write(f"{key}: {value}\n")


def snapshot(device_id=None):
    """
    Chụp một UI snapshot.

    Bao gồm:
        - screen.png
        - ui.xml nếu UiAutomator thành công
        - meta.txt

    Trả về đường dẫn thư mục snapshot.
    """

    # Timestamp có millisecond
    now = datetime.now()

    timestamp = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]

    snapshot_path = SNAPSHOT_DIR / timestamp
    snapshot_path.mkdir(parents=True, exist_ok=True)

    screen_file = snapshot_path / "screen.png"
    xml_file = snapshot_path / "ui.xml"
    meta_file = snapshot_path / "meta.txt"

    print()
    print("=" * 60)
    print(f"SNAPSHOT: {timestamp}")
    print("=" * 60)

    # ---------------------------------------------------------
    # 1. Screenshot
    # ---------------------------------------------------------

    print("[1/2] Capturing screenshot...")

    screen_ok, screen_error = capture_screen(
        screen_file,
        device_id=device_id,
    )

    if screen_ok:
        print(f"      OK -> {screen_file}")
    else:
        print(f"      FAILED -> {screen_error}")

    # ---------------------------------------------------------
    # 2. UIAutomator XML
    # ---------------------------------------------------------

    print("[2/2] Dumping UI hierarchy...")

    xml_ok, xml_error = dump_uiautomator(
        xml_file,
        device_id=device_id,
    )

    if xml_ok:
        print(f"      OK -> {xml_file}")
    else:
        print(f"      FAILED -> {xml_error}")

    # ---------------------------------------------------------
    # 3. Metadata
    # ---------------------------------------------------------

    meta = {
        "timestamp": now.isoformat(),
        "device_id": device_id or "default",
        "screen": str(screen_file) if screen_ok else "FAILED",
        "ui_xml": str(xml_file) if xml_ok else "FAILED",
        "ui_xml_error": xml_error if not xml_ok else "",
    }

    save_meta(meta_file, meta)

    print(f"      META -> {meta_file}")

    print("=" * 60)

    return snapshot_path


def snapshot_from_local_ui(ui_path):
    """
    Tạo snapshot từ file UI XML có sẵn (sinh bởi test_appium.py).

    - Sao chép file XML vào thư mục snapshot
    - Tạo meta.txt
    """
    if not os.path.exists(ui_path):
        print(f"Không tìm thấy file UI XML: {ui_path}")
        return None

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S_%f")[:-3]

    snapshot_path = SNAPSHOT_DIR / timestamp
    snapshot_path.mkdir(parents=True, exist_ok=True)

    xml_file = snapshot_path / "ui.xml"
    try:
        shutil.copyfile(ui_path, xml_file)
        print(f"Copied UI XML -> {xml_file}")
    except Exception as e:
        print("Không thể sao chép UI XML:", e)
        return None

    # Nếu có screen.png trong cwd, copy vào snapshot
    src_screen = Path("screen.png")
    if src_screen.exists():
        try:
            shutil.copyfile(src_screen, snapshot_path / "screen.png")
            screen_ok = True
        except Exception:
            screen_ok = False
    else:
        screen_ok = False

    meta = {
        "timestamp": now.isoformat(),
        "device_id": "local-file",
        "screen": str(snapshot_path / "screen.png") if screen_ok else "NOT_PROVIDED",
        "ui_xml": str(xml_file),
        "ui_xml_error": "",
    }

    save_meta(snapshot_path / "meta.txt", meta)

    print(f"Snapshot saved at: {snapshot_path}")
    return snapshot_path


def main():
    parser = argparse.ArgumentParser(description="Dump UI XML via ADB or use existing ui.xml to create snapshot")
    parser.add_argument("--from-ui", dest="ui_path", help="Path to existing ui.xml to import into a snapshot")
    args = parser.parse_args()

    # if args.ui_path:
    #     # Use local UI XML file to create snapshot
    #     snapshot_path = snapshot_from_local_ui(args.ui_path)
    #     if not snapshot_path:
    #         print("Tạo snapshot từ file UI thất bại.")
    #     return

    # ---------------------------------------------------------
    # Kiểm tra device (ADB mode)
    # ---------------------------------------------------------

    devices = get_device_list()

    if not devices:
        print("Không tìm thấy Android device.")
        print()
        print("Hãy kiểm tra:")
        print("  adb devices")
        return

    print("Android devices:")

    for i, device in enumerate(devices):
        print(f"  [{i}] {device}")

    # Nếu chỉ có 1 device thì tự chọn
    if len(devices) == 1:
        device_id = devices[0]

    else:
        try:
            index = int(input("Chọn device: "))
            device_id = devices[index]
        except (ValueError, IndexError):
            print("Device không hợp lệ.")
            return

    print()
    print(f"Using device: {device_id}")

    # ---------------------------------------------------------
    # Snapshot
    # ---------------------------------------------------------

    path = snapshot(device_id)

    print()
    print(f"Snapshot saved at:")
    print(path)


if __name__ == "__main__":
    main()