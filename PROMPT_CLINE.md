# GameTrans AI V2 – hướng dẫn cho người phát triển

Dự án đã được nâng cấp lên kiến trúc OCR toàn màn hình, không cần khoanh vùng.
Các nhiệm vụ còn lại là kiểm thử trực tiếp trong Windows và tinh chỉnh:

1. Giữ nguyên chế độ chọn một cửa sổ game, OCR mọi chữ Trung trong vùng client.
2. Tối ưu OCR nhận được chữ nhỏ và hiệu ứng động bằng đo thời gian thực, không đưa số liệu giả.
3. Mỗi kết quả OCR là một box độc lập và dịch trong overlay, không vẽ tràn desktop.
4. Đảm bảo WDA_EXCLUDEFROMCAPTURE trên Windows; nếu API không hỗ trợ, hiển thị cảnh báo và tránh tự nhận lại overlay.
5. Thử chính ảnh 斗罗大陆：诛邪传说 trong tests/fixtures/douluo_settings.jpg.b64, rồi thử trực tiếp với game.
6. Không sử dụng inject/hook hoặc vượt qua anti-cheat, không tuyên bố đạt 100% chính xác.
7. Build Windows bằng .github/workflows/build-windows.yml: test OCR thực, test EXE OCR được đóng gói và GUI smoke.

Không gọi phiên bản này là phát hành hoàn chỉnh cho tới khi xác nhận hoạt động với game thật.
