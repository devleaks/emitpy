from datetime import datetime, timedelta
import logging

logger = logging.getLogger("Metar")

try:
    from urllib2 import urlopen
except:
    from urllib.request import urlopen
from metar import Metar as MetarLib


from .parameters import METAR_URL

OLD_METAR = 30  # minutes


class Metar:
    """
    Retrieves Metar for supplied airport (ICAO code).
    """

    def __init__(self, icao: str, metar: str = None):
        self.icao = icao
        self.last_updated = None

        if metar is not None:
            self.raw = metar
            try:
                if metar.startswith(self.icao):
                    report = metar.strip()
                    self.raw = metar
                    self.obs = MetarLib.Metar(metar)
                    self.last_updated = datetime.now()
                if not report:
                    logger.warning("No data for %s", self.icao)
            except MetarLib.ParserError as exc:
                logger.error("METAR code: %s", metar)
                logger.error(", ".join(exc.args), "\n")
            except:
                import traceback

                logger.critical(traceback.format_exc())
                logger.critical("Error retrieving %s %s", self.icao, "data")
        else:
            self.update()


    def update(self):
        """
        Updates METAR if old
        """
        if self.last_updated is not None and datetime.now() < (self.last_updated + timedelta(minutes=OLD_METAR)):
            logger.debug("update: METAR up to date")
            return

        line = None
        try:
            url = "%s/%s.TXT" % (METAR_URL, self.icao)
            urlh = urlopen(url)
            report = ""
            for line in urlh:
                if not isinstance(line, str):
                    line = line.decode()  # convert Python3 bytes buffer to string
                if line.startswith(self.icao):
                    report = line.strip()
                    self.raw = line
                    self.obs = MetarLib.Metar(line)
                    self.last_updated = datetime.now()
                    break
            if not report:
                logger.warning("No data for %s", self.icao)
        except MetarLib.ParserError as exc:
            logger.error("METAR code: %s", line)
            logger.error(", ".join(exc.args), "\n")
        except:
            import traceback

            logger.critical(traceback.format_exc())
            logger.critical("Error retrieving %s %s", self.icao, "data")


    def wind(self) -> [float]:
        """
        Get wind direction (in degrees) and speed (in meter per seconds).
        To be used in airport.qfu.

        :returns:   The ground wind.
        :rtype:     { return_type_description }
        """
        if self.obs is None:
            self.update()

        if self.obs is not None:
            return [self.obs.wind_dir.value(), self.obs.wind_speed.value("MPS")]

        return None
