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
@st.cache_data(ttl=5) # Cache data for 5 seconds
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
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        load_data.clear() # Clear cache to show update immediately
    except Exception as e:
        st.error(f"Save Error: {e}")

# Helper to prevent crashes if columns are missing
def ensure_cols(df, cols):
    if df.empty: return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            # Smart default: 0.0 for numbers, "" for text
            is_num = any(x in c for x in ["Count", "Price", "Weight", "Limit", "Target", "Width", "Length", "Thick"])
            df[c] = 0.0 if is_num else "N/A"
    return df

# --- 3. PDF GENERATOR (DO & INVOICE) ---
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
    
    # Title & Metadata
    p.setFont("Helvetica-Bold", 24)
    p.drawRightString(width - 50, height - 130, doc_type.upper())
    
    p.setFont("Helvetica-Bold", 12)
    p.drawString(50, height - 130, "Bill To:")
    p.setFont("Helvetica", 12)
    p.drawString(50, height - 145, f"{data['Customer']}")
    
    p.drawString(width - 200, height - 145, f"Date: {datetime.now().strftime('%d-%b-%Y')}")
    p.drawString(width - 200, height - 160, f"Ref: {data['Doc_ID']}")
    
    # Table Header
    y = height - 200
    p.setFillColor(colors.lightgrey)
    p.rect(50, y, width - 100, 20, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y + 6, "Product / Spec")
    p.drawString(300, y + 6, "Quantity")
    if doc_type == "INVOICE":
        p.drawString(400, y + 6, "Unit Price")
        p.drawString(480, y + 6, "Total (RM)")
    
    # Table Content
    y -= 25
    p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}")
    # Handle Sheet Dimensions in Description if available
    desc_extra = f"{data.get('Thickness',0)}mm x {data.get('Width',0)}mm x {data.get('Length',0)}mm"
    p.drawString(60, y-12, desc_extra)
    
    p.drawString(300, y, f"{data['Weight']} kg")
    
    if doc_type == "INVOICE":
        price = float(data['Price']) if data['Price'] else 0.0
        weight = float(data['Weight']) if data['Weight'] else 1.0
        p.drawString(400, y, f"RM {price/weight:.2f}/kg")
        p.drawString(480, y, f"{price:,.2f}")
        
        # Totals
        y -= 50
        p.line(350, y, width - 50, y)
        y -= 20
        p.setFont("Helvetica-Bold", 12)
        p.drawRightString(width - 55, y, f"Total Payable: RM {price * 1.06:,.2f}") # Incl 6% SST

    # Footer
    y = 100
    p.line(50, y, width - 50, y)
    p.setFont("Helvetica-Oblique", 8)
    if doc_type == "DELIVERY ORDER":
        p.drawString(50, y - 15, "Received by (Sign & Chop): __________________________")
    else:
        p.drawString(50, y - 15, "Payment Terms: 30 Days. Cheques payable to PP PRODUCTS SDN BHD.")

    p.save()
    return buffer

# --- 4. SIDEBAR NAVIGATION ---
with st.sidebar:
    st.title("☁️ PP PRODUCTS ERP")
    menu = st.radio("Navigation", [
        "📝 Quotation & CRM", 
        "🏭 Production Floor", 
        "🚚 Logistics & Billing",
        "📦 Warehouse & Mixing",
        "🎨 Tooling (Molds/Screens)",
        "🔧 Maintenance", 
        "🏆 Leaderboard"
    ])
    st.divider()
    st.caption(f"System Online: {datetime.now().strftime('%H:%M')}")

