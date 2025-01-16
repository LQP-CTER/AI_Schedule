import google.generativeai as genai
import pandas as pd
import os
from config import GOOGLE_API_KEY

# Kiểm tra API Key
if not GOOGLE_API_KEY:
    raise ValueError("API Key không tồn tại. Hãy kiểm tra lại file config.py")

# Cấu hình API Key
genai.configure(api_key=GOOGLE_API_KEY)

# Cấu hình tham số sinh nội dung
generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 3048
}

# Khởi tạo model
model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    generation_config=generation_config
)

# Hàm hiển thị file trong một thư mục
def list_files_in_folder(folder_path):
    files = [f for f in os.listdir(folder_path) if f.endswith(('.csv', '.xls', '.xlsx'))]
    if not files:
        print("Không tìm thấy file CSV hoặc Excel nào trong thư mục này.")
        return None
    print("Danh sách file khả dụng:")
    for index, file in enumerate(files):
        print(f"{index + 1}. {file}")
    return files

# Hàm đọc dữ liệu từ file CSV hoặc Excel
def read_data_from_file(folder_path):
    files = list_files_in_folder(folder_path)
    if not files:
        return None

    try:
        file_index = int(input("Chọn file (nhập số thứ tự): ")) - 1
        if file_index < 0 or file_index >= len(files):
            print("Lựa chọn không hợp lệ.")
            return None

        file_path = os.path.join(folder_path, files[file_index])

        if file_path.endswith(".csv"):
            try:
                data = pd.read_csv(file_path, encoding='utf-8')
            except UnicodeDecodeError:
                data = pd.read_csv(file_path, encoding='ISO-8859-1')
        elif file_path.endswith(('.xls', '.xlsx')):
            data = pd.read_excel(file_path)
        else:
            raise ValueError("File không được hỗ trợ. Chỉ chấp nhận CSV hoặc Excel.")

        print(f"Dữ liệu từ {file_path} đã được tải thành công!")
        return data

    except Exception as e:
        print(f"Lỗi khi đọc file: {e}")
        return None

# Hàm tạo phản hồi từ chatbot
def chat_with_bot(data=None):
    print("🤖 Chatbot đã sẵn sàng! Gõ 'thoát' để kết thúc.")
    while True:
        user_input = input("Bạn: ")

        if user_input.lower() == "thoát":
            print("Tạm biệt! Hẹn gặp lại! 👋")
            break

        # Tìm kiếm thông tin trong file nếu có dữ liệu
        if data is not None:
            try:
                matched_rows = data[data['Keyword'].str.contains(user_input, case=False, na=False)]
                if not matched_rows.empty:
                    print("🔎 Dữ liệu tìm thấy từ file:")
                    for _, row in matched_rows.iterrows():
                        print(f"- {row['Information']}")
                else:
                    print("❗ Không tìm thấy thông tin phù hợp trong file.")
            except KeyError:
                print("File không có cột 'Keyword' hoặc 'Information'. Kiểm tra lại file của bạn.")

        # Gọi mô hình AI để trả lời
        try:
            response = model.generate_content(user_input)
            print("Chatbot:", response.text)
        except Exception as e:
            print(f"Lỗi từ mô hình AI: {e}")

# Khởi chạy chương trình
if __name__ == "__main__":
    folder_path = input("Nhập đường dẫn thư mục chứa file CSV hoặc Excel: ")
    if os.path.isdir(folder_path):
        data = read_data_from_file(folder_path)
    else:
        print("Thư mục không tồn tại. Chương trình sẽ chạy mà không có file dữ liệu.")
        data = None

    chat_with_bot(data)
