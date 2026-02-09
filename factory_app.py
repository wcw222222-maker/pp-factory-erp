import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import time
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

# --- 1. CONFIGURATION & CLOUD CONNECTION ---
st.set_page_config(page_title="PP Products Master ERP", layout="wide", initial_sidebar_state="expanded")

# Cache connection to save API quota
@st.cache_resource
def get_db_connection():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("PP_ERP_Database")
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return None

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=10) # Cache data for 10 seconds to prevent 429 errors
def load_data(sheet_name):
    try:
        client = get_db_connection()
        if not client: return pd.DataFrame()
        ws = client.worksheet(sheet_name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def save_data(df, sheet_name):
    try:
        client = get_db_connection()
        ws = client.worksheet(sheet_name)
        df = df.fillna("") # Convert NaNs to empty strings for Google
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        load_data.clear() # Reset cache
    except Exception as e:
        st.error(f"Critical Save Error: {e}")

def ensure_cols(df, cols):
    if df.empty: return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            is_num = any(x in c for x in ["Count", "Price", "Weight", "Limit", "Target", "Width", "Length", "Thick"])
            df[c] = 0.0 if is_num else ""
    return df

# --- 3. PDF GENERATOR ENGINE ---
def generate_pdf(doc_type, data, customer_df):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    
    # Header
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "PP PRODUCTS SDN BHD")
    p.setFont("Helvetica", 9)
    p.drawString(50, height - 65, "28 Jalan Mas Jaya 3, Cheras 43200, Selangor")
    p.line(50, height - 85, width - 50, height - 85)
    
    # Doc Type & Ref
    p.setFont("Helvetica-Bold", 20)
    p.drawRightString(width - 50, height - 120, doc_type.upper())
    
    # Address Logic
    cust_addr = "No address on file."
    if not customer_df.empty:
        match = customer_df[customer_df["Name"] == data['Customer']]
        if not match.empty:
            cust_addr = str(match.iloc[0].get("Address", "No Address Stated"))

    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, height - 120, "SHIP / BILL TO:")
    p.setFont("Helvetica", 10)
    p.drawString(50, height - 135, f"{data['Customer']}")
    text_obj = p.beginText(50, height - 150)
    text_obj.setFont("Helvetica", 9)
    text_obj.textLines(cust_addr)
    p.drawText(text_obj)
    
    p.drawRightString(width - 50, height - 135, f"Date: {datetime.now().strftime('%d-%b-%Y')}")
    p.drawRightString(width - 50, height - 150, f"Ref: {data['Doc_ID']}")
    
    # Items Table
    y = height - 230
    p.setFillColor(colors.lightgrey)
    p.rect(50, y, width - 100, 20, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y + 6, "Description")
    p.drawString(350, y + 6, "Weight (kg)")
    if doc_type == "INVOICE": p.drawString(480, y + 6, "Total (RM)")
    
    y -= 25
    p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}")
    p.drawString(350, y, f"{data['Weight']:.2f}")
    if doc_type == "INVOICE": p.drawString(480, y, f"{data['Price']:,.2f}")

    # T&C Footer
    y_f = 150
    p.line(50, y_f, width - 50, y_f)
    p.setFont("Helvetica-Bold", 8); p.drawString(50, y_f - 15, "TERMS & CONDITIONS:")
    p.setFont("Helvetica", 7)
    if doc_type == "INVOICE":
        tc = ["1. Terms: 30 Days.", "2. Overdue: 1.5% interest/month.", "3. Bank: Public Bank 3123-XXXX-XXXX."]
    else:
        tc = ["1. Received in good condition.", "2. No claims after signing.", "3. Goods are not returnable."]
    y_t = y_f - 25
    for line in tc: p.drawString(50, y_t, line); y_t -= 10

    p.drawString(50, 50, "____________________"); p.drawString(50, 40, "Authorized Sign")
    p.drawRightString(width - 50, 50, "____________________"); p.drawRightString(width - 50, 40, "Chop & Sign")
    p.save()
    return buffer

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("🏭 PP ERP System")
    menu = st.radio("Navigation", ["🏠 Dashboard", "📝 Quotation & CRM", "🏭 Production Floor", "🚚 Logistics & Billing", "💰 Payment Tracking", "📦 Warehouse"])
    st.divider()
    st.subheader("🛡️ Admin Panel")
    boss_key = st.text_input("Boss Password", type="password")
    is_boss = (boss_key == "boss777")
    if is_boss: st.success("BOSS MODE ON")

