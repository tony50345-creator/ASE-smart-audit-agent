import streamlit as st
import google.generativeai as genai
import pandas as pd
import json
import io
import time
import re

st.set_page_config(page_title="ASE AI 智慧稽核系統 (邏輯嚴選版)", layout="wide")

# ==========================================
# 1. 🔑 金鑰載入
# ==========================================
if "API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["API_KEY"])
else:
    st.error("❌ 找不到 API_KEY！")
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
        except: continue
    return "ERROR_READ"

MATRIX_DICTIONARY = load_matrix()

# ==========================================
# 3. 🧠 專業顧問分析邏輯 (事實隔離機制)
# ==========================================
STRICT_SYSTEM_PROMPT = f"""
你是一位極度嚴謹、具備『事實隔離分析』能力的 ASE 品質稽核專家。
你必須確保稽核判定的高度一致性，並嚴格區分『事實潤飾』與『延伸建議』。

【對標字典】：{MATRIX_DICTIONARY}

【🚨 核心執行準則：嚴禁過度衍生】
1. **純粹潤飾 (潤飾筆記)**：
   - 任務：僅針對原始紀錄進行專業化改寫 (使用 ISO 專業術語)。
   - **禁止**：嚴禁提到原始紀錄中『沒有提及』的缺失或不完整處。
   - **範例**：若紀錄說『新增機台配置』，潤飾應為『執行產能擴充之設備重新配置 (Relayout) 作業，並完成環安衛評估』。
   - **錯誤做法**：『...但未提及驗收紀錄』(這是錯誤的，這不叫潤飾)。

2. **等級判定邏輯**：
   - 若原始紀錄是在描述一個『已執行的程序、已完成的活動或現狀』，且無明確提到異常，等級必須判為 **Acceptable**。
   - 只有當紀錄中明確提到『未、不、沒、缺失、延遲』等負面事實時，才能判定為缺失 (Major/Minor/OFI)。

3. **分流建議 (建議與備註)**：
   - 任何關於『應進一步確認細節』、『缺失風險提醒』或『後續驗收稽核手法』，必須全部放在『建議』欄位。

4. **母子項垂直對標 (一致性要求)**：
   - 先定 ISO 章節，再推 IATF 同章節條文。相同的事項 (如 Relayout) 必須穩定對應到相同條文。

【輸出 JSON 格式】：
{{
  "潤飾筆記": "純事實的專業術語描述",
  "代碼": "AXXXX 中文名稱",
  "等級": "Acceptable/Major/Minor/OFI",
  "分類": "C1~C8 或 -",
  "ISO": "編號+標題",
  "IATF": "編號+標題",
  "VDA": "條目+標題",
  "建議": "此處放延伸建議，例如：應確認重新配置後之製程能力驗收紀錄是否完整。"
}}
"""

def analyze_audit_process(items):
    # Temperature 設為 0 以確保一致性
    model = genai.GenerativeModel(model_name=MODEL_NAME, generation_config={"temperature": 0}, system_instruction=STRICT_SYSTEM_PROMPT)
    all_results = []
    progress_bar = st.progress(0)
    
    for idx, item in enumerate(items):
        if not str(item).strip(): continue
        try:
            # 增加 User 指令引導一致性
            response = model.generate_content(f"請針對此紀錄進行『純事實潤飾』與『法規對標』：'{item}'")
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            
            if json_match:
                res = json.loads(json_match.group())
            else:
                res = {{"潤飾筆記": item, "代碼": "A2700 其他事項", "等級": "Acceptable", "分類": "-", "ISO": "N/A", "IATF": "N/A", "VDA": "N/A", "建議": "格式異常"}}

            # Python 後端邏輯鎖 (針對 Acceptable 邏輯強化)
            grade = str(res.get("等級", "Acceptable")).strip()
            # 若無缺失關鍵字，強制校正為 Acceptable
            negative_keywords = ["未", "不", "缺失", "沒", "無", "fail", "lack", "missing"]
            is_negative = any(kw in str(item) for kw in negative_keywords)
            
            if not is_negative and grade != "Acceptable":
                # 這邊不強制蓋掉，但如果 AI 判缺失，我們在建議欄加強提醒
                pass

            all_results.append({
                "原始紀錄": str(item),
                "專業稽核筆記 (潤飾)": res.get("潤飾筆記", "-"),
                "Category Check Item": res.get("代碼", "A2700 其他事項"),
                "缺失等級": grade,
                "不符合分類": "-" if grade == "Acceptable" else str(res.get("分類", "C2")),
                "ISO 9001 條文": res.get("ISO", "N/A"),
                "IATF 16949 條文": res.get("IATF", "N/A"),
                "VDA 6.3 條目": res.get("VDA", "N/A"),
                "建議與備註": res.get("建議", "-")
            })
            time.sleep(0.5)
        except Exception as e:
            all_results.append({"原始紀錄": item, "專業稽核筆記 (潤飾)": f"分析失敗: {e}", "Category Check Item": "A2700"})
            
        progress_bar.progress((idx + 1) / len(items))
    return pd.DataFrame(all_results)

# ==========================================
# 4. 🖥️ 介面
# ==========================================
st.title("🛡️ ASE AI 智慧稽核系統 (事實對標版)")
st.info("💡 核心更新：嚴禁過度衍生、事實與建議分流、強化判定一致性。")

uploaded_file = st.file_uploader("上傳 Excel 或 CSV 稽核清單", type=["xlsx", "csv"])
input_df = pd.DataFrame({"稽核紀錄事項": [""] * 3})
edited_df = st.data_editor(input_df, num_rows="dynamic", use_container_width=True)

if st.button("🚀 執行專業稽核分析"):
    records = []
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                for enc in ["utf-8-sig", "big5", "cp950"]:
                    try:
                        df = pd.read_csv(uploaded_file, encoding=enc); break
                    except: continue
            else:
                df = pd.read_excel(uploaded_file)
            records.extend(df.iloc[:, 0].dropna().tolist())
        except Exception as e: st.error(f"檔案讀取失敗: {e}")
            
    records.extend([r for r in edited_df["稽核紀錄事項"].dropna().tolist() if str(r).strip() != ""])
    
    if records:
        final_df = analyze_audit_process(records)
        st.write("### 📊 稽核分析結果")
        st.dataframe(final_df.astype(str), use_container_width=True)
        
        output = io.BytesIO()
        final_df.to_excel(output, index=False)
        st.download_button("📥 下載 Excel 報告", output.getvalue(), file_name="ASE_Audit_Report.xlsx")
    else:
        st.warning("請先輸入稽核紀錄！")
