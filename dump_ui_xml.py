import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom

DEVICE_XML_PATH = "/sdcard/ui_dump.xml"
LOCAL_XML_PATH = "ui_dump.xml"
ADB_TIMEOUT = 15


def dump_ui_xml(max_retries=3):
    """Yêu cầu thiết bị chụp lại UI hierarchy hiện tại thành XML rồi kéo file về máy.

    Xoá file cũ (trên máy tính và trên thiết bị) trước khi dump, rồi xác minh
    file mới thực sự được tạo và là XML hợp lệ trước khi trả về, để tránh
    trường hợp đọc nhầm file XML cũ còn sót lại.
    """
    if os.path.exists(LOCAL_XML_PATH):
        os.remove(LOCAL_XML_PATH)

    for attempt in range(1, max_retries + 1):
        subprocess.run(
            ["adb", "shell", "rm", "-f", DEVICE_XML_PATH],
            check=False,
            capture_output=True,
            text=True,
            timeout=ADB_TIMEOUT,
        )

        try:
            result = subprocess.run(
                ["adb", "shell", "uiautomator", "dump", DEVICE_XML_PATH],
                check=False,
                capture_output=True,
                text=True,
                timeout=ADB_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            print(f"[WARN] (lần {attempt}) uiautomator dump quá thời gian chờ, thử lại...")
            continue

        output = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0 or "error" in output.lower():
            print(f"[WARN] (lần {attempt}) uiautomator dump thất bại: {output.strip()}")
            time.sleep(1)
            continue

        try:
            pull = subprocess.run(
                ["adb", "pull", DEVICE_XML_PATH, LOCAL_XML_PATH],
                check=False,
                capture_output=True,
                text=True,
                timeout=ADB_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            print(f"[WARN] (lần {attempt}) adb pull quá thời gian chờ, thử lại...")
            continue

        if pull.returncode != 0 or not os.path.exists(LOCAL_XML_PATH):
            print(f"[WARN] (lần {attempt}) Không kéo được file XML về: {pull.stderr.strip()}")
            time.sleep(1)
            continue

        if os.path.getsize(LOCAL_XML_PATH) == 0:
            print(f"[WARN] (lần {attempt}) File XML kéo về bị rỗng, thử lại...")
            continue

        try:
            ET.parse(LOCAL_XML_PATH)
        except ET.ParseError as e:
            print(f"[WARN] (lần {attempt}) File XML không hợp lệ ({e}), thử lại...")
            continue

        return LOCAL_XML_PATH

    print(f"[ERROR] Không tạo được file UI XML mới sau {max_retries} lần thử.")
    return None


def parse_bounds(bounds_str):
    """'[x1,y1][x2,y2]' -> (x1, y1, x2, y2, center_x, center_y)"""
    try:
        left, rest = bounds_str.split("][")
        x1, y1 = map(int, left.strip("[]").split(","))
        x2, y2 = map(int, rest.strip("[]").split(","))
        return x1, y1, x2, y2, (x1 + x2) // 2, (y1 + y2) // 2
    except (ValueError, AttributeError):
        return None


def print_pretty_xml(xml_path):
    with open(xml_path, "r", encoding="utf-8") as f:
        raw = f.read()
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    print(pretty)


def print_clickable_nodes(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    print("\n=== Các node có thể click (clickable=true hoặc có text/resource-id) ===")
    for node in root.iter("node"):
        attrib = node.attrib
        clickable = attrib.get("clickable") == "true"
        text = attrib.get("text", "")
        resource_id = attrib.get("resource-id", "")
        desc = attrib.get("content-desc", "")

        if not (clickable or text or resource_id or desc):
            continue

        bounds = parse_bounds(attrib.get("bounds", ""))
        if bounds is None:
            continue
        x1, y1, x2, y2, cx, cy = bounds

        print(
            f"  click=({cx},{cy}) bounds=[{x1},{y1}][{x2},{y2}] "
            f"clickable={clickable} text='{text}' id='{resource_id}' desc='{desc}'"
        )

def find_node_by_resource_id(xml_path, target_resource_id):
    tree = ET.parse(xml_path)
    root = tree.getroot()

    for node in root.iter("node"):
        attrib = node.attrib
        resource_id = attrib.get("resource-id", "")

        if resource_id != target_resource_id:
            continue

        bounds = parse_bounds(attrib.get("bounds", ""))
        if bounds is None:
            continue

        x1, y1, x2, y2, cx, cy = bounds

        print(
            f"Found:"
            f"bounds=[{x1},{y1}][{x2},{y2}] "
            f"center=({cx},{cy})"
            f"resource-id='{resource_id}'"
        )

        return cx, cy

    print(f"Không tìm thấy resource-id: {target_resource_id}")
    return None

def main():
    xml_path = dump_ui_xml()
    if xml_path is None:
        sys.exit(1)

    # print_pretty_xml(xml_path)
    # print_clickable_nodes(xml_path)

    target_id = "com.shopee.vn.dfpluginshopee7:id/tv_state_btn"
    result = find_node_by_resource_id(xml_path, target_id)

    if result:
        cx, cy = result
        print(f"Click tại: ({cx}, {cy})")



if __name__ == "__main__":
    main()
