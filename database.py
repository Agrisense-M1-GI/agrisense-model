"""
Accès SQLite. Une base légère suffit pour un POC (pas besoin de Postgres ici).
On utilise check_same_thread=False car plusieurs threads (API + worker + scheduler)
accèdent à la même connexion ; chaque fonction ouvre/ferme sa propre connexion
pour éviter les soucis de concurrence en écriture.
"""
import sqlite3
import json
import uuid
from datetime import datetime
from contextlib import contextmanager

from config import DB_PATH


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id TEXT PRIMARY KEY,
                sensor_id TEXT,
                path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'non_traite',
                result_json TEXT,
                created_at TEXT NOT NULL,
                processed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                humidity REAL,
                air_temp REAL,
                soil_temp REAL,
                raw_json TEXT,
                fetched_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        # Historique léger (texte uniquement, jamais l'image) conservé pour donner
        # du contexte au chat même après suppression de l'image et de son entrée.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS image_analysis_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)


# ---------- Images ----------

def create_image_entry(sensor_id: str, path: str) -> str:
    image_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO images (id, sensor_id, path, status, created_at) VALUES (?, ?, ?, 'non_traite', ?)",
            (image_id, sensor_id, path, datetime.utcnow().isoformat()),
        )
    return image_id


def set_image_status(image_id: str, status: str):
    with get_conn() as conn:
        conn.execute("UPDATE images SET status = ? WHERE id = ?", (status, image_id))


def get_image(image_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        return dict(row) if row else None


def finalize_image_processing(image_id: str, sensor_id: str, result: dict):
    """Une fois le traitement terminé : archive le résultat (texte) dans l'historique
    léger pour le chat, puis supprime l'entrée de la table de queue 'images'.
    Le fichier image lui-même est supprimé séparément par l'appelant (voir worker.py)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO image_analysis_history (sensor_id, result_json, created_at) VALUES (?, ?, ?)",
            (sensor_id, json.dumps(result, ensure_ascii=False), datetime.utcnow().isoformat()),
        )
        conn.execute("DELETE FROM images WHERE id = ?", (image_id,))


def get_recent_image_analyses(limit: int):
    """Contexte pour le chat : lit l'historique léger (texte seulement, images déjà supprimées)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM image_analysis_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- Métriques ----------

def insert_metrics_batch(metrics_list: list):
    with get_conn() as conn:
        for m in metrics_list:
            conn.execute(
                "INSERT INTO metrics (humidity, air_temp, soil_temp, raw_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (
                    m.get("humidity"),
                    m.get("air_temp"),
                    m.get("soil_temp"),
                    json.dumps(m, ensure_ascii=False),
                    datetime.utcnow().isoformat(),
                ),
            )


def get_recent_metrics(limit: int):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM metrics ORDER BY fetched_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def save_metrics_analysis(result: dict):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO metrics_analysis (result_json, created_at) VALUES (?, ?)",
            (json.dumps(result, ensure_ascii=False), datetime.utcnow().isoformat()),
        )
