from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
from .zendesk.zendesk_client import (
    create_zendesk_ticket,
    close_zendesk_ticket,
    parse_alarm_timestamp
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

        # ================= OPEN =================
        if action == "OPEN":

            if alarm.get("severity") != "Critical":
                return JsonResponse({"status": "ignored"})

            customer = Customer.objects.filter(
                customer_id=alarm.get("customer_id")
            ).first()

            if not customer:
                return JsonResponse({"status": "ignored", "message": "Customer not found"})

            customer_emails = list(
                customer.emails.values_list("email", flat=True)
            )

            alarm_time = parse_alarm_timestamp(alarm)
            site_name = alarm.get("objectFullName")

            try:
                with transaction.atomic():

                    # 🔧 CHANGED: rely on DB constraint, not pre-filter
                    outage_record, created = SiteOutage.objects.get_or_create(
                        site_name=site_name,
                        is_active=True,
                        defaults={
                            "alarm_time": alarm_time,
                            "notification_sent": True
                        }
                    )

                    if not created:
                        # 🔧 CHANGED: duplicate OPEN safely ignored
                        return JsonResponse({
                            "status": "duplicate_open_ignored",
                            "ticket_id": outage_record.zendesk_ticket_id
                        })

                    # 🆕 Zendesk ticket created ONLY once
                    ticket_id = create_zendesk_ticket(alarm, customer_emails)

                    outage_record.zendesk_ticket_id = ticket_id
                    outage_record.save(update_fields=["zendesk_ticket_id"])

                    return JsonResponse({
                        "status": "ticket_created",
                        "ticket_id": ticket_id
                    })

            except IntegrityError:
                # 🆕 Handles rare race-condition collisions
                existing = SiteOutage.objects.filter(
                    site_name=site_name,
                    is_active=True
                ).first()

                return JsonResponse({
                    "status": "duplicate_open_ignored",
                    "ticket_id": existing.zendesk_ticket_id if existing else None
                })

        # ================= CLOSE =================
        elif action == "CLOSE":

            site_name = alarm.get("objectFullName")

            outage = SiteOutage.objects.filter(
                site_name=site_name,
                is_active=True
            ).first()

            if not outage:
                return JsonResponse({"status": "no_active_outage"})

            # Attempt to close the Zendesk ticket
            ticket_closed = close_zendesk_ticket(
                outage.zendesk_ticket_id,
                alarm,
                outage.alarm_time
            )

            # Only mark outage inactive if the ticket was successfully closed
            if ticket_closed:  # ticket_closed should be True if ticket actually closed
                outage.is_active = False
                outage.save(update_fields=["is_active"])
                return JsonResponse({"status": "closed"})
            else:
                return JsonResponse({"status": "ticket_not_closed"})

        #return JsonResponse({"status": "ignored"})

        '''elif action == "CLOSE":

            site_name = alarm.get("objectFullName")

            outage = SiteOutage.objects.filter(
                site_name=site_name,
                is_active=True
            ).first()

            if not outage:
                return JsonResponse({"status": "no_active_outage"})

            close_zendesk_ticket(
                outage.zendesk_ticket_id,
                alarm,
                outage.alarm_time
            )

            # 🔧 CHANGED: do NOT delete, mark inactive
            outage.is_active = False
            outage.save(update_fields=["is_active"])

            return JsonResponse({"status": "closed"})

        return JsonResponse({"status": "ignored"})'''

    except Exception:
        print("\n🔥🔥🔥 FULL ERROR TRACEBACK 🔥🔥🔥")
        traceback.print_exc()
        print("🔥🔥🔥 END TRACEBACK 🔥🔥🔥\n")
        raise
