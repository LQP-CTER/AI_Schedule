import streamlit as st
import pandas as pd
import io
import google.generativeai as genai
import yaml
from datetime import datetime, timedelta
from ortools.sat.python import cp_model
from config import GOOGLE_API_KEY
import re
import json

# Kiểm tra và import xlsxwriter
try:
    import xlsxwriter
except ImportError:
    import sys
    st.error("Module 'xlsxwriter' is missing. Please install by running 'pip install xlsxwriter'.")
    sys.exit(1)


# Configure Google AI
if not GOOGLE_API_KEY:
    raise ValueError("API Key not found. Please check config.py")

genai.configure(api_key=GOOGLE_API_KEY)

# Configure generation parameters
generation_config = {
    "temperature": 0.9,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 3048
}

model = genai.GenerativeModel(
    model_name="gemini-1.5-pro",
    generation_config=generation_config
)


def load_credentials():
    try:
        with open('credentials.yaml') as file:
            credentials = yaml.safe_load(file)
            return credentials
    except FileNotFoundError:
        st.error("Credentials file not found. Please create credentials.yaml")
        return {}
    except yaml.YAMLError as e:
        st.error(f"Error reading credentials file: {e}")
        return {}


def login():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    # Đặt tiêu đề tổng quát ở đầu trang (tuỳ ý)
    st.markdown("""
        <h2 style='text-align: center; color: #FFFFFF;'>
            [MSS] Work Schedule Manager
        </h2>
        <p style='text-align: center; color: #FFFFFF; margin-top: -10px;'>
            Vui lòng đăng nhập để sử dụng hệ thống
        </p>
    """, unsafe_allow_html=True)

    # Logo hoặc hình minh hoạ (nếu muốn)
    # st.image("logo.png", width=120)  # Chỉnh đường dẫn/logo tùy nhu cầu

    # Nhúng CSS để tạo background và một box login chính giữa
    st.markdown("""
        <style>
            /* Toàn trang: có thể đổi màu hoặc gradient tuỳ ý */
            body {
                background: linear-gradient(to right, #ECE9E6, #FFFFFF);
            }

            /* Tạo một box chính giữa màn hình cho form đăng nhập */
            .login-box {
                margin: 0 auto;           /* canh giữa */
                max-width: 380px;         /* độ rộng tối đa của box */
                background-color: rgba(255, 255, 255, 0.85); 
                backdrop-filter: blur(5px); /* hiệu ứng mờ nền */
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 3px 6px rgba(0,0,0,0.16);
                text-align: center;
            }

            .login-title {
                font-size: 22px;
                font-weight: 600;
                color: #31333F;
                margin-bottom: 20px;
            }

            /* Tuỳ chọn style cho phần input */
            .stTextInput>div>div>input {
                padding: 10px;
                border: 1px solid #ccc;
                border-radius: 5px;
                width: 100%;
            }

            /* Tuỳ chọn style cho nút đăng nhập */
            .login-button {
                width: 100%;
                height: 45px;
                background-color: #31333F;
                color: #FFFFFF;
                border: none;
                border-radius: 5px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                margin-top: 10px;
            }

            .login-button:hover {
                background-color: #50525C;
            }

            /* Ẩn menu hamburger và "Made with Streamlit" footer (tuỳ chọn) */
            /* .css-1rs6os edgvbvh3 { visibility: hidden; } */
            /* footer {visibility: hidden;} */
        </style>
    """, unsafe_allow_html=True)

    # Load credentials từ file credentials.yaml
    credentials = load_credentials()
    if not credentials:
        return False

    # Tạo container hiển thị box đăng nhập
    with st.container():
        st.markdown("<div class='login-box'>", unsafe_allow_html=True)

        st.markdown("<div class='login-title' style='color: #FFFFFF;'>Đăng Nhập</div>", unsafe_allow_html=True)

        # Input username / password
        username = st.text_input("Tên đăng nhập").strip()
        password = st.text_input("Mật khẩu", type="password")

        # Nút Login
        if st.button("Đăng nhập", key="login-button"):
            if username in credentials and credentials[username] == password:
                st.session_state.logged_in = True
                st.success("Đăng nhập thành công!")
                st.rerun()
            else:
                st.error("Tên đăng nhập hoặc mật khẩu không đúng.")

        st.markdown("</div>", unsafe_allow_html=True)

    return st.session_state.logged_in


