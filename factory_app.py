import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# --- 1. CONFIGURATION & CLOUD CONNECTION ---
st.set_page_config(page_title="PP Factory Master", layout="wide", initial_sidebar_state="expanded")
SAP_BLUE = "#0070b1"

# Connect to Google Sheets
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

try:
    sh = get_db_connection()
    if sh:
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
    else:
        st.error("❌ Database Connection Failed. Check Secrets.")
        st.stop()
except Exception as e:
    st.error(f"❌ Database Error: Missing Tab in Google Sheet. {e}")
    st.stop()

# --- 2. DATA ENGINE (CLOUD) ---
def load_data(key, cols):
    try:
        data = WS[key].get_all_records()
        df = pd.DataFrame(data)
        if df.empty: return pd.DataFrame(columns=cols)
        for c in cols:
            if c not in df.columns: 
                df[c] = 0.0 if any(x in c for x in ["Count", "Price", "Weight", "Limit", "Target"]) else "N/A"
        return df
    except: return pd.DataFrame(columns=cols)

def save_data(df, key):
    ws = WS[key]
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.values.tolist())

# --- 3. PDF GENERATOR ENGINE ---
def generate_pdf(doc_type, data):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # --- HEADER ---
    p.setFont("Helvetica-Bold", 18)
    p.drawString(50, height - 50, "PP PRODUCTS SDN BHD")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 65, "28 Jalan Mas Jaya 3, Cheras 43200, Selangor")
    p.drawString(50, height - 80, "Tel: +603-9074-XXXX | Email: sales@ppproducts.com")
    
    p.line(50, height - 90, width - 50, height - 90)
    
    # --- DOCUMENT TITLE ---
    p.setFont("Helvetica-Bold", 24)
    p.drawRightString(width - 50, height - 130, doc_type.upper())
    
    # --- CUSTOMER DETAILS ---
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 130, "Bill To:")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 145, f"{data['Customer']}")
    # (In a real app, fetch address from CUST tab here)
    p.drawString(50, height - 160, "Selangor, Malaysia")
    
    # --- METADATA ---
    p.drawString(width - 200, height - 145, f"Date: {datetime.now().strftime('%d-%b-%Y')}")
    p.drawString(width - 200, height - 160, f"{doc_type} #: {data['Doc_ID']}")
    
    # --- TABLE HEADER ---
    y = height - 200
    p.setFillColor(colors.lightgrey)
    p.rect(50, y, width - 100, 20, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y + 6, "Item Description")
    p.drawString(300, y + 6, "Qty / Weight")
    if doc_type == "INVOICE":
        p.drawString(400, y + 6, "Unit Price")
        p.drawString(480, y + 6, "Total (RM)")
    
    # --- TABLE ROW ---
    y -= 25
    p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}")
    p.drawString(300, y, f"{data['Weight']} kg")
    
    if doc_type == "INVOICE":
        price = float(data['Price']) if data['Price'] else 0.0
        p.drawString(400, y, f"RM {price/float(data['Weight']):.2f}/kg" if float(data['Weight']) > 0 else "-")
        p.drawString(480, y, f"{price:,.2f}")
        
        # TOTALS
        y -= 40
        p.line(350, y, width - 50, y)
        y -= 20
        p.setFont("Helvetica-Bold", 12)
        p.drawRightString(width - 55, y, f"Subtotal: RM {price:,.2f}")
        y -= 15
        sst = price * 0.06 # 6% SST
        p.setFont("Helvetica", 10)
        p.drawRightString(width - 55, y, f"SST (6%): RM {sst:,.2f}")
        y -= 20
        p.setFont("Helvetica-Bold", 14)
        p.drawRightString(width - 55, y, f"TOTAL: RM {price + sst:,.2f}")

    # --- FOOTER ---
    y = 100
    p.line(50, y, width - 50, y)
    p.setFont("Helvetica-Oblique", 8)
    if doc_type == "DELIVERY ORDER":
        p.drawString(50, y - 15, "Received by (Sign & Chop): __________________________")
        p.drawString(50, y - 30, "Date: __________________________")
    else:
        p.drawString(50, y - 15, "Payment Terms: 30 Days. Cheques payable to PP PRODUCTS SDN BHD.")
        p.drawString(50, y - 30, "Bank: Public Bank | Acc: 3123456789")

    p.save()
    return buffer

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("☁️ PP PRODUCTS ERP")
    menu = st.radio("Navigation", [
        "📝 Quotation & Sales", 
        "🏭 Production Floor", 
        "📦 Warehouse & Mixing",
        "🚚 Logistics & Billing",  # NEW!
        "🎨 Screens & Molds",
        "🔧 Maintenance", 
        "🏆 Leaderboard"
    ])
    st.divider()
    st.info(f"System Online\n{datetime.now().strftime('%d %b %H:%M')}")