# --- 5. MODULE: QUOTATION & CRM (THE CALCULATOR IS BACK!) ---
if menu == "📝 Quotation & CRM":
    st.header("📝 Smart Quotation System")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}

    # Load Data
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date", "Thickness", "Width", "Length"])
    c_df = ensure_cols(load_data("CUSTOMER"), ["Name", "Contact", "Phone"])

    # --- A. NEW CUSTOMER ADDITION ---
    with st.expander("👤 Add New Customer"):
        with st.form("add_cust"):
            c1, c2 = st.columns(2)
            new_name = c1.text_input("Company Name")
            new_phone = c2.text_input("Phone (e.g. 60123456789)")
            if st.form_submit_button("Save Customer"):
                save_data(pd.concat([c_df, pd.DataFrame([{"Name": new_name, "Phone": new_phone}])], ignore_index=True), "CUSTOMER")
                st.success("Customer Added")
                st.rerun()

    # --- B. THE PP SHEET CALCULATOR (RESTORED!) ---
    st.subheader("1. PP Sheet Calculator")
    
    with st.container(border=True):
        # 1. Select Customer
        cust_list = c_df["Name"].unique().tolist() if not c_df.empty else ["Cash Customer"]
        cust_input = st.selectbox("Customer", cust_list)
        
        c1, c2, c3, c4 = st.columns(4)
        
        # 2. Dimensions Input
        thick = c1.number_input("Thickness (mm)", value=0.5, step=0.1, format="%.2f")
        width = c2.number_input("Width (mm)", value=650.0, step=10.0)
        length = c3.number_input("Length (mm)", value=900.0, step=10.0)
        density = c4.number_input("Density", value=0.91, disabled=True, help="Standard PP Density")
        
        # 3. Quantity Input
        qty_pcs = st.number_input("Quantity (Pieces)", value=1000, step=100)
        
        # 4. The Math (Hidden Magic)
        # Weight (kg) = T(mm) * W(mm) * L(mm) * Density * Qty / 1,000,000
        one_sheet_wgt = (thick * width * length * density) / 1000000
        total_wgt = one_sheet_wgt * qty_pcs
        
        # 5. Price Input
        price_per_kg = st.number_input("Price per KG (RM)", value=5.50, step=0.10)
        total_price = total_wgt * price_per_kg
        
        # 6. Display Results
        st.info(f"📊 **Spec:** {thick}mm x {width}mm x {length}mm")
        m1, m2, m3 = st.columns(3)
        m1.metric("Weight per Piece", f"{one_sheet_wgt:.4f} kg")
        m2.metric("Total Order Weight", f"{total_wgt:.2f} kg")
        m3.metric("Grand Total (RM)", f"{total_price:,.2f}")

        # 7. Submit
        if st.button("💾 Generate Quote"):
            new_row = {
                "Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}",
                "Customer": cust_input, 
                "Product": f"PP Sheet {thick}mm x {width}mm x {length}mm",
                "Thickness": thick, "Width": width, "Length": length,
                "Weight": total_wgt, 
                "Price": total_price, 
                "Status": "Pending Approval", 
                "Date": datetime.now().strftime("%Y-%m-%d")
            }
            save_data(pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True), "QUOTE")
            st.success("Quote Saved to System!")
            time.sleep(1)
            st.rerun()

    # --- C. APPROVAL & WHATSAPP ---
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
                    st.caption(f"{row['Product']}")
                    st.write(f"⚖️ **{float(row['Weight']):,.2f} kg**")
                    
                    if is_auth:
                        if st.button("✅ APPROVE", key=f"app_{idx}"):
                            real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                            q_df.at[real_idx, "Status"] = "Approved"
                            save_data(q_df, "QUOTE"); st.rerun()
                    else: st.button("🔒 Locked", disabled=True, key=f"lck_{idx}")

    with col_q2:
        st.subheader("📤 WhatsApp Sender")
        approved = q_df[q_df["Status"] == "Approved"]
        if not approved.empty:
            for idx, row in approved.iterrows():
                with st.container(border=True):
                    st.write(f"**{row['Customer']}**")
                    phone = "60123456789"
                    if not c_df.empty:
                        match = c_df[c_df["Name"] == row["Customer"]]
                        if not match.empty: phone = str(match.iloc[0]["Phone"]).replace("+","").replace("-","").replace(" ","")
                    
                    msg = f"Hi {row['Customer']}, Quote {row['Doc_ID']} for {row['Product']} is ready.%0A%0A⚖️ Weight: {row['Weight']:.2f}kg%0A💰 Total: RM {row['Price']:,.2f}%0A%0APlease confirm."
                    st.link_button("📲 Send WhatsApp", f"https://wa.me/{phone}?text={msg}")

