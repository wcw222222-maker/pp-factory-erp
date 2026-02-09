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

# CACHE THE CONNECTION (Prevents "Quota Exceeded" error)
@st.cache_resource
def get_db_connection():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("PP_ERP_Database")
    except Exception as e:
        return None

# --- 2. DATA ENGINE (OPTIMIZED) ---
@st.cache_data(ttl=5) 
def load_data(sheet_name):
    try:
        client = get_db_connection()
        if not client: return pd.DataFrame()
        ws = client.worksheet(sheet_name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        return df
    except:
        return pd.DataFrame()

def save_data(df, sheet_name):
    try:
        client = get_db_connection()
        ws = client.worksheet(sheet_name)
        
        # CLEAN DATA: Replace NaN/Errors with empty strings so Google Sheets accepts it
        df = df.fillna("") 
        
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        load_data.clear() 
    except Exception as e:
        st.error(f"Save Error: {e}")

# Helper to prevent crashes if columns are missing
def ensure_cols(df, cols):
    if df.empty: return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            is_num = any(x in c for x in ["Count", "Price", "Weight", "Limit", "Target", "Width", "Length", "Thick"])
            df[c] = 0.0 if is_num else "N/A"
    return df

# --- 3. PDF GENERATOR ---
def generate_pdf(doc_type, data):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, "PP PRODUCTS SDN BHD")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 65, "28 Jalan Mas Jaya 3, Cheras 43200, Selangor")
    p.line(50, height - 90, width - 50, height - 90)
    p.setFont("Helvetica-Bold", 24)
    p.drawRightString(width - 50, height - 130, doc_type.upper())
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 145, f"Customer: {data['Customer']}")
    p.drawString(width - 200, height - 145, f"Date: {datetime.now().strftime('%d-%b-%Y')}")
    p.drawString(width - 200, height - 160, f"Ref: {data['Doc_ID']}")
    y = height - 200
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y, "Product / Spec")
    p.drawString(300, y, "Weight (kg)")
    if doc_type == "INVOICE": p.drawString(480, y, "Total (RM)")
    y -= 20
    p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}")
    p.drawString(300, y, f"{data['Weight']:.2f}")
    if doc_type == "INVOICE": p.drawString(480, y, f"{data['Price']:,.2f}")
    p.save()
    return buffer

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("☁️ PP PRODUCTS ERP")
    menu = st.radio("Navigation", [
        "📝 Quotation & CRM", 
        "🏭 Production Floor", 
        "🚚 Logistics & Billing",
        "📦 Warehouse & Mixing",
        "🔧 Maintenance", 
        "🏆 Leaderboard"
    ])
    st.divider()
    # 🔐 SIDEBAR BOSS OVERRIDE
    st.subheader("🛡️ Admin Bypass")
    boss_key = st.text_input("Boss Password", type="password", help="Enter secret key to sell below RM 12.60")
    is_boss = (boss_key == "boss777")
    if is_boss:
        st.success("🔓 BOSS MODE ACTIVE")

