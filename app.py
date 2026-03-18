import os
import re
import time
import datetime
import urllib.parse
import requests
import streamlit as st

# =========================================
# 基本設定
# =========================================
APP_VERSION = 1
APP_TITLE = "祇園配車アプリ"
DEFAULT_STORE_ADDRESS = "岡山県岡山市北区田町2丁目11-15"
DEFAULT_BASE_ARRIVAL_TIME = "19:50"

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🚕",
    layout="centered",
    initial_sidebar_state="collapsed"
)

try:
    API_URL = st.secrets["API_URL"]
except Exception:
    API_URL = ""

try:
    GOOGLE_MAPS_API_KEY = st.secrets["GOOGLE_MAPS_API_KEY"]
except Exception:
    GOOGLE_MAPS_API_KEY = ""

JST = datetime.timezone(datetime.timedelta(hours=+9), 'JST')
dt = datetime.datetime.now(JST)
today_str = dt.strftime("%m月%d日")
days_jp = ['月', '火', '水', '木', '金', '土', '日']
dow = days_jp[dt.weekday()]

# =========================================
# セッション初期化
# =========================================
for k in [
    "page",
    "logged_in_cast",
    "logged_in_staff",
    "is_admin",
    "flash_msg",
    "current_staff_tab",
]:
    if k not in st.session_state:
        st.session_state[k] = None if k != "page" else "home"

if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

if (
    "current_staff_tab" not in st.session_state
    or st.session_state.current_staff_tab not in [
        "① 配車リスト",
        "② キャスト送迎",
        "③ キャスト登録",
        "④ STAFF設定",
        "⚙️ 管理設定",
    ]
):
    st.session_state.current_staff_tab = "① 配車リスト"

if st.session_state.get("flash_msg"):
    st.toast(st.session_state.flash_msg, icon="✅")
    st.session_state.flash_msg = ""

# =========================================
# 共通API
# =========================================
def post_api(payload):
    if not API_URL:
        return {"status": "error", "message": "API_URL が未設定です。"}
    try:
        res = requests.post(API_URL, json=payload, timeout=15)
        if res.status_code == 404:
            return {"status": "error", "message": "api.php が見つかりません。"}
        if res.status_code != 200:
            return {"status": "error", "message": f"サーバーエラー ({res.status_code})"}
        try:
            return res.json()
        except Exception:
            return {"status": "error", "message": f"PHP応答エラー: {res.text[:200]}"}
    except Exception as e:
        return {"status": "error", "message": f"通信失敗: {str(e)}"}

@st.cache_data(ttl=3)
def get_db_data():
    res = post_api({"action": "get_all_data"})
    if res.get("status") == "success":
        return res["data"]
    st.error(f"データベース通信エラー: {res.get('message', '不明なエラー')}")
    return {"drivers": [], "casts": [], "attendance": [], "settings": {}}

def clear_cache():
    st.cache_data.clear()

# =========================================
# 住所・判定系
# =========================================
def parse_address(addr_str):
    pref, city, rest = "", "", str(addr_str)

    for p in ["岡山県", "広島県", "香川県", "兵庫県"]:
        if rest.startswith(p):
            pref = p
            rest = rest[len(p):]
            break

    if pref == "岡山県":
        for c in [
            "岡山市北区", "岡山市中区", "岡山市東区", "岡山市南区",
            "倉敷市", "総社市", "玉野市", "瀬戸内市", "赤磐市",
            "浅口市", "笠岡市", "井原市"
        ]:
            if rest.startswith(c):
                city = c
                rest = rest[len(c):]
                break
    elif pref == "広島県":
        for c in ["福山市", "尾道市", "三原市", "府中市", "東広島市"]:
            if rest.startswith(c):
                city = c
                rest = rest[len(c):]
                break

    return pref, city, rest

def clean_address_for_map(addr_str):
    if not addr_str:
        return ""
    addr = str(addr_str).replace("　", " ").strip()

    if re.match(r'^[0-9\.]+\s*,\s*[0-9\.]+$', addr):
        return addr

    addr = addr.split(" ")[0]

    match1 = re.match(r'^(.*?[0-9０-９]+[-ー]+[0-9０-９]+(?:[-ー]+[0-9０-９]+)?).*', addr)
    if match1:
        return match1.group(1)

    match2 = re.match(r'^(.*?[0-9０-９]+(?:丁目|番|番地|号)).*', addr)
    if match2:
        return match2.group(1)

    return addr

def get_route_line_and_distance(addr_str):
    addr = str(addr_str).replace("　", " ")
    line, dist = "Route_Okayama_Center", 50

    if any(x in addr for x in ["福山", "笠岡", "井原"]):
        line, dist = "Route_West", 1000
    elif any(x in addr for x in ["倉敷", "総社", "玉島", "真備"]):
        line, dist = "Route_Kurashiki", 700
    elif any(x in addr for x in ["岡山市東区", "岡山市南区", "瀬戸内", "赤磐"]):
        line, dist = "Route_Okayama_EastSouth", 400
    elif any(x in addr for x in ["岡山市北区", "岡山市中区", "田町", "柳町", "磨屋町", "中央町"]):
        line, dist = "Route_Okayama_Center", 100
    elif any(x in addr for x in ["玉野"]):
        line, dist = "Route_Tamano", 500

    return line, dist

def is_in_range(val, rng):
    if rng == "全表示":
        return True
    try:
        return int(rng.split('-')[0]) <= int(val) <= int(rng.split('-')[1])
    except Exception:
        return False

# =========================================
# ルート計算
# =========================================
@st.cache_data(ttl=120)
def optimize_and_calc_route(api_key, store_addr, tasks_list, manual_order=False):
    if not tasks_list:
        return tasks_list, 0, 0, ""

    valid_tasks = []
    for t in tasks_list:
        addr = clean_address_for_map(t.get("pickup_addr", ""))
        if not addr:
            continue

        try:
            if api_key:
                dist_res = requests.get(
                    "https://maps.googleapis.com/maps/api/directions/json",
                    params={
                        "origin": store_addr,
                        "destination": addr,
                        "key": api_key,
                        "language": "ja"
                    },
                    timeout=8
                ).json()

                if dist_res.get("status") == "OK":
                    t["real_dist_from_store"] = dist_res["routes"][0]["legs"][0]["distance"]["value"]
                else:
                    _, backup_dist = get_route_line_and_distance(addr)
                    t["real_dist_from_store"] = backup_dist * 1000
            else:
                _, backup_dist = get_route_line_and_distance(addr)
                t["real_dist_from_store"] = backup_dist * 1000
        except Exception:
            _, backup_dist = get_route_line_and_distance(addr)
            t["real_dist_from_store"] = backup_dist * 1000

        valid_tasks.append(t)

    if not manual_order:
        valid_tasks.sort(key=lambda x: x.get("real_dist_from_store", 0), reverse=True)

    total_sec = 0
    first_leg_sec = 0
    api_error_msg = ""

    full_path = [clean_address_for_map(t.get("pickup_addr", "")) for t in valid_tasks if clean_address_for_map(t.get("pickup_addr", ""))]

    if full_path and api_key:
        params = {
            "origin": store_addr,
            "destination": store_addr,
            "key": api_key,
            "language": "ja",
            "departure_time": "now",
            "waypoints": "|".join(full_path),
        }
        try:
            res2 = requests.get(
                "https://maps.googleapis.com/maps/api/directions/json",
                params=params,
                timeout=12
            ).json()
            if res2.get("status") == "OK":
                legs = res2["routes"][0]["legs"]
                total_sec = sum(leg["duration"]["value"] for leg in legs)
                if legs:
                    first_leg_sec = legs[0]["duration"]["value"]
            else:
                api_error_msg = f"{res2.get('status')} - {res2.get('error_message', '')}"
        except Exception as e:
            api_error_msg = f"通信例外: {str(e)}"

    return valid_tasks, total_sec, first_leg_sec, api_error_msg

