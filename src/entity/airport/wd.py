def computeRunway(runways, wind, rwys):
    r0 = rwys > 1 ? runways[0].substring(0, 2) : runways[0]
    r1 = rwys > 1 ? runways[1].substring(0, 2) : runways[1]

    runway_heading = r0 < r1 ? r0 : r1  # keep the smallest heading value
    runway_alt = r0 < r1 ? r1 : r0  # keep the smallest heading value

    runway_heading_txt = r0 < r1 ? runways[0] : runways[1]  # keep the smallest heading value
    runway_alt_txt = r0 < r1 ? runways[1] : runways[0]  # keep the smallest heading value

    wmin = runway_heading - 9
    if (wmin < 0) wmin += 36
    wmax = runway_heading + 9
    if (wmax > 36) wmax -= 36

    if (wmin > wmax) {  # switch them
        t = wmax
        wmax = wmin
        wmin = t
    }

    wind_int = Math.round((parseInt(wind) + 5) / 10)
    wind_ret = (wind_int > wmin && wind_int < wmax) ? runway_alt_txt : runway_heading_txt
    debug.print(wind, runway_heading, runway_alt, wmin, wmax, wind_int, wind_ret)
    return wind_ret  # (wind_int > wmin && wind_int < wmax) ? runway_alt_txt : runway_heading_txt
