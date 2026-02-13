from django.db import models

# Create your models here.

# Main Customer model
class Customer(models.Model):
    customer_id = models.IntegerField(unique=True)
    customer_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.customer_name}"


class CustomerSites(models.Model):
    Site_name_nfmp = models.CharField(max_length=255,unique=True)
    Site_name_master_db = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.Site_name_master_db}"

# Separate model for customer emails (1-to-many relationship)
class CustomerEmail(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='emails')
    email = models.EmailField()

    def __str__(self):
        return f"{self.email} ({self.customer.customer_name})"

class SiteOutage(models.Model):
    site_name = models.CharField(max_length=255)
    alarm_time = models.DateTimeField()
    notification_sent = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)  # site currently down
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    zendesk_ticket_id = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["site_name", "is_active"],
                condition=models.Q(is_active=True),
                name="unique_active_site_outage"
            )
        ]

    def __str__(self):
        return f"{self.site_name} - {'DOWN' if self.is_active else 'UP'}"