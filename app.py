#test
import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import pytz

# ------------------ SETTINGS ------------------
APP_TITLE = "Die Casting Production Downstream Data"
SHEET_NAME = "Casting_downstream"  # Changed to match your spreadsheet name
DOWNSTREAM_CONFIG_SHEET = "Downstream_config"
DOWNSTREAM_HISTORY_SHEET = "Downstream_history"
TIME_FORMAT_DATE = "%Y-%b-%d"  # 2025-AUG-01 format
TIME_FORMAT_TIME = "%H:%M"     # 24 hour time
SRI_LANKA_TZ = pytz.timezone('Asia/Colombo')

# ------------------ USER CREDENTIALS ------------------
USER_CREDENTIALS = {
    "Team Leader A": "Team@A",
    "Team Leader B": "Team@B",
    "Team Leader C": "Team@C",
    "Supervisor": "Team@123"
}

# ------------------ STREAMLIT PAGE CONFIG ------------------
st.set_page_config(page_title=APP_TITLE, layout="centered")
st.title(APP_TITLE)

# ------------------ SESSION STATE INIT ------------------
for var in ["logged_in", "logged_user", "local_data"]:
    if var not in st.session_state:
        st.session_state[var] = False if "logged" in var else []

# ------------------ GOOGLE SHEET CONNECTION ------------------
def get_gs_client():
    try:
        if 'gcp_service_account' not in st.secrets:
            st.error("Google Service Account credentials not found in secrets.")
            return None
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds_dict = {
            "type": st.secrets["gcp_service_account"]["type"],
            "project_id": st.secrets["gcp_service_account"]["project_id"],
            "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
            "private_key": st.secrets["gcp_service_account"]["private_key"].replace('\\n', '\n'),
            "client_email": st.secrets["gcp_service_account"]["client_email"],
            "client_id": st.secrets["gcp_service_account"]["client_id"],
            "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
            "token_uri": st.secrets["gcp_service_account"]["token_uri"],
            "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
            "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"]
        }
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Failed to authenticate with Google Sheets: {str(e)}")
        return None

def get_gsheet_data(sheet_name):
    client = get_gs_client()
    if client:
        try:
            return client.open(sheet_name)
        except gspread.exceptions.SpreadsheetNotFound:
            st.error(f"❌ Spreadsheet '{sheet_name}' not found. Please check the spreadsheet name and ensure it's shared with the service account.")
            return None
    else:
        return None

