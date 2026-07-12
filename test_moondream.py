"""
Script de diagnostic : teste UNIQUEMENT moondream (sans llama), en utilisant exactement
le même code que le service (ollama_client.analyze_image_with_moondream), pour voir
précisément ce que le modèle de vision détecte sur une image donnée.

Usage :
    python test_moondream.py "C:\\chemin\\vers\\image.jpg"
"""
import sys

from ollama_client import analyze_image_with_moondream

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage : python test_moondream.py <chemin_vers_image>")
        sys.exit(1)

    image_path = sys.argv[1]
    print(f"Analyse de : {image_path}\n")
    description = analyze_image_with_moondream(image_path)
    print("=== Description brute de moondream ===")
    print(description)
