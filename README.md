# emitpy

Flight path and Ground Support Vehicle path generator


# Aknowledgements

I thank the following software owners and programmers.

I used their tools and free software numerous time for inspiration or education during the development of mine.

 1. X-Plane, for its open data, free data designer tool, and data documentation.
 2. Little Navmap, to the exceptional software to plan flights. I use it to visualize plan, routes, procedures, transitions. I also visualize all my generated tracks on the moving map.
 3. LiveTraffic, to allow me to "inject" my generated tracks into X-Plane and get a "Digital Twin" vizualisation of them.
 4. XPPython3, to allow me to smoothly integrate my development to X-Plane


Gépès Cidesimal, geospatial specialist,
& Nafis Atou Ahouiyassa, developer,
& Hessa Hamplis, developer.



Future releases tags:
Felicity Ace
Tricolor
Titanic


===
Limitation

It is not currently possible to have more than one emission for a movement.
I.e. it is not possible to emit a flight as ADSB with a 30 sec interval
and emit the same flight as GroundRadar with a 1 sec interval.

Another example: It is not possible to "see" the same vehicle with two GroundRadars.

It is foreseen to lift this restriction in a later release.
