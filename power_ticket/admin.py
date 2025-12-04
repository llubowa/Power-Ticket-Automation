from django.contrib import admin

# Register your models here.
from .models import Customer, CustomerEmail

admin.site.register(Customer)
admin.site.register(CustomerEmail)