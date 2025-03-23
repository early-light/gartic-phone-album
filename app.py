import streamlit as st
from PIL import Image
import io
import base64
import math
import os
import tempfile
import imageio.v3 as iio
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# === 設定 ===
GIFS_PER_PAGE = 50
PASSWORD = st.secrets["auth"]["password"]
PARENT_FOLDER_ID = "1NNXwYExNh-JRgV4e-UXH0xIUzDk8kVdM"

# ページレイアウトをワイドに設定
st.set_page_config(layout="wide")

# --- Google Drive API 認証（キャッシュ） ---
@st.cache_resource(show_spinner=False)
def get_drive_service():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["google_service_account"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=credentials)

# --- Google Drive から画像をダウンロード（キャッシュ） ---
@st.cache_resource(show_spinner=False)
def load_image_from_drive_once(drive_file_id: str, filename: str) -> str:
    tmp_path = os.path.join(tempfile.gettempdir(), filename)

    if not os.path.exists(tmp_path):
        service = get_drive_service()
        request = service.files().get_media(fileId=drive_file_id)
        with open(tmp_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    return tmp_path

# --- GIFのフレーム分割（キャッシュ） ---
@st.cache_data(show_spinner=False)
def split_gif_frames_once(path: str):
    return list(iio.imread(path))

# --- サムネイル縮小（キャッシュ） ---
@st.cache_data(show_spinner=False)
def load_and_resize_thumbnail(path: str, size=(330, 256)):
    img = Image.open(path)
    img.thumbnail(size)
    return img

# === ログイン判定 ===
def check_login():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.markdown(
            """
            <style>
            .block-container {
                max-width: 500px;
                margin: auto;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        st.title("ログイン")
        pw = st.text_input("パスワードを入力", type="password")
        if st.button("ログイン"):
            if pw == PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        st.stop()

# --- Google Drive 操作 ---
def list_date_folders():
    service = get_drive_service()
    results = service.files().list(
        q=f"'{PARENT_FOLDER_ID}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name)",
        orderBy="name desc"
    ).execute()
    return results.get("files", [])

def list_gif_files(folder_id):
    service = get_drive_service()
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType='image/gif' and trashed=false",
        fields="files(id, name)",
        orderBy="name"
    ).execute()
    return results.get("files", [])

# === サムネイル一覧表示 ===
def show_thumbnail_grid():
    st.title("Gartic Phone アルバム")

    folders = list_date_folders()
    folder_options = {f["name"]: f["id"] for f in folders}
    selected_date = st.sidebar.selectbox("日付を選択", sorted(folder_options.keys(), reverse=True))

    if "page_index" not in st.session_state:
        st.session_state.page_index = 0

    folder_id = folder_options[selected_date]
    gif_files = list_gif_files(folder_id)

    total_pages = math.ceil(len(gif_files) / GIFS_PER_PAGE)
    current = st.session_state.page_index
    start = current * GIFS_PER_PAGE
    end = start + GIFS_PER_PAGE
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
    for i, gif in enumerate(page_gifs):
        gif_path = load_image_from_drive_once(gif["id"], gif["name"])
        thumb_img = load_and_resize_thumbnail(gif_path)

        buf = io.BytesIO()
        thumb_img.save(buf, format="PNG")
        b64_thumb = base64.b64encode(buf.getvalue()).decode("utf-8")

        with cols[i % 5]:
            st.image(f"data:image/png;base64,{b64_thumb}", width=300)
            if st.button("見る", key=f"view_{selected_date}_{gif['id']}"):
                st.session_state.selected_gif_id = gif["id"]
                st.session_state.gif_name = gif["name"]
                st.session_state.page = "viewer"
                st.session_state.frame_index = 0
                st.rerun()

# === GIF閲覧ページ ===
def show_viewer():
    st.title("GIF スライドショー")
    gif_id = st.session_state.get("selected_gif_id")
    gif_name = st.session_state.get("gif_name")

    if not gif_id or not gif_name:
        st.error("GIFが選択されていません")
        return

    gif_path = load_image_from_drive_once(gif_id, gif_name)
    frames = split_gif_frames_once(gif_path)

    if "frame_index" not in st.session_state:
        st.session_state.frame_index = 0

    total_frames = len(frames)
    idx = st.session_state.frame_index

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
        nav_subcols = st.columns(total_frames + 2)
        if nav_subcols[0].button("◀", use_container_width=True) and idx > 0:
            st.session_state.frame_index -= 1
            st.rerun()
        for i in range(total_frames):
            label = f"{i+1}"
            if nav_subcols[i+1].button(label, use_container_width=True):
                st.session_state.frame_index = i
                st.rerun()
        if nav_subcols[-1].button("▶", use_container_width=True) and idx < total_frames - 1:
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
