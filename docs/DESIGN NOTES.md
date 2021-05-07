


Use minimal packages.
 - Geographic processing: pyturf



Units:
 - Time unit: second
 - Distance unit: m, km, nm(route), ft(alt)


Timestamps for flights
--------

Formal:
Scheduled (== on/off-block time)
Takeoff/landing slot.

Note: For TO: Make plane arrive at TO holding position the slot BEFORE their actual TO slot.

Always maintain slot separation between flights.


Not formal in simulation:
    "TAXI",
    "TAKE_OFF",
    "TO_ROLL",
    "ROTATE",
    "LIFT_OFF",
    "INITIAL_CLIMB",
    "CLIMB",
    "CRUISE",
    "DESCEND",
    "APPROACH",
    "FINAL",
    "LANDING",
    "FLARE",
    "TOUCH_DOWN",
    "ROLL_OUT",
    "STOPPED_ON_RWY"