# --- 5. MODULE: QUOTATION & SALES ---
if menu == "📝 Quotation & Sales":
    st.header("📝 Sales Quotation & WhatsApp")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}

    q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date"])
    c_df = load_data("CUST", ["Name", "Contact", "Phone"])
    
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
                save_data(pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True), "QUOTE")
                st.success("Quote Submitted!")
                st.rerun()

    st.divider()
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        st.subheader("📋 Manager Approval")
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
        st.subheader("📤 Send via WhatsApp")
        approved = q_df[q_df["Status"] == "Approved"]
        if approved.empty: st.info("No approved quotes.")
        else:
            for idx, row in approved.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Customer']}** - {row['Doc_ID']}")
                    phone = "60123456789"
                    if not c_df.empty:
                        match = c_df[c_df["Name"] == row["Customer"]]
                        if not match.empty: phone = str(match.iloc[0]["Phone"]).replace("+","")
                    msg = f"Hi {row['Customer']}, Quote {row['Doc_ID']} for {row['Product']} (RM {row['Price']}) is ready."
                    st.link_button("📲 Open WhatsApp", f"https://wa.me/{phone}?text={msg}")

# --- 6. MODULE: PRODUCTION FLOOR ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Factory Production Control")
    with st.expander("📸 Scan Job QR Code"):
        cam_val = st.camera_input("Scan QR")
        if cam_val: st.success("Scanned! (Simulated)")
    
    st.divider()
    t1, t2, t3, t4, t5 = st.tabs(["🔥 Extrusion", "📏 Trimming", "🎨 Printing", "⚙️ Die Cut (Mech)", "💧 Die Cut (Hydro)"])
    
    # Simplified Extrusion View for Demo
    with t1:
        st.subheader("Amut & Ampang Lines")
        q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Status"])
        relevant = q_df[q_df["Status"].isin(["Approved", "In Progress (Extrusion)"])]
        if relevant.empty: st.info("No jobs.")
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

    # (Other tabs copy previous logic)
    with t2: st.info("Heidelberg Module Active")
    with t3: st.info("Silk Screen Module Active")
    with t4: st.info("Die Cut Module Active")
    with t5: st.info("Hydraulic Module Active")

# --- 7. MODULE: LOGISTICS & BILLING (NEW!) ---
elif menu == "🚚 Logistics & Billing":
    st.header("🚚 Logistics & Invoicing Center")
    
    q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status"])
    
    # Filter only COMPLETED jobs
    completed = q_df[q_df["Status"] == "Completed"]
    
    if completed.empty:
        st.info("No completed jobs ready for billing. Finish a job on the Production Floor first.")
    else:
        st.write("### ✅ Ready for Delivery")
        for idx, row in completed.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.write(f"**{row['Customer']}**")
                c1.caption(f"{row['Doc_ID']} | {row['Product']} | {row['Weight']}kg")
                
                # DO Button
                pdf_do = generate_pdf("DELIVERY ORDER", row)
                c2.download_button(
                    label="📄 Download DO",
                    data=pdf_do.getvalue(),
                    file_name=f"DO_{row['Doc_ID']}.pdf",
                    mime="application/pdf",
                    key=f"do_{idx}"
                )
                
                # Invoice Button
                pdf_inv = generate_pdf("INVOICE", row)
                c3.download_button(
                    label="💰 Download Invoice",
                    data=pdf_inv.getvalue(),
                    file_name=f"INV_{row['Doc_ID']}.pdf",
                    mime="application/pdf",
                    key=f"inv_{idx}"
                )

# --- 8. MODULE: WAREHOUSE ---
elif menu == "📦 Warehouse & Mixing":
    st.header("📦 Inventory")
    i_df = load_data("INV", ["Item", "Stock_kg"])
    st.dataframe(i_df, use_container_width=True)

# --- 9. MODULE: MAINTENANCE ---
elif menu == "🔧 Maintenance":
    st.header("🔧 Maintenance")
    set_df = load_data("SETTINGS", ["Machine", "Last_Svc"])
    for idx, row in set_df.iterrows():
        st.write(f"**{row['Machine']}**")
        st.progress(0.8)

# --- 10. MODULE: LEADERBOARD ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 Staff Performance")
    h_df = load_data("HANDOVER", ["Operator", "Output_kg"])
    if not h_df.empty:
        st.bar_chart(h_df.groupby("Operator")["Output_kg"].sum())
