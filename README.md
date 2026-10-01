# Hướng dẫn sử dụng

## Chuẩn bị trên thiết bị Android

### 1. Bật chế độ Nhà phát triển (Developer Options)

* Vào **Cài đặt → Giới thiệu điện thoại**.
* Nhấn nhiều lần vào **Số bản dựng (Build Number)** cho đến khi xuất hiện thông báo đã bật chế độ nhà phát triển.

### 2. Bật USB Debugging

* Vào **Tùy chọn nhà phát triển (Developer Options)**.
* Bật **USB Debugging**.
* Kết nối điện thoại với máy tính bằng cáp USB.
* Khi điện thoại hiển thị hộp thoại xác nhận:

  * Chọn **Cho phép gỡ lỗi USB (Allow USB Debugging)**.
  * Nếu có tùy chọn **Luôn cho phép từ máy tính này (Always allow from this computer)** thì nên tích chọn.

### 3. Cho phép truyền dữ liệu qua USB

* Khi kết nối điện thoại với máy tính, chọn chế độ **Truyền tệp (File Transfer)** nếu Android yêu cầu.

### 4. Bật hiển thị vị trí con trỏ

* Trong **Tùy chọn nhà phát triển (Developer Options)**, bật:

  * **Pointer Location** (Hiển thị vị trí con trỏ)

Tính năng này giúp xác định chính xác tọa độ các điểm cần thao tác trên màn hình.

### 5. (Tùy chọn) Kết nối ADB không dây

* Trong **Tùy chọn nhà phát triển**, bật **Gỡ lỗi không dây (Wireless debugging)** rồi ghép nối thiết bị với máy tính.
* Serial của thiết bị không dây có dạng `adb-xxxx-xxxx._adb-tls-connect._tcp`.

---

## Yêu cầu trên máy tính

* Python 3 và các thư viện: `pip install opencv-python numpy`
* **ADB** (Android platform-tools) đã cài và có trong `PATH`.
* Kiểm tra thiết bị đã kết nối và lấy serial:

```bash
adb devices
```

---

## Cấu hình ứng dụng

Sau khi đã kết nối ADB thành công:

### 1. Thiết lập thiết bị và tọa độ

* Ghi lại tọa độ các vị trí cần kiểm tra bằng tính năng **Pointer Location**.
* Mở file `main.py`, sửa `DEVICE_TARGETS`: mỗi thiết bị (theo serial từ `adb devices`) có danh sách điểm `(x, y)` riêng. Có thể chạy nhiều thiết bị cùng lúc.
* Các thông số khác có thể chỉnh trong `main.py`:

| Biến | Ý nghĩa |
|---|---|
| `CAPTURE_DELAY_SEC` | Chu kỳ chụp màn hình |
| `CLICK_COOLDOWN_SEC` | Thời gian nghỉ tối thiểu giữa 2 lần click |
| `ADB_TIMEOUT_SEC` | Timeout mỗi lệnh adb |
| `TARGET_REGION_RADIUS`, `MIN_ORANGE_RATIO` | Vùng tròn kiểm tra và tỉ lệ pixel cam tối thiểu để coi là nút Lưu |
| `LOWER_ORANGE`, `UPPER_ORANGE` | Ngưỡng màu cam (HSV) của nút |
| `SAVE_DEBUG_IMAGE` | Bật/tắt lưu ảnh mỗi lần click |

### 2. Chạy chương trình

Mở Terminal hoặc Command Prompt tại thư mục dự án và chạy:

```bash
python main.py
```

Hoặc trên PowerShell:

```powershell
python .\main.py
```

Nhấn `Ctrl+C` để dừng.

---

## Ảnh lưu theo tháng

Mỗi lần click, tool lưu ảnh vào:

```
image/<YYYY-MM>/<serial thiết bị>/<YYYYMMDD_HHMMSS>_x<X>y<Y>.png       # ảnh có vẽ chú thích
image/<YYYY-MM>/<serial thiết bị>/<YYYYMMDD_HHMMSS>_x<X>y<Y>_raw.png   # ảnh gốc, để dò lại ngưỡng màu
```

Ví dụ: `image/2026-10/<serial>/20261001_093015_x915y610.png`.

## Đếm số lần click

* Số lần click lưu trong `click_count.json`, tách theo tháng và theo thiết bị:

```json
{"2026-10": {"<serial>": 12}}
```

* Sang tháng mới tự đếm lại từ 0, dữ liệu tháng cũ vẫn được giữ.
* Mỗi lần click, log in ra số lần của thiết bị và tổng cả tháng.
* Có thể reset hoặc sửa file khi tool đang chạy, số liệu vẫn đúng.

```bash
python main.py --count            # xem số lần tháng này
python main.py --reset            # reset tháng này, tất cả thiết bị
python main.py --reset <serial>   # reset riêng một thiết bị
```
