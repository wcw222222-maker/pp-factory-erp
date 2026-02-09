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

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="PP Products Master ERP", layout="wide", initial_sidebar_state="expanded")

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

@st.cache_data(ttl=10)
def load_data(sheet_name):
    try:
        client = get_db_connection()
        if not client: return pd.DataFrame()
        ws = client.worksheet(sheet_name)
        return pd.DataFrame(ws.get_all_records())
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
            is_num = any(x in c for x in ["Price", "Weight", "Thick", "Width", "Length"])
            df[c] = 0.0 if is_num else ""
    return df

# --- 2. PDF ENGINE ---
def generate_pdf(doc_type, data, customer_df):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFont("Helvetica-Bold", 16); p.drawString(50, height - 50, "PP PRODUCTS SDN BHD")
    p.setFont("Helvetica", 9); p.drawString(50, height - 65, "28 Jalan Mas Jaya 3, Cheras 43200, Selangor")
    p.line(50, height - 85, width - 50, height - 85)
    
    cust_addr = "No Address"
    if not customer_df.empty:
        match = customer_df[customer_df["Name"] == data['Customer']]
        if not match.empty: cust_addr = str(match.iloc[0].get("Address", "No Address"))

    p.setFont("Helvetica-Bold", 11); p.drawString(50, height - 120, "BILL / SHIP TO:")
    p.setFont("Helvetica", 10); p.drawString(50, height - 135, f"{data['Customer']}")
    t = p.beginText(50, height - 150); t.setFont("Helvetica", 9); t.textLines(cust_addr); p.drawText(t)
    
    p.drawRightString(width - 50, height - 135, f"Date: {data['Date']}")
    p.drawRightString(width - 50, height - 150, f"Ref: {data['Doc_ID']}")
    
    y = height - 230
    p.setFillColor(colors.lightgrey); p.rect(50, y, width - 100, 20, fill=1, stroke=0)
    p.setFillColor(colors.black); p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y + 6, "Description"); p.drawString(350, y + 6, "Weight (kg)")
    if doc_type == "INVOICE": p.drawString(480, y + 6, "Total (RM)")
    
    y -= 25; p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}"); p.drawString(350, y, f"{data['Weight']:.2f}")
    if doc_type == "INVOICE": p.drawString(480, y, f"{data['Price']:,.2f}")

    y_f = 120; p.line(50, y_f, width - 50, y_f)
    p.setFont("Helvetica-Bold", 8); p.drawString(50, y_f - 15, "TERMS & CONDITIONS:")
    tc = ["1. Terms: 30 Days.", "2. Interest 1.5% for late payment.", "3. Public Bank: 3123-XXXX-XXXX"] if doc_type=="INVOICE" else ["1. Received in good condition.", "2. Check goods before signing."]
    y_t = y_f - 25
    for line in tc: p.drawString(50, y_t, line); y_t -= 10
    p.save(); return buffer

# --- 3. SIDEBAR ---
with st.sidebar:
    st.title("🏭 PP MASTER ERP")
    menu = st.radio("Navigation", ["🏠 Dashboard", "📝 Quote & CRM", "📞 Sales Follow-Up", "🏭 Production", "🚚 Logistics", "💰 Payments"])
    st.divider()
    boss_pwd = st.text_input("Boss Password", type="password")
    is_boss = (boss_pwd == "boss777")

# --- 4. MODULE: DASHBOARD ---
if menu == "🏠 Dashboard":
    st.header("🏠 Business Dashboard")
    q_df = ensure_cols(load_data("QUOTE"), ["Price", "Status", "Sales_Person", "Payment_Status"])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Revenue", f"RM {q_df[q_df['Status']=='Completed']['Price'].sum():,.2f}")
    c2.metric("Outstanding Debt", f"RM {q_df[(q_df['Status']=='Completed') & (q_df['Payment_Status']!='Paid')]['Price'].sum():,.2f}")
    c3.metric("Edward vs Sujita", f"{len(q_df[q_df['Sales_Person']=='Edward'])} vs {len(q_df[q_df['Sales_Person']=='Sujita'])}", delta="Quotes Sent")
    
    

