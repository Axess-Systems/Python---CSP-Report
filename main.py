import os
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Base URL for the API
base_url = "https://api.cloud.com"

def get_customer_details():
    customers = {}
    i = 1
    while True:
        customer_id = os.getenv(f'CUSTOMER_ID_{i}')
        if not customer_id:
            break
        customers[customer_id] = {
            'client_id': os.getenv(f'CLIENT_ID_{i}'),
            'client_secret': os.getenv(f'CLIENT_SECRET_{i}'),
            'customer_name': os.getenv(f'CUSTOMER_NAME_{i}'),
            'site_id': os.getenv(f'SITE_ID_{i}')
        }
        i += 1
    return customers

def get_vda_status(token, customer_id, site_id):
    url = f"{base_url}/cvad/manage/Machines"
    auth_token = f"CwsAuth bearer={token}"
    headers = {
        'Accept': 'application/json',
        'Citrix-CustomerId': customer_id,
        'Citrix-InstanceId': site_id,
        'Authorization': auth_token
    }
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()

def create_report(data, customer_names):
    report_date = datetime.now().strftime('%d/%m/%Y')
    report = f"VDA Status Report\n"
    report += f"Report completed: {report_date}\n\n"

    for customer_id, vda_data in data.items():
        client_name = customer_names.get(customer_id, 'Unknown')
        report += f"Customer Name: {client_name}\n"

        machine_catalogs = {}
        for item in vda_data['Items']:
            machine_catalog = item.get('MachineCatalog', {}).get('Name', 'Unknown')
            if machine_catalog not in machine_catalogs:
                machine_catalogs[machine_catalog] = []
            machine_catalogs[machine_catalog].append(item)
        
        for machine_catalog, items in machine_catalogs.items():
            report += f"  Machine Catalog: {machine_catalog}\n"
            report += f"    Total Machines: {len(items)}\n"
            
            registered = sum(1 for item in items if item.get('RegistrationState') == 'Registered')
            unregistered = len(items) - registered
            
            report += f"    Registered: {registered}\n"
            report += f"    Unregistered: {unregistered}\n"
            
            in_maintenance = sum(1 for item in items if item.get('InMaintenanceMode', False))
            report += f"    In Maintenance Mode: {in_maintenance}\n"
            
            report += "\n"

    return report

def save_report(report):
    with open('vda_status_report.txt', 'w') as file:
        file.write(report)
    logging.info(f"Report saved as vda_status_report.txt")

def get_bearer_token(customer_id, client_id, client_secret):
    url = f"https://api.cloud.com/cctrustoauth2/{customer_id}/tokens/clients"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    payload = {
        'grant_type': 'client_credentials',
        'client_id': client_id,
        'client_secret': client_secret
    }
    response = requests.post(url, headers=headers, data=payload)
    response.raise_for_status()
    return response.json().get('access_token')

def send_email(subject, body, recipients):
    smtp_server = os.getenv('SMTP_SERVER')
    smtp_port = int(os.getenv('SMTP_PORT'))
    smtp_username = os.getenv('SMTP_USERNAME')
    smtp_password = os.getenv('SMTP_PASSWORD')
    use_tls = os.getenv('USE_TLS', 'False').lower() == 'true'

    msg = MIMEMultipart()
    msg['From'] = smtp_username
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject

    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP(smtp_server, smtp_port) as server:
        if use_tls:
            server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)

def vda_status_task(customers):
    logging.info(f"Running VDA status task for customers: {list(customers.keys())}")

    tokens = {}
    customer_names = {}
    for customer_id, details in customers.items():
        try:
            token = get_bearer_token(customer_id, details['client_id'], details['client_secret'])
            tokens[customer_id] = (token, details['site_id'])
            customer_names[customer_id] = details['customer_name']
        except Exception as e:
            logging.error(f"Failed to get token for {customer_id}: {str(e)}")

    data = {}
    for customer_id, (token, site_id) in tokens.items():
        try:
            data[customer_id] = get_vda_status(token, customer_id, site_id)
        except Exception as e:
            logging.error(f"Failed to get VDA status for {customer_id}: {str(e)}")

    report = create_report(data, customer_names)

    save_report(report)

    # Send email
    recipients = os.getenv('EMAIL_RECIPIENTS').split(',')
    subject = "VDA Status Report"
    send_email(subject, report, recipients)

    return report

if __name__ == "__main__":
    customers = get_customer_details()
    vda_status_task(customers)
