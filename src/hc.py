# Hypercaster startup
# When REST API is not necessary or used, start Hypercaster only.
#
import logging
import coloredlogs

import emitpy
from emitpy.broadcast import Hypercaster

# #########################
# COLORFUL LOGGING
#
logging.basicConfig(level=logging.DEBUG)
logging.addLevelName(5, "spam")

coloredlogs.DEFAULT_FIELD_STYLES["levelname"] = {"color": "blue"}
coloredlogs.DEFAULT_FIELD_STYLES["name"] = {"color": "white", "bold": False, "bright": True}
coloredlogs.DEFAULT_FIELD_STYLES["asctime"] = {"color": 60, "bold": False, "bright": False}
coloredlogs.DEFAULT_FIELD_STYLES["name"] = {"color": 120, "bold": False, "bright": True}

coloredlogs.DEFAULT_LEVEL_STYLES["spam"] = {"color": "red"}
coloredlogs.DEFAULT_LEVEL_STYLES["info"] = {"color": 159, "bright": True}
coloredlogs.DEFAULT_LEVEL_STYLES["debug"] = {"color": "white"}  # , "faint": True

logger = logging.getLogger("Hypercaster")
coloredlogs.install(level=logging.DEBUG, logger=logger, fmt="%(asctime)s %(name)s:%(message)s", datefmt="%H:%M:%S")



logger.info(f"{emitpy.__NAME__} {emitpy.__COPYRIGHT__}")
logger.info(f"Release {emitpy.__version__} «{emitpy.__version_name__}»")
logger.info(f"Usable under Licence {emitpy.__LICENSE__} {emitpy.__LICENSEURL__}")


hypercaster = None
try:
    logger.info("starting Hypercaster..")
    hypercaster = Hypercaster()  # blocks inside Hypercaster
    logger.info("..started")
except KeyboardInterrupt:
    logger.info("Stopping Hypercaster..")
    if hypercaster is not None:
        hypercaster.shutdown()
    logger.info("..stopped")