# --- 5. MODULE: QUOTE & CRM ---
elif menu == "📝 Quote & CRM":
    st.header("📝 New Quotation")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date", "Auth_By", "Sales_Person"])
    c_df = ensure_cols(load_data("CUSTOMER"), ["Name", "Phone", "Address"])

    with st.expander("👤 Register New Customer"):
        with st.form("add_cust", clear_on_submit=True):
            n_name, n_phone, n_addr = st.text_input("Company Name"), st.text_input("Phone (60...)"), st.text_area("Address")
            if st.form_submit_button("Save"):
                get_db_connection().worksheet("CUSTOMER").append_row([n_name, "", n_phone, n_addr])
                st.success("Saved!"); load_data.clear(); time.sleep(1); st.rerun()

    with st.container(border=True):
        st.subheader("📐 Calculator")
        c1, c2, c3 = st.columns([2,1,1])
        cin = c1.selectbox("Customer", c_df["Name"].tolist() if not c_df.empty else ["Cash"])
        sperson = c2.selectbox("Sales Person", ["Sujita", "Edward"])
        
        col1, col2, col3, col4 = st.columns(4)
        th = col1.number_input("Thick (mm)", 0.50, format="%.2f")
        wd = col2.number_input("Width (mm)", 650.0)
        lg = col3.number_input("Length (mm)", 900.0)
        qty = col4.number_input("Qty (Pcs)", 1000)
        
        # LaTeX for technical accuracy
        # $$Weight = \frac{T \times W \times L \times 0.91 \times Qty}{1,000,000}$$
        calc_wgt = (th * wd * lg * 0.91 * qty) / 1000000
        rate = st.number_input("Price/KG (RM)", 12.60)
        
        can_save, auth_lvl = True, "Standard"
        if rate < 12.60:
            if is_boss: auth_lvl = "BOSS_BYPASS"
            else: st.error("🚫 Blocked: Price < RM 12.60"); can_save = False
            
        final_p = calc_wgt * rate
        st.info(f"⚖️ {calc_wgt:.2f} kg | 💰 RM {final_p:,.2f}")
        
        if st.button("💾 Generate Quote", disabled=not can_save):
            new_row = {"Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}", "Customer": cin, "Product": f"PP {th}x{wd}x{lg}", "Weight": calc_wgt, "Price": final_p, "Status": "Pending Approval", "Date": datetime.now().strftime("%Y-%m-%d"), "Auth_By": auth_lvl, "Sales_Person": sperson, "Payment_Status": "Unpaid"}
            save_data(pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True), "QUOTE"); st.rerun()

    st.divider()
    ca1, ca2 = st.columns(2)
    with ca1:
        st.subheader("📋 Approvals")
        pwd = st.text_input("Manager Password", type="password")
        pend = q_df[q_df["Status"] == "Pending Approval"]
        for i, r in pend.iterrows():
            st.write(f"**{r['Doc_ID']}** | {r['Sales_Person']}")
            if (pwd in MANAGERS.values()) or is_boss:
                if st.button(f"Approve {r['Doc_ID']}", key=f"ap_{i}"):
                    q_df.at[i, "Status"] = "Approved"; save_data(q_df, "QUOTE"); st.rerun()
    with ca2:
        st.subheader("📤 WhatsApp")
        appr = q_df[q_df["Status"] == "Approved"]
        for i, r in appr.iterrows():
            match = c_df[c_df["Name"] == r["Customer"]]
            ph = str(match.iloc[0]["Phone"]) if not match.empty else "60123456789"
            st.link_button(f"Notify {r['Customer']}", f"https://wa.me/{ph}?text=Hi {r['Customer']}, Quote {r['Doc_ID']} is ready for RM {r['Price']:.2f}")

