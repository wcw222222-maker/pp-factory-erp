import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURATION & CLOUD CONNECTION ---
st.set_page_config(page_title="PP Factory Cloud", layout="wide")
SAP_BLUE = "#0070b1"

# Connect to Google Sheets
@st.cache_resource
def get_db_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client.open("PP_ERP_Database")

try:
    sh = get_db_connection()
    # Map all worksheets
    WS = {
        "QUOTE": sh.worksheet("QUOTE"),
        "INV": sh.worksheet("INVENTORY"),
        "SETTINGS": sh.worksheet("SETTINGS"),
        "MAINT": sh.worksheet("MAINTENANCE"),
        "MOLDS": sh.worksheet("MOLDS"),
        "SCREENS": sh.worksheet("SCREENS"),
        "DIE": sh.worksheet("DIE_JOBS"),
        "PRINT": sh.worksheet("PRINT_JOBS"),
        "TRIM": sh.worksheet("GUILLOTINE_JOBS"),
        "HANDOVER": sh.worksheet("HANDOVER"),
        "SCRAP": sh.worksheet("SCRAP"),
        "CUST": sh.worksheet("CUSTOMER")
    }
except Exception as e:
    st.error(f"❌ Database Error: Missing Tab in Google Sheet. {e}")
    st.stop()

# --- 2. DATA ENGINE (CLOUD) ---
def load_data(key, cols):
    try:
        data = WS[key].get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=cols)
        # Force cols if missing
        for c in cols:
            if c not in df.columns: 
                df[c] = 0.0 if any(x in c for x in ["Count", "Price", "Weight", "Limit"]) else "N/A"
        return df
    except: return pd.DataFrame(columns=cols)

def save_data(df, key):
    ws = WS[key]
    ws.clear()
    # Write headers and data
    ws.update([df.columns.values.tolist()] + df.values.tolist())

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("☁️ PP PRODUCTS ERP")
    menu = st.radio("Navigation", [
        "📝 Quotation & Sales", 
        "🏭 Production Floor", 
        "📦 Warehouse & Mixing",
        "🎨 Screens & Molds",
        "🔧 Maintenance", 
        "🏆 Leaderboard"
    ])

# --- 4. MODULE: QUOTATION & SALES ---
if menu == "📝 Quotation & Sales":
    st.header("📝 Sales Quotation & Approval")
    
    q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date"])
    c_df = load_data("CUST", ["Name", "Contact"])
    
    # New Quote Form
    with st.expander("➕ Create New Quotation"):
        with st.form("new_quote"):
            c1, c2 = st.columns(2)
            cust = c1.text_input("Customer Name")
            prod = c2.text_input("Product Spec (e.g. 0.8mm White)")
            wgt = c1.number_input("Target Weight (kg)", 100.0)
            price = c2.number_input("Total Price (RM)", 0.0)
            
            if st.form_submit_button("Submit Quote"):
                new_row = {
                    "Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}",
                    "Customer": cust, "Product": prod, "Weight": wgt, "Price": price,
                    "Status": "Pending Approval", "Date": datetime.now().strftime("%Y-%m-%d")
                }
                updated = pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(updated, "QUOTE")
                st.success("Quote Saved!")
                st.rerun()

    # Approval Queue
    st.divider()
    st.subheader("📋 Approval Queue")
    pending = q_df[q_df["Status"] == "Pending Approval"]
    
    if pending.empty:
        st.info("No pending quotes.")
    else:
        for idx, row in pending.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{row['Customer']}** - {row['Product']} ({row['Weight']}kg)")
                c1.caption(f"Price: RM {row['Price']}")
                
                if c2.button("✅ Approve", key=f"app_{idx}"):
                    # Find original index in full dataframe to update
                    real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                    q_df.at[real_idx, "Status"] = "Approved / Pending Production"
                    save_data(q_df, "QUOTE")
                    st.rerun()