def read_sheet(sheet, worksheet_name):
    try:
        worksheet = sheet.worksheet(worksheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error reading worksheet '{worksheet_name}': {str(e)}")
        return pd.DataFrame()

# ------------------ LOCAL SAVE ------------------
def save_locally(data, storage_key):
    if storage_key not in st.session_state:
        st.session_state[storage_key] = []
    st.session_state[storage_key].append(data)
    st.success("Data saved locally!")

# ------------------ SYNC FUNCTION ------------------
def sync_local_data_to_sheet(local_key, history_sheet_name):
    if local_key not in st.session_state or len(st.session_state[local_key]) == 0:
        st.warning("No local data to sync!")
        return
    client = get_gs_client()
    if not client:
        st.error("Cannot connect to Google Sheets!")
        return

    try:
        ws = client.open(SHEET_NAME).worksheet(history_sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        st.error(f"Worksheet '{history_sheet_name}' not found!")
        return

    # Get existing headers
    existing_cols = ws.row_values(1) if ws.row_values(1) else []
    
    # Ensure User, Date, Time are first
    mandatory_cols = ["User", "Date", "Time"]
    other_existing_cols = [col for col in existing_cols if col not in mandatory_cols]
    
    # Collect new columns from local data
    new_cols = set()
    for entry in st.session_state[local_key]:
        for k in entry.keys():
            if k not in mandatory_cols and k not in other_existing_cols:
                new_cols.add(k)
    new_cols = list(new_cols)
    
    # Final column order
    final_cols = mandatory_cols + other_existing_cols + new_cols
    
    # Update header row only if columns changed
    if final_cols != existing_cols:
        ws.update('1:1', [final_cols])
    
    # Prepare rows to append
    rows_to_append = []
    for entry in st.session_state[local_key]:
        row = [entry.get(col, "") for col in final_cols]
        rows_to_append.append(row)

    ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
    
    # Clear local storage
    st.session_state[local_key] = []
    st.success(f"✅ {len(rows_to_append)} records synced to {history_sheet_name}!")

# ------------------ UNSYNCED DATA COUNT FUNCTION ------------------
def get_unsynced_counts():
    return len(st.session_state.get("local_data", []))

# ------------------ SYNC ALL FUNCTION ------------------
def sync_all_data():
    if st.session_state.get("local_data"):
        sync_local_data_to_sheet("local_data", DOWNSTREAM_HISTORY_SHEET)
    st.rerun()

# ------------------ DATA ENTRY FUNCTION ------------------
def downstream_data_entry(logged_user):
    df = st.session_state.downstream_config_df
    if df.empty:
        st.error("⚠️ Downstream_config not loaded!")
        return

    st.subheader("Please Enter the Downstream Data")
    
    # Get Sri Lankan date and time
    now_sri_lanka = datetime.now(SRI_LANKA_TZ)
    current_date = now_sri_lanka.strftime(TIME_FORMAT_DATE).upper()  # 2025-AUG-01
    current_time = now_sri_lanka.strftime(TIME_FORMAT_TIME)          # 24 hour format
    
    st.write(f"📅 Date: {current_date}")
    st.write(f"⏰ Time: {current_time}")

    entry = {"User": logged_user, "Date": current_date, "Time": current_time}

    with st.form(key="downstream_entry_form"):
        # Required Data Section (from config sheet)
        st.subheader("📋 Required Data")
        
        # Track if all required fields are filled
        all_required_filled = True
        
        # Get all column names from config (admin renamed columns)
        for column in df.columns:
            if column:  # Skip empty column names
                # Get dropdown options for this column (non-empty values)
                options = [str(x).strip() for x in df[column].dropna().unique() if str(x).strip() != ""]
                if options:
                    selected_value = st.selectbox(
                        f"{column} *", 
                        options, 
                        key=f"downstream_{column}",
                        index=None,
                        placeholder=f"Select {column}"
                    )
                    entry[column] = selected_value
                else:
                    selected_value = st.text_input(
                        f"{column} *", 
                        key=f"downstream_{column}",
                        placeholder=f"Enter {column}"
                    )
                    entry[column] = selected_value
                
                # Check if this required field is filled
                if not selected_value:
                    all_required_filled = False

        # Show Production Quantities only after required data is filled
        if all_required_filled:
            st.subheader("📊 Production Quantities")
            
            # Create columns for better layout
            col1, col2 = st.columns(2)
            
            with col1:
                entry["Target Qty (PCS)"] = st.number_input(
                    "Target Qty (PCS) *", 
                    min_value=0, 
                    value=0, 
                    step=1,
                    key="target_qty"
                )
                
                entry["Actual Qty (PCS)"] = st.number_input(
                    "Actual Qty (PCS) *", 
                    min_value=0, 
                    value=0, 
                    step=1,
                    key="actual_qty"
                )
            
            with col2:
                entry["Reject Qty (PCS)"] = st.number_input(
                    "Reject Qty (PCS)", 
                    min_value=0, 
                    value=0, 
                    step=1,
                    key="reject_qty",
                    help="Can be zero or above"
                )
                
                entry["Approved Qty (PCS)"] = st.number_input(
                    "Approved Qty (PCS) *", 
                    min_value=0, 
                    value=0, 
                    step=1,
                    key="approved_qty"
                )
            
            # Calculate efficiency metrics (informational only)
            if entry["Target Qty (PCS)"] > 0:
                efficiency = (entry["Actual Qty (PCS)"] / entry["Target Qty (PCS)"]) * 100
                st.info(f"📈 Production Efficiency: {efficiency:.1f}%")
            
            if entry["Actual Qty (PCS)"] > 0:
                reject_rate = (entry["Reject Qty (PCS)"] / entry["Actual Qty (PCS)"]) * 100
                st.info(f"📉 Rejection Rate: {reject_rate:.1f}%")
            
            # Check if all production quantities are filled
            production_filled = (
                entry["Target Qty (PCS)"] is not None and
                entry["Actual Qty (PCS)"] is not None and
                entry["Approved Qty (PCS)"] is not None
            )
            
            # Form buttons - only enable if all data is filled
            col1, col2, col3 = st.columns(3)
            
            with col1:
                submitted = st.form_submit_button(
                    "💾 Save Locally", 
                    disabled=not (all_required_filled and production_filled)
                )
            
            with col2:
                sync_button = st.form_submit_button(
                    "☁️ Sync to Google Sheets",
                    disabled=not (all_required_filled and production_filled)
                )
            
            with col3:
                clear_button = st.form_submit_button("🗑️ Clear Form")
        else:
            st.warning("⚠️ Please fill all required data fields above to proceed to Production Quantities")
            
            # Disabled buttons when required data is not filled
            col1, col2, col3 = st.columns(3)
            
            with col1:
                submitted = st.form_submit_button("💾 Save Locally", disabled=True)
            
            with col2:
                sync_button = st.form_submit_button("☁️ Sync to Google Sheets", disabled=True)
            
            with col3:
                clear_button = st.form_submit_button("🗑️ Clear Form")

    if submitted:
        save_locally(entry, "local_data")
    
    if sync_button:
        sync_local_data_to_sheet("local_data", DOWNSTREAM_HISTORY_SHEET)
        st.rerun()
    
    if clear_button:
        st.rerun()
    
    # Logout button outside the form
    if st.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.session_state.logged_user = ""
        st.rerun()

# ------------------ LOAD CONFIG SHEETS ------------------
sheet = get_gsheet_data(SHEET_NAME)
if sheet:
    if "downstream_config_df" not in st.session_state:
        st.session_state.downstream_config_df = read_sheet(sheet, DOWNSTREAM_CONFIG_SHEET)
else:
    st.error("❌ Unable to connect to Google Sheets. Please check your configuration.")

# ------------------ MAIN APP LOGIC ------------------
menu = ["Home", "Downstream Data Entry"]
choice = st.sidebar.selectbox("Main Sections", menu)

# HOME SECTION
if choice == "Home":
    st.markdown(f"<h2 style='text-align: center;'>Welcome to {APP_TITLE}</h2>", unsafe_allow_html=True)
    st.markdown("<h4 style='text-align: center;'>Please select a section to continue</h4>", unsafe_allow_html=True)
    
    # Add sync status and button
    st.markdown("---")
    st.subheader("📊 Data Sync Status")
    
    # Get counts of unsynced data
    unsynced_count = get_unsynced_counts()
    
    if unsynced_count > 0:
        st.warning(f"⚠️ You have {unsynced_count} unsynced records!")
        
        # Show sync button
        if st.button("🔄 Sync All Data to Google Sheets", type="primary", use_container_width=True):
            sync_all_data()
    else:
        st.success("✅ All data is synced with Google Sheets!")
        
    # Quick stats if there's any data
    if st.session_state.get("local_data"):
        st.subheader("📈 Quick Statistics")
        local_data = st.session_state.local_data
        total_actual = sum(entry.get("Actual Qty (PCS)", 0) for entry in local_data)
        total_reject = sum(entry.get("Reject Qty (PCS)", 0) for entry in local_data)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Total Actual Production", f"{total_actual} PCS")
        with col2:
            st.metric("Total Rejects", f"{total_reject} PCS")

# DOWNSTREAM DATA ENTRY SECTION
elif choice == "Downstream Data Entry":
    if st.session_state.logged_in:
        downstream_data_entry(st.session_state.logged_user)
    else:
        st.header("🔑 Downstream Data Login")
        selected_user = st.selectbox("Select Username", list(USER_CREDENTIALS.keys()), key="downstream_user")
        entered_password = st.text_input("Enter Password", type="password", key="downstream_pass")
        if st.button("Login", key="downstream_login_btn"):
            if USER_CREDENTIALS.get(selected_user) == entered_password:
                st.session_state.logged_in = True
                st.session_state.logged_user = selected_user
                st.success(f"Welcome, {selected_user}!")
                st.rerun()
            else:
                st.error("❌ Incorrect password!")
