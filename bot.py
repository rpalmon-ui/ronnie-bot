import os
from datetime import datetime
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client as TwilioClient
import anthropic
from supabase import create_client
from apscheduler.schedulers.background import BackgroundScheduler
import pytz

app = Flask(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_NUMBER = "whatsapp:+14155238886"
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
YOAV_NUMBER = os.getenv("YOAV_NUMBER")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

RONNIE_CONTEXT = """You are Ronnie - a fitness bot modeled after Ronnie Coleman, the 8-time Mr. Olympia champion.
You speak Hebrew to Yoel, but with Ronnie Coleman's legendary enthusiasm and catchphrases.
Mix in English phrases like "Yeah buddy!", "Lightweight baby!", "Ain't nothing but a peanut!"

Yoav's profile:
- Age: 17.5, Height: 180cm, Weight: 84kg
- Goal: Cut (חיטוב) - lose fat while maintaining muscle
- Training: Sunday-Thursday, 1 hour, split program, gym + outdoors
- Calories: 1800-2000/day, Protein: 170g/day
- Doesn't eat: bread, overly oily food
- Meals: 3/day, first at 10:00, last at 21-22:00
- Takes creatine (his mom isn't thrilled about it 😄)

Your job:
1. Motivate Yoel in Ronnie Coleman style
2. Every evening at 22:00 ask what he ate today and give nutrition feedback
3. Based on what he ate, suggest what to eat tomorrow
4. Track his progress over time
5. Give workout tips and encouragement
6. Be tough but supportive - no excuses accepted!

For cutting: aim for slight caloric deficit (1800 cal), high protein (170g+), low carbs except around workout."""

conversation_history = []

def send_whatsapp(to: str, message: str):
    twilio_client.messages.create(
        from_=TWILIO_WHATSAPP_NUMBER,
        to=f"whatsapp:{to}",
        body=message
    )

def workout_reminder():
    send_whatsapp(YOAV_NUMBER, 
        "Yeah buddy! 💪 שעה 15:00 — זמן לאימון! Lightweight baby! אין תירוצים, יואל. LETS GO! 🔥")

def evening_checkin():
    send_whatsapp(YOAV_NUMBER,
        "Ain't nothing but a peanut! 🥜 יואל, ספר לי מה אכלת היום. כל ארוחה, כל חטיף, הכל. הגוף שלך דורש דיווח! 💪")

@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get("Body", "").strip()
    sender = request.values.get("From", "").replace("whatsapp:", "")
    
    conversation_history.append({"role": "user", "content": incoming_msg})
    if len(conversation_history) > 20:
        conversation_history.pop(0)
    
    try:
        recent = supabase.table("ronnie_logs").select("*").order("created_at", desc=True).limit(14).execute()
        import json
        logs_context = json.dumps(recent.data if recent.data else [], ensure_ascii=False)
    except:
        logs_context = "[]"
    
    system = RONNIE_CONTEXT + f"\n\nYoav's recent logs:\n{logs_context}"
    
    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        system=system,
        messages=conversation_history
    )
    
    reply = response.content[0].text
    conversation_history.append({"role": "assistant", "content": reply})
    
    try:
        supabase.table("ronnie_logs").insert({
            "message": incoming_msg,
            "reply": reply,
            "created_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"Error saving: {e}")
    
    resp = MessagingResponse()
    resp.message(reply)
    return str(resp)

if __name__ == "__main__":
    israel_tz = pytz.timezone("Asia/Jerusalem")
    scheduler = BackgroundScheduler(timezone=israel_tz)
    scheduler.add_job(workout_reminder, "cron", day_of_week="0,1,2,3,4", hour=15, minute=0)
    scheduler.add_job(evening_checkin, "cron", day_of_week="0,1,2,3,4", hour=22, minute=0)
    scheduler.start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
