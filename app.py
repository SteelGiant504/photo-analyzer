import streamlit as st
import google.generativeai as genai
from PIL import Image, ExifTags
import pandas as pd
import io
import json
import os
from datetime import datetime  #

# StreamlitのシークレットからGemini APIキーを読み込む
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# Gemini 3.8 Flashモデルを直接指定（JSON形式で確実に出力させる）
model = genai.GenerativeModel(
    'gemini-3.8-flash',
    generation_config={"response_mime_type": "application/json"}
)

# AIへの指示（プロンプト）
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
    """画像からEXIFの撮影日を取得し、なければ現在の日時を返す関数"""
    try:
        exif = image._getexif()
        if exif is not None:
            for tag_id, value in exif.items():
                tag = ExifTags.TAGS.get(tag_id, tag_id)
                if tag == 'DateTimeOriginal':
                    # EXIFの日付フォーマット(YYYY:MM:DD HH:MM:SS)を少し整える
                    return value.replace(':', '/', 2)
    except Exception:
        pass
    
    # EXIFが取れなかった場合（ブラウザのカメラ撮影時など）は、現在の日時を返す
    now = datetime.now()
    return now.strftime("%Y/%m/%d %H:%M:%S")

# --- これより上のコード（importやget_exif_dateなど）はそのまま ---

st.title("📸 写真解析＆Excel書き出しアプリ")
st.write("スマホで撮影した写真をアップロードすると、AIが解析してExcelにまとめます。")

# --- ▼ここから下を丸ごと入れ替え▼ ---

# 撮影した写真を貯めておくための「箱」を準備する
if "camera_photos" not in st.session_state:
    st.session_state.camera_photos = []

# 写真の入力方法を選択（ラジオボタンで切り替え）
upload_method = st.radio("写真の入力方法を選んでください", ("フォルダから選ぶ", "カメラで撮影する"))

uploaded_files = [] # 最終的に解析に回す写真のリスト

if upload_method == "フォルダから選ぶ":
    # フォルダからの場合は、既存の複数選択機能を使う
    files = st.file_uploader("写真を選択してください", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    if files:
        uploaded_files = files
        # フォルダモードの時は、カメラのストックをリセットしておく
        st.session_state.camera_photos = [] 

else:
    # カメラ起動機能（連続撮影用）
    st.write("💡 **ヒント:** 撮影ボタンを押すたびに写真がストックされます。撮り終えたら下部の「解析を開始する」を押してください。")
    
    # 毎回新しいキーを生成することで、カメラウィジェットをリセットして連続撮影を可能にする
    if "camera_key" not in st.session_state:
        st.session_state.camera_key = 0
        
    camera_file = st.camera_input("カメラで撮影", key=f"camera_{st.session_state.camera_key}")
    
    if camera_file:
        # 撮影されたら、ストック（箱）に追加する
        st.session_state.camera_photos.append(camera_file)
        # 次の撮影ができるようにキーを更新
        st.session_state.camera_key += 1
        st.rerun() # 画面を再読み込みしてカメラを空にする
    
    # ストックされている写真の枚数を表示
    if len(st.session_state.camera_photos) > 0:
        st.success(f"📸 現在 {len(st.session_state.camera_photos)} 枚の写真をストック中！")
        # やり直しボタン
        if st.button("🗑️ ストックを全て消去する"):
            st.session_state.camera_photos = []
            st.rerun()
        
        # ストックされた写真を最終的な解析リストに入れる
        uploaded_files = st.session_state.camera_photos


# 共通の解析処理（ファイルがある場合のみ表示）
if uploaded_files:
    # ボタンを押して解析スタート
    if st.button("🚀 解析を開始する"):
        results = []
        progress_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            # ... (ここから下の for ループの中身やExcel出力の処理は元のままでOKです) ...
            progress_text.text(f"解析中... ({i+1}/{len(uploaded_files)}枚目): {file.name}")
            
            image = Image.open(file)
            shot_date = get_exif_date(image)
            
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
        st.dataframe(df)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='解析結果')
        output.seek(0)
        
        st.download_button(
            label="📥 Excelファイルをダウンロード",
            data=output,
            file_name="photo_analysis_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

