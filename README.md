# Service IA - Analyse Agricole (POC local)

Service FastAPI qui orchestre deux modèles IA locaux via Ollama :
- **moondream** pour la vision (description d'image)
- **llama3.2:1b** pour la classification, la traduction et la génération de recommandations

Voir aussi `API_DOCUMENTATION.md` pour le détail complet de chaque endpoint (requêtes,
réponses, codes d'erreur, exemples).

---

## Justification des choix technologiques

### Pourquoi FastAPI (et pas Flask/Django) ?

- **Support natif de l'upload de fichiers** (`multipart/form-data`) sans dépendance
  supplémentaire, nécessaire pour `/analyze-image`.
- **Validation automatique** des requêtes via Pydantic (les erreurs 422 avec détail précis
  qu'on a vues pendant les tests viennent de là — c'est un vrai gain de temps en debug).
- **Asynchrone par nature** : permet de répondre immédiatement sur `/analyze-image` pendant
  qu'un thread de fond continue le traitement, sans complexité additionnelle.
- Plus léger que Django (inutile ici : pas de vues, pas d'admin, pas d'ORM complexe requis),
  et la documentation interactive générée automatiquement (`/docs`) aide pour les tests manuels.

### Pourquoi Ollama + modèles locaux (et pas une API cloud comme OpenAI/Anthropic) ?

- **Contrainte de départ du projet** : le service doit fonctionner en local, sans dépendance
  à une connexion internet ni à un abonnement payant — pertinent pour un déploiement terrain
  agricole où la connectivité peut être limitée.
- Ollama offre une API HTTP simple (`/api/generate`) qui gère le chargement/déchargement des
  modèles, ce qui évite d'avoir à gérer soi-même l'inférence bas niveau (llama.cpp, tokenisation...).
- Inconvénient assumé et documenté tout au long du développement : les modèles locaux de
  petite taille (imposés par le matériel disponible) sont nettement moins fiables qu'une
  API cloud — voir la section "Pourquoi tant de mécanismes de sécurité" plus bas.

### Pourquoi moondream (et pas un modèle de vision plus gros comme llava:7b) ?

- Machine cible : Intel i3-1005G1 (4 threads, 1.2GHz), 8 Go RAM, pas de GPU dédié.
  moondream (~1.6B paramètres) est un des rares modèles de vision qui tient sur cette
  configuration avec un temps de réponse raisonnable (quelques secondes à ~1 minute).
- Un modèle plus gros (llava:7b ou supérieur) apporterait probablement une meilleure
  précision de description, mais serait probablement inutilisable en pratique sur cette
  machine (temps de réponse de plusieurs minutes, voire échec par manque de RAM).

### Pourquoi llama3.2:1b (et pas llama3.2:3b ou plus gros) ?

- Même contrainte matérielle que ci-dessus. Le 3b a été testé/envisagé au départ mais jugé
  trop lourd pour un temps de réponse acceptable sur cette machine.
- **Limite assumée** : au fil des tests, on a constaté que même des tâches simples (traduction,
  classification à 2 valeurs) restent parfois peu fiables avec un modèle de cette taille
  (hallucinations, incohérences d'un run à l'autre malgré une température à 0). C'est un
  compromis matériel/fiabilité assumé pour ce POC, pas un choix idéal dans l'absolu.

### Pourquoi SQLite (et pas PostgreSQL/MySQL) ?

- Pas de serveur de base de données à installer/gérer séparément — un simple fichier
  (`storage/agri_ai.db`), cohérent avec l'objectif "POC local, installation minimale".
- Le volume de données (quelques images en cours de traitement à la fois, un historique
  de métriques) est très en dessous de ce qui justifierait une base serveur.
- Limite assumée : SQLite gère mal les fortes charges concurrentes en écriture. Ce n'est
  pas un problème ici car le traitement est volontairement séquentiel (voir ci-dessous),
  mais ce choix serait à revoir en cas de déploiement avec plusieurs capteurs simultanés
  à haut débit.

### Pourquoi un worker séquentiel (une seule image traitée à la fois) et pas du parallélisme ?

- Décision directement liée à la contrainte RAM (8 Go, partagés avec l'OS et l'Intel UHD
  Graphics). Faire tourner moondream et llama en parallèle sur plusieurs images ferait
  swapper la mémoire et ralentirait tout au lieu d'accélérer le traitement global.
- La réception des images reste non-bloquante (queue interne) : plusieurs capteurs peuvent
  envoyer des images "en même temps", elles sont juste traitées les unes après les autres
  plutôt qu'en parallèle. C'est un compromis débit/stabilité adapté au matériel disponible.

### Pourquoi le pattern "réponse immédiate + callback" sur `/analyze-image` (et pas une
### réponse HTTP synchrone comme pour `/chat`) ?

- L'analyse complète (moondream + llama) peut prendre 30s à plusieurs minutes sur cette
  machine. Personne n'attend activement cette réponse (l'appelant est une caméra/capteur
  automatique côté backend), donc bloquer la connexion HTTP tout ce temps n'a pas de sens
  et risquerait des timeouts côté backend.
- `/chat`, à l'inverse, reste synchrone car un humain attend la réponse en direct dans une
  conversation — découpler la réponse n'aurait pas de sens pour cet usage.

### Pourquoi un filet de sécurité par mots-clés, une traduction séparée, et des
### recommandations générées par règles plutôt que par le modèle ?

C'est le résultat direct de plusieurs bugs rencontrés et corrigés pendant le développement,
tous liés à la même cause : **llama3.2:1b n'est pas fiable pour du raisonnement en texte
libre**, même avec des prompts soigneusement écrits. Constats faits en testant :
- Le modèle peut écrire une observation correcte ("nécrose apicale, lésions...") tout en
  mettant quand même `etat: normal` — incohérence logique interne.
- Il peut inventer des symptômes qui ne figurent pas du tout dans la description source
  (halluciner "pourriture" sur une image parfaitement saine).
- Il peut recommander une action sans rapport avec l'image ("retirer les fruits atteints"
  sur une plante saine).
