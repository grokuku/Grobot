from app.database.sql_session import SessionLocal
from app.database.sql_models import GlobalSettings

# Connexion à la DB
db = SessionLocal()
settings = db.query(GlobalSettings).first()

# Si la config n'existe pas, on la crée (sécurité)
if not settings:
    settings = GlobalSettings()
    db.add(settings)

# Injection de la clé (remplacez la valeur ci-dessous !)
VOTRE_CLE = 'sk-017a5557f82b458baa86182073a0bd72' 

# Mise à jour des 3 catégories
settings.decisional_llm_api_key = VOTRE_CLE
settings.tools_llm_api_key = VOTRE_CLE
settings.output_client_llm_api_key = VOTRE_CLE

# Sauvegarde
db.commit()
print(f"Succès ! Clés mises à jour. ID settings: {settings.id}")
print(f"Clé stockée (vérification partielle) : {settings.tools_llm_api_key[:5]}...")
exit()