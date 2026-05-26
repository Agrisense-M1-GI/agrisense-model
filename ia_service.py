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
        self.client = genai.Client(api_key="AIzaSyAq067XHQKTVTVFeMN2y3gPsHAwEMq1XKo")
        self.model_name = "gemini-2.5-flash"
        
        # Fichiers de persistance pour l'algorithme local et le suivi d'état
        self.chemin_image_sauvegarde = "derniere_capture.jpg"
        self.chemin_statut_sauvegarde = "dernier_statut.txt"

    def _recuperer_image_recente(self, dossier_backend: str) -> str:
        """Scane le dossier du backend et retourne le chemin de l'image la plus récente (via timestamp)."""
        extensions = ('*.jpg', '*.jpeg', '*.png')
        fichiers = []
        for ext in extensions:
            fichiers.extend(glob.glob(os.path.join(dossier_backend, ext)))
        
        if not fichiers:
            return None
            
        # Tri des fichiers du plus récent au plus ancien
        fichiers.sort(key=os.path.getmtime, reverse=True)
        return fichiers[0]

    def _optimiser_image(self, chemin_image: str, max_taille=(800, 800)) -> Image.Image:
        """Redimensionne l'image à la volée pour diviser par 4 la consommation de tokens."""
        img = Image.open(chemin_image).convert('RGB')
        img.thumbnail(max_taille, Image.Resampling.LANCZOS)
        return img

    def _lire_dernier_statut(self) -> str:
        """Récupère le dernier statut de santé connu de la plante en mémoire locale."""
        if os.path.exists(self.chemin_statut_sauvegarde):
            with open(self.chemin_statut_sauvegarde, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "Normal"

    def _sauvegarder_statut(self, statut: str):
        """Sauvegarde le nouveau statut pour sécuriser le prochain cycle d'analyse."""
        with open(self.chemin_statut_sauvegarde, "w", encoding="utf-8") as f:
            f.write(statut)

    def _evaluer_changement_reel(self, chemin_actuelle: str, seuil: float = 2.0) -> bool:
        """Compare mathématiquement les pixels de l'image actuelle avec la dernière analysée."""
        if not os.path.exists(self.chemin_image_sauvegarde):
            return True # Pas d'historique, analyse obligatoire
            
        img1 = Image.open(chemin_actuelle).convert('RGB')
        img2 = Image.open(self.chemin_image_sauvegarde).convert('RGB')
        img2 = img2.resize(img1.size)
        
        diff = ImageChops.difference(img1, img2)
        stat = ImageStat.Stat(diff)
        moyenne_diff = sum(stat.mean) / 3.0
        
        return moyenne_diff > seuil

    def executer_analyse_vers_json(self, dossier_backend: str, culture_cible: str) -> dict:
        """
        Exécute la chaîne complète d'analyse (Filtre local -> Analyse IA Contextuelle).
        Retourne un dictionnaire structuré au format JSON pour le Backend.
        """
        try:
            # 1. Détection et récupération de la photo du capteur
            chemin_actuelle = self._recuperer_image_recente(dossier_backend)
            if not chemin_actuelle:
                return {"succes": False, "error": "Aucune image trouvée dans le dossier du backend."}
                
            statut_precedent = self._lire_dernier_statut()
            
            # 2. Vérification par le filtre de pixels local léger
            a_change = self._evaluer_changement_reel(chemin_actuelle)
            
            # --- Sécurité Anticrise ---
            # Si aucun changement de pixel ET que la plante était saine (Normal), on économise l'API.
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
            
            if not a_change and statut_precedent != "Normal":
                print(f"[Sécurité] Pixels stables, mais statut précédent '{statut_precedent}'. Suivi IA forcé.")

            # 3. Préparation des données optimisées pour l'API
            img_analyse = self._optimiser_image(chemin_actuelle)
            
            contenu_requete = [
                f"Culture ciblée dans ce champ : {culture_cible}",
                f"Statut sanitaire lors de l'analyse précédente : {statut_precedent}",
                "Image actuelle du champ à inspecter :",
                img_analyse
            ]
            
            prompt = """
            Tu es l'expert en vision par ordinateur et agronomie pour AgriSense. 
            Analyse l'image de la plante (culture ciblée fournie) et détecte toute anomalie (taches, chlorose, nécrose, flétrissement).
            
            Tu dois obligatoirement formuler ta réponse en respectant la structure JSON demandée.
            Si la plante a le moindre défaut visuel (même un stress léger), le champ 'statut_general' ne peut pas être 'Normal'.
            """
            contenu_requete.append(prompt)

            # 4. Définition du schéma JSON strict pour éviter les bugs de structure
            schema_json = {
                "type": "OBJECT",
                "properties": {
                    "diagnostic_titre": {"type": "STRING", "description": "Nom précis de la maladie/stress détecté ou 'Plante Saine'"},
                    "statut_general": {"type": "STRING", "description": "Doit être strictly unique : 'Normal', 'Moyen' ou 'Critique'"},
                    "diagnostic_sante": {"type": "STRING", "description": "Description technique et très brève des symptômes visibles observés"},
                    "actions_suggerees": {
                        "type": "ARRAY",
                        "items": {"type": "STRING"},
                        "description": "Liste de 2 actions physiques correctives immédiates à afficher à l'utilisateur"
                    }
                },
                "required": ["diagnostic_titre", "statut_general", "diagnostic_sante", "actions_suggerees"]
            }

            # 5. Appel de l'API Gemini avec Structured Outputs
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contenu_requete,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=schema_json,
                    temperature=0.1
                )
            )
            
            # Conversion de la réponse texte de l'IA en dictionnaire Python (JSON)
            resultat_ia_json = json.loads(response.text)
            
            # 6. Sauvegarde des états locaux pour la mémoire du prochain cycle
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