- Même la traduction, tâche a priori plus simple, produit parfois des résultats incohérents
  sur des mots moins courants (ex : "pineapple" → "arbre à pomme").

La réponse à ces constats a été de **réduire la responsabilité du modèle au strict minimum**
à chaque étape, et de reporter le reste sur du code déterministe :
- **moondream** : uniquement une description libre de l'image, sans aucune instruction
  conditionnelle (les prompts avec conditions ("si tu vois X, dis Y") le faisaient échouer
  complètement — voir `analyze_image_with_moondream` dans `ollama_client.py`).
- **llama3.2:1b** : sert uniquement à classifier (`etat`/`priorite`, un choix contraint parmi
  quelques valeurs) et à traduire — jamais à rédiger une recommandation en texte libre.
- **Le filet de mots-clés** (`_contains_red_flag`, sensible aux négations) revérifie
  indépendamment le texte source, sans faire confiance à la cohérence du modèle.
- **Les recommandations** (`_generate_recommendation`) sont choisies dans une table de
  règles fixes basées sur les mots-clés détectés — jamais rédigées par le modèle.
- **Le dictionnaire de pré-substitution** (`_KNOWN_TERMS_EN_FR`) corrige les termes agricoles
  courants avant traduction, pour réduire le risque d'erreur sur les mots les plus importants.
- **Principe de prudence général** : en cas de doute (sortie invalide, signe de problème
  détecté malgré un `etat: normal` déclaré par le modèle), le système penche systématiquement
  vers `critique`/`haute` plutôt que `normal`/`basse` — un faux positif vérifié manuellement
  coûte moins cher qu'un vrai problème agricole passé inaperçu.

### Pourquoi un mock (`mock_external_services.py`) pour tester ?

- Le backend réel et les capteurs sol n'existent pas encore côté projet au moment du
  développement de ce service. Le mock permet de tester tout le flux (réception d'image,
  callback de résultat, récupération de métriques) sans dépendre d'un système externe pas
  encore prêt, et sans bloquer l'avancement du développement.

---

## ⚠️ Notes sur ta machine (i3-1005G1, 8 Go RAM, pas de GPU)

- Utilise bien **llama3.2:1b**, pas la version 3b (trop lourde pour cette machine).
- Le traitement des images est **séquentiel** (un seul worker), volontairement, pour éviter
  de saturer la RAM en chargeant deux modèles en parallèle.
- Attends-toi à plusieurs dizaines de secondes par image en analyse complète (moondream +
  plusieurs appels llama : classification, traduction).
- Configure Ollama pour ne garder qu'un modèle en mémoire à la fois :
  ```
  set OLLAMA_MAX_LOADED_MODELS=1
  set OLLAMA_NUM_PARALLEL=1
  ```
- **Ollama doit être lancé** avant de démarrer le service (`ollama serve`, ou l'app Ollama
  doit tourner en arrière-plan). Une erreur `ConnectionRefusedError` / `Failed to establish
  a new connection` sur le port 11434 dans les logs du service veut dire qu'Ollama n'est pas
  démarré ou plus accessible — ce n'est pas un bug du code Python.

## Installation