# --- 5. MODULE: DASHBOARD (NEW) ---
if menu == "🏠 Dashboard":
    st.header("🏠 Business Overview")
    q_df = ensure_cols(load_data("QUOTE"), ["Price", "Status", "Payment_Status", "Date"])
    
    # Stats
    total_sales = q_df[q_df['Status'] == 'Completed']['Price'].sum()
    unpaid = q_df[(q_df['Status'] == 'Completed') & (q_df['Payment_Status'] != 'Paid')]
    outstanding = unpaid['Price'].sum()
    in_prod = len(q_df[q_df['Status'] == 'In Progress'])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Lifetime Sales", f"RM {total_sales:,.2f}")
    c2.metric("Total Outstanding", f"RM {outstanding:,.2f}", delta=f"{len(unpaid)} Unpaid", delta_color="inverse")
    c3.metric("Live Production", f"{in_prod} Jobs")

    

    st.divider()
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("📊 Recent Activity")
        st.table(q_df.tail(5)[["Date", "Customer", "Product", "Status"]])
    with col_right:
        st.subheader("📦 Warehouse Alerts")
        st.info("No low stock alerts today.")

# --- 6. MODULE: QUOTATION & CRM ---
elif menu == "📝 Quotation & CRM":
    st.header("📝 Smart Quote & Customer CRM")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date", "Auth_By", "Payment_Status"])
    c_df = ensure_cols(load_data("CUSTOMER"), ["Name", "Phone", "Address"])

    with st.expander("👤 Register New Customer"):
        with st.form("add_cust", clear_on_submit=True):
            n_name = st.text_input("Company Name")
            n_phone = st.text_input("WhatsApp Number (60...)")
            n_addr = st.text_area("Full Delivery Address")
            if st.form_submit_button("Save Customer"):
                if n_name and n_addr:
                    try:
                        client = get_db_connection()
                        ws = client.worksheet("CUSTOMER")
                        ws.append_row([n_name, "", n_phone, n_addr])
                        st.success("Customer Saved!"); load_data.clear(); st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    st.subheader("📐 PP Sheet Calculator")
    with st.container(border=True):
        clist = c_df["Name"].tolist() if not c_df.empty else ["Cash"]
        cin = st.selectbox("Select Customer", clist)
        c1, c2, c3, c4 = st.columns(4)
        th = c1.number_input("Thick (mm)", 0.50, step=0.05, format="%.2f")
        wd = c2.number_input("Width (mm)", 650.0, step=10.0)
        lg = c3.number_input("Length (mm)", 900.0, step=10.0)
        qty = c4.number_input("Qty (Pcs)", 1000, step=100)
        
        calc_wgt = (th*wd*lg*0.91*qty)/1000000
        rate = st.number_input("Price per KG (RM)", 12.60)
        
        can_save, auth_lvl = True, "Standard"
        if rate < 12.60:
            if is_boss: auth_lvl = "BOSS_BYPASS"
            else: st.error("🚫 Price below RM12.60 blocked."); can_save = False
            
        final_p = calc_wgt * rate
        st.info(f"⚖️ Weight: {calc_wgt:.2f} kg | 💰 Total: RM {final_p:,.2f}")
        
        if st.button("💾 Generate Quotation", disabled=not can_save):
            new_q = {
                "Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}", 
                "Customer": cin, "Product": f"PP {th}x{wd}x{lg}", 
                "Weight": calc_wgt, "Price": final_p, "Status": "Pending Approval", 
                "Date": datetime.now().strftime("%Y-%m-%d"), "Auth_By": auth_lvl, "Payment_Status": "Unpaid"
            }
            save_data(pd.concat([q_df, pd.DataFrame([new_q])], ignore_index=True), "QUOTE")
            st.success("Quote Saved to Queue!"); st.rerun()

    st.divider()
    ca1, ca2 = st.columns(2)
    with ca1:
        st.subheader("📋 Approvals")
        pwd = st.text_input("Security Code", type="password")
        pend = q_df[q_df["Status"] == "Pending Approval"]
        for i, r in pend.iterrows():
            with st.container(border=True):
                st.write(f"**{r['Doc_ID']}** {'[BYPASS]' if r['Auth_By']=='BOSS_BYPASS' else ''}")
                if (pwd in MANAGERS.values()) or is_boss:
                    if st.button(f"Approve {r['Doc_ID']}", key=f"ap_{i}"):
                        q_df.at[i, "Status"] = "Approved"; save_data(q_df, "QUOTE"); st.rerun()
    with ca2:
        st.subheader("📤 WhatsApp Notify")
        appr = q_df[q_df["Status"] == "Approved"]
        for i, r in appr.iterrows():
            match = c_df[c_df["Name"] == r["Customer"]]
            phone = str(match.iloc[0]["Phone"]) if not match.empty else "60123456789"
            wa_link = f"https://wa.me/{phone}?text=Hi {r['Customer']}, Quote {r['Doc_ID']} for RM {r['Price']:.2f} is ready."
            st.link_button(f"Notify {r['Customer']}", wa_link)

