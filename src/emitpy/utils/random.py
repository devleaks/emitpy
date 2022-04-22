import random

ponctuality = {
    "early": 10,
    "ontime": 50,
    "late": 40
}

ontime_margins = [-10, 15]
earliest = 30
latest = 45

def randomFlightDelay(flight: "Flight"):
    """
    Function to adjust flight estimated time based on statistical input and/or randomness.
    Return delays in seconds.

    :param      flight:  The flight
    :type       flight:  { type_description }
    """
    how = random.choices(ponctuality.keys(), weights=ponctuality.values())
    delay = 0
    if how == "early":
        delay = ontime_margins[0] - random.range(earliest)
    elif how == "delay":
        delay = ontime_margins[1] + random.range(latests)
    else
        delay_range = ontime_margins[1] - ontime_margins[0]
        delay = 0 + ontime_margins[0] + random.range(delay_range)
    return delay * 60


def randomServiceDelay(service: "Service"):
    """
    Returns a random service delay in seconds, to be used to delay arrival time at service position.

    :param      service:  The service
    :type       service:  { type_description }
    """
    return random.range(15) * 60


def randomServicePause(service: "Service", short: bool = True):
    """
    Returns a random service delay in seconds, to be used to delay service after service.

    :param      service:  The service
    :type       service:  { type_description }
    """
    wait = 6 if short else 30  # minutes
    return random.range(wait) * 60


def randomServiceDuration(service: "Service"):
    duration = service.duration()
    variable = int(duration * 0.1)
    return duration - variable + random.range(2 * variable)