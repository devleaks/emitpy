# emitpy

Flight path and Ground Support Vehicle path generator


# Aknowledgements

I thank the following software owners and programmers.

I used their tools and free software numerous time during the development of mine.

 1. X-Plane, for its open data, free data designer tool, and data documentation.
 2. Little Navmap, to the exceptional software to plan flights. I use it to visualize plan, procedures, transitions.
 3. LiveTraffic, to allow me to "inject" my generated tracks into X-Plane and get a "Digital Twin" vizualisation of them.
 4. XPPython3, to allow me to smoothly integrate my development to X-Plane


# To Do

Better SID/STAR selection.
Suggestion: Make a directed graph from antepenultimate/second point of cruise (last/first is not sufficient) to arrival/from departure runway.
Let AStar algorithm choose fastest arrival/departure route.

Automatic runway exit findings?

Better hold entry / exit

Add ACARS messages, OOOI, TMO

--
Service(orig, ramp, dest, service)

service
    qty -> duration

dest=code: DEPOT|REST|RAMP


--

Solution for broadcaster:

PUSH
----
set emit_item.version = versions[emit_item.id] + 1
versions[emit_item.id] = versions[emit_item.id] + 1

store new emit in datetime-based heapq

POP
---


while emitdate < now():
    item = heapq.pop()

    if item[item.id].version != versions[item.id]:
        discard
    else:
        send

    emitdate = item.emitdate

sleep until emitdate
