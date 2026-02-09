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

# --- 2. DATA ENGINE ---
@st.cache_data(ttl=5) 
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
        df = df.fillna("") 
        ws.clear()
        ws.update([df.columns.values.tolist()] + df.values.tolist())
        load_data.clear() 
    except Exception as e:
        st.error(f"Save Error: {e}")

def ensure_cols(df, cols):
    if df.empty: return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            is_num = any(x in c for x in ["Count", "Price", "Weight", "Limit", "Target", "Width", "Length", "Thick"])
            df[c] = 0.0 if is_num else ""
    return df

# --- 3. PDF GENERATOR ---
def generate_pdf(doc_type, data, customer_df):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFont("Helvetica-Bold", 16)
    p.drawString(50, height - 50, "PP PRODUCTS SDN BHD")
    p.setFont("Helvetica", 9)
    p.drawString(50, height - 65, "28 Jalan Mas Jaya 3, Cheras 43200, Selangor")
    p.line(50, height - 85, width - 50, height - 85)
    p.setFont("Helvetica-Bold", 20)
    p.drawRightString(width - 50, height - 120, doc_type.upper())
    
    cust_addr = "Address Not Found"
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
    
    p.setFont("Helvetica", 10)
    p.drawRightString(width - 50, height - 135, f"Date: {datetime.now().strftime('%d-%b-%Y')}")
    p.drawRightString(width - 50, height - 150, f"Ref: {data['Doc_ID']}")
    
    y = height - 230
    p.setFillColor(colors.lightgrey)
    p.rect(50, y, width - 100, 20, fill=1, stroke=0)
    p.setFillColor(colors.black)
    p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y + 6, "Description / Spec")
    p.drawString(350, y + 6, "Weight (kg)")
    if doc_type == "INVOICE": p.drawString(480, y + 6, "Total (RM)")
    
    y -= 25
    p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}")
    p.drawString(350, y, f"{data['Weight']:.2f}")
    if doc_type == "INVOICE": p.drawString(480, y, f"{data['Price']:,.2f}")

    y_footer = 150
    p.line(50, y_footer, width - 50, y_footer)
    p.setFont("Helvetica-Bold", 9); p.drawString(50, y_footer - 15, "TERMS & CONDITIONS:")
    p.setFont("Helvetica", 8)
    
    if doc_type == "INVOICE":
        tc = ["1. Payment terms: 30 days.", "2. Late interest: 1.5% per month.", "3. Payable to: PP PRODUCTS SDN BHD.", "4. Public Bank: 3123-4567-XXXX"]
    else:
        tc = ["1. Goods received in good condition.", "2. Damage must be noted before signing.", "3. Goods are not returnable."]
    
    y_text = y_footer - 28
    for line in tc:
        p.drawString(50, y_text, line); y_text -= 12

    p.drawString(50, 60, "__________________________"); p.drawString(50, 45, "Authorised Signature")
    p.drawRightString(width - 50, 60, "__________________________"); p.drawRightString(width - 50, 45, "Customer Chop & Sign")
    p.save()
    return buffer

# --- 4. SIDEBAR ---
with st.sidebar:
    st.title("☁️ PP PRODUCTS ERP")
    menu = st.radio("Navigation", ["📝 Quotation & CRM", "🏭 Production Floor", "🚚 Logistics & Billing", "💰 Payment Tracking", "📦 Warehouse & Mixing"])
    st.divider()
    boss_key = st.text_input("Boss Password", type="password")
    is_boss = (boss_key == "boss777")

