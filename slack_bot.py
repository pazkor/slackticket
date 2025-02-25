import os
import json
import requests
from flask import Flask, request, jsonify
from datetime import datetime, timedelta

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
PRIORITY_API_KEY = os.getenv("PRIORITY_API_KEY")
PRIORITY_API_URL = os.getenv("PRIORITY_API_URL")

app = Flask(__name__)

# מילון לאיתור שם האתר לפי מספר
SITE_MAP = {
    "1": "עמק",
    "2": "באר שבע",
    "3": "חולון"
}

# זיכרון זמני לשמירת קלט המשתמש עד לבחירת אתר
USER_SELECTIONS = {}

# פונקציה להחזרת מספר העמודות האחרון לכל אתר
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

# פונקציה לפענוח המיקום והחזרת תיאור בעברית
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
                f"הטוט נמצא במעבר {aisle}, בצד {side_desc} (מקדמת המעבר), "
                f"בעמודה {column}, בקומה {floor}, בתא מספר {cell}.\n"
                f"אם אתה נכנס מהחלק האחורי, עליך לספור {columns_from_back} עמודות קדימה. ✅\n\n"
                f"📌 **תזכורת: באתר, המספרים מתחילים מ-0.**")
    except Exception:
        return f"שגיאה בפענוח המיקום: {location_str}"

# פונקציה לשליפת טיקטים ממערכת Priority
def get_priority_tickets(robot_number, search_range="2_weeks"):
    date_ranges = {
        "2_weeks": 14,
        "1m": 30,
        "2m": 60
    }
    days_back = date_ranges.get(search_range, 14)
    search_date = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")

    url = f"{PRIORITY_API_URL}/tickets?robot={robot_number}&created_since={search_date}"
    headers = {"Authorization": f"Bearer {PRIORITY_API_KEY}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        return f"API Error: {response.text}"

    return response.json()

# פונקציה לפורמט התוצאה
def format_ticket_response(tickets, robot_number):
    formatted_tickets = []

    for ticket in tickets:
        ticket_id = ticket["ticket_id"]
        ticket_subject = ticket["subject"]
        created_at = datetime.strptime(ticket["created_at"], "%Y-%m-%dT%H:%M:%SZ").strftime("%d/%m/%Y")
        ticket_link = ticket["url"]

        formatted_tickets.append(f"*Ticket:* <{ticket_link}|#{ticket_id}>\n"
                                 f"*Subject:* {ticket_subject}\n"
                                 f"*Date:* {created_at}\n"
                                 "------------------------------------")

    return "\n".join(formatted_tickets) if formatted_tickets else f"No tickets found for robot {robot_number}."

# פונקציה שקולטת פקודות מסלאק
@app.route("/slack", methods=["POST"])
def slack_command():
    data = request.form
    user_id = data.get("user_id")  
    command = data.get("command")  
    user_input = data.get("text").strip()

    if not user_input:
        return jsonify({"response_type": "ephemeral", "text": "אנא הזן קלט מתאים."})

    # אם המשתמש בחר אתר אחרי שהזין קוד SU
    if user_id in USER_SELECTIONS and user_input in SITE_MAP:
        location_str = USER_SELECTIONS.pop(user_id)  
        site = SITE_MAP[user_input]
        response_text = format_su_location_by_site(location_str, site)

    # אם המשתמש הזין קוד מיקום - נבקש ממנו לבחור אתר
    elif command == "/SU":
        USER_SELECTIONS[user_id] = user_input  
        response_text = (
            "📍 אנא בחר את האתר על ידי שליחת מספר מתאים:\n"
            "1️⃣ עמק\n"
            "2️⃣ באר שבע\n"
            "3️⃣ חולון\n\n"
            "לדוגמה, הקלד '1' כדי לבחור את עמק."
        )

    # פקודת שליפת טיקטים
    elif command == "/ticket_finder":
        input_parts = user_input.split()
        robot_number = input_parts[0].strip()
        search_range = input_parts[1].strip() if len(input_parts) > 1 and input_parts[1] in ["1m", "2m"] else "2_weeks"

        tickets = get_priority_tickets(robot_number, search_range)

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
