# check_tickets.py
import os, re, json, requests, pathlib
from bs4 import BeautifulSoup

# --- Variables d'environnement (voir workflow) ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
TICKETMASTER_API_KEY = os.getenv("TICKETMASTER_API_KEY", "")

EVENT_KEYWORD = os.getenv("EVENT_KEYWORD", "Lady Gaga")
VENUE = os.getenv("VENUE", "Accor Arena")
EVENT_DATE = os.getenv("EVENT_DATE", "2025-11-22")

TM_EVENT_URL = os.getenv("TM_EVENT_URL", "")                 # Ticketmaster Fan-to-Fan
TICKETSWAP_EVENT_URL = os.getenv("TICKETSWAP_EVENT_URL", "") # Ticketswap
VIAGOGO_EVENT_URL = os.getenv("VIAGOGO_EVENT_URL", "")       # Viagogo

STATE_PATH = pathlib.Path(".state.json")
UA = {"User-Agent": "Mozilla/5.0 (TicketWatcher/1.1)"}

# --- Utils ---
def send_telegram(text: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram non configuré.")
        return
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=20,
        )
        print("Telegram status:", r.status_code)
    except Exception as e:
        print("Telegram error:", e)

_price_re = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s?(?:€|EUR)\b")

def extract_min_price_eur_from_text(text: str):
    prices = []
    for m in _price_re.finditer(text.replace("\xa0", " ")):
        try:
            prices.append(float(m.group(1).replace(",", ".")))
        except:
            pass
    return min(prices) if prices else None

def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except:
            return {}
    return {}

def save_state(state: dict):
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

# --- 1) Ticketmaster primaire (API) ---
def check_ticketmaster_primary():
    if not TICKETMASTER_API_KEY:
        print("Pas de clé Ticketmaster API : skip primaire.")
        return []
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {"apikey": TICKETMASTER_API_KEY, "keyword": EVENT_KEYWORD, "venueName": VENUE, "locale": "*"}
    try:
        r = requests.get(url, params=params, timeout=25)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("Erreur Ticketmaster API:", e)
        return []

    out = []
    emb = data.get("_embedded", {})
    for ev in emb.get("events", []):
        date = ev.get("dates", {}).get("start", {}).get("localDate")
        if date == EVENT_DATE:
            priceRanges = ev.get("priceRanges", [])
            min_price = priceRanges[0].get("min") if priceRanges else None
            out.append(("Ticketmaster (primaire)", ev.get("url"), min_price))
    return out

# --- 2) Ticketmaster Fan-to-Fan (page publique) ---
def check_ticketmaster_resale():
    if not TM_EVENT_URL:
        return []
    try:
        r = requests.get(TM_EVENT_URL, headers=UA, timeout=25)
        if r.status_code != 200:
            print("TM resale HTTP:", r.status_code)
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        min_price = extract_min_price_eur_from_text(soup.get_text(" ", strip=True))
        return [("Ticketmaster (Fan-to-Fan)", TM_EVENT_URL, min_price)] if min_price is not None else []
    except Exception as e:
        print("TM resale error:", e)
        return []

# --- 3) Ticketswap ---
def check_ticketswap():
    if not TICKETSWAP_EVENT_URL:
        return []
    try:
        r = requests.get(TICKETSWAP_EVENT_URL, headers=UA, timeout=25)
        if r.status_code != 200:
            print("Ticketswap HTTP:", r.status_code)
            return []
        min_price = extract_min_price_eur_from_text(r.text)
        return [("Ticketswap", TICKETSWAP_EVENT_URL, min_price)] if min_price is not None else []
    except Exception as e:
        print("Ticketswap error:", e)
        return []

# --- 4) Viagogo ---
def check_viagogo():
    if not VIAGOGO_EVENT_URL:
        return []
    try:
        r = requests.get(VIAGOGO_EVENT_URL, headers=UA, timeout=25)
        if r.status_code != 200:
            print("Viagogo HTTP:", r.status_code)
            return []
        min_price = extract_min_price_eur_from_text(r.text)
        return [("Viagogo", VIAGOGO_EVENT_URL, min_price)] if min_price is not None else []
    except Exception as e:
        print("Viagogo error:", e)
        return []

def main():
    # Récupère toutes les infos
    findings = []
    findings += check_ticketmaster_primary()
    findings += check_ticketmaster_resale()
    findings += check_ticketswap()
    findings += check_viagogo()

    # État précédent (par source)
    state = load_state()  # ex: {"Ticketmaster (primaire)": 120.0, "Ticketswap": 95.0}
    improved = []         # sources dont le prix a baissé
    appeared = []         # nouvelles sources avec prix

    # Compare
    for (src, url, price) in findings:
        if price is None:
            continue
        prev = state.get(src)
        if prev is None:
            appeared.append((src, url, price))
            state[src] = price
        elif price < prev:
            improved.append((src, url, price, prev))
            state[src] = price

    # Sauvegarde l'état mis à jour (le workflow commit/push ensuite)
    save_state(state)

    # Envoi Telegram uniquement si baisse ou nouvelle source
    if improved or appeared:
        lines = []
        if appeared:
            lines.append("🆕 Nouvelles sources détectées :")
            for (src, url, p) in sorted(appeared, key=lambda x: x[2]):
                lines.append(f"- {src}: ~{p:.2f}€\n{url}")
        if improved:
            lines.append("\n⬇️ Baisse de prix :")
            for (src, url, p, prev) in sorted(improved, key=lambda x: x[2]):
                lines.append(f"- {src}: ~{prev:.2f}€ → ~{p:.2f}€\n{url}")
        send_telegram("🎟️ Mises à jour billets:\n\n" + "\n".join(lines))
        print("Alert sent.")
    else:
        print("Aucune nouveauté (pas de baisse ni nouvelle source).")

if __name__ == "__main__":
    main()