# --- 5. MODULE: QUOTATION & CRM ---
if menu == "📝 Quotation & CRM":
    st.header("📝 Smart Quotation & CRM")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date", "Auth_By", "Payment_Status"])
    c_df = ensure_cols(load_data("CUSTOMER"), ["Name", "Contact", "Phone", "Address"])

    with st.expander("👤 Add New Customer"):
        with st.form("add_cust", clear_on_submit=True):
            n_name, n_phone, n_addr = st.text_input("Company Name"), st.text_input("Phone Number"), st.text_area("Address")
            if st.form_submit_button("Save"):
                ws = get_db_connection().worksheet("CUSTOMER")
                ws.append_row([n_name, "", n_phone, n_addr])
                st.success("Added!"); load_data.clear(); time.sleep(1); st.rerun()

    st.subheader("1. Quote Calculator")
    with st.container(border=True):
        c_in = st.selectbox("Select Customer", c_df["Name"].tolist() if not c_df.empty else ["Cash"])
        col1, col2, col3, col4 = st.columns(4)
        th, wd, lg, qty = col1.number_input("Thick"), col2.number_input("Width"), col3.number_input("Length"), col4.number_input("Qty")
        wgt = (th*wd*lg*0.91*qty)/1000000; rate = st.number_input("Price/KG", 12.60)
        can_save = is_boss or rate >= 12.60
        if st.button("💾 Save Quote", disabled=not can_save):
            new_q = {"Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}", "Customer": c_in, "Product": f"PP {th}x{wd}x{lg}", "Weight": wgt, "Price": wgt*rate, "Status": "Pending Approval", "Date": datetime.now().strftime("%Y-%m-%d"), "Auth_By": "BOSS" if is_boss else "Standard", "Payment_Status": "Unpaid"}
            save_data(pd.concat([q_df, pd.DataFrame([new_q])], ignore_index=True), "QUOTE"); st.rerun()

# --- 6. MODULE: PRODUCTION FLOOR ---
elif menu == "🏭 Production Floor":
    st.header("🏭 Factory Floor")
    q_df = load_data("QUOTE")
    active = q_df[q_df["Status"].isin(["Approved", "In Progress"])]
    for i, r in active.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Doc_ID']}** | {r['Product']}")
            btn_label = "Start" if r["Status"] == "Approved" else "Finish"
            if st.button(f"{btn_label} {r['Doc_ID']}", key=f"p_{i}"):
                q_df.at[i, "Status"] = "In Progress" if r["Status"] == "Approved" else "Completed"
                save_data(q_df, "QUOTE"); st.rerun()

# --- 7. MODULE: LOGISTICS ---
elif menu == "🚚 Logistics & Billing":
    st.header("🚚 Logistics")
    q_df = load_data("QUOTE"); c_df = load_data("CUSTOMER")
    done = q_df[q_df["Status"] == "Completed"]
    for i, r in done.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Customer']}** - {r['Doc_ID']}")
            c1, c2 = st.columns(2)
            c1.download_button("📄 DO", generate_pdf("DELIVERY ORDER", r, c_df).getvalue(), f"DO_{r['Doc_ID']}.pdf")
            c2.download_button("💰 INV", generate_pdf("INVOICE", r, c_df).getvalue(), f"INV_{r['Doc_ID']}.pdf")

# --- 8. MODULE: PAYMENT TRACKING (NEW!) ---
elif menu == "💰 Payment Tracking":
    st.header("💰 Accounts Receivable (Unpaid Invoices)")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Price", "Status", "Payment_Status", "Date_Paid"])
    
    # Filter for Completed (Invoiced) but Unpaid
    unpaid_df = q_df[(q_df["Status"] == "Completed") & (q_df["Payment_Status"] != "Paid")]
    
    if unpaid_df.empty:
        st.success("🎉 All clear! No outstanding payments.")
    else:
        total_outstanding = unpaid_df["Price"].sum()
        st.metric("Total Outstanding", f"RM {total_outstanding:,.2f}")
        
        

        for i, r in unpaid_df.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.write(f"**{r['Customer']}**")
                c1.caption(f"Ref: {r['Doc_ID']}")
                c2.write(f"RM {r['Price']:,.2f}")
                
                if c3.button("✅ Mark as Paid", key=f"pay_{i}"):
                    # Update status in the main dataframe
                    real_idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                    q_df.at[real_idx, "Payment_Status"] = "Paid"
                    q_df.at[real_idx, "Date_Paid"] = datetime.now().strftime("%Y-%m-%d")
                    save_data(q_df, "QUOTE")
                    st.toast(f"Payment for {r['Doc_ID']} recorded!")
                    time.sleep(1)
                    st.rerun()

    st.divider()
    with st.expander("📂 View Payment History"):
        paid_df = q_df[q_df["Payment_Status"] == "Paid"]
        st.dataframe(paid_df[["Date_Paid", "Customer", "Doc_ID", "Price"]], use_container_width=True)

# --- 9. MODULE: WAREHOUSE ---
elif menu == "📦 Warehouse & Mixing":
    st.header("📦 Inventory")
    st.dataframe(load_data("INVENTORY"), use_container_width=True)