# =========================================
# 送迎更新
# =========================================
def recalc_route_for_driver(driver_name, base_arrival_time, store_addr):
    if not driver_name or driver_name == "未定":
        return

    db = get_db_data()
    casts = db.get("casts", [])
    attendance = db.get("attendance", [])

    my_rows = [
        r for r in attendance
        if r["target_date"] == "当日"
        and r["status"] == "出勤"
        and r.get("driver_name") == driver_name
    ]

    if not my_rows:
        return

    tasks = []
    for r in my_rows:
        c_info = next((c for c in casts if str(c["cast_id"]) == str(r["cast_id"])), {})
        pickup_addr = c_info.get("address", "")
        tasks.append({
            "task": r,
            "pickup_addr": pickup_addr,
            "cast_name": c_info.get("name", r["cast_name"]),
            "cast_id": r["cast_id"],
        })

    tasks.sort(key=lambda x: x["task"].get("pickup_time", "99:99"))
    ordered_tasks, total_sec, first_leg_sec, _ = optimize_and_calc_route(
        GOOGLE_MAPS_API_KEY,
        store_addr,
        tasks,
        manual_order=False
    )

    try:
        bh, bm = map(int, base_arrival_time.split(":"))
        b_mins = bh * 60 + bm
    except Exception:
        b_mins = 19 * 60 + 50

    total_casts = len(ordered_tasks)
    if total_casts == 0:
        return

    if total_sec == 0:
        interval_mins = 15
    else:
        interval_mins = max(1, (total_sec // 60) // (total_casts + 1))

    updates = []
    for idx, item in enumerate(ordered_tasks):
        mins_to_subtract = (total_casts - idx) * interval_mins
        t_mins = b_mins - mins_to_subtract
        if t_mins < 0:
            t_mins += 24 * 60
        pickup_time = f"{(t_mins // 60) % 24}:{t_mins % 60:02d}"
        updates.append({
            "id": item["task"]["id"],
            "driver_name": driver_name,
            "pickup_time": pickup_time
        })

    if updates:
        post_api({"action": "batch_update_dispatch", "updates": updates})

# =========================================
# UI共通
# =========================================
def render_top_nav():
    if st.session_state.page == "home":
        return
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🏠 ホーム", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
    with c2:
        if st.button("🔙 戻る", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
    with c3:
        if st.button("🚪 ログアウト", use_container_width=True):
            st.session_state.logged_in_cast = None
            st.session_state.logged_in_staff = None
            st.session_state.is_admin = False
            st.session_state.page = "home"
            st.rerun()
    st.markdown("<hr style='margin: 5px 0 15px 0; border-top: 1px dashed #ccc;'>", unsafe_allow_html=True)

# =========================================
# CSS
# =========================================
st.markdown("""
<style>
    html, body, [data-testid="stAppViewContainer"], .block-container {
        max-width: 100vw !important;
        overflow-x: hidden !important;
        background-color: #f0f2f5;
        font-family: -apple-system, sans-serif;
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
        border: 2px solid #000000 !important;
        border-radius: 6px !important;
        background-color: #ffffff !important;
    }
    div[role="radiogroup"] {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        justify-content: center;
        padding-bottom: 10px;
    }
    div[role="radiogroup"] > label {
        background-color: #ffffff !important;
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
</style>
""", unsafe_allow_html=True)

time_slots = [f"{h}:{m:02d}" for h in range(17, 27) for m in range(0, 60, 10)]
# =========================================
# ホーム
# =========================================
if st.session_state.page == "home":
    st.markdown("""
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
    """, unsafe_allow_html=True)

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
        unsafe_allow_html=True
    )
    st.markdown('<div class="footer">サーバー同期完了　　　最新データ受信</div>', unsafe_allow_html=True)

# =========================================
# キャストログイン
# =========================================
elif st.session_state.page == "cast_login":
    render_top_nav()
    db = get_db_data()
    casts = db.get("casts", [])

    st.markdown('<div class="app-header">キャストログイン</div>', unsafe_allow_html=True)
    st.caption("店番 または キャスト名を入力し、パスワードを入れてください")

    c_input = st.text_input("店番 または キャスト名", placeholder="例: 15 または さくら")
    pw = st.text_input("パスワード", type="password")

    if st.button("ログイン", type="primary", use_container_width=True):
        c_input_str = str(c_input).strip()
        if c_input_str:
            if c_input_str.isdigit():
                t = next((c for c in casts if str(c["cast_id"]) == c_input_str), None)
            else:
                t = next((c for c in casts if c_input_str == str(c.get("name", "")).strip()), None)

            if t:
                correct_pass = str(t.get("password", "")).strip().replace("None", "")
                if pw == correct_pass or not correct_pass:
                    st.session_state.logged_in_cast = {
                        "店番": str(t["cast_id"]),
                        "キャスト名": str(t["name"]),
                        "方面": t.get("area", "他"),
                        "担当": t.get("manager", "未設定")
                    }
                    st.session_state.page = "cast_mypage"
                    st.rerun()
                else:
                    st.error("⚠️ パスワードが違います。")
            else:
                st.error("⚠️ 該当するキャストが見つかりません。")
        else:
            st.warning("店番かキャスト名を入力してください。")

# =========================================
# 管理者ログイン
# =========================================
elif st.session_state.page == "admin_login":
    render_top_nav()
    db = get_db_data()
    settings = db.get("settings") or {}

    st.markdown('<div class="app-header">管理者ログイン</div>', unsafe_allow_html=True)
    pw = st.text_input("管理者パスワード", type="password")

    if st.button("ログイン", type="primary", use_container_width=True):
        admin_pass = str(settings.get("admin_password", "1234"))
        if pw == admin_pass:
            st.session_state.is_admin = True
            st.session_state.logged_in_staff = "管理者"
            st.session_state.page = "staff_portal"
            st.rerun()
        else:
            st.error("⚠️ パスワードが違います。")

# =========================================
# スタッフログイン
# =========================================
if st.session_state.page == "staff_portal":
    render_top_nav()
    db = get_db_data()
    drivers = db.get("drivers", [])

    st.markdown('<div class="app-header">スタッフログイン</div>', unsafe_allow_html=True)

    valid_drivers = [x for x in drivers if str(x.get("name", "")).strip() != ""]
    if not valid_drivers:
        st.warning("スタッフがまだ登録されていません。")
    else:
        for d in valid_drivers:
            st.markdown(
                f"<div style='font-weight:bold; margin-top:15px; border-bottom:2px solid #ddd; padding-bottom:5px; margin-bottom:10px;'>👤 {d['name']}</div>",
                unsafe_allow_html=True
            )
            colA, colB = st.columns([3, 1.2])
            with colA:
                p_in = st.text_input(
                    "PW",
                    type="password",
                    key=f"pw_{d['driver_id']}",
                    label_visibility="collapsed",
                    placeholder="パスワード"
                )
            with colB:
                if st.button("開始", key=f"b_{d['driver_id']}", type="primary", use_container_width=True):
                    if p_in in ["0000", str(d.get("password", "")).strip()]:
                        st.session_state.is_admin = False
                        st.session_state.logged_in_staff = str(d["name"])
                        st.session_state.page = "staff_portal"
                        st.rerun()
                    else:
                        st.error("❌ エラー")
            st.markdown("<div style='height: 30px;'></div>", unsafe_allow_html=True)

# =========================================
# キャストマイページ
# =========================================
elif st.session_state.page == "cast_mypage":
    render_top_nav()

    c = st.session_state.logged_in_cast
    db = get_db_data()
    settings = db.get("settings") or {}
    casts = db.get("casts", [])
    attendance = db.get("attendance", [])

    my_c = next((x for x in casts if str(x["cast_id"]) == str(c["店番"])), None)
    latest_name = my_c.get("name", c["キャスト名"]) if my_c else c["キャスト名"]

    st.markdown(
        f'<div style="text-align: center; font-weight: bold; font-size: 20px;">店番 {c["店番"]} {latest_name} 様</div>',
        unsafe_allow_html=True
    )

    bot_id = str(settings.get("line_bot_id", ""))
    line_uid = my_c.get("line_user_id", "") if my_c else ""

    if line_uid:
        st.markdown(
            '<div style="text-align:center; background:#e8f5e9; color:#2e7d32; padding:8px; border-radius:8px; margin-bottom:15px; font-weight:bold; font-size:14px; border:2px solid #4caf50;">✅ LINE通知：連携済み<br><span style="font-size:11px; font-weight:normal;">(配車決定などがLINEにお知らせされます)</span></div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<div style="text-align:center; background:#ffebee; color:#d32f2f; padding:8px; border-radius:8px; margin-bottom:15px; font-size:13px; border:2px solid #f44336;"><b>⚠️ LINE未連携</b><br>お店のLINE({bot_id})に<br>合言葉「<b>{c["店番"]}{c["キャスト名"]}</b>」とメッセージを送ってください。</div>',
            unsafe_allow_html=True
        )

    if settings.get("notice_text"):
        st.markdown(
            f'<div class="warning-content"><b>📢 お知らせ</b><br>{settings.get("notice_text","")}</div>',
            unsafe_allow_html=True
        )

    tab_today, tab_tmr, tab_week = st.tabs(["当日申請", "翌日申請", "週間申請"])

    # -----------------------------
    # 当日
    # -----------------------------
    with tab_today:
        m_tdy = next(
            (r for r in attendance if r["target_date"] == "当日" and str(r["cast_id"]) == str(c["店番"])),
            None
        )

        cur_status_today = m_tdy["status"] if m_tdy and m_tdy["status"] in ["未定", "出勤", "自走", "休み"] else "未定"
        memo_today = m_tdy.get("memo", "") if m_tdy else ""

        col_t1, col_t2 = st.columns([3, 1.2])
        with col_t1:
            s = st.radio(
                "状態",
                ["未定", "出勤", "自走", "休み"],
                index=["未定", "出勤", "自走", "休み"].index(cur_status_today),
                horizontal=True,
                key="tdy_s"
            )
            m = st.text_input("備考", value=memo_today, key="tdy_m")
        with col_t2:
            st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
            if st.button("📤 送信", type="primary", use_container_width=True, key="tdy_btn"):
                if s != "未定":
                    rec = {
                        "cast_id": c["店番"],
                        "cast_name": latest_name,
                        "area": c["方面"],
                        "status": s,
                        "memo": m,
                        "target_date": "当日"
                    }
                    res = post_api({"action": "save_attendance", "records": [rec]})
                    if res.get("status") == "success":
                        clear_cache()
                        st.session_state.page = "report_done"
                        st.rerun()
                    else:
                        st.error(res.get("message", "保存に失敗しました"))
                else:
                    st.warning("状態を選択してください。")

    # -----------------------------
    # 翌日
    # -----------------------------
    with tab_tmr:
        m_tmr = next(
            (r for r in attendance if r["target_date"] == "翌日" and str(r["cast_id"]) == str(c["店番"])),
            None
        )

        cur_status_tmr = m_tmr["status"] if m_tmr and m_tmr["status"] in ["未定", "出勤", "自走", "休み"] else "未定"
        memo_tmr = m_tmr.get("memo", "") if m_tmr else ""

        col_tm1, col_tm2 = st.columns([3, 1.2])
        with col_tm1:
            s_tmr = st.radio(
                "明日の状態",
                ["未定", "出勤", "自走", "休み"],
                index=["未定", "出勤", "自走", "休み"].index(cur_status_tmr),
                horizontal=True,
                key="tmr_s"
            )
            m_tmr_txt = st.text_input("明日の備考", value=memo_tmr, key="tmr_m")
        with col_tm2:
            st.markdown('<div style="height: 28px;"></div>', unsafe_allow_html=True)
            if st.button("📤 送信", type="primary", use_container_width=True, key="tmr_btn"):
                if s_tmr != "未定":
                    rec = {
                        "cast_id": c["店番"],
                        "cast_name": latest_name,
                        "area": c["方面"],
                        "status": s_tmr,
                        "memo": m_tmr_txt,
                        "target_date": "翌日"
                    }
                    res = post_api({"action": "save_attendance", "records": [rec]})
                    if res.get("status") == "success":
                        clear_cache()
                        st.session_state.page = "report_done"
                        st.rerun()
                    else:
                        st.error(res.get("message", "保存に失敗しました"))
                else:
                    st.warning("状態を選択してください。")

    # -----------------------------
    # 週間
    # -----------------------------
    with tab_week:
        weekly_data = []
        for i in range(1, 8):
            d = dt + datetime.timedelta(days=i)
            target_val = "翌日" if i == 1 else d.strftime("%Y-%m-%d")
            day_label = days_jp[d.weekday()]
            date_disp = "明日" if i == 1 else f"{d.month}/{d.day}({day_label})"

            m_w = next(
                (r for r in attendance if r["target_date"] == target_val and str(r["cast_id"]) == str(c["店番"])),
                None
            )
            cur_s = m_w["status"] if m_w and m_w["status"] in ["未定", "出勤", "自走", "休み"] else "未定"
            memo_w = m_w.get("memo", "") if m_w else ""

            st.write(f"**{date_disp}**")
            col_w1, col_w2 = st.columns([3, 1.2])
            with col_w1:
                w_att = st.radio(
                    "状態",
                    ["未定", "出勤", "自走", "休み"],
                    index=["未定", "出勤", "自走", "休み"].index(cur_s),
                    horizontal=True,
                    key=f"ws_{i}"
                )
                w_mem = st.text_input("備考", value=memo_w, key=f"wm_{i}")

            weekly_data.append({"date": target_val, "attend": w_att, "memo": w_mem})
            st.markdown("---")

        if st.button("📤 週間申請を一括送信", type="primary", use_container_width=True):
            records = []
            for w in weekly_data:
                if w["attend"] != "未定":
                    records.append({
                        "cast_id": c["店番"],
                        "cast_name": latest_name,
                        "area": c["方面"],
                        "status": w["attend"],
                        "memo": w["memo"],
                        "target_date": w["date"]
                    })
            if records:
                res = post_api({"action": "save_attendance", "records": records})
                if res.get("status") == "success":
                    clear_cache()
                    st.session_state.page = "report_done"
                    st.rerun()
                else:
                    st.error(res.get("message", "保存に失敗しました"))
            else:
                st.warning("1件以上、状態を選択してください。")

# =========================================
# 申請完了
# =========================================
elif st.session_state.page == "report_done":
    render_top_nav()
    st.markdown("<h1 style='text-align:center; margin-top:50px;'>✅</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align:center;'>出勤報告を受け付けました。</h3>", unsafe_allow_html=True)

    if st.button("マイページへ戻る", type="primary", use_container_width=True):
        st.session_state.page = "cast_mypage"
        st.rerun()
# =========================================
# キャスト編集カード
# =========================================
def render_cast_edit_card(c_id, c_name, pref, target_row, d_names_list, t_slots, loop_idx):
    key_suffix = f"{c_id}_{loop_idx}"

    if target_row:
        cur_status = target_row.get("status", "未定")
        cur_drv = target_row.get("driver_name", "未定") or "未定"
        cur_time = target_row.get("pickup_time", "未定") or "未定"
        cur_memo = target_row.get("memo", "")
    else:
        cur_status, cur_drv, cur_time, cur_memo = "未定", "未定", "未定", ""

    title_badge = "🚙 送迎" if cur_drv != "未定" else ("🏃 自走" if cur_status == "自走" else ("💤 休み" if cur_status == "休み" else "未定"))

    with st.expander(f"店番 {c_id} : {c_name} ({pref}) - {title_badge}"):
        col1, col2, col3 = st.columns(3)

        with col1:
            n_s = st.selectbox(
                "状態",
                ["未定", "出勤", "自走", "休み"],
                index=["未定", "出勤", "自走", "休み"].index(cur_status) if cur_status in ["未定", "出勤", "自走", "休み"] else 0,
                key=f"st_{key_suffix}"
            )
        with col2:
            n_d = st.selectbox(
                "ドライバー",
                ["未定"] + d_names_list,
                index=(["未定"] + d_names_list).index(cur_drv) if cur_drv in (["未定"] + d_names_list) else 0,
                key=f"drv_{key_suffix}"
            )
        with col3:
            n_t = st.selectbox(
                "時間",
                ["未定"] + t_slots,
                index=(["未定"] + t_slots).index(cur_time) if cur_time in (["未定"] + t_slots) else 0,
                key=f"tm_{key_suffix}"
            )

        new_memo = st.text_input("備考", value=cur_memo, key=f"memo_{key_suffix}")

        if st.button("💾 決定する", key=f"btn_upd_{key_suffix}", type="primary", use_container_width=True):
            if target_row:
                if n_s == "未定":
                    res = post_api({"action": "cancel_dispatch", "cast_id": c_id})
                else:
                    rec = {
                        "cast_id": c_id,
                        "cast_name": c_name,
                        "area": pref,
                        "status": n_s,
                        "memo": new_memo,
                        "target_date": "当日"
                    }
                    res = post_api({"action": "save_attendance", "records": [rec]})
                    if res.get("status") == "success" and n_s in ["出勤", "自走"]:
                        clear_cache()
                        db_after = get_db_data()
                        attendance_after = db_after.get("attendance", [])
                        new_row = next(
                            (r for r in attendance_after if r["target_date"] == "当日" and str(r["cast_id"]) == str(c_id)),
                            None
                        )
                        if new_row:
                            res = post_api({
                                "action": "update_dispatch",
                                "attendance_id": new_row["id"],
                                "pickup_time": n_t,
                                "driver_name": n_d
                            })
                if res.get("status") == "success":
                    clear_cache()
                    st.session_state.flash_msg = f"{c_name} 更新完了"
                    st.rerun()
                else:
                    st.error(res.get("message", "更新失敗"))
            else:
                if n_s == "未定":
                    st.warning("状態を選択してください。")
                else:
                    if n_s in ["出勤", "自走"]:
                        rec = {
                            "cast_id": c_id,
                            "cast_name": c_name,
                            "area": pref,
                            "status": n_s,
                            "memo": new_memo,
                            "target_date": "当日"
                        }
                        res = post_api({"action": "save_attendance", "records": [rec]})
                        if res.get("status") == "success":
                            clear_cache()
                            db_after = get_db_data()
                            attendance_after = db_after.get("attendance", [])
                            new_row = next(
                                (r for r in attendance_after if r["target_date"] == "当日" and str(r["cast_id"]) == str(c_id)),
                                None
                            )
                            if new_row:
                                res = post_api({
                                    "action": "update_dispatch",
                                    "attendance_id": new_row["id"],
                                    "pickup_time": n_t,
                                    "driver_name": n_d
                                })
                        if res.get("status") == "success":
                            clear_cache()
                            st.session_state.flash_msg = f"{c_name} 追加完了"
                            st.rerun()
                        else:
                            st.error(res.get("message", "追加失敗"))

# =========================================
# スタッフ・管理者ポータル
# =========================================
if st.session_state.page == "staff_portal":
    render_top_nav()

    staff_n = st.session_state.logged_in_staff
    is_adm = st.session_state.is_admin
    db = get_db_data()

    casts = db.get("casts", [])
    drvs = db.get("drivers", [])
    atts = db.get("attendance", [])
    sets = db.get("settings") or {}

    d_names = [str(d["name"]) for d in drvs if d.get("name")]
    store_addr = str(sets.get("store_address", DEFAULT_STORE_ADDRESS))
    base_arrival_time = str(sets.get("base_arrival_time", DEFAULT_BASE_ARRIVAL_TIME))
    current_hour, current_minute = dt.hour, dt.minute
    is_return_time = (current_hour > 20) or (current_hour == 20 and current_minute >= 30) or (current_hour <= 7)

    # --------------------------------------
    # ドライバー画面
    # --------------------------------------
    if not is_adm:
        st.markdown(f'<div class="date-header">{today_str} ({dow})</div>', unsafe_allow_html=True)

        d_info = next((d for d in drvs if str(d.get("name")) == staff_n), None)
        if d_info:
            bot_id = str(sets.get("line_bot_id", ""))
            line_uid = d_info.get("line_user_id", "")

            if line_uid:
                st.markdown(
                    '<div style="text-align:center; background:#e8f5e9; color:#2e7d32; padding:8px; border-radius:8px; margin-bottom:15px; font-size:13px; font-weight:bold;">✅ LINE通知連携済み</div>',
                    unsafe_allow_html=True
                )
            else:
                st.markdown(
                    f'<div style="text-align:center; background:#ffebee; color:#d32f2f; padding:8px; border-radius:8px; margin-bottom:15px; font-size:13px;"><b>⚠️ LINE未連携</b><br>お店のLINE({bot_id})に<br>合言葉「<b>STAFF{staff_n}</b>」と送信してください。</div>',
                    unsafe_allow_html=True
                )

            try:
                cur_cap = int(d_info.get("capacity", 4))
            except Exception:
                cur_cap = 4

            col_sn1, col_sn2 = st.columns([2, 1])
            with col_sn1:
                st.markdown(
                    f"<div style='font-size:20px; font-weight:bold; color:#333; margin-top:5px; margin-bottom:15px;'>👤 {staff_n} 班</div>",
                    unsafe_allow_html=True
                )
            with col_sn2:
                with st.popover(f"💺 定員: {cur_cap}名"):
                    n_cap = st.number_input("人数", min_value=1, max_value=10, value=cur_cap, key="temp_cap_input")
                    if st.button("変更を反映", type="primary", use_container_width=True):
                        res = post_api({
                            "action": "save_driver",
                            "driver_id": d_info["driver_id"],
                            "name": d_info["name"],
                            "password": d_info.get("password", ""),
                            "address": d_info.get("address", ""),
                            "phone": d_info.get("phone", ""),
                            "area": d_info.get("area", "全般"),
                            "capacity": n_cap
                        })
                        if res.get("status") == "success":
                            clear_cache()
                            st.rerun()
                        else:
                            st.error(res.get("message", "定員更新失敗"))

        my_tasks = []
        for t in atts:
            if t["target_date"] == "当日" and t["status"] in ["出勤", "自走"] and t.get("driver_name") == staff_n:
                if t["status"] != "自走":
                    my_tasks.append(t)

        if my_tasks:
            t_rows = sorted(
                my_tasks,
                key=lambda x: x.get("pickup_time", "99:99") if x.get("pickup_time") and x.get("pickup_time") != "未定" else "99:99"
            )

            list_html_head = '<div style="background:#444; color:white; padding:10px; font-weight:bold; border-radius:5px 5px 0 0;">🚕 通常便ルート</div><div style="background:#ffffff; border:1px solid #ccc; border-top:none; padding:10px; border-radius:0 0 5px 5px; margin-bottom:20px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">'

            tasks_with_details = []
            for t in t_rows:
                c_info = next((c for c in casts if str(c["cast_id"]) == str(t["cast_id"])), {})
                raw_addr = c_info.get("address", "")
                latest_name = c_info.get("name", t["cast_name"])
                tasks_with_details.append({
                    "task": t,
                    "pickup_addr": raw_addr,
                    "cast_name": latest_name,
                    "cast_id": t["cast_id"],
                    "home_addr": raw_addr
                })

            tasks_with_details.sort(key=lambda x: x["task"].get("pickup_time", "99:99"))
            st.markdown("<div style='font-size:12px; font-weight:bold; color:#e91e63; text-align:center; margin-bottom:5px;'>🤖 遠いキャストから拾いながら店舗に戻る想定ルートです</div>", unsafe_allow_html=True)

            ordered_tasks, total_sec, first_leg_sec, api_err = optimize_and_calc_route(
                GOOGLE_MAPS_API_KEY,
                store_addr,
                tasks_with_details,
                manual_order=True
            )

            list_html = list_html_head

            if not GOOGLE_MAPS_API_KEY:
                list_html += "<div style='font-size:14px; font-weight:bold; color:white; background:#f44336; padding:8px; border-radius:5px; margin-bottom:10px; text-align:center;'>🚨 Google Maps APIキー未設定のため簡易表示です</div>"
            else:
                earliest_m = 9999
                for t in ordered_tasks:
                    try:
                        pt = str(t["task"].get("pickup_time", ""))
                        if pt and pt != "未定":
                            h, m = map(int, pt.split(":"))
                            earliest_m = min(earliest_m, h * 60 + m)
                    except Exception:
                        pass

                if earliest_m != 9999:
                    dep_m = earliest_m - (first_leg_sec // 60) - 5
                    if dep_m < 0:
                        dep_m += 24 * 60
                    if 6 * 60 < dep_m < 16 * 60:
                        dep_m = 16 * 60
                    list_html += f"<div style='font-size:15px; font-weight:bold; color:#d32f2f; background:#ffebee; padding:8px; border-radius:5px; margin-bottom:10px; text-align:center; border: 1px solid #f44336;'>🚀 店舗出発時刻 (計算): {(dep_m // 60) % 24}:{dep_m % 60:02d}</div>"

            valid_path = [clean_address_for_map(t.get("pickup_addr", "")) for t in ordered_tasks if clean_address_for_map(t.get("pickup_addr", ""))]
            if valid_path:
                org_enc = urllib.parse.quote(store_addr)
                dest_enc = urllib.parse.quote(store_addr)
                wp_enc = urllib.parse.quote("/".join(valid_path))
                map_url = f"https://www.google.com/maps/dir/現在地/{wp_enc}/{dest_enc}"
                list_html += f"<a href='{map_url}' target='_blank' style='display:block;text-align:center;color:white;padding:10px;border-radius:8px;font-weight:bold;text-decoration:none;background:#4caf50;margin-bottom:15px;'>🗺️ スマホのナビで全行程を開始</a>"

            for idx, t in enumerate(ordered_tasks):
                addr_display = f"🏠 迎え: {t['home_addr'] if t['home_addr'] else '未登録'}"
                list_html += f"<div style='margin-bottom:8px;'><b>迎え順 {idx+1}： {t['task'].get('pickup_time','未定')}</b>　<span style='font-size:16px; font-weight:bold;'>{t['cast_name']}</span> <br><span style='font-size:13px;'>{addr_display}</span></div><hr style='margin:5px 0;'>"

            list_html += "</div>"
            st.markdown(list_html, unsafe_allow_html=True)

        else:
            st.info("本日の担当送迎はありません。")

    # --------------------------------------
    # 管理者画面
    # --------------------------------------
    else:
        tabs_list_admin = ["① 配車リスト", "② キャスト送迎", "③ キャスト登録", "④ STAFF設定", "⚙️ 管理設定"]
        current_tab = st.session_state.get("current_staff_tab", "① 配車リスト")
        try:
            tab_index = tabs_list_admin.index(current_tab)
        except ValueError:
            tab_index = 0

        selected_tab = st.radio(
            "メニュー",
            tabs_list_admin,
            index=tab_index,
            horizontal=True,
            label_visibility="collapsed"
        )
        st.session_state.current_staff_tab = selected_tab
        st.session_state.staff_tab = selected_tab

        st.markdown("<hr style='margin:10px 0;'>", unsafe_allow_html=True)
        range_opts = ["全表示"] + [f"{i*10+1}-{i*10+10}" for i in range(15)]

        # ==================================
        # ① 配車リスト
        # ==================================
        if selected_tab == "① 配車リスト":
            st.markdown(f'<div class="date-header">{today_str} 配車</div>', unsafe_allow_html=True)

            if not GOOGLE_MAPS_API_KEY:
                st.error("🚨 Google Maps APIキーが設定されていません。自動配車は簡易ロジックで動作します。")

            st.markdown(
                '<div style="background:#e8f5e9; border: 2px solid #4caf50; padding: 10px; border-radius: 8px; margin-bottom: 10px;"><div style="font-weight:bold; color:#2e7d32; font-size:16px; margin-bottom:5px;">🤖 自動配車</div><div style="font-size:12px; color:#555;">現在の当日出勤キャストを、定員を守りながら遠方優先で割り振ります。</div></div>',
                unsafe_allow_html=True
            )

            if not d_names:
                st.warning("⚠️ まだドライバーが登録されていません。「④ STAFF設定」タブを開いて登録してください。")
            else:
                if "active_drv_state" not in st.session_state:
                    st.session_state.active_drv_state = d_names

                valid_drv = [d for d in st.session_state.active_drv_state if d in d_names]

                def on_drv_change():
                    st.session_state.active_drv_state = st.session_state.active_drv_ms

                with st.expander("🛠️ 稼働ドライバーの選択 (タップで開く)", expanded=False):
                    active_drivers = st.multiselect(
                        "稼働するドライバーを選択",
                        d_names,
                        default=valid_drv,
                        key="active_drv_ms",
                        on_change=on_drv_change
                    )

                if st.button("🚀 AI自動配車 (ゼロベース再編成)", type="primary", use_container_width=True):
                    if not active_drivers:
                        st.error("稼働するドライバーを1人以上選択してください。")
                    else:
                        st.info("配車計算中... ⏳")

                        all_today_casts = []
                        seen_cids_ai = set()

                        for row in atts:
                            if row["target_date"] == "当日" and row["status"] in ["出勤", "自走"]:
                                cid_str = str(row["cast_id"])
                                if cid_str in seen_cids_ai:
                                    continue
                                seen_cids_ai.add(cid_str)

                                if row["status"] == "自走":
                                    continue

                                c_info = next((c for c in casts if str(c["cast_id"]) == str(row["cast_id"])), {})
                                raw_addr = c_info.get("address", "")
                                actual_pickup = raw_addr
                                line, dst = get_route_line_and_distance(actual_pickup)

                                all_today_casts.append({
                                    "row": row,
                                    "line": line,
                                    "dist": dst,
                                    "pickup_addr": actual_pickup
                                })

                        if not all_today_casts:
                            st.warning("⚠️ 当日出勤の配車対象者がいません。")
                        else:
                            all_today_casts.sort(key=lambda x: x["dist"], reverse=True)

                            drv_specs = {}
                            for d in drvs:
                                if d["name"] in active_drivers:
                                    try:
                                        cap = int(d.get("capacity", 4))
                                    except Exception:
                                        cap = 4
                                    drv_specs[d["name"]] = {
                                        "capacity": cap,
                                        "assigned_rows": [],
                                        "line": None,
                                        "area": d.get("area", "全般")
                                    }

                            for uc in all_today_casts:
                                assigned_d = None
                                c_line = uc["line"]

                                for d_name, stat in drv_specs.items():
                                    if len(stat["assigned_rows"]) >= stat["capacity"]:
                                        continue
                                    if stat["line"] is not None and stat["line"] != c_line:
                                        continue
                                    assigned_d = d_name
                                    break

                                if not assigned_d:
                                    for d_name, stat in drv_specs.items():
                                        if len(stat["assigned_rows"]) < stat["capacity"]:
                                            assigned_d = d_name
                                            break

                                if assigned_d:
                                    if drv_specs[assigned_d]["line"] is None:
                                        drv_specs[assigned_d]["line"] = c_line
                                    drv_specs[assigned_d]["assigned_rows"].append(uc)

                            try:
                                bh, bm = map(int, base_arrival_time.split(':'))
                                b_mins = bh * 60 + bm
                            except Exception:
                                b_mins = 19 * 60 + 50

                            updates = []
                            for d_name, stat in drv_specs.items():
                                assigned_list = stat["assigned_rows"]
                                if not assigned_list:
                                    continue

                                tasks = []
                                for item in assigned_list:
                                    c_info = next((c for c in casts if str(c["cast_id"]) == str(item["row"]["cast_id"])), {})
                                    latest_name = c_info.get("name", item["row"]["cast_name"])
                                    tasks.append({
                                        "task": item["row"],
                                        "pickup_addr": item["pickup_addr"],
                                        "cast_name": latest_name,
                                        "cast_id": item["row"]["cast_id"]
                                    })

                                ordered_tasks, total_sec, first_leg_sec, _ = optimize_and_calc_route(
                                    GOOGLE_MAPS_API_KEY,
                                    store_addr,
                                    tasks,
                                    manual_order=False
                                )

                                total_casts = len(ordered_tasks)
                                if total_casts == 0:
                                    continue

                                if total_sec == 0:
                                    interval_mins = 15
                                else:
                                    interval_mins = max(1, (total_sec // 60) // (total_casts + 1))

                                for idx, item in enumerate(ordered_tasks):
                                    mins_to_subtract = (total_casts - idx) * interval_mins
                                    t_mins = b_mins - mins_to_subtract
                                    if t_mins < 0:
                                        t_mins += 24 * 60
                                    current_calc_time = f"{(t_mins // 60) % 24}:{t_mins % 60:02d}"

                                    updates.append({
                                        "id": item["task"]["id"],
                                        "driver_name": d_name,
                                        "pickup_time": current_calc_time
                                    })

                            if updates:
                                res = post_api({"action": "batch_update_dispatch", "updates": updates})
                                if res.get("status") == "success":
                                    clear_cache()
                                    st.session_state.flash_msg = "自動配車が完了しました！"
                                    st.rerun()
                                else:
                                    st.error(res.get("message", "自動配車失敗"))
                            else:
                                st.warning("配車対象がありませんでした。")

            st.radio("表示", ["当日", "翌日", "週間"], horizontal=True, label_visibility="collapsed")

            unassigned, my_tasks = [], {}
            seen_cids_disp = set()
            for row in atts:
                if row["target_date"] == "当日" and row["status"] in ["出勤", "自走"]:
                    cid_str = str(row["cast_id"])
                    if cid_str in seen_cids_disp:
                        continue
                    seen_cids_disp.add(cid_str)

                    drv = row.get("driver_name", "")
                    if not drv or drv == "未定" or row["status"] == "自走":
                        if row["status"] != "自走":
                            unassigned.append(row)
                    else:
                        if drv not in my_tasks:
                            my_tasks[drv] = []
                        my_tasks[drv].append(row)

            if unassigned:
                unassigned_html = '<div class="warning-box">⚠️ 未割り当てキャスト</div><div class="warning-content">'
                for u in unassigned:
                    c_info = next((c for c in casts if str(c["cast_id"]) == str(u["cast_id"])), {})
                    latest_name = c_info.get("name", u["cast_name"])
                    unassigned_html += f"<div style='margin-bottom:5px;'><b>未割当</b>　<span style='font-size:16px; font-weight:bold; color:#d32f2f;'>{latest_name}</span> <br><span style='font-size:12px; color:#555;'>({u['status']})</span></div><hr style='margin:5px 0;'>"
                unassigned_html += "</div>"
                st.markdown(unassigned_html, unsafe_allow_html=True)

            course_idx = 1
            for d_name, t_rows in my_tasks.items():
                t_rows = sorted(
                    t_rows,
                    key=lambda x: x.get("pickup_time", "99:99") if x.get("pickup_time") and x.get("pickup_time") != "未定" else "99:99"
                )

                st.markdown(
                    f'<div style="background:#444; color:white; padding:10px; font-weight:bold; border-radius:5px 5px 0 0;">🚕 コース{course_idx}：{d_name}</div><div style="background:#ffffff; border:1px solid #ccc; border-top:none; padding:10px; border-radius:0 0 5px 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.05);">',
                    unsafe_allow_html=True
                )

                tasks_with_details = []
                for t in t_rows:
                    c_info = next((c for c in casts if str(c["cast_id"]) == str(t["cast_id"])), {})
                    raw_addr = c_info.get("address", "")
                    latest_name = c_info.get("name", t["cast_name"])
                    tasks_with_details.append({
                        "task": t,
                        "pickup_addr": raw_addr,
                        "cast_name": latest_name,
                        "cast_id": t["cast_id"],
                        "home_addr": raw_addr
                    })

                ordered_tasks, total_sec, first_leg_sec, _ = optimize_and_calc_route(
                    GOOGLE_MAPS_API_KEY,
                    store_addr,
                    tasks_with_details,
                    manual_order=True
                )

                if not GOOGLE_MAPS_API_KEY:
                    st.markdown(
                        "<div style='font-size:14px; font-weight:bold; color:white; background:#f44336; padding:8px; border-radius:5px; margin-bottom:10px; text-align:center;'>🚨 Google Maps APIキー未設定のため簡易表示です</div>",
                        unsafe_allow_html=True
                    )

                else:
                    earliest_m = 9999
                    for t in ordered_tasks:
                        try:
                            pt = str(t["task"].get("pickup_time", ""))
                            if pt and pt != "未定":
                                h, m = map(int, pt.split(":"))
                                earliest_m = min(earliest_m, h * 60 + m)
                        except Exception:
                            pass

                    if earliest_m != 9999:
                        dep_m = earliest_m - (first_leg_sec // 60) - 5
                        if dep_m < 0:
                            dep_m += 24 * 60
                        if 6 * 60 < dep_m < 16 * 60:
                            dep_m = 16 * 60
                        st.markdown(
                            f"<div style='font-size:15px; font-weight:bold; color:#d32f2f; background:#ffebee; padding:8px; border-radius:5px; margin-bottom:10px; text-align:center; border: 1px solid #f44336;'>🚀 店舗出発時刻 (計算): {(dep_m // 60) % 24}:{dep_m % 60:02d}</div>",
                            unsafe_allow_html=True
                        )

                valid_path = [clean_address_for_map(t.get("pickup_addr", "")) for t in ordered_tasks if clean_address_for_map(t.get("pickup_addr", ""))]
                if valid_path:
                    wp_enc = urllib.parse.quote("/".join(valid_path))
                    dest_enc = urllib.parse.quote(store_addr)
                    map_url = f"https://www.google.com/maps/dir/現在地/{wp_enc}/{dest_enc}"
                    st.markdown(
                        f"<a href='{map_url}' target='_blank' style='display:block;text-align:center;color:white;padding:10px;border-radius:8px;font-weight:bold;text-decoration:none;background:#4caf50;margin-bottom:15px;'>🗺️ スマホのナビで全行程を開始</a>",
                        unsafe_allow_html=True
                    )

                for idx, t in enumerate(ordered_tasks):
                    addr_display = f"🏠 迎え: {t['home_addr'] if t['home_addr'] else '未登録'}"
                    st.markdown(
                        f"<div style='margin-bottom:8px;'><b>迎え順 {idx+1}： {t['task'].get('pickup_time','未定')}</b>　<span style='font-size:16px; font-weight:bold;'>{t['cast_name']}</span> <br><span style='font-size:13px;'>{addr_display}</span></div><hr style='margin:5px 0;'>",
                        unsafe_allow_html=True
                    )

                st.markdown("</div>", unsafe_allow_html=True)
                course_idx += 1
        # ==================================
        # ② キャスト送迎
        # ==================================
        elif selected_tab == "② キャスト送迎":
            dispatch_count = 0
            today_active_casts = []
            seen_cids_today = set()

            for row in atts:
                if row["target_date"] == "当日" and row["status"] in ["出勤", "自走"]:
                    cid_str = str(row["cast_id"])
                    if cid_str in seen_cids_today:
                        continue
                    seen_cids_today.add(cid_str)
                    dispatch_count += 1

                    c_info_dict = next((c for c in casts if str(c["cast_id"]) == str(row["cast_id"])), {})
                    pref = c_info_dict.get("area", "他")
                    today_active_casts.append({
                        "id": row["cast_id"],
                        "name": row["cast_name"],
                        "status": row["status"],
                        "pref": pref,
                        "row": row
                    })

            today_active_casts = sorted(
                today_active_casts,
                key=lambda x: int(x["id"]) if str(x["id"]).isdigit() else 999
            )

            st.markdown(f'''
            <div style="background-color: #e3f2fd; border: 2px solid #2196f3; padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 10px;">
                <span style="font-size: 14px; color: #1565c0; font-weight: bold;">🚗 現在の送迎申請数（当日）</span><br>
                <span style="font-size: 24px; font-weight: bold; color: #e91e63;">{dispatch_count}</span>
                <span style="font-size: 16px; color: #1565c0; font-weight: bold;">名</span>
            </div>
            ''', unsafe_allow_html=True)

            show_active_casts = st.toggle(f"📋 当日の出勤キャストを表示する（{dispatch_count}名）")
            if show_active_casts:
                if today_active_casts:
                    list_search = st.text_input(
                        "🔍 一覧からキャストを絞り込み検索",
                        placeholder="名前 または 店番",
                        key="today_list_search"
                    )
                    st.markdown("<div style='margin-top:10px;'>", unsafe_allow_html=True)
                    display_c = 0
                    for loop_idx, c_dict in enumerate(today_active_casts):
                        c_id, c_name = str(c_dict["id"]), c_dict["name"]
                        if list_search and list_search not in c_name and list_search != c_id:
                            continue
                        display_c += 1

                        c_inf = next((c for c in casts if str(c["cast_id"]) == c_id), {})
                        latest_name = c_inf.get("name", c_name)

                        render_cast_edit_card(
                            c_id,
                            latest_name,
                            c_dict.get("pref", "他"),
                            c_dict.get("row"),
                            d_names,
                            time_slots,
                            loop_idx
                        )
                    if display_c == 0:
                        st.write("該当するキャストがいません。")
                    st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.info("本日の送迎申請はまだありません。")

            st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)

            if "search_cast_key" not in st.session_state:
                st.session_state.search_cast_key = 0
            if "active_search_query" not in st.session_state:
                st.session_state.active_search_query = ""

            st.markdown(
                "<div style='font-size:14px; font-weight:bold; color:#555; margin-bottom:5px;'>🔍 全キャスト検索 (未出勤者の予定追加・変更)</div>",
                unsafe_allow_html=True
            )

            col_search1, col_search2 = st.columns([3, 1])
            with col_search1:
                input_q = st.text_input(
                    "検索キーワード",
                    placeholder="名前 または 店番",
                    key=f"search_input_{st.session_state.search_cast_key}",
                    label_visibility="collapsed"
                )
            with col_search2:
                if st.button("検索", type="secondary", use_container_width=True):
                    st.session_state.active_search_query = input_q
                    st.rerun()

            act_rng = st.radio("範囲", range_opts, horizontal=True, label_visibility="collapsed")
            st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)

            search_query = st.session_state.active_search_query
            display_count = 0
            seen_all_cids = set()

            for loop_idx, cast in enumerate(casts):
                c_id, c_name = str(cast["cast_id"]), str(cast["name"])
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
                pref = str(cast.get("area", "他"))
                target_row = next(
                    (
                        row for row in atts
                        if row["target_date"] == "当日"
                        and row["status"] in ["出勤", "自走"]
                        and str(row["cast_id"]) == str(c_id)
                    ),
                    None
                )

                render_cast_edit_card(
                    c_id,
                    c_name,
                    pref,
                    target_row,
                    d_names,
                    time_slots,
                    loop_idx
                )

            if display_count == 0:
                st.info("条件に一致するキャストが見つかりません。")

        # ==================================
        # ③ キャスト登録
        # ==================================
        elif selected_tab == "③ キャスト登録":
            st.markdown('<div style="margin-bottom:15px;">', unsafe_allow_html=True)
            search_query_reg = st.text_input(
                "🔍 キャスト検索 (名前 または 店番)",
                placeholder="例: さくら, 94",
                key="search_cast_reg"
            )
            st.markdown("</div>", unsafe_allow_html=True)

            act_rng = st.radio("範囲", range_opts, horizontal=True, label_visibility="collapsed", key="reg_rng")
            existing = {str(c["cast_id"]): c for c in casts if str(c["cast_id"]) != ""}
            staff_list = ["未設定"] + d_names

            display_count = 0
            for i in range(1, 151):
                c = existing.get(
                    str(i),
                    {
                        "cast_id": i,
                        "name": "",
                        "phone": "",
                        "password": "0000",
                        "area": "",
                        "address": "",
                        "manager": "未設定",
                    }
                )

                nm = str(c.get("name", ""))
                mgr = str(c.get("manager", "未設定"))

                if search_query_reg:
                    if search_query_reg not in nm and search_query_reg != str(i):
                        continue
                else:
                    if not is_in_range(i, act_rng):
                        continue

                display_count += 1
                st.markdown(
                    "<div style='background:#fff; padding:10px; border-radius:8px; border:1px solid #ccc; margin-bottom:10px;'>",
                    unsafe_allow_html=True
                )

                col_title, col_mgr = st.columns([3, 2])
                with col_title:
                    st.markdown(
                        f"<div style='font-size:16px; font-weight:bold; margin-top:5px;'>店番 {i} : {nm if nm else '未登録'}</div>",
                        unsafe_allow_html=True
                    )
                with col_mgr:
                    mgr_idx = staff_list.index(mgr) if mgr in staff_list else 0
                    n_mgr = st.selectbox("担当", staff_list, index=mgr_idx, key=f"cmgr_{i}", label_visibility="collapsed")
                    if n_mgr != mgr:
                        res = post_api({
                            "action": "save_cast",
                            "cast_id": i,
                            "name": nm,
                            "password": str(c.get("password", "0000")),
                            "phone": str(c.get("phone", "")),
                            "area": str(c.get("area", "")),
                            "address": str(c.get("address", "")),
                            "manager": n_mgr
                        })
                        if res.get("status") == "success":
                            clear_cache()
                            st.rerun()

                with st.expander(f"詳細・住所設定 (店番 {i})"):
                    nn = st.text_input("名前", value=nm, key=f"cn_{i}")
                    raw_addr = str(c.get("address", ""))
                    p_pref, p_city, p_rest = parse_address(raw_addr)

                    c_pref = st.selectbox(
                        "県",
                        ["", "岡山県", "広島県", "香川県", "兵庫県"],
                        index=["", "岡山県", "広島県", "香川県", "兵庫県"].index(p_pref) if p_pref in ["", "岡山県", "広島県", "香川県", "兵庫県"] else 0,
                        key=f"c_pref_{i}"
                    )

                    c_opts = [""]
                    if c_pref == "岡山県":
                        c_opts = ["", "岡山市北区", "岡山市中区", "岡山市東区", "岡山市南区", "倉敷市", "総社市", "玉野市", "瀬戸内市", "赤磐市", "浅口市", "笠岡市", "井原市", "他"]
                    elif c_pref == "広島県":
                        c_opts = ["", "福山市", "尾道市", "三原市", "府中市", "東広島市", "他"]
                    elif c_pref == "香川県":
                        c_opts = ["", "他"]
                    elif c_pref == "兵庫県":
                        c_opts = ["", "他"]

                    colC1, colC2 = st.columns(2)
                    with colC1:
                        c_idx = c_opts.index(p_city) if p_city in c_opts else (c_opts.index("他") if p_city and "他" in c_opts else 0)
                        c_city = st.selectbox("市町村", c_opts, index=c_idx, key=f"c_city_{i}")
                    with colC2:
                        other_val = p_city if p_city and p_city not in c_opts else ""
                        c_other_city = st.text_input(
                            "「他」の場合の直接入力",
                            value=other_val,
                            key=f"c_other_city_{i}",
                            placeholder="例: 真庭市"
                        )

                    c_rest = st.text_input("町名・番地・建物名", value=p_rest, key=f"c_rest_{i}", placeholder="例: 田町2丁目11-15")
                    nt = st.text_input("電話番号", value=str(c.get("phone", "")), key=f"ct_{i}")
                    np = st.text_input("パスワード", value=str(c.get("password", "0000")), key=f"cp_{i}")

                    if st.button("保存する", key=f"cs_{i}", type="primary", use_container_width=True):
                        city_part = c_other_city if c_city == "他" else c_city
                        final_home = c_pref + city_part + c_rest
                        auto_area = "岡山" if c_pref == "岡山県" else ("広島" if c_pref == "広島県" else ("香川" if c_pref == "香川県" else "他"))

                        res = post_api({
                            "action": "save_cast",
                            "cast_id": i,
                            "name": nn,
                            "password": np,
                            "phone": nt,
                            "area": auto_area,
                            "address": final_home,
                            "manager": n_mgr
                        })
                        if res.get("status") == "success":
                            clear_cache()
                            st.success("保存しました！")
                            st.rerun()
                        else:
                            st.error(res.get("message", "保存失敗"))

                st.markdown("</div>", unsafe_allow_html=True)

            if display_count == 0:
                st.info("条件に一致するキャストが見つかりません。")

        # ==================================
        # ④ STAFF設定
        # ==================================
        elif selected_tab == "④ STAFF設定":
            exist_drvs = {str(d["driver_id"]): d for d in drvs}
            if "editing_staff_id" not in st.session_state:
                st.session_state.editing_staff_id = None

            if st.session_state.editing_staff_id is None:
                st.markdown('<div class="app-header">STAFF一覧・登録</div>', unsafe_allow_html=True)

                for i in range(1, 31):
                    d = exist_drvs.get(str(i), {})
                    nm, area = d.get("name", ""), d.get("area", "全般")
                    disp_nm = nm if nm else "(未登録)"
                    disp_area = f"[{area}]" if nm else ""

                    col1, col2 = st.columns([4, 1])
                    with col1:
                        st.markdown(
                            f"<div style='padding:10px 0; border-bottom:1px solid #ddd; font-size:15px;'><b>STAFF {i}</b> : {disp_nm} <span style='color:#666; font-size:12px;'>{disp_area}</span></div>",
                            unsafe_allow_html=True
                        )
                    with col2:
                        st.markdown("<div style='margin-top:5px;'></div>", unsafe_allow_html=True)
                        if st.button("詳細", key=f"edit_staff_btn_{i}", use_container_width=True):
                            st.session_state.editing_staff_id = i
                            st.rerun()
            else:
                i = st.session_state.editing_staff_id
                if st.button("🔙 STAFF一覧に戻る", use_container_width=True):
                    st.session_state.editing_staff_id = None
                    st.rerun()

                d = exist_drvs.get(str(i), {})
                nm = str(d.get("name", ""))

                st.markdown(
                    f'<div class="card" style="padding:15px; border-top: 4px solid #4caf50; margin-top:15px;">',
                    unsafe_allow_html=True
                )
                st.markdown(
                    f'<div style="font-weight:bold; font-size:18px; margin-bottom:15px;">✏️ STAFF {i} の詳細設定</div>',
                    unsafe_allow_html=True
                )

                d_area = str(d.get("area", "全般")).strip()
                area_opts = ["全般", "岡山方面", "倉敷方面", "岡山・倉敷方面", "広島方面", "他"]
                if d_area not in area_opts:
                    d_area = "全般"

                try:
                    d_cap = int(d.get("capacity", 4))
                except Exception:
                    d_cap = 4

                nn = st.text_input("STAFF名", value=nm, key=f"dn_{i}")
                colA, colB = st.columns(2)
                with colA:
                    n_area = st.selectbox("担当方面", area_opts, index=area_opts.index(d_area), key=f"d_ar_{i}")
                with colB:
                    n_cap = st.number_input("乗車定員", min_value=1, max_value=10, value=d_cap, key=f"d_cp_{i}")

                p_pref, p_city, p_rest = parse_address(str(d.get("address", "")))
                d_pref = st.selectbox(
                    "県",
                    ["", "岡山県", "広島県", "香川県", "兵庫県"],
                    index=["", "岡山県", "広島県", "香川県", "兵庫県"].index(p_pref) if p_pref in ["", "岡山県", "広島県", "香川県", "兵庫県"] else 0,
                    key=f"dpf_{i}"
                )

                d_opts = [""]
                if d_pref == "岡山県":
                    d_opts = ["", "岡山市北区", "岡山市中区", "岡山市東区", "岡山市南区", "倉敷市", "総社市", "玉野市", "瀬戸内市", "赤磐市", "浅口市", "笠岡市", "井原市", "他"]
                elif d_pref == "広島県":
                    d_opts = ["", "福山市", "尾道市", "三原市", "府中市", "東広島市", "他"]
                elif d_pref == "香川県":
                    d_opts = ["", "他"]
                elif d_pref == "兵庫県":
                    d_opts = ["", "他"]

                colC1, colC2 = st.columns(2)
                with colC1:
                    d_idx = d_opts.index(p_city) if p_city in d_opts else (d_opts.index("他") if p_city and "他" in d_opts else 0)
                    d_city = st.selectbox("市町村", d_opts, index=d_idx, key=f"dct_{i}")
                with colC2:
                    other_val = p_city if p_city and p_city not in d_opts else ""
                    d_other_city = st.text_input(
                        "「他」の場合の直接入力",
                        value=other_val,
                        key=f"d_other_city_{i}",
                        placeholder="例: 真庭市"
                    )

                d_rest = st.text_input("町名・番地・建物名", value=p_rest, key=f"drs_{i}")
                n_tel = st.text_input("電話番号", value=str(d.get("phone", "")), key=f"dt_{i}")
                n_pass = st.text_input("パスワード", value=str(d.get("password", "1234")), key=f"dp_{i}")

                if st.button("💾 決定する", key=f"ds_{i}", type="primary", use_container_width=True):
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
                        "capacity": n_cap
                    }
                    res = post_api(payload)
                    if res.get("status") == "success":
                        clear_cache()
                        st.success("保存しました！")
                        st.rerun()
                    else:
                        st.error(res.get("message", "保存失敗"))

                st.markdown("</div>", unsafe_allow_html=True)

        # ==================================
        # ⚙️ 管理設定
        # ==================================
        elif selected_tab == "⚙️ 管理設定":
            st.markdown('<div class="app-header" style="border:none;">📢 アプリ全体設定</div>', unsafe_allow_html=True)

            with st.form("adm_form"):
                s_notice = sets.get("notice_text", "") if isinstance(sets, dict) else ""
                s_pass = sets.get("admin_password", "1234") if isinstance(sets, dict) else "1234"
                s_line = sets.get("line_bot_id", "") if isinstance(sets, dict) else ""
                s_addr = sets.get("store_address", DEFAULT_STORE_ADDRESS) if isinstance(sets, dict) else DEFAULT_STORE_ADDRESS
                s_time = sets.get("base_arrival_time", DEFAULT_BASE_ARRIVAL_TIME) if isinstance(sets, dict) else DEFAULT_BASE_ARRIVAL_TIME

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
                        "base_arrival_time": n_time
                    })
                    if res.get("status") == "success":
                        clear_cache()
                        st.session_state.flash_msg = "設定を保存しました"
                        st.rerun()
                    else:
                        st.error(res.get("message", "保存失敗"))