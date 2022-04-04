import redis
import logging
import threading
import websockets
import asyncio


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Reader")


CONNECTIONS =  set()


class Reader:

    def __init__(self, name: str):
        self.name = name
        self.redis = redis.Redis()
        self.pubsub = self.redis.pubsub()
        self.pubsub.subscribe(self.name)

        self.connections = set()

        self._wsserver = websockets.serve(self.message_control, 'localhost', 8051)
        self.thread = threading.Thread(target=self.run)
        self.thread.start()
        self.wsserver()

    async def register(self, websocket):
        logger.debug(":register: client added")
        self.connections.add(websocket)

    async def unregister(self, websocket):
        logger.debug(":unregister: client removed")
        self.connections.remove(websocket)

    async def notify_users(self, message, websocket):
        connection_list = []
        for connection in self.connections:
            if connection != websocket:
                connection_list.append(connection)

        logger.debug(f":notify_users: notify {len(connection_list)} clients {message}")
        await asyncio.wait([
            connection.send(message) for connection in connection_list
        ])

    async def message_control(self, websocket, path):
        await self.register(websocket)

    def wsserver(self):
        asyncio.get_event_loop().run_until_complete(self._wsserver)
        asyncio.get_event_loop().run_forever()


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
        logger.debug(f":forward: {msg}")
        self.notify_users(msg, None)

r = Reader("lt")