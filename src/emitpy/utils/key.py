from emitpy.constants import ID_SEP
from redis.commands.json.path import Path

def key_path(*args):
    a = map(lambda x: x if x is not None else "", args)
    return ID_SEP.join(a)


def rejson(redis, key: str, db: int = 0, path: str = None):
    if db != 0:
        prevdb = redis.client_info()["db"]
        redis.select(db)
    if path is None:
        ret = redis.json().get(key)
    else:
        ret = redis.json().get(key, Path(path))
    if db != 0:
        redis.select(prevdb)
    return ret

def rejson_keys(redis, key_pattern: str, db: int = 0):
    if db != 0:
        prevdb = redis.client_info()["db"]
        redis.select(db)
    ret = redis.keys(key_pattern)
    if db != 0:
        redis.select(prevdb)
    return ret