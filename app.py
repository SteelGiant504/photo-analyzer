import streamlit as st
from openai import OpenAI
from PIL import Image, ExifTags
import pandas as pd
import io
import json
import base64
from datetime import datetime

# StreamlitのシークレットからOpenAI APIキーを読み込む
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

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

def encode_image_to_base64(image):
    """画像をOpenAI APIに送るためにBase64形式に変換する関数"""
    buffered = io.BytesIO()
    # RGBAモード（透過PNGなど）の場合はRGBに変換
    if image.mode in ("RGBA", "P"):
        image = image.convert("RGB")
    # サイズを縮小してAPIの通信量とコストを節約
    image.thumbnail((1024, 1024))
    image.save(buffered, format="JPEG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

st.set_page_config(page_title="写真解析アプリ", layout="centered")
st.title("📸 写真解析＆Excel書き出しアプリ (PC版)")
st.write("パソコン内の写真を選択すると、Copilot(GPT-4o)が解析してExcelにまとめます。")

# PC前提なので、複数ファイルの一括アップロードをメインにする
uploaded_files = st.file_uploader(
    "解析したい写真をドラッグ＆ドロップ、または選択してください（複数選択可）", 
    type=["jpg", "jpeg", "png"], 
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"📁 {len(uploaded_files)} 枚の写真が選択されています。")
    
    if st.button("🚀 解析を開始する", type="primary"):
        results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i, file in enumerate(uploaded_files):
            status_text.text(f"解析中... ({i+1}/{len(uploaded_files)}枚目): {file.name}")
            
            # 画像を読み込み
            image = Image.open(file)
            shot_date = get_exif_date(image)
            
            # OpenAI用に画像をエンコード
            base64_image = encode_image_to_base64(image)
            
            try:
                # Copilotの頭脳である GPT-4o モデルに解析を依頼
                response = client.chat.completions.create(
                    model="gpt-4o",
                    response_format={ "type": "json_object" },
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ]
                )
                
                # 結果のJSON文字列を辞書型に変換
                response_text = response.choices[0].message.content
                ai_data = json.loads(response_text)
                
            except Exception as e:
                st.error(f"{file.name} の解析に失敗しました: {e}")
                ai_data = {"品物目": "", "色": "", "メーカー": "", "その他の特徴": ""}
            
            # 結果を追加
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
        
        # データを表に変換
        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)
        
        # Excelファイルの作成
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='解析結果')
            
            # Excelの列幅を少し見やすく調整（PC向けのおまけ機能）
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
                worksheet.column_dimensions[column].width = min(adjusted_width, 50) # 最大幅を50に制限
                
        # ダウンロードボタン
        st.download_button(
            label="📥 Excelファイルをダウンロード",
            data=output.getvalue(),
            file_name="photo_analysis_result.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary"
        )
