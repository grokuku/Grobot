#### Fichier : app/database/redis_session.py
import redis
from app.config import settings # Nous utilisons le config existant pour les paramètres

# Création d'un pool de connexions Redis. C'est la manière la plus efficace
# de gérer les connexions dans une application web.
# L'URL est construite à partir de votre configuration existante.
redis_pool = redis.ConnectionPool.from_url(settings.REDIS_URL, decode_responses=True)

def get_redis():
    """
    FastAPI dependency that provides a Redis client from the connection pool.
    """
    # 'decode_responses=True' assure que les données lues depuis Redis
    # sont automatiquement décodées en strings Python (utf-8).
    redis_client = redis.Redis(connection_pool=redis_pool)
    try:
        yield redis_client
    finally:
        # Contrairement à une DB, les clients Redis gèrent la connexion via le pool,
        # il n'est généralement pas nécessaire de les fermer explicitement ici.
        pass