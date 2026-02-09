import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import time

# --- 1. CONFIGURATION & CLOUD CONNECTION ---
st.set_page_config(page_title="PP Factory Master", layout="wide", initial_sidebar_state="expanded")
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
                df[c] = 0.0 if any(x in c for x in ["Count", "Price", "Weight", "Limit", "Target"]) else "N/A"
        return df
    except: return pd.DataFrame(columns=cols)

def save_data(df, key):
    ws = WS[key]
    ws.clear()
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
    st.divider()
    st.info(f"System Online\n{datetime.now().strftime('%d %b %H:%M')}")

# --- 4. MODULE: QUOTATION & SALES (WHATSAPP + PASSWORD) ---
if menu == "📝 Quotation & Sales":
    st.header("📝 Sales Quotation & WhatsApp")
    
    # 🔐 MANAGER CREDENTIALS
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}

    q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date"])
    c_df = load_data("CUST", ["Name", "Contact", "Phone"])
    
    # --- PART A: NEW QUOTE FORM ---
    with st.expander("➕ Create New Quotation", expanded=False):
        with st.form("new_quote"):
            c1, c2 = st.columns(2)
            cust_list = c_df["Name"].unique().tolist() if not c_df.empty else ["Cash Customer"]
            cust = c1.selectbox("Customer Name", cust_list)
            
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
                st.success("Quote Submitted!")
                st.rerun()

    # --- PART B: APPROVAL & WHATSAPP ---
    st.divider()
    col_q1, col_q2 = st.columns(2)
    
    with col_q1:
        st.subheader("📋 Manager Approval")
        pending = q_df[q_df["Status"] == "Pending Approval"]
        
        manager_pass = st.text_input("Manager Password (to Approve)", type="password", key="q_pass")
        is_auth = manager_pass in MANAGERS.values()

        if pending.empty:
            st.info("No pending quotes.")
        else:
            for idx, row in pending.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Doc_ID']}** | {row['Customer']}")
                    st.caption(f"{row['Product']} @ RM {row['Price']}")
                    
                    if is_auth:
                        if st.button("✅ APPROVE", key=f"app_{idx}"):
                            real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                            q_df.at[real_idx, "Status"] = "Approved"
                            save_data(q_df, "QUOTE")
                            st.rerun()
                    else:
                        st.button("🔒 Locked", disabled=True, key=f"lck_{idx}")

    with col_q2:
        st.subheader("📤 Send via WhatsApp")
        approved = q_df[q_df["Status"] == "Approved"]
        
        if approved.empty:
            st.info("No approved quotes ready.")
        else:
            for idx, row in approved.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Customer']}**")
                    st.caption(f"Quote {row['Doc_ID']} Ready")
                    
                    phone = "60123456789"
                    if not c_df.empty:
                        match = c_df[c_df["Name"] == row["Customer"]]
                        if not match.empty:
                            phone = str(match.iloc[0]["Phone"]).replace("+","").replace(" ","").replace("-","")
                    
                    msg = f"Hi *{row['Customer']}*,%0A%0AYour quote *{row['Doc_ID']}* for {row['Product']} is ready.%0A%0A💰 *Total: RM {row['Price']:,.2f}*%0A⚖️ Weight: {row['Weight']}kg%0A%0APlease reply to confirm.%0A%0A- *PP Products*"
                    st.link_button("📲 Open WhatsApp", f"https://wa.me/{phone}?text={msg}")

