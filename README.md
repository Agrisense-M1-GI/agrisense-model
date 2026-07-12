# Service IA - Analyse Agricole (POC local)

Service FastAPI qui orchestre deux modèles IA locaux via Ollama :
- **moondream** pour la vision (description d'image)
- **llama3.2:1b** pour le formatage structuré et la discussion

## ⚠️ Notes sur ta machine (i3-1005G1, 8 Go RAM, pas de GPU)

- Utilise bien **llama3.2:1b**, pas la version 3b (trop lourde pour cette machine).
- Le traitement des images est **séquentiel** (un seul worker), volontairement, pour éviter
  de saturer la RAM en chargeant deux modèles en parallèle.
- Attends-toi à plusieurs dizaines de secondes par image en analyse complète (moondream + llama).
- Configure Ollama pour ne garder qu'un modèle en mémoire à la fois :
  ```
  set OLLAMA_MAX_LOADED_MODELS=1
  set OLLAMA_NUM_PARALLEL=1
  ```

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

**Déclencher manuellement un cycle de métriques** (sans attendre l'intervalle auto) :
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
   moondream (description) -> llama3.2:1b (formatage JSON) -> callback backend
   |
   v
 Suppression fichier + entrée DB (historique texte conservé pour le chat)


POST /metrics/trigger (déclenchement manuel) :
   GET /api/metrics (endpoint du BACKEND, qui centralise déjà les capteurs sol)
     -> stockage SQLite -> llama3.2:1b (analyse) -> callback backend (résultat) -> réponse HTTP


[POST /chat] -> contexte (dernières métriques + dernières analyses d'images) -> llama3.2:1b -> réponse
```

## Tester avec Postman (procédure complète)

### Étape 0 — Lancer les deux services

Ouvre **2 terminaux** :

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

⚠️ Sur ta machine, l'analyse complète (moondream + llama) peut prendre 30s à 2 min. Patiente
avant de vérifier le statut/historique.

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

## Limitations connues (assumées pour un POC)

- Traitement des images 100% séquentiel : plusieurs images en attente = latence cumulée.
- SQLite (pas adapté à une forte charge concurrente, mais très bien pour une démo locale).
- Pas d'authentification sur les endpoints (à ajouter avant tout déploiement réel).
- Le worker et le scheduler tournent dans le même processus que l'API ; un crash du process
  arrête tout (acceptable en POC, à revoir en prod avec un vrai gestionnaire de process).
