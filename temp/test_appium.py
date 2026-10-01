import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from appium import webdriver
from appium.options.android import UiAutomator2Options

# Đảm bảo stdout/stderr dùng UTF-8 kể cả khi bị pipe từ tiến trình khác trên Windows
# (mặc định Windows dùng codepage cp1252, gây UnicodeEncodeError với text tiếng Việt có dấu)
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

TARGET_RESOURCE_ID = "com.shopee.vn.dfpluginshopee7:id/tv_state_btn"
XML_OUTPUT_PATH = Path("ui.xml")
RETRY_ATTEMPTS = 3
RETRY_DELAY_SEC = 0.5


def find_bounds(ui_path: Path, resource_id: str):
    try:
        tree = ET.parse(ui_path)
    except ET.ParseError as pe:
        print("Không thể phân tích UI XML:", pe)
        return []

    found = []
    for elem in tree.getroot().iter():
        if elem.get("resource-id") == resource_id:
            text = elem.get("text") or ""
            bounds = elem.get("bounds") or ""
            found.append((text, bounds))
    return found


def dump_ui_with_retry(driver, xml_path: Path, resource_id: str):
    last_error = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            xml_path.write_text(driver.page_source, encoding="utf-8")
        except Exception as e:
            last_error = e
            print(f"Lần thử {attempt}/{RETRY_ATTEMPTS} lấy page_source thất bại: {e}")
            if attempt < RETRY_ATTEMPTS:
                time.sleep(RETRY_DELAY_SEC)
            continue

        found = find_bounds(xml_path, resource_id)
        if found:
            return found
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_DELAY_SEC)

    if last_error is not None:
        print("Không lấy được UI XML sau các lần thử:", last_error)
    return []


def build_options():
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.automation_name = "UiAutomator2"
    options.device_name = "Android"
    options.new_command_timeout = 60
    options.uiautomator2_server_launch_timeout = 30000
    options.uiautomator2_server_install_timeout = 30000
    return options


def main():
    try:
        driver = webdriver.Remote("http://127.0.0.1:4723", options=build_options())
    except Exception as e:
        print("Không kết nối được Appium server. Kiểm tra Appium đã chạy chưa:")
        print(e)
        return 1

    try:
        found = dump_ui_with_retry(driver, XML_OUTPUT_PATH, TARGET_RESOURCE_ID)
        print("UI XML:", XML_OUTPUT_PATH)

        if not found:
            print(f"Không tìm thấy node với resource-id '{TARGET_RESOURCE_ID}' trong {XML_OUTPUT_PATH}")
            return 1

        for _, bounds in found:
            print(f"bounds={bounds}")
        return 0
    finally:
        driver.quit()


if __name__ == "__main__":
    raise SystemExit(main())
