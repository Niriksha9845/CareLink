# 🩺 CareLink - Automated Healthcare Medication Scheduler

CareLink is a full-stack automated patient reminder system built with Flask, Twilio WhatsApp API, and SQLite. It automates daily medication alerts in local languages (Kannada & English) and handles automated escalation alerts to caregivers.

## ✨ Features
- **Automated Cron Scheduling**: Background scheduler (APScheduler) dispatches personalized WhatsApp reminders at custom times.
- **Multilingual Support**: Supports automated responses and confirmation messages in Kannada and English.
- **Real-Time Escalation**: Instantly alerts caregivers/admins via WhatsApp if a patient explicitly misses a dosage ("NO" / "ಇಲ್ಲ").
- **Dynamic Control Panel**: Full-featured web dashboard to configure schedules, manage patient details, and view real-time WhatsApp response logs.

## 🛠️ Tech Stack
- **Backend**: Python, Flask, APScheduler
- **Database**: SQLite
- **API Integration**: Twilio WhatsApp API
- **Frontend**: HTML5, CSS3, JavaScript (Fetch API)

## 🚀 Quick Setup
1. Clone the repository:
   ```bash
   git clone [https://github.com/Niriksha9845/CareLink.git](https://github.com/Niriksha9845/CareLink.git)
   cd CareLink
