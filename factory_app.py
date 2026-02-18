import streamlit as st
import smtplib
from email.mime.text import MIMEText
import pandas as pd
from datetime import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import io
import time
import re
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors

def send_waste_alert(doc_id, customer, waste_pct, real_input, target_weight):
    """Sends an email to the Boss if waste is too high."""
    try:
        # Get credentials from your Streamlit Secrets
        sender_email = st.secrets["email"]["user"]
        sender_password = st.secrets["email"]["password"]
        receiver_email = st.secrets["email"]["receiver"] # Your email

        subject = f"🚨 HIGH WASTE ALERT: {doc_id} ({customer})"
        body = f"""
        Boss, we have a high waste issue in production!
        
        Ref: {doc_id}
        Customer: {customer}
        Target Weight: {target_weight:.2f} kg
        Actual Input: {real_input:.2f} kg
        -----------------------------------
        WASTE PERCENTAGE: {waste_pct:.1f}% 🚩
        
        Please check Machine/Operator settings.
        """

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = receiver_email

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, [receiver_email], msg.as_string())
        return True
    except Exception as e:
        st.error(f"Email Alert Failed: {e}")
        return False

def send_daily_summary(q_df):
    """Calculates today's metrics and sends an end-of-day email to the Boss."""
    try:
        sender_email = st.secrets["email"]["user"]
        sender_password = st.secrets["email"]["password"]
        receivers_str = st.secrets["email"]["receiver"]
        receiver_list = [email.strip() for email in receivers_str.split(",")]

        # Get today's date
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        # Filter the data for TODAY
        today_quotes = q_df[q_df["Date"] == today_str]
        today_paid = q_df[q_df["Date_Paid"] == today_str]
        
        # Calculate Math
        new_sales = today_quotes[today_quotes["Status"] != "Lost"]["Price"].sum()
        collected_cash = today_paid["Price"].sum()
        quotes_count = len(today_quotes)
        
        subject = f"📊 Daily Sales Summary: {today_str}"
        body = f"""
        Boss, here is the End of Day Report for PP Products SDN BHD ({today_str}):
        
        💰 TOTAL NEW SALES (Generated Today): RM {new_sales:,.2f}
        📝 TOTAL QUOTES CREATED: {quotes_count}
        
        💵 TOTAL CASH COLLECTED TODAY: RM {collected_cash:,.2f}
        
        Have a great evening!
        Miss PP 👩‍💼
        """

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = ", ".join(receiver_list)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_list, msg.as_string())
        return True
    except Exception as e:
        st.error(f"Daily Summary Failed: {e}")
        return False

# --- 1. THEME & PAGE CONFIG ---
st.set_page_config(page_title="PP Products ERP", layout="wide", initial_sidebar_state="expanded")

