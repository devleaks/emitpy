"""
A METAR is a weather situation at a named location, usually an airport.
"""
import logging
import requests

from .metar import Metar

logger = logging.getLogger("Ogimet")


class OGIMETMetar(WebFetch):

	def __init__(self, icao: str, moment):
		WebFetch.__init__(self, icao, moment)

	def fetch(self):
		yr = self.moment_norm.strftime("%Y")
		mo = self.moment_norm.strftime("%m")
		dy = self.moment_norm.strftime("%d")
		hr = self.moment_norm.strftime("%H")
		nowstr = self.moment_norm.strftime('%d%H%MZ')
		nowstr2 = self.moment_norm.strftime('%Y%m%d%H%M')

		"""
		https://www.ogimet.com/display_metars2.php?lang=en&lugar=OTHH&tipo=SA&ord=REV&nil=SI&fmt=txt&ano=2019&mes=04&day=13&hora=07&anof=2019&mesf=04&dayf=13&horaf=07&minf=59&send=send	  ==>
		201904130700 METAR OTHH 130700Z 29012KT 3500 TSRA FEW015 SCT030 FEW040CB OVC100 21/17 Q1011 NOSIG=
		"""
		url1 = f"https://www.ogimet.com/display_metars2.php?lang=en&lugar={self.icao}&tipo=SA&ord=REV&nil=SI&fmt=txt"
		url1 = url1 + f"&ano={yr}&mes={mo}&day={dy}&hora={hr}&anof={yr}&mesf={mo}&dayf={dy}&horaf={hr}&minf=59&send=send"

		url = url1

		logger.debug(f"url={url}")
		#with open("/Users/pierre/Developer/oscars/emitpy/src/emitpy/airspace/result.txt", "r") as response:  # urllib.request.urlopen(url) as response:

		response = requests.get(url, cookies={'cookieconsent_status': 'dismiss'})
		txt = response.text
		# with urllib.request.urlopen(url) as response:
		#	 txt = response.read().decode("UTF-8")
		logger.debug(f"{txt}")

		metar = self.scrap_metar(txt)
		if metar is None:
			return (False, "MetarOgimet::fetch: failed to get historical metar")

		self.raw = metar[len(nowstr2)+7:-1]
		logger.debug(f"historical metar {self.moment_norm} '{self.raw}'")
		return self.parse()

	def scrap_metar(self, txt):
		metar = None

		nowstr = self.moment_norm.strftime('%d%H%MZ')
		nowstr2 = self.moment_norm.strftime('%Y%m%d%H%M')
		# 201903312300 METAR OTHH 312300Z
		start = f"{nowstr2} METAR {self.icao} {nowstr}"
		logger.debug(f"start '{start}'")
		for line in re.findall(start+"(.*)", txt):
			 metar = start+line
			# logger.debug(f"search for '{start}(.*)': {metar}")

		return metar