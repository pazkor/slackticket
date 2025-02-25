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

# רשימת משתמשים עם עדיפות גבוהה
PRIORITY_USERS = [
    "adi stav", "alex zeldin", "gabriella kotin", "gali pruzansky", "mor levi",
    "nevo cohen", "omri geva", "ori avraham", "rotem cohen", "sun ben sela",
    "war room", "yotam ness", "yonatan daiti"
]

# מילון בחירת אתר
SITE_MAP = {
    "1": "עמק",
    "2": "באר שבע",
    "3": "חולון"
}

USER_SELECTIONS = {}  # זיכרון זמני לקלט המשתמשים עבור `/SU`

# פונקציה לשליפת טיקטים מ-Freshdesk
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

# פורמט טיקטים, נותן עדיפות למשתמשים מסוימים
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

            if ticket_creator in PRIORITY_USERS:
                priority_tickets.append(ticket_entry)
            else:
                regular_tickets.append(ticket_entry)

    formatted_tickets.extend(priority_tickets)
    formatted_tickets.extend(regular_tickets)

    return "\n".join(formatted_tickets) if formatted_tickets else f"No tickets found for robot {robot_number}."

# שליפת מספר עמודות אחרון לפי אתר
def get_last_column(aisle, site):
    if site == "עמק":
        last_column_map = {1: 91, 2: 91, 7: 71}
        default_last_column = 74
    elif site == "חולון":
        last_column_map = {}
        default_last_column = 64
    elif site == "באר שבע":
        last_column_map = {1: 99, 2: 99}
        default_last_column = 98
    else:
        return None
    return last_column_map.get(aisle, default_last_column)

# חישוב מיקום בהתבסס על האתר שנבחר
def format_su_location_by_site(location_str, site):
    try:
        aisle, details, cell = location_str.split(":")
        side, column, floor = map(int, details.strip("()").split(","))

        side_desc = "שמאל" if side == -1 else "ימין"
        aisle = int(aisle)
        last_column = get_last_column(aisle, site)

        if last_column is None:
            return f"שגיאה: האתר '{site}' אינו מוכר."

        columns_from_back = last_column - column

        return (f"🔹 מעבר: {aisle}\n"
                f"🔹 צד: {side_desc} (כאשר מסתכלים מקדמת המעבר)\n"
                f"🔹 עמודה: {column}\n"
                f"🔹 קומה: {floor}\n"
                f"🔹 תא: {cell}\n"
                f"🔹 מספר עמודות לספור מהכניסה האחורית: {columns_from_back}\n\n"
                f"📌 **המספרים באתר מתחילים מ-0.**")
    except Exception:
        return f"שגיאה בפענוח המיקום: {location_str}"

# קליטת פקודות מסלאק
@app.route("/slack", methods=["POST"])
def slack_command():
    data = request.form
    user_id = data.get("user_id")  
    command = data.get("command")  
    user_input = data.get("text").strip()

    if not user_input:
        return jsonify({"response_type": "ephemeral", "text": "אנא הזן קלט מתאים."})

    # אם המשתמש הזין קוד מיקום - נבקש ממנו לבחור אתר
    if command == "/SU":
        USER_SELECTIONS[user_id] = user_input  
        response_text = (
            "📍 אנא בחר את האתר על ידי שליחת מספר מתאים:\n"
            "1️⃣ עמק\n"
            "2️⃣ באר שבע\n"
            "3️⃣ חולון"
        )

    # אם המשתמש בחר אתר אחרי שהזין קוד SU
    elif user_id in USER_SELECTIONS and user_input in SITE_MAP:
        location_str = USER_SELECTIONS.pop(user_id)  
        site = SITE_MAP[user_input]
        response_text = format_su_location_by_site(location_str, site)

    # שליפת טיקטים לרובוט
    elif command == "/robot_ticket":
        input_parts = user_input.split()
        if len(input_parts) == 0:
            return jsonify({"response_type": "ephemeral", "text": "שגיאה: נא להזין מספר רובוט."})
        
        robot_number = input_parts[0].strip()
        search_range = input_parts[1].strip() if len(input_parts) > 1 and input_parts[1] in ["1m", "2m"] else "2_weeks"

        tickets = get_tickets(robot_number, search_range)

        if isinstance(tickets, str):
            return jsonify({"response_type": "ephemeral", "text": tickets})

        response_text = format_ticket_response(tickets, robot_number)

    else:
        response_text = "שגיאה בפורמט ההזנה."

    return app.response_class(
        response=json.dumps({"response_type": "ephemeral", "text": response_text}, ensure_ascii=False),
        status=200,
        mimetype="application/json"
    )

if __name__ == "__main__":
    app.run(port=3000)
