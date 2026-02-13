import gspread
from oauth2client.service_account import ServiceAccountCredentials

# 1️⃣ Define the scope for Google APIs
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 2️⃣ Load credentials from JSON file
creds = ServiceAccountCredentials.from_json_keyfile_name(
    "power_ticket/config/google_service.json",  # path to your JSON
    scope
)

# 3️⃣ Authorize gspread client
client = gspread.authorize(creds)

# 4️⃣ Open the Google Sheet by name
sheet = client.open("Dummy Master DB").sheet1  # replace "Site IDs" with your sheet name

# 5️⃣ Fetch all records
def get_site_ids():
    return sheet.get_all_records()