# --- 5. MODULE: PRODUCTION FLOOR (ALL DEPTS) ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Factory Production")
    t1, t2, t3, t4, t5 = st.tabs(["🔥 Extrusion", "📏 Trimming", "🎨 Printing", "⚙️ Die Cut (Mech)", "💧 Die Cut (Hydro)"])
    
    # --- Extrusion ---
    with t1:
        st.subheader("Amut & Ampang Lines")
        q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Status", "Weight"])
        approved = q_df[q_df["Status"] == "Approved / Pending Production"]
        
        if approved.empty: st.info("No approved jobs ready for extrusion.")
        else:
            for idx, row in approved.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Doc_ID']}** | {row['Product']}")
                    if st.button("▶ Start Extrusion", key=f"start_{idx}"):
                        real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                        q_df.at[real_idx, "Status"] = "In Progress (Extrusion)"
                        save_data(q_df, "QUOTE")
                        st.rerun()

    # --- Trimming (Guillotine) ---
    with t2:
        st.subheader("Heidelberg Trimming")
        g_df = load_data("TRIM", ["Job_ID", "Target", "Count", "Status"])
        # (Add your logic here or copy from previous snippets)
        st.info("Guillotine Module Active")

    # --- Printing ---
    with t3:
        st.subheader("Silk Screen Printing")
        p_df = load_data("PRINT", ["Job_ID", "Screen", "Status"])
        st.info("Printing Module Active")

    # --- Die Cutting ---
    with t4:
        st.subheader("Mechanical Die Cutters (A, B, C)")
        d_df = load_data("DIE", ["Job_ID", "Machine", "Status"])
        st.info("Mechanical Die Module Active")

    with t5:
        st.subheader("Hydraulic Presses (01, 02)")
        st.info("Hydraulic Module Active")

# --- 6. MODULE: WAREHOUSE ---
elif menu == "📦 Warehouse & Mixing":
    st.header("📦 Inventory & Resin Mixing")
    i_df = load_data("INV", ["Item", "Stock_kg", "Type"])
    s_df = load_data("SCRAP", ["Date", "Weight_kg"])
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Inventory Levels")
        st.dataframe(i_df, use_container_width=True)
    
    with col2:
        st.subheader("🧪 Resin Mixing Calculator")
        target = st.number_input("Batch Size (kg)", 500)
        virgin_pct = st.slider("Virgin %", 0, 100, 70)
        
        v_kg = target * (virgin_pct/100)
        r_kg = target - v_kg
        st.info(f"Mix: **{v_kg}kg Virgin** + **{r_kg}kg Regrind**")

# --- 7. MODULE: MAINTENANCE ---
elif menu == "🔧 Maintenance":
    st.header("🔧 Maintenance Predictor")
    set_df = load_data("SETTINGS", ["Machine", "Threshold", "Last_Svc"])
    
    if set_df.empty:
        # Initial Setup if empty
        data = [
            ["Amut Extruder", 50000, 0],
            ["Heidelberg 01", 5000, 0],
            ["Die Cut A", 100000, 0]
        ]
        set_df = pd.DataFrame(data, columns=["Machine", "Threshold", "Last_Svc"])
        save_data(set_df, "SETTINGS")
    
    for idx, row in set_df.iterrows():
        st.write(f"**{row['Machine']}**")
        st.progress(0.9) # Placeholder logic

# --- 8. MODULE: SCREENS & MOLDS ---
elif menu == "🎨 Screens & Molds":
    st.header("🗄️ Tooling Library")
    
    t1, t2 = st.tabs(["Die Molds", "Print Screens"])
    
    with t1:
        m_df = load_data("MOLDS", ["ID", "Location", "Status"])
        with st.form("new_mold"):
            mid = st.text_input("Mold ID")
            loc = st.text_input("Location")
            if st.form_submit_button("Add Mold"):
                new_row = {"ID": mid, "Location": loc, "Status": "Active"}
                updated = pd.concat([m_df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(updated, "MOLDS")
                st.rerun()
        st.dataframe(m_df)
    
    with t2:
        s_df = load_data("SCREENS", ["ID", "Mesh", "Location"])
        st.dataframe(s_df)

# --- 9. MODULE: LEADERBOARD ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 Staff Performance")
    h_df = load_data("HANDOVER", ["Operator", "Output_kg"])
    if not h_df.empty:
        leaderboard = h_df.groupby("Operator")["Output_kg"].sum().sort_values(ascending=False)
        st.bar_chart(leaderboard)
    else:
        st.info("No data yet.")
