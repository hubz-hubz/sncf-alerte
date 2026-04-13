import asyncio
import os
import sys
from playwright.async_api import async_playwright
from twilio.rest import Client

TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM")
MY_WHATSAPP_NUMBER = os.environ.get("MY_WHATSAPP_NUMBER")

TARGET_ORIGIN = "PARIS MONTPARNASSE"
TARGET_DESTINATION = "ARCACHON"
TARGET_DATE = "30/04/2026"
TARGET_DEPARTURE = "18:38"
WHATSAPP_MESSAGE = (
    "🚆 Place dispo ! PARIS → ARCACHON 30/04 18h38 - "
    "Réserve vite : https://www.sncf-connect.com"
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
    print(f"[INFO] Démarrage de la vérification pour {TARGET_ORIGIN} → {TARGET_DESTINATION} le {TARGET_DATE} à {TARGET_DEPARTURE}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        print("[INFO] Ouverture de sncf-connect.com...")
        await page.goto("https://www.sncf-connect.com", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        # Fermer le bandeau cookies si présent
        try:
            cookie_button = page.locator("button[id*='accept'], button[aria-label*='accepter'], button[aria-label*='Accepter']").first
            if await cookie_button.is_visible(timeout=5000):
                await cookie_button.click()
                print("[INFO] Bandeau cookies fermé.")
                await page.wait_for_timeout(1000)
        except Exception:
            print("[INFO] Pas de bandeau cookies détecté.")

        # Champ origine
        print(f"[INFO] Saisie de l'origine : {TARGET_ORIGIN}")
        try:
            origin_input = page.locator("input[placeholder*='Départ'], input[aria-label*='Départ'], input[id*='origin']").first
            await origin_input.click(timeout=10000)
            await origin_input.fill(TARGET_ORIGIN)
            await page.wait_for_timeout(2000)
            suggestion = page.locator(f"text={TARGET_ORIGIN}").first
            await suggestion.click(timeout=8000)
            print(f"[INFO] Origine sélectionnée : {TARGET_ORIGIN}")
        except Exception as e:
            print(f"[ERREUR] Impossible de saisir l'origine : {e}")
            await browser.close()
            return

        # Champ destination
        print(f"[INFO] Saisie de la destination : {TARGET_DESTINATION}")
        try:
            dest_input = page.locator("input[placeholder*='Arrivée'], input[aria-label*='Arrivée'], input[id*='destination']").first
            await dest_input.click(timeout=10000)
            await dest_input.fill(TARGET_DESTINATION)
            await page.wait_for_timeout(2000)
            suggestion = page.locator(f"text={TARGET_DESTINATION}").first
            await suggestion.click(timeout=8000)
            print(f"[INFO] Destination sélectionnée : {TARGET_DESTINATION}")
        except Exception as e:
            print(f"[ERREUR] Impossible de saisir la destination : {e}")
            await browser.close()
            return

        # Sélection de la date
        print(f"[INFO] Saisie de la date : {TARGET_DATE}")
        try:
            date_input = page.locator("input[type='date'], input[aria-label*='date'], button[aria-label*='date']").first
            await date_input.click(timeout=10000)
            await page.wait_for_timeout(1000)
            await page.keyboard.type(TARGET_DATE)
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"[ERREUR] Impossible de saisir la date : {e}")
            await browser.close()
            return

        # Lancement de la recherche
        print("[INFO] Lancement de la recherche...")
        try:
            search_button = page.locator("button[type='submit'], button[aria-label*='Rechercher'], button[aria-label*='rechercher']").first
            await search_button.click(timeout=10000)
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"[ERREUR] Impossible de lancer la recherche : {e}")
            await browser.close()
            return

        print(f"[INFO] URL de résultats : {page.url}")

        # Récupération du contenu de la page
        content = await page.content()

        # Recherche du train cible (18:38)
        print(f"[INFO] Recherche du train {TARGET_DEPARTURE}...")
        if TARGET_DEPARTURE not in content:
            print(f"[INFO] Le train {TARGET_DEPARTURE} n'est pas visible sur la page. Il est peut-être sur une autre date ou absent.")
            await browser.close()
            return

        # Détection de la disponibilité autour du train 18:38
        # On cherche les blocs qui contiennent 18:38 et qui ne sont pas "Complet" / "Indisponible"
        train_cards = page.locator(f"[class*='train'], [class*='journey'], [class*='proposal'], article").all()
        found = False
        available = False

        try:
            cards = await train_cards
            for card in cards:
                card_text = await card.inner_text()
                if TARGET_DEPARTURE in card_text:
                    found = True
                    print(f"[INFO] Train {TARGET_DEPARTURE} trouvé. Contenu : {card_text[:200]}")
                    unavailable_keywords = ["Complet", "Indisponible", "Non disponible", "Épuisé"]
                    if any(kw.lower() in card_text.lower() for kw in unavailable_keywords):
                        print(f"[INFO] Train {TARGET_DEPARTURE} : COMPLET ou INDISPONIBLE.")
                    else:
                        available = True
                        print(f"[INFO] Train {TARGET_DEPARTURE} : PLACES DISPONIBLES !")
                    break
        except Exception:
            pass

        if not found:
            # Fallback : analyse du texte brut autour de 18:38
            idx = content.find(TARGET_DEPARTURE)
            if idx != -1:
                snippet = content[max(0, idx - 200):idx + 500]
                found = True
                unavailable_keywords = ["Complet", "Indisponible", "Non disponible", "Épuisé"]
                if any(kw.lower() in snippet.lower() for kw in unavailable_keywords):
                    print(f"[INFO] Train {TARGET_DEPARTURE} : COMPLET ou INDISPONIBLE (fallback texte).")
                else:
                    available = True
                    print(f"[INFO] Train {TARGET_DEPARTURE} : PLACES DISPONIBLES (fallback texte) !")

        await browser.close()

        if available:
            send_whatsapp_alert()
        else:
            print("[INFO] Aucune place disponible pour ce train. Pas d'alerte envoyée.")


def check_env():
    missing = []
    for var in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM", "MY_WHATSAPP_NUMBER"]:
        if not os.environ.get(var):
            missing.append(var)
    if missing:
        print(f"[ERREUR] Variables d'environnement manquantes : {', '.join(missing)}")
        sys.exit(1)


if __name__ == "__main__":
    check_env()
    asyncio.run(check_availability())
