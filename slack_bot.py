import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
FRESHDESK_API_KEY = os.getenv("FRESHDESK_API_KEY")
FRESHDESK_DOMAIN = os.getenv("FRESHDESK_DOMAIN")

if not SLACK_BOT_TOKEN or not FRESHDESK_API_KEY:
    raise ValueError("Missing SLACK_BOT_TOKEN or FRESHDESK_API_KEY in environment variables.")

app = Flask(__name__)

# List of priority ticket creators
PRIORITY_USERS = [
    "adi stav", "alex zeldin", "gabriella kotin", "gali pruzansky", "mor levi",
    "nevo cohen", "omri geva", "ori avraham", "rotem cohen", "sun ben sela",
    "war room", "yotam ness", "yonatan daiti"
]

# Function to fetch tickets from Freshdesk
def get_tickets(robot_number, search_range="2_weeks"):
    date_ranges = {
        "2_weeks": 14,
        "1m": 30,
        "2m": 60
    }
    days_back = date_ranges.get(search_range, 14)
    search_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")

    tickets = []
    page = 1

    while len(tickets) < 500:
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

# Function to format and prioritize results
def format_ticket_response(tickets, robot_number):
    formatted_tickets = []
    priority_tickets = []
    regular_tickets = []

    for ticket in tickets:
        if str(robot_number) in ticket["subject"]:
            ticket_id = ticket["id"]
            ticket_subject = ticket["subject"]
            created_at = datetime.fromisoformat(ticket['created_at'][:-1]).strftime("%d/%m/%Y")
            ticket_link = f"https://{FRESHDESK_DOMAIN}/a/tickets/{ticket_id}"
            ticket_creator = ticket.get("requester", {}).get("name", "").lower()

            ticket_entry = (f"*Ticket:* <{ticket_link}|#{ticket_id}>\n"
                            f"*Subject:* {ticket_subject}\n"
                            f"*Date:* {created_at}\n"
                            "------------------------------------")

            # Prioritize certain ticket creators
            if ticket_creator in PRIORITY_USERS:
                priority_tickets.append(ticket_entry)
            else:
                regular_tickets.append(ticket_entry)

    # Combine results: priority tickets first
    formatted_tickets.extend(priority_tickets)
    formatted_tickets.extend(regular_tickets)

    return "\n".join(formatted_tickets) if formatted_tickets else f"No tickets found for robot {robot_number}."

# Slack command endpoint
@app.route("/slack", methods=["POST"])
def slack_command():
    data = request.form
    user_input = data.get("text")

    if not user_input:
        return jsonify({"response_type": "ephemeral", "text": "Please provide a robot number."})

    # Check if input contains a time modifier
    input_parts = user_input.split()
    robot_number = input_parts[0].strip()
    search_range = input_parts[1].strip() if len(input_parts) > 1 and input_parts[1] in ["1m", "2m"] else "2_weeks"

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
