import redis
import logging
import threading
import json

from datetime import datetime
from simple_websocket_server import WebSocketServer, WebSocket


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WSForwarder")

WSS_HOST = "localhost"
WSS_PORT = 8051

QUIT_MSG = "quit"


class WSHandler(WebSocket):
    """
    Basic, minimalistic websocket server handler. Accept connection and disconnection,
    keep track of connected client in CLIENTS class attribute.
    """
    CLIENTS = []
    NOTIFY  = False
    WIRE    = True

    def handle(self):
        pass

    def connected(self):
        logger.debug(f":connected: {self.address} connected")
        if WSHandler.NOTIFY:
            for client in WSHandler.CLIENTS:
                client.send_message(self.address[0] + u' - connected')
        WSHandler.CLIENTS.append(self)
        if WSHandler.WIRE:
            self.send_message(u"" + self.status_message("connected"))

    def handle_close(self):
        WSHandler.CLIENTS.remove(self)
        logger.debug(f":handle_close: {self.address} closed")
        if WSHandler.NOTIFY:
            for client in WSHandler.CLIENTS:
                client.send_message(self.address[0] + u' - disconnected')

    def status_message(self, msg):
        return json.dumps({
            "source": "EMITPY",
            "topic": "aodb/wire",
            "type": "wire",
            "timestamp": datetime.now().isoformat(),
            "payload": {
                "source": "emitpy",
                "type": "news",
                "subject": "Websocket connection",
                "body": msg,
                "created_at": datetime.now().isoformat(),
                "priority": 3,
                "icon": "la-info",
                "icon-color": "info"
            }
        })


class WSForwarder:

    def __init__(self, queue_names):
        self.queue_names = queue_names if type(queue_names).__name__ == "list" else [queue_names]

        self.redis = redis.Redis()
        self.pubsub = self.redis.pubsub()
        self._wsserver = WebSocketServer(WSS_HOST, WSS_PORT, WSHandler)

        for queue in self.queue_names:
            self.thread = threading.Thread(target=self._forward, args=(queue,))
            self.thread.start()

    def run(self):
        logger.info(f":run: listening for websockets..")
        self._wsserver.serve_forever()
        logger.debug(f":run: done listening for websockets")

    def _forward(self, name):
        self.pubsub.subscribe(name)
        logger.info(f":_forward: {name}: listening..")
        for message in self.pubsub.listen():
            # logger.debug(f":run: received {message}")
            msg = message["data"]
            if type(msg) == bytes:
                msg = msg.decode("UTF-8")
                logger.debug(f":_forward: {name}: got {msg}")
                if msg == QUIT_MSG:
                    logger.info(f":_forward: {name}: quitting..")
                    self.pubsub.unsubscribe(name)
                    logger.debug(f":_forward: {name}: ..done")
                    return
                # logger.debug(f":forward: {msg} ..")
                for client in WSHandler.CLIENTS:
                    # logger.debug(f":forward: forwarding to {client.address[0]} ..")
                    client.send_message(msg)
            else:
                logger.debug(f":_forward: got non bytes message {msg}")

    def terminate_all(self):
        self._wsserver.close()
        logger.info(f":terminate_all: web server terminated")
        for queue in self.queue_names:
            logger.info(f":terminate_all: notifying {queue}")
            self.redis.publish(queue, QUIT_MSG)


try:
    r = WSForwarder(["viewapp"])
    logger.debug(f"WSForwarder: inited, starting..")
    r.run()
except KeyboardInterrupt:
    logger.warning(f"WSForwarder: quitting..")
    r.terminate_all()
finally:
    logger.warning(f"WSForwarder: ..bye")
