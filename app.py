import streamlit as st
import google.generativeai as genai
from PIL import Image, ExifTags
import pandas as pd
import io
import json
from datetime import datetime

# StreamlitのシークレットからGemini APIキーを読み込む
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])

# モデルは最新のGemini 3.8 Flashを指定
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
    """画像からEXIFの撮影日を取得し、なければ現在の日時を返す関数"""
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

# 画面を広く使う設定
st.set_page_config(page_title="写真解析アプリ", layout="wide")
st.title("📸 写真解析＆Excel書き出しアプリ (PC版)")
st.write("パソコンのフォルダから複数の写真をドラッグ＆ドロップで追加し、AIが解析してExcelにまとめます。")

# --- 状態保存（セッションステート）の準備 ---
if "final_df" not in st.session_state:
    st.session_state.final_df = None
if "excel_data" not in st.session_state:
    st.session_state.excel_data = None

# PC向け：シンプルなドラッグ＆ドロップ対応の複数ファイルアップローダー
uploaded_files = st.file_uploader(
    "解析したい写真をドラッグ＆ドロップ、または選択してください（Shiftキー/Ctrlキーで複数選択可）", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

# --- 解析処理 ---
if uploaded_files:
    st.info(f"📁 {len(uploaded_files)} 枚の写真が選択されています。")
    
    if st.button("🚀 解析を開始する", type="primary"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            status_text.text(f"解析中... ({i+1}/{len(uploaded_files)}枚目): {file.name}")
            
            image = Image.open(file)
            shot_date = get_exif_date(image)
            
            # メモリ不足と通信時間削減のため、写真を縮小する
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
            
            # プログレスバーを更新
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        status_text.success("✨ 全ての解析が完了しました！")
        
        df = pd.DataFrame(results)
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='解析結果')
            
            # PC向け：Excelの列幅を文字数に合わせて見やすく自動調整
            worksheet = writer.sheets['解析結果']
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column].width = min(adjusted_width, 50)
        
        # 解析結果を保存
        st.session_state.final_df = df
        st.session_state.excel_data = output.getvalue()

# --- 結果とダウンロードボタンの表示 ---
if st.session_state.final_df is not None:
    # 画面幅いっぱいに表を表示
    st.dataframe(st.session_state.final_df, use_container_width=True)
    st.download_button(
        label="📥 Excelファイルをダウンロード",
        data=st.session_state.excel_data,
        file_name="photo_analysis_result_pc.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )
