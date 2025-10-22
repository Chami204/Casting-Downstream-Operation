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
    existing_headers = ws.row_values(1) if ws.row_values(1) else []
    
    # If no headers exist, create them from the first local data entry
    if not existing_headers:
        first_entry = st.session_state[local_key][0]
        headers = list(first_entry.keys())
        ws.update('1:1', [headers])
        existing_headers = headers
    
    # Prepare rows to append - map data to correct columns by header name
    rows_to_append = []
    for entry in st.session_state[local_key]:
        row = []
        for header in existing_headers:
            # Map each header to the corresponding data in the entry
            # Use empty string if the header doesn't exist in the entry
            row.append(entry.get(header, ""))
        rows_to_append.append(row)
    
    # Check for new columns in local data that don't exist in sheet
    all_local_headers = set()
    for entry in st.session_state[local_key]:
        all_local_headers.update(entry.keys())
    
    new_headers = all_local_headers - set(existing_headers)
    
    if new_headers:
        # Add new columns to the sheet
        updated_headers = existing_headers + list(new_headers)
        ws.update('1:1', [updated_headers])
        
        # Re-prepare rows with new column structure
        rows_to_append = []
        for entry in st.session_state[local_key]:
            row = []
            for header in updated_headers:
                row.append(entry.get(header, ""))
            rows_to_append.append(row)
    
    # Append all rows
    if rows_to_append:
        ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")
        
        # Clear local storage
        st.session_state[local_key] = []
        st.success(f"✅ {len(rows_to_append)} records synced to {history_sheet_name}!")
    else:
        st.error("No data to append!")

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
        
        # Track missing required fields
        missing_fields = []
        
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
                
                # Track if this required field is missing
                if not selected_value:
                    missing_fields.append(column)

        # Production Quantities Section (also required)
        st.subheader("📊 Production Quantities")
        
        # Create columns for better layout
        col1, col2 = st.columns(2)
        
        with col1:
            target_qty = st.number_input(
                "Target Qty (PCS) *", 
                min_value=0, 
                value=0, 
                step=1,
                key="target_qty"
            )
            entry["Target Qty (PCS)"] = target_qty
            
            actual_qty = st.number_input(
                "Actual Qty (PCS) *", 
                min_value=0, 
                value=0, 
                step=1,
                key="actual_qty"
            )
            entry["Actual Qty (PCS)"] = actual_qty
        
        with col2:
            reject_qty = st.number_input(
                "Reject Qty (PCS)", 
                min_value=0, 
                value=0, 
                step=1,
                key="reject_qty",
                help="Can be zero or above"
            )
            entry["Reject Qty (PCS)"] = reject_qty
            
            approved_qty = st.number_input(
                "Approved Qty (PCS) *", 
                min_value=0, 
                value=0, 
                step=1,
                key="approved_qty"
            )
            entry["Approved Qty (PCS)"] = approved_qty
        
        

        # ADD THE NEW FIELDS HERE - Reject Reason and Other Comments
        st.subheader("📝 Additional Information")
        
        # Reject Reason - text area for user to type anything
        reject_reason = st.text_area(
            "Reject Reason",
            placeholder="Enter the reason for rejects (if any)...",
            key="reject_reason",
            help="Optional: Describe why items were rejected"
        )
        entry["Reject Reason"] = reject_reason
        
        # Other Comments - text area for user to type anything
        other_comments = st.text_area(
            "Other Comments", 
            placeholder="Enter any additional comments or observations...",
            key="other_comments",
            help="Optional: Any other relevant information"
        )
        entry["Other Comments"] = other_comments
        
        # Form buttons - always enabled
        col1, col2, col3 = st.columns(3)
        
        with col1:
            submitted = st.form_submit_button("💾 Save Locally")
        
        with col2:
            sync_button = st.form_submit_button("☁️ Sync to Google Sheets")
        
        with col3:
            clear_button = st.form_submit_button("🗑️ Clear Form")

    # Handle form submissions
    if submitted:
        # Check for missing fields and show specific warnings
        if missing_fields:
            st.error(f"❌ The following required fields are missing: {', '.join(missing_fields)}")
        else:
            save_locally(entry, "local_data")
    
    if sync_button:
        if missing_fields:
            st.error(f"❌ Cannot sync data. The following required fields are missing: {', '.join(missing_fields)}")
        else:
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
        total_target = sum(entry.get("Target Qty (PCS)", 0) for entry in local_data)
        total_approved = sum(entry.get("Approved Qty (PCS)", 0) for entry in local_data)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Target", f"{total_target} PCS")
        with col2:
            st.metric("Total Actual", f"{total_actual} PCS")
        with col3:
            st.metric("Total Approved", f"{total_approved} PCS")
        with col4:
            st.metric("Total Rejects", f"{total_reject} PCS")
        
        # Calculate overall efficiency
        if total_target > 0:
            overall_efficiency = (total_actual / total_target) * 100
            st.info(f"🏭 Overall Production Efficiency: {overall_efficiency:.1f}%")
        
        if total_actual > 0:
            overall_reject_rate = (total_reject / total_actual) * 100
            st.info(f"🏭 Overall Rejection Rate: {overall_reject_rate:.1f}%")

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
