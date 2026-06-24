from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from .zendesk.zendesk_client import (
    create_zendesk_ticket,
    close_zendesk_ticket,
    parse_alarm_timestamp,
    close_CSQ_power_ticket
)
from .models import SiteOutage, Customer
from django.db import IntegrityError, transaction
import traceback


@csrf_exempt
def receive_alarm(request):
    if request.method != "POST":
        return JsonResponse({"error": "Invalid method"}, status=405)

    try:
        alarm = json.loads(request.body)
        action = alarm.get("action")
        site_name = alarm.get("objectFullName")

        # ================= OPEN (Site goes DOWN) =================
        if action == "OPEN":
            if alarm.get("severity") != "Critical":
                return JsonResponse({"status": "ignored_non_critical"})

            customer = Customer.objects.filter(customer_id=alarm.get("customer_id")).first()
            if not customer:
                return JsonResponse({"status": "ignored", "message": "Customer not found"})

            customer_emails = list(customer.emails.values_list("email", flat=True))
            alarm_time = parse_alarm_timestamp(alarm)

            try:
                with transaction.atomic():
                    # Check if the site is already marked as DOWN (is_active=True)
                    # get_or_create uses the UniqueConstraint to prevent duplicates
                    outage_record, created = SiteOutage.objects.get_or_create(
                        site_name=site_name,
                        is_active=True,  # Looking for an existing DOWN state
                        defaults={
                            "alarm_time": alarm_time,
                            "notification_sent": True
                        }
                    )

                    if not created:
                        # Site is already DOWN; ignore duplicate alarm
                        return JsonResponse({
                            "status": "already_down_ignored",
                            "ticket_id": outage_record.zendesk_ticket_id
                        })

                    # If created is True, this is a fresh outage
                    ticket_id = create_zendesk_ticket(alarm, customer_emails)
                    outage_record.zendesk_ticket_id = ticket_id
                    outage_record.save(update_fields=["zendesk_ticket_id"])

                    return JsonResponse({"status": "site_down_ticket_created", "ticket_id": ticket_id})

            except IntegrityError:
                # Secondary safety for race conditions
                existing = SiteOutage.objects.filter(site_name=site_name, is_active=True).first()
                return JsonResponse({
                    "status": "already_down_ignored",
                    "ticket_id": existing.zendesk_ticket_id if existing else None
                })

        # ================= CLOSE (Site goes UP) =================
        elif action == "CLOSE":
            customer_id = alarm.get("customer_id")

            with transaction.atomic():
                outage = (
                    SiteOutage.objects
                    .select_for_update()
                    .filter(site_name=site_name, is_active=True)
                    .first()
                )

                if not outage:
                    return JsonResponse({"status": "already_up_ignored"})

                ticket_id = outage.zendesk_ticket_id
                original_alarm_time = outage.alarm_time

                # Close ticket WHILE lock is held
                if customer_id == 1:
                    ticket_closed = close_CSQ_power_ticket(ticket_id, alarm, original_alarm_time)
                else:
                    ticket_closed = close_zendesk_ticket(ticket_id, alarm, original_alarm_time)

                if not ticket_closed:
                    return JsonResponse({"status": "ticket_close_failed"})

                # Only mark inactive if close succeeded
                outage.delete()
                #outage.is_active = False
                #outage.save(update_fields=["is_active"])

            return JsonResponse({"status": "site_restored_up", "ticket_id": ticket_id})
    except Exception:
        traceback.print_exc()
        return JsonResponse({"error": "Internal server error"}, status=500)