def get_scheduling_requirements():
    st.sidebar.subheader("Điều Kiện Lập Lịch")

    requirements = {
        "shifts": {
            "Ca sáng": {"start": "09:00", "end": "15:00"},
            "Ca chiều": {"start": "14:00", "end": "20:00"}
        },
        "max_shifts_per_day": st.sidebar.number_input("Số ca tối đa/người/ngày", 1, 2, 1),
        "min_rest_hours": st.sidebar.number_input("Số giờ nghỉ tối thiểu giữa các ca", 8, 24, 12),
        "max_consecutive_days": st.sidebar.number_input("Số ngày làm việc liên tiếp tối đa", 1, 7, 5),
        "staff_per_shift": {
            "Ca sáng": st.sidebar.number_input("Số nhân viên/ca sáng", 1, 5, 2),
            "Ca chiều": st.sidebar.number_input("Số nhân viên/ca chiều", 1, 5, 2)
        },
        "preferences_weight": st.sidebar.slider("Mức độ ưu tiên nguyện vọng nhân viên", 0.0, 1.0, 0.5)
    }

    return requirements


def fallback_analyze_note(note):
    """
    Phân tích cơ bản dựa trên từ khóa khi AI không trả về kết quả hợp lệ.
    """
    note_lower = note.lower()
    priority = 0
    preferred = []
    avoid = []

    # Ưu tiên / tránh ca sáng
    if 'ca sáng' in note_lower:
        if any(word in note_lower for word in ['muốn', 'thích', 'được']):
            preferred.append('Ca sáng')
        elif any(word in note_lower for word in ['không', 'khó', 'bận']):
            avoid.append('Ca sáng')

    # Ưu tiên / tránh ca chiều
    if 'ca chiều' in note_lower or 'chiều' in note_lower:
        if any(word in note_lower for word in ['muốn', 'thích', 'được']):
            preferred.append('Ca chiều')
        elif any(word in note_lower for word in ['không', 'khó', 'bận']):
            avoid.append('Ca chiều')

    # Xác định priority basic
    if any(word in note_lower for word in ['cần', 'phải', 'quan trọng', 'khẩn']):
        priority = 8
    elif any(word in note_lower for word in ['muốn', 'thích']):
        priority = 5

    return {
        'priority': priority,
        'preferred_shifts': preferred,
        'avoid_shifts': avoid
    }


def parse_ai_response(text):
    """
    Tách chuỗi JSON từ phản hồi AI và chuẩn hóa kết quả
    """
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in AI response.")

    json_str = match.group(0)
    json_str = json_str.replace("'", '"')

    parsed = json.loads(json_str)

    priority = parsed.get('priority', 0)
    preferred_shifts = parsed.get('preferred_shifts', [])
    avoid_shifts = parsed.get('avoid_shifts', [])

    if not isinstance(priority, int):
        priority = int(float(priority))
    priority = max(0, min(10, priority))

    valid_shifts = ['Ca sáng', 'Ca chiều']
    preferred_shifts = [s for s in preferred_shifts if s in valid_shifts]
    avoid_shifts = [s for s in avoid_shifts if s in valid_shifts]

    return {
        "priority": priority,
        "preferred_shifts": preferred_shifts,
        "avoid_shifts": avoid_shifts
    }


