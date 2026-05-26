import os
from flask import Flask, request, jsonify
from ia_service import AgriSenseIAService  # On importe ton travail !

app = Flask(__name__)

# On initialise ton service avec ta clé API
# Idéalement, la clé est stockée dans les variables d'environnement de la machine
API_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyAq067XHQKTVTVFeMN2y3gPsHAwEMq1XKo")
service_ia = AgriSenseIAService(api_key=API_KEY)

# --- CRÉATION DE TON PREMIER ENDPOINT ---
@app.route('/api/ia/analyser', methods=['POST'])
def analyser_champ():
    """
    Cet endpoint reçoit les demandes du backend.
    Il attend le nom de la culture et va scanner le dossier pour analyser l'image.
    """
    try:
        # 1. On récupère les données envoyées par le Backend (au format JSON)
        donnees_recues = request.get_json()
        
        if not donnees_recues or 'culture' not in donnees_recues:
            return jsonify({
                "succes": False, 
                "error": "Données manquantes. Le champ 'culture' est obligatoire."
            }), 400
            
        culture = donnees_recues['culture']
        # Vous pouvez définir ensemble le chemin du dossier partagé
        dossier_images = donnees_recues.get('dossier_images', 'images_backend')

        print(f"[Endpoint] Requête reçue pour analyser du {culture} dans {dossier_images}")

        # 2. On appelle TA fonction de diagnostic que nous avons écrite
        resultat = service_ia.executer_analyse_vers_json(
            dossier_backend=dossier_images,
            culture_cible=culture
        )

        # 3. On renvoie le résultat JSON directement au Backend sur le réseau
        return jsonify(resultat), 200

    except Exception as e:
        return jsonify({"succes": False, "error": f"Erreur serveur endpoint : {str(e)}"}), 500


# --- UN DEUXIÈME ENDPOINT DE SÉCURITÉ (POUR VÉRIFIER SI LE SERVEUR TOURNE) ---
@app.route('/api/ia/statut', methods=['GET'])
def verifier_statut():
    return jsonify({
        "status": "online",
        "service": "AgriSense IA Engine",
        "model": "gemini-2.5-flash"
    }), 200


if __name__ == "__main__":
    # On lance le serveur sur le port 5000 de ta machine
    print("--- Serveur Web AgriSense IA démarré sur http://127.0.0.1:5000 ---")
    app.run(host="0.0.0.0", port=5000, debug=True)