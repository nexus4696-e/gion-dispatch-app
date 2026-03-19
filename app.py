import datetime
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st


# =========================================================
# 基本設定
# =========================================================
APP_VERSION = 2
APP_TITLE = "祇園配車アプリ"
DEFAULT_STORE_ADDRESS = "岡山県岡山市北区田町2丁目11-15"
DEFAULT_BASE_ARRIVAL_TIME = "19:50"

API_URL = st.secrets.get("API_URL", "https://central-6.com/gion/api.php")
GOOGLE_MAPS_API_KEY = st.secrets.get("GOOGLE_MAPS_API_KEY", "")

JST = datetime.timezone(datetime.timedelta(hours=9), "JST")
NOW = datetime.datetime.now(JST)
TODAY_STR = NOW.strftime("%m月%d日")
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
if "page" not in st.session_state:
    st.session_state.page = "home"

if "role" not in st.session_state:
    st.session_state.role = None

if "logged_in_staff" not in st.session_state:
    st.session_state.logged_in_staff = ""

if "logged_in_cast" not in st.session_state:
    st.session_state.logged_in_cast = {}

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if "flash_msg" not in st.session_state:
    st.session_state.flash_msg = ""

if "active_search_query" not in st.session_state:
    st.session_state.active_search_query = ""

if "search_cast_key" not in st.session_state:
    st.session_state.search_cast_key = 0

if "editing_staff_id" not in st.session_state:
    st.session_state.editing_staff_id = None

