# --- 4. MODULE: QUOTATION & SALES (SECURE VERSION) ---
if menu == "📝 Quotation & Sales":
    st.header("📝 Sales Quotation & Approval")
    
    # 🔐 MANAGER CREDENTIALS
    # You can change these passwords here!
    MANAGERS = {
        "Iris": "iris888",
        "Tomy": "tomy999"
    }

    q_df = load_data("QUOTE", ["Doc_ID", "Customer", "Product", "Weight", "Price", "Status", "Date"])
    
    # --- PART A: NEW QUOTE FORM (Anyone can create) ---
    with st.expander("➕ Create New Quotation", expanded=False):
        with st.form("new_quote"):
            c1, c2 = st.columns(2)
            cust = c1.text_input("Customer Name")
            prod = c2.text_input("Product Spec (e.g. 0.8mm White)")
            wgt = c1.number_input("Target Weight (kg)", 100.0)
            price = c2.number_input("Total Price (RM)", 0.0)
            
            if st.form_submit_button("Submit Quote"):
                new_row = {
                    "Doc_ID": f"QT-{datetime.now().strftime('%y%m%d-%H%M')}",
                    "Customer": cust, "Product": prod, "Weight": wgt, "Price": price,
                    "Status": "Pending Approval", "Date": datetime.now().strftime("%Y-%m-%d")
                }
                updated = pd.concat([q_df, pd.DataFrame([new_row])], ignore_index=True)
                save_data(updated, "QUOTE")
                st.success("Quote Submitted! Waiting for Iris or Tomy.")
                st.rerun()

    # --- PART B: APPROVAL QUEUE (Password Protected) ---
    st.divider()
    st.subheader("📋 Manager Approval Queue")
    
    pending = q_df[q_df["Status"] == "Pending Approval"]
    
    if pending.empty:
        st.info("No pending quotes to approve.")
    else:
        # 🔐 LOGIN BOX
        st.markdown("### 🔒 Manager Authorization")
        col_auth1, col_auth2 = st.columns(2)
        manager_name = col_auth1.selectbox("Select Manager", ["Select", "Iris", "Tomy"])
        manager_pass = col_auth2.text_input("Enter Password", type="password")
        
        # Check Password
        is_authorized = False
        if manager_name in MANAGERS and manager_pass == MANAGERS[manager_name]:
            is_authorized = True
            st.success(f"✅ Welcome, {manager_name}. You may authorize jobs.")
        elif manager_pass:
            st.error("❌ Wrong Password")

        # Display Jobs
        for idx, row in pending.iterrows():
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{row['Doc_ID']}** | {row['Customer']}")
                c1.write(f"📦 {row['Product']} - {row['Weight']}kg @ RM {row['Price']}")
                
                # Only show the Approve button if Authorized
                if is_authorized:
                    if c2.button(f"✅ AUTHORIZE", key=f"auth_{idx}"):
                        # Find the real index to update
                        real_idx = q_df[q_df["Doc_ID"] == row["Doc_ID"]].index[0]
                        q_df.at[real_idx, "Status"] = "Approved / Pending Production"
                        save_data(q_df, "QUOTE")
                        st.balloons()
                        st.rerun()
                else:
                    c2.markdown("🚫 *Locked*")