def analyze_note(note, model, max_retries=2):
    """
    Phân tích ghi chú của nhân viên qua AI, trả về dict:
    {
        "priority": int [0..10],
        "preferred_shifts": list[str],
        "avoid_shifts": list[str]
    }
    Nếu AI trả về sai định dạng hoặc không thành công sau N lần thử -> fallback_analyze_note
    """

    if pd.isna(note) or note.strip() == '':
        return {'priority': 0, 'preferred_shifts': [], 'avoid_shifts': []}

    prompt_template = f"""
Bạn là công cụ phân tích ghi chú của nhân viên về ca làm việc.
Trả lời DUY NHẤT một đối tượng JSON có cấu trúc sau:
{{
    "priority": <một số nguyên từ 0-10>,
    "preferred_shifts": <mảng, chỉ chứa "Ca sáng" hoặc "Ca chiều">,
    "avoid_shifts": <mảng, chỉ chứa "Ca sáng" hoặc "Ca chiều">
}}

Ví dụ:
Ghi chú: "Mong được làm ca sáng càng nhiều càng tốt, rất gấp."
Trả về:
{{
    "priority": 8,
    "preferred_shifts": ["Ca sáng"],
    "avoid_shifts": []
}}

Ghi chú: "Em bận buổi chiều, không thể làm ca chiều được ạ!"
Trả về:
{{
    "priority": 5,
    "preferred_shifts": [],
    "avoid_shifts": ["Ca chiều"]
}}

Bây giờ, hãy phân tích ghi chú này: "{note}"
"""

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt_template)
            response_text = response.text.strip()
            result = parse_ai_response(response_text)
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                continue
            else:
                st.warning(f"Lỗi AI parse lần {attempt+1}: {e}. Fallback sang từ khóa cho ghi chú: {note}")
                return fallback_analyze_note(note)


def process_schedule_data(df, model):
    processed_data = []

    try:
        week_col = [col for col in df.columns if 'tuần' in col.lower()][0]
        week_value = df[week_col].iloc[0]

        try:
            start_date = pd.to_datetime(week_value, format='%d/%m/%Y')
        except:
            try:
                start_date = pd.to_datetime(week_value, format='%Y-%m-%d')
            except:
                start_date = pd.Timestamp.now().normalize()
                st.warning(f"Không thể xác định ngày từ giá trị '{week_value}'. Sử dụng ngày hiện tại làm mặc định.")
    except:
        start_date = pd.Timestamp.now().normalize()
        st.warning("Không tìm thấy cột chứa thông tin tuần. Sử dụng ngày hiện tại làm mặc định.")

    day_columns = [
        col for col in df.columns
        if any(day in col.lower() for day in ['thứ 2', 'thứ 3', 'thứ 4', 'thứ 5', 'thứ 6', 'thứ 7', 'chủ nhật'])
    ]

    employee_col = [col for col in df.columns if 'tên' in col.lower() and 'viên' in col.lower()][0]
    note_col = [col for col in df.columns if 'ghi chú' in col.lower()][0]

    for _, row in df.iterrows():
        employee = row[employee_col]
        note_analysis = analyze_note(row.get(note_col, ''), model)

        for i, day_col in enumerate(day_columns):
            date = start_date + pd.Timedelta(days=i)
            availability = str(row[day_col])

            if 'nghỉ' not in availability.lower():
                if 'sáng' in availability.lower():
                    processed_data.append({
                        'Date': date,
                        'Employee': employee,
                        'Available': True,
                        'Shift': 'Ca sáng',
                        'Priority': note_analysis['priority'],
                        'Preferred': ('Ca sáng' in note_analysis['preferred_shifts']),
                        'Avoid': ('Ca sáng' in note_analysis['avoid_shifts'])
                    })
                if 'chiều' in availability.lower():
                    processed_data.append({
                        'Date': date,
                        'Employee': employee,
                        'Available': True,
                        'Shift': 'Ca chiều',
                        'Priority': note_analysis['priority'],
                        'Preferred': ('Ca chiều' in note_analysis['preferred_shifts']),
                        'Avoid': ('Ca chiều' in note_analysis['avoid_shifts'])
                    })
            else:
                processed_data.append({
                    'Date': date,
                    'Employee': employee,
                    'Available': False,
                    'Shift': None,
                    'Priority': 0,
                    'Preferred': False,
                    'Avoid': False
                })

    return pd.DataFrame(processed_data)


