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


def _post_generate(payload: dict) -> dict:
    """Wrapper commun pour tous les appels à /api/generate : si Ollama renvoie une erreur,
    on inclut le corps de sa réponse (le vrai message d'erreur) dans l'exception, au lieu de
    le laisser masqué par un simple 'raise_for_status()' générique."""
    resp = requests.post(f"{OLLAMA_HOST}/api/generate", json=payload, timeout=TIMEOUT)
    if resp.status_code >= 400:
        raise requests.exceptions.HTTPError(
            f"{resp.status_code} depuis Ollama pour le modèle '{payload.get('model')}' : {resp.text}",
            response=resp,
        )
    return resp.json()


def analyze_image_with_moondream(image_path: str) -> str:
    """Retourne une description texte brute de l'image, orientée agriculture.

    IMPORTANT : moondream (~1.6B paramètres) est instable dès que le prompt contient une
    instruction CONDITIONNELLE ("décris X, et si tu vois Y, précise Z") — il casse et
    recopie des fragments du prompt ou produit du texte dégénéré ("!!!"), même avec un
    prompt court. Il ne sait faire qu'une chose de façon fiable : une description libre,
    sans condition ni instruction imbriquée. Toute la détection de maladie/anomalie est
    donc déléguée à l'étape suivante (llama + filet de mots-clés dans _normalize_result),
    PAS à moondream. Ne pas ajouter de conditions à ce prompt sans retester avec
    test_moondream.py sur plusieurs images."""
    prompt = "Décris cette image de champ agricole en détail."
    payload = {
        "model": MOONDREAM_MODEL,
        "prompt": prompt,
        "images": [_image_to_base64(image_path)],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    resp_json = _post_generate(payload)
    return resp_json.get("response", "").strip()


# Dictionnaire de termes agricoles courants EN->FR, substitués AVANT l'appel au traducteur.
# Ça réduit le risque que le petit modèle mal-traduise les mots les plus importants du texte
# (ex : a déjà produit "arbre à pomme" pour "pineapple") — les noms clés sont déjà en français
# quand le modèle ne fait plus que traduire la grammaire autour.
_KNOWN_TERMS_EN_FR = {
    "pineapple": "ananas", "pineapples": "ananas",
    "tomato": "tomate", "tomatoes": "tomates",
    "apple": "pomme", "apples": "pommes",
    "banana": "banane", "bananas": "bananes",
    "mango": "mangue", "mangoes": "mangues",
    "orange": "orange", "oranges": "oranges",
    "lemon": "citron", "lemons": "citrons",
    "grape": "raisin", "grapes": "raisins",
    "corn": "maïs", "maize": "maïs",
    "potato": "pomme de terre", "potatoes": "pommes de terre",
    "pepper": "poivron", "peppers": "poivrons",
    "cucumber": "concombre", "cucumbers": "concombres",
    "leaf": "feuille", "leaves": "feuilles",
    "plant": "plante", "plants": "plantes",
    "stem": "tige", "stems": "tiges",
    "root": "racine", "roots": "racines",
    "soil": "sol", "field": "champ", "fields": "champs",
    "crop": "culture", "crops": "cultures",
    "flower": "fleur", "flowers": "fleurs",
    "branch": "branche", "branches": "branches",
    "spiky": "épineux", "crown": "couronne", "ripe": "mûr",
}


def _pre_substitute_known_terms(text: str) -> str:
    """Remplace les mots agricoles connus par leur équivalent français, avant traduction."""
    result = text
    for en, fr in _KNOWN_TERMS_EN_FR.items():
        result = re.sub(rf"\b{re.escape(en)}\b", fr, result, flags=re.IGNORECASE)
    return result


def _translate_to_french(text: str) -> str:
    """Traduit un texte en français. Tâche volontairement SIMPLE et unique (pas de jugement,
    pas de condition) car c'est le genre de tâche où un petit modèle comme llama3.2:1b reste
    globalement plus fiable que sur l'analyse/la recommandation — mais reste imparfait sur des
    mots moins courants (ex : a déjà produit "arbre à pomme" pour "pineapple"). Le contexte
    explicite ("texte agricole, décrit une plante/un fruit") et la demande de traduction
    littérale aident à réduire ce genre d'erreur, sans l'éliminer complètement."""
    if not text.strip():
        return text
    pre_substituted = _pre_substitute_known_terms(text)
    prompt = (
        "Traduis fidèlement et littéralement ce texte en français (certains mots sont déjà "
        "en français, garde-les tels quels et traduis le reste). Le texte décrit une image "
        "agricole (une plante, un fruit ou des feuilles). Ne reformule pas.\n\n"
        f'Texte : "{pre_substituted}"\n\n'
        "Traduction française (uniquement la traduction, rien d'autre) :"
    )
    payload = {
        "model": LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    try:
        resp_json = _post_generate(payload)
        translated = resp_json.get("response", "").strip().strip('"')
        return translated if translated else text
    except requests.exceptions.RequestException:
        # En cas d'échec, on préfère renvoyer le texte original (même en anglais) plutôt
        # que de faire planter toute l'analyse pour un problème de traduction.
        return text


# Recommandations par mot-clé détecté : plus fiable qu'une recommandation générée en texte
# libre par llama3.2:1b, qui a tendance à halluciner des conseils sans rapport avec l'image
# (ex : recommander de "retirer les fruits atteints" sur une image parfaitement saine).
_RECOMMENDATIONS_BY_KEYWORD = [
    (["pourriture", "pourri", "rot", "rotting", "rotten", "decay", "nécrose", "necrose"],
     "Retirer les fruits ou parties atteints et vérifier l'irrigation (les excès ou manques "
     "d'eau sont une cause fréquente de pourriture/nécrose)."),
    (["parasite", "pest"],
     "Inspecter de plus près pour confirmer la présence de parasites et envisager un "
     "traitement adapté si confirmé."),
    (["champignon", "fungus", "mildiou", "blight", "moisissure", "mold", "mould", "rouille", "rust"],
     "Isoler la zone si possible et envisager un traitement fongicide adapté après confirmation."),
    (["flétri", "fletri", "wilt", "wilted"],
     "Vérifier l'irrigation et l'état racinaire de la plante concernée."),
    (["lésion", "lesion", "tache noire", "taches noires", "tache sombre", "taches sombres",
      "black spot", "brown spot", "dark spot"],
     "Examiner de plus près les zones affectées et surveiller leur évolution dans les prochains jours."),
]
_DEFAULT_RECOMMENDATION_PROBLEME = (
    "Inspection manuelle recommandée sur le terrain pour confirmer la nature du problème et "
    "traiter si nécessaire."
)
_RECOMMENDATION_NORMAL = "Aucune action nécessaire pour l'instant."


def _generate_recommendation(etat: str, text: str) -> str:
    """Génère une recommandation en français à partir de règles fixes basées sur les
    mots-clés détectés, plutôt que de laisser le modèle rédiger un conseil en texte libre
    (trop instable/halluciné à cette taille de modèle)."""
    if etat == "normal":
        return _RECOMMENDATION_NORMAL
    text_lower = text.lower()
    for keywords, recommendation in _RECOMMENDATIONS_BY_KEYWORD:
        if any(kw in text_lower for kw in keywords):
            return recommendation
    return _DEFAULT_RECOMMENDATION_PROBLEME


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
    """Cherche des signes de problème dans le texte, PHRASE PAR PHRASE, en ignorant les
    mentions niées (ex : "ne présente aucune tache" ne doit pas déclencher d'alerte, alors
    que "présente des taches" doit la déclencher). Une analyse mot-clé globale sans tenir
    compte des négations produirait trop de faux positifs sur des descriptions qui disent
    explicitement l'absence d'un problème."""
    negation_words = [
        "pas de", "pas ", "aucun", "aucune", "sans ", "ni ", "non ",
        "no ", "not ", "n'y a pas", "n'a pas", "absence de",
    ]
    sentences = re.split(r"[.!?;\n]", text.lower())
    for sentence in sentences:
        for kw in _RED_FLAG_KEYWORDS:
            if kw in sentence:
                # Le mot-clé est présent : on regarde si la MÊME phrase contient une négation.
                if not any(neg in sentence for neg in negation_words):
                    return True
                # sinon : négation détectée dans cette phrase, on ne compte pas ce mot-clé ici
    return False


def _normalize_result(result: dict, source_text: str = "") -> dict:
    """Valide et corrige le JSON renvoyé par le modèle. Principe de prudence : si une valeur
    est invalide/manquante et ne peut pas être corrigée avec certitude, ou si la description
    source contient un signe de problème que le modèle a ignoré, on force une alerte plutôt
    qu'un état "normal" — mieux vaut un faux positif (vérifié manuellement) qu'un faux négatif.

    `source_text` = la description source (moondream), plus fiable que le résumé texte du
    petit modèle de formatage, qui peut halluciner ou se contredire d'un run à l'autre même
    à température 0. En cas de correction, on préfère donc reconstruire le message final à
    partir de la description source plutôt que d'empiler des préfixes sur un texte du modèle
    potentiellement faux ou contradictoire."""
    etat = str(result.get("etat", "")).strip().lower()
    priorite = str(result.get("priorite", "")).strip().lower()
    actions = str(result.get("actions", "")).strip()

    etat = _TYPO_FIXES.get(etat, etat)
    priorite = _TYPO_FIXES.get(priorite, priorite)

    invalid_output = etat not in VALID_ETATS or priorite not in VALID_PRIORITES or not actions

    if etat not in VALID_ETATS:
        etat = "alerte"

    # On scanne la description source ET le texte du modèle (même invalide) pour les mots-clés.
    combined_text = f"{source_text} {actions}"
    red_flag = _contains_red_flag(combined_text)

    if invalid_output or (red_flag and etat == "normal"):
        # Le résultat du modèle n'est pas fiable ici (invalide, ou en contradiction avec un
        # signe de problème détecté dans la description). On reconstruit un message propre
        # ENTIÈREMENT EN FRANÇAIS, avec une vraie recommandation, plutôt que de recopier le
        # texte du modèle (potentiellement en anglais, incohérent, ou halluciné).
        if red_flag:
            etat = "critique" if etat == "normal" else etat
            priorite = "moyenne" if priorite == "basse" else priorite
        if red_flag:
            actions = (
                "Un signe potentiel de problème a été détecté automatiquement dans les données "
                "d'analyse. Inspection manuelle recommandée sur le terrain pour confirmer la "
                "nature du problème et isoler/traiter la zone concernée si nécessaire."
            )
        else:
            actions = "Aucun problème détecté. Aucune action nécessaire pour l'instant."
    elif red_flag and priorite == "basse":
        priorite = "moyenne"

    # Cohérence etat/priorite : si le modèle a renvoyé une priorité invalide, on la déduit de
    # l'état plutôt que d'imposer un défaut fixe (évite les combinaisons absurdes du type
    # etat="normal" + priorite="haute").
    if priorite not in VALID_PRIORITES:
        priorite = "basse" if etat == "normal" else "haute"

    return {"etat": etat, "actions": actions, "priorite": priorite}


def format_image_analysis_with_llama(description: str) -> dict:
    """Construit le résultat structuré {etat, actions, priorite} à partir de la description
    brute de moondream.

    Approche volontairement séparée en 3 étapes indépendantes plutôt qu'une seule requête
    "tout-en-un" à llama :
      1. Traduction de la description (tâche simple, fiable même pour un petit modèle)
      2. Classification etat/priorite par llama (tâche de classification, plus contrainte
         qu'une génération de texte libre, donc plus fiable)
      3. Recommandation générée par RÈGLES FIXES sur mots-clés (pas par le modèle) — on a
         observé que llama3.2:1b invente des recommandations sans rapport avec l'image
         (ex : "retirer les fruits atteints" sur une image saine) dès qu'on lui laisse
         rédiger ce texte librement.
    Le champ "actions" final est TOUJOURS construit ainsi : description traduite + recommandation.
    """
    prompt = f"""Description d'une image de champ agricole (éventuellement en anglais) :
"{description}"

À partir UNIQUEMENT de cette description (n'invente aucun détail qui n'y figure pas),
réponds avec un objet JSON ayant exactement ces 2 champs :
- "etat": "normal" si la description ne mentionne aucun problème (maladie, taches, pourriture,
  parasites, flétrissement), "critique" ou "alerte" si elle en mentionne un
- "priorite": "basse" si "etat" est "normal", sinon "moyenne" ou "haute"

Réponds UNIQUEMENT avec le JSON, sans texte autour.
JSON :"""
    payload = {
        "model": LLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
    }
    resp_json = _post_generate(payload)
    raw = resp_json.get("response", "")
    try:
        parsed = _extract_json(raw)
    except (ValueError, json.JSONDecodeError):
        # Filet de sécurité : si le modèle a mal formaté, on force une revue manuelle
        # plutôt que de renvoyer un faux "normal" silencieux.
        parsed = {"etat": "alerte", "priorite": "haute"}

    # On donne un champ "actions" bidon ici : _normalize_result ne s'en sert que pour son
    # propre filet de mots-clés, on reconstruit le vrai champ juste après.
    parsed.setdefault("actions", "")
    normalized = _normalize_result(parsed, source_text=description)

    description_fr = _translate_to_french(description)
    recommandation = _generate_recommendation(normalized["etat"], f"{description} {description_fr}")
    normalized["actions"] = f"{description_fr} Action recommandée : {recommandation}"

    return normalized


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
    resp_json = _post_generate(payload)
    raw = resp_json.get("response", "")
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
    resp_json = _post_generate(payload)
    return resp_json.get("response", "").strip()