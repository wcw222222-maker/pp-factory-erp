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
    """Sends an email to the Boss & Managers if waste is too high."""
    try:
        sender_email = st.secrets["email"]["user"]
        sender_password = st.secrets["email"]["password"]
        receivers_str = st.secrets["email"]["receiver"]
        receiver_list = [email.strip() for email in receivers_str.split(",")]

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
        msg['To'] = ", ".join(receiver_list)

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_list, msg.as_string())
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
        if not match.empty: cust_addr = str(match.iloc
