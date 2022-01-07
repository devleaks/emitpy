"""
Test API for flightplandatabase with request caching.

"""

import flightplandb as fpdb
import requests_cache

from metar import Metar
import pytaf

requests_cache.install_cache()

api = fpdb.FlightPlanDB("vMzb5J3qtRnIo4CgdCqiGUsRhWEXpAHLMJj04Rds")


metar = api.weather.fetch(icao="OTHH")
print (metar)


obs = Metar.Metar(metar.METAR)
print (obs.string())


taf = pytaf.TAF(metar.TAF)
decoder = pytaf.Decoder(taf)
print(decoder.decode_taf())


# GENERATE = False
# if GENERATE:
#     fpq = fpdb.GenerateQuery(fromICAO="EDDF", toICAO="EBBR", useAWYLO=True, useAWYHI=True,
#                              cruiseSpeed=380)
#     qres = api.plan.generate(fpq)
#     if qres is not None:
#         plan = api.plan.fetch(id_=qres.id)
#         if plan is not None:
#             for n in plan.route.nodes:
#                 print("%s (%s)" % (n.ident, n.type))
# else:
#     fpq = fpdb.PlanQuery(fromICAO="EBBR", toICAO="EDDF")
#     qres = api.plan.search(fpq)
#     if qres is not None:
#         for plan in qres:
#             print(plan)