# --- 7. MODULE: PRODUCTION FLOOR ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Production Control")
    q_df = load_data("QUOTE")
    active = q_df[q_df["Status"].isin(["Approved", "In Progress"])]
    if active.empty: st.info("No jobs on the floor.")
    for i, r in active.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Doc_ID']}** | {r['Customer']}")
            st.caption(f"Spec: {r['Product']}")
            label = "Start Production" if r["Status"] == "Approved" else "Complete & Mark Ready"
            if st.button(label, key=f"prod_{i}"):
                q_df.at[i, "Status"] = "In Progress" if r["Status"] == "Approved" else "Completed"
                save_data(q_df, "QUOTE"); st.rerun()

# --- 8. MODULE: LOGISTICS ---
elif menu == "🚚 Logistics & Billing":
    st.header("🚚 Shipping & Invoicing")
    q_df, c_df = load_data("QUOTE"), load_data("CUSTOMER")
    done = q_df[q_df["Status"] == "Completed"]
    if done.empty: st.info("No jobs ready for delivery.")
    for i, r in done.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Customer']}** | {r['Doc_ID']}")
            c1, c2 = st.columns(2)
            c1.download_button("📄 Download DO", generate_pdf("DELIVERY ORDER", r, c_df).getvalue(), f"DO_{r['Doc_ID']}.pdf")
            c2.download_button("💰 Download Invoice", generate_pdf("INVOICE", r, c_df).getvalue(), f"INV_{r['Doc_ID']}.pdf")

# --- 9. MODULE: PAYMENT TRACKING ---
elif menu == "💰 Payment Tracking":
    st.header("💰 Aging Report & Payment Status")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Price", "Status", "Payment_Status", "Date"])
    unpaid = q_df[(q_df["Status"] == "Completed") & (q_df["Payment_Status"] != "Paid")].copy()
    
    if unpaid.empty: st.success("All invoices paid!")
    else:
        unpaid['Date_DT'] = pd.to_datetime(unpaid['Date'], errors='coerce')
        unpaid['Days'] = (datetime.now() - unpaid['Date_DT']).dt.days
        
        for i, r in unpaid.iterrows():
            overdue = r['Days'] > 30
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                if overdue: c1.error(f"🚩 **{r['Customer']}** ({r['Days']} days overdue)")
                else: c1.write(f"**{r['Customer']}** ({r['Days']} days old)")
                c2.subheader(f"RM {r['Price']:,.2f}")
                if c3.button("✅ Mark Paid", key=f"pay_{i}"):
                    real_idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                    q_df.at[real_idx, "Payment_Status"] = "Paid"
                    save_data(q_df, "QUOTE"); st.rerun()

# --- 10. MODULE: WAREHOUSE ---
elif menu == "📦 Warehouse":
    st.header("📦 Current Inventory")
    st.dataframe(load_data("INVENTORY"), use_container_width=True)
