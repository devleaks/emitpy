import logging
from datetime import datetime

from entity.emit import Emit

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("mkEmit")


def main():

    ae = Emit()
    ae.load("QR196-S202201181200")
    ae.emit()
    ae.save()
    # f = ae.get("TOUCH_DOWN", datetime.now())

    # metar may change between the two
    # managed.setMETAR(metar=metar)  # calls prepareRunways()
    # dm = Movement.create(dep, managed)
    # dm.make()
    # dm.save()

    # de = Emit(am)
    # de.emit()
    # de.save()

    # f = ae.get("TAKE_OFF", datetime.now())

    logger.debug("..done")

main()
