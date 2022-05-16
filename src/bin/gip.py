import json
import jsonpath

class GIP:

    def __init__(self, queues):
        self.queues = queues
        try:
            self.redis = redis.Redis(**REDIS_CONNECT)
            self.redis.ping()
        except:
            logger.error(":init: no redis")
            return

        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(self.queues)


    def process(self, queue, msg):
        pass


    def listen(self):
        # {'type': 'psubscribe', 'pattern': None, 'channel': b'emitpy:*', 'data': 1}
        for message in self.pubsub.listen():
            # logger.debug(f":listen: received {message}")
            msg = message["data"]
            channel = message["channel"]
            if type(msg) == bytes:
                msg = msg.decode('UTF-8')
            if type(channel) == bytes:
                channel = channel.decode('UTF-8')
            self.process(channel, msg)


gip = Gip()
gip.listen()

# Info: What we save and how:
#
# 1. Aircraft
# aircrafts:adsb:abcdef -> data
# aircrafts:reg:A7PMA -> named position (runway, taxiway, parking, airway...)

# airport:named_position:A7PMA -> data
#
#
# 2. Service vehicle
# vehicle:adsb:abcdef -> data
# vehicle:CAT001 -> named position (runway, taxiway, parking, airway...)
#
# airport:named_position:CAT001 -> data
#
# 3. Admin
#
# Flight board
# airport:arrival:QR195 -> flight info
# airport:departure:QR196 -> flight info
#
# TMO
# airport:final:A7PMA -> data
#
# Taxi
# airport:taxiin:A7PMA -> data
# airport:taxiout:A7PMA -> data
#
# OOOI
# airport:oooi:{off,on,out,in} -> data
#
# New ETA
# airport:{arrival|departure}:QR195:{ETA|ETD}:date-received -> data
#
#
