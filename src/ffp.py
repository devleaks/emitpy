"""
Test API for flightplandatabase with request caching.

"""

import flightplandb as fpdb
import requests_cache

requests_cache.install_cache()

# obviously, substitute your own token
api = fpdb.FlightPlanDB("vMzb5J3qtRnIo4CgdCqiGUsRhWEXpAHLMJj04Rds")

# list all users named lemon
for user in api.user.search("devleaks"):
    print(user)

# fetch most relevant user named lemon
print(api.user.fetch("devleaks"))

# fetch first 20 of lemon's plans
plans = api.user.plans(username="devleaks", limit=2)
for plan in plans:
    print(plan)
