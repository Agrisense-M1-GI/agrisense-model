"""
Worker séquentiel de traitement des images.

IMPORTANT (contrainte machine) : on utilise UN SEUL thread worker qui dépile une queue,
et non un thread par image. Sur une machine à 4 threads / 8 Go RAM sans GPU, faire tourner
moondream et llama en parallèle sur plusieurs images ferait swapper la mémoire et ralentirait
tout. La réception peut être "parallèle" (plusieurs images arrivent en même temps et sont
stockées immédiatement), mais le traitement IA lui-même est sérialisé.
"""
import os
import queue
import threading
import logging

import requests

import database as db
from config import BACKEND_IMAGE_RESULT_URL
from ollama_client import analyze_image_with_moondream, format_image_analysis_with_llama

logger = logging.getLogger("image_worker")

_image_queue: "queue.Queue[str]" = queue.Queue()


def enqueue_image(image_id: str):
    _image_queue.put(image_id)


def _send_result_to_backend(image_id: str, sensor_id: str, result: dict):
    payload = {"image_id": image_id, "sensor_id": sensor_id, **result}
    try:
        requests.post(BACKEND_IMAGE_RESULT_URL, json=payload, timeout=15)
    except requests.RequestException as e:
        logger.error("Échec envoi résultat au backend pour image %s : %s", image_id, e)


def _process_one(image_id: str):
    image_row = db.get_image(image_id)
    if not image_row:
        logger.warning("Image %s introuvable (déjà traitée ou supprimée), on ignore.", image_id)
        return

    db.set_image_status(image_id, "en_cours")
    path = image_row["path"]
    sensor_id = image_row["sensor_id"]

    try:
        description = analyze_image_with_moondream(path)
        result = format_image_analysis_with_llama(description)
    except Exception as e:
        logger.exception("Erreur lors de l'analyse de l'image %s", image_id)
        result = {
            "etat": "alerte",
            "actions": f"[À vérifier manuellement] Échec technique de l'analyse automatique ({e}).",
            "priorite": "haute",
        }

    # Archive texte (pour le chat) + suppression de l'entrée de queue, comme demandé.
    db.finalize_image_processing(image_id, sensor_id, result)

    # Suppression du fichier image temporaire, une fois le traitement terminé.
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError as e:
        logger.warning("Impossible de supprimer le fichier image %s : %s", path, e)

    _send_result_to_backend(image_id, sensor_id, result)


def _worker_loop():
    while True:
        image_id = _image_queue.get()
        try:
            _process_one(image_id)
        finally:
            _image_queue.task_done()


def start_worker():
    thread = threading.Thread(target=_worker_loop, daemon=True, name="image-worker")
    thread.start()
    logger.info("Worker de traitement d'images démarré (mode séquentiel, 1 thread).")
