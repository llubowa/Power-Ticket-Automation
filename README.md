# Power Ticket Automation

An automated site power outage detection and ticketing system built with Django that integrates Nokia NFM-P network alarms with Zendesk to create, manage, close and submit customer incidents automatically.

## Overview

Power Ticket Automation is a production-ready backend system that:

- Periodically request for current alarms on nfm-p
- Identifies outages due to power
- Automatically creates Zendesk tickets
- Prevents duplicate incidents
- Closes the ticket when power restores
- Submits the incident to the incident database

Designed for telecom/NOC environments where reliability and automation are critical.

---

## Architecture

Alarm Source (NFM-P)
        ↓
Django Webhook Endpoint
        ↓
Outage Correlation Logic
        ↓
Zendesk Ticket Creation
        ↓
Database Tracking (SQLite)
        ↓
Zendesk Ticket Closure
        ↓
Incident Database submission


## Tech Stack

- Python 3.12
- Django
- Zenpy (Zendesk API client)
- Git (Version Control)
- Ubuntu Linux (Server Environment)

External Integrations:
- Zendesk (Ticketing)
- Nokia NFM-P (Alarm Source)
- Google sheets(Site IDs)

## Project Structure

Power-Ticket-Automation/
│
├── manage.py
├── db.sqlite3
├── requirements.txt
├── venv/
│
├── auto_ticketing_system/        # Django Project (Core Settings)
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
└── power_ticket/                 # Main Application Logic
    ├── admin.py
    ├── apps.py
    ├── models.py
    ├── views.py
    ├── urls.py
    ├── tests.py
    ├── scheduler.py
    ├── google_sheets.py
    ├── migrations/
    ├── config/
    │
    ├── nfmp/                     # Nokia NFM-P Integration
    │   ├── alarms_to_django.py
    │   └── auth_token.py
    │
    └── zendesk/                  # Zendesk Ticket Integration
        └── zendesk_client.py

### Clone Repository

```bash
git clone git@github.com:llubowa/Power-Ticket-Automation.git
cd Power-Ticket-Automation
```

### Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Create `.env` File

```
ZENDESK_EMAIL=your_email
ZENDESK_API_TOKEN=your_token
ZENDESK_SUBDOMAIN=your_subdomain
NSP_HOST=your_nsp_ip_address
NSP_CLIENT_ID=your_user_name
NSP_CLIENT_SECRET=your_password
```

### Run Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Start Server

```bash
python manage.py runserver
```  
