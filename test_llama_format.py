"""
Script de diagnostic : teste UNIQUEMENT le formatage llama3.2:1b, en lui donnant une
description texte (que tu peux copier depuis test_moondream.py, ou une description de
test comme celle par défaut ci-dessous simulant clairement une nécrose apicale visible).

Usage :
    python test_llama_format.py
    python test_llama_format.py "ta propre description ici"
"""
import sys

from ollama_client import format_image_analysis_with_llama

DEFAULT_TEST_DESCRIPTION = (
    "L'image montre quatre tomates sur une même tige. Trois d'entre elles présentent "
    "de larges zones noires et brunes de pourriture avec des lésions ouvertes et craquelées "
    "à leur extrémité inférieure, caractéristiques d'une nécrose apicale. La quatrième tomate "
    "est encore verte et semble saine. Les feuilles environnantes paraissent en bonne santé."
)

if __name__ == "__main__":
    description = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TEST_DESCRIPTION
    print(f"Description en entrée :\n{description}\n")
    result = format_image_analysis_with_llama(description)
    print("=== Résultat formaté par llama3.2:1b ===")
    print(result)
