"""
A Ground Support Equipment Profile is a list of identiied Feature<Point>.
Each Point determine where a specific service vehicle has to stop close to the aircraft.
"""

class GSEProfile:

    def __init__(self, data):
        self.rawdata = data
        self.service_pois = {}


    def getServicePOIs(self):
        return self.service_pois


    def make(self, ramp: "Ramp"):
        # Get position (center of ramp)
        # Get orientation
        # Compute all service points in profile, name them, cache them.
        # Return all service points or None if ramp has insuficient information.
        pass

