import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
FRESHDESK_API_KEY = os.getenv("FRESHDESK_API_KEY")
FRESHDESK_DOMAIN = os.getenv("FRESHDESK_DOMAIN", "fabric.freshdesk.com")

if not SLACK_BOT_TOKEN or not FRESHDESK_API_KEY:
    raise ValueError("Missing SLACK_BOT_TOKEN or FRESHDESK_API_KEY in environment variables.")

app = Flask(__name__)

def get_tickets(robot_number, search_range="2_weeks"):
    date_ranges = {
        "2_weeks": 14,  # ברירת מחדל: שבועיים
        "1m": 30,       # חודש
        "2m": 60,       # חודשיים
    }
    days_back = date_ranges.get(search_range, 14)  # ברירת מחדל: 2_weeks
    search_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    tickets = []
    page = 1

    while len(tickets) < 300:
        url = f"https://{FRESHDESK_DOMAIN}/api/v2/tickets?page={page}&per_page=100&updated_since={search_date}"
        response = requests.get(url, auth=(FRESHDESK_API_KEY, "X"))

        if response.status_code != 200:
            return f"API Error: {response.text}"

        batch = response.json()
        if not batch:
            break

        tickets.extend(batch)
        page += 1

    return tickets

def format_ticket_response(tickets, robot_number):
    formatted_tickets = []

    for ticket in tickets:
        if str(robot_number) in ticket["subject"]:
            ticket_id = ticket["id"]
            ticket_subject = ticket["subject"]
            created_at = datetime.fromisoformat(ticket['created_at'][:-1]).strftime("%d/%m/%Y")
            ticket_link = f"https://{FRESHDESK_DOMAIN}/a/tickets/{ticket_id}"

            formatted_tickets.append(f"*Ticket:* <{ticket_link}|#{ticket_id}>\n"
                                     f"*Subject:* {ticket_subject}\n"
                                     f"*Date:* {created_at}\n"
                                     "------------------------------------")

    return "\n".join(formatted_tickets) if formatted_tickets else f"No tickets found for robot {robot_number}."

@app.route("/slack", methods=["POST"])
def slack_command():
    data = request.form
    user_input = data.get("text", "").strip()

    if not user_input:
        return jsonify({"response_type": "ephemeral", "text": "Please provide a robot number."})

    # Extracting robot number and optional search range
    parts = user_input.split()
    robot_number = parts[0]
    search_range = parts[1] if len(parts) > 1 and parts[1] in ["1m", "2m"] else "2_weeks"

    tickets = get_tickets(robot_number, search_range)

    if isinstance(tickets, str):
        return jsonify({"response_type": "ephemeral", "text": tickets})

    response_text = format_ticket_response(tickets, robot_number)

    return app.response_class(
        response=json.dumps({"response_type": "in_channel", "text": response_text}, ensure_ascii=False),
        status=200,
        mimetype="application/json"
    )

if __name__ == "__main__":
    app.run(port=3000)
