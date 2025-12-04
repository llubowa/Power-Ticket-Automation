from apscheduler.schedulers.background import BackgroundScheduler
from power_ticket.nfmp.alarms_to_django import run_alarm_job

def start():
    scheduler = BackgroundScheduler()
    # Run job every 2 minutes
    scheduler.add_job(run_alarm_job, "interval", minutes=2, id="pull_nfm_alarms")
    scheduler.start()