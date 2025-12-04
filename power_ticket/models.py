from django.db import models

# Create your models here.

# Main Customer model
class Customer(models.Model):
    customer_id = models.IntegerField(unique=True)
    customer_name = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.customer_name}"

# Separate model for customer emails (1-to-many relationship)
class CustomerEmail(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='emails')
    email = models.EmailField()

    def __str__(self):
        return f"{self.email} ({self.customer.customer_name})"