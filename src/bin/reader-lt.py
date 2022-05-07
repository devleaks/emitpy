import redis
import logging
import threading
import sys
import socket
import time

from datetime import datetime

from emitpy.parameters import REDIS_CONNECT

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("LiveTrafficForwarder")

WSS_HOST = "Mac-mini-de-Pierre.local"
WSS_PORT = 49003

QUIT_MSG = "quit"


class LiveTrafficForwarder:

    def __init__(self, queue_names):
        self.queue_names = queue_names if type(queue_names).__name__ == "list" else [queue_names]

        self.redis = redis.Redis(**REDIS_CONNECT)
        self.pubsub = self.redis.pubsub()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        for queue in self.queue_names:
            self.thread = threading.Thread(target=self._forward, args=(queue,))
            self.thread.start()

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
    def send_traffic_data(self, ln: str) -> int:
        fields = ln.split(',')
        if len(fields) != 15:
            logger.warning(f"Found {len(fields)} fields, expected 15, in line {ln}")
            return 1
        # Update and wait for timestamp
        # fields[14] = compWaitTS(fields[14])
        datagram = ','.join(fields)
        self.sock.sendto(datagram.encode('ascii'), (WSS_HOST, WSS_PORT))
        fields[1] = f"{int(fields[1]):x}"
        logger.debug(f"{datagram}")
        logger.debug(f":send_traffic_data: ac:{fields[1]}: alt={fields[4]} ft, hdg={fields[7]}, speed={fields[8]} kn, vspeed={fields[5]} ft/min")
        return 0

    def _forward(self, name):
        self.pubsub.subscribe(name)
        logger.info(f":_forward: {name}: listening..")
        for message in self.pubsub.listen():
            # logger.debug(f":run: received {message}")
            msg = message["data"]
            if type(msg) == bytes:
                msg = msg.decode("UTF-8")
                # logger.debug(f":_forward: {name}: got {msg}")
                if msg == QUIT_MSG:
                    logger.info(f":_forward: {name}: quitting..")
                    self.pubsub.unsubscribe(name)
                    logger.debug(f":_forward: {name}: ..done")
                    return
                # logger.debug(f":forward: {msg} ..")
                r = self.send_traffic_data(msg)
                if r != 0:
                    logger.warning(f":_forward: returned issue")
            else:
                logger.debug(f":_forward: got non bytes message {msg}")

    def terminate_all(self):
        for queue in self.queue_names:
            logger.info(f":terminate_all: notifying {queue}")
            self.redis.publish(queue, QUIT_MSG)

logger.info(f"it is now {datetime.now()}, {datetime.now().timestamp()}")
r = LiveTrafficForwarder(["lt"])


# try:
#     r = LiveTrafficForwarder(["lt"])
#     logger.debug(f"LiveTrafficForwarder: inited, starting..")
# except KeyboardInterrupt:
#     logger.warning(f"LiveTrafficForwarder: quitting..")
#     r.terminate_all()
# finally:
#     logger.warning(f"LiveTrafficForwarder: ..bye")
