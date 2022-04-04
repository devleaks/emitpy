import redis
import logging
import threading

from simple_websocket_server import WebSocketServer, WebSocket


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Reader")


clients = []

class SimpleChat(WebSocket):
    def handle(self):
        pass

    def connected(self):
        logger.debug(f":connected: {self.address} connected")
        for client in clients:
            client.send_message(self.address[0] + u' - connected')
        clients.append(self)

    def handle_close(self):
        clients.remove(self)
        logger.debug(f":connected: {self.address} closed")
        for client in clients:
            client.send_message(self.address[0] + u' - disconnected')


class Reader:

    def __init__(self, name: str):
        self.name = name
        self.redis = redis.Redis()
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(self.name)

        self.connections = set()

        self._wsserver = WebSocketServer('localhost', 8051, SimpleChat)
        print(self._wsserver)
        self.thread = threading.Thread(target=self.run)
        self.thread.start()
        self._wsserver.serve_forever()

    def run(self):
        logger.debug(f":run: listening on {self.name}..")
        for message in self.pubsub.listen():
            # logger.debug(f":run: received {message}")
            msg = message["data"]
            if type(msg) == bytes:
                msg = msg.decode('UTF-8')
                logger.debug(f":run: got {msg}")
                self.forward(msg)

    def forward(self, msg):
        # shoud do some check to not forward redis internal messages
        logger.debug(f":forward: {msg} ..")
        for client in clients:
            client.send_message(msg)
        logger.debug(f":forward: .. done")


r = Reader("viewapp")