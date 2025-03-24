import streamlit as st
from PIL import Image
import io
import base64
import math
import os
import tempfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# === 設定 ===
IMAGES_PER_PAGE = 50
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

def list_image_sets(folder_id):
    service = get_drive_service()
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false",
        fields="files(id, name)"
    ).execute()
    files = results.get("files", [])

    image_sets = {}
    for f in files:
        if "_th.png" in f["name"]:
            key = f["name"].replace("_th.png", "")
            image_sets[key] = {"thumb": f}
        elif "_" in f["name"] and f["name"].endswith(".png"):
            base = f["name"].rsplit("_", 1)[0]
            image_sets.setdefault(base, {}).setdefault("frames", []).append(f)

    # フレームは順番に並べる
    for v in image_sets.values():
        if "frames" in v:
            v["frames"] = sorted(v["frames"], key=lambda x: x["name"])

    return image_sets

# === サムネイル一覧表示 ===
def show_thumbnail_grid():
    st.title("Gartic Phone アルバム")

    folders = list_date_folders()
    folder_options = {f["name"]: f["id"] for f in folders}
    selected_date = st.sidebar.selectbox("日付を選択", sorted(folder_options.keys(), reverse=True))

    if "page_index" not in st.session_state:
        st.session_state.page_index = 0

    folder_id = folder_options[selected_date]
    image_sets = list_image_sets(folder_id)
    keys = sorted(image_sets.keys())

    total_pages = math.ceil(len(keys) / IMAGES_PER_PAGE)
    current = st.session_state.page_index
    start = current * IMAGES_PER_PAGE
    end = start + IMAGES_PER_PAGE
    page_keys = keys[start:end]

    header_col1, header_col2 = st.columns([8, 2])
    with header_col1:
        st.subheader(f"{selected_date} のアルバム ({len(keys)} 件中 {start+1}〜{min(end, len(keys))})")
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
    for i, key in enumerate(page_keys):
        info = image_sets[key]
        thumb_path = load_image_from_drive_once(info["thumb"]["id"], info["thumb"]["name"])
        thumb = Image.open(thumb_path)
        buf = io.BytesIO()
        thumb.save(buf, format="PNG")
        b64_thumb = base64.b64encode(buf.getvalue()).decode("utf-8")

        with cols[i % 5]:
            st.image(f"data:image/png;base64,{b64_thumb}", width=300)
            if st.button("見る", key=f"view_{selected_date}_{key}"):
                st.session_state.selected_key = key
                st.session_state.selected_date = selected_date
                st.session_state.page = "viewer"
                st.session_state.frame_index = 0
                st.rerun()

# === GIF閲覧ページ ===
def show_viewer():
    st.title("GIF スライドショー")
    key = st.session_state.get("selected_key")
    date = st.session_state.get("selected_date")
    if not key or not date:
        st.error("GIFが選択されていません")
        return

    folders = list_date_folders()
    folder_id = {f["name"]: f["id"] for f in folders}.get(date)
    image_sets = list_image_sets(folder_id)
    frames = image_sets[key]["frames"]

    idx = st.session_state.get("frame_index", 0)
    img_path = load_image_from_drive_once(frames[idx]["id"], frames[idx]["name"])
    img = Image.open(img_path)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
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
