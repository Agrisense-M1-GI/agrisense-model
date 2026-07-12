"""
Service IA d'analyse agricole - point d'entrée FastAPI.

3 endpoints :
  1. POST /analyze-image   -> reçoit une image, répond immédiatement, traite en tâche de fond
  2. GET  /metrics/status   & POST /metrics/trigger -> supervision de la récupération auto des métriques
  3. POST /chat             -> discussion libre avec contexte (métriques + analyses d'images récentes)
"""
import logging
import os
import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

import database as db
from config import IMAGES_DIR, CHAT_CONTEXT_LAST_METRICS, CHAT_CONTEXT_LAST_IMAGE_ANALYSES
from image_worker import enqueue_image, start_worker
from metrics_service import poll_once
from ollama_client import chat_with_context

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")

app = FastAPI(title="Service IA - Analyse Agricole")


@app.on_event("startup")
def on_startup():
    db.init_db()
    start_worker()
    # Pas de scheduler automatique pour l'instant : la récupération des métriques se fait
    # manuellement via POST /metrics/trigger. À activer plus tard si besoin.
    logger.info("Service démarré.")


# ---------------------------------------------------------------------------
# 1. Endpoint analyse d'images
# ---------------------------------------------------------------------------

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@app.post("/analyze-image")
async def analyze_image(image: UploadFile = File(...), sensor_id: str = Form(...)):
    ext = os.path.splitext(image.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Extension non supportée : {ext}")

    filename = f"{uuid.uuid4()}{ext}"
    path = os.path.join(IMAGES_DIR, filename)
    with open(path, "wb") as f:
        f.write(await image.read())

    image_id = db.create_image_entry(sensor_id=sensor_id, path=path)
    enqueue_image(image_id)

    # Réponse immédiate : on coupe la communication ici, le traitement se fait en tâche de fond
    # et le résultat sera envoyé plus tard vers l'endpoint du backend (voir config.py).
    return {"image_id": image_id, "status": "non_traite", "message": "Image reçue, traitement en cours."}


@app.get("/analyze-image/{image_id}/status")
def get_image_status(image_id: str):
    """Utile en debug/démo pour suivre le statut avant que l'entrée ne soit supprimée."""
    row = db.get_image(image_id)
    if not row:
        return {"image_id": image_id, "status": "traite_ou_inconnu"}
    return {"image_id": image_id, "status": row["status"]}


# ---------------------------------------------------------------------------
# 2. Endpoint métriques (récupération automatique en tâche de fond ; ici, supervision)
# ---------------------------------------------------------------------------

@app.get("/metrics/recent")
def get_recent_metrics_endpoint(limit: int = 30):
    return db.get_recent_metrics(limit)


@app.post("/metrics/trigger")
def trigger_metrics_poll():
    """Déclenche manuellement un cycle de récupération/analyse des métriques auprès du
    backend. C'est actuellement le SEUL moyen de récupérer des métriques (pas d'automatisation
    pour l'instant)."""
    try:
        result = poll_once()
    except Exception as e:
        raise HTTPException(502, f"Échec de récupération des métriques auprès du backend : {e}")
    return {"message": "Cycle de récupération des métriques exécuté.", "result": result}


# ---------------------------------------------------------------------------
# 3. Endpoint chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    question: str


def _build_chat_context() -> str:
    metrics = db.get_recent_metrics(CHAT_CONTEXT_LAST_METRICS)
    analyses = db.get_recent_image_analyses(CHAT_CONTEXT_LAST_IMAGE_ANALYSES)

    lines = []
    if metrics:
        lines.append("Dernières métriques du sol :")
        for m in metrics:
            lines.append(
                f"- humidité={m['humidity']}, temp. air={m['air_temp']}, "
                f"temp. sol={m['soil_temp']} ({m['fetched_at']})"
            )
    if analyses:
        lines.append("\nDernières analyses d'images :")
        for a in analyses:
            lines.append(f"- capteur {a['sensor_id']} : {a['result_json']} ({a['created_at']})")

    return "\n".join(lines) if lines else "Aucune donnée récente disponible."


@app.post("/chat")
def chat(req: ChatRequest):
    try:
        context = _build_chat_context()
        answer = chat_with_context(req.question, context)
    except Exception as e:
        logger.exception("Erreur dans /chat")
        raise HTTPException(500, f"Erreur lors du traitement du chat : {type(e).__name__}: {e}")
    return {"answer": answer}


@app.get("/health")
def health():
    return {"status": "ok"}
