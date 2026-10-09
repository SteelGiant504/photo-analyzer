import streamlit as st
import google.generativeai as genai
from PIL import Image, ExifTags
import pandas as pd
import io
import json
import os

# StreamlitのシークレットからGemini APIキーを読み込む
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# Gemini 1.5 Flashモデルの設定（JSON形式で確実に出力させる）
model = genai.GenerativeModel(
    'gemini-1.5-flash',
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
    """画像からEXIFの撮影日を取得する関数"""
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
    return ""

st.title("📸 写真解析＆Excel書き出しアプリ")
st.write("スマホで撮影した写真をアップロードすると、AIが解析してExcelにまとめます。")

# 写真のアップロード（複数枚対応）
uploaded_files = st.file_uploader("写真を選択してください", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    if st.button("🚀 解析を開始する"):
        results = []
        progress_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            progress_text.text(f"解析中... ({i+1}/{len(uploaded_files)}枚目): {file.name}")
            
            # 画像を読み込む
            image = Image.open(file)
            
            # EXIFから撮影日を取得
            shot_date = get_exif_date(image)

                        # Geminiに画像を投げて解析
            try:
                response = model.generate_content([PROMPT, image])
                ai_data = json.loads(response.text)
            except Exception as e:
                st.error(f"{file.name} の解析に失敗しました: {e}")
                ai_data = {"品物目": "", "色": "", "メーカー": "", "その他の特徴": ""}

            
            # 結果をリストにまとめる
            results.append({
                "写真撮影日": shot_date,
                "写真ファイル名": file.name,
                "品物目": ai_data.get("品物目", ""),
                "色": ai_data.get("色", ""),
                "メーカー": ai_data.get("メーカー", ""),
                "その他の特徴": ai_data.get("その他の特徴", "")
            })
            
        progress_text.text("✨ 解析が完了しました！")
        
        # データを表（データフレーム）に変換して画面に表示
        df = pd.DataFrame(results)
        st.dataframe(df)
        
        # Excelファイルの作成準備
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='解析結果')
        output.seek(0)
        
        # ダウンロードボタンの表示
        st.download_button(
            label="📥 Excelファイルをダウンロード",
            data=output,
            file_name="photo_analysis_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
