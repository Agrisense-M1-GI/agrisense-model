# AgriSense - IA Model Service 🌿🤖

Ce dépôt contient le sous-module d'Intelligence Artificielle du projet **AgriSense** (Master 1 GI). Il s'agit d'un microservice autonome développé en Python (Flask) qui fournit deux fonctionnalités d'ingénierie agronomique majeures au Backend principal (Laravel) :
1. **Un module de diagnostic phytosanitaire** (analyse de maladies sur plantes en croissance).
2. **Un module prédictif d'aide à la décision** (recommandation des cultures optimales avant plantation).

## 🚀 Fonctionnalités Clés

* **Microservice REST API :** Expose des points d'accès (endpoints) réseau standardisés pour une intégration fluide avec l'écosystème du projet.
* **Double Moteur Prédictif & Diagnostique :** Exploite l'API Google GenAI (`gemini-2.5-flash`) pour croiser des flux visuels (feuilles, texture du sol nu) et des données textuelles/numériques.
* **Analyse Hybride ou Métriques Pures :** Le module de prédiction s'adapte à l'infrastructure terrain. S'il reçoit une photo du sol, il effectue une analyse combinée (Visuel + Capteurs). Si l'appareil photo est absent, il bascule dynamiquement sur un traitement purement agronomique des données chiffrées (pH, humidité, température).
* **Filtre de Pixels Local (Économie de Jetons) :** Un algorithme léger basé sur `Pillow` évalue mathématiquement les variations d'images. Si la plante est saine et que les pixels n'ont pas bougé, la requête API vers Google est court-circuitée. **Bilan : 0 token dépensé.**
* **Sécurité Anticrise (Suivi d'état) :** Maintient une mémoire locale de l'état sanitaire (`Moyen` ou `Critique`). Si la plante présente des signes de faiblesse ou de maladie, le suivi par l'IA est forcé à chaque cycle pour analyser l'évolution du stress nutritionnel ou hydrique, même si l'image reste fixe.
* **Garantie de Format (Structured Outputs) :** Utilise des schémas JSON stricts appliqués à l'IA pour garantir des réponses directes, typées et sans fioritures textuelles pour le Backend.

---

## 📂 Architecture du Dossier

```text
agrisense-model/
│
├── app.py                     # Serveur Web Flask (Gestion et routage des Endpoints)
├── ia_service.py              # Cœur logique de l'IA (Filtres locaux, diagnostics et prédictions)
├── .gitignore                 # Exclusion des caches, environnements virtuels et fichiers d'état locaux
└── README.md                  # Documentation générale du projet

🛠️ Installation et Démarrage rapide
1. Installation des dépendances
Installez l'environnement d'exécution requis via pip :

Bash
pip install flask google-genai pillow
2. Variable d'environnement (Sécurité)
Configurez votre jeton d'accès sans jamais l'écrire en dur dans le code :

Windows (CMD) : set GEMINI_API_KEY="votre_clef_ici"

Linux/macOS : export GEMINI_API_KEY="votre_clef_ici"

3. Lancement du serveur
Bash
python app.py
Le service est actif et écoute sur l'adresse : http://127.0.0.1:5000