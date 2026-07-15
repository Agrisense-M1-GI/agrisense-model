"""
Script de diagnostic : teste UNIQUEMENT moondream (sans llama), en utilisant exactement
le même code que le service (ollama_client.analyze_image_with_moondream), pour voir
précisément ce que le modèle de vision détecte sur une image donnée.

Affiche aussi des infos de diagnostic (taille du fichier, dimensions) car une réponse
dégénérée du type "!!!" est souvent liée à une image trop lourde ou à un souci d'encodage.

Usage :
    python test_moondream.py "C:\\chemin\\vers\\image.jpg"
"""
import os
import sys
import base64

import requests

from config import OLLAMA_HOST, MOONDREAM_MODEL
from ollama_client import analyze_image_with_moondream, _image_to_base64, TIMEOUT

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python test_moondream.py <chemin_vers_image>")
        sys.exit(1)

    image_path = sys.argv[1]

    # --- Infos de base sur le fichier ---
    size_bytes = os.path.getsize(image_path)
    print(f"Fichier : {image_path}")
    print(f"Taille  : {size_bytes / 1024:.1f} Ko")

    try:
        from PIL import Image
        with Image.open(image_path) as img:
            print(f"Dimensions : {img.size[0]}x{img.size[1]} px, mode={img.mode}")
    except ImportError:
        print("(Pillow non installé, pas de vérification des dimensions - "
              "pip install Pillow --break-system-packages pour l'activer)")
    except Exception as e:
        print(f"Impossible de lire les dimensions : {e}")

    b64 = _image_to_base64(image_path)
    print(f"Taille en base64 : {len(b64) / 1024:.1f} Ko\n")

    # --- Appel brut à Ollama pour voir la réponse complète (pas juste le champ 'response') ---
    print("=== Appel direct à l'API Ollama (réponse JSON complète) ===")
    payload = {
        "model": MOONDREAM_MODEL,
        "prompt": "Décris cette image en détail.",
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
    print(f"Status HTTP : {resp.status_code}")
    print(resp.json())
    print()

    # --- Test avec le vrai code du service (prompt complet orienté agriculture) ---
    print("=== Description via le code du service (analyze_image_with_moondream) ===")
    description = analyze_image_with_moondream(image_path)
    print(repr(description))