def optimize_schedule(availability_df, requirements):
    model_cp = cp_model.CpModel()
    solver = cp_model.CpSolver()

    dates = availability_df['Date'].unique()
    employees = availability_df['Employee'].unique()
    shifts = ['Ca sáng', 'Ca chiều']

    shift_vars = {}
    for date in dates:
        for shift in shifts:
            for emp in employees:
                shift_vars[(date, shift, emp)] = model_cp.NewBoolVar(f'{date}_{shift}_{emp}')

    objective_terms = []
    for date in dates:
        for shift in shifts:
            for emp in employees:
                emp_data = availability_df[
                    (availability_df['Date'] == date) &
                    (availability_df['Employee'] == emp) &
                    (availability_df['Shift'] == shift)
                ]
                if not emp_data.empty:
                    if emp_data['Preferred'].iloc[0]:
                        objective_terms.append(
                            shift_vars[(date, shift, emp)] * emp_data['Priority'].iloc[0]
                        )
                    if emp_data['Avoid'].iloc[0]:
                        objective_terms.append(
                            shift_vars[(date, shift, emp)] * -emp_data['Priority'].iloc[0]
                        )

    model_cp.Maximize(sum(objective_terms))

    for date in dates:
        for shift in shifts:
            model_cp.Add(
                sum(shift_vars[(date, shift, emp)] for emp in employees) ==
                requirements['staff_per_shift'][shift]
            )

        for emp in employees:
            model_cp.Add(
                sum(shift_vars[(date, shift, emp)] for shift in shifts) <=
                requirements['max_shifts_per_day']
            )

    for emp in employees:
        total_shifts = sum(
            shift_vars[(date, shift, emp)]
            for date in dates
            for shift in shifts
        )
        model_cp.Add(total_shifts >= 4)
        model_cp.Add(total_shifts <= 6)

    available_shifts = availability_df[availability_df['Available']] \
        .groupby(['Date', 'Employee'])['Shift'].apply(list).to_dict()

    for date in dates:
        for emp in employees:
            for shift in shifts:
                if (date, emp) not in available_shifts or shift not in available_shifts[(date, emp)]:
                    model_cp.Add(shift_vars[(date, shift, emp)] == 0)

    status = solver.Solve(model_cp)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        schedule_data = []
        for date in dates:
            row = {'Date': date}
            for shift in shifts:
                assigned = [emp for emp in employees if solver.Value(shift_vars[(date, shift, emp)]) == 1]
                for i in range(requirements['staff_per_shift'][shift]):
                    row[f'{shift}_{i + 1}'] = assigned[i] if i < len(assigned) else ''
            schedule_data.append(row)
        return pd.DataFrame(schedule_data)
    else:
        raise Exception("Không tìm được giải pháp khả thi. Vui lòng kiểm tra lại các ràng buộc.")


def clean_note(note):
    if pd.isna(note) or note == '':
        return ''
    note = re.sub(r'[^\w\s\-:,]', ' ', note)
    note = ' '.join(note.split())
    return note


def display_schedule(df):
    st.write("### Lịch Làm Việc")

    max_staff = max(
        [int(col.split('_')[1]) for col in df.columns if '_' in col]
    )
    num_cols = 1 + 2 * max_staff

    cols = st.columns(num_cols)
    cols[0].write("**Ngày**")

    for i in range(max_staff):
        cols[i + 1].write(f"**Ca sáng {i + 1}**")
        cols[i + 1 + max_staff].write(f"**Ca chiều {i + 1}**")

    st.markdown("---")

    for _, row in df.iterrows():
        cols = st.columns(num_cols)
        cols[0].write(row['Date'].strftime('%Y-%m-%d'))

        for i in range(max_staff):
            cols[i + 1].write(row.get(f'Ca sáng_{i + 1}', ''))
            cols[i + 1 + max_staff].write(row.get(f'Ca chiều_{i + 1}', ''))


