import os, requests, urllib3, json, re
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from collections import defaultdict
import time
from requests.exceptions import RequestException

TIME_THRESHOLD = 300000   # 5 minutes in milliseconds

load_dotenv(override=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================================
# LOAD ENV VARIABLES
# ==========================================================
NSP_HOSTS = [
    host.strip()
    for host in os.getenv("NSP_HOSTS", "").split(",")
    if host.strip()
]

if not NSP_HOSTS:
    raise Exception("NSP_HOSTS not configured in .env")

CID = os.environ["NSP_CLIENT_ID"].strip()
SEC = os.environ["NSP_CLIENT_SECRET"].strip()

DJANGO_ALARM_URL = "http://127.0.0.1:8000/power_ticket/webhook/"

# ==========================================================
# CENTRAL FAILOVER REQUEST FUNCTION
# ==========================================================
def nsp_request(method, path, token=None, params=None, data=None, auth=None):

    headers = {"Content-Type": "application/json"}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    for host in NSP_HOSTS:
        url = f"https://{host}{path}"

        try:
            r = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                auth=auth,
                timeout=60,
                verify=False
            )

            if r.ok:
                #print(f"✅ Connected to NSP {host}")
                return r
            else:
                print(f"⚠ {host} returned {r.status_code}")

        except Exception as e:
            print(f"❌ {host} failed: {e}")

    raise Exception("All NSP hosts unreachable")


# ==========================================================
# TOKEN WITH FAILOVER
# ==========================================================
def get_token():

    path = "/rest-gateway/rest/api/v1/auth/token"

    for host in NSP_HOSTS:
        try:
            url = f"https://{host}{path}"

            r = requests.post(
                url,
                data={"grant_type": "client_credentials"},
                auth=HTTPBasicAuth(CID, SEC),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
                verify=False
            )

            r.raise_for_status()
            print(f"🔐 Token acquired from {host}")
            return r.json().get("access_token")

        except Exception as e:
            print(f"❌ Token failed on {host}: {e}")

    raise Exception("Failed to acquire token from all NSP hosts")


# ==========================================================
# API FUNCTIONS (NOW USING FAILOVER)
# ==========================================================
def get_alarms_v2(token, filter_str):

    r = nsp_request(
        "GET",
        "/FaultManagement/rest/api/v2/alarms/details",
        token=token,
        params={"alarmFilter": filter_str}
    )

    return r.json().get("response", {}).get("data", [])


def correlate_dyinggasp_linkdown(alarms):

    grouped = defaultdict(lambda: {"dying": [], "linkdown": []})

    for alarm in alarms:
        ne = alarm.get("neName")
        port = alarm.get("affectedObjectName")
        name = alarm.get("alarmName")
        time_detected = alarm.get("lastTimeDetected")

        if not ne or not port or not time_detected:
            continue

        key = (ne, port)

        if name == "DyingGaspSignal":
            grouped[key]["dying"].append(time_detected)

        elif name == "LinkDown":
            grouped[key]["linkdown"].append(time_detected)

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
                    break

    return matches


def get_physical_link(token, ne_name, port):

    port_id = port.replace("Port ", "").strip()
    filter_str = f"name like '%{ne_name}:{port_id}%'"

    r = nsp_request(
        "GET",
        "/NetworkSupervision/rest/api/v1/physicalLinks",
        token=token,
        params={"filter": filter_str}
    )

    links = r.json().get("response", {}).get("data", [])

    if not links:
        return None

    return [link.get("name") for link in links]


def get_peer_site(link_name, current_ne):

    if not link_name:
        return None

    if isinstance(link_name, list):
        link_name = link_name[0]

    try:
        left, right = link_name.split("--")
        left_ne = left.split(":")[0]
        right_ne = right.split(":")[0]
        return right_ne if left_ne == current_ne else left_ne
    except Exception:
        return None


def get_reachability_alarm(token, ne_name):

    filter_str = f"alarmName like '%25Reachability%25' and neName ='{ne_name}'"

    r = nsp_request(
        "GET",
        "/FaultManagement/rest/api/v2/alarms/details",
        token=token,
        params={"alarmFilter": filter_str}
    )

    alarms = r.json().get("response", {}).get("data", [])

    if not alarms:
        return None

    extracted = []

    for alarm in alarms:
        extracted.append({
            "neName": alarm.get("neName"),
            "neId": alarm.get("neId"),
            "lastTimeDetected": alarm.get("lastTimeDetected")
        })

    return extracted

