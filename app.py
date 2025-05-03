import streamlit as st
from PIL import Image
import io
import base64
import math
import os
import tempfile
import zipfile
from hashlib import md5
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# === 設定 ===
IMAGES_PER_PAGE = 50
PARENT_FOLDER_ID = "1NNXwYExNh-JRgV4e-UXH0xIUzDk8kVdM"  # images フォルダのID

st.set_page_config(layout="wide")

# --- Google Drive API 認証 ---
@st.cache_resource(show_spinner=False)
def get_drive_service():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=credentials)

# --- Driveファイル一覧と各ZIPの更新時間取得 ---
@st.cache_data(show_spinner=False)
def get_zip_file_info(guild_id: str):
    service = get_drive_service()
    prefix = f"{guild_id}_"
    results = service.files().list(
        q=f"'{PARENT_FOLDER_ID}' in parents and name contains '{prefix}' and trashed = false",
        fields="files(id, name, modifiedTime)",
        orderBy="name desc"
    ).execute()
    files = results.get("files", [])
    info = {}
    for f in files:
        if f["name"].endswith(".zip"):
            date = f["name"].replace(prefix, "").replace(".zip", "")
            info[date] = {
                "id": f["id"],
                "modified": f["modifiedTime"]
            }
    return info

# --- ZIPファイルをダウンロードして展開 ---
@st.cache_resource(show_spinner=False)
def extract_zip_for_date(guild_id: str, date_folder: str, file_id: str, modified_time: str):
    zip_name = f"{guild_id}_{date_folder}.zip"
    zip_temp_path = os.path.join(tempfile.gettempdir(), zip_name)
    extract_path = os.path.join(tempfile.gettempdir(), f"{guild_id}_{date_folder}_{md5(modified_time.encode()).hexdigest()}")

    if not os.path.exists(extract_path):
        service = get_drive_service()
        request = service.files().get_media(fileId=file_id)
        with open(zip_temp_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        with zipfile.ZipFile(zip_temp_path, "r") as zip_ref:
            zip_ref.extractall(extract_path)

    return extract_path

# --- GIF分解(PNGならそのまま) ---
@st.cache_data(show_spinner=False)
def split_gif_frames_once(image_path: str):
    img = Image.open(image_path)
    frames = []
    if image_path.lower().endswith(".gif"):
        try:
            while True:
                frame = img.copy().convert("RGB")
                frames.append(frame)
                img.seek(len(frames))
        except EOFError:
            pass
    else:
        frames.append(img.convert("RGB"))
    return frames

# --- ローカルから画像読み込み ---
def load_local_image(path: str):
    return Image.open(path).convert("RGB")

# === ログイン判定 ===
def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.markdown("""
            <style>
            .block-container {
                max-width: 500px;
                margin: auto;
            }
            </style>
        """, unsafe_allow_html=True)

        st.title("ログイン")
        server_options = {
            v["name"]: k for k, v in st.secrets["servers"].items()
        }
        server_name = st.selectbox("サーバー名を選択", options=list(server_options.keys()))
        pw = st.text_input("パスワードを入力", type="password")

        if st.button("ログイン"):
            guild_id = server_options[server_name]
            correct_pw = st.secrets["servers"][guild_id]["password"]
            if pw == correct_pw:
                st.session_state.logged_in = True
                st.session_state.guild_id = guild_id
                st.session_state.server_name = server_name
                st.rerun()
            else:
                st.error("パスワードが違います")
        st.stop()

# === ログアウト処理 ===
def logout_button():
    if st.sidebar.button("ログアウト"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

# === サムネイル一覧表示 ===
def show_thumbnail_grid():
    logout_button()
    st.title("Gartic Phone アルバム")

    guild_id = st.session_state.guild_id
    file_info = get_zip_file_info(guild_id)
    dates = sorted(file_info.keys(), reverse=True)
    selected_date = st.sidebar.selectbox("日付を選択", dates)

    if "page_index" not in st.session_state:
        st.session_state.page_index = 0

    selected_file_id = file_info[selected_date]["id"]
    modified_time = file_info[selected_date]["modified"]

    extract_path = extract_zip_for_date(guild_id, selected_date, selected_file_id, modified_time)
    gif_files = sorted([
        f for f in os.listdir(extract_path)
        if f.endswith(".gif") or f.endswith(".png")
    ])

    total_pages = math.ceil(len(gif_files) / IMAGES_PER_PAGE)
    current = st.session_state.page_index
    start = current * IMAGES_PER_PAGE
    end = start + IMAGES_PER_PAGE
    page_gifs = gif_files[start:end]

    header_col1, header_col2 = st.columns([8, 2])
    with header_col1:
        st.subheader(f"{selected_date} のアルバム ({len(gif_files)} 件中 {start+1}〜{min(end, len(gif_files))})")
    with header_col2:
        if total_pages > 1:
            nav_cols = st.columns([3.5, 1.5, 1.5, 1.5, 3.5])
            with nav_cols[0]:
                if st.button("最初へ", use_container_width=True):
                    st.session_state.page_index = 0
                    st.rerun()
            with nav_cols[1]:
                if current - 1 >= 0:
                    if st.button(str(current), use_container_width=True):
                        st.session_state.page_index = current - 1
                        st.rerun()
                else:
                    st.write("")
            with nav_cols[2]:
                st.button(str(current + 1), key=f"page_{current}", disabled=True, use_container_width=True)
            with nav_cols[3]:
                if current + 1 < total_pages:
                    if st.button(str(current + 2), use_container_width=True):
                        st.session_state.page_index = current + 1
                        st.rerun()
                else:
                    st.write("")
            with nav_cols[4]:
                if st.button("最後へ", use_container_width=True):
                    st.session_state.page_index = total_pages - 1
                    st.rerun()

    cols = st.columns(5)
    for i, gif_filename in enumerate(page_gifs):
        gif_path = os.path.join(extract_path, gif_filename)
        thumb = load_local_image(gif_path)
        thumb.thumbnail((300, 300))

        buf = io.BytesIO()
        thumb.save(buf, format="PNG")
        b64_thumb = base64.b64encode(buf.getvalue()).decode("utf-8")

        with cols[i % 5]:
            st.image(f"data:image/png;base64,{b64_thumb}", width=300)
            if st.button("見る", key=f"view_{selected_date}_{gif_filename}"):
                st.session_state.selected_gif = gif_filename
                st.session_state.selected_date = selected_date
                st.session_state.page = "viewer"
                st.session_state.frame_index = 0
                st.rerun()

# === GIF閲覧ページ ===
def show_viewer():
    logout_button()
    st.title("GIF スライドショー")
    gif_filename = st.session_state.get("selected_gif")
    date = st.session_state.get("selected_date")
    guild_id = st.session_state.get("guild_id")
    if not gif_filename or not date or not guild_id:
        st.error("GIFが選択されていません")
        return

    file_info = get_zip_file_info(guild_id)
    file_id = file_info[date]["id"]
    modified_time = file_info[date]["modified"]
    extract_path = extract_zip_for_date(guild_id, date, file_id, modified_time)
    gif_path = os.path.join(extract_path, gif_filename)
    frames = split_gif_frames_once(gif_path)

    idx = st.session_state.get("frame_index", 0)

    buf = io.BytesIO()
    frames[idx].save(buf, format="PNG")
    b64_img = base64.b64encode(buf.getvalue()).decode("utf-8")

    st.markdown(
        f"""
        <div style="text-align: center; margin: 30px 0;">
            <img src="data:image/png;base64,{b64_img}" width="770">
        </div>
        """,
        unsafe_allow_html=True
    )

    nav_cols = st.columns([1, 8, 1])
    with nav_cols[1]:
        nav_subcols = st.columns(len(frames) + 2)
        if nav_subcols[0].button("◀", use_container_width=True) and idx > 0:
            st.session_state.frame_index -= 1
            st.rerun()
        for i in range(len(frames)):
            label = f"{i+1}"
            if nav_subcols[i+1].button(label, use_container_width=True):
                st.session_state.frame_index = i
                st.rerun()
        if nav_subcols[-1].button("▶", use_container_width=True) and idx < len(frames) - 1:
            st.session_state.frame_index += 1
            st.rerun()

    if st.button("戻る"):
        st.session_state.page = "home"
        st.rerun()

# === メイン ===
check_login()

if "page" not in st.session_state:
    st.session_state.page = "home"

if st.session_state.page == "home":
    show_thumbnail_grid()
elif st.session_state.page == "viewer":
    show_viewer()
