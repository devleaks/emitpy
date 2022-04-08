from emitpy.business import Airline
from emitpy.emit import HyperCaster

# from emitpy.emit import Broadcaster
# One queue only
# QUEUE_NAME="lt"
# b = Broadcaster(QUEUE_NAME)
# b.broadcast()

h = HyperCaster()
h.run()