# --- 6. MODULE: SALES FOLLOW-UP (NEW!) ---
elif menu == "📞 Sales Follow-Up":
    st.header("📞 Sales Follow-Up & Analysis")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Status", "Sales_Person", "Loss_Reason", "Improvement_Plan"])
    
    # Show only Approved but not started jobs
    follow_df = q_df[q_df["Status"] == "Approved"]
    
    if follow_df.empty: st.success("No active quotes to follow up!")
    else:
        for i, r in follow_df.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.write(f"**{r['Customer']}** ({r['Sales_Person']})")
                c1.caption(f"Ref: {r['Doc_ID']} | Quote is currently Approved.")
                
                with c2.expander("❌ Mark as Lost"):
                    reason = st.selectbox("Reason for Failure", ["Price too high", "Lead time too long", "Competitor cheaper", "Customer cancelled"], key=f"rs_{i}")
                    improve = st.text_area("How can we improve?", key=f"im_{i}")
                    if st.button("Confirm Lost", key=f"lst_{i}"):
                        idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                        q_df.at[idx, "Status"] = "Lost"
                        q_df.at[idx, "Loss_Reason"] = reason
                        q_df.at[idx, "Improvement_Plan"] = improve
                        save_data(q_df, "QUOTE"); st.rerun()
                
                if c3.button("🏭 Send to Production", key=f"win_{i}"):
                    idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                    q_df.at[idx, "Status"] = "In Progress"
                    save_data(q_df, "QUOTE"); st.rerun()

    st.divider()
    with st.expander("📂 View Lost Jobs & Lessons Learned"):
        lost_df = q_df[q_df["Status"] == "Lost"]
        st.dataframe(lost_df[["Doc_ID", "Customer", "Sales_Person", "Loss_Reason", "Improvement_Plan"]], use_container_width=True)

# --- 7. MODULE: PRODUCTION ---
elif menu == "🏭 Production":
    st.header("🏭 Production Floor")
    q_df = load_data("QUOTE")
    active = q_df[q_df["Status"].isin(["In Progress"])]
    if active.empty: st.info("No active production.")
    for i, r in active.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Doc_ID']}** | {r['Customer']}")
            if st.button("Finish Production", key=f"f_{i}"):
                q_df.at[i, "Status"] = "Completed"; save_data(q_df, "QUOTE"); st.rerun()

# --- 8. MODULE: LOGISTICS ---
elif menu == "🚚 Logistics":
    st.header("🚚 Shipping")
    q_df, c_df = load_data("QUOTE"), load_data("CUSTOMER")
    done = q_df[q_df["Status"] == "Completed"]
    for i, r in done.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Customer']}** - {r['Doc_ID']}")
            c1, c2 = st.columns(2)
            c1.download_button("📄 DO", generate_pdf("DELIVERY ORDER", r, c_df).getvalue(), f"DO_{r['Doc_ID']}.pdf")
            c2.download_button("💰 INV", generate_pdf("INVOICE", r, c_df).getvalue(), f"INV_{r['Doc_ID']}.pdf")

# --- 9. MODULE: PAYMENTS ---
elif menu == "💰 Payments":
    st.header("💰 Aging Report")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Price", "Status", "Payment_Status", "Date"])
    unpaid = q_df[(q_df["Status"] == "Completed") & (q_df["Payment_Status"] != "Paid")].copy()
    if unpaid.empty: st.success("No unpaid invoices!")
    else:
        unpaid['Date_DT'] = pd.to_datetime(unpaid['Date'], errors='coerce')
        unpaid['Days'] = (datetime.now() - unpaid['Date_DT']).dt.days
        for i, r in unpaid.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                if r['Days'] > 30: c1.error(f"🚩 {r['Customer']} ({r['Days']} Days)"); c2.subheader(f"RM {r['Price']:,.2f}")
                else: c1.write(f"{r['Customer']} ({r['Days']} Days)"); c2.write(f"RM {r['Price']:,.2f}")
                if c3.button("Mark Paid", key=f"pay_{i}"):
                    idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                    q_df.at[idx, "Payment_Status"] = "Paid"; save_data(q_df, "QUOTE"); st.rerun()
