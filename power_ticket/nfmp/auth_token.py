import os
import json
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

# Load .env and let it override any exported vars (avoids confusion when you change creds)
load_dotenv(override=True)

NSP = os.environ["NSP_HOST"]              # e.g. "nsp.lab.local"
CID = os.environ["NSP_CLIENT_ID"]
SEC = os.environ["NSP_CLIENT_SECRET"]

url = f"https://{NSP}/rest-gateway/rest/api/v1/auth/token"
payload = {"grant_type": "client_credentials"}

resp = requests.post(
    url,
    json=payload,
    auth=HTTPBasicAuth(CID, SEC),
    timeout=30,
    verify=False   # LAB ONLY: disables TLS certificate verification
)
resp.raise_for_status()

# Keep response format identical to Postman: print raw JSON text
print(resp.text)
