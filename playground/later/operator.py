"""
An Operator is a compagny that organizes transports (also called movements.)
"""

class Operator:

    def __init__(self, name: str, locations: [Location], fleet: [Carrier]):
        self.locations = locations
        self.fleet = fleet
