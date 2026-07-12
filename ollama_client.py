"""
Wrapper simple autour de l'API Ollama locale (http://localhost:11434).
Deux usages :
  - moondream : décrire une image (analyse brute)
  - llama3.2:1b : reformater cette description en JSON structuré, ou discuter (chat)
"""
import base64
import json
import re
import requests

from config import OLLAMA_HOST, MOONDREAM_MODEL, LLAMA_MODEL

TIMEOUT = 120  # généreux, l'inférence CPU peut être lente


def _image_to_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def analyze_image_with_moondream(image_path: str) -> str:
    """Retourne une description texte brute de l'image, orientée agriculture."""
    prompt = (
        "Décris cette image de champ agricole avec un maximum de précision. "
        "Vérifie spécifiquement et mentionne explicitement si tu observes : "
        "des taches sombres, noires ou brunes sur les fruits ou les feuilles, "
        "des zones de pourriture ou de nécrose, des lésions ou des trous, "
        "un flétrissement, une décoloration anormale, ou des parasites visibles. "
        "Si tu ne vois aucun de ces signes, dis-le clairement. "
        "Décris aussi l'état général du sol (sec, humide, boueux). "
        "Réponds en français."
    )
    payload = {
        "model": MOONDREAM_MODEL,
        "prompt": prompt,
        "images": [_image_to_base64(image_path)],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()


def _extract_json(text: str) -> dict:
    """Le modèle peut entourer le JSON de texte ou de balises markdown ; on extrait le bloc JSON."""
    text = text.strip()
    text = re.sub(r"^```json|```$", "", text, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"Aucun JSON trouvé dans la réponse du modèle : {text[:200]}")
    return json.loads(match.group(0))


VALID_ETATS = {"normal", "critique", "alerte"}
VALID_PRIORITES = {"basse", "moyenne", "haute"}

# Petites corrections de fautes de frappe fréquentes chez les petits modèles.
_TYPO_FIXES = {
    "baesse": "basse", "bass": "basse", "basse ": "basse",
    "moyen": "moyenne", "moyene": "moyenne",
    "haut": "haute", "hautes": "haute",
    "critque": "critique", "critic": "critique",
    "alert": "alerte", "alerta": "alerte",
}

# Filet de sécurité par mots-clés : les petits modèles (llama3.2:1b) peuvent décrire un
# problème dans "actions" tout en mettant "normal" dans "etat" par erreur de logique.
# On ne fait donc pas confiance au champ "etat" seul : on scanne aussi le texte pour des
# signes de problème et on force la prudence si nécessaire, quoi que le modèle ait décidé.
# NB : moondream répond parfois en anglais même si on lui écrit en français, d'où la liste
# bilingue. Limite connue : une négation ("no spots visible") contient quand même le mot-clé
# et peut déclencher une fausse alerte — c'est un compromis assumé (mieux vaut un faux positif
# qu'un vrai problème masqué).
_RED_FLAG_KEYWORDS = [
    # Français
    "pourriture", "pourri", "nécrose", "necrose", "lésion", "lesion",
    "maladie", "malade", "parasite", "moisissure", "tache noire", "taches noires",
    "tache sombre", "taches sombres", "flétri", "fletri", "infection", "infecté", "infecte",
    "champignon", "mildiou", "rouille", "carence", "anormal", "anomalie",
    # Anglais (moondream répond parfois dans cette langue)
    "rot", "rotting", "rotten", "disease", "diseased", "pest", "mold", "mould",
    "black spot", "brown spot", "dark spot", "wilt", "wilted", "infected",
    "fungus", "blight", "rust", "deficiency", "abnormal", "anomaly", "decay",
]


def _contains_red_flag(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _RED_FLAG_KEYWORDS)


def _normalize_result(result: dict, source_text: str = "") -> dict:
    """Valide et corrige le JSON renvoyé par le modèle. Principe de prudence : si une valeur
    est invalide/manquante et ne peut pas être corrigée avec certitude, on force une alerte
    plutôt qu'un état "normal" — mieux vaut un faux positif (vérifié manuellement) qu'un faux
    négatif (un vrai problème passé inaperçu, comme une nécrose apicale non détectée).

    `source_text` = texte source (description moondream et/ou "actions" générées) qu'on scanne
    par mots-clés, car on ne peut pas faire confiance à la cohérence logique du petit modèle
    de formatage entre son propre "etat" et son propre "actions"."""
    etat = str(result.get("etat", "")).strip().lower()
    priorite = str(result.get("priorite", "")).strip().lower()
    actions = str(result.get("actions", "")).strip()

    etat = _TYPO_FIXES.get(etat, etat)
    priorite = _TYPO_FIXES.get(priorite, priorite)

    needs_review = False
    if etat not in VALID_ETATS:
        needs_review = True
        etat = "alerte"
    if priorite not in VALID_PRIORITES:
        needs_review = True
        priorite = "haute"
    if not actions:
        needs_review = True
        actions = "Résultat du modèle incomplet ou invalide."

    if needs_review:
        actions = f"[À vérifier manuellement - sortie du modèle invalide] {actions}"

    # Filet de sécurité par mots-clés, appliqué APRÈS la validation ci-dessus : si le texte
    # (description source + actions du modèle) mentionne un signe de problème mais que le
    # modèle a quand même dit "normal"/"basse", on corrige de force.
    combined_text = f"{source_text} {actions}"
    if _contains_red_flag(combined_text):
        if etat == "normal":
            etat = "critique"
            actions = f"[Corrigé automatiquement - signe de problème détecté par mots-clés] {actions}"
        if priorite == "basse":
            priorite = "moyenne"

    return {"etat": etat, "actions": actions, "priorite": priorite}


def format_image_analysis_with_llama(description: str) -> dict:
    """Transforme la description brute de moondream en JSON structuré :
    {etat, actions, priorite}"""
    prompt = f"""Voici la description d'une image de champ agricole faite par un système de vision :

\"\"\"{description}\"\"\"

Analyse cette description avec rigueur. S'il est fait mention de taches sombres, pourriture,
nécrose, lésions, flétrissement, décoloration anormale ou parasites, l'état ne peut PAS être
"normal" : utilise "critique" ou "alerte" selon la gravité, et priorité "moyenne" ou "haute".

Réponds UNIQUEMENT avec un objet JSON valide, sans aucun texte autour, avec exactement ces
champs (respecte l'orthographe EXACTE des valeurs, pas de faute de frappe) :
- "etat": exactement "normal", "critique" ou "alerte"
- "actions": une courte description (2-3 phrases max) de ce qui est observé et des actions à mener
- "priorite": exactement "basse", "moyenne" ou "haute"

JSON :"""
    payload = {
        "model": LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        # Filet de sécurité : si le modèle a mal formaté, on force une revue manuelle
        # plutôt que de renvoyer un faux "normal" silencieux.
        parsed = {
            "etat": "alerte",
            "actions": f"[À vérifier manuellement - JSON invalide] Description brute : {description[:300]}",
            "priorite": "haute",
        }
    return _normalize_result(parsed, source_text=description)


def analyze_metrics_with_llama(metrics_list: list) -> dict:
    """Analyse un lot de métriques sol (humidité, temp air/sol) et retourne un état structuré."""
    metrics_str = json.dumps(metrics_list, ensure_ascii=False)
    prompt = f"""Voici une série de mesures récentes d'un capteur agricole (humidité, température
de l'air, température du sol) :

{metrics_str}

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour, avec ces champs :
- "etat": une valeur parmi "normal", "critique", "alerte"
- "actions": une courte description (2-3 phrases max) de la tendance observée et des actions à mener
- "priorite": une valeur parmi "basse", "moyenne", "haute"

JSON :"""
    payload = {
        "model": LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    raw = resp.json().get("response", "")
    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        parsed = {
            "etat": "alerte",
            "actions": "[À vérifier manuellement - JSON invalide] Analyse des métriques non formatée correctement.",
            "priorite": "haute",
        }
    return _normalize_result(parsed)


def chat_with_context(question: str, context: str) -> str:
    """Discussion libre avec l'IA, enrichie du contexte (métriques + analyses d'images récentes)."""
    prompt = f"""Tu es un assistant agricole. Voici le contexte récent du terrain :

{context}

Question de l'utilisateur : {question}

Réponds de façon concise et pratique, en te basant sur le contexte ci-dessus quand c'est pertinent."""
    payload = {
        "model": LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4},
    }
    resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json().get("response", "").strip()