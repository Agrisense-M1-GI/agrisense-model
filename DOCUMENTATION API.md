## 2. Le fichier `API_DOCUMENTATION.md` mis à jour

Voici la nouvelle version de ta documentation d'API. Tu peux écraser le fichier précédent avec ces informations qui expliquent en détail le fonctionnement des **trois endpoints**.

```markdown
# Spécification de l'API REST - AgriSense IA Engine 🌿📡

Cette documentation décrit les protocoles d'échange et les points d'accès (endpoints) mis à la disposition de l'équipe Backend (Laravel) pour interagir avec le modèle d'intelligence artificielle AgriSense.

## 📌 Spécifications Globales
* **URL Racine :** `http://127.0.0.1:5000`
* **Entêtes HTTP obligatoires :** `Content-Type: application/json`
* **Format d'échange :** JSON strict (Entrées et Sorties)

---

## 📡 Liste des Points d'Accès (Endpoints)

### 1. Vérification de la disponibilité (`GET /api/ia/statut`)
Permet de s'assurer que le serveur Flask tourne correctement en tâche de fond.

* **Code de retour succès :** `200 OK`
* **Exemple de réponse :**
```json
{
    "status": "online",
    "service": "AgriSense IA Engine",
    "model": "gemini-2.5-flash"
}
2. Diagnostic Phytosanitaire (POST /api/ia/analyser)
Analyse l'état de santé d'une plante en croissance à partir de la photo la plus récente capturée sur le terrain.

📥 Corps de la requête (JSON)
culture (String, Obligatoire) : Le nom de la plante ciblée (ex: "Tomate").

dossier_images (String, Optionnel) : Le répertoire où récupérer l'image. Défaut : "images_backend".

📤 Réponses possibles (JSON)
Cas A : Analyse IA effectuée (Changement visuel ou plante malade) -> 200 OK
{
    "succes": true,
    "analyse_requise": true,
    "fichier_traite": "capture_recent.jpg",
    "ia_output": {
        "diagnostic_titre": "Chlorose ferrique suspectée",
        "statut_general": "Moyen",
        "diagnostic_sante": "Jaunissement des tissus entre les nervures sur les jeunes feuilles.",
        "actions_suggerees": [
            "Apporter un engrais riche en chélates de fer.",
            "Vérifier le pH du sol pour s'assurer qu'il n'est pas trop calcaire."
        ]
    }
}
Cas B : Économie de ressources (Plante saine et pixels identiques) -> 200 OK
{
    "succes": true,
    "analyse_requise": false,
    "fichier_traite": "capture_recent.jpg",
    "ia_output": {
        "diagnostic_titre": "Plante stable et saine",
        "statut_general": "Normal",
        "diagnostic_sante": "Aucun changement détecté par rapport au cycle précédent. La plante reste saine.",
        "actions_suggerees": [
            "Maintenir la surveillance automatique."
        ]
    }
}
3. Prédiction d'Adéquation de Culture (POST /api/ia/predire)
Évalue l'environnement avant la plantation pour recommander si le terrain est propice à accueillir de l'ananas, de la mangue, des oignons ou des tomates.

📥 Corps de la requête (JSON)
metriques (Object, Obligatoire) : Dictionnaire contenant les relevés des capteurs physiques ou les données saisies par l'utilisateur.

dossier_images (String, Optionnel) : Chemin du dossier contenant une éventuelle photo du sol nu/terrain.

Exemple de structure envoyée par le Backend :

JSON
{
    "dossier_images": "images_backend",
    "metriques": {
        "pH_sol": "5.5",
        "humidite_sol": "65%",
        "temperature_moyenne": "28°C",
        "texture": "Sableux"
    }
}
📤 Réponse du Serveur (200 OK)
L'IA retourne une analyse synthétique globale suivie d'un tableau d'évaluation trié par pertinence.

JSON
{
    "succes": true,
    "mode_evaluation": "Hybride (Image du terrain + Métriques)",
    "fichier_sol_analyse": "sol_champ_nord.jpg",
    "predictions_output": {
        "analyse_environnementale_synthese": "Sol très propice aux cultures de zones chaudes nécessitant un excellent drainage grâce à sa texture sableuse et son acidité marquée.",
        "recommandations": [
            {
                "culture": "Ananas",
                "score_compatibilite": "95%",
                "justification": "Le pH de 5.5 (acide) couplé à un sol sableux drainant et une température de 28°C réunit les conditions parfaites pour l'ananas."
            },
            {
                "culture": "Tomate",
                "score_compatibilite": "65%",
                "justification": "Possible mais le sol sableux lessive rapidement les nutriments. Un apport régulier de compost sera indispensable."
            },
            {
                "culture": "Oignon",
                "score_compatibilite": "30%",
                "justification": "Non recommandé. L'humidité du sol à 65% est trop élevée, ce qui provoquera l'asphyxie et le pourrissement des bulbes d'oignons."
            }
        ]
    }
}
🛠️ Code d'intégration Laravel type (Client HTTP)
Voici comment l'équipe backend peut appeler l'endpoint de prédiction depuis un contrôleur PHP :

PHP
use Illuminate\Support\Facades\Http;

public function obtenirPredictionsTerrain()
{
    $response = Http::post('[http://127.0.0.1:5000/api/ia/predire](http://127.0.0.1:5000/api/ia/predire)', [
        'dossier_images' => storage_path('app/public/terrain'),
        'metriques' => [
            'pH_sol' => '6.2',
            'humidite_sol' => '40%',
            'temperature_moyenne' => '26°C'
        ]
    ]);

    if ($response->successful()) {
        $data = $response->json();
        if ($data['succes']) {
            // Contient la synthèse et le tableau des cultures triées
            return view('predictions.index', ['recommandations' => $data['predictions_output']]);
        }
    }
    
    return response()->json(['error' => 'Erreur de calcul du module IA'], 500);
}