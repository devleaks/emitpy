import logging
import os
import glob
import re
import subprocess

from datetime import datetime

from metar import Metar

from .weather_engine import WeatherEngine, AirportWeather, Wind
from .utils import c, lin_interpol

from emitpy.parameters import XPLANE_DIR, WEATHER_DIR

logger = logging.getLogger("XPWeatherEngine")


# X-Plane specific
REAL_WEATHER_DIR = os.path.join(XPLANE_DIR, "Output", "Real weather")

# Emitpy specific
GFS_WEATHER_DIR = os.path.join(WEATHER_DIR, "gfs")
FLIGHT_WEATHER_DIR = os.path.join(WEATHER_DIR, "flights")


class XPAirportWeather(AirportWeather):
    # Shell class, used to get airport weather information for Emitpy

    def __init__(self, icao: str, moment: datetime | None = None, engine=None, source=None):
        AirportWeather.__init__(self, icao=icao, moment=moment, engine=engine)

        self.type = "METAR"
        self.source = source
        self.source_date = None

        self.init()

    def init(self):
        # Did we cache it?
        ret = self.load()

        if not ret[0]:
            logger.debug(ret[1])

            # 1. Find most appropriate weather (metar) file
            self.find_source_date()
            self.raw = None
            fn = os.path.join(REAL_WEATHER_DIR, self.source)
            metars = open(fn, "r")
            line = metars.readline()
            line = line.strip().rstrip("\n\r")
            while line and self.raw is None:
                # logger.debug("loadFromFile: SCENERY_PACK '%s'", scenery)
                if line.startswith(self.icao):
                    self.raw = line
                    # logger.debug(f"found {self.raw}")
                line = metars.readline()
            metars.close()
            self.save()  # caches it
        else:
            logger.debug("found in cache")

        if self.raw is not None:
            if self.source_date is None:
                self.parsed = Metar.Metar(self.raw, strict=False)
            else:
                self.parsed = Metar.Metar(self.raw, month=self.source_date.month, year=self.source_date.year, strict=False)
        else:
            logger.warning(f"no metar for {self.icao} in file {fn}")
        # if self.parsed is not None:
        #   logger.debug(self.parsed.string())

    def find_source_date(self):
        if self.source is None:
            return
        # /Users/pierre/Developer/oscars/emit/emitpy/data/x-plane/Output/Real weather/metar-2023-07-25-08.00.txt
        m = re.match(r"(.*)metar-(?P<date>[\.\-\d]+).txt", self.source)
        m2 = m.groupdict()
        if "date" in m2:
            datestr = m2["date"]
            if datestr is not None and len(datestr) > 0:
                try:
                    date = datetime.strptime(datestr, "%Y-%m-%d-%H.%M").astimezone()
                    logger.debug(f"metar file dated {date.isoformat()}")
                    self.source_date = date
                except:
                    logger.warning(f"metar file date {datestr} cannot be parsed")

    def summary(self):
        logger.debug(self.getInfo())
        return self.parsed.string()

    def getInfo(self) -> dict:
        """
        Returns weather information.
        """
        return {"source": self.source, "type": self.type, "icao": self.icao, "data": self.raw}

    def get_wind(self) -> Wind | None:
        if self.parsed is None:
            return None
        wind_dir = self.parsed.wind_dir.value() if self.parsed.wind_dir is not None else None
        wind_speed = self.parsed.wind_speed.value(units="MPS") if self.parsed.wind_speed is not None else None
        return Wind(direction=wind_dir, speed=wind_speed)

    def get_precipirations(self) -> float:
        if self.parsed is not None:
            if self.parsed.precip_1hr is not None:
                if self.parsed.precip_1hr.istrace():
                    return 0.1
                return self.parsed.precip_1hr.value(units="CM")
        return 0