# --- 6. MODULE: PRODUCTION FLOOR (CAMERA & TABS) ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Factory Production Control")
    
    # Camera Section
    with st.expander("📸 Scan Job QR Code (An Tu)"):
        cam_val = st.camera_input("Scan Job Sheet")
        if cam_val: st.success("Job QT-260209 Scanned! (Simulated)")
    
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
    
    # Placeholders for other depts (Logic same as Extrusion)
    with t2: st.info("Heidelberg Trimming Active")
    with t3: st.info("Silk Screen Printing Active")
    with t4: st.info("Mechanical Die Cutting Active")
    with t5: st.info("Hydraulic Die Cutting Active")

# --- 7. MODULE: LOGISTICS (PDF GENERATOR) ---
elif menu == "🚚 Logistics & Billing":
    st.header("🚚 Logistics & Billing")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status"])
    completed = q_df[q_df["Status"] == "Completed"]
    
    if completed.empty: st.info("No completed jobs.")
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
    st.header("📦 Inventory & Mixing")
    i_df = ensure_cols(load_data("INVENTORY"), ["Item", "Stock_kg"])
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Current Stock")
        st.dataframe(i_df, use_container_width=True)
    with c2:
        st.subheader("🧪 Resin Calculator")
        batch = st.number_input("Batch Size (kg)", 500)
        v_pct = st.slider("Virgin %", 0, 100, 70)
        st.info(f"Mix: **{batch * (v_pct/100)}kg Virgin** + **{batch * (1-(v_pct/100))}kg Regrind**")

# --- 9. MODULE: TOOLING ---
elif menu == "🎨 Tooling (Molds/Screens)":
    st.header("🗄️ Die Molds & Print Screens")
    t1, t2 = st.tabs(["Die Molds", "Screens"])
    with t1: st.dataframe(ensure_cols(load_data("MOLDS"), ["ID", "Location", "Status"]), use_container_width=True)
    with t2: st.dataframe(ensure_cols(load_data("SCREENS"), ["ID", "Mesh", "Location"]), use_container_width=True)

# --- 10. MODULE: MAINTENANCE ---
elif menu == "🔧 Maintenance":
    st.header("🔧 Maintenance")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}
    set_df = ensure_cols(load_data("SETTINGS"), ["Machine", "Last_Svc", "Threshold", "Current"])
    
    c1, c2 = st.columns(2)
    mgr = c1.selectbox("Manager Auth", ["Select", "Iris", "Tomy"])
    pwd = c2.text_input("Password", type="password")
    is_auth = mgr in MANAGERS and pwd == MANAGERS[mgr]
    if is_auth: st.success("🔓 Controls Unlocked")

    for idx, row in set_df.iterrows():
        with st.container(border=True):
            st.write(f"**{row['Machine']}**")
            # Logic: (Current - Last_Svc) / Threshold
            used = float(row['Current']) - float(row['Last_Svc'])
            limit = float(row['Threshold']) if float(row['Threshold']) > 0 else 50000.0
            health = max(0.0, 1.0 - (used / limit))
            st.progress(health)
            st.caption(f"Health: {health*100:.0f}%")
            
            if is_auth and st.button("✅ RESET", key=f"rst_{idx}"):
                set_df.at[idx, "Last_Svc"] = float(row['Current'])
                save_data(set_df, "SETTINGS"); st.rerun()

# --- 11. LEADERBOARD ---
elif menu == "🏆 Leaderboard":
    st.header("🏆 Staff Performance")
    h_df = ensure_cols(load_data("HANDOVER"), ["Operator", "Output_kg"])
    if not h_df.empty:
        st.bar_chart(h_df.groupby("Operator")["Output_kg"].sum())
