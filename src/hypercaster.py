from emitpy.business import Airline
from emitpy.emit import Broadcaster, HyperCaster

# One queue only
QUEUE_NAME="lt"
# b = Broadcaster(QUEUE_NAME)
# b.broadcast()

h = HyperCaster()
h.run()