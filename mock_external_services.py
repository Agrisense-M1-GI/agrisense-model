"""
Service MOCK pour simuler le BACKEND externe, qui :
  - reçoit les résultats d'analyse (images + métriques) que notre service lui envoie
  - expose lui-même un endpoint de métriques agrégées (déjà collectées auprès des capteurs sol)
    que notre service interroge automatiquement

À lancer en parallèle du service principal, sur un port différent (9000 par défaut).
Sert uniquement à tester le flux complet dans Postman sans backend réel.

Lancement : uvicorn mock_external_services:app --port 9000
"""
import random
from datetime import datetime, timedelta

from fastapi import FastAPI, Request

app = FastAPI(title="Mock backend + capteur sol")

received_image_results = []
received_metrics_results = []


@app.post("/api/image-analysis-result")
async def receive_image_result(request: Request):
    payload = await request.json()
    received_image_results.append(payload)
    print(f"[MOCK BACKEND] Résultat image reçu : {payload}")
    return {"received": True}


@app.post("/api/metrics-analysis-result")
async def receive_metrics_result(request: Request):
    payload = await request.json()
    received_metrics_results.append(payload)
    print(f"[MOCK BACKEND] Résultat métriques reçu : {payload}")
    return {"received": True}


@app.get("/api/image-analysis-result/history")
def get_image_results_history():
    """Endpoint pratique pour vérifier dans Postman ce que le service IA a envoyé."""
    return received_image_results


@app.get("/api/metrics-analysis-result/history")
def get_metrics_results_history():
    """Idem pour les résultats de métriques."""
    return received_metrics_results


@app.get("/api/metrics")
def get_backend_metrics(limit: int = 30):
    """Simule l'endpoint du BACKEND qui agrège déjà les métriques des capteurs sol
    (nous n'interrogeons jamais les capteurs directement, seulement le backend)."""
    now = datetime.utcnow()
    metrics = []
    for i in range(limit):
        metrics.append({
            "humidity": round(random.uniform(20, 80), 1),
            "air_temp": round(random.uniform(18, 35), 1),
            "soil_temp": round(random.uniform(15, 28), 1),
            "timestamp": (now - timedelta(minutes=i * 5)).isoformat(),
        })
    return metrics
