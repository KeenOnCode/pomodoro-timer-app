# Pomodoro Timer ⏱🌸

Ứng dụng **Pomodoro Timer** viết bằng Python & Tkinter, hỗ trợ:
- Đếm giờ theo phương pháp Pomodoro (25/5 hoặc 50/10 phút)
- Thống kê số phiên tập trung (focus sessions) bằng heatmap
- Phát nhạc nền ngẫu nhiên từ thư mục `music/` (loop + shuffle)
- Giao diện tùy chỉnh ảnh nền
- Icon tuỳ chỉnh (file `.ico` với hình đồng hồ & hoa anh đào 🌸)

---

## 📦 Yêu cầu hệ thống
- **Python** 3.9+
- Các thư viện Python:
  ```bash
  pip install -r requirements.txt
  ```
  (Gồm `tkinter`, `pygame`, `matplotlib`, `Pillow`, `numpy`, `plyer`...)

---

## 🚀 Chạy ứng dụng
1. Clone repo:
   ```bash
   git clone https://github.com/KeenOnCode/pomodoro-timer-app.git
   cd pomodoro-timer-app
   ```

2. Chạy bằng Python:
   ```bash
   python app.py
   ```

---

## 🎵 Thêm nhạc nền
- Đặt file `.mp3` vào thư mục `music/` (cùng cấp với `app.py`).
- Ứng dụng sẽ tự động phát tất cả bài hát, **shuffle** và **loop** liên tục.

---

## 🖼 Đổi ảnh nền
- Thay thế file `assets/bg.jpg` bằng ảnh của bạn.
- Ảnh sẽ được tự động scale để khớp kích thước cửa sổ.

---

## 📌 Build file .exe (Windows)
1. Cài **PyInstaller**:
   ```bash
   pip install pyinstaller
   ```

2. Build onefile kèm icon:
   ```bash
   python -m PyInstaller --noconsole --onefile --icon=assets/app.ico --add-data "assets;assets" --add-data "music;music" app.py
   ```

3. File `.exe` sẽ nằm trong thư mục `dist/`.

💡 **Mẹo**: Để đổi icon hiển thị trên **taskbar khi chạy**, icon phải được set trong code:
```python
self.root.iconbitmap(resource_path("assets/app.ico"))
```

---

## 📤 Phát hành (Release)
1. Nén file `.exe` hoặc nguyên thư mục `dist/` (nếu muốn người dùng đổi nhạc/ảnh).
2. Tạo **GitHub Release** và upload file `.zip` hoặc `.exe`.

---

## 📄 Giấy phép
MIT License – tự do sử dụng, chỉnh sửa và phân phối.
