import os, requests, urllib3, json, re
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from collections import defaultdict
import time

TIME_THRESHOLD = 300000   # 5 minutes in milliseconds

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
    #print("\n== Raw token response =="); print(r.text)
    r.raise_for_status()
    tok = r.json().get("access_token")
    if not tok: raise SystemExit("No access_token in response")
    #print("\n== Access token (sensitive) =="); print(tok)
    return tok

FM_BASE = os.getenv("FM_BASE", f"https://{NSP}").strip()
DJANGO_ALARM_URL = "http://127.0.0.1:8000/power_ticket/webhook/"   # server IP
ALARMS_URL = f"{FM_BASE}/FaultManagement/rest/api/v2/alarms/details/?alarmFilter=alarmName%2520like%2520'%2525Reachability%2525'"


def get_alarms_v2(token, fm_base, filter_str):
    url = f"{fm_base}/FaultManagement/rest/api/v2/alarms/details"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    params = {"alarmFilter": filter_str}

    r = requests.get(url, headers=headers, params=params, timeout=60, verify=False)

    if not r.ok:
        print(f"\nHTTP {r.status_code}:\n{r.text}")
        r.raise_for_status()

    js = r.json()

    # Extract alarm dictionaries safely
    return js.get("response", {}).get("data", [])

def correlate_dyinggasp_linkdown(alarms):
    """
    Returns correlated alarms where:
    - Same NE
    - Same Port
    - LinkDown occurs within 5 minutes of DyingGasp
    """

    grouped = defaultdict(lambda: {"dying": [], "linkdown": []})

    # Group alarms
    for alarm in alarms:

        ne = alarm.get("neName")
        port = alarm.get("affectedObjectName")
        name = alarm.get("alarmName")
        time = alarm.get("lastTimeDetected")

        if not ne or not port or not time:
            continue

        key = (ne, port)

        if name == "DyingGaspSignal":
            grouped[key]["dying"].append(time)

        elif name == "LinkDown":
            grouped[key]["linkdown"].append(time)

    # Correlate
    matches = []

    for (ne, port), data in grouped.items():

        for dying_time in data["dying"]:
            for link_time in data["linkdown"]:

                if abs(link_time - dying_time) <= TIME_THRESHOLD:
                    matches.append({
                        "neName": ne,
                        "port": port,
                        "dying_time": dying_time,
                        "linkdown_time": link_time
                    })
                    break   # stop after first match

    return matches

def get_physical_link(token, fm_base, ne_name, port):

    url = f"{fm_base}/NetworkSupervision/rest/api/v1/physicalLinks"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # Convert "Port 1/1/1" -> "1/1/1"
    port_id = port.replace("Port ", "").strip()

    filter_str = f"name like '%{ne_name}:{port_id}%'"

    params = {"filter": filter_str}

    r = requests.get(url, headers=headers, params=params, timeout=60, verify=False)

    if not r.ok:
        #print(f"\nHTTP {r.status_code}:\n{r.text}")
        r.raise_for_status()

    js = r.json()

    # ✅ Correct parsing
    links = js.get("response", {}).get("data", [])

    if not links:
        return None

    # Return link names
    return [link.get("name") for link in links]

def get_peer_site(link_name, current_ne):
    """
    Extract the peer NE from a physical link string.
    """

    if not link_name:
        return None

    # If list was returned
    if isinstance(link_name, list):
        link_name = link_name[0]

    try:
        left, right = link_name.split("--")

        left_ne = left.split(":")[0]
        right_ne = right.split(":")[0]

        return right_ne if left_ne == current_ne else left_ne

    except Exception:
        return None

def get_reachability_alarm(token, fm_base, ne_name):

    url = f"{fm_base}/FaultManagement/rest/api/v2/alarms/details"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    filter_str = f"alarmName like '%25Reachability%25' and neName ='{ne_name}'"


    params = {"alarmFilter": filter_str}

    r = requests.get(url, headers=headers, params=params, timeout=60, verify=False)

    if not r.ok:
        #print(f"\nHTTP {r.status_code}:\n{r.text}")
        r.raise_for_status()

    alarms = r.json().get("response", {}).get("data", [])

    if not alarms:
        return None

    # Return only fields you care about
    extracted = []

    for alarm in alarms:
        extracted.append({
            "neName": alarm.get("neName"),
            "neId": alarm.get("neId"),
            "lastTimeDetected": alarm.get("lastTimeDetected")
        })

    return extracted

def push_alarm_to_django(alarm):
    """Send one alarm to Django webhook"""
    try:
        r = requests.post(
            DJANGO_ALARM_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(alarm),
            timeout=10
        )
        #print("Pushed alarm → Django:", r.status_code, r.text)
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
        "csq":1,
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
        "bluecrane":24,
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
    filter_str = "alarmName in ('DyingGaspSignal','LinkDown')"
    alarms = get_alarms_v2(token, FM_BASE, filter_str)
    matches = correlate_dyinggasp_linkdown(alarms)
    seen_sites = set()
    for match in matches:

        link = get_physical_link(
            token,
            FM_BASE,
            match["neName"],
            match["port"]
        )

        peer_site = get_peer_site(link, match["neName"])

        if not peer_site:
            continue

        if peer_site in seen_sites:
            continue

        seen_sites.add(peer_site)

        reachability = get_reachability_alarm(
            token,
            FM_BASE,
            peer_site
        )

        objectFullName = reachability[0]["neName"]
        customer = extract_customer(objectFullName)
        id = customer_id(customer)

        alarm_payload = {
            "customer_id": id,
            "objectFullName": objectFullName,
            "severity": "Critical",
            "lastTimeDetected": reachability[0]["lastTimeDetected"],
            "action": "OPEN" 
        }

        push_alarm_to_django(alarm_payload)

    filter_str_reboot = "alarmName in ('NodeRebooted')"
    reboot_alarms = get_alarms_v2(token, FM_BASE, filter_str_reboot)
    
    for alarm in reboot_alarms:
        
        objectFullName = alarm["neName"]
        payload = {
            "objectFullName": objectFullName,
            "severity": "Critical",
            "lastTimeDetected": alarm["lastTimeDetected"],
            "action": "CLOSE"
        }
        push_alarm_to_django(payload)
        #print("Pushed NodeReboot alarm to Django")


