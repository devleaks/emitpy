# Types of constraints and handling



# Speed-based Constraints

## Minimum speed

?


## Maximum speed

### Below FL100

250kn



# Altitude-based Constraints


## Minimum altitude


## Maximum altitude


## MORA

At airspace level.


# General

Constraints are carried over to adjacent segements (sometimes before, sometimes after)


# Environmental Constraints


## Noise Abatment

Time dependant?

In general, can constraints be time-based? or dependent on other factor (time (time of day, day of week, seasonal), weather...)


## Toxic Gas Emission Reduction

(is it strictly equal to lower fuel consumption?)



# Computation for FMS/Flight plan

From constraints, carry over to nearby waypoints according to rules.

Ignore waypoints with no constraints.


# Aicraft

Aircraft has capacity:

Speed (min, max), acceleration, deceleration (capacity to change speed, may be ignored in first instance?)

Alt (min?, max?), vertical speed (min, max) (ignore v/s acceleration)


## Start

speed
vertical speed
alt

## Move

distance


## AC Capacity

accel/decel
vspeed min/max

## End - Goals

### Free

### Constrained

#### Speed


#### Altitude



# Constraint Programming

Problem: Civil aircraft flight plan

Flight plan is a succession of waypoints. (20 to 200+)

A few waypoints (less than 20) have constraints.

Altitude: Below, at or above.
Speed: Below, or at (above rare)

Travelling aircraft has a constraints too:
speed: min, max, acceleration, deceleration
vertical speed: min, max (vertical acceleration negligible)
Target « cruise » speed and altitude (to reach)

optimize climb, descend respecting constraints.

Problem: Give optimum high and speed at each waypoint.