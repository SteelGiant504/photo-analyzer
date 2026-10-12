import streamlit as st
import google.generativeai as genai
from PIL import Image, ExifTags
import pandas as pd
import io
import json
import os
from datetime import datetime

# StreamlitのシークレットからGemini APIキーを読み込む
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# モデルは先ほど成功した最新版を指定
model = genai.GenerativeModel(
    'gemini-3.8-flash',
    generation_config={"response_mime_type": "application/json"}
)

PROMPT = """
この写真を解析し、以下の項目を特定してください。
わからない項目や写真に写っていない項目は必ず空白("")にしてください。
以下のJSONスキーマに厳密に従って出力してください。
{
    "品物目": "品物の一般的な名称",
    "色": "メインのカラー",
    "メーカー": "ロゴや特徴から推測できるメーカー名",
    "その他の特徴": "傷、形状、素材などの特徴"
}
"""

def get_exif_date(image):
    try:
        exif = image._getexif()
        if exif is not None:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == 'DateTimeOriginal':
                    return value.replace(':', '/', 2)
    except Exception:
        pass
    now = datetime.now()
    return now.strftime("%Y/%m/%d %H:%M:%S")

st.title("📸 写真解析＆Excel書き出しアプリ")
st.write("スマホで撮影した写真をアップロードすると、AIが解析してExcelにまとめます。")

# --- 状態保存（セッションステート）の準備 ---
if "all_photos" not in st.session_state:
    st.session_state.all_photos = []
if "final_df" not in st.session_state:
    st.session_state.final_df = None
if "excel_data" not in st.session_state:
    st.session_state.excel_data = None

upload_method = st.radio("写真の入力方法を選んでください", ("フォルダから選ぶ", "カメラで撮影する"))

uploaded_files = [] 

if upload_method == "フォルダから選ぶ":
    st.write("💡 スマホの制限で複数選択すると初期画面に戻ってしまう場合、1〜2枚ずつ選んでストックしてください。")
    if "folder_key" not in st.session_state:
        st.session_state.folder_key = 0
    files = st.file_uploader("写真を選択して追加", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key=f"folder_{st.session_state.folder_key}")
    
    if files:
        for f in files:
            st.session_state.all_photos.append(f)
        st.session_state.folder_key += 1
        st.rerun()
else:
    st.write("💡 撮影ボタンを押すたびに写真がストックされます。")
    if "camera_key" not in st.session_state:
        st.session_state.camera_key = 0
        
    camera_file = st.camera_input("カメラで撮影", key=f"camera_{st.session_state.camera_key}")
    
    if camera_file:
        st.session_state.all_photos.append(camera_file)
        st.session_state.camera_key += 1
        st.rerun()

if len(st.session_state.all_photos) > 0:
    st.success(f"📸 現在 {len(st.session_state.all_photos)} 枚の写真をストック中！")
    if st.button("🗑️ ストックを全て消去する"):
        st.session_state.all_photos = []
        st.session_state.final_df = None
        st.session_state.excel_data = None
        st.rerun()
    
    uploaded_files = st.session_state.all_photos

# --- 解析処理 ---
if uploaded_files:
    if st.button("🚀 解析を開始する"):
        results = []
        progress_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            progress_text.text(f"解析中... ({i+1}/{len(uploaded_files)}枚目): {file.name}")
            
            image = Image.open(file)
            shot_date = get_exif_date(image)
            
            # 💡重要：メモリ不足による強制終了を防ぐため、写真を縮小する
            image.thumbnail((1024, 1024))
            
            try:
                response = model.generate_content([PROMPT, image])
                ai_data = json.loads(response.text)
            except Exception as e:
                st.error(f"{file.name} の解析に失敗しました: {e}")
                ai_data = {"品物目": "", "色": "", "メーカー": "", "その他の特徴": ""}
            
            results.append({
                "写真撮影日": shot_date,
                "写真ファイル名": file.name,
                "品物目": ai_data.get("品物目", ""),
                "色": ai_data.get("色", ""),
                "メーカー": ai_data.get("メーカー", ""),
                "その他の特徴": ai_data.get("その他の特徴", "")
            })
            
        progress_text.text("✨ 解析が完了しました！")
        
        df = pd.DataFrame(results)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='解析結果')
        
        # 💡重要：解析結果とExcelデータを「保存（ストック）」して消えないようにする
        st.session_state.final_df = df
        st.session_state.excel_data = output.getvalue()

# --- 結果とダウンロードボタンの表示（ボタンの外に出す） ---
if st.session_state.final_df is not None:
    st.dataframe(st.session_state.final_df)
    st.download_button(
        label="📥 Excelファイルをダウンロード",
        data=st.session_state.excel_data,
        file_name="photo_analysis_result.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
