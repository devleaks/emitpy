import re

icao = "OTHH"
nowstr = "312300Z"
nowstr2 = "201903312300"


with open("/Users/pierre/Developer/oscars/emitpy/src/emitpy/airspace/result.txt", "r") as response:  # urllib.request.urlopen(url) as response:
    txt = response.read()
    s = "201903312300 METAR OTHH 312300Z"
    for line in re.findall(s+"(.*)", txt):
         print(s+line)
