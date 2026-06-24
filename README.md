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

---

## Cấu hình ứng dụng

Sau khi đã kết nối ADB thành công:

### 1. Thiết lập tọa độ

* Xác định 3 vị trí cần kiểm tra trên màn hình.
* Ghi lại tọa độ bằng tính năng **Pointer Location**.
* Mở file `main.py`.
* Cập nhật các giá trị tọa độ tương ứng trong file.

### 2. Chạy chương trình

Mở Terminal hoặc Command Prompt tại thư mục dự án và chạy:

```bash
python main.py
```

Hoặc trên PowerShell:

```powershell
python .\main.py
```
