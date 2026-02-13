from django.contrib import admin

# Register your models here.
from .models import Customer, CustomerEmail,SiteOutage,CustomerSites

admin.site.register(Customer)
admin.site.register(CustomerEmail)
admin.site.register(SiteOutage)
admin.site.register(CustomerSites)