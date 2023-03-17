"""
A METAR is a weather situation at a named location, usually an airport.
"""
import logging
import requests

from .metar import Metar

logger = logging.getLogger("MetarMesonet")

class MetarMesonet(Metar):
    """
    Fetch past METAR and cache it
    """
    def __init__(self, icao: str, redis = None):
        Metar.__init__(self, icao=icao, redis=redis)

    def fetch(self):
        yr = self.moment_norm.strftime("%Y")
        mo = self.moment_norm.strftime("%m")
        dy = self.moment_norm.strftime("%d")
        hr = self.moment_norm.strftime("%H")
        nowstr = self.moment_norm.strftime('%d%H%MZ')
        nowstr2 = self.moment_norm.strftime('%Y%m%d%H%M')

        """
        Also:
        * https://xplane-weather.danielkappelle.com
        * https://mesonet.agron.iastate.edu/request/download.phtml
        * https://github.com/akrherz/iem/blob/main/scripts/asos/iem_scraper_example.py

        https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station=OTHH&data=all&year1=2023&month1=2&day1=14&year2=2023&month2=2&day2=14&tz=Etc%2FUTC&format=onlycomma&latlon=no&elev=no&missing=null&trace=null&direct=no&report_type=3&report_type=4

        returns:
        station,valid,tmpf,dwpf,relh,drct,sknt,p01i,alti,mslp,vsby,gust,skyc1,skyc2,skyc3,skyc4,skyl1,skyl2,skyl3,skyl4,wxcodes,ice_accretion_1hr,ice_accretion_3hr,ice_accretion_6hr,peak_wind_gust,peak_wind_drct,peak_wind_time,feel,metar,snowdepth
        OTHH,2023-02-14 00:00,66.20,62.60,88.18,360.00,9.00,0.00,29.97,null,2.80,null,NSC,null,null,null,null,null,null,null,HZ,null,null,null,null,null,null,66.20,OTHH 140000Z 36009KT 4500 HZ NSC 19/17 Q1015 TEMPO 4000 BR,null
        OTHH,2023-02-14 01:00,66.20,64.40,93.92,20.00,7.00,0.00,29.97,null,3.11,null,NSC,null,null,null,null,null,null,null,HZ,null,null,null,null,null,null,66.20,OTHH 140100Z 02007KT 5000 HZ NSC 19/18 Q1015 NOSIG,null
        OTHH,2023-02-14 02:00,66.20,64.40,93.92,50.00,5.00,0.00,29.97,null,3.73,null,NSC,null,null,null,null,null,null,null,null,null,null,null,null,null,null,66.20,OTHH 140200Z 05005KT 6000 NSC 19/18 Q1015 NOSIG,null
        OTHH,2023-02-14 03:00,66.20,64.40,93.92,80.00,3.00,0.00,29.97,null,2.55,null,NSC,null,null,null,null,null,null,null,BR,null,null,null,null,null,null,66.20,OTHH 140300Z 08003KT 4100 BR NSC 19/18 Q1015 TEMPO 3000,null
        (...)
        """
        url2 = f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={self.icao}&data=all"
        url2 = url2 + f"&year1={yr}&month1={mo}&day1={dy}&year2={yr}&month2={mo}&day2={dy}&tz=Etc%2FUTC&format=onlycomma&latlon=no&elev=no&missing=null&trace=null&direct=no&report_type=3"

        url = url2

        logger.debug(f":fetch: url={url}")
        #with open("/Users/pierre/Developer/oscars/emitpy/src/emitpy/airspace/result.txt", "r") as response:  # urllib.request.urlopen(url) as response:

        response = requests.get(url, cookies={'cookieconsent_status': 'dismiss'})
        txt = response.text
        # with urllib.request.urlopen(url) as response:
        #     txt = response.read().decode("UTF-8")
        logger.debug(f":fetch: {txt}")

        metar = self.scrap_metar(txt)
        if metar is None:
            return (False, "MetarMesonet::fetch: failed to get historical metar")

        self.raw = metar[len(nowstr2)+7:-1]
        logger.debug(f":fetch: historical metar {self.moment_norm} '{self.raw}'")
        return self.parse()

    def scrap_metar(self, txt):
        """
        In this case, we should save/store metars for the whole day since we got it.

        :param      txt:  The text
        :type       txt:  { type_description }
        """
        metar = None

        nowstr = self.moment_norm.strftime('%Y-%m-%d %H:00')
        csvdata = csv.DictReader(StringIO(txt))
        for row in csvdata:
            if row["station"] == self.icao and row["valid"] == nowstr:
                metar = row["metar"]
                # logger.debug(f":fetchHistoricalMetar: search for '{start}(.*)': {metar}")
        return metar

#