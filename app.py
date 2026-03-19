import datetime
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st


# =========================================================
# 基本設定
# =========================================================
APP_VERSION = 300
APP_TITLE = "祇園配車アプリ"
DEFAULT_STORE_ADDRESS = "岡山県岡山市北区田町2丁目11-15"
DEFAULT_BASE_ARRIVAL_TIME = "19:50"

API_URL = st.secrets.get("API_URL", "https://central-6.com/gion/api.php")
GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "")

JST = datetime.timezone(datetime.timedelta(hours=9), "JST")
NOW = datetime.datetime.now(JST)
TODAY_STR = NOW.strftime("%m月%d日")
TODAY_DATE = NOW.strftime("%Y-%m-%d")
DOW_LIST = ["月", "火", "水", "木", "金", "土", "日"]
TODAY_DOW = DOW_LIST[NOW.weekday()]

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🚕",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# =========================================================
# セッション初期化
# =========================================================
DEFAULT_SESSION_VALUES = {
    "page": "home",
    "role": None,
    "logged_in_staff": "",
    "logged_in_cast": {},
    "is_admin": False,
    "flash_msg": "",
    "current_staff_tab": "① 配車リスト",
    "cast_send_date_mode": "当日",
    "admin_send_date_mode": "当日",
    "admin_search_cast": "",
}

for k, v in DEFAULT_SESSION_VALUES.items():
    if k not in st.session_state:
        st.session_state[k] = v


# =========================================================
# CSS
# =========================================================
st.markdown(
    """
<style>
html, body, [data-testid="stAppViewContainer"], .block-container {
    max-width: 100vw !important;
    overflow-x: hidden !important;
    background-color: #f0f2f5;
    font-family: -apple-system, BlinkMacSystemFont, sans-serif;
}
.block-container {
    padding-top: 1rem;
    padding-bottom: 5rem;
    max-width: 860px !important;
}
header, footer, [data-testid="stToolbar"] {
    display: none !important;
}
.app-header {
    border-bottom: 2px solid #333;
    padding-bottom: 5px;
    margin-bottom: 10px;
    font-size: 20px;
    font-weight: bold;
}
.date-header {
    text-align: center;
    margin-bottom: 15px;
    padding: 10px;
    background: #fff;
    border: 2px solid #333;
    border-radius: 8px;
    font-size: 24px;
    font-weight: 900;
    color: #e91e63;
}
.card {
    background: #fff;
    padding: 12px;
    border-radius: 10px;
    border: 1px solid #ccc;
    margin-bottom: 12px;
}
.small-note {
    font-size: 12px;
    color: #666;
}
.title1 {
    text-align:center;
    font-size:40px;
    font-weight:bold;
    color:white;
    text-shadow:2px 2px 5px black;
    margin-top: 30px;
}
.title2 {
    text-align:center;
    font-size:32px;
    font-weight:bold;
    color:white;
    text-shadow:2px 2px 5px black;
    margin-bottom:40px;
}
.footer {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background: #333;
    color: white;
    padding: 10px;
    text-align: center;
    z-index: 9999;
}
.section-title {
    font-weight:bold;
    font-size:16px;
    margin-top:10px;
    margin-bottom:8px;
}
</style>
""",
    unsafe_allow_html=True,
)


