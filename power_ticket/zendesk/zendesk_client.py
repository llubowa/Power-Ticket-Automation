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





# GOLD STANDARD timestamp parser
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

# ==========================
# Zendesk HTML Signature
# ==========================
SIGNATURE_HTML = """
    <hr>
    <table style="font-family:Arial, sans-serif; font-size:13px;">
    <tr>
        <td style="padding-right:10px; vertical-align:top; text-align:center;">
        <img src="https://csquared.com/wp-content/uploads/2024/02/cropped-favicon-192x192.png"
            width="90"
            alt="CSquared"
            style="display:block; margin:0 auto;">
        <br>
        <strong style="display:block;">C Squared</strong>
        </td>
        <td>
            CSquared Network Operations Team<br>
            Unit B3, Plot 7/11, Buganda Road, Kampala, Uganda<br>
            Email: <a href="mailto:support-ug@csquared.com">support-ug@csquared.com</a><br>
            <strong>Tel: +256312180500 | Toll Free: +256800280500</strong><br>
            <em><strong>'FibeRising' Africa for affordable broadband internet connectivity.</strong></em>
        </td>
    </tr>
    </table>

    <p style="font-family:Arial, sans-serif; font-size:13px;">
    If you received this communication by mistake, please do not forward it.
    It may contain confidential or privileged information. Please erase all
    copies and notify the sender.
    </p>
    """

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

    # Switched to HTML line breaks for better compatibility with html_body
    body_html = (
        f"Dear Valued Customer,<br><br>"
        f"Ticket Status: Open<br><br>"
        f"Name of NE/Circuit/Link affected: {alarm['objectFullName']}<br><br>"
        f"Date and Time Reported: {alarm_dt.strftime('%Y-%m-%d %H:%M')} hrs<br><br>"
        f"Client Services Affected: Yes<br><br>"
        f"Fault Priority: {alarm['severity']}<br><br>"
        f"Description: Site is not reachable.<br><br>"
        f"Kindly restore power at site and revert.<br><br>"
        f"Kind Regards,<br>"
    )

    # Combine the email body and the signature
    full_comment_html = f"""
    <div style="font-family:Arial, sans-serif; font-size:14px;">
        {body_html}
    </div>
    {SIGNATURE_HTML}
    """

    ticket = Ticket(
        subject=f"Outage at site: {alarm['objectFullName']}",
        requester=requester,
        collaborators=collaborators,
        priority="urgent",
        type="incident",
        brand=brand,
        comment={                 
            "html_body": full_comment_html,
            "public": True
        },
        custom_fields=[
            {"id": 360027172557, "value": "cleo-technical_ops-power-outage-customer"},
            {"id": 1900001737793, "value": fault_date},
            {"id": 360026291617, "value": fault_time},
        ]
    )

    created_ticket = client.tickets.create(ticket)

    # Zenpy usually returns the object directly; handle response safely
    ticket_id = getattr(getattr(created_ticket, 'ticket', None), 'id', None)

    if not ticket_id:
        raise Exception("Zendesk created ticket but returned no ID!")

    return ticket_id


# ================= CLOSE =================

def close_zendesk_ticket(ticket_id, alarm, fault_occurance_time):
    """
    Attempts to close a Zendesk ticket with an HTML signature.
    """
    if not ticket_id:
        return False

    alarm_dt = parse_alarm_timestamp(alarm)
    fault_local = dj_timezone.localtime(fault_occurance_time)

    if alarm_dt <= fault_occurance_time:
        #print("⚠️ Ignoring stale clear alarm")
        return False

    try:
        nfmp_name = alarm['objectFullName']
        db_name = db_site_name(nfmp_name)
        site_id = find_site_id(db_name) if db_name else None

        restoration_date = alarm_dt.strftime("%Y-%m-%d")
        restoration_time = alarm_dt.strftime("%H:%M")

        # Re-formatted as HTML to support the signature layout
        body_html = (
            f"Dear Valued Customer,<br><br>"
            f"Ticket status: Closed<br><br>"
            f"Name of NE/Circuit/Link: {nfmp_name}<br><br>"
            f"Date and Time Reported: {fault_local.strftime('%Y-%m-%d %H:%M')} hrs<br><br>"
            f"Date and Time Cleared: {alarm_dt.strftime('%Y-%m-%d %H:%M')} hrs<br><br>"
            f"Client Services Affected (Yes/No): Yes.<br><br>"
            f"Fault Priority: Critical.<br><br>"
            f"Reason for Outage: Power Outage at Site.<br><br>"
            f"Fault Resolution: Power restored at Site to restore service.<br><br>"
            f"Kind regards,<br>"
        )

        # Wrap everything in a div for consistent font styling
        full_comment_html = f"""
        <div style="font-family:Arial, sans-serif; font-size:14px;">
            {body_html}
        </div>
        {SIGNATURE_HTML}
        """

        ticket = Ticket(
            id=int(ticket_id),
            status="solved",  # Zendesk practice: Solved status before automated Closure
            comment={
                "html_body": full_comment_html,
                "public": True
            },
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
        #print(f"✅ Ticket {ticket_id} closed")
        return True

    except Exception as e:
        print(f"❌ Failed to close ticket {ticket_id}: {e}")
        return False


def close_CSQ_power_ticket(ticket_id, alarm, fault_occurance_time):
    """
    Attempts to close a Zendesk ticket with an HTML signature.
    """
    if not ticket_id:
        return False

    alarm_dt = parse_alarm_timestamp(alarm)
    fault_local = dj_timezone.localtime(fault_occurance_time)

    if alarm_dt <= fault_occurance_time:
        #print("⚠️ Ignoring stale clear alarm")
        return False

    try:
        nfmp_name = alarm['objectFullName']
        db_name = db_site_name(nfmp_name)
        site_id = find_site_id(db_name) if db_name else None

        restoration_date = alarm_dt.strftime("%Y-%m-%d")
        restoration_time = alarm_dt.strftime("%H:%M")

        # Re-formatted as HTML to support the signature layout
        body_html = (
            f"Dear Valued Customer,<br><br>"
            f"Ticket status: Closed<br><br>"
            f"Name of NE/Circuit/Link: {nfmp_name}<br><br>"
            f"Date and Time Reported: {fault_local.strftime('%Y-%m-%d %H:%M')} hrs<br><br>"
            f"Date and Time Cleared: {alarm_dt.strftime('%Y-%m-%d %H:%M')} hrs<br><br>"
            f"Client Services Affected (Yes/No): Yes.<br><br>"
            f"Fault Priority: Critical.<br><br>"
            f"Reason for Outage: Power Outage at Site.<br><br>"
            f"Fault Resolution: Power restored at Site to restore service.<br><br>"
            f"Kind regards,<br>"
        )

        # Wrap everything in a div for consistent font styling
        full_comment_html = f"""
        <div style="font-family:Arial, sans-serif; font-size:14px;">
            {body_html}
        </div>
        {SIGNATURE_HTML}
        """

        ticket = Ticket(
            id=int(ticket_id),
            status="solved",  # Zendesk practice: Solved status before automated Closure
            comment={
                "html_body": full_comment_html,  # ✅ Switched to html_body
                "public": True
            },
            custom_fields=[
                {"id": 1900001930773, "value": restoration_date},
                {"id": 360025570617, "value": restoration_time}
            ]
        )

        client.tickets.update(ticket)
        #print(f"✅ Ticket {ticket_id} closed")
        return True

    except Exception as e:
        print(f"❌ Failed to close ticket {ticket_id}: {e}")
        return False
