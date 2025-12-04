from django.apps import AppConfig


class PowerTicketConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'power_ticket'

    def ready(self):
        from .scheduler import start
        start()