# --- 5. MODULE: PRODUCTION FLOOR (CAMERA SCANNING) ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Factory Production Control")
    
    # 📸 CAMERA SCANNER
    with st.expander("📸 Scan Job QR Code (For An Tu)", expanded=False):
        cam_val = st.camera_input("Hold QR Code up to Camera")
        if cam_val:
            # In a real app, you'd use a QR library (cv2/pyzbar) here.
            # Since Streamlit cloud can't easily do local CV without heavy setup,
            # we simulate the scan success for now or use the text input below.
            st.success("Image Captured! Processing...")
            # For this demo, we assume the camera worked and An Tu confirms the ID manually
            # or we rely on text input fallback for robustness.

    # Manual Search Fallback (Robustness)
    search_job = st.text_input("🔍 Or Enter Job ID manually (e.g. QT-2502...)")
    
    st.divider()

    t1, t2, t3, t4, t5 = st.tabs(["🔥 Extrusion", "📏 Trimming", "🎨 Printing", "⚙️ Die Cut (Mech)", "💧 Die Cut (Hydro)"])
    
    # --- Extrusion ---
    with t1:
        st.subheader("Amut & Ampang Lines")
        q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Status", "Weight"])
        
        # Filter by Search if active
        if search_job:
            relevant = q_df[q_df["Doc_ID"].str.contains(search_job, case=False)]
        else:
            relevant = q_df[q_df["Status"].isin(["Approved", "In Progress (Extrusion)"])]
            
        if relevant.empty: 
            st.info("No active extrusion jobs.")
        else:
            for idx, row in relevant.iterrows():
                with st.container(border=True):
                    c1, c2 = st.columns([3, 1])
                    c1.write(f"**{row['Doc_ID']}** | {row['Product']}")
                    c1.caption(f"Status: {row['Status']}")
                    
                    if row["Status"] == "Approved":
                        if c2.button("▶ START", key=f"ex_st_{idx}"):
                            # Update logic
                            real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                            q_df.at[real_idx, "Status"] = "In Progress (Extrusion)"
                            save_data(q_df, "QUOTE")
                            st.rerun()
                    elif "In Progress" in row["Status"]:
                        if c2.button("✅ FINISH", key=f"ex_fin_{idx}"):
                            real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                            q_df.at[real_idx, "Status"] = "Completed (Extrusion)"
                            save_data(q_df, "QUOTE")
                            st.rerun()

    # --- Trimming (Guillotine) ---
    with t2:
        st.subheader("Heidelberg Trimming")
        g_df = load_data("TRIM", ["Job_ID", "Status", "Target", "Count"])
        
        with st.form("trim_job"):
            jid = st.text_input("Job ID")
            tgt = st.number_input("Target Cuts", 100)
            if st.form_submit_button("Start Trim"):
                new_row = {"Job_ID": jid, "Status": "In Progress", "Target": tgt, "Count": 0}
                save_data(pd.concat([g_df, pd.DataFrame([new_row])], ignore_index=True), "TRIM")
                st.rerun()
        
        active = g_df[g_df["Status"] == "In Progress"]
        for idx, row in active.iterrows():
            st.write(f"**{row['Job_ID']}** - {row['Count']}/{row['Target']}")
            if st.button("Finish Trim", key=f"trim_{idx}"):
                g_df.at[idx, "Status"] = "Completed"
                save_data(g_df, "TRIM"); st.rerun()

    # --- Printing ---
    with t3:
        st.subheader("Silk Screen Printing")
        p_df = load_data("PRINT", ["Job_ID", "Machine", "Status", "Target", "Count"])
        st.dataframe(p_df[p_df["Status"] == "In Progress"])

    # --- Die Cutting ---
    with t4:
        st.subheader("Mechanical Die Cutters (A, B, C)")
        d_df = load_data("DIE", ["Job_ID", "Machine", "Status", "Target", "Count"])
        active_d = d_df[(d_df["Status"] == "In Progress") & (d_df["Machine"].str.contains("Die Cut"))]
        st.dataframe(active_d)

    with t5:
        st.subheader("Hydraulic Presses (01, 02)")
        h_df = load_data("DIE", ["Job_ID", "Machine", "Status", "Target", "Count"])
        active_h = h_df[(h_df["Status"] == "In Progress") & (h_df["Machine"].str.contains("Hydro"))]
        st.dataframe(active_h)

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
        st.info(f"Mix: **{v_kg:.1f}kg Virgin** + **{r_kg:.1f}kg Regrind**")

# --- 7. MODULE: MAINTENANCE (SECURE) ---
elif menu == "🔧 Maintenance":
    st.header("🔧 Maintenance Predictor")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}
    
    set_df = load_data("SETTINGS", ["Machine", "Type", "Threshold", "Last_Svc", "Current"])
    
    col_auth1, col_auth2 = st.columns(2)
    mgr = col_auth1.selectbox("Manager Auth", ["Select", "Iris", "Tomy"])
    pwd = col_auth2.text_input("Password", type="password", key="m_pwd")
    is_auth = mgr in MANAGERS and pwd == MANAGERS[mgr]
    
    if is_auth: st.success(f"🔓 Controls Unlocked for {mgr}")

    for idx, row in set_df.iterrows():
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 3, 2])
            c1.write(f"**{row['Machine']}**")
            c1.caption(row['Type'])
            
            # Simple Health Logic
            threshold = float(row['Threshold']) if row['Threshold'] else 50000.0
            last = float(row['Last_Svc']) if row['Last_Svc'] else 0.0
            curr = float(row['Current']) if row['Current'] else last + 1000.0
            health = max(0.0, 1.0 - ((curr - last)/threshold))
            
            c2.progress(health)
            c2.caption(f"{health*100:.0f}% Health Remaining")
            
            if is_auth:
                if c3.button("✅ RESET", key=f"rst_{idx}"):
                    set_df.at[idx, "Last_Svc"] = curr
                    save_data(set_df, "SETTINGS")
                    st.rerun()
            else:
                c3.button("🔒 Locked", disabled=True, key=f"l_{idx}")

# --- 8. MODULE: SCREENS & MOLDS ---
elif menu == "🎨 Screens & Molds":
    st.header("🗄️ Tooling Library")
    t1, t2 = st.tabs(["Die Molds", "Print Screens"])
    
    with t1:
        m_df = load_data("MOLDS", ["ID", "Location", "Status"])
        st.dataframe(m_df, use_container_width=True)
    with t2:
        s_df = load_data("SCREENS", ["ID", "Mesh", "Location"])
        st.dataframe(s_df, use_container_width=True)

# --- 9. MODULE: LEADERBOARD ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 Staff Performance")
    h_df = load_data("HANDOVER", ["Operator", "Output_kg"])
    if not h_df.empty:
        leaderboard = h_df.groupby("Operator")["Output_kg"].sum().sort_values(ascending=False)
        st.bar_chart(leaderboard)
    else:
        st.info("No data yet.")
