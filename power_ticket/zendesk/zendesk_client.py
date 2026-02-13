# power_ticket/zendesk/zendesk_client.py

import os
from dotenv import load_dotenv
from zenpy import Zenpy
from zenpy.lib.api_objects import Ticket, Brand, User
from power_ticket.google_sheets import get_site_ids
from power_ticket.models import CustomerSites
from django.utils import timezone as dj_timezone
from datetime import datetime, timezone
#from django.utils import timezone

load_dotenv(override=True)

client = Zenpy(
    email=os.getenv("ZENDESK_EMAIL"),
    token=os.getenv("ZENDESK_TOKEN"),
    subdomain=os.getenv("ZENDESK_SUBDOMAIN")
)

BRAND_ID = int(os.getenv("ZENDESK_BRAND_ID"))



# ==========================
# Zendesk HTML Signature
# ==========================
SIGNATURE_HTML = """
<hr>
<table style="font-family:Arial, sans-serif; font-size:13px;">
<tr>
    <td style="padding-right:10px; vertical-align:top;">
        <img src="https://upload.wikimedia.org/wikipedia/commons/5/5f/C_Squared_logo.png"
             width="90" alt="CSquared">
    </td>
    <td>
        <strong>CSquared Network Operations Team</strong><br>
        Unit B3, Plot 7/11, Buganda Road, Kampala, Uganda<br>
        Email: <a href="mailto:support-ug@csquared.com">support-ug@csquared.com</a><br>
        Tel: +256312180500 | Toll Free: +256800280500<br>
        <em>'FibeRising' Africa for affordable broadband internet connectivity.</em>
    </td>
</tr>
</table>

<p style="font-size:10px;color:#666;">
If you received this communication by mistake, please do not forward it.
It may contain confidential or privileged information. Please erase all
copies and notify the sender.
</p>
"""



# ⭐ GOLD STANDARD timestamp parser
def parse_alarm_timestamp(alarm):
    alarm_ts = alarm["lastTimeDetected"] / 1000
    # Create UTC aware datetime
    utc_dt = datetime.fromtimestamp(alarm_ts, tz=timezone.utc)
    # Convert to Nairobi time
    local_dt = dj_timezone.localtime(utc_dt)
    return local_dt


def find_site_id(db_site_name):
    all_sites = get_site_ids()
    for row in all_sites:
        if row["Network ID"] == db_site_name:
            return row["Site ID"]
    return None


def db_site_name(nfmp_site_name):
    site = CustomerSites.objects.filter(
        Site_name_nfmp=nfmp_site_name
    ).first()

    return site.Site_name_master_db if site else None


# ================= CREATE =================

def create_zendesk_ticket(alarm, customer_emails):

    if not customer_emails:
        raise ValueError("No emails provided for this customer!")

    alarm_dt = parse_alarm_timestamp(alarm)

    requester = User(email=customer_emails[0])
    collaborators = [User(email=e) for e in customer_emails[1:]]

    brand = Brand(id=BRAND_ID)

    fault_date = alarm_dt.strftime("%Y-%m-%d")
    fault_time = alarm_dt.strftime("%H:%M")

    body = (
              f"Dear Valued Customer,\n\n"
              f"Ticket Status: Open\n\n"
              f"Name of NE/Circuit/Link affected: {alarm['objectFullName']}\n\n"
              f"Date and Time Reported: {alarm_dt.strftime("%Y-%m-%d %H:%M")} hrs\n\n"
              f"Client Services Affected: Yes\n\n"
              f"Fault Priority: {alarm['severity']}\n\n"
              f"Description: Site is not reachable. \n\n"
              f"Kindly restore power at site and revert.\n\n"
              f"Kind Regards,\n\n\n"
           )

        comment_body = f"""
        <pre style="font-family:Arial, sans-serif; font-size:14px;">
        {body_text}
        </pre>
        {SIGNATURE_HTML}
        """
           

    ticket = Ticket(
        subject=f"Outage at site: {alarm['objectFullName']}",
        requester=requester,
        collaborators=collaborators,
        description=body,
        priority="urgent",
        type="incident",
        brand=brand,
        custom_fields=[
            {"id": 360027172557, "value": "cleo-technical_ops-power-outage-customer"},
            {"id": 1900001737793, "value": fault_date},
            {"id": 360026291617, "value": fault_time},
        ]
    )

    created_ticket = client.tickets.create(ticket)

    ticket_id = getattr(getattr(created_ticket, 'ticket', None), 'id', None)

    if not ticket_id:
        raise Exception("Zendesk created ticket but returned no ID!")

    return ticket_id


# ================= CLOSE =================



def close_zendesk_ticket(ticket_id, alarm, fault_occurance_time):
    """
    Attempts to close a Zendesk ticket.
    Returns True if ticket was successfully closed, False otherwise.
    """

    if not ticket_id:
        return False  # Never crash alarm pipelines

    alarm_dt = parse_alarm_timestamp(alarm)
    fault_local = dj_timezone.localtime(fault_occurance_time)

    # ⭐ Ignore stale clears instead of crashing
    if alarm_dt <= fault_occurance_time:
        print("⚠️ Ignoring stale clear alarm")
        return False

    try:
        nfmp_name = alarm['objectFullName']
        db_name = db_site_name(nfmp_name)
        site_id = find_site_id(db_name) if db_name else None

        restoration_date = alarm_dt.strftime("%Y-%m-%d")
        restoration_time = alarm_dt.strftime("%H:%M")

        body = (
                  f"Dear Valued Customer,\n\n"
                  f"Ticket status: Closed\n\n"
                  f"Name of NE/Circuit/Link: {nfmp_name}\n\n"
                  f"Date and Time Reported: {fault_local.strftime("%Y-%m-%d %H:%M")} hrs\n\n"
                  f"Date and Time Cleared: {alarm_dt.strftime("%Y-%m-%d %H:%M")} hrs\n\n"
                  f"Client Services Affected (Yes/No): Yes.\n\n"
                  f"Fault Priority: Critical.\n\n"
                  f"Reason for Outage: Power Outage at Site.\n\n"
                  f"Fault Resolution: Power restored at Site to restore service.\n\n"
                  f"Kind regards,\n\n\n"
              )

        ticket = Ticket(
            id=int(ticket_id),
            status="solved",
            comment={"body": body, "public": True},
            custom_fields=[
                {"id": 1900001930773, "value": restoration_date},
                {"id": 360025570617, "value": restoration_time},
                {"id": 1900001931133, "value": True},
                {"id": 4416385593361, "value": "power_outage"},
                {"id": 360025574877, "value": "power_failure_-_customer"},
                {"id": 360025402958, "value": "customer"},
                {"id": 360025571117, "value": "site"},
                {"id": 1900001005553, "value": True},
                {"id": 360025575537, "value": site_id},
                {"id": 9053827490065, "value": "csquared_uganda"},
                {"id": 360026509317, "value": "p1_-_service_affecting"}
            ]
        )

        client.tickets.update(ticket)
        print(f"✅ Ticket {ticket_id} closed")
        return True

    except Exception as e:
        print(f"❌ Failed to close ticket {ticket_id}: {e}")
        return False


