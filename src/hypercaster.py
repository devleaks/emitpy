from entity.business import Airline
from entity.emit import Broadcaster, HyperCaster

# One queue only
QUEUE_NAME="lt"
# b = Broadcaster(QUEUE_NAME)
# b.broadcast()

h = HyperCaster()
h.run()