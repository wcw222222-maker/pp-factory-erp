import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- 1. CONFIGURATION & CLOUD CONNECTION ---
st.set_page_config(page_title="PP Factory Cloud", layout="wide")

SAP_BLUE = "#0070b1"
COMPANY_NAME = "PP PRODUCTS SDN BHD"

# This checks if we are on the Cloud or Local
# If local, it looks for the secrets file. If cloud, it uses Streamlit Secrets.
def get_db_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # Load credentials from Streamlit Secrets (Best for Cloud)
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    
    # Open the Google Sheet
    return client.open("PP_ERP_Database")

# Cached to prevent reloading every second
@st.cache_resource
def init_connection():
    return get_db_connection()

try:
    sh = init_connection()
    # Define Worksheets
    WORKSHEETS = {
        "QUOTE": sh.worksheet("QUOTE"),
        "SETTINGS": sh.worksheet("SETTINGS"),
        "INV": sh.worksheet("INVENTORY"),
        "MAINT_LOG": sh.worksheet("MAINTENANCE"),
        "MOLDS": sh.worksheet("MOLDS"),
        "SCREENS": sh.worksheet("SCREENS"),
        "DIE_JOBS": sh.worksheet("DIE_JOBS"),
        "PRINT_JOBS": sh.worksheet("PRINT_JOBS"),
        "GUILLOTINE_JOBS": sh.worksheet("GUILLOTINE_JOBS")
    }
except Exception as e:
    st.error(f"❌ Database Connection Failed: {e}")
    st.stop()

# --- 2. DATA ENGINE (CLOUD VERSION) ---
def load_data(sheet_key, cols):
    try:
        ws = WORKSHEETS[sheet_key]
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # If sheet is empty, create columns
        if df.empty:
            df = pd.DataFrame(columns=cols)
            
        # Ensure numeric columns are actually numbers (Google Sheets sometimes makes them strings)
        for c in cols:
            if c not in df.columns:
                df[c] = 0.0 if any(x in c for x in ["Count", "Limit", "Price", "Weight"]) else "N/A"
        return df
    except Exception as e:
        return pd.DataFrame(columns=cols)

def save_data(df, sheet_key):
    ws = WORKSHEETS[sheet_key]
    # Update entire sheet (Clear + Set)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

# --- 3. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title(f"☁️ {COMPANY_NAME}")
    st.success("🟢 Online: Google Database Connected")
    menu = st.radio("Navigation", ["🏭 Production Floor", "📦 Inventory & Mixing", "🔧 Maintenance", "⚙️ Admin"])

# --- 4. PRODUCTION FLOOR (Example Module) ---
if menu == "🏭 Production Floor":
    st.header("🏭 Cloud Production Control")
    
    t1, t2 = st.tabs(["🔥 Extrusion", "📏 Trimming"])
    
    with t1:
        st.subheader("Amut & Ampang Extruders")
        # Load Live Data from Cloud
        q_df = load_data("QUOTE", ["Job_ID", "Status", "Target", "Count"])
        
        # Display Jobs
        if not q_df.empty:
            st.dataframe(q_df, use_container_width=True)
            
            with st.expander("➕ Add New Job (Cloud)"):
                with st.form("new_job"):
                    jid = st.text_input("Job ID")
                    tgt = st.number_input("Target KG", 1000)
                    if st.form_submit_button("Upload to Database"):
                        new_row = {"Job_ID": jid, "Status": "Pending", "Target": tgt, "Count": 0}
                        # Append to DataFrame and Save
                        updated_df = pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True)
                        save_data(updated_df, "QUOTE")
                        st.success("Job Synced to Google Sheet!")
                        st.rerun()

# --- (Other Modules: Copy/Paste logic from previous versions, using load_data/save_data) ---