import os
import shutil
from google import genai
from PIL import Image, ImageChops, ImageStat

class AgriSenseIAService:
    def __init__(self, api_key: str = None):
        self.client = genai.Client(api_key="AIzaSyBaj0tXKfyJc1PxijLJFT7l9gKLgEhokLg")
        self.model_name = "gemini-2.5-flash"
        
        # Fichiers de persistance locales
        self.chemin_image_sauvegarde = "derniere_capture.jpg"
        self.chemin_statut_sauvegarde = "dernier_statut.txt"

    def _lire_dernier_statut(self) -> str:
        """Lit le dernier statut enregistré. Renvoie 'Normal' par défaut."""
        if os.path.exists(self.chemin_statut_sauvegarde):
            with open(self.chemin_statut_sauvegarde, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "Normal"

    def _sauvegarder_statut(self, statut: str):
        """Enregistre le statut actuel pour le prochain cycle."""
        with open(self.chemin_statut_sauvegarde, "w", encoding="utf-8") as f:
            f.write(statut)

    def _evaluer_changement_reel(self, chemin_actuelle: str, seuil: float = 2.0) -> bool:
        """Compare l'image actuelle avec la dernière capture."""
        if not os.path.exists(self.chemin_image_sauvegarde):
            print("[Info] Première capture absolue. Analyse forcée.")
            return True
            
        img1 = Image.open(chemin_actuelle).convert('RGB')
        img2 = Image.open(self.chemin_image_sauvegarde).convert('RGB')
        img2 = img2.resize(img1.size)
        
        diff = ImageChops.difference(img1, img2)
        stat = ImageStat.Stat(diff)
        moyenne_diff = sum(stat.mean) / 3.0
        
        return moyenne_diff > seuil

    def analyser_evolution_champ(self, chemin_image_actuelle: str, dossier_references: str = None) -> dict:
        try:
            # 1. Récupération AUTOMATIQUE du statut précédent en mémoire
            statut_precedent = self._lire_dernier_statut()
            print(f"[Mémoire] Statut de la période précédente : {statut_precedent}")
            
            # 2. Évaluation du changement de pixels
            a_change = self._evaluer_changement_reel(chemin_image_actuelle)
            
            # --- LOGIQUE DE SÉCURITÉ AUTOMATIQUE ---
            if not a_change and statut_precedent == "Normal":
                shutil.copy(chemin_image_actuelle, self.chemin_image_sauvegarde)
                return {
                    "analyse_requise": False,
                    "statut": "Normal",
                    "message": "Plante stable et saine. Requête IA économisée."
                }
            
            if not a_change and statut_precedent != "Normal":
                print("[Sécurité] Aucun changement de pixel, mais la plante est déjà malade. Ré-analyse IA forcée pour suivi.")

            # --- RECONSTRUCTION DE LA REQUÊTE POUR L'IA ---
            contenu_requete = []
            
            # Injection des images de référence étiquetées
            if dossier_references and os.path.exists(dossier_references):
                extensions = ('.jpg', '.jpeg', '.png')
                fichiers = [f for f in os.listdir(dossier_references) if f.lower().endswith(extensions)]
                
                if fichiers:
                    contenu_requete.append("--- IMAGES DE RÉFÉRENCE DE SÉCURITÉ (ETAT IDÉAL ET SAIN EXIGÉ) ---")
                    for f in fichiers[:3]:
                        contenu_requete.append(f"Fichier référence : {f}")
                        contenu_requete.append(Image.open(os.path.join(dossier_references, f)))
                    contenu_requete.append("--- FIN DES IMAGES DE RÉFÉRENCE ---")

            # Injection de l'image actuelle du champ
            contenu_requete.append("--- IMAGE ACTUELLE DU CHAMP À ANALYSER CRITIQUEMENT ---")
            contenu_requete.append(Image.open(chemin_image_actuelle))
            
            # Prompt durci et ultra-directif
            prompt = """
            Tu es l'expert phytosanitaire et agronome en chef du système AgriSense. 
            Ton rôle est de détecter sans complaisance la moindre anomalie sur l'IMAGE ACTUELLE DU CHAMP.

            CONSIGNES D'ANALYSE TRÈS STRICTES :
            1. Compare l'IMAGE ACTUELLE avec les IMAGES DE RÉFÉRENCE saines fournies.
            2. Si l'image actuelle présente des taches (brunes, noires, jaunes), des trous, des flétrissements, des feuilles qui pendent ou une couleur jaunie/pâle par rapport aux références, la plante est MALADE ou STRESSÉE. 
            3. Il est STRICTEMENT INTERDIT de répondre 'Plante Saine' ou 'RAS' si la feuille inspectée est visiblement endommagée, tachée ou flétrie.

            Format de réponse attendu (STRICT, court, en français pour écran mobile) :
            🚨 [DIAGNOSTIC : Écris ici le nom de la maladie ou du problème d'irrigation, ou 'Plante Saine' si aucun défaut]
            - **Statut général :** [Moyen ou Critique - Ne mets SURTOUT PAS 'Normal' s'il y a un défaut]
            - **Diagnostic Irrigation :** [Sol sec / Humidité correcte / Excès d'eau / Flétrissement visible]
            - **Diagnostic Santé :** [Décris ici précisément les taches ou anomalies observées sur la feuille]
            
            🛠️ ACTIONS SUGGÉRÉES :
            1. [Action urgente 1]
            2. [Action urgente 2]
            """
            
            contenu_requete.append(prompt)

            # Appel API
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contenu_requete
            )
            
            texte_reponse = response.text
            
            # Détection du statut pour la persistance locale
            nouveau_statut = "Normal"
            if "Critique" in texte_reponse or "CRITIQUE" in texte_reponse:
                nouveau_statut = "Critique"
            elif "Moyen" in texte_reponse or "MOYEN" in texte_reponse:
                nouveau_statut = "Moyen"
            elif "Plante Saine" not in texte_reponse and "RAS" not in texte_reponse:
                nouveau_statut = "Moyen"

            # Sauvegarde de l'état sur le disque
            shutil.copy(chemin_image_actuelle, self.chemin_image_sauvegarde)
            self._sauvegarder_statut(nouveau_statut)
            print(f"[Mémoire] Nouveau statut '{nouveau_statut}' enregistré pour le prochain cycle.")

            return {
                "analyse_requise": True,
                "statut": nouveau_statut,
                "resultat": texte_reponse
            }

        except Exception as e:
            return {"error": f"Erreur lors de l'analyse : {str(e)}"}

# --- Bloc de test autonome ---
if __name__ == "__main__":
    # Pense à nettoyer ton fichier "dernier_statut.txt" avant de re-tester la photo malade !
    service_ia = AgriSenseIAService(api_key="AIzaSyBaj0tXKfyJc1PxijLJFT7l9gKLgEhokLg")
    
    print("--- Lancement de la supervision AgriSense ---")
    analyse = service_ia.analyser_evolution_champ(
        chemin_image_actuelle="capteur_champ.jpg", 
        dossier_references="references"
    )
    
    if analyse.get("analyse_requise"):
        print(analyse["resultat"])
    else:
        print(analyse.get("message") or analyse.get("error"))