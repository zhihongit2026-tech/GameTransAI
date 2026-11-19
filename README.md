# GameTrans AI V2 – tự động dịch chữ Trung trong cửa sổ game Windows

**Trạng thái: V2 – bản thử nghiệm; không cam kết chính xác 100% hoặc độ trễ cố định.**

Ứng dụng chạy độc lập, không sửa bộ nhớ hay file game, không bypass anti-cheat. Mở game ở chế độ cửa sổ/borderless, mở GameTransAI và chọn cửa sổ game trong danh sách: ứng dụng tự bắt đầu dịch. Bạn có thể nhấn **BẮT ĐẦU DỊCH TỰ ĐỘNG** nếu muốn khởi động lại bằng nút thủ công. Không phải khoanh bất cứ vùng OCR nào.

## Cách hoạt động

1. Chụp *toàn bộ vùng nội dung* cửa sổ game (DXcam hoặc MSS).
2. RapidOCR tự phát hiện các dòng/cụm chữ Trung cùng tọa độ polygon trong ảnh.
3. Chỉ dịch các chuỗi có chữ Hán; mỗi chuỗi có một hộp dịch riêng tại vị trí gốc.
4. Cache SQLite và glossary theo từng game, có tách thuật ngữ xuất hiện trong chuỗi dài.
5. So sánh khung hình theo các ô nhỏ, giữ các hộp chữ không đổi, chỉ OCR lại vùng biến động; khi cảnh thay đổi lớn thì OCR toàn màn hình.
6. Lớp phủ Qt trong suốt, không nhận chuột/phím, giới hạn trong khung game; theo dõi vị trí và kích thước client mỗi 100 ms. Cố gắng loại lớp phủ khỏi ảnh chụp bằng `WDA_EXCLUDEFROMCAPTURE` khi được Windows hỗ trợ.

Tính năng tự động chỉ là **quét mọi vùng có thể nhận diện trong khung game**, không có khả năng đảm bảo đọc hoặc dịch chính xác 100% mọi chữ cách điệu, chữ quá nhỏ hay bị hiệu ứng che. Câu chưa có cache cần Internet để gọi Google Translate qua `deep-translator`; không gửi toàn bộ ảnh lên dịch vụ, nhưng gửi các dòng chữ cần dịch. Một số game chặn chụp màn hình hoặc overlay do anti-cheat, nhất là fullscreen exclusive.

## Cách chạy mã nguồn

Windows 10/11 x64, Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## Tạo bản EXE Windows

GitHub → Actions → **Build Windows EXE V2** → Run workflow. Build bắt buộc qua:

- Unit tests, gồm bài test ảnh gốc của game **斗罗大陆：诛邪传说** (fixture lưu dưới dạng JPEG base64 để GitHub API nhận được).
- RapidOCR thật đọc các dòng tiếng Trung trong ảnh mẫu.
- PyInstaller `onedir`, kiểm tra EXE tồn tại, chạy `GameTransAI.exe --ocr-self-test tests/fixtures/douluo_settings.jpg.b64` và smoke test khởi động giao diện Qt `offscreen`.
- Nếu tất cả đạt, upload artifact `GameTransAI-V2-Windows-x64` (ZIP chứa `GameTransAI.exe` và thư mục `_internal`).

Chỉ xác nhận bản build sau khi job thành công và có artifact tải được.

## Giới hạn và trách nhiệm sử dụng

- Vùng bị che, chữ chuyển động hoặc font nghệ thuật có thể OCR sai; giao diện chuyển nhanh có thể dẫn đến trễ dịch.
- Dịch dựa vào mạng cho các câu mới; gọi dịch vụ ngoài có thể chậm hoặc bị giới hạn. Không cam kết dịch tức thì toàn màn hình.
- Hiệu năng phụ thuộc CPU, đồ họa game, độ phân giải và số lượng nhãn; pipeline chạy riêng khỏi luồng GUI.
- Overlay phụ thuộc hỗ trợ Windows và cách game render, đặc biệt anti-cheat/fullscreen-exclusive; không tìm cách can thiệp hoặc vượt qua bảo vệ game.
- Kiểm thử tự động xác nhận cấu trúc, OCR và EXE khởi chạy trong Windows CI, **không thay thế kiểm thử game thật trực tiếp tại máy của bạn**.
