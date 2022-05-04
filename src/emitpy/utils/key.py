from emitpy.constants import ID_SEP


def make_key(database: str, name: str, extension: str = None):
    if extension is None:
        return key_path(database, name)
    return key_path(database, name, extension)


def key_path(*args):
    a = map(lambda x: x if x is not None else "", args)
    return ID_SEP.join(a)