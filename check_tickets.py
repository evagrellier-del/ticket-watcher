# check_tickets.py
import os, requests

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")
EVENT_KEYWORD = os.getenv("EVENT_KEYWORD", "Lady Gaga")
VENUE = os.getenv("VENUE", "Accor Arena")
EVENT_DATE = os.getenv("EVENT_DATE", "2025-11-22")
MAX_PRICE_EUR = float(os.getenv("MAX_PRICE_EUR", "100"))

def send_telegram(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram non configuré.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    r = requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    print("Telegram status:", r.status_code)

def check_ticketmaster():
    if not TICKETMASTER_API_KEY:
        print("Pas de clé Ticketmaster fournie, mode limité.")
        return []
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": TICKETMASTER_API_KEY,
        "keyword": EVENT_KEYWORD,
        "venueName": VENUE,
        "locale": "*"
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("Erreur TM:", e)
        return []

    events = []
    if "_embedded" in data and "events" in data["_embedded"]:
        for ev in data["_embedded"]["events"]:
            datestr = ev.get("dates", {}).get("start", {}).get("localDate", "")
            if datestr == EVENT_DATE:
                priceRanges = ev.get("priceRanges", [])
                min_price = priceRanges[0].get("min") if priceRanges else None
                events.append({
                    "name": ev.get("name"),
                    "url": ev.get("url"),
                    "min_price": min_price
                })
    return events

def main():
    alerts = []
    for e in check_ticketmaster():
        if e["min_price"] is not None and float(e["min_price"]) <= MAX_PRICE_EUR:
            alerts.append(f"Offre TM ≤ {MAX_PRICE_EUR}€ : {e['name']} - {e['url']}")
    if alerts:
        send_telegram("ALERTE BILLETS:\n" + "\n\n".join(alerts))
        print("Alert sent.")
    else:
        print("Aucune alerte.")

if __name__ == "__main__":
    main()
