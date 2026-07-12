"""
Récupération des métriques du sol (humidité, température air/sol) depuis l'endpoint
exposé par le BACKEND (celui-ci centralise déjà les données des capteurs sol ; on ne parle
jamais directement aux capteurs).

Pour l'instant, la récupération est déclenchée MANUELLEMENT via POST /metrics/trigger
(voir main.py). L'automatisation (interrogation périodique en tâche de fond) pourra être
ajoutée plus tard si besoin — la fonction poll_once() ci-dessous est déjà écrite de façon
à pouvoir être branchée telle quelle sur un scheduler quand ce sera le moment.
"""
import logging

import requests

import database as db
from config import BACKEND_METRICS_SOURCE_URL, METRICS_MAX_FETCH, BACKEND_METRICS_RESULT_URL
from ollama_client import analyze_metrics_with_llama

logger = logging.getLogger("metrics_service")


def _fetch_metrics_from_backend() -> list:
    resp = requests.get(BACKEND_METRICS_SOURCE_URL, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    # On s'attend à une liste de mesures ; on tronque à METRICS_MAX_FETCH par sécurité.
    if isinstance(data, dict) and "metrics" in data:
        data = data["metrics"]
    return data[:METRICS_MAX_FETCH]


def _send_result_to_backend(result: dict):
    try:
        requests.post(BACKEND_METRICS_RESULT_URL, json=result, timeout=15)
    except requests.RequestException as e:
        logger.error("Échec envoi résultat métriques au backend : %s", e)


def poll_once() -> dict:
    """Récupère les métriques auprès du backend, les stocke, les analyse, et envoie
    le résultat au backend. Retourne le résultat pour permettre à l'endpoint de le
    renvoyer directement dans la réponse HTTP (pratique pour tester dans Postman)."""
    metrics_list = _fetch_metrics_from_backend()

    if not metrics_list:
        logger.info("Aucune nouvelle métrique reçue du backend.")
        return {"message": "Aucune métrique reçue."}

    db.insert_metrics_batch(metrics_list)

    try:
        result = analyze_metrics_with_llama(metrics_list)
    except Exception as e:
        logger.exception("Erreur lors de l'analyse des métriques")
        result = {
            "etat": "alerte",
            "actions": f"[À vérifier manuellement] Échec technique de l'analyse automatique ({e}).",
            "priorite": "haute",
        }

    db.save_metrics_analysis(result)
    _send_result_to_backend(result)
    return result
