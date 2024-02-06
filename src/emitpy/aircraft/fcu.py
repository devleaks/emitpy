from emitpy.aircraft import AircraftTypeWithPerformance


class FCU:
    """
    The Flight control unit of an aircraft.
    """

    def __init__(self, acperf: AircraftTypeWithPerformance):
        """
        The FCU.

        """
        self.acperf = acperf

        self.flight_phase = "READY"

        self.course = 0.0

        self.speed = 0.0
        self.vertical_speed = 0.0

        self.altitude = 0.0

        self.target_speed = 0.0
        self.target_alt = 0.0
        self.target_course = 0.0
        self.target_vspeed = 0.0

        self.speed_managed = False
        self.vert_nav_managed = False
        self.lat_nav_managed = False

    def set_speed(self, speed: float):
        self.target_speed = speed
        self.lat_nav_managed = False

    def set_course(self, course: float):
        self.target_course = course
        self.lat_nav_managed = False

    def set_alt(self, alt: float):
        self.target_alt = alt
        self.vert_nav_managed = False

    def set_vspeed(self, vspeed: float, alt: float = None):
        self.target_vspeed = vspeed
        self.vert_nav_managed = False

    def set_speed_managed(self):
        self.speed_managed = True

    def set_course_managed(self):
        self.lat_nav_managed = True

    def set_altitude_managed(self):
        self.vert_nav_managed = True
