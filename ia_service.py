import os
import glob
import json
import shutil
from google import genai
from google.genai import types
from PIL import Image, ImageChops, ImageStat

class AgriSenseIAService:
    def __init__(self, api_key: str = None):
        """Initialise le client Gemini et définit les fichiers de mémoire locale."""
        self.client = genai.Client(api_key=api_key)
        self.model_name = "gemini-2.5-flash"
        
        # Fichiers de persistance pour l'algorithme local de diagnostic
        self.chemin_image_sauvegarde = "derniere_capture.jpg"
        self.chemin_statut_sauvegarde = "dernier_statut.txt"

    def _recuperer_image_recente(self, dossier_backend: str) -> str:
        """Scane le dossier du backend et retourne le chemin de l'image la plus récente (via timestamp)."""
        if not dossier_backend or not os.path.exists(dossier_backend):
            return None
        extensions = ('*.jpg', '*.jpeg', '*.png')
        fichiers = []
        for ext in extensions:
            fichiers.extend(glob.glob(os.path.join(dossier_backend, ext)))
        
        if not fichiers:
            return None
            
        fichiers.sort(key=os.path.getmtime, reverse=True)
        return fichiers[0]

    def _optimiser_image(self, chemin_image: str, max_taille=(800, 800)) -> Image.Image:
        """Redimensionne l'image à la volée pour diviser par 4 la consommation de tokens."""
        img = Image.open(chemin_image).convert('RGB')
        img.thumbnail(max_taille, Image.Resampling.LANCZOS)
        return img

    def _lire_dernier_statut(self) -> str:
        if os.path.exists(self.chemin_statut_sauvegarde):
            with open(self.chemin_statut_sauvegarde, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "Normal"

    def _sauvegarder_statut(self, statut: str):
        with open(self.chemin_statut_sauvegarde, "w", encoding="utf-8") as f:
            f.write(statut)

    def _evaluer_changement_reel(self, chemin_actuelle: str, seuil: float = 2.0) -> bool:
        """Compare mathématiquement les pixels de l'image actuelle avec la dernière analysée."""
        if not os.path.exists(self.chemin_image_sauvegarde):
            return True
            
        img1 = Image.open(chemin_actuelle).convert('RGB')
        img2 = Image.open(self.chemin_image_sauvegarde).convert('RGB')
        img2 = img2.resize(img1.size)
        
        diff = ImageChops.difference(img1, img2)
        stat = ImageStat.Stat(diff)
        moyenne_diff = sum(stat.mean) / 3.0
        
        return moyenne_diff > seuil

    # =========================================================================
    # MODULE 1 : DIAGNOSTIC PHYTOSANITAIRE (DÉJÀ VALIDÉ)
    # =========================================================================
    def executer_analyse_vers_json(self, dossier_backend: str, culture_cible: str) -> dict:
        try:
            chemin_actuelle = self._recuperer_image_recente(dossier_backend)
            if not chemin_actuelle:
                return {"succes": False, "error": "Aucune image trouvée dans le dossier du backend."}
                
            statut_precedent = self._lire_dernier_statut()
            a_change = self._evaluer_changement_reel(chemin_actuelle)
            
            if not a_change and statut_precedent == "Normal":
                shutil.copy(chemin_actuelle, self.chemin_image_sauvegarde)
                return {
                    "succes": True,
                    "analyse_requise": False,
                    "fichier_traite": os.path.basename(chemin_actuelle),
                    "ia_output": {
                        "diagnostic_titre": "Plante stable et saine",
                        "statut_general": "Normal",
                        "diagnostic_sante": "Aucun changement détecté par rapport au cycle précédent. La plante reste saine.",
                        "actions_suggerees": ["Maintenir la surveillance automatique."]
                    }
                }
            
            img_analyse = self._optimiser_image(chemin_actuelle)
            contenu_requete = [
                f"Culture ciblée dans ce champ : {culture_cible}",
                f"Statut sanitaire lors de l'analyse précédente : {statut_precedent}",
                "Image actuelle du champ à inspecter :",
                img_analyse
            ]
            
            prompt = """
            Tu es l'expert en vision par ordinateur et agronomie pour AgriSense. 
            Analyse l'image de la plante et détecte toute anomalie (taches, chlorose, nécrose, flétrissement).
            Respecte strictement la structure JSON demandée.
            """
            contenu_requete.append(prompt)

            schema_json = {
                "type": "OBJECT",
                "properties": {
                    "diagnostic_titre": {"type": "STRING"},
                    "statut_general": {"type": "STRING"},
                    "diagnostic_sante": {"type": "STRING"},
                    "actions_suggerees": {"type": "ARRAY", "items": {"type": "STRING"}}
                },
                "required": ["diagnostic_titre", "statut_general", "diagnostic_sante", "actions_suggerees"]
            }

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contenu_requete,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_json,
                    temperature=0.1
                )
            )
            
            resultat_ia_json = json.loads(response.text)
            shutil.copy(chemin_actuelle, self.chemin_image_sauvegarde)
            self._sauvegarder_statut(resultat_ia_json.get("statut_general", "Normal"))

            return {
                "succes": True,
                "analyse_requise": True,
                "fichier_traite": os.path.basename(chemin_actuelle),
                "ia_output": resultat_ia_json
            }
        except Exception as e:
            return {"succes": False, "error": f"Erreur système IA : {str(e)}"}

    # =========================================================================
    # MODULE 2 : PRÉDICTION DE CULTURE (NOUVEAUTÉ)
    # =========================================================================
    def executer_prediction_culture(self, dossier_backend: str, metriques_sol: dict) -> dict:
        """
        Analyse les métriques du sol (et l'échantillon visuel du terrain si disponible)
        pour recommander la compatibilité des cultures (ananas, mangue, tomates, oignons, etc.).
        """
        try:
            contenu_requete = []
            
            # Conversion des métriques JSON en texte pour le prompt
            texte_metriques = "\n".join([f"- {clef}: {valeur}" for clef, valeur in metriques_sol.items()])
            contenu_requete.extend([
                "--- MÉTRIQUES DU SOL ET DU CLIMAT (DONNÉES CAPTEURS OU SAISIES) ---",
                texte_metriques,
                "------------------------------------------------------------------"
            ])
            
            # Tentative de récupération d'une image (Sol nu, terrain, etc.)
            chemin_sol = self._recuperer_image_recente(dossier_backend)
            mode_analyse = "Métriques pures (Pas de visuel)"
            
            if chemin_sol:
                mode_analyse = "Hybride (Image du terrain + Métriques)"
                img_sol = self._optimiser_image(chemin_sol)
                contenu_requete.extend([
                    "--- IMAGE VISUELLE DU TERRAIN / SOL FOURNIE ---",
                    img_sol
                ])
                
            prompt = f"""
            Tu es le moteur prédictif et conseiller agronomique en chef d'AgriSense.
            Mode d'analyse actuel : {mode_analyse}.
            
            Analyse méticuleusement les caractéristiques fournies (pH, humidité, température, type de sol).
            Tu dois évaluer la pertinence de planter des cultures populaires africaines et maraîchères, notamment : Ananas, Mangue, Tomate, Oignon, et d'autres si hautement compatibles.
            
            Génère obligatoirement une réponse structurée selon le schéma JSON dicté.
            Pour chaque culture évaluée, fournis un score de compatibilité (ex: "85%") et une justification agronomique claire basée sur les métriques reçues.
            """
            contenu_requete.append(prompt)

            # Schéma JSON strict pour la structure des recommandations de culture
            schema_prediction = {
                "type": "OBJECT",
                "properties": {
                    "analyse_environnementale_synthese": {
                        "type": "STRING", 
                        "description": "Synthèse globale de la qualité du terrain détectée d'après les chiffres."
                    },
                    "recommandations": {
                        "type": "ARRAY",
                        "description": "Liste des cultures évaluées classées de la plus compatible à la moins compatible",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "culture": {"type": "STRING", "description": "Nom du fruit ou légume (ex: Ananas)"},
                                "score_compatibilite": {"type": "STRING", "description": "Pourcentage estimé de réussite (ex: 90%)"},
                                "justification": {"type": "STRING", "description": "Explication de la note selon le pH, la température ou l'humidité."}
                            },
                            "required": ["culture", "score_compatibilite", "justification"]
                        }
                    }
                },
                "required": ["analyse_environnementale_synthese", "recommandations"]
            }

            # Appel à l'API Gemini
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contenu_requete,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_prediction,
                    temperature=0.2
                )
            )
            
            prediction_json = json.loads(response.text)
            
            return {
                "succes": true,
                "mode_evaluation": mode_analyse,
                "fichier_sol_analyse": os.path.basename(chemin_sol) if chemin_sol else "Aucun",
                "predictions_output": prediction_json
            }

        except Exception as e:
            return {"succes": False, "error": f"Erreur lors du calcul prédictif : {str(e)}"}