if "current_staff_tab" not in st.session_state:
    st.session_state.current_staff_tab = "① 配車リスト"

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
    max-width: 800px !important;
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
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
div[data-baseweb="textarea"] > div {
    border: 2px solid #000 !important;
    border-radius: 6px !important;
    background-color: #fff !important;
}
div[role="radiogroup"] {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    padding-bottom: 10px;
}
div[role="radiogroup"] > label {
    background-color: #fff !important;
    border: 2px solid #ccc !important;
    border-radius: 8px !important;
    padding: 10px 5px !important;
    margin: 0 !important;
    flex: 1 1 auto !important;
    min-width: 60px !important;
    justify-content: center !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
}
div[role="radiogroup"] > label[data-checked="true"] {
    background-color: #e3f2fd !important;
    border-color: #2196f3 !important;
}
div[role="radiogroup"] > label[data-checked="true"] p {
    color: #1565c0 !important;
    font-weight: 900 !important;
}
div[role="radiogroup"] > label p {
    font-size: 15px !important;
    font-weight: bold !important;
    margin: 0 !important;
}
div[role="radiogroup"] > label div[data-baseweb="radio"] > div {
    display: none !important;
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
.card {
    background:#fff;
    padding:10px;
    border-radius:8px;
    border:1px solid #ccc;
    margin-bottom:10px;
}
.small-note {
    font-size:12px;
    color:#666;
}
.warning-box {
    background: #f44336;
    color: white;
    padding: 10px;
    font-weight: bold;
    border-radius: 5px 5px 0 0;
}
.warning-content {
    background: #ffebee;
    border-left: 4px solid #d32f2f;
    padding: 10px;
    margin-bottom: 15px;
    border-radius: 0 0 5px 5px;
}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# 共通関数
# =========================================================
def post_api(payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        r = requests.post(API_URL, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


@st.cache_data(ttl=10)
def get_db_data() -> Dict[str, Any]:
    try:
        r = requests.post(API_URL, json={"action": "get_all_data"}, timeout=20)
        r.raise_for_status()
        res = r.json()
        if res.get("status") == "success":
            return res.get("data", {})
    except Exception:
        pass
    return {"casts": [], "drivers": [], "attendance": [], "settings": {}}


def clear_cache() -> None:
    get_db_data.clear()


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


def parse_address(addr: str) -> Tuple[str, str, str]:
    if not addr:
        return "", "", ""
    prefs = ["岡山県", "広島県", "香川県", "京都府"]
    pref = ""
    for p in prefs:
        if addr.startswith(p):
            pref = p
            break
    body = addr[len(pref):] if pref else addr

    cities = [
        "岡山市", "倉敷市", "玉野市", "総社市", "瀬戸市", "浅口市", "笠岡市",
        "福山市", "尾道市", "三原市", "府中市", "東広島市", "京都市"
    ]
    city = ""
    for c in cities:
        if body.startswith(c):
            city = c
            break
    rest = body[len(city):] if city else body
    return pref, city, rest


def is_in_range(cast_id: Any, range_label: str) -> bool:
    if range_label == "全表示":
        return True
    try:
        start_str, end_str = range_label.split("-")
        cid = int(str(cast_id))
        return int(start_str) <= cid <= int(end_str)
    except Exception:
        return True


def get_time_slots(start_hour: int, end_hour: int, step: int = 10) -> List[str]:
    slots = []
    for h in range(start_hour, end_hour + 1):
        for m in range(0, 60, step):
            hh = h if h < 24 else h - 24
            slots.append(f"{hh:02d}:{m:02d}")
    return slots


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
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("←戻る", use_container_width=True):
            logout_and_home()
    with col2:
        st.markdown(
            f"<div style='text-align:right; font-size:12px; color:#666; padding-top:8px;'>ver {APP_VERSION}</div>",
            unsafe_allow_html=True,
        )def render_cast_edit_card(
    c_id: str,
    c_name: str,
    pref: str,
    target_row: Optional[Dict[str, Any]],
    mode_key: str,
    d_names: List[str],
    time_slots: List[str],
    loop_idx: int,
) -> None:
    current_status = target_row.get("status", "未定") if target_row else "未定"
    current_driver = target_row.get("driver_name", "未定") if target_row else "未定"
    current_time = target_row.get("pickup_time", "未定") if target_row else "未定"
    current_memo = target_row.get("memo", "") if target_row else ""

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown(f"**店番 {c_id}：{c_name}**")
    st.markdown(f"<div class='small-note'>方面: {pref}</div>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        status_options = ["未定", "出勤", "自走", "休み"]
        status_idx = status_options.index(current_status) if current_status in status_options else 0
        new_status = st.selectbox(
            "状態",
            status_options,
            index=status_idx,
            key=f"status_{mode_key}_{loop_idx}_{c_id}",
        )
    with col2:
        driver_options = ["未定"] + d_names
        driver_idx = driver_options.index(current_driver) if current_driver in driver_options else 0
        new_driver = st.selectbox(
            "担当ドライバー",
            driver_options,
            index=driver_idx,
            key=f"driver_{mode_key}_{loop_idx}_{c_id}",
        )

    col3, col4 = st.columns(2)
    with col3:
        time_options = ["未定"] + time_slots
        time_idx = time_options.index(current_time) if current_time in time_options else 0
        new_time = st.selectbox(
            "迎え時間",
            time_options,
            index=time_idx,
            key=f"time_{mode_key}_{loop_idx}_{c_id}",
        )
    with col4:
        st.markdown("<div style='height:28px;'></div>", unsafe_allow_html=True)
        save_btn = st.button(
            "保存",
            key=f"save_{mode_key}_{loop_idx}_{c_id}",
            use_container_width=True,
        )

    new_memo = st.text_input(
        "備考",
        value=current_memo,
        key=f"memo_{mode_key}_{loop_idx}_{c_id}",
        placeholder="メモがあれば入力",
    )

    if save_btn:
        record = {
            "cast_id": c_id,
            "cast_name": c_name,
            "area": pref,
            "status": new_status,
            "memo": new_memo,
            "target_date": "当日",
        }

        res = post_api({"action": "save_attendance", "records": [record]})
        if res.get("status") != "success":
            st.error(res.get("message", "出勤情報の保存に失敗しました。"))
            st.markdown("</div>", unsafe_allow_html=True)
            return

        clear_cache()

        db2 = get_db_data()
        atts2 = db2.get("attendance", [])
        saved_row = next(
            (
                r for r in atts2
                if str(r.get("cast_id")) == str(c_id)
                and r.get("target_date") == "当日"
            ),
            None,
        )

        if saved_row and new_status in ["出勤", "自走"]:
            res2 = post_api({
                "action": "update_dispatch",
                "attendance_id": saved_row["id"],
                "driver_name": new_driver,
                "pickup_time": new_time,
            })
            if res2.get("status") != "success":
                st.error(res2.get("message", "配車情報の保存に失敗しました。"))
                st.markdown("</div>", unsafe_allow_html=True)
                return

        st.session_state.flash_msg = f"{c_name} の送迎設定を保存しました。"
        clear_cache()
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# ホーム
# =========================================================
if st.session_state.page == "home":
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

    show_flash()
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
    c = st.session_state.logged_in_cast

    my_c = next((x for x in casts if str(x.get("cast_id")) == str(c.get("店番"))), None)
    latest_name = my_c.get("name", c.get("キャスト名", "")) if my_c else c.get("キャスト名", "")

    st.markdown(
        f'<div style="text-align:center; font-weight:bold; font-size:20px;">店番 {c.get("店番","")} {latest_name} 様</div>',
        unsafe_allow_html=True,
    )

    with st.expander("🏠 自分の登録情報（自宅・託児所）の確認・変更", expanded=False):
        if my_c:
            raw_addr = str(my_c.get("address", ""))
            home_addr, takuji_en, takuji_addr, _ = parse_cast_address(raw_addr)
            new_home = st.text_input("自宅住所 (迎え先)", value=home_addr)
            st.markdown("<div style='margin-top:10px; font-weight:bold; color:#2196f3;'>👶 託児所の利用設定</div>", unsafe_allow_html=True)
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
                    clear_cache()
                    st.success("登録情報を更新しました。")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(res.get("message", "更新失敗"))

    tab_today, tab_tmr = st.tabs(["当日申請", "翌日申請"])

    with tab_today:
        m_tdy = next(
            (
                r for r in attendance
                if r.get("target_date") == "当日"
                and str(r.get("cast_id")) == str(c.get("店番"))
            ),
            None,
        )
        current_status = m_tdy.get("status", "未定") if m_tdy else "未定"
        memo_t, temp_addr, takuji_cancel, e_drv, e_time, e_dest, stopover = parse_attendance_memo(m_tdy.get("memo", "")) if m_tdy else ("", "", "0", "", "", "", "")

        s = st.radio("状態", ["未定", "出勤", "自走", "休み"], index=["未定", "出勤", "自走", "休み"].index(current_status), horizontal=True, key="tdy_s")
        m = st.text_input("備考", value=memo_t, key="tdy_m")
        req_stopover = st.checkbox("🍽️ 途中で寄る場所（同伴等）がある", value=bool(stopover), key="tdy_stop_chk")
        stop_a = st.text_input("立ち寄り先", value=stopover, key="tdy_stop_val") if req_stopover else ""
        req_change = st.checkbox("📍 本日のみ迎え先を変更する", value=bool(temp_addr), key="tdy_temp_chk")
        ta = st.text_input("迎え先変更", value=temp_addr, key="tdy_temp_val") if req_change else ""

        if st.button("📤 当日申請を送信", type="primary", use_container_width=True, key="tdy_btn"):
            enc_memo = encode_attendance_memo(m, ta, takuji_cancel, e_drv, e_time, e_dest, stop_a)
            if s in ["未定", "休み"]:
                post_api({"action": "cancel_dispatch", "cast_id": c.get("店番")})
            res = post_api({
                "action": "save_attendance",
                "records": [{
                    "cast_id": c.get("店番"),
                    "cast_name": latest_name,
                    "area": c.get("方面", ""),
                    "status": s,
                    "memo": enc_memo,
                    "target_date": "当日",
                }],
            })
            if res.get("status") == "success":
                clear_cache()
                st.session_state.page = "report_done"
                st.rerun()
            else:
                st.error(res.get("message", "送信失敗"))

    with tab_tmr:
        m_tmr = next(
            (
                r for r in attendance
                if r.get("target_date") == "翌日"
                and str(r.get("cast_id")) == str(c.get("店番"))
            ),
            None,
        )
        current_status = m_tmr.get("status", "未定") if m_tmr else "未定"
        memo_t, temp_addr, takuji_cancel, e_drv, e_time, e_dest, stopover = parse_attendance_memo(m_tmr.get("memo", "")) if m_tmr else ("", "", "0", "", "", "", "")

        s = st.radio("明日の状態", ["未定", "出勤", "自走", "休み"], index=["未定", "出勤", "自走", "休み"].index(current_status), horizontal=True, key="tmr_s")
        m = st.text_input("明日の備考", value=memo_t, key="tmr_m")
        req_stopover = st.checkbox("🍽️ 明日途中で寄る場所がある", value=bool(stopover), key="tmr_stop_chk")
        stop_a = st.text_input("明日の立ち寄り先", value=stopover, key="tmr_stop_val") if req_stopover else ""
        req_change = st.checkbox("📍 明日のみ迎え先を変更", value=bool(temp_addr), key="tmr_temp_chk")
        ta = st.text_input("明日の迎え先", value=temp_addr, key="tmr_temp_val") if req_change else ""

        if st.button("📤 翌日申請を送信", type="primary", use_container_width=True, key="tmr_btn"):
            enc_memo = encode_attendance_memo(m, ta, takuji_cancel, e_drv, e_time, e_dest, stop_a)
            res = post_api({
                "action": "save_attendance",
                "records": [{
                    "cast_id": c.get("店番"),
                    "cast_name": latest_name,
                    "area": c.get("方面", ""),
                    "status": s,
                    "memo": enc_memo,
                    "target_date": "翌日",
                }],
            })
            if res.get("status") == "success":
                clear_cache()
                st.session_state.page = "report_done"
                st.rerun()
            else:
                st.error(res.get("message", "送信失敗"))
    st.stop()


if st.session_state.page == "report_done":
    render_top_nav()
    st.markdown("<h1 style='text-align:center; margin-top:50px;'>✅</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;'>出勤報告を受け付けました。</h3>", unsafe_allow_html=True)
    if st.button("マイページへ戻る", type="primary", use_container_width=True):
        st.session_state.page = "cast_mypage"
        st.rerun()
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

    d_names = [str(d["name"]) for d in drvs if d.get("name")]
    time_slots = [f"{h:02d}:{m:02d}" for h in range(17, 24) for m in range(0, 60, 10)]
    store_addr = str(sets.get("store_address", DEFAULT_STORE_ADDRESS))

    if not is_adm:
        st.markdown(f'<div class="date-header">{TODAY_STR} ({TODAY_DOW})</div>', unsafe_allow_html=True)
        st.markdown(f"<div style='font-size:20px; font-weight:bold; color:#333; margin-top:5px; margin-bottom:15px;'>👤 {staff_n} 班</div>", unsafe_allow_html=True)

        my_tasks = [
            r for r in atts
            if r.get("target_date") == "当日"
            and r.get("status") in ["出勤", "自走"]
            and r.get("driver_name") == staff_n
        ]

        st.markdown('<div class="app-header">スタッフ画面</div>', unsafe_allow_html=True)

        if not my_tasks:
            st.info("本日の担当配車はありません。")
        else:
            for idx, t in enumerate(sorted(my_tasks, key=lambda x: str(x.get("pickup_time", "99:99"))), start=1):
                c_info = next((c for c in casts if str(c.get("cast_id")) == str(t.get("cast_id"))), {})
                latest_name = c_info.get("name", t.get("cast_name", ""))
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"**{idx}. {latest_name}**")
                st.write(f"迎え時間: {t.get('pickup_time', '未定')}")
                st.write(f"状態: {t.get('status', '')}")
                st.write(f"担当: {t.get('driver_name', '未定')}")
                st.markdown("</div>", unsafe_allow_html=True)

        if st.button("ログアウト", use_container_width=True):
            logout_and_home()
        st.stop()

    tabs_list_admin = ["① 配車リスト", "② キャスト送迎", "③ キャスト登録", "④ STAFF設定", "⚙️ 管理設定"]
    current_tab = st.session_state.get("current_staff_tab", "① 配車リスト")
    tab_index = tabs_list_admin.index(current_tab) if current_tab in tabs_list_admin else 0
    selected_tab = st.radio("メニュー", tabs_list_admin, index=tab_index, horizontal=True, label_visibility="collapsed")
    st.session_state.current_staff_tab = selected_tab
    st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)

    range_opts = ["全表示"] + [f"{i*10+1}-{i*10+10}" for i in range(15)]

    if selected_tab == "① 配車リスト":
        st.markdown(f'<div class="date-header">{TODAY_STR} 配車</div>', unsafe_allow_html=True)

        dispatch_count = 0
        today_rows = []
        seen_cids = set()

        for row in atts:
            if row.get("target_date") == "当日" and row.get("status") in ["出勤", "自走"]:
                cid_str = str(row.get("cast_id"))
                if cid_str in seen_cids:
                    continue
                seen_cids.add(cid_str)
                dispatch_count += 1
                today_rows.append(row)

        st.markdown(
            f"""
            <div style="background-color:#e3f2fd; border:2px solid #2196f3; padding:10px; border-radius:8px; text-align:center; margin-bottom:10px;">
                <span style="font-size:14px; color:#1565c0; font-weight:bold;">🚗 現在の送迎申請数（当日）</span><br>
                <span style="font-size:24px; font-weight:bold; color:#e91e63;">{dispatch_count}</span>
                <span style="font-size:16px; color:#1565c0; font-weight:bold;">名</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if not today_rows:
            st.info("本日の送迎申請はまだありません。")
        else:
            for row in today_rows:
                c_info = next((c for c in casts if str(c.get("cast_id")) == str(row.get("cast_id"))), {})
                latest_name = c_info.get("name", row.get("cast_name", ""))
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"**{latest_name}**")
                st.write(f"店番: {row.get('cast_id')}")
                st.write(f"状態: {row.get('status')}")
                st.write(f"担当: {row.get('driver_name', '未定')}")
                st.write(f"迎え時間: {row.get('pickup_time', '未定')}")

                assigned_driver = st.selectbox(
                    f"担当ドライバー_{row['id']}",
                    ["未定"] + d_names,
                    index=(["未定"] + d_names).index(row.get("driver_name", "未定")) if row.get("driver_name", "未定") in (["未定"] + d_names) else 0,
                    key=f"drv_{row['id']}",
                )
                pickup_time = st.selectbox(
                    f"迎え時間_{row['id']}",
                    ["未定"] + time_slots,
                    index=(["未定"] + time_slots).index(row.get("pickup_time", "未定")) if row.get("pickup_time", "未定") in (["未定"] + time_slots) else 0,
                    key=f"pt_{row['id']}",
                )

                if st.button(f"保存_{row['id']}", use_container_width=True):
                    res = post_api({
                        "action": "update_dispatch",
                        "attendance_id": row["id"],
                        "driver_name": assigned_driver,
                        "pickup_time": pickup_time,
                    })
                    if res.get("status") == "success":
                        clear_cache()
                        st.session_state.flash_msg = "配車を更新しました。"
                        st.rerun()
                    else:
                        st.error(res.get("message", "更新失敗"))
                st.markdown("</div>", unsafe_allow_html=True)

    elif selected_tab == "② キャスト送迎":
        st.markdown('<div class="app-header">キャスト送迎登録</div>', unsafe_allow_html=True)

        dispatch_count = 0
        today_active_casts = []
        seen_cids_today = set()

        for row in atts:
            if row.get("target_date") == "当日":
                cid_str = str(row.get("cast_id"))
                if cid_str in seen_cids_today:
                    continue
                seen_cids_today.add(cid_str)
                dispatch_count += 1
                c_info_dict = next((c for c in casts if str(c.get("cast_id")) == cid_str), {})
                pref = c_info_dict.get("area", "他")
                today_active_casts.append({
                    "id": row.get("cast_id"),
                    "name": row.get("cast_name", ""),
                    "status": row.get("status", "未定"),
                    "pref": pref,
                    "row": row,
                })

        today_active_casts = sorted(today_active_casts, key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else 999)

        st.markdown(
            f"""
            <div style="background-color:#e3f2fd; border:2px solid #2196f3; padding:10px; border-radius:8px; text-align:center; margin-bottom:10px;">
                <span style="font-size:14px; color:#1565c0; font-weight:bold;">🚗 現在の送迎申請数（当日）</span><br>
                <span style="font-size:24px; font-weight:bold; color:#e91e63;">{dispatch_count}</span>
                <span style="font-size:16px; color:#1565c0; font-weight:bold;">名</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        show_active_casts = st.toggle(f"📋 当日の出勤キャストを表示する（{dispatch_count}名）", value=True)
        if show_active_casts:
            if today_active_casts:
                list_search = st.text_input("🔍 一覧からキャストを絞り込み検索", placeholder="名前 または 店番", key="today_list_search")
                display_c = 0
                for loop_idx, c_dict in enumerate(today_active_casts):
                    c_id = str(c_dict["id"])
                    c_name = str(c_dict["name"])
                    if list_search and list_search not in c_name and list_search != c_id:
                        continue
                    display_c += 1
                    c_inf = next((c for c in casts if str(c.get("cast_id")) == c_id), {})
                    latest_name = c_inf.get("name", c_name)
                    render_cast_edit_card(
                        c_id=c_id,
                        c_name=latest_name,
                        pref=c_dict.get("pref", "他"),
                        target_row=c_dict.get("row"),
                        mode_key="tdy",
                        d_names=d_names,
                        time_slots=time_slots,
                        loop_idx=loop_idx,
                    )
                if display_c == 0:
                    st.info("該当するキャストがいません。")
            else:
                st.info("本日の送迎申請はまだありません。")

        st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:14px; font-weight:bold; color:#555; margin-bottom:5px;'>🔍 全キャスト検索（未出勤者の予定追加・変更）</div>", unsafe_allow_html=True)

        col_search1, col_search2 = st.columns([3, 1])
        with col_search1:
            input_q = st.text_input(
                "検索キーワード",
                placeholder="名前 または 店番",
                key=f"search_input_{st.session_state.search_cast_key}",
                label_visibility="collapsed",
            )
        with col_search2:
            if st.button("検索", type="secondary", use_container_width=True):
                st.session_state.active_search_query = input_q
                st.rerun()

        act_rng = st.radio("範囲", range_opts, horizontal=True, label_visibility="collapsed", key="send_rng")
        st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)

        search_query = st.session_state.active_search_query
        display_count = 0
        seen_all_cids = set()

        for loop_idx, cast in enumerate(casts):
            c_id = str(cast.get("cast_id"))
            c_name = str(cast.get("name", ""))
            if not c_name:
                continue
            if c_id in seen_all_cids:
                continue
            seen_all_cids.add(c_id)

            if search_query:
                if search_query not in c_name and search_query not in c_id:
                    continue
            else:
                if not is_in_range(c_id, act_rng):
                    continue

            display_count += 1
            pref = str(cast.get("area", ""))
            target_row = next((row for row in atts if row.get("target_date") == "当日" and str(row.get("cast_id")) == str(c_id)), None)

            render_cast_edit_card(
                c_id=c_id,
                c_name=c_name,
                pref=pref,
                target_row=target_row,
                mode_key="all",
                d_names=d_names,
                time_slots=time_slots,
                loop_idx=loop_idx,
            )

        if display_count == 0:
            st.info("条件に一致するキャストが見つかりません。")

    elif selected_tab == "③ キャスト登録":
        st.markdown('<div class="app-header">キャスト一覧・登録</div>', unsafe_allow_html=True)
        search_query_reg = st.text_input("🔍 キャスト検索 (名前 または 店番)", placeholder="例: みなみ, 94", key="search_cast_reg")
        act_rng = st.radio("範囲", range_opts, horizontal=True, label_visibility="collapsed", key="reg_rng")

        existing = {str(c["cast_id"]): c for c in casts if str(c.get("cast_id", "")) != ""}
        staff_list = ["未設定"] + d_names

        display_count = 0
        for i in range(1, 151):
            c = existing.get(str(i), {
                "cast_id": i,
                "name": "",
                "phone": "",
                "password": "0000",
                "area": "",
                "address": "",
                "manager": "未設定",
            })
            nm = str(c.get("name", ""))

            if search_query_reg:
                if search_query_reg not in nm and search_query_reg != str(i):
                    continue
            else:
                if not is_in_range(i, act_rng):
                    continue

            display_count += 1
            st.markdown("<div class='card'>", unsafe_allow_html=True)
            col_title, col_mgr = st.columns([3, 2])

            with col_title:
                st.markdown(f"<div style='font-size:16px; font-weight:bold; margin-top:5px;'>店番 {i} : {nm if nm else '未登録'}</div>", unsafe_allow_html=True)

            with col_mgr:
                mgr = str(c.get("manager", "未設定"))
                mgr_idx = staff_list.index(mgr) if mgr in staff_list else 0
                n_mgr = st.selectbox("担当", staff_list, index=mgr_idx, key=f"cmgr_{i}", label_visibility="collapsed")

            nn = st.text_input("名前", value=nm, key=f"cn_{i}")
            raw_addr = str(c.get("address", ""))
            home_addr, takuji_en, takuji_addr, _ = parse_cast_address(raw_addr)

            pref, city, rest = parse_address(home_addr)
            c_pref = st.selectbox("県", ["", "岡山県", "広島県", "香川県", "京都府"], index=["", "岡山県", "広島県", "香川県", "京都府"].index(pref) if pref in ["", "岡山県", "広島県", "香川県", "京都府"] else 0, key=f"c_pref_{i}")

            city_options = [""]
            if c_pref == "岡山県":
                city_options = ["", "岡山市", "倉敷市", "玉野市", "総社市", "瀬戸市", "浅口市", "笠岡市", "他"]
            elif c_pref == "広島県":
                city_options = ["", "福山市", "尾道市", "三原市", "府中市", "東広島市", "他"]
            elif c_pref == "京都府":
                city_options = ["", "京都市", "他"]
            else:
                city_options = ["", "他"]

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                city_idx = city_options.index(city) if city in city_options else (city_options.index("他") if city and "他" in city_options else 0)
                c_city = st.selectbox("市町村", city_options, index=city_idx, key=f"c_city_{i}")
            with col_c2:
                other_val = city if city and city not in city_options else ""
                c_other_city = st.text_input("「他」の場合の直接入力", value=other_val, key=f"c_other_city_{i}")

            c_rest = st.text_input("町名・番地・建物名", value=rest, key=f"c_rest_{i}")
            st.markdown("<div class='section-title' style='color:#2196f3;'>👶 託児設定</div>", unsafe_allow_html=True)
            new_takuji_en = st.checkbox("託児所を利用する", value=(takuji_en == "1"), key=f"takuji_en_{i}")
            new_takuji_addr = st.text_input("託児所の住所", value=takuji_addr, key=f"takuji_addr_{i}")
            nt = st.text_input("電話番号", value=str(c.get("phone", "")), key=f"ct_{i}")
            np = st.text_input("パスワード", value=str(c.get("password", "0000")), key=f"cp_{i}")

            if st.button(f"保存する_{i}", type="primary", use_container_width=True):
                city_part = c_other_city if c_city == "他" else c_city
                final_home = c_pref + city_part + c_rest
                auto_area = "岡山" if c_pref == "岡山県" else ("広島" if c_pref == "広島県" else ("京都" if c_pref == "京都府" else "他"))
                encoded_addr = encode_cast_address(final_home, "1" if new_takuji_en else "0", new_takuji_addr, "0")
                res = post_api({
                    "action": "save_cast",
                    "cast_id": i,
                    "name": nn,
                    "password": np,
                    "phone": nt,
                    "area": auto_area,
                    "address": encoded_addr,
                    "manager": n_mgr,
                })
                if res.get("status") == "success":
                    clear_cache()
                    st.session_state.flash_msg = "キャストを保存しました。"
                    st.rerun()
                else:
                    st.error(res.get("message", "保存失敗"))
            st.markdown("</div>", unsafe_allow_html=True)

        if display_count == 0:
            st.info("条件に一致するキャストが見つかりません。")

    elif selected_tab == "④ STAFF設定":
        exist_drvs = {str(d["driver_id"]): d for d in drvs}
        st.markdown('<div class="app-header">STAFF一覧・登録</div>', unsafe_allow_html=True)

        for i in range(1, 31):
            d = exist_drvs.get(str(i), {})
            nm = str(d.get("name", ""))
            area = str(d.get("area", "全般"))
            disp_nm = nm if nm else "(未登録)"

            st.markdown("<div class='card'>", unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:16px; font-weight:bold;'>STAFF {i} : {disp_nm}</div>", unsafe_allow_html=True)

            nn = st.text_input("STAFF名", value=nm, key=f"dn_{i}")
            area_opts = ["全般", "広島方面", "岡山方面", "広島＆岡山方面", "倉敷・岡山方面", "倉敷方面"]
            area_idx = area_opts.index(area) if area in area_opts else 0

            col_a, col_b = st.columns(2)
            with col_a:
                n_area = st.selectbox("担当方面", area_opts, index=area_idx, key=f"d_ar_{i}")
            with col_b:
                d_cap = int(d.get("capacity", 4)) if str(d.get("capacity", "")).isdigit() else 4
                n_cap = st.number_input("乗車定員", min_value=1, max_value=10, value=d_cap, key=f"d_cp_{i}")

            pref, city, rest = parse_address(str(d.get("address", "")))
            d_pref = st.selectbox("県", ["", "岡山県", "広島県", "香川県", "京都府"], index=["", "岡山県", "広島県", "香川県", "京都府"].index(pref) if pref in ["", "岡山県", "広島県", "香川県", "京都府"] else 0, key=f"dpf_{i}")

            d_opts = [""]
            if d_pref == "岡山県":
                d_opts = ["", "岡山市", "倉敷市", "玉野市", "総社市", "瀬戸市", "浅口市", "笠岡市", "他"]
            elif d_pref == "広島県":
                d_opts = ["", "福山市", "尾道市", "三原市", "府中市", "東広島市", "他"]
            elif d_pref == "京都府":
                d_opts = ["", "京都市", "他"]
            else:
                d_opts = ["", "他"]

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                d_idx = d_opts.index(city) if city in d_opts else (d_opts.index("他") if city and "他" in d_opts else 0)
                d_city = st.selectbox("市町村", d_opts, index=d_idx, key=f"dct_{i}")
            with col_c2:
                other_val = city if city and city not in d_opts else ""
                d_other_city = st.text_input("「他」の場合の直接入力", value=other_val, key=f"d_other_city_{i}")

            d_rest = st.text_input("町名・番地・建物名", value=rest, key=f"drs_{i}")
            n_tel = st.text_input("電話番号", value=str(d.get("phone", "")), key=f"dt_{i}")
            n_pass = st.text_input("パスワード", value=str(d.get("password", "1234")), key=f"dp_{i}")

            if st.button(f"💾 決定する_{i}", type="primary", use_container_width=True):
                city_part = d_other_city if d_city == "他" else d_city
                final_addr = d_pref + city_part + d_rest
                payload = {
                    "action": "save_driver",
                    "driver_id": i,
                    "name": nn,
                    "password": n_pass,
                    "address": final_addr,
                    "phone": n_tel,
                    "area": n_area,
                    "capacity": n_cap,
                }
                res = post_api(payload)
                if res.get("status") == "success":
                    clear_cache()
                    st.session_state.flash_msg = "スタッフを保存しました。"
                    st.rerun()
                else:
                    st.error(res.get("message", "保存失敗"))
            st.markdown("</div>", unsafe_allow_html=True)

    elif selected_tab == "⚙️ 管理設定":
        st.markdown('<div class="app-header" style="border:none;">📢 アプリ全体設定</div>', unsafe_allow_html=True)

        with st.form("adm_form"):
            s_notice = str(sets.get("notice_text", ""))
            s_pass = str(sets.get("admin_password", "admin"))
            s_line = str(sets.get("line_bot_id", ""))
            s_addr = str(sets.get("store_address", DEFAULT_STORE_ADDRESS))
            s_time = str(sets.get("base_arrival_time", DEFAULT_BASE_ARRIVAL_TIME))

            st.markdown('<div class="section-title" style="color:#2196f3; margin-top:0;">📍 送迎基本設定 (店舗・到着時間)</div>', unsafe_allow_html=True)
            n_addr = st.text_input("到着場所（店舗住所）", value=s_addr)
            arr_idx = time_slots.index(s_time) if s_time in time_slots else 0
            n_time = st.selectbox("基本到着時間 (厳守)", time_slots, index=arr_idx)

            st.markdown('<div class="section-title" style="margin-top:20px;">お知らせ</div>', unsafe_allow_html=True)
            n_text = st.text_area("例：本日イベント開催！", value=s_notice, label_visibility="collapsed")

            st.markdown('<div class="section-title" style="color:#e91e63;">🔑 管理者パスワード</div>', unsafe_allow_html=True)
            a_pass = st.text_input("パスワード", value=s_pass, label_visibility="collapsed")

            st.markdown('<div class="section-title" style="color:#00c300;">📱 LINE Bot設定</div>', unsafe_allow_html=True)
            l_id = st.text_input("Bot ID (表示用)", value=s_line, placeholder="@123abcde")

            if st.form_submit_button("保存して反映", type="primary", use_container_width=True):
                res = post_api({
                    "action": "save_settings",
                    "admin_password": a_pass,
                    "notice_text": n_text,
                    "line_bot_id": l_id,
                    "store_address": n_addr,
                    "base_arrival_time": n_time,
                })
                if res.get("status") == "success":
                    clear_cache()
                    st.session_state.flash_msg = "設定を保存しました。"
                    st.rerun()
                else:
                    st.error(res.get("message", "保存失敗"))

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)
    if st.button("ログアウト", use_container_width=True):
        logout_and_home()
    st.stop()


st.warning("ページ状態が不明です。ホームへ戻ります。")
if st.button("ホームへ戻る", use_container_width=True):
    logout_and_home()
