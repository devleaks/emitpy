# Ideas, To do

Services:
If no start position, use (closest) depot
If no end position, use ramp rest position

Gépès Cidesimal, geospatial specialist,
& Nafis Atou Ahouiyassa, developer,
& Hessa Hamplis, developer.



Future releases tags:
13: Titanic
14: Titan
15: HMS Namur
Toyama Maru
Indomptable
Achille
Redoutable
Scilly naval disaster of 1707



---

Route with constraints:

Make sure constraints are on vertices (uniform).
Make sure constraints that are on edges are carried on vertices (uniform too, possible conflict).

---

Read from file/dict, not Redis
Redis only if queue?

---

service-pois: when loading, check that each service has at least 1 depot, 1 parking.
if not: either suppress service or add depot and/or parking at airport's center.

---

simplify aircraft types to narrow-body, wide-body?
add turnaround profiles for them

---
Correct: LoadAirlines in loadapp to load flight operators as well

---
Ramp: Add: hasJetway()
Flight: Add cargo/pax + service choice, shortcut: cargo fligth are not Jetway

May be add a rule in airport to tell whether Ramp has jetway?

airport.hasJetway(ramp) -> bool
based on list of ramp with jetways, supplied in airport.yaml?

---
To do:
-----

add pax/cargo to API
make some parameters optionals
runway not used?

create arbitrary event


logger\.(debug|info|warn|warning|error)\(([f'"]*):([a-zA-Z0-9_]+): 


