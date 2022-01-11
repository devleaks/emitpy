
class Info:
    """
    Helper class dictionary to add info to entities.
    Current classes using Info:
      - Flight

    """
    def __init__(self, info: object = {}):
        self._info = info

    def set_info(self, name: str, value: object):
        self._info[name] = value

    def get_info(self, name: str):
        return self._info[name] if name in self._info else None
