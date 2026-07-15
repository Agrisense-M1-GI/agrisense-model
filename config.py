"""
Configuration centralisée du service.
Toutes les valeurs peuvent être surchargées via des variables d'environnement.
"""
import os

# --- Ollama ---
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
MOONDREAM_MODEL = os.getenv("MOONDREAM_MODEL", "moondream")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama3.2:1b")  # 1b recommandé sur machine modeste

# --- Backend externe (celui qui nous envoie les images / expose les endpoints de résultats) ---
BACKEND_IMAGE_RESULT_URL = os.getenv("BACKEND_IMAGE_RESULT_URL", "https://webhook.site/d4d169bb-9526-4d3c-bdf3-0aa655e233c9/api/ia/callback/image")
BACKEND_METRICS_RESULT_URL = os.getenv("BACKEND_METRICS_RESULT_URL", "https://webhook.site/d4d169bb-9526-4d3c-bdf3-0aa655e233c9/api/ia/callback/metriques")

# --- Backend externe : endpoint agrégeant les métriques des capteurs sol ---
# (on interroge le BACKEND, pas les capteurs directement — c'est lui qui centralise les données)
# Récupération déclenchée manuellement pour l'instant (voir POST /metrics/trigger)c
BACKEND_METRICS_SOURCE_URL = os.getenv("BACKEND_METRICS_SOURCE_URL", "https://webhook.site/d4d169bb-9526-4d3c-bdf3-0aa655e233c9/api/ia/metrics-source?limit=30")
METRICS_MAX_FETCH = int(os.getenv("METRICS_MAX_FETCH", "30"))

# --- Stockage ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STORAGE_DIR = os.path.join(BASE_DIR, "storage")
IMAGES_DIR = os.path.join(STORAGE_DIR, "images")
DB_PATH = os.path.join(STORAGE_DIR, "agri_ai.db")

# --- Contexte pour le chat ---
CHAT_CONTEXT_LAST_METRICS = int(os.getenv("CHAT_CONTEXT_LAST_METRICS", "10"))
CHAT_CONTEXT_LAST_IMAGE_ANALYSES = int(os.getenv("CHAT_CONTEXT_LAST_IMAGE_ANALYSES", "5"))

os.makedirs(IMAGES_DIR, exist_ok=True)
