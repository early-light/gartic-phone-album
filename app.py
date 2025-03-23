import streamlit as st
from PIL import Image
import os
from io import BytesIO
import base64
import math

# === 設定 ===
BASE_DIR = "./images"
PASSWORD = st.secrets["auth"]["password"]
GIFS_PER_PAGE = 50

# ページレイアウトをワイドに設定
st.set_page_config(layout="wide")

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

# === サムネイル一覧表示 ===
def show_thumbnail_grid():
    st.title("Gartic Phone アルバム")

    date_folders = sorted([f for f in os.listdir(BASE_DIR) if os.path.isdir(os.path.join(BASE_DIR, f))], reverse=True)
    selected_date = st.sidebar.selectbox("日付を選択", date_folders)

    if "page_index" not in st.session_state:
        st.session_state.page_index = 0

    folder_path = os.path.join(BASE_DIR, selected_date)
    gif_files = sorted([f for f in os.listdir(folder_path) if f.endswith(".gif")])

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

            # 最初へ
            with nav_cols[0]:
                if st.button("最初へ", use_container_width=True):
                    st.session_state.page_index = 0
                    st.rerun()

            # p-1
            with nav_cols[1]:
                if current - 1 >= 0:
                    if st.button(str(current), use_container_width=True):
                        st.session_state.page_index = current - 1
                        st.rerun()
                else:
                    st.write("")

            # p
            with nav_cols[2]:
                st.button(str(current + 1), key=f"page_{current}", disabled=True, use_container_width=True)

            # p+1
            with nav_cols[3]:
                if current + 1 < total_pages:
                    if st.button(str(current + 2), use_container_width=True):
                        st.session_state.page_index = current + 1
                        st.rerun()
                else:
                    st.write("")

            # 最後へ
            with nav_cols[4]:
                if st.button("最後へ", use_container_width=True):
                    st.session_state.page_index = total_pages - 1
                    st.rerun()

    cols = st.columns(5)
    for i, gif in enumerate(page_gifs):
        gif_path = os.path.join(folder_path, gif)
        with Image.open(gif_path) as img:
            img.seek(0)
            thumbnail = img.copy().convert("RGBA")

        buf = BytesIO()
        thumbnail.save(buf, format="PNG")
        b64_thumb = base64.b64encode(buf.getvalue()).decode("utf-8")

        with cols[i % 5]:
            st.image(f"data:image/png;base64,{b64_thumb}", width=300)
            if st.button("見る", key=f"view_{selected_date}_{gif}"):
                st.session_state.selected_gif_path = gif_path
                st.session_state.page = "viewer"
                st.session_state.frame_index = 0
                st.rerun()

# === GIF閲覧ページ ===
def show_viewer():
    st.title("GIF スライドショー")
    gif_path = st.session_state.get("selected_gif_path")

    if not gif_path or not os.path.exists(gif_path):
        st.error("ファイルが見つかりません")
        return

    with Image.open(gif_path) as img:
        frames = []
        try:
            while True:
                frames.append(img.copy().convert("RGBA"))
                img.seek(len(frames))
        except EOFError:
            pass

    if "frame_index" not in st.session_state:
        st.session_state.frame_index = 0

    total_frames = len(frames)
    idx = st.session_state.frame_index

    buf = BytesIO()
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