def pf_site_name(token,nename,port):
    filter_str = (
        "neName like '%25{nename}%25' and name like '{port}'"
    )
    r = nsp_request(
        "GET",
        "/NetworkSupervision/rest/api/v1/ports",
        token=token,
        params={"alarmFilter": filter_str}
    )
    alarms = r.json().get("response", {}).get("data", [])

    if not alarms:
        return None
    site_name = alarms.get("description")
    return site_name
    

def sasm_cascased_linkdown_alarms(token):

    filter_str = (
        "alarmName like '%25LinkDown%25' "
        "and (neName like '%25SAS-M%25' or neName like '%25cascaded%25')"
    )

    r = nsp_request(
        "GET",
        "/FaultManagement/rest/api/v2/alarms/details",
        token=token,
        params={"alarmFilter": filter_str}
    )

    alarms = r.json().get("response", {}).get("data", [])

    if not alarms:
        return None

    extracted = []

    for alarm in alarms:

        ne_name = alarm.get("neName", "")
        port_raw = alarm.get("affectedObjectName", "")
        last_time = alarm.get("lastTimeDetected")

        if not ne_name or not port_raw:
            continue

        # ==============================
        # CASCADED FILTERING LOGIC
        # ==============================
        if "cascaded" in ne_name.lower():

            # Extract port number using regex (handles -ddm, :xxx, etc)
            match = re.search(r"1/1/(\d+)", port_raw)

            if not match:
                continue

            port_number = int(match.group(1))

            # Only allow ports 1 to 6
            if port_number < 1 or port_number > 6:
                continue

        # SAS-M → no port restriction
        site = pf_site_name(token,ne_name,port_raw)
        extracted.append({
            "neName": ne_name,
            "port": port_raw,
            "lastTimeDetected": last_time,
            "Name":site
        })


    return extracted



def push_alarm_to_django(alarm):

    try:
        requests.post(
            DJANGO_ALARM_URL,
            headers={"Content-Type": "application/json"},
            data=json.dumps(alarm),
            timeout=10
        )
    except Exception as e:
        print("Error sending alarm:", e)


# ==========================================================
# YOUR ORIGINAL BUSINESS LOGIC (UNCHANGED)
# ==========================================================
def extract_customer(name: str) -> str:

    if name.startswith("UG-"):
        parts = name.split("-")
        if len(parts) >= 3:
            provider_segment = parts[2]
            return provider_segment.split("_")[0]

    if "-" in name:
        return name.split("-")[0]

    return name.split("_")[0].split(" ")[0]


def customer_id(name: str) -> str:

    name = name.lower().strip()

    provider_map = {
        "intsol": 21,
        "csq": 1,
        "intsolagencybankingmuyengahq": 21,
        "is": 21,
        "iway": 7,
        "echotel": 7,
        "liquid": 31,
        "liquidtelecom": 31,
        "sprint": 27,
        "simbanet": 5,
        "roke": 2,
        "bcc": 24,
        "bluecrane": 24,
        "gilat": 12,
        "giat": 12,
        "renu": 10,
        "seacom": 19,
        "sombha": 16,
        "datanet": 29,
        "savanna": 3
    }

    if name in provider_map:
        return provider_map[name]

    for key, value in provider_map.items():
        if key in name:
            return value

    return name


def run_alarm_job():

    token = get_token()

    # OPEN logic
    #filter_str = "alarmName in ('DyingGaspSignal','LinkDown')"
    filter_str = (
    "(alarmName = 'DyingGaspSignal' "
    "or alarmName = 'LinkDown')"
    )
    alarms = get_alarms_v2(token, filter_str)
    matches = correlate_dyinggasp_linkdown(alarms)

    seen_sites = set()

    for match in matches:

        link = get_physical_link(token, match["neName"], match["port"])
        peer_site = get_peer_site(link, match["neName"])

        if not peer_site or peer_site in seen_sites:
            continue

        seen_sites.add(peer_site)

        reachability = get_reachability_alarm(token, peer_site)

        if not reachability:
            continue

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

    # CLOSE logic
    filter_str_reboot = "alarmName in ('NodeRebooted')"
    reboot_alarms = get_alarms_v2(token, filter_str_reboot)

    for alarm in reboot_alarms:

        objectFullName = alarm["neName"]
        customer = extract_customer(objectFullName)
        id = customer_id(customer)

        payload = {
            "customer_id": id,
            "objectFullName": objectFullName,
            "severity": "Critical",
            "lastTimeDetected": alarm["lastTimeDetected"],
            "action": "CLOSE"
        }

        push_alarm_to_django(payload)
    #sasm = sasm_cascased_linkdown_alarms(token)
    #print(sasm)    


if __name__ == "__main__":
    run_alarm_job()