def main_app():
    st.title("[MSS] Create a work schedule")

    st.markdown('<div id="user-manual-section"></div>', unsafe_allow_html=True)

    user_manual_table = """
    | **Bước** | **Mục tiêu**                                   | **Hành động**                                                                                                                                         |
    |----------|------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
    | 1        | **Thiết Lập Điều Kiện Lập Lịch**               | - Ở cột **sidebar** (bên trái):<br/>  + Nhập **Số ca tối đa/người/ngày**.<br/>  + Nhập **Số giờ nghỉ tối thiểu**.<br/>  + Nhập **Số ngày làm liên tiếp tối đa**.<br/>  + Chọn **Số nhân viên/ca sáng** và **ca chiều**.<br/>  + Chọn **Mức độ ưu tiên nguyện vọng**. |
    | 2        | **Upload File Lịch (Excel hoặc CSV)**          | - Trong khu vực chính (main), bấm **Browse files** để tải file lịch nhân viên (cột *Tên*, cột *Thứ 2..Chủ Nhật*, cột *Ghi chú*, v.v.).<br/> - Xem trước dữ liệu tại mục **Raw Input Data**.                                                                                                             |
    | 3        | **Kiểm tra & Phân tích dữ liệu**               | - Ứng dụng tự động tạo **Processed Schedule Data**, gồm:<br/>  + Thông tin về ca sáng/chiều,<br/>  + Ai có thể làm, ai nghỉ,<br/>  + Ưu tiên/Tránh ca (dựa trên ghi chú + AI).                                                                                                                           |
    | 4        | **Generate Schedule (Tạo Lịch Làm Việc)**       | - Nhấn nút **Generate Schedule**.<br/> - Ứng dụng sẽ chạy **OR-Tools** để tối ưu (theo điều kiện lập lịch + phân tích AI).<br/> - Nếu thành công, hiển thị lịch làm việc theo ngày, ca sáng/ca chiều.                                                                                                     |
    | 5        | **Tải Xuống (Download) Kết Quả**               | - Sau khi xếp lịch xong, bạn có thể **Download** bảng lịch ở dạng **CSV** hoặc **Excel**.<br/> - Lưu trữ hoặc gửi lịch này cho quản lý/nhân viên tham khảo.                                                                                                                                                |
    | 6        | **Kiểm Tra Lỗi**                               | - Nếu gặp **Error** (ví dụ, không đủ người cho mỗi ca), ứng dụng sẽ báo lỗi. Hãy điều chỉnh lại **Điều Kiện Lập Lịch** hoặc **File dữ liệu** rồi **Generate** lại.                                                                                                                                            |
    """

    # === 5) HIỂN THỊ BẢNG HƯỚNG DẪN TRONG EXPANDER ===
    with st.expander("Hướng dẫn sử dụng", expanded=False):
        st.markdown("""
        ### Hướng Dẫn Sử Dụng (Dạng Bảng)
        Bấm vào từng bước dưới đây để tham khảo chi tiết cách dùng:
        """)
        st.markdown(user_manual_table)

    requirements = get_scheduling_requirements()

    uploaded_file = st.file_uploader("Upload Schedule Data", type=['xlsx', 'csv'])

    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)

            st.write("### Raw Input Data")
            st.dataframe(df)

            try:
                processed_df = process_schedule_data(df, model)
                st.write("### Processed Schedule Data")
                st.dataframe(processed_df)

                if st.button("Generate Schedule"):
                    with st.spinner("Optimizing schedule..."):
                        try:
                            optimized_schedule = optimize_schedule(processed_df, requirements)
                            display_schedule(optimized_schedule)

                            col1, col2 = st.columns(2)
                            # Download CSV
                            csv = optimized_schedule.to_csv(index=False)
                            col1.download_button(
                                label="Download Schedule (CSV)",
                                data=csv,
                                file_name="optimized_schedule.csv",
                                mime="text/csv"
                            )

                            buffer = io.BytesIO()
                            with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
                                optimized_schedule.to_excel(writer, index=False)
                            col2.download_button(
                                label="Download Schedule (Excel)",
                                data=buffer.getvalue(),
                                file_name="optimized_schedule.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            )

                        except Exception as e:
                            st.error(f"Error generating schedule: {str(e)}")
                            st.error("Please check if the input data meets all requirements")

            except Exception as e:
                st.error(f"Error processing schedule data: {str(e)}")
                st.error("Please check if the input file has the correct format")

        except Exception as e:
            st.error(f"Error reading file: {str(e)}")
            st.error("Please make sure the file is not corrupted and has the correct format")

    st.sidebar.markdown("---")

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    st.markdown(
        """
        <style>
        .footer {
            position: fixed;
            right: 10px;        
            bottom: 10px;       
            background-color: #222222; 
            color: #FFFFFF;        
            padding: 6px 12px;  
            border-radius: 8px; 
            font-size: 14px;    
            box-shadow: 0px 0px 10px rgba(0, 0, 0, 0.1); 
            z-index: 9999;      
        }
        </style>
        <div class="footer">
            Built by <strong>Le Quy Phat</strong> © 2025
        </div>
        """,
        unsafe_allow_html=True
    )


def main():
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        login()
    else:
        main_app()


if __name__ == "__main__":
    main()