# --- 5. MODULE: QUOTATION & CRM ---
if menu == "📝 Quotation & CRM":
    st.header("📝 Smart Quotation & CRM")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}

    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date", "Thickness", "Width", "Length", "Auth_By"])
    c_df = ensure_cols(load_data("CUSTOMER"), ["Name", "Contact", "Phone"])

    # A. ADD CUSTOMER (SAFE APPEND VERSION)
    with st.expander("👤 Add New Customer"):
        with st.form("add_cust", clear_on_submit=True):
            c1, c2 = st.columns(2)
            n_name = c1.text_input("Company Name")
            n_phone = c2.text_input("Phone (60...)")
            if st.form_submit_button("Save Customer"):
                if n_name:
                    try:
                        client = get_db_connection()
                        ws = client.worksheet("CUSTOMER")
                        ws.append_row([n_name, "", n_phone]) # Safe append
                        st.success(f"✅ {n_name} added!")
                        load_data.clear()
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")

    # B. PP SHEET CALCULATOR
    st.subheader("1. PP Sheet Weight Calculator")
    with st.container(border=True):
        cust_list = c_df["Name"].unique().tolist() if not c_df.empty else ["Cash Customer"]
        c_in = st.selectbox("Select Customer", cust_list)
        col1, col2, col3, col4 = st.columns(4)
        th = col1.number_input("Thick (mm)", 0.50, step=0.05, format="%.2f")
        wd = col2.number_input("Width (mm)", 650.0, step=10.0)
        lg = col3.number_input("Length (mm)", 900.0, step=10.0)
        qty = col4.number_input("Qty (Pcs)", 1000, step=100)
        
        # MATH: T * W * L * 0.91 * Qty / 1,000,000
        calc_wgt = (th * wd * lg * 0.91 * qty) / 1000000
        
        st.divider()
        rate = st.number_input("Selling Price per KG (RM)", value=12.60, min_value=0.0, step=0.10)
        
        # 🛡️ PRICE GUARDRAIL
        MIN_PRICE = 12.60
        can_save = True
        auth_level = "Standard"

        if rate < MIN_PRICE:
            if is_boss:
                st.warning("⚠️ Boss Override Applied.")
                auth_level = "BOSS_BYPASS"
            else:
                st.error(f"🚫 BLOCKED: Price cannot be below RM {MIN_PRICE:.2f}. Ask Janson for bypass.")
                can_save = False
        
        calc_price = calc_wgt * rate
        st.info(f"⚖️ Total Weight: **{calc_wgt:.2f} kg** | 💰 Total Price: **RM {calc_price:,.2f}**")
        
        if st.button("💾 Save Quotation", disabled=not can_save):
            new_q = {
                "Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}",
                "Customer": c_in, "Product": f"PP Sheet {th}mm x {wd}mm x {lg}mm",
                "Thickness": th, "Width": wd, "Length": lg,
                "Weight": calc_wgt, "Price": calc_price, "Status": "Pending Approval",
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Auth_By": auth_level # Audit Log
            }
            save_data(pd.concat([q_df, pd.DataFrame([new_q])], ignore_index=True), "QUOTE")
            st.success("Quote Saved to Audit Log!")
            st.rerun()

    # C. APPROVAL & WHATSAPP
    st.divider()
    ca1, ca2 = st.columns(2)
    with ca1:
        st.subheader("📋 Approvals")
        pwd = st.text_input("Manager Password", type="password")
        is_auth = (pwd in MANAGERS.values()) or (pwd == "boss777")
        pend = q_df[q_df["Status"] == "Pending Approval"]
        for i, r in pend.iterrows():
            with st.container(border=True):
                label = "⚠️ [BYPASS]" if r.get("Auth_By") == "BOSS_BYPASS" else ""
                st.write(f"**{r['Doc_ID']}** {label}")
                st.caption(f"{r['Customer']} | RM {r['Price']:,.2f}")
                if is_auth:
                    if st.button(f"Approve {r['Doc_ID']}", key=f"app_{i}"):
                        q_df.at[i, "Status"] = "Approved"
                        save_data(q_df, "QUOTE"); st.rerun()
    with ca2:
        st.subheader("📤 WhatsApp")
        appr = q_df[q_df["Status"] == "Approved"]
        for i, r in appr.iterrows():
            phone = "60123456789"
            if not c_df.empty:
                m = c_df[c_df["Name"] == r["Customer"]]
                if not m.empty: phone = str(m.iloc[0]["Phone"])
            wa_link = f"https://wa.me/{phone}?text=Hi {r['Customer']}, Quote {r['Doc_ID']} for RM {r['Price']:.2f} is ready."
            st.link_button(f"Notify {r['Customer']}", wa_link)

# --- 6. MODULE: PRODUCTION FLOOR ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Factory Floor")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Status"])
    active = q_df[q_df["Status"].isin(["Approved", "In Progress"])]
    if active.empty: st.info("No active jobs.")
    for i, r in active.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Doc_ID']}** | {r['Product']}")
            if r["Status"] == "Approved":
                if st.button(f"Start {r['Doc_ID']}"):
                    q_df.at[i, "Status"] = "In Progress"
                    save_data(q_df, "QUOTE"); st.rerun()
            else:
                if st.button(f"Finish {r['Doc_ID']}"):
                    q_df.at[i, "Status"] = "Completed"
                    save_data(q_df, "QUOTE"); st.rerun()

# --- 7. MODULE: LOGISTICS ---
elif menu == "🚚 Logistics & Billing":
    st.header("🚚 Delivery & Invoicing")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status"])
    done = q_df[q_df["Status"] == "Completed"]
    for i, r in done.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Customer']}** - {r['Doc_ID']}")
            c1, c2 = st.columns(2)
            c1.download_button("📄 DO", generate_pdf("DELIVERY ORDER", r).getvalue(), f"DO_{r['Doc_ID']}.pdf")
            c2.download_button("💰 INV", generate_pdf("INVOICE", r).getvalue(), f"INV_{r['Doc_ID']}.pdf")

# --- OTHER MODULES ---
elif menu == "📦 Warehouse & Mixing":
    st.header("📦 Inventory")
    st.dataframe(load_data("INVENTORY"), use_container_width=True)
elif menu == "🔧 Maintenance":
    st.header("🔧 Maintenance")
    st.info("Check machine health in Google Sheet Settings.")
elif menu == "🏆 Leaderboard":
    st.header("🏆 Performance")
    st.info("Production logs will appear here.")