class XPWeatherEngine(WeatherEngine):
    def __init__(self, redis):
        WeatherEngine.__init__(self, redis)

        self.WIND_CACHE = {}

    def get_airport_weather(self, icao: str, moment: datetime):
        # Get airport weather from X-Plane Real weather files
        if not os.path.exists(REAL_WEATHER_DIR) or not os.path.isdir(REAL_WEATHER_DIR):
            logger.warning(f"no Real weather metar directory")
            return None

        fn = None
        # 1. Try the exact date, if any
        if moment is not None:
            dfn = moment.strftime("metar-%Y-%m-%d-%H.%M.txt")
            fn = os.path.join(REAL_WEATHER_DIR, dfn)
            if not os.path.exists(fn):
                logger.warning(f"no metar file for {moment.isoformat()}, trying alternate dates/times")
                fn = None
        # 2. Try any metar file
        if fn is None:
            metar_dir = os.path.join(REAL_WEATHER_DIR, "metar-*.txt")
            filenames = glob.glob(metar_dir)
            if len(filenames) > 0:
                filenames = sorted(filenames)
                fn = filenames[-1]
            else:
                logger.warning(f"no metar files in {metar_dir}")
        if fn is None:
            logger.warning("no metar file")
            return None

        return XPAirportWeather(icao=icao, moment=moment, engine=self, source=fn)

    def find_source_date(self):
        if self.source is None:
            return
        # /Users/pierre/Developer/oscars/emit/emitpy/data/x-plane/Output/Real weather/metar-2023-07-25-08.00.txt
        m = re.match(r"(.*)GRIB-(?P<date>[\.\-\d]+)-ZULU-wind-v2.grib", self.source)
        m2 = m.groupdict()
        if "date" in m2:
            datestr = m2["date"]
            if datestr is not None and len(datestr) > 0:
                try:
                    date = datetime.strptime(datestr, "%Y-%m-%d-%H.%M").astimezone()
                    logger.debug(f"wind file dated {date.isoformat()}")
                    self.source_date = date
                except:
                    logger.warning(f"wind file date {datestr} cannot be parsed")

    def prepare_enroute_winds(self, flight, use_gfs: bool = False) -> bool:
        # Check and select a X-Plane Real weather file
        # Get wind from X-Plane Real weather files
        #
        if use_gfs:
            if not os.path.exists(GFS_WEATHER_DIR) or not os.path.isdir(GFS_WEATHER_DIR):
                logger.warning(f"no GFS weather directory")
                return False
        else:
            if not os.path.exists(REAL_WEATHER_DIR) or not os.path.isdir(REAL_WEATHER_DIR):
                logger.warning(f"no Real weather directory")
                return False

        fn = None
        fid = flight.getId()
        if use_gfs:
            # 1.2. Try any grib file
            if fn is None:
                gfs_dir = os.path.join(GFS_WEATHER_DIR, "gfs.*")
                filenames = [filename for filename in glob.glob(gfs_dir) if not filename.endswith("idx")]
                if len(filenames) > 0:
                    filenames = sorted(filenames)
                    fn = filenames[-1]
                else:
                    logger.warning(f"no GFS files in {gfs_dir}")
            if fn is None:
                logger.warning("no GFS file")
                return False
            logger.debug(f"found {fn} GFS file")
        else:
            # 1.1. Try the exact date, if any
            #
            moment = flight.getScheduledDepartureTime()
            if moment is not None:
                dfn = moment.strftime("GRIB-%Y-%m-%d-%H.%M-ZULU-wind-v2.grib")
                fn = os.path.join(REAL_WEATHER_DIR, dfn)
                if not os.path.exists(fn):
                    logger.warning(f"no GRIB file for {moment.isoformat()}, trying alternate dates/times")
                    fn = None
            # 1.2. Try any grib file
            if fn is None:
                rw_dir = os.path.join(REAL_WEATHER_DIR, "GRIB-*-ZULU-wind-v2.grib")
                filenames = glob.glob(rw_dir)
                if len(filenames) > 0:
                    filenames = sorted(filenames)
                    fn = filenames[-1]
                else:
                    logger.warning(f"no GRIB files in {rw_dir}")
            if fn is None:
                logger.warning("no GRIB file")
                return False
            logger.debug(f"found {fn} Real weather GRIB wind file")

        self.find_source_date()

        # 2. Preselect the file for the flight, save its name in self.bbox_source
        #   wgrib -small_grib LonW:LonE LatS:LatN file_name
        bbox = flight.get_movement().getBoundingBox(rounding=1)  # (north, east, south, west)
        fbbfile = os.path.join(FLIGHT_WEATHER_DIR, fid + ".grib")

        args = [fn, "-small_grib", f"{bbox[3]}:{bbox[1]}", f"{bbox[2]}:{bbox[0]}", fbbfile]
        kwargs = {"stdout": subprocess.PIPE}
        cmd = ["wgrib2"] + args
        p = subprocess.Popen(["wgrib2"] + args, **kwargs)  # type: ignore [call-overload]
        logger.debug(f"{' '.join(cmd)}: {''.join([a.decode('UTF-8') for a in p.stdout])}")
        logger.debug(f"bounded box {bbox} stored in {fbbfile}")

        if not os.path.exists(fbbfile):
            logger.warning(f"wind file {fbbfile} not created")
            return False
        self.source = fbbfile
        self.flight_id = fid
        return True

    def parse_grib_data(self, lat, lon, alt, moment):
        # Parses GRIB data from file for WIND only
        args = ["-s", "-lon", f"{lon}", f"{lat}", self.source]
        kwargs = {"stdout": subprocess.PIPE}
        p = subprocess.Popen(["wgrib2"] + args, **kwargs)  # type: ignore [call-overload]
        winds = {}
        plat = None
        plon = None
        for line in iter(p.stdout):
            # 0   1      2          3   4            5           67
            # 638:132795878:d=2023072500:HGT:cloud ceiling:384 hour fcst::lon=51.000000,lat=4.500000,val=20000.2
            # 640:133298716:d=2023072500:PRES:low cloud bottom level:378-384 hour ave fcst::lon=51.000000,lat=4.500000,val=9.999e+20
            # 641:133658548:d=2023072500:PRES:middle cloud bottom level:378-384 hour ave fcst::lon=51.000000,lat=4.500000,val=9.999e+20
            # 642:133974124:d=2023072500:PRES:high cloud bottom level:378-384 hour ave fcst::lon=51.000000,lat=4.500000,val=14120.1
            r = line.decode("utf-8")[:-1].split(":")
            # Level, variable, value
            level, variable, value, lat, lon = [
                r[4].split(" "),
                r[3],
                r[7].split(",")[2].split("=")[1],
                r[7].split(",")[1].split("=")[1],
                r[7].split(",")[0].split("=")[1],
            ]
            if plat is None:
                if (lat, lon, moment.isoformat()) in self.WIND_CACHE.keys():
                    logger.debug("from cache", lat, lon, filename)
                    return (lat, lon, self.WIND_CACHE[(lat, lon, self.source)])
                plat = lat
                plon = lon
            elif plat != lat or plon != lon:
                logger.debug("WARNING: not same latitude, longitude", plat, plon, "vs", lat, lon)
            if len(level) > 1 and level[1] == "mb":
                # wind levels
                winds.setdefault(level[0], {})
                winds[level[0]][variable] = value

        windlevels = []
        # Let data ready to push on datarefs.
        # Convert wind and temperature levels
        for level, wind in winds.items():
            if "UGRD" in wind and "VGRD" in wind:
                lvl = level
                if (
                    "-" in level
                ):  # if it is a Layer between two specified height levels: Height of top in hm - Height of bottom in hm above ground: Example: 30-0
                    wa = level.split("-")
                    if len(wa) > 0:
                        lvl = wa[0]  # we keep the top of the layer..
                    # else will probably raise an error
                hdg, vel = c.c2p(float(wind["UGRD"]), float(wind["VGRD"]))
                lalt = int(c.mb2alt(float(lvl)))  # meters
                windlevels.append([lalt, hdg, vel])

        windlevels.sort()
        self.WIND_CACHE[(lat, lon, self.source)] = windlevels
        return (plat, plon, windlevels)

    def get_enroute_wind(self, flight_id, lat, lon, alt, moment: datetime) -> Wind | None:
        # Main function: Request wind information at lat, lon, alt at moment.
        # Return wind direction and speed and closest lat, lon, alt, and closest moment (of forecast)
        if self.flight_id != flight_id:
            logger.warning("requested flight id do not match prepared flight")
            return None

        if self.source is None:
            logger.warning(f"no file for flight {flight_id}")
            return None

        res = self.parse_grib_data(lat, lon, alt, moment)
        wl = res[2]

        # find lower and upper bounds
        i = 0
        while i < len(wl):
            if wl[i][0] > alt:
                break
            i = i + 1
        if i == 0:
            a1 = wl[0]
            # logger.debug("lower is ground (-1)")
        else:
            a1 = wl[i - 1]
        if i > 0 and i == len(wl):
            a2 = wl[-1]
            # logger.debug(f"upper is above measures ({alt} > {a2[0]})")
        else:
            a2 = wl[i]
        # interpolate between lower and upper bounds
        hdg = lin_interpol(a1[0], a1[1], a2[0], a2[1], alt)
        spd = lin_interpol(a1[0], a1[2], a2[0], a2[2], alt)

        w = Wind(speed=spd, direction=hdg)
        w.position = [float(res[0]), float(res[1]), alt]  # add details
        w.moment = self.source_date

        return w
