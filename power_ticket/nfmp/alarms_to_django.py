import os, requests, urllib3, json, re
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth

load_dotenv(override=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
NSP = os.environ["NSP_HOST"].strip()
CID = os.environ["NSP_CLIENT_ID"].strip()
SEC = os.environ["NSP_CLIENT_SECRET"].strip()

def get_token():
    url = f"https://{NSP}/rest-gateway/rest/api/v1/auth/token"
    r = requests.post(
        url, json={"grant_type":"client_credentials"},
        auth=HTTPBasicAuth(CID, SEC),
        timeout=30, verify=False
    )
    print("\n== Raw token response =="); print(r.text)
    r.raise_for_status()
    tok = r.json().get("access_token")
    if not tok: raise SystemExit("No access_token in response")
    print("\n== Access token (sensitive) =="); print(tok)
    return tok

FM_BASE = os.getenv("FM_BASE", f"https://{NSP}").strip()
ALARMS_URL = f"{FM_BASE}/FaultManagement/rest/api/v2/alarms/details/?alarmFilter=alarmName%2520like%2520'%2525Reachability%2525'"

def get_alarms_v2(token):
    hdrs = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    r = requests.get(ALARMS_URL, headers=hdrs, timeout=60, verify=False)
    if not r.ok:
        print(f"\nHTTP {r.status_code} on GET {ALARMS_URL}:\n{r.text}")
        r.raise_for_status()
    js = r.json()

    # --- v2 envelope parsing ---
    # Expect: {"response":{"totalRows":N,"data":[ "fdn:...Alarm:ID", ... ]}}
    if isinstance(js, dict) and "response" in js:
        resp = js["response"] or {}
        ids = resp.get("data", []) or []
        total = resp.get("totalRows", len(ids))
        return total, ids, js

    # Fallbacks (in case your cluster differs)
    if isinstance(js, list):
        return len(js), js, js
    for key in ("alarms", "items"):
        if key in js and isinstance(js[key], list):
            return len(js[key]), js[key], js

    # Unknown shape
    return 0, [], js

DJANGO_ALARM_URL = "http://127.0.0.1:8000/power_ticket/webhook/"   # server IP

def push_alarm_to_django(alarm):
    """Send one alarm to Django webhook"""
    try:
        r = requests.post(
            DJANGO_ALARM_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(alarm),
            timeout=10
        )
        print("Pushed alarm → Django:", r.status_code, r.text)
    except Exception as e:
        print("Error sending alarm:", e)

def extract_customer(name: str) -> str:
    """
    Extracts provider name from different naming formats.
    
    Handles:
    - UG-KLA-iWay_KampalaHospital → iWay
    - Simbanet-SGA Ntinda → Simbanet
    - UG-KLA-Datanet-TexolNamasuba → Datanet
    """

    # 1. If input contains a region prefix (UG-KLA-...), remove it
    if name.startswith("UG-"):
        # Remove first three segments e.g. UG-KLA-iWay_ → take 3rd segment as provider
        parts = name.split("-")
        # Ensure enough parts
        if len(parts) >= 3:
            # The provider is the third segment (may contain underscores)
            provider_segment = parts[2]
            # Provider ends before first underscore
            return provider_segment.split("_")[0]

    # 2. Format like "Simbanet-SGA Ntinda" → provider is first part before hyphen
    if "-" in name:
        return name.split("-")[0]

    # 3. Fallback: return first token
    return name.split("_")[0].split(" ")[0]

def customer_id(name: str) -> str:
    name = name.lower().strip()

    provider_map = {
        "intsol": 21,
        "intsolagencybankingmuyengahq": 21,
        "is": 21,
        "iway": 7,
        "echotel": 7,
        "liquid": 31,
        "liquidtelecom": 31,
        "sprint":27,
        "simbanet":5,
        "roke":2,
        "bcc":24,
        "gilat":12,
        "renu":10,
        "seacom":19

    }

    # Look for direct matches
    if name in provider_map:
        return provider_map[name]

    # If the name contains a provider keyword (more flexible)
    for key, value in provider_map.items():
        if key in name:
            return value

    # If nothing matches, return the raw name
    return name

def run_alarm_job():
    token = get_token()
    total, ids, raw = get_alarms_v2(token)
    print(f"Total alarms: {total}")

    for fdn in ids:
        objectFullName = fdn["affectedObjectName"]
        customer = extract_customer(objectFullName)
        id = customer_id(customer)

        alarm_payload = {
            "customer_id": id,
            "objectFullName": objectFullName,
            "severity": fdn["severity"],
            "lastTimeDetected": fdn["lastTimeDetected"]
        }

        push_alarm_to_django(alarm_payload)


"""if __name__ == "__main__":
    token = get_token()
    print("\n== Calling FaultManagement v2 /alarms ==")
    total, ids, raw = get_alarms_v2(token)

    print(f"\nTotal alarms (server-reported): {total}")
    print(f"Returned in this page: {len(ids)}")

    # Each element in `ids` is an FDN string, you need full alarm details
    for fdn in ids:
        objectFullName = fdn["affectedObjectName"]
        customer= extract_customer(objectFullName)
        id = customer_id(customer)
        alarm_payload = {
            "customer_id": id,   # You must map this later
            "objectFullName": objectFullName,
            "severity": fdn["severity"],
            "lastTimeDetected": fdn["lastTimeDetected"]
        }
        push_alarm_to_django(alarm_payload)"""
