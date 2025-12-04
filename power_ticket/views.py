from django.shortcuts import render

# Create your views here.
import json
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Customer
from datetime import datetime
from django.core.mail import send_mail

ZENDESK_API_URL = "https://<your-subdomain>.zendesk.com/api/v2/tickets.json"
ZENDESK_API_TOKEN = "<your-zendesk-api-token>"
ZENDESK_USER = "<your-email>/token" 

@csrf_exempt
def receive_alarm(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            customer_id = data.get("customer_id")  # get customer_id from API data
            site_name = data.get("objectFullName")
            alarm_time = datetime.fromtimestamp(data.get("lastTimeDetected") / 1000)

            # Get customer by customer_id
            customer = Customer.objects.filter(customer_id=customer_id).first()

            if customer:
                subject = f"[Test] Outage at Site: {site_name}"
                body = (
                    f"Dear Valued Customer,\n\n"
                    f"Ticket Status: Open\n\n"
                    f"Name of NE/Circuit/Link affected: '{site_name}'\n\n"
                    f"Date and Time Reported: {alarm_time}.\n\n"
                    f"Client Services Affected (Yes/No): Yes\n\n"
                    f"Fault Priority: {data.get('severity')}\n\n"
                    f"Description: Site is not reachable\n\n"
                    f"Kindly restore power at site and revert.\n\n\n"
                    f"Regards,\nNOC Team"
                )

                for email_obj in customer.emails.all():
                    # send_to_zendesk(email_obj.email, subject, body)
                    send_test_email(email_obj.email, subject, body)

                return JsonResponse({"message": "Notification sent"}, status=200)
            else:
                return JsonResponse({"error": "Customer not found"}, status=404)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid method"}, status=405)


def send_test_email(recipient_email, subject, message):
    send_mail(
        subject,
        message,
        "llubowa@csquared.com",
        [recipient_email],       # To email (you can hardcode yours here)
        fail_silently=False,
    )

def send_to_zendesk(recipient_email, subject, message):
    payload = {
        "ticket": {
            "subject": subject,
            "comment": {
                "body": message
            },
            "priority": "urgent",
            "requester": {
                "name": "NFM-P Auto Alarm",
                "email": recipient_email
            }
        }
    }

    headers = {
        "Content-Type": "application/json"
    }

    response = requests.post(
        ZENDESK_API_URL,
        headers=headers,
        auth=(ZENDESK_USER, ZENDESK_API_TOKEN),
        json=payload
    )

    print("Zendesk response:", response.status_code, response.text)