# =========================================================
# API / 共通関数
# =========================================================
def post_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        r = requests.post(API_URL, json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@st.cache_data(ttl=10)
def get_db_data() -> Dict[str, Any]:
    try:
        r = requests.post(API_URL, json={"action": "get_all_data"}, timeout=30)
        r.raise_for_status()
        res = r.json()
        if res.get("status") == "success":
            return res.get("data", {})
    except Exception:
        pass
    return {"casts": [], "drivers": [], "attendance": [], "settings": {}}


def clear_cache() -> None:
    get_db_data.clear()


def show_flash() -> None:
    if st.session_state.flash_msg:
        st.success(st.session_state.flash_msg)
        st.session_state.flash_msg = ""


def logout_and_home() -> None:
    st.session_state.page = "home"
    st.session_state.role = None
    st.session_state.logged_in_staff = ""
    st.session_state.logged_in_cast = {}
    st.session_state.is_admin = False
    st.rerun()


def render_top_nav() -> None:
    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("←戻る", use_container_width=True):
            logout_and_home()
    with c2:
        st.markdown(
            f"<div style='text-align:right; font-size:12px; color:#666; padding-top:8px;'>ver {APP_VERSION}</div>",
            unsafe_allow_html=True,
        )


def normalize_target_date(label_or_date: str) -> str:
    s = str(label_or_date).strip()
    if s == "" or s == "当日":
        return TODAY_DATE
    if s == "翌日":
        return (NOW + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    return s


def make_next_7_dates() -> List[str]:
    return [
        (NOW + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(7)
    ]


def date_label(ymd: str) -> str:
    try:
        d = datetime.datetime.strptime(ymd, "%Y-%m-%d")
        jp = DOW_LIST[d.weekday()]
        return d.strftime(f"%m/%d（{jp}）")
    except Exception:
        return ymd


def get_time_slots(start_hour: int, end_hour: int, step: int = 10) -> List[str]:
    slots: List[str] = []
    for h in range(start_hour, end_hour + 1):
        for m in range(0, 60, step):
            hh = h if h < 24 else h - 24
            slots.append(f"{hh:02d}:{m:02d}")
    return slots


def parse_cast_address(raw: str) -> Tuple[str, str, str, str]:
    if not raw:
        return "", "0", "", "0"
    parts = str(raw).split("||")
    home_addr = parts[0] if len(parts) > 0 else ""
    takuji_en = parts[1] if len(parts) > 1 else "0"
    takuji_addr = parts[2] if len(parts) > 2 else ""
    is_edited = parts[3] if len(parts) > 3 else "0"
    return home_addr, takuji_en, takuji_addr, is_edited


def encode_cast_address(home_addr: str, takuji_en: str, takuji_addr: str, is_edited: str) -> str:
    return f"{home_addr}||{takuji_en}||{takuji_addr}||{is_edited}"


def parse_attendance_memo(raw: str) -> Tuple[str, str, str, str, str, str, str]:
    if not raw:
        return "", "", "0", "", "", "", ""
    parts = str(raw).split("||")
    memo_text = parts[0] if len(parts) > 0 else ""
    temp_addr = parts[1] if len(parts) > 1 else ""
    takuji_cancel = parts[2] if len(parts) > 2 else "0"
    early_driver = parts[3] if len(parts) > 3 else ""
    early_time = parts[4] if len(parts) > 4 else ""
    early_dest = parts[5] if len(parts) > 5 else ""
    stopover = parts[6] if len(parts) > 6 else ""
    return memo_text, temp_addr, takuji_cancel, early_driver, early_time, early_dest, stopover


def encode_attendance_memo(
    memo_text: str,
    temp_addr: str,
    takuji_cancel: str,
    early_driver: str,
    early_time: str,
    early_dest: str,
    stopover: str,
) -> str:
    return f"{memo_text}||{temp_addr}||{takuji_cancel}||{early_driver}||{early_time}||{early_dest}||{stopover}"


def find_attendance_row(attendance: List[Dict[str, Any]], cast_id: str, target_date: str) -> Optional[Dict[str, Any]]:
    td = normalize_target_date(target_date)
    for row in attendance:
        if str(row.get("cast_id")) == str(cast_id) and str(row.get("target_date")) == td:
            return row
    return None


def get_driver_names(drivers: List[Dict[str, Any]]) -> List[str]:
    return [str(d.get("name", "")).strip() for d in drivers if str(d.get("name", "")).strip()]


def get_cast_display_name(cast_row: Dict[str, Any]) -> str:
    return str(cast_row.get("name", "")).strip()


def get_cast_area(cast_row: Dict[str, Any]) -> str:
    return str(cast_row.get("area", "")).strip()


def get_cast_address(cast_row: Dict[str, Any]) -> str:
    addr_raw = str(cast_row.get("address", ""))
    home_addr, takuji_en, takuji_addr, is_edited = parse_cast_address(addr_raw)
    return home_addr


def render_send_status_selector(key_prefix: str, current_status: str) -> str:
    options = ["送迎", "自走", "休み", "未定"]
    idx = options.index(current_status) if current_status in options else 3
    return st.selectbox("状態", options, index=idx, key=f"{key_prefix}_status")


def save_one_attendance(
    cast_id: str,
    cast_name: str,
    area: str,
    status: str,
    memo: str,
    target_date: str,
) -> Dict[str, Any]:
    return post_api({
        "action": "save_attendance",
        "records": [{
            "cast_id": cast_id,
            "cast_name": cast_name,
            "area": area,
            "status": status,
            "memo": memo,
            "target_date": normalize_target_date(target_date),
        }]
    })


def rerun_with_message(msg: str) -> None:
    clear_cache()
    st.session_state.flash_msg = msg
    st.rerun()


def render_cast_edit_card(
    c_id: str,
    c_name: str,
    pref: str,
    target_row: Optional[Dict[str, Any]],
    mode_key: str,
    d_names: List[str],
    time_slots: List[str],
    loop_idx: int,
    target_date: str,
) -> None:
    current_status = target_row.get("status", "未定") if target_row else "未定"
    current_driver = target_row.get("driver_name", "") if target_row else ""
    current_time = target_row.get("pickup_time", "") if target_row else ""
    current_memo = target_row.get("memo", "") if target_row else ""
    current_route = int(target_row.get("route_no", 0)) if target_row and str(target_row.get("route_no", "")).isdigit() else 0

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"**店番 {c_id}：{c_name}**")
    st.markdown(f"<div class='small-note'>方面: {pref} / 対象日: {date_label(normalize_target_date(target_date))}</div>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        status_options = ["送迎", "自走", "休み", "未定"]
        new_status = st.selectbox(
            "状態",
            status_options,
            index=status_options.index(current_status) if current_status in status_options else 3,
            key=f"status_{mode_key}_{loop_idx}_{c_id}_{target_date}",
        )
    with col2:
        driver_options = [""] + d_names
        new_driver = st.selectbox(
            "担当ドライバー",
            driver_options,
            index=driver_options.index(current_driver) if current_driver in driver_options else 0,
            key=f"driver_{mode_key}_{loop_idx}_{c_id}_{target_date}",
        )
    with col3:
        new_route = st.number_input(
            "ルートNo",
            min_value=0,
            max_value=20,
            value=current_route,
            step=1,
            key=f"route_{mode_key}_{loop_idx}_{c_id}_{target_date}",
        )

    col4, col5 = st.columns(2)
    with col4:
        time_options = [""] + time_slots
        new_time = st.selectbox(
            "迎え時間",
            time_options,
            index=time_options.index(current_time) if current_time in time_options else 0,
            key=f"time_{mode_key}_{loop_idx}_{c_id}_{target_date}",
        )
    with col5:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        save_btn = st.button(
            "保存",
            key=f"save_{mode_key}_{loop_idx}_{c_id}_{target_date}",
            use_container_width=True,
        )

    new_memo = st.text_input(
        "備考",
        value=current_memo,
        key=f"memo_{mode_key}_{loop_idx}_{c_id}_{target_date}",
        placeholder="メモがあれば入力",
    )

    if save_btn:
        res = save_one_attendance(
            cast_id=c_id,
            cast_name=c_name,
            area=pref,
            status=new_status,
            memo=new_memo,
            target_date=target_date,
        )
        if res.get("status") != "success":
            st.error(res.get("message", "送迎情報の保存に失敗しました"))
            st.markdown("</div>", unsafe_allow_html=True)
            return

        clear_cache()
        db2 = get_db_data()
        atts2 = db2.get("attendance", [])
        saved_row = find_attendance_row(atts2, c_id, target_date)

        if saved_row:
            res2 = post_api({
                "action": "update_dispatch",
                "attendance_id": saved_row["id"],
                "driver_name": new_driver,
                "pickup_time": new_time,
                "route_no": int(new_route),
            })
            if res2.get("status") != "success":
                st.error(res2.get("message", "配車情報の保存に失敗しました"))
                st.markdown("</div>", unsafe_allow_html=True)
                return

        rerun_with_message(f"{c_name} の送迎設定を保存しました。")
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# ホーム
# =========================================================
if st.session_state.page == "home":
    show_flash()

    st.markdown(
        """
    <style>
    div.element-container:has(#btn-staff-marker) + div.element-container button,
    div.element-container:has(#btn-cast-marker) + div.element-container button {
        width: 100% !important;
        height: 80px !important;
        border-radius: 15px !important;
        border: 2px solid black !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
        margin-bottom: 10px !important;
    }
    div.element-container:has(#btn-staff-marker) + div.element-container button p,
    div.element-container:has(#btn-cast-marker) + div.element-container button p {
        font-size: 20px !important;
        font-weight: bold !important;
        white-space: pre-wrap !important;
        margin: 0 !important;
        color: white !important;
    }
    div.element-container:has(#btn-staff-marker) + div.element-container button {
        background-color: #64b5f6 !important;
    }
    div.element-container:has(#btn-cast-marker) + div.element-container button {
        background-color: #f48fb1 !important;
    }
    div.element-container:has(#btn-admin-marker) + div.element-container button {
        width: 100% !important;
        height: 40px !important;
        border-radius: 15px !important;
        border: none !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1) !important;
        margin-bottom: 10px !important;
        background-color: #e0e0e0 !important;
    }
    div.element-container:has(#btn-admin-marker) + div.element-container button p {
        font-size: 16px !important;
        font-weight: bold !important;
        white-space: pre-wrap !important;
        margin: 0 !important;
        color: #333333 !important;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="title1">祇園</div>', unsafe_allow_html=True)
    st.markdown('<div class="title2">配車アプリ</div>', unsafe_allow_html=True)

    st.markdown('<div id="btn-staff-marker"></div>', unsafe_allow_html=True)
    if st.button("スタッフ業務開始\n（配車・送迎設定）", use_container_width=True):
        st.session_state.page = "staff_login"
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div id="btn-cast-marker"></div>', unsafe_allow_html=True)
    if st.button("キャスト専用ログイン\n（予定の申請）", use_container_width=True):
        st.session_state.page = "cast_login"
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div id="btn-admin-marker"></div>', unsafe_allow_html=True)
    if st.button("管理者ログイン（設定・リセット）", use_container_width=True):
        st.session_state.page = "admin_login"
        st.rerun()

    st.markdown(
        f"<div style='text-align:center; color:#999; font-size:12px; margin-top:30px; padding-bottom:60px;'>ver {APP_VERSION}</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="footer">サーバー同期完了　　　最新データ受信</div>', unsafe_allow_html=True)
    st.stop()


# =========================================================
# 管理者ログイン
# =========================================================
if st.session_state.page == "admin_login":
    render_top_nav()
    db = get_db_data()
    settings = db.get("settings") or {}

    st.markdown('<div class="app-header">管理者ログイン</div>', unsafe_allow_html=True)
    pw = st.text_input("管理者パスワード", type="password")

    if st.button("ログイン", type="primary", use_container_width=True):
        correct_pw = str(settings.get("admin_password", "admin")) or "admin"
        if pw == correct_pw:
            st.session_state.role = "admin"
            st.session_state.is_admin = True
            st.session_state.logged_in_staff = "管理者"
            st.session_state.page = "staff_portal"
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()


# =========================================================
# スタッフログイン
# =========================================================
if st.session_state.page == "staff_login":
    render_top_nav()
    db = get_db_data()
    drivers = db.get("drivers", [])

    st.markdown('<div class="app-header">スタッフログイン</div>', unsafe_allow_html=True)
    valid_drivers = [x for x in drivers if str(x.get("name", "")).strip() != ""]

    if not valid_drivers:
        st.warning("スタッフがまだ登録されていません。")
        st.stop()

    for d in valid_drivers:
        st.markdown(
            f"<div style='font-weight:bold; margin-top:15px; border-bottom:2px solid #ddd; padding-bottom:5px; margin-bottom:10px;'>👤 {d['name']}</div>",
            unsafe_allow_html=True,
        )
        col_a, col_b = st.columns([3, 1.2])
        with col_a:
            p_in = st.text_input(
                "PW",
                type="password",
                key=f"pw_{d['driver_id']}",
                label_visibility="collapsed",
                placeholder="パスワード",
            )
        with col_b:
            if st.button("開始", key=f"b_{d['driver_id']}", type="primary", use_container_width=True):
                saved_pw = str(d.get("password", "1234")).strip() or "1234"
                if p_in == saved_pw:
                    st.session_state.role = "staff"
                    st.session_state.is_admin = False
                    st.session_state.logged_in_staff = str(d["name"])
                    st.session_state.page = "staff_portal"
                    st.rerun()
                else:
                    st.error("パスワードが違います。")
        st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    st.stop()


# =========================================================
# キャストログイン
# =========================================================
if st.session_state.page == "cast_login":
    render_top_nav()
    db = get_db_data()
    casts = db.get("casts", [])

    st.markdown('<div class="app-header">キャストログイン</div>', unsafe_allow_html=True)
    st.caption("店番 または キャスト名を入力し、パスワードを入れてください")

    c_input = st.text_input("店番 または キャスト名", placeholder="例: 15 または みなみ")
    pw = st.text_input("パスワード", type="password")

    if st.button("ログイン", type="primary", use_container_width=True):
        c_input_str = str(c_input).strip()
        if not c_input_str:
            st.warning("店番かキャスト名を入力してください。")
            st.stop()

        if c_input_str.isdigit():
            target = next((c for c in casts if str(c.get("cast_id")) == c_input_str), None)
        else:
            target = next((c for c in casts if c_input_str == str(c.get("name", "")).strip()), None)

        if not target:
            st.error("該当するキャストが見つかりません。")
            st.stop()

        saved_pw = str(target.get("password", "0000")).strip() or "0000"
        if pw == saved_pw:
            st.session_state.role = "cast"
            st.session_state.logged_in_cast = {
                "店番": str(target.get("cast_id", "")),
                "キャスト名": str(target.get("name", "")),
                "方面": str(target.get("area", "")),
                "担当": str(target.get("manager", "未設定")),
            }
            st.session_state.page = "cast_mypage"
            st.rerun()
        else:
            st.error("パスワードが違います。")
    st.stop()


# =========================================================
# キャストマイページ
# =========================================================
if st.session_state.page == "cast_mypage":
    render_top_nav()

    if st.session_state.role != "cast":
        logout_and_home()

    db = get_db_data()
    casts = db.get("casts", [])
    attendance = db.get("attendance", [])
    settings = db.get("settings") or {}

    c = st.session_state.logged_in_cast
    my_c = next((x for x in casts if str(x.get("cast_id")) == str(c.get("店番"))), None)
    latest_name = my_c.get("name", c.get("キャスト名", "")) if my_c else c.get("キャスト名", "")
    my_area = my_c.get("area", c.get("方面", "")) if my_c else c.get("方面", "")

    st.markdown(
        f'<div style="text-align:center; font-weight:bold; font-size:20px;">店番 {c.get("店番","")} {latest_name} 様</div>',
        unsafe_allow_html=True,
    )

    with st.expander("🏠 自分の登録情報（自宅・託児所）の確認・変更", expanded=False):
        if my_c:
            raw_addr = str(my_c.get("address", ""))
            home_addr, takuji_en, takuji_addr, _ = parse_cast_address(raw_addr)

            new_home = st.text_input("自宅住所 (迎え先)", value=home_addr)
            new_takuji_en = st.checkbox("毎回自動的に託児所を経由する", value=(takuji_en == "1"))
            new_takuji_addr = st.text_input("託児所の住所", value=takuji_addr) if new_takuji_en else ""

            if st.button("💾 登録情報を保存", type="primary", use_container_width=True):
                encoded_addr = encode_cast_address(new_home, "1" if new_takuji_en else "0", new_takuji_addr, "1")
                res = post_api({
                    "action": "save_cast",
                    "cast_id": my_c["cast_id"],
                    "name": my_c.get("name", ""),
                    "password": my_c.get("password", "0000"),
                    "phone": my_c.get("phone", ""),
                    "area": my_c.get("area", ""),
                    "address": encoded_addr,
                    "manager": my_c.get("manager", "未設定"),
                })
                if res.get("status") == "success":
                    rerun_with_message("登録情報を更新しました。")
                else:
                    st.error(res.get("message", "更新失敗"))

    date_modes = ["当日", "翌日", "今後1週間"]
    mode = st.radio("申請対象", date_modes, horizontal=True, key="cast_send_date_mode")

    if mode == "今後1週間":
        date_candidates = make_next_7_dates()
        selected_date = st.selectbox(
            "対象日を選択",
            date_candidates,
            format_func=date_label,
            key="cast_week_select_date",
        )
    else:
        selected_date = normalize_target_date(mode)

    my_row = find_attendance_row(attendance, c.get("店番", ""), selected_date)
    current_status = my_row.get("status", "未定") if my_row else "未定"
    memo_t, temp_addr, takuji_cancel, e_drv, e_time, e_dest, stopover = parse_attendance_memo(my_row.get("memo", "")) if my_row else ("", "", "0", "", "", "", "")

    st.markdown(f"<div class='app-header'>送迎申請：{date_label(normalize_target_date(selected_date))}</div>", unsafe_allow_html=True)

    status_options = ["送迎", "自走", "休み", "未定"]
    status = st.selectbox(
        "状態",
        status_options,
        index=status_options.index(current_status) if current_status in status_options else 3,
        key="cast_send_status",
    )
    memo_text = st.text_input("備考", value=memo_t, key="cast_send_memo")

    req_stopover = st.checkbox("途中で寄る場所（同伴等）がある", value=bool(stopover), key="cast_stop_chk")
    stop_a = st.text_input("立ち寄り先", value=stopover, key="cast_stop_val") if req_stopover else ""

    req_change = st.checkbox("この日のみ迎え先を変更する", value=bool(temp_addr), key="cast_temp_chk")
    temp_pickup = st.text_input("変更後の迎え先", value=temp_addr, key="cast_temp_val") if req_change else ""

    if st.button("📤 申請を保存", type="primary", use_container_width=True):
        enc_memo = encode_attendance_memo(memo_text, temp_pickup, takuji_cancel, e_drv, e_time, e_dest, stop_a)
        res = save_one_attendance(
            cast_id=str(c.get("店番", "")),
            cast_name=latest_name,
            area=my_area,
            status=status,
            memo=enc_memo,
            target_date=selected_date,
        )
        if res.get("status") == "success":
            rerun_with_message("申請を保存しました。")
        else:
            st.error(res.get("message", "送信失敗"))

    st.stop()
# =========================================================
# スタッフ / 管理者ポータル
# =========================================================
if st.session_state.page == "staff_portal":
    render_top_nav()

    if st.session_state.role not in ["staff", "admin"]:
        logout_and_home()

    staff_n = st.session_state.logged_in_staff
    is_adm = st.session_state.is_admin

    db = get_db_data()
    casts = db.get("casts", [])
    drvs = db.get("drivers", [])
    atts = db.get("attendance", [])
    sets = db.get("settings") or {}

    d_names = get_driver_names(drvs)
    time_slots = get_time_slots(17, 26, 10)

    # =====================================================
    # スタッフ画面
    # =====================================================
    if not is_adm:
        st.markdown(f'<div class="date-header">{TODAY_STR} ({TODAY_DOW})</div>', unsafe_allow_html=True)
        st.markdown(
            f"<div style='font-size:20px; font-weight:bold; color:#333; margin-top:5px; margin-bottom:15px;'>👤 {staff_n} 班</div>",
            unsafe_allow_html=True,
        )

        my_tasks = [
            r for r in atts
            if str(r.get("target_date")) == TODAY_DATE
            and str(r.get("status")) == "送迎"
            and str(r.get("driver_name", "")) == staff_n
        ]

        st.markdown('<div class="app-header">スタッフ画面</div>', unsafe_allow_html=True)

        if not my_tasks:
            st.info("本日の担当配車はありません。")
        else:
            my_tasks = sorted(
                my_tasks,
                key=lambda x: (int(x.get("route_no", 0)) if str(x.get("route_no", "")).isdigit() else 0, str(x.get("pickup_time", "")))
            )

            for idx, t in enumerate(my_tasks, start=1):
                c_info = next((c for c in casts if str(c.get("cast_id")) == str(t.get("cast_id"))), {})
                latest_name = c_info.get("name", t.get("cast_name", ""))
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"**{idx}. {latest_name}**")
                st.write(f"店番: {t.get('cast_id')}")
                st.write(f"ルート: {t.get('route_no', 0)}")
                st.write(f"迎え時間: {t.get('pickup_time', '未定')}")
                st.write(f"状態: {t.get('status', '')}")
                st.write(f"担当: {t.get('driver_name', '未定')}")
                st.markdown("</div>", unsafe_allow_html=True)

        if st.button("ログアウト", use_container_width=True):
            logout_and_home()
        st.stop()

    # =====================================================
    # 管理者画面
    # =====================================================
    tabs_list_admin = ["① 配車リスト", "② キャスト送迎", "③ キャスト登録", "④ STAFF設定", "⚙️ 管理設定"]
    current_tab = st.session_state.get("current_staff_tab", "① 配車リスト")
    tab_index = tabs_list_admin.index(current_tab) if current_tab in tabs_list_admin else 0
    selected_tab = st.radio("メニュー", tabs_list_admin, index=tab_index, horizontal=True, label_visibility="collapsed")
    st.session_state.current_staff_tab = selected_tab
    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

    date_mode_admin = st.radio("対象期間", ["当日", "翌日", "今後1週間"], horizontal=True, key="admin_send_date_mode")

    if date_mode_admin == "今後1週間":
        admin_dates = make_next_7_dates()
        target_date = st.selectbox(
            "対象日を選択",
            admin_dates,
            format_func=date_label,
            key="admin_week_select_date",
        )
    else:
        target_date = normalize_target_date(date_mode_admin)

    # =====================================================
    # ① 配車リスト
    # =====================================================
    if selected_tab == "① 配車リスト":
        st.markdown(f'<div class="date-header">{date_label(target_date)} 配車</div>', unsafe_allow_html=True)

        today_rows = []
        for row in atts:
            if str(row.get("target_date")) == str(target_date) and str(row.get("status")) == "送迎":
                today_rows.append(row)

        dispatch_count = len(today_rows)
        st.markdown(
            f"""
            <div style="background-color:#e3f2fd; border:2px solid #2196f3; padding:10px; border-radius:8px; text-align:center; margin-bottom:10px;">
                <span style="font-size:14px; color:#1565c0; font-weight:bold;">🚗 現在の送迎対象数</span><br>
                <span style="font-size:24px; font-weight:bold; color:#e91e63;">{dispatch_count}</span>
                <span style="font-size:16px; color:#1565c0; font-weight:bold;">名</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🤖 自動配車を実行", type="primary", use_container_width=True):
                res = post_api({
                    "action": "auto_dispatch",
                    "target_date": target_date,
                })
                if res.get("status") == "success":
                    rerun_with_message(res.get("message", "自動配車を実行しました。"))
                else:
                    st.error(res.get("message", "自動配車に失敗しました"))

        with c2:
            if st.button("🔄 再計算", use_container_width=True):
                res = post_api({
                    "action": "auto_dispatch",
                    "target_date": target_date,
                })
                if res.get("status") == "success":
                    rerun_with_message("ルート・時間を再計算しました。")
                else:
                    st.error(res.get("message", "再計算に失敗しました"))

        if not today_rows:
            st.info("この日の送迎対象はまだありません。")
        else:
            route_nos = sorted(
                list(set([
                    int(r.get("route_no", 0))
                    for r in today_rows
                    if str(r.get("route_no", "")).isdigit() and int(r.get("route_no", 0)) > 0
                ]))
            )

            if not route_nos:
                st.warning("まだルートが組まれていません。先に「自動配車を実行」を押してください。")
            else:
                for route_no in route_nos:
                    route_rows = [r for r in today_rows if int(r.get("route_no", 0)) == route_no]
                    route_rows = sorted(route_rows, key=lambda x: str(x.get("pickup_time", "")))
                    current_driver = str(route_rows[0].get("driver_name", "")) if route_rows else ""

                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    st.markdown(f"### ルート {route_no}")

                    driver_options = [""] + d_names
                    selected_driver = st.selectbox(
                        f"ルート{route_no}の担当ドライバー",
                        driver_options,
                        index=driver_options.index(current_driver) if current_driver in driver_options else 0,
                        key=f"route_driver_{route_no}_{target_date}",
                    )

                    if st.button(f"ルート{route_no}のドライバーを変更", key=f"swap_driver_{route_no}_{target_date}", use_container_width=True):
                        res = post_api({
                            "action": "swap_route_driver",
                            "route_no": route_no,
                            "target_date": target_date,
                            "driver_name": selected_driver,
                        })
                        if res.get("status") == "success":
                            rerun_with_message(f"ルート{route_no}のドライバーを変更しました。")
                        else:
                            st.error(res.get("message", "ドライバー変更失敗"))

                    st.markdown("---")

                    for row in route_rows:
                        cast_name = str(row.get("cast_name", ""))
                        cast_id = str(row.get("cast_id", ""))
                        cast_info = next((c for c in casts if str(c.get("cast_id")) == cast_id), {})
                        latest_name = cast_info.get("name", cast_name)
                        latest_area = cast_info.get("area", row.get("area", ""))
                        latest_addr = get_cast_address(cast_info) if cast_info else ""

                        st.markdown(f"**{latest_name}（店番 {cast_id}）**")
                        st.write(f"迎え時間: {row.get('pickup_time', '')}")
                        st.write(f"住所: {latest_addr}")
                        st.write(f"担当: {row.get('driver_name', '')}")

                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            move_driver = st.selectbox(
                                f"{latest_name} 担当変更",
                                [""] + d_names,
                                index=([""] + d_names).index(str(row.get("driver_name", ""))) if str(row.get("driver_name", "")) in ([""] + d_names) else 0,
                                key=f"move_drv_{row['id']}",
                            )
                        with col_b:
                            move_route = st.number_input(
                                f"{latest_name} ルート変更",
                                min_value=0,
                                max_value=20,
                                value=int(row.get("route_no", 0)) if str(row.get("route_no", "")).isdigit() else 0,
                                step=1,
                                key=f"move_route_{row['id']}",
                            )
                        with col_c:
                            move_time = st.selectbox(
                                f"{latest_name} 時間変更",
                                [""] + time_slots,
                                index=([""] + time_slots).index(str(row.get("pickup_time", ""))) if str(row.get("pickup_time", "")) in ([""] + time_slots) else 0,
                                key=f"move_time_{row['id']}",
                            )

                        if st.button(f"{latest_name} の配車更新", key=f"upd_dispatch_{row['id']}", use_container_width=True):
                            res = post_api({
                                "action": "update_dispatch",
                                "attendance_id": row["id"],
                                "driver_name": move_driver,
                                "pickup_time": move_time,
                                "route_no": int(move_route),
                            })
                            if res.get("status") == "success":
                                rerun_with_message(f"{latest_name} の配車を更新しました。")
                            else:
                                st.error(res.get("message", "更新失敗"))

                        st.markdown("<hr>", unsafe_allow_html=True)

                    st.markdown("</div>", unsafe_allow_html=True)

    # =====================================================
    # ② キャスト送迎（根幹）
    # =====================================================
    elif selected_tab == "② キャスト送迎":
        st.markdown('<div class="app-header">キャスト送迎登録</div>', unsafe_allow_html=True)

        target_rows = [r for r in atts if str(r.get("target_date")) == str(target_date)]
        dispatch_count = len([r for r in target_rows if str(r.get("status")) == "送迎"])
        self_count = len([r for r in target_rows if str(r.get("status")) == "自走"])
        off_count = len([r for r in target_rows if str(r.get("status")) == "休み"])

        st.markdown(
            f"""
            <div style="background:#fff; border:2px solid #bbb; border-radius:10px; padding:12px; margin-bottom:10px;">
                <b>対象日:</b> {date_label(target_date)}<br>
                <b>送迎:</b> {dispatch_count}名　
                <b>自走:</b> {self_count}名　
                <b>休み:</b> {off_count}名
            </div>
            """,
            unsafe_allow_html=True,
        )

        search_word = st.text_input("キャスト検索", value=st.session_state.admin_search_cast, placeholder="店番 または 名前")
        st.session_state.admin_search_cast = search_word

        for loop_idx, cast in enumerate(casts):
            c_id = str(cast.get("cast_id", ""))
            c_name = get_cast_display_name(cast)
            if c_id == "" and c_name == "":
                continue

            if search_word:
                if search_word not in c_id and search_word not in c_name:
                    continue

            pref = get_cast_area(cast)
            target_row = find_attendance_row(atts, c_id, target_date)

            render_cast_edit_card(
                c_id=c_id,
                c_name=c_name,
                pref=pref,
                target_row=target_row,
                mode_key="adminsend",
                d_names=d_names,
                time_slots=time_slots,
                loop_idx=loop_idx,
                target_date=target_date,
            )

    # =====================================================
    # ③ キャスト登録
    # =====================================================
    elif selected_tab == "③ キャスト登録":
        st.markdown('<div class="app-header">キャスト登録</div>', unsafe_allow_html=True)

        search_cast = st.text_input("検索", placeholder="店番 または 名前", key="cast_reg_search")
        cast_rows = casts[:]

        if search_cast:
            cast_rows = [
                c for c in cast_rows
                if search_cast in str(c.get("cast_id", "")) or search_cast in str(c.get("name", ""))
            ]

        st.markdown("### 新規 / 既存キャスト編集")

        for cast in cast_rows:
            c_id = str(cast.get("cast_id", ""))
            c_name = str(cast.get("name", ""))
            c_password = str(cast.get("password", "0000"))
            c_phone = str(cast.get("phone", ""))
            c_area = str(cast.get("area", ""))
            c_address = str(cast.get("address", ""))
            c_manager = str(cast.get("manager", "未設定"))

            with st.expander(f"店番 {c_id} / {c_name if c_name else '未登録'}", expanded=False):
                n_id = st.text_input("店番", value=c_id, key=f"castid_{c_id}")
                n_name = st.text_input("名前", value=c_name, key=f"castname_{c_id}")
                n_pass = st.text_input("パスワード", value=c_password, key=f"castpass_{c_id}")
                n_phone = st.text_input("電話番号", value=c_phone, key=f"castphone_{c_id}")
                n_area = st.text_input("方面", value=c_area, key=f"castarea_{c_id}")
                n_addr = st.text_area("住所", value=c_address, key=f"castaddr_{c_id}")
                n_manager = st.text_input("担当", value=c_manager, key=f"castmanager_{c_id}")

                if st.button(f"キャスト保存_{c_id}", key=f"save_cast_{c_id}", use_container_width=True):
                    res = post_api({
                        "action": "save_cast",
                        "cast_id": n_id,
                        "name": n_name,
                        "password": n_pass,
                        "phone": n_phone,
                        "area": n_area,
                        "address": n_addr,
                        "manager": n_manager,
                    })
                    if res.get("status") == "success":
                        rerun_with_message(f"{n_name or n_id} を保存しました。")
                    else:
                        st.error(res.get("message", "保存失敗"))

        st.markdown("---")
        st.markdown("### 新規キャスト追加")
        new_id = st.text_input("新規店番", key="new_cast_id")
        new_name = st.text_input("新規名前", key="new_cast_name")
        new_pass = st.text_input("新規パスワード", value="0000", key="new_cast_pass")
        new_phone = st.text_input("新規電話番号", key="new_cast_phone")
        new_area = st.text_input("新規方面", key="new_cast_area")
        new_addr = st.text_area("新規住所", key="new_cast_addr")
        new_manager = st.text_input("新規担当", value="未設定", key="new_cast_manager")

        if st.button("新規キャストを追加", type="primary", use_container_width=True):
            if not str(new_id).strip():
                st.warning("店番を入れてください。")
            else:
                res = post_api({
                    "action": "save_cast",
                    "cast_id": new_id,
                    "name": new_name,
                    "password": new_pass,
                    "phone": new_phone,
                    "area": new_area,
                    "address": new_addr,
                    "manager": new_manager,
                })
                if res.get("status") == "success":
                    rerun_with_message("新規キャストを追加しました。")
                else:
                    st.error(res.get("message", "追加失敗"))

    # =====================================================
    # ④ STAFF設定
    # =====================================================
    elif selected_tab == "④ STAFF設定":
        st.markdown('<div class="app-header">STAFF設定</div>', unsafe_allow_html=True)

        for d in drvs:
            driver_id = str(d.get("driver_id", ""))
            driver_name = str(d.get("name", ""))
            driver_pass = str(d.get("password", "1234"))

            with st.expander(f"STAFF {driver_id} / {driver_name if driver_name else '未登録'}", expanded=False):
                n_driver_id = st.text_input("スタッフID", value=driver_id, key=f"drv_id_{driver_id}")
                n_driver_name = st.text_input("スタッフ名", value=driver_name, key=f"drv_name_{driver_id}")
                n_driver_pass = st.text_input("パスワード", value=driver_pass, key=f"drv_pass_{driver_id}")

                if st.button(f"STAFF保存_{driver_id}", key=f"save_driver_{driver_id}", use_container_width=True):
                    res = post_api({
                        "action": "save_driver",
                        "driver_id": n_driver_id,
                        "name": n_driver_name,
                        "password": n_driver_pass,
                    })
                    if res.get("status") == "success":
                        rerun_with_message(f"{n_driver_name or n_driver_id} を保存しました。")
                    else:
                        st.error(res.get("message", "保存失敗"))

    # =====================================================
    # ⚙️ 管理設定
    # =====================================================
    elif selected_tab == "⚙️ 管理設定":
        st.markdown('<div class="app-header">管理設定</div>', unsafe_allow_html=True)

        s_admin = str(sets.get("admin_password", "admin"))
        s_store = str(sets.get("store_address", DEFAULT_STORE_ADDRESS))
        s_time = str(sets.get("base_arrival_time", DEFAULT_BASE_ARRIVAL_TIME))

        with st.form("settings_form"):
            n_admin = st.text_input("管理者パスワード", value=s_admin)
            n_store = st.text_area("店舗住所", value=s_store)
            n_time = st.text_input("基本到着時間", value=s_time)

            submitted = st.form_submit_button("設定を保存", use_container_width=True)
            if submitted:
                res = post_api({
                    "action": "save_settings",
                    "admin_password": n_admin,
                    "store_address": n_store,
                    "base_arrival_time": n_time,
                })
                if res.get("status") == "success":
                    rerun_with_message("設定を保存しました。")
                else:
                    st.error(res.get("message", "保存失敗"))

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    if st.button("ログアウト", use_container_width=True):
        logout_and_home()
    st.stop()


# =========================================================
# フォールバック
# =========================================================
st.warning("ページ状態が不明です。ホームへ戻ります。")
if st.button("ホームへ戻る", use_container_width=True):
    logout_and_home()
