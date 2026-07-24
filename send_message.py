import os
import sqlite3
from datetime import datetime
from twilio.rest import Client
from dotenv import load_dotenv
from pytz import timezone
import sys 

# --- 1. CONFIGURATION AND DATA ---
# Set the project folder path dynamically for stable loading
project_dir = os.path.dirname(os.path.abspath(__file__))

# Load configuration from the .env file located in the project directory
load_dotenv(os.path.join(project_dir, '.env')) 
TW_SID = os.getenv("TWILIO_ACCOUNT_SID")
TW_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TW_WHATSAPP = os.getenv("TWILIO_WHATSAPP_NUMBER")

# Timezone setting for IST
TIMEZONE = timezone('Asia/Kolkata')

# Database path (Absolute path)
DB_FILE = os.path.join(project_dir, 'medi_ping.db') 

# --- 2. PERSONALIZED MEDICINE SCHEDULE (UPDATE YOUR NUMBERS HERE) ---
# IMPORTANT: Replace the placeholder phone numbers with your Mom's and Dad's actual numbers!
# You can update the medicine names later on PythonAnywhere.
FULL_MEDICINE_SCHEDULE = {
    # MOM'S NUMBER: (Replace with her actual number!)
    "+917019378817": {
        "name": "Amma",
        "language": "Kannada",
        "schedule": {
            "09:00": ["PLACEHOLDER A", "PLACEHOLDER B"], # Breakfast time (IST)
            "14:00": ["PLACEHOLDER C"],                   # Lunch time (IST)
            "20:00": ["PLACEHOLDER D", "PLACEHOLDER E"]   # Dinner time (IST)
        }
    },
    # DAD'S NUMBER: (Replace with his actual number!)
    "+919036741020": {
        "name": "Appa",
        "language": "English",
        "schedule": {
            "09:00": ["TABLET 1", "TABLET 2"], 
            "14:00": ["TABLET 3"],             
            "20:00": ["TABLET 4", "TABLET 5"]  
        }
    }
}

REMINDER_TAGS = {
    "09:00": "Breakfast",
    "14:00": "Lunch",
    "20:00": "Dinner"
}

# --- 3. CORE FUNCTIONS ---
client = Client(TW_SID, TW_TOKEN)

def send_whatsapp(phone, text):
    # Sends message via Twilio
    try:
        msg = client.messages.create(
            body=text,
            from_=TW_WHATSAPP,
            to=f"whatsapp:{phone}"
        )
        print(f"Successfully sent to {phone}. SID: {msg.sid}")
        return True
    except Exception as e:
        # NOTE: This will print the error to the task log on PythonAnywhere
        print(f"Twilio send error to {phone}: {e}")
        return False

def run_daily_reminders():
    # Get the current time in IST
    now = datetime.now(TIMEZONE)
    current_hour_str = now.strftime("%H") # Get the current hour (e.g., '14')
    current_time_str = now.strftime("%H:%M") # Get current time (e.g., '14:27')
    
    print(f"Scheduler check running at {now.isoformat()}...")

    # Logic to find the scheduled time based on the current hour (flexible check)
    scheduled_time = None
    for time_str in REMINDER_TAGS:
        if time_str.split(':')[0] == current_hour_str:
            scheduled_time = time_str
            break

    # If the current hour matches a scheduled hour (e.g., 14:xx matches 14:00)
    if scheduled_time:
        meal_tag = REMINDER_TAGS[scheduled_time]
        
        # NOTE: We are running the check every minute on PythonAnywhere, 
        # so this logic will fire on the minute the task is run (e.g., 14:00)
        
        # You can add logic here if you want to only send at 14:00 and not 14:01, etc.
        # But for now, we send if it's within the hour (14:xx)

        print(f"TRIGGER: Sending {meal_tag} reminders...")
        
        # Iterate through the schedule for all users
        for phone, user_data in FULL_MEDICINE_SCHEDULE.items():
            
            # Check if this user has a medicine scheduled for this specific time
            if scheduled_time in user_data["schedule"]:
                
                med_list = user_data["schedule"][scheduled_time]
                meds_str = ", ".join(med_list) 
                
                # --- Create Language-Specific Message ---
                if user_data["language"] == "Kannada":
                    message_body = (
                        f"ನಮಸ್ಕಾರ {user_data['name']}! ಇದು {meal_tag} ಜ್ಞಾಪನೆ. "
                        f"ದಯವಿಟ್ಟು ಈ ಔಷಧಿಗಳನ್ನು ತೆಗೆದುಕೊಳ್ಳಿ: {meds_str}. (ಹೌದು/ಇಲ್ಲ)"
                    )
                else:
                    message_body = (
                        f"Hello {user_data['name']}! This is your {meal_tag} reminder. "
                        f"Please take these medicines: {meds_str}. Reply YES when done."
                    )
                
                send_whatsapp(phone, message_body)

    else:
        print("No main reminder found for this time.")

    # NOTE: No BlockingScheduler or scheduler.start() here.
    # This script runs ONCE and exits, which is required by PythonAnywhere Scheduled Tasks.

# --- Execute the script when it runs on PythonAnywhere ---
if __name__ == "__main__":
    run_daily_reminders()
