# --- CUSTOM CSS FOR HIGH CONTRAST & VISIBLE HEADER ---
st.markdown("""
    <style>
    /* 1. Main Background - Light Blue */
    .stApp {
        background-color: #f0f8ff;
    }
    
    /* 2. Sidebar Background - Slightly Darker Blue */
    [data-testid="stSidebar"] {
        background-color: #e1f5fe;
        border-right: 2px solid #b3e5fc;
    }

    /* 3. TOP HEADER BAR - FORCE LIGHT BLUE (Fixes the visibility issue) */
    header[data-testid="stHeader"] {
        background-color: #f0f8ff !important;
    }

    /* 4. FORCE ALL TEXT TO BLACK */
    .stMarkdown, .stText, p, div, span, label, li {
        color: #000000 !important;
    }

    /* 5. Headers - Dark Blue */
    h1, h2, h3, h4, h5, h6 {
        color: #01579b !important;
    }

    /* 6. Metrics - Blue Numbers */
    [data-testid="stMetricValue"] {
        color: #0288d1 !important;
    }
    
    /* 7. Input Fields - White Background */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div, .stTextArea>div>div>textarea {
        background-color: #ffffff !important;
        color: #000000 !important;
        border: 1px solid #b3e5fc;
    }

    /* 8. Buttons - Blue */
    .stButton>button {
        background-color: #0288d1 !important;
        color: white !important;
        border-radius: 5px;
        border: none;
    }
    </style>
    """, unsafe_allow_html=True)
