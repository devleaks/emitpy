import logging
import socket
from datetime import datetime

from emitpy.parameters import XPLANE_HOSTNAME, XPLANE_PORT
from .broadcaster import Broadcaster

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("LiveTrafficForwarder")


class LiveTrafficForwarder(Broadcaster):

    def __init__(self, redis, name: str, speed: float = 1, starttime: datetime = None):
        Broadcaster.__init__(self, redis=redis, name=name, speed=speed, starttime=starttime)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # def compWaitTS(ts_s: str) -> str:
    #     global _tsDiff
    #     # current time and convert timestamp
    #     now = int(time.time())
    #     ts = int(ts_s)
    #     # First time called? -> compute initial timestamp difference
    #     if not _tsDiff:
    #         _tsDiff = now - ts - args.bufPeriod
    #         if args.verbose:
    #             print ("Timestamp difference: {}".format(_tsDiff))
    #     # What's the required timestamp to wait for and then return?
    #     ts += _tsDiff
    #     # if that's in the future then wait
    #     if (ts > now):
    #         if args.verbose:
    #             print ("Waiting for {} seconds...".format(ts-now), end='\r')
    #         time.sleep (ts-now)
    #     # Adjust returned timestamp value for historic timestamp
    #     ts -= args.historic
    #     return str(ts)

    def send_data(self, data: str) -> int:
        fields = data.split(',')
        if len(fields) != 15:
            logger.warning(f"Found {len(fields)} fields, expected 15, in line {data}")
            return 1
        # Update and wait for timestamp
        # fields[14] = compWaitTS(fields[14])
        datagram = ','.join(fields)
        self.sock.sendto(datagram.encode('ascii'), (XPLANE_HOSTNAME, XPLANE_PORT))
        fields[1] = f"{int(fields[1]):x}"
        logger.debug(f"{datagram}")
        logger.debug(f":send_data: ac:{fields[1]}: alt={fields[4]} ft, hdg={fields[7]}, speed={fields[8]} kn, vspeed={fields[5]} ft/min")
        return 0
