import requests
import os

# --- STRATÉGIE S.C.A.L.E 2.0 ---
# Modifiez vos prix ici (Prix Achat / Prix Sortie)
ACTIONS_FAVORITES = {
    "SNEP": {"achat": 495.0, "sortie": 610.0},
    "HPS": {"achat": 556.0, "sortie": 675.0},
    "IAM": {"achat": 109.0, "sortie": 130.0},
    "SONASID": {"achat": 835.0, "sortie": 960.0}
}

# Clés secrètes récupérées depuis GitHub Settings
TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def envoyer_alerte(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def analyser_marche():
    # Simulation des cours (Ces données seront réelles en 2026)
    cours_actuels = {"SNEP": 494.0, "HPS": 560.0, "IAM": 108.5, "SONASID": 840.0}
    
    rapport = "📊 *SCAN SCALE 2.0 - BOURSE CASA* 📊\n\n"
    trouve = False
    
    for action, seuils in ACTIONS_FAVORITES.items():
        prix = cours_actuels.get(action)
        if prix and prix <= seuils["achat"]:
            potentiel = ((seuils["sortie"] - prix) / prix) * 100
            rapport += f"✅ *ACHAT : {action}*\nPrix : {prix} MAD\nPotentiel : +{potentiel:.1f}%\n\n"
            trouve = True
            
    if trouve:
        envoyer_alerte(rapport)

if __name__ == "__main__":
    analyser_marche()
