from math import sqrt, radians, degrees, sin, cos, atan2

# https://math.stackexchange.com/questions/1365622/adding-two-polar-vectors
def add_speed(r1, r2):
	p21 = radians(r2[1]) - radians(r1[1])
	r = sqrt( r1[0]*r1[0]  + r2[0]*r2[0] + 2 * r1[0] * r2[0] * cos(p21) )
	phi = radians(r1[1]) + atan2(r2[0] * sin(p21), r1[0] + r2[0] * cos(p21) )
	dp = round(degrees(phi), 3)
	if dp == 0:
		dp = 0
	if dp < 0:
		dp = dp + 360
	if dp >= 360:
		dp = dp - 360
	if dp == 0:
		dp = abs(dp)  # avoid -0.0
	return (r, dp)

# Opposite
def subtract_speed(r1, r2):

	opp = r2[1] + 180
	if opp > 360:
		opp = opp - 360
	return add _speed(r1, (r2[0], opp))

#
# Aliases
def ground_speed(true_airspeed, wind_speed):
	return subtract_speed(true_airspeed, wind_speed)


def air_speed(ground_speed, wind_speed):
	return add_speed(ground_speed, wind_speed)