# --- CUSTOM CSS: DARK GREEN BUTTON MODE ---
st.markdown("""
    <style>
    .stApp { background-color: #f0f8ff; }
    [data-testid="stSidebar"] { background-color: #e1f5fe; border-right: 2px solid #b3e5fc; }
    header[data-testid="stHeader"] { background-color: #f0f8ff !important; }
    
    /* Text Colors - Keep Orange Theme for text */
    .stMarkdown, .stText, p, div, span, label, li, h1, h2, h3, h4, h5, h6, b, strong { color: #d84315 !important; }
    [data-testid="stMetricValue"] { color: #bf360c !important; }
    
    /* Inputs */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div, .stTextArea>div>div>textarea {
        background-color: #ffffff !important; color: #d84315 !important; border: 2px solid #ffab91;
    }
    
    /* BUTTONS - DARK GREEN */
    .stButton>button { 
        background-color: #2e7d32 !important; 
        color: white !important; 
        border-radius: 5px; 
        border: none; 
        font-weight: bold; 
    }
    .stButton>button:hover { 
        background-color: #1b5e20 !important; 
        color: white !important; 
    }
    
    .stSuccess, .stError, .stInfo, .stWarning { background-color: #ffffff !important; color: #d84315 !important; }
    div[data-testid="stDataFrame"] div { color: #000000 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CLOUD CONNECTION ---
@st.cache_resource
def get_db_connection():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open("PP_ERP_Database")
    except Exception as e:
        st.error(f"Connection Failed: {e}"); return None

# --- 3. DATA ENGINE ---
@st.cache_data(ttl=5)
def load_data(sheet_name):
    try:
        client = get_db_connection()
        if not client: return pd.DataFrame()
        ws = client.worksheet(sheet_name)
        return pd.DataFrame(ws.get_all_records())
    except: return pd.DataFrame()

def save_data(df, sheet_name):
    try:
        client = get_db_connection()
        ws = client.worksheet(sheet_name)
        df = df.fillna("") 
        ws.clear(); ws.update([df.columns.values.tolist()] + df.values.tolist())
        load_data.clear() 
    except Exception as e: st.error(f"Save Error: {e}")

def ensure_cols(df, cols):
    if df.empty: return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            is_num = any(x in c for x in ["Price", "Weight", "Thick", "Width", "Length", "Current_Weight_kg", "Input_Weight", "Waste_Kg"])
            df[c] = 0.0 if is_num else ""
    return df

# --- 4. INVENTORY ENGINE ---
def update_inventory(product_name, weight_change, operation):
    try:
        client = get_db_connection()
        ws = client.worksheet("INVENTORY")
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        if "Product" not in df.columns: df["Product"] = ""
        if "Current_Weight_kg" not in df.columns: df["Current_Weight_kg"] = 0.0
        
        df["Current_Weight_kg"] = pd.to_numeric(df["Current_Weight_kg"], errors='coerce').fillna(0.0)

        match = df[df["Product"] == product_name]
        
        if match.empty:
            if operation == "ADD":
                new_row = {"Product": product_name, "Current_Weight_kg": float(weight_change), "Last_Updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            else:
                return False, "Product not found."
        else:
            idx = match.index[0]
            current_w = float(df.at[idx, "Current_Weight_kg"])
            
            if operation == "ADD":
                df.at[idx, "Current_Weight_kg"] = current_w + float(weight_change)
            elif operation == "SUBTRACT":
                if current_w < float(weight_change):
                    return False, f"Not enough stock! Current: {current_w}kg"
                df.at[idx, "Current_Weight_kg"] = current_w - float(weight_change)
            
            df.at[idx, "Last_Updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            
        save_data(df, "INVENTORY")
        return True, "Updated"
    except Exception as e:
        return False, str(e)

# --- 5. PDF ENGINE ---
def generate_pdf(doc_type, data, customer_df):
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    p.setFont("Helvetica-Bold", 16); p.drawString(50, height - 50, "PP PRODUCTS SDN BHD")
    p.setFont("Helvetica", 9); p.drawString(50, height - 65, "28 Jalan Mas Jaya 3, Cheras 43200, Selangor")
    p.line(50, height - 85, width - 50, height - 85)
    
    cust_addr = "No Address Provided"
    if not customer_df.empty:
        match = customer_df[customer_df["Name"] == data['Customer']]
        if not match.empty: cust_addr = str(match.iloc[0].get("Address", "No Address"))

    p.setFont("Helvetica-Bold", 11); p.drawString(50, height - 120, "BILL / SHIP TO:")
    p.setFont("Helvetica", 10); p.drawString(50, height - 135, f"{data['Customer']}")
    t = p.beginText(50, height - 150); t.setFont("Helvetica", 9); t.textLines(cust_addr); p.drawText(t)
    
    p.drawRightString(width - 50, height - 135, f"Date: {data['Date']}")
    p.drawRightString(width - 50, height - 150, f"Ref: {data['Doc_ID']}")
    
    y = height - 230
    p.setFillColor(colors.orange); p.rect(50, y, width - 100, 20, fill=1, stroke=0)
    p.setFillColor(colors.black); p.setFont("Helvetica-Bold", 10)
    p.drawString(60, y + 6, "Description"); p.drawString(350, y + 6, "Weight (kg)")
    if doc_type == "INVOICE": p.drawString(480, y + 6, "Total (RM)")
    
    y -= 25; p.setFont("Helvetica", 10)
    p.drawString(60, y, f"{data['Product']}"); p.drawString(350, y, f"{data['Weight']:.2f}")
    if doc_type == "INVOICE": p.drawString(480, y, f"{data['Price']:,.2f}")

    y_f = 120; p.line(50, y_f, width - 50, y_f)
    p.setFont("Helvetica-Bold", 8); p.drawString(50, y_f - 15, "TERMS & CONDITIONS:")
    tc = ["1. Terms: 30 Days.", "2. Overdue: 1.5% interest.", "3. Public Bank: 3123-XXXX-XXXX"] if doc_type == "INVOICE" else ["1. Received in good condition.", "2. No claims after signing."]
    y_t = y_f - 25
    for line in tc: p.drawString(50, y_t, line); y_t -= 10
    
    p.drawString(50, 50, "_"*30); p.drawString(50, 40, "Authorized Signature")
    p.drawRightString(width - 50, 50, "_"*30); p.drawRightString(width - 50, 40, "Customer Chop & Sign")
    p.save(); return buffer

# --- 6. MISS PP AI LOGIC (SMARTER VERSION) ---
def get_smart_response(user_text):
    """
    This function checks for keywords to give a 'human' answer 
    before we try to calculate math.
    """
    text = user_text.lower()
    
    # 1. GREETINGS
    if any(x in text for x in ["hi", "hello", "hey", "morning", "afternoon", "boss"]):
        return "Hello Boss! 👋 I'm ready to calculate. Tell me what the customer needs (e.g. '2000pcs 0.5mm')."
    
    # 2. AGREEMENT / THANKS
    if any(x in text for x in ["thanks", "thank", "ok", "yes", "proceed", "good", "nice"]):
        return "You're welcome Boss! 😊 Let me know if you need another quote."

    # 3. QUESTION: RECOMMENDATIONS
    if any(x in text for x in ["recommend", "suggest", "best", "packaging", "box"]):
        return (
            "💡 **Recommendation:**\n"
            "- For **Layer Pads**: I suggest **0.5mm or 0.6mm** (Sandy/Emboss).\n"
            "- For **Heavy Boxes**: Better use **0.8mm or 1.0mm**.\n\n"
            "Do you want me to quote for 1000pcs of 0.5mm to start?"
        )

    # 4. QUESTION: PRICE
    if any(x in text for x in ["price", "cost", "expensive", "rate", "cheap"]):
        return (
            "💰 **Current Pricing:**\n"
            "- **Standard (>100kg):** RM 12.60/kg\n"
            "- **Mid Volume (<100kg):** RM 26.00/kg\n"
            "- **Sample (<10kg):** RM 36.00/kg\n\n"
            "Give me the Qty & Thickness, and I'll tell you the exact total!"
        )

    # 5. QUESTION: DELIVERY
    if any(x in text for x in ["delivery", "time", "long", "when", "ship"]):
        return "🚚 **Lead Time:** Usually 7-10 days for production. If urgent, please ask Mr. Boss to check the production schedule tab!"

    # 6. DEFAULT FAIL (If no numbers found)
    return None # Return None so the main loop knows to check for math next

def parse_sales_request(user_text):
    # This function STRICTLY looks for numbers to calculate math
    user_text = user_text.lower()
    if not re.search(r'\d', user_text): return None # No numbers = No math

    response = {}
    qty_match = re.search(r'(\d+)\s*(pcs|pieces|pc)', user_text)
    response['qty'] = int(qty_match.group(1)) if qty_match else 1000 
    
    thick_match = re.search(r'(\d?\.?\d+)\s*(mm)', user_text)
    response['thick'] = float(thick_match.group(1)) if thick_match else 0.5
    
    if "black" in user_text: response['color'] = "Black"
    elif "white" in user_text: response['color'] = "White"
    elif "special" in user_text: response['color'] = "Special"
    else: response['color'] = "Silk Nature"
    
    if "emboss" in user_text: response['surface'] = "Sandy / Emboss"
    elif "lining" in user_text: response['surface'] = "Lining / Shining"
    elif "shining" in user_text and "sandy" in user_text: response['surface'] = "Sandy / Shining"
    else: response['surface'] = "Sandy / Emboss" 
    
    return response

# --- 7. SIDEBAR ---
with st.sidebar:
    st.title("🛡️ PP ERP ADMIN")
    menu = st.radio("MAIN MENU", ["👩‍💼 Ask Miss PP", "🏠 Dashboard", "📝 Quote & CRM", "📞 Sales Follow-Up", "🏭 Production", "🚚 Logistics", "💰 Payments", "💸 Commission", "📦 Warehouse"])
    st.divider()
    boss_pwd = st.text_input("Boss Override", type="password")
    is_boss = (boss_pwd == "boss777")
    if is_boss: st.success("🔓 BOSS MODE ACTIVE")

# --- 8. MODULE: MISS PP (SMART CHAT AGENT) ---
if menu == "👩‍💼 Ask Miss PP":
    st.header("👩‍💼 Chat with Miss PP")
    st.caption("Type your request below like you are talking to Sujita.")

    if "messages" not in st.session_state: st.session_state.messages = []
    if "latest_quote" not in st.session_state: st.session_state.latest_quote = None

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if st.session_state.latest_quote:
        with st.container(border=True):
            c1, c2 = st.columns([2, 1])
            lq = st.session_state.latest_quote
            c1.success(f"**Ready to Save:** RM {lq['total_price']:,.2f} ({lq['qty']}pcs)")
            if c2.button("🚀 Save Official Quote", use_container_width=True):
                q_df = load_data("QUOTE")
                new_row = {"Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}", "Customer": "Cash (Miss PP)", "Product": lq['desc'], "Weight": lq['weight'], "Price": lq['total_price'], "Status": "Pending Approval", "Date": datetime.now().strftime("%Y-%m-%d"), "Auth_By": "MISS_PP", "Sales_Person": "Sujita", "Payment_Status": "Unpaid", "Shipped_Status": "No", "Input_Weight": 0, "Waste_Kg": 0, "Date_Paid": ""}
                save_data(pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True), "QUOTE")
                st.toast("✅ Saved successfully!")
                st.session_state.latest_quote = None; time.sleep(1); st.rerun()

    if prompt := st.chat_input("Type request (e.g. '2000pcs 0.5mm black sandy'):"):
        with st.chat_message("user"): st.markdown(prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("assistant"):
            with st.spinner("Miss PP is thinking..."):
                time.sleep(0.5) 
                
                # STEP 1: Check for Conversation/Knowledge First
                chat_reply = get_smart_response(prompt)
                
                if chat_reply:
                    st.markdown(chat_reply)
                    st.session_state.messages.append({"role": "assistant", "content": chat_reply})
                
                # STEP 2: If no chat reply, try to Calculate Math
                else:
                    data = parse_sales_request(prompt)
                    if data:
                        wd, lg = 650.0, 900.0
                        weight = (data['thick'] * wd * lg * 0.91 * data['qty']) / 1000000
                        price_rate = 12.60
                        if weight < 10: price_rate = 36.00
                        elif weight < 100: price_rate = 26.00
                        total_price = weight * price_rate
                        
                        prod_desc = f"PP {data['surface']} {data['color']} {data['thick']}mm x {wd}mm x {lg}mm"
                        
                        response_text = (
                            f"**Quote Generated!** 📝\n\n"
                            f"📦 **Product:** {data['color']} {data['surface']}\n"
                            f"📏 **Specs:** {data['thick']}mm x {wd}mm x {lg}mm\n"
                            f"🔢 **Qty:** {data['qty']} pcs\n"
                            f"⚖️ **Weight:** {weight:.2f} kg\n"
                            f"💰 **Total:** RM {total_price:,.2f} (Rate: RM {price_rate:.2f}/kg)\n\n"
                            f"*WhatsApp Draft (Copy & Send):*\n"
                            f"```\nHi Boss! Quote for {data['qty']}pcs {data['thick']}mm is RM {total_price:,.2f}. Proceed?\n```"
                        )
                        st.markdown(response_text)
                        st.session_state.messages.append({"role": "assistant", "content": response_text})
                        st.session_state.latest_quote = {"desc": prod_desc, "weight": weight, "total_price": total_price, "qty": data['qty']}
                        st.rerun()
                    else:
                        # STEP 3: Total Failure (Nice Error Message)
                        fail_msg = "😅 I'm just a humble bot, I didn't understand that. Try asking about **Price**, **Recommendations**, or give me a **Qty** to calculate!"
                        st.markdown(fail_msg)
                        st.session_state.messages.append({"role": "assistant", "content": fail_msg})

# --- 9. MODULE: DASHBOARD ---
elif menu == "🏠 Dashboard":
    st.header("🏠 Factory & Sales Dashboard")
    # Make sure we load the Date and Date_Paid columns!
    q_df = ensure_cols(load_data("QUOTE"), ["Price", "Status", "Sales_Person", "Payment_Status", "Date", "Date_Paid"])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Revenue", f"RM {q_df[q_df['Status']=='Completed']['Price'].sum():,.2f}")
    c2.metric("Uncollected Cash", f"RM {q_df[(q_df['Status']=='Completed') & (q_df['Payment_Status']!='Paid')]['Price'].sum():,.2f}")
    c3.metric("Lead Source", f"Edward ({len(q_df[q_df['Sales_Person']=='Edward'])})", delta=f"Sujita ({len(q_df[q_df['Sales_Person']=='Sujita'])})")
    
    st.divider()
    
    # --- 🚨 NEW: BOSS ONLY DAILY SUMMARY BUTTON ---
    if is_boss:
        st.subheader("📧 End of Day Report")
        st.caption("Click this before you leave the factory to get today's sales and collection totals.")
        if st.button("📈 Send Daily Sales Summary Now", use_container_width=True):
            with st.spinner("Miss PP is compiling the report..."):
                if send_daily_summary(q_df):
                    st.success("✅ Daily Summary sent to your email successfully!")
        st.divider()
    # ----------------------------------------------

    st.subheader("📊 Sales Force Analytics")
    if not q_df.empty: st.bar_chart(q_df.groupby("Sales_Person")["Price"].sum())# --- 10. MODULE: QUOTE & CRM ---
elif menu == "📝 Quote & CRM":
    st.header("📝 Create Quotation")
    MANAGERS = {"Iris": "iris888", "Tomy": "tomy999"}
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date", "Auth_By", "Sales_Person", "Loss_Reason", "Improvement_Plan", "Payment_Status", "Shipped_Status", "Date_Paid"])
    c_df = ensure_cols(load_data("CUSTOMER"), ["Name", "Phone", "Address"])

    with st.expander("👤 Register New Customer"):
        with st.form("add_cust", clear_on_submit=True):
            n_name = st.text_input("Company Name")
            n_phone = st.text_input("WhatsApp (e.g. 60123456789)")
            n_addr = st.text_area("Address")
            if st.form_submit_button("Save"):
                clean_phone = ''.join(filter(str.isdigit, str(n_phone)))
                get_db_connection().worksheet("CUSTOMER").append_row([n_name, "", clean_phone, n_addr])
                st.success("Saved!"); load_data.clear(); time.sleep(1); st.rerun()

    with st.container(border=True):
        st.subheader("📐 PP Sheet Calculator")
        clist = c_df["Name"].tolist() if not c_df.empty else ["Cash"]
        c1, c2 = st.columns(2)
        cin = c1.selectbox("Select Customer", clist)
        sperson = c2.selectbox("Assigned Sales Person", ["Sujita", "Edward"])
        
        if cin != "Cash":
            match = c_df[c_df["Name"] == cin]
            if not match.empty:
                raw_ph = str(match.iloc[0]["Phone"])
                clean_ph = ''.join(filter(str.isdigit, raw_ph))
                if clean_ph:
                    st.link_button(f"🟢 Chat with {cin}", f"https://wa.me/{clean_ph}")

        sc1, sc2 = st.columns(2)
        surf_type = sc1.selectbox("Surface Type", ["Sandy / Emboss", "Sandy / Shining", "Shining / Shining", "Lining / Shining"])
        color_type = sc2.selectbox("Color", ["Silk Nature", "Black", "White", "Special"])
        
        col1, col2, col3, col4 = st.columns(4)
        th = col1.number_input("Thickness (mm)", 0.50, format="%.2f")
        wd = col2.number_input("Width (mm)", 650.0)
        lg = col3.number_input("Length (mm)", 900.0)
        qty = col4.number_input("Quantity (Pcs)", 1000)
        
        calc_wgt = (th * wd * lg * 0.91 * qty) / 1000000
        
        suggested_price = 12.60; price_msg = "Standard Rate"
        if calc_wgt > 0:
            if calc_wgt < 10: suggested_price = 36.00; price_msg = "⚠️ Low Volume (<10kg)"
            elif calc_wgt < 100: suggested_price = 26.00; price_msg = "⚠️ Mid Volume (<100kg)"
        
        st.caption(f"Material Pricing: **{price_msg}**")
        mat_rate = st.number_input("Material Price/KG (RM)", value=suggested_price)
        material_total = calc_wgt * mat_rate

        st.divider(); st.subheader("🎨 Silkscreen Printing")
        print_colors = st.number_input("Number of Colors", 0, 10, 0)
        printing_cost = 0.0
        if print_colors > 0:
            film_mold_cost = print_colors * 360.00
            run_cost = print_colors * 0.62 * qty
            printing_cost = film_mold_cost + run_cost
            st.info(f"🎨 Print Cost: RM {printing_cost:,.2f}")
        
        grand_total = material_total + printing_cost
        
        can_save, auth_lvl = True, "Standard"
        min_rate = 12.60
        if calc_wgt < 10: min_rate = 36.00
        elif calc_wgt < 100: min_rate = 26.00
        
        if mat_rate < min_rate:
            if is_boss: auth_lvl = "BOSS_BYPASS"; st.warning(f"⚠️ Boss Override Active")
            else: st.error(f"🚫 Min RM {min_rate}"); can_save = False
            
        st.success(f"💰 **TOTAL: RM {grand_total:,.2f}**")
        
        if st.button("💾 Finalize Quote", disabled=not can_save):
            prod_desc = f"PP {surf_type} {color_type} {th}mm x {wd}mm x {lg}mm"
            if print_colors > 0: prod_desc += f" + {print_colors} Color Print"
            new_row = {"Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}", "Customer": cin, "Product": prod_desc, "Weight": calc_wgt, "Price": grand_total, "Status": "Pending Approval", "Date": datetime.now().strftime("%Y-%m-%d"), "Auth_By": auth_lvl, "Sales_Person": sperson, "Payment_Status": "Unpaid", "Shipped_Status": "No", "Input_Weight": 0, "Waste_Kg": 0, "Date_Paid": ""}
            save_data(pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True), "QUOTE"); st.rerun()

    st.divider()
    ca1, ca2 = st.columns(2)
    with ca1:
        st.subheader("📋 Approvals")
        pwd = st.text_input("Authorize Code", type="password")
        pend = q_df[q_df["Status"] == "Pending Approval"]
        for i, r in pend.iterrows():
            st.write(f"**{r['Doc_ID']}** | {r['Sales_Person']}")
            if (pwd in MANAGERS.values()) or is_boss:
                if st.button(f"Approve {r['Doc_ID']}", key=f"ap_{i}"):
                    q_df.at[i, "Status"] = "Approved"; save_data(q_df, "QUOTE"); st.rerun()
    with ca2:
        st.subheader("📤 Notifications")
        appr = q_df[q_df["Status"] == "Approved"]
        for i, r in appr.iterrows():
            match = c_df[c_df["Name"] == r["Customer"]]
            ph = str(match.iloc[0]["Phone"]) if not match.empty else ""
            clean_ph = ''.join(filter(str.isdigit, ph))
            if clean_ph:
                st.link_button(f"WhatsApp {r['Customer']}", f"https://wa.me/{clean_ph}?text=Hi {r['Customer']}, Quote {r['Doc_ID']} for RM {r['Price']:.2f} is ready.")
            else:
                st.caption(f"No number for {r['Customer']}")

# --- 11. MODULE: SALES FOLLOW-UP ---
elif menu == "📞 Sales Follow-Up":
    st.header("📞 Sales Follow-Up")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Status", "Sales_Person", "Loss_Reason", "Improvement_Plan"])
    follow_df = q_df[q_df["Status"] == "Approved"]
    if follow_df.empty: st.info("No active quotes.")
    else:
        for i, r in follow_df.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.write(f"**{r['Customer']}** ({r['Sales_Person']})")
                with c2.expander("❌ Mark Lost"):
                    reason = st.selectbox("Reason", ["Price", "Competitor", "Lead Time", "Other"], key=f"rs_{i}")
                    if st.button("Confirm Loss", key=f"lst_{i}"):
                        idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                        q_df.at[idx, "Status"] = "Lost"; q_df.at[idx, "Loss_Reason"] = reason
                        save_data(q_df, "QUOTE"); st.rerun()
                if c3.button("🏗️ Production", key=f"win_{i}"):
                    idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                    q_df.at[idx, "Status"] = "In Progress"; save_data(q_df, "QUOTE"); st.rerun()

# --- 12. MODULE: PRODUCTION ---
elif menu == "🏭 Production":
    st.header("🏭 Production Queue")
    q_df = load_data("QUOTE")
    active = q_df[q_df["Status"] == "In Progress"]
    
    if active.empty:
        st.info("Lines idle. No active production orders.")
    
    for i, r in active.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Doc_ID']}** | {r['Customer']}")
            st.caption(f"{r['Product']} | Target: {r['Weight']} kg")
            
            with st.form(f"prod_fin_{i}"):
                real_input = st.number_input("Total Resin Input (kg)", min_value=0.0, step=1.0)
                if st.form_submit_button("✅ Finish & Calculate Waste"):
                    if real_input >= r['Weight']:
                        # WASTE CALCULATION
                        waste = real_input - r['Weight']
                        waste_pct = (waste / real_input) * 100 if real_input > 0 else 0
                        
                        # TRIGGER ALERT IF WASTE > 10%
                        if waste_pct > 10:
                            st.error(f"⚠️ HIGH WASTE: {waste_pct:.1f}%")
                            send_waste_alert(r['Doc_ID'], r['Customer'], waste_pct, real_input, r['Weight'])
                            st.warning("📩 High waste alert sent to Boss.")
                        else:
                            st.success(f"✅ Efficient Production: {waste_pct:.1f}% Waste")
                            
                        success, msg = update_inventory(r['Product'], r['Weight'], "ADD")
                        if success:
                            q_df.at[i, "Status"] = "Completed"
                            q_df.at[i, "Input_Weight"] = real_input
                            q_df.at[i, "Waste_Kg"] = waste
                            save_data(q_df, "QUOTE")
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(msg)
                    else:
                        st.error("Input must be at least the target weight!")

# --- 13. MODULE: LOGISTICS ---
elif menu == "🚚 Logistics":
    st.header("🚚 Logistics")
    q_df, c_df = load_data("QUOTE"), load_data("CUSTOMER")
    done = q_df[q_df["Status"] == "Completed"]
    for i, r in done.iterrows():
        with st.container(border=True):
            st.write(f"**{r['Customer']}** - {r['Doc_ID']}")
            c1, c2 = st.columns(2)
            c1.download_button("📄 DO", generate_pdf("DELIVERY ORDER", r, c_df).getvalue(), f"DO_{r['Doc_ID']}.pdf")
            c2.download_button("💰 INV", generate_pdf("INVOICE", r, c_df).getvalue(), f"INV_{r['Doc_ID']}.pdf")

# --- 14. MODULE: PAYMENTS ---
elif menu == "💰 Payments":
    st.header("💰 Aging & Collections")
    q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Customer", "Price", "Status", "Payment_Status", "Date", "Date_Paid"])
    unpaid = q_df[(q_df["Status"] == "Completed") & (q_df["Payment_Status"] != "Paid")].copy()
    
    if unpaid.empty: st.success("All Paid!")
    else:
        unpaid['Date_DT'] = pd.to_datetime(unpaid['Date'], errors='coerce')
        unpaid['Days'] = (datetime.now() - unpaid['Date_DT']).dt.days
        
        for i, r in unpaid.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                if r['Days'] > 30: c1.error(f"🚩 {r['Customer']} ({r['Days']} Days)")
                else: c1.write(f"{r['Customer']} ({r['Days']} Days)")
                c2.subheader(f"RM {r['Price']:,.2f}")
                if c3.button("Confirm Paid", key=f"pay_{i}"):
                    idx = q_df[q_df["Doc_ID"] == r["Doc_ID"]].index[0]
                    q_df.at[idx, "Payment_Status"] = "Paid"
                    q_df.at[idx, "Date_Paid"] = datetime.now().strftime("%Y-%m-%d") # RECORD DATE PAID
                    save_data(q_df, "QUOTE"); st.rerun()

# --- 15. MODULE: COMMISSION ---
elif menu == "💸 Commission":
    st.header("💸 Sales Commission Calculator")
    
    if not is_boss:
        st.warning("🔒 Restricted: Boss Only.")
    else:
        q_df = ensure_cols(load_data("QUOTE"), ["Doc_ID", "Sales_Person", "Price", "Payment_Status", "Date", "Date_Paid"])
        paid_df = q_df[q_df["Payment_Status"] == "Paid"].copy()
        
        paid_df['Inv_Date'] = pd.to_datetime(paid_df['Date'], errors='coerce')
        paid_df['Pay_Date'] = pd.to_datetime(paid_df['Date_Paid'], errors='coerce')
        paid_df['Days_Taken'] = (paid_df['Pay_Date'] - paid_df['Inv_Date']).dt.days
        
        def calc_commission_factor(row):
            if row['Days_Taken'] > 60: return 0.0 # Penalty
            if row['Days_Taken'] > 30: return 0.5 # Half Comm
            return 1.0 # Full Comm
            
        paid_df['Comm_Factor'] = paid_df.apply(calc_commission_factor, axis=1)

        st.subheader("👩 Sujita (Indoor)")
        su_df = paid_df[paid_df["Sales_Person"] == "Sujita"].copy()
        su_df['Commission'] = su_df['Price'] * 0.015 * su_df['Comm_Factor']
        
        c1, c2 = st.columns(2)
        c1.metric("Total Collected", f"RM {su_df['Price'].sum():,.2f}")
        c2.metric("Commission", f"RM {su_df['Commission'].sum():,.2f}")
        
        st.divider()

        st.subheader("👨 Edward (Outdoor)")
        ed_df = paid_df[paid_df["Sales_Person"] == "Edward"].copy()
        valid_sales = ed_df[ed_df['Days_Taken'] <= 60]['Price'].sum()
        
        threshold = 400000
        if valid_sales > threshold:
            excess_amount = valid_sales - threshold
            ed_df['Potential_Comm'] = ed_df.apply(lambda x: x['Price'] * 0.02 * x['Comm_Factor'] if x['Days_Taken'] <= 60 else 0, axis=1)
            total_potential = ed_df['Potential_Comm'].sum()
            effective_yield = total_potential / valid_sales if valid_sales > 0 else 0
            final_comm = excess_amount * effective_yield
            
            c3, c4, c5 = st.columns(3)
            c3.metric("Valid Sales", f"RM {valid_sales:,.2f}")
            c4.metric("Excess > 400k", f"RM {excess_amount:,.2f}")
            c5.metric("Final Commission", f"RM {final_comm:,.2f}")
        else:
            c3, c4 = st.columns(2)
            c3.metric("Valid Sales", f"RM {valid_sales:,.2f}")
            c4.error(f"❌ Target Missed (<400k)")

# --- 16. WAREHOUSE ---
elif menu == "📦 Warehouse":
    st.header("📦 Live Inventory")
    with st.expander("🛠️ Manual Stock Adjustment"):
        with st.form("man_stock"):
            st.warning("Manual Adjustment")
            p_name = st.text_input("Product Name")
            w_adj = st.number_input("Weight (+/-)", step=10.0)
            if st.form_submit_button("Update"):
                if p_name and w_adj != 0:
                    success, msg = update_inventory(p_name, w_adj, "ADD")
                    if success: st.success(f"Updated {p_name}"); time.sleep(1); st.rerun()
                else: st.error("Invalid Input")

    inv_df = load_data("INVENTORY")
    if not inv_df.empty: st.dataframe(inv_df, use_container_width=True)
    else: st.info("Empty Warehouse")
