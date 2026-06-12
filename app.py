import os
from flask import Flask, request, jsonify
from ia_service import AgriSenseIAService

app = Flask(__name__)

# Initialisation du service (Recherche automatique de la clé d'environnement ou repli local)
API_KEY = os.environ.get("GEMINI_API_KEY", "TA_CLEF_ICI")
service_ia = AgriSenseIAService(api_key=API_KEY)


# =========================================================================
# ENDPOINT 1 : STATUT / HEALTHCHECK
# =========================================================================
@app.route('/api/ia/statut', methods=['GET'])
def verifier_statut():
    return jsonify({
        "status": "online",
        "service": "AgriSense IA Engine",
        "model": "gemini-2.5-flash"
    }), 200


# =========================================================================
# ENDPOINT 2 : DIAGNOSTIC PHYTOSANITAIRE (Feuilles / Maladies)
# =========================================================================
@app.route('/api/ia/analyser', methods=['POST'])
def analyser_champ():
    try:
        donnees_recues = request.get_json()
        
        if not donnees_recues or 'culture' not in donnees_recues:
            return jsonify({
                "succes": False, 
                "error": "Données malformées. Le champ 'culture' est obligatoire."
            }), 400
            
        culture = donnees_recues['culture']
        dossier_images = donnees_recues.get('dossier_images', 'images_backend')

        # Appel de la brique de diagnostic
        resultat = service_ia.executer_analyse_vers_json(
            dossier_backend=dossier_images,
            culture_cible=culture
        )
        return jsonify(resultat), 200

    except Exception as e:
        return jsonify({"succes": False, "error": f"Erreur serveur endpoint diagnostic : {str(e)}"}), 500


# =========================================================================
# ENDPOINT 3 : PRÉDICTION ET CONSEIL DE CULTURE (Sol nu / Métriques JSON)
# =========================================================================
@app.route('/api/ia/predire', methods=['POST'])
def predire_culture():
    """
    Endpoint appelé avant de planter. Reçoit les métriques environnementales 
    et calcule l'indice d'adéquation pour l'ananas, la mangue, la tomate, etc.
    """
    try:
        donnees_recues = request.get_json()
        
        if not donnees_recues or 'metriques' not in donnees_recues:
            return jsonify({
                "succes": False,
                "error": "Données de capteurs manquantes. L'objet 'metriques' est obligatoire."
            }), 400
            
        metriques = donnees_recues['metriques']
        # Chemin optionnel si le backend transmet une photo du sol nu
        dossier_images = donnees_recues.get('dossier_images', None)

        print(f"[Endpoint] Demande de prédiction agronomique reçue. Mode dossier : {dossier_images}")

        # Appel de la brique prédictive
        resultat_prediction = service_ia.executer_prediction_culture(
            dossier_backend=dossier_images,
            metriques_sol=metriques
        )
        
        return jsonify(resultat_prediction), 200

    except Exception as e:
        return jsonify({"succes": False, "error": f"Erreur serveur endpoint prédiction : {str(e)}"}), 500


if __name__ == "__main__":
    print("--- Serveur Web AgriSense IA connecté et actif [Port 5000] ---")
    app.run(host="0.0.0.0", port=5000, debug=True)