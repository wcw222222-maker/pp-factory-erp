import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import time
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# --- 1. CONFIGURATION & CLOUD CONNECTION ---
st.set_page_config(page_title="PP Factory Master", layout="wide", initial_sidebar_state="expanded")
SAP_BLUE = "#0070b1"

# CACHE THE CONNECTION (So we don't login 100 times)
@st.cache_resource
def get_db_connection():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # Open the sheet once and keep it open
        return client.open("PP_ERP_Database")
    except Exception as e:
        return None

# --- 2. DATA ENGINE (OPTIMIZED WITH CACHE) ---

# CACHE DATA FOR 5 SECONDS (Prevents Quota Error)
@st.cache_data(ttl=5)
def load_data(sheet_name):
    try:
        client = get_db_connection()
        if not client: return pd.DataFrame()
        
        # Only load the specific tab we need
        ws = client.worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        # If tab is empty or missing, return empty DF
        return pd.DataFrame()

def save_data(df, sheet_name):
    try:
        client = get_db_connection()
        ws = client.worksheet(sheet_name)
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        # CLEAR CACHE so the user sees the update immediately
        load_data.clear()
    except Exception as e:
        st.error(f"Save Failed: {e}")

# Helper to ensure columns exist (prevents KeyErrors)
def ensure_cols(df, cols):
    if df.empty: return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = 0.0 if any(x in c for x in ["Count", "Price", "Weight", "Limit", "Target"]) else "N/A"
    return df

# --- 3. PDF GENERATOR ENGINE ---
def generate_pdf(doc_type, data):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Header
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, "PP PRODUCTS SDN BHD")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 65, "28 Jalan Mas Jaya 3, Cheras 43200, Selangor")
    p.drawString(50, height - 80, "Tel: +603-9074-XXXX | Email: sales@ppproducts.com")
    p.line(50, height - 90, width - 50, height - 90)
    
    # Title
    p.setFont("Helvetica-Bold", 24)
    p.drawRightString(width - 50, height - 130, doc_type.upper())
    
    # Details
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 130, "Bill To:")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 145, f"{data['Customer']}")
    p.drawString(width - 200, height - 145, f"Date: {datetime.now().strftime('%d-%b-%Y')}")
    p.drawString(width - 200, height - 160, f"Ref: {data['Doc_ID']}")
    
    # Table
    y = height - 200
    p.setFillColor(colors.lightgrey)
    p.rect(50, y, width - 100, 20, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y + 6, "Description")
    p.drawString(300, y + 6, "Qty / Weight")
    if doc_type == "INVOICE":
        p.drawString(400, y + 6, "Unit Price")
        p.drawString(480, y + 6, "Total (RM)")
    
    y -= 25
    p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}")
    p.drawString(300, y, f"{data['Weight']} kg")
    
    if doc_type == "INVOICE":
        price = float(data['Price']) if data['Price'] else 0.0
        p.drawString(400, y, f"RM {price/float(data['Weight']):.2f}/kg" if float(data['Weight']) > 0 else "-")
        p.drawString(480, y, f"{price:,.2f}")
        y -= 40
        p.line(350, y, width - 50, y)
        y -= 20
        p.setFont("Helvetica-Bold", 12)
        p.drawRightString(width - 55, y, f"Total: RM {price * 1.06:,.2f}") # Incl 6% SST

    p.save()
    return buffer

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("☁️ PP PRODUCTS ERP")
    menu = st.radio("Navigation", [
        "📝 Quotation & Sales", 
        "🏭 Production Floor", 
        "📦 Warehouse & Mixing",
        "🚚 Logistics & Billing",
        "🎨 Screens & Molds",
        "🔧 Maintenance", 
        "🏆 Leaderboard"
    ])
    st.divider()
    st.info(f"System Online\n{datetime.now().strftime('%H:%M')}")

