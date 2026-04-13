import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM")
MY_WHATSAPP_NUMBER = os.environ.get("MY_WHATSAPP_NUMBER")

TARGET_ORIGIN = "Paris Montparnasse"
TARGET_DESTINATION = "Arcachon"
TARGET_DATE = "2026-04-30"
TARGET_DEPARTURE = "18:38"
WHATSAPP_MESSAGE = (
    "🚆 Place dispo ! PARIS → ARCACHON 30/04 18h38 - "
    "Réserve vite : https://www.sncf-connect.com"
)

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# URL directe vers les résultats de recherche SNCF Connect
# FRPMO = Paris Montparnasse, FRARC = Arcachon
SEARCH_URL = (
    "https://www.sncf-connect.com/app/trips/search"
    "?originCode=FRPMO"
    "&destinationCode=FRARC"
    "&outwardDate=2026-04-30T18%3A00%3A00"
    "&passengers=%5B%7B%22age%22%3A%22ADULT%22%7D%5D"
    "&directTravel=false"
    "&selectedOptions=%7B%7D"
)


def send_whatsapp_alert():
    print("[ALERTE] Envoi du message WhatsApp via Twilio...")
    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    message = client.messages.create(
        body=WHATSAPP_MESSAGE,
        from_=f"whatsapp:{TWILIO_WHATSAPP_FROM}",
        to=f"whatsapp:{MY_WHATSAPP_NUMBER}",
    )
    print(f"[ALERTE] Message envoyé. SID : {message.sid}")


async def check_availability():
    print(f"[INFO] Démarrage de la vérification : {TARGET_ORIGIN} → {TARGET_DESTINATION} le {TARGET_DATE} à {TARGET_DEPARTURE}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="fr-FR",
        )
        page = await context.new_page()

        # --- Étape 1 : navigation directe vers les résultats ---
        print(f"[INFO] Navigation vers l'URL de recherche directe...")
        print(f"[INFO] URL : {SEARCH_URL}")
        await page.goto(SEARCH_URL, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(4000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "01_page_loaded.png"))
        print(f"[INFO] URL actuelle après chargement : {page.url}")

        # --- Fermer le bandeau cookies ---
        try:
            for selector in [
                "button#didomi-notice-agree-button",
                "button[id*='accept']",
                "button[aria-label*='accepter']",
                "button[aria-label*='Accepter']",
                "#axeptio_btn_acceptAll",
            ]:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=3000):
                    await btn.click()
                    print(f"[INFO] Bandeau cookies fermé via : {selector}")
                    await page.wait_for_timeout(2000)
                    break
        except Exception:
            print("[INFO] Pas de bandeau cookies détecté.")

        await page.wait_for_timeout(5000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "02_after_cookies.png"))

        # --- Attendre que la page de résultats se charge ---
        print("[INFO] Attente du chargement des résultats...")
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            print("[INFO] networkidle timeout — on continue quand même.")

        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(SCREENSHOTS_DIR / "03_results.png"))
        print(f"[INFO] URL finale : {page.url}")

        # --- Analyse du contenu ---
        content = await page.content()
        page_text = await page.evaluate("document.body.innerText")

        print(f"[INFO] Longueur du contenu HTML : {len(content)} caractères")
        print(f"[INFO] Aperçu du texte de la page :")
        print(page_text[:1000])
        print("...")

        # --- Recherche du train 18:38 ---
        print(f"\n[INFO] Recherche du train {TARGET_DEPARTURE} dans la page...")

        if TARGET_DEPARTURE not in page_text and TARGET_DEPARTURE not in content:
            print(f"[INFO] '{TARGET_DEPARTURE}' introuvable sur la page.")
            print("[INFO] Mots-clés présents (debug) :")
            for kw in ["Complet", "complet", "Indisponible", "dispo", "€", "TGV", "Intercités", "train"]:
                count = page_text.lower().count(kw.lower())
                if count:
                    print(f"  - '{kw}' : {count} fois")
            await browser.close()
            return

        # Chercher le bloc contenant 18:38 et analyser la disponibilité
        unavailable_keywords = ["complet", "indisponible", "non disponible", "épuisé", "sold out"]
        available = False

        # Analyse par blocs de texte autour de 18:38
        idx = page_text.find(TARGET_DEPARTURE)
        if idx != -1:
            snippet = page_text[max(0, idx - 300):idx + 600]
            print(f"[INFO] Contexte autour de {TARGET_DEPARTURE} :")
            print(snippet)
            print()

            if any(kw in snippet.lower() for kw in unavailable_keywords):
                print(f"[INFO] Train {TARGET_DEPARTURE} : COMPLET ou INDISPONIBLE.")
            else:
                available = True
                print(f"[INFO] Train {TARGET_DEPARTURE} : PLACES DISPONIBLES !")

        await browser.close()

        if available:
            send_whatsapp_alert()
        else:
            print("[INFO] Aucune place disponible. Pas d'alerte envoyée.")


def check_env():
    missing = [v for v in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "MY_WHATSAPP_NUMBER"] if not os.environ.get(v)]
    if missing:
        print(f"[ERREUR] Variables d'environnement manquantes : {', '.join(missing)}")
        sys.exit(1)


if __name__ == "__main__":
    check_env()
    asyncio.run(check_availability())