1. Installe [Ollama](https://ollama.com) puis récupère les modèles :
   ```
   ollama pull moondream
   ollama pull llama3.2:1b
   ```

2. Installe les dépendances Python (dans un venv de préférence) :
   ```
   pip install -r requirements.txt
   ```

3. Configure les URLs des endpoints externes (backend uniquement — on ne parle jamais
   directement aux capteurs, le backend centralise tout) via variables d'environnement,
   ou modifie directement `config.py` :
   ```
   set BACKEND_IMAGE_RESULT_URL=http://<ton-backend>/api/image-analysis-result
   set BACKEND_METRICS_RESULT_URL=http://<ton-backend>/api/metrics-analysis-result
   set BACKEND_METRICS_SOURCE_URL=http://<ton-backend>/api/metrics?limit=30
   ```

4. Lance le service :
   ```
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

## Tester les endpoints

**Analyse d'image** (réponse immédiate, traitement en tâche de fond) :
```
curl -X POST http://localhost:8000/analyze-image ^
  -F "image=@chemin/vers/photo.jpg" ^
  -F "sensor_id=camera-01"
```

**Statut d'une image** (debug avant suppression) :
```
curl http://localhost:8000/analyze-image/<image_id>/status
```

**Déclencher manuellement un cycle de métriques** (pas d'automatisation pour l'instant) :
```
curl -X POST http://localhost:8000/metrics/trigger
```

**Voir les métriques récentes stockées :**
```
curl http://localhost:8000/metrics/recent?limit=30
```

**Chat avec contexte :**
```
curl -X POST http://localhost:8000/chat ^
  -H "Content-Type: application/json" ^
  -d "{\"question\": \"Est-ce que le champ va bien en ce moment ?\"}"
```

Procédure complète pas à pas pour Postman (avec les champs à remplir) : voir plus bas dans
ce document, ou `API_DOCUMENTATION.md`.

## Architecture

```
Backend externe
   |
   |  POST image (multipart)
   v
[POST /analyze-image] --réponse immédiate--> Backend
   |
   v
 storage/images/ (fichier temporaire)
   |
   v
 Queue interne (thread-safe)
   |
   v
 Worker séquentiel (1 thread) :
   moondream (description libre, sans condition)
     -> llama3.2:1b (classification etat/priorite UNIQUEMENT)
     -> filet de mots-clés (vérifie la description source, corrige si besoin)
     -> traduction (llama3.2:1b, tâche simple, pré-substitution de termes connus)
     -> recommandation (règles fixes, PAS le modèle)
     -> callback backend (JSON : image_id, sensor_id, etat, actions, priorite)
   |
   v
 Suppression fichier + entrée DB (historique texte conservé pour le chat)


POST /metrics/trigger (déclenchement manuel) :
   GET /api/metrics (endpoint du BACKEND, qui centralise déjà les capteurs sol)
     -> stockage SQLite -> llama3.2:1b (analyse) -> callback backend (résultat) -> réponse HTTP


[POST /chat] -> contexte (dernières métriques + dernières analyses d'images) -> llama3.2:1b -> réponse
```

## Fichiers du projet

| Fichier | Rôle |
|---|---|
| `main.py` | Endpoints FastAPI |
| `config.py` | Configuration centralisée (URLs, chemins, paramètres) |
| `database.py` | Accès SQLite (images en cours, métriques, historique) |
| `ollama_client.py` | Tous les appels aux modèles IA (vision, classification, traduction, recommandations) |
| `image_worker.py` | Queue + worker séquentiel de traitement des images |
| `metrics_service.py` | Récupération/analyse des métriques (déclenchement manuel) |
| `mock_external_services.py` | Simule le backend + capteur sol, pour tester sans dépendances externes |
| `test_moondream.py` | Script de diagnostic : teste uniquement la vision, avec infos de debug détaillées |
| `test_llama_format.py` | Script de diagnostic : teste uniquement la classification/formatage |
| `API_DOCUMENTATION.md` | Documentation détaillée de chaque endpoint |

## Tester avec Postman (procédure complète)

### Étape 0 — Lancer les deux services

Ouvre **2 terminaux** (en plus d'avoir Ollama démarré séparément) :

**Terminal 1 — le service mock** (simule backend + capteur sol) :
```
uvicorn mock_external_services:app --port 9000 --reload
```

**Terminal 2 — le service IA principal** :
```
uvicorn main:app --port 8000 --reload
```

Par défaut, `config.py` pointe déjà vers `http://localhost:9000` pour le capteur sol et le
backend — pas besoin de changer quoi que ce soit pour tester en local.

---

### 1. Endpoint santé (sanity check)

- Méthode : `GET`
- URL : `http://localhost:8000/health`
- Body : aucun
- Réponse attendue : `{"status": "ok"}`

---

### 2. Endpoint analyse d'image

- Méthode : `POST`
- URL : `http://localhost:8000/analyze-image`
- Body → onglet **form-data** (pas raw/JSON) :
  | Key | Type | Value |
  |---|---|---|
  | `image` | File | choisis un fichier .jpg/.png sur ton disque |
  | `sensor_id` | Text | `camera-01` |
- Réponse immédiate attendue :
  ```json
  {"image_id": "xxxx-xxxx", "status": "non_traite", "message": "Image reçue, traitement en cours."}
  ```
  Copie la valeur de `image_id`, elle sert pour l'étape suivante.

**Vérifier le statut pendant le traitement :**
- Méthode : `GET`
- URL : `http://localhost:8000/analyze-image/{image_id}/status` (remplace `{image_id}`)
- Rejoue cette requête plusieurs fois : tu devrais voir `non_traite` → `en_cours` → puis
  `traite_ou_inconnu` (l'entrée est supprimée une fois traitée, comme prévu).

**Vérifier que le résultat est bien arrivé côté "backend" (le mock) :**
- Méthode : `GET`
- URL : `http://localhost:9000/api/image-analysis-result/history`
- Tu devrais voir apparaître un objet avec `image_id`, `sensor_id`, `etat`, `actions`, `priorite`.

⚠️ Sur ta machine, l'analyse complète (moondream + plusieurs appels llama) peut prendre 30s
à 2-3 min. Patiente avant de vérifier le statut/historique.

---

### 3. Endpoint métriques (récupération manuelle pour l'instant)

**Déclencher un cycle** — c'est actuellement le seul moyen de récupérer des métriques,
il n'y a pas encore d'automatisation périodique :
- Méthode : `POST`
- URL : `http://localhost:8000/metrics/trigger`
- Body : aucun
- Réponse : `{"message": "Cycle de récupération des métriques exécuté.", "result": {...}}`
  (le résultat de l'analyse est renvoyé directement, pratique pour tester)

**Vérifier les métriques stockées :**
- Méthode : `GET`
- URL : `http://localhost:8000/metrics/recent?limit=30`
- Tu devrais voir la liste des mesures (humidité, temp air/sol) récupérées du mock.

**Vérifier que le résultat d'analyse est arrivé côté "backend" :**
- Méthode : `GET`
- URL : `http://localhost:9000/api/metrics-analysis-result/history`

---

### 4. Endpoint chat

⚠️ Teste ceci **après** avoir déclenché au moins une analyse d'image et un cycle de métriques,
pour que l'IA ait du contexte à exploiter.

- Méthode : `POST`
- URL : `http://localhost:8000/chat`
- Body → onglet **raw**, type **JSON** :
  ```json
  {"question": "Comment se porte le champ en ce moment ?"}
  ```
- Réponse attendue :
  ```json
  {"answer": "..."}
  ```

---

### Astuce Postman : crée une Collection

Regroupe ces 6 requêtes dans une Collection Postman (`Nouveau > Collection`), avec une
variable `{{base_url}}` = `http://localhost:8000` et `{{mock_url}}` = `http://localhost:9000`.
Ça te permet de rejouer tout le scénario de démo en un clic sans retaper les URLs.

## Scripts de diagnostic

En cas de résultat inattendu sur une image, isole le problème étape par étape :

```
python test_moondream.py "chemin\vers\image.jpg"
```
Affiche la taille/dimensions du fichier, la réponse JSON complète d'Ollama, et la description
obtenue via le code réel du service — utile pour repérer une image trop lourde, un modèle non
chargé, ou une réponse dégénérée du modèle de vision.

```
python test_llama_format.py "une description à formater"
```
Teste uniquement l'étape de classification/formatage, indépendamment de la vision — utile
pour savoir si un résultat bizarre vient de moondream ou de llama.

## Limitations connues (assumées pour un POC)

- Traitement des images 100% séquentiel : plusieurs images en attente = latence cumulée.
- SQLite (pas adapté à une forte charge concurrente, mais très bien pour une démo locale).
- Pas d'authentification sur les endpoints (à ajouter avant tout déploiement réel).
- Le worker tourne dans le même processus que l'API ; un crash du process arrête tout
  (acceptable en POC, à revoir en prod avec un vrai gestionnaire de process).
- Pas de récupération automatique/périodique des métriques pour l'instant — uniquement
  via déclenchement manuel (`POST /metrics/trigger`), voir `metrics_service.py`.
- La fiabilité des résultats dépend fortement de la taille des modèles utilisés (imposée par
  le matériel). De nombreux mécanismes de robustesse (filet de mots-clés, recommandations par
  règles, dictionnaire de traduction) compensent cette limite mais ne l'éliminent pas
  totalement — un résultat généré automatiquement reste à vérifier pour un cas critique réel.