# --- 5. MODULE: QUOTATION & SALES ---
if menu == "📝 Quotation & Sales":
    st.header("📝 Sales Quotation")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}

    # Load Data Safely
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date"])
    c_df = ensure_cols(load_data("CUSTOMER"), ["Name", "Contact", "Phone"])
    
    with st.expander("➕ Create New Quotation", expanded=False):
        with st.form("new_quote"):
            c1, c2 = st.columns(2)
            cust_list = c_df["Name"].unique().tolist() if not c_df.empty else ["Cash Customer"]
            cust = c1.selectbox("Customer Name", cust_list)
            prod = c2.text_input("Product Spec")
            wgt = c1.number_input("Target Weight (kg)", 100.0)
            price = c2.number_input("Total Price (RM)", 0.0)
            
            if st.form_submit_button("Submit Quote"):
                new_row = {
                    "Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}",
                    "Customer": cust, "Product": prod, "Weight": wgt, "Price": price,
                    "Status": "Pending Approval", "Date": datetime.now().strftime("%Y-%m-%d")
                }
                save_data(pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True), "QUOTE")
                st.success("Quote Submitted!")
                st.rerun()

    st.divider()
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        st.subheader("📋 Approval Queue")
        pending = q_df[q_df["Status"] == "Pending Approval"]
        manager_pass = st.text_input("Manager Password", type="password", key="q_pass")
        is_auth = manager_pass in MANAGERS.values()

        if pending.empty: st.info("No pending quotes.")
        else:
            for idx, row in pending.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Doc_ID']}** | {row['Customer']}")
                    if is_auth:
                        if st.button("✅ APPROVE", key=f"app_{idx}"):
                            real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                            q_df.at[real_idx, "Status"] = "Approved"
                            save_data(q_df, "QUOTE"); st.rerun()
                    else: st.button("🔒 Locked", disabled=True, key=f"lck_{idx}")

    with col_q2:
        st.subheader("📤 WhatsApp")
        approved = q_df[q_df["Status"] == "Approved"]
        if not approved.empty:
            for idx, row in approved.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Customer']}** - {row['Doc_ID']}")
                    phone = "60123456789"
                    if not c_df.empty:
                        match = c_df[c_df["Name"] == row["Customer"]]
                        if not match.empty: phone = str(match.iloc[0]["Phone"]).replace("+","")
                    msg = f"Hi {row['Customer']}, Quote {row['Doc_ID']} for {row['Product']} (RM {row['Price']}) is ready."
                    st.link_button("📲 Send WhatsApp", f"https://wa.me/{phone}?text={msg}")

# --- 6. MODULE: PRODUCTION FLOOR ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Factory Production Control")
    with st.expander("📸 Scan Job QR Code"):
        cam_val = st.camera_input("Scan QR")
        if cam_val: st.success("Scanned! (Simulated)")
    
    st.divider()
    t1, t2, t3, t4, t5 = st.tabs(["🔥 Extrusion", "📏 Trimming", "🎨 Printing", "⚙️ Die Cut (Mech)", "💧 Die Cut (Hydro)"])
    
    # Extrusion View
    with t1:
        st.subheader("Amut & Ampang Lines")
        q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Status"])
        relevant = q_df[q_df["Status"].isin(["Approved", "In Progress (Extrusion)"])]
        if relevant.empty: st.info("No active jobs.")
        else:
            for idx, row in relevant.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Doc_ID']}** | {row['Product']}")
                    st.caption(row['Status'])
                    if row["Status"] == "Approved":
                        if st.button("▶ START", key=f"st_{idx}"):
                            real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                            q_df.at[real_idx, "Status"] = "In Progress (Extrusion)"
                            save_data(q_df, "QUOTE"); st.rerun()
                    elif "In Progress" in row["Status"]:
                        if st.button("✅ FINISH", key=f"fin_{idx}"):
                            real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                            q_df.at[real_idx, "Status"] = "Completed"
                            save_data(q_df, "QUOTE"); st.rerun()
    
    with t2: st.info("Heidelberg Module Active (Check Trim Tab in Sheet)")
    with t3: st.info("Printing Module Active")
    with t4: st.info("Die Cut Module Active")
    with t5: st.info("Hydraulic Module Active")

# --- 7. MODULE: LOGISTICS & BILLING ---
elif menu == "🚚 Logistics & Billing":
    st.header("🚚 Logistics Center")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status"])
    completed = q_df[q_df["Status"] == "Completed"]
    
    if completed.empty: st.info("No completed jobs ready for billing.")
    else:
        st.write("### ✅ Ready for Delivery")
        for idx, row in completed.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{row['Customer']}**")
                c1.caption(f"{row['Doc_ID']} | {row['Product']}")
                
                pdf_do = generate_pdf("DELIVERY ORDER", row)
                c2.download_button("📄 DO", pdf_do.getvalue(), f"DO_{row['Doc_ID']}.pdf", "application/pdf", key=f"do_{idx}")
                
                pdf_inv = generate_pdf("INVOICE", row)
                c3.download_button("💰 INV", pdf_inv.getvalue(), f"INV_{row['Doc_ID']}.pdf", "application/pdf", key=f"inv_{idx}")

# --- 8. MODULE: WAREHOUSE ---
elif menu == "📦 Warehouse & Mixing":
    st.header("📦 Inventory")
    i_df = ensure_cols(load_data("INVENTORY"), ["Item", "Stock_kg"])
    st.dataframe(i_df, use_container_width=True)

# --- 9. MODULE: MAINTENANCE ---
elif menu == "🔧 Maintenance":
    st.header("🔧 Maintenance")
    set_df = ensure_cols(load_data("SETTINGS"), ["Machine", "Last_Svc", "Threshold", "Type"])
    if set_df.empty: st.warning("Settings tab empty.")
    else:
        for idx, row in set_df.iterrows():
            with st.container(border=True):
                st.write(f"**{row['Machine']}** ({row['Type']})")
                st.progress(0.8) # Logic simplified for display

# --- 10. MODULE: LEADERBOARD ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 Staff Performance")
    h_df = ensure_cols(load_data("HANDOVER"), ["Operator", "Output_kg"])
    if not h_df.empty:
        st.bar_chart(h_df.groupby("Operator")["Output_kg"].sum())
