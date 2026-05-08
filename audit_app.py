import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time
import re

st.set_page_config(page_title="ASE AI 智慧稽核系統 (專家顧問版)", layout="wide")

# ==========================================
# 1. 🔑 金鑰載入
# ==========================================
if "API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["API_KEY"])
else:
    st.error("❌ 找不到 API_KEY！請檢查 Secrets 設定。")
    st.stop()

MODEL_NAME = "models/gemini-2.5-flash" 

# ==========================================
# 2. 📂 讀取 ARR_checklist.csv
# ==========================================
@st.cache_data
def load_matrix():
    encodings = ["utf-8-sig", "big5", "cp950", "utf-8"]
    for enc in encodings:
        try:
            df = pd.read_csv("ARR_checklist.csv", encoding=enc)
            return df.to_string()
        except:
            continue
    return "ERROR_READ"

MATRIX_DICTIONARY = load_matrix()

# ==========================================
# 3. 🧠 專業顧問分析邏輯 (ISO老師潤飾 + C1~C8連動)
# ==========================================
STRICT_SYSTEM_PROMPT = f"""
你是一位資深的 ISO 專業首席稽核員。請根據以下規則進行深度分析：

【內部判定字典】：
{MATRIX_DICTIONARY}

【任務規則】：
1. **身分潤飾 (專業稽核筆記)**：請扮演專業 ISO 老師，將『原始紀錄』優化為言簡意賅、清楚扼要且專業的稽核描述。不可無中生有、不可過度衍生。
2. **法規判定**：請依據『潤飾後的描述』，從你的專家知識庫找出最相符的條文。
3. **條文格式**：只需呈現『條文編號 + 中文標題』。嚴禁重複出現國際標準名稱或版本(例如不要寫 ISO 9001:2015)。範例：『8.5.1 生產與服務提供之管制』。
4. **N/A 處理**：若找不到條文，填寫：『N/A (原因，例如：描述過於簡略或非QMS範疇)』。
5. **不符合分類 (C1~C8 邏輯)**：
   - 若等級為『Acceptable』，此欄位必須填『-』。
   - 若等級為缺失(Major/Minor/OFI)，請從以下代碼判定：
     C1: 系統未建立 / C2: 系統未落實 / C3: 系統不適切 / C4: 人員能力與意識不足 / C5: 資源不足 / C6: 監視與量測失效 / C7: 供應商管理失效 / C8: 風險評估與持續改善失效。
6. **備註 (建議)**：針對稽核事項點出 key point，例如應進一步確認的方向或更專業的詢問手法。

【🚨 JSON 輸出格式】：
{{
  "潤飾筆記": "專業潤飾後的描述",
  "代碼": "AXXXX 中文名稱",
  "等級": "Acceptable/Major/Minor/OFI",
  "分類": "C1~C8 代碼或 -",
  "ISO": "編號+標題或N/A(原因)",
  "IATF": "編號+標題或N/A(原因)",
  "VDA": "條目+標題或N/A(原因)",
  "建議": "精簡的稽核建議"
}}
"""

def analyze_audit_process(items):
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        generation_config={"temperature": 0},
        system_instruction=STRICT_SYSTEM_PROMPT
    )
    
    all_results = []
    progress_bar = st.progress(0)
    
    for idx, item in enumerate(items):
        if not str(item).strip(): continue
        try:
            response = model.generate_content(f"稽核事項：'{item}'")
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            
            if json_match:
                res = json.loads(json_match.group())
            else:
                res = {{"潤飾筆記": item, "代碼": "A2700 其他事項", "等級": "Acceptable", "分類": "-", "ISO": "N/A", "IATF": "N/A", "VDA": "N/A", "建議": "格式錯誤"}}

            # --- Python 後端強制邏輯檢核 ---
            grade = str(res.get("等級", "Acceptable")).strip()
            
            # 強制分類連動：Acceptable 一律為 -
            inconform_cat = str(res.get("分類", "-")).strip()
            if grade == "Acceptable":
                inconform_cat = "-"
            elif inconform_cat == "-" or "C" not in inconform_cat:
                inconform_cat = "C2" # 預設為未落實，若 AI 漏判

            all_results.append({
                "原始紀錄": str(item),
                "專業稽核筆記 (潤飾)": res.get("潤飾筆記", "-"),
                "Category Check Item": res.get("代碼", "A2700 其他事項"),
                "缺失等級": grade,
                "不符合分類": inconform_cat,
                "ISO 9001 條文": res.get("ISO", "N/A"),
                "IATF 16949 條文": res.get("IATF", "N/A"),
                "VDA 6.3 條目": res.get("VDA", "N/A"),
                "建議與備註": res.get("建議", "-")
            })
            time.sleep(0.5)
        except Exception as e:
            all_results.append({"原始紀錄": item, "專業稽核筆記 (潤飾)": f"異常: {e}", "Category Check Item": "A2700"})
            
        progress_bar.progress((idx + 1) / len(items))
    
    return pd.DataFrame(all_results)

# ==========================================
# 4. 🖥️ 介面
# ==========================================
st.title("🛡️ ASE AI 智慧稽核系統 (顧問版)")
st.info("💡 特色：專業潤飾描述 | C1~C8 自動連動 | 精確法規呈現 | 專家稽核建議")

uploaded_file = st.file_uploader("上傳 Excel 或 CSV 稽核清單", type=["xlsx", "csv"])
input_df = pd.DataFrame({"稽核紀錄事項": [""] * 3})
edited_df = st.data_editor(input_df, num_rows="dynamic", use_container_width=True)

if st.button("🚀 開始深度分析"):
    records = []
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
            records.extend(df.iloc[:, 0].dropna().tolist())
        except Exception as e:
            st.error(f"檔案讀取失敗: {e}")
            
    records.extend([r for r in edited_df["稽核紀錄事項"].dropna().tolist() if str(r).strip() != ""])
    
    if records:
        final_df = analyze_audit_process(records)
        st.write("### 📊 專家判定結果")
        st.dataframe(final_df.astype(str), use_container_width=True)
        
        output = io.BytesIO()
        final_df.to_excel(output, index=False)
        st.download_button("📥 下載完整分析報告", output.getvalue(), file_name="Audit_Expert_Report.xlsx")
    else:
        st.warning("請輸入稽核紀錄！")
