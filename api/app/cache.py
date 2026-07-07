"""Cache TTL en mémoire pour les réponses d'endpoints.

Les marts ne changent qu'au run quotidien du DAG : un TTL de 10 minutes
suffit largement et absorbe les rafales du frontend (filtres interactifs).
Clé = nom de fonction + arguments. Taille bornée (LRU grossier).
"""

import time
from functools import wraps

TTL_SECONDES = 600
MAX_ENTREES = 512

_store: dict[tuple, tuple[float, object]] = {}


def ttl_cache(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        cle = (fn.__qualname__, args, tuple(sorted(kwargs.items())))
        maintenant = time.monotonic()
        hit = _store.get(cle)
        if hit and maintenant - hit[0] < TTL_SECONDES:
            return hit[1]
        resultat = fn(*args, **kwargs)
        if len(_store) >= MAX_ENTREES:  # éviction grossière : on purge les expirés, sinon tout
            expirees = [k for k, (t, _) in _store.items() if maintenant - t >= TTL_SECONDES]
            for k in expirees or list(_store):
                _store.pop(k, None)
        _store[cle] = (maintenant, resultat)
        return resultat

    return wrapper


def vider() -> None:
    _store.clear()
