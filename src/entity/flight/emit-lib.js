import turf from "@turf/turf";
import * as geojson from "./geojson-util.js";
import * as debug from "./debug.js";
import { smoothTurns } from "./arc-lib.js"
import { copyProps } from "./device.js"
import util from "util"

function point_on_line(c, n, d) {
    let brng = turf.bearing(c, n)
    const p = turf.destination(c, d, brng)
    return p.geometry.coordinates
}

/*  Add jitter around point, random direction, random distance between 0 and r (meters)
 *  @todo: Jitter 3D
 */
export function jitter(p, r = 0) {
    if (r == 0) return p
    const j = turf.destination(p, Math.random() * Math.abs(r) / 1000, Math.random() * 360)
    // should add some vertical uncertainty as well...
    // if(j.geometry.coordinates.length == 3)
    //  j.geometry.coordinates[2] = j.geometry.coordinates[2] + (Math.random() * Math.abs(r) / 2000)
    return j.geometry.coordinates
}

function linear_interpolate(currpos, lsidx, ls, speeds) { // linear acceleration
    let totald = turf.distance(ls[lsidx], ls[lsidx + 1])
    let s = 0
    if (totald == 0) {
        s = speeds[lsidx + 1]
    } else {
        let partiald = turf.distance(ls[lsidx], currpos)
        let portion = partiald / totald
        s = speeds[lsidx] + portion * (speeds[lsidx + 1] - speeds[lsidx])
    }
    return s
}


// we're at currpos, heading to nextvtx
// we move rate seconds in that direction
// returns where we land after rate seconds
function point_in_rate_sec(options, currpos, rate, lsidx, ls, speeds) {
    // We are at currpos, between ls[lsidx] and ls[lsidx+1]. We go towards ls[idx+1] for rate seconds.
    // 1. What is the speed at currpos. We assume linear accelleration.
    let totald = turf.distance(ls[lsidx], ls[lsidx + 1])

    if (totald == 0)
        return ls[lsidx + 1]

    let partiald = turf.distance(ls[lsidx], currpos)
    let leftd = totald - partiald // leftd = turf.distance(currpos, ls[lsidx+1])
    let portion = partiald / totald
    let v0 = speeds[lsidx] + portion * (speeds[lsidx + 1] - speeds[lsidx])
    v0 = v0 < options.minSpeed ? options.minSpeed : v0
    let v1 = speeds[lsidx + 1] // should be >= options.minSpeed by design...
    let acc = (speeds[lsidx + 1] * speeds[lsidx + 1] - speeds[lsidx] * speeds[lsidx]) / (2 * totald) // a=(u²-v²)/2d

    // 2. Given the speedatcurrpos and speeds[idx+1] at ls[idx+1] how far do we travel duing rate seconds?
    let hourrate = rate / 3600
    let dist = v0 * hourrate + acc * hourrate * hourrate / 2

    let nextpos = point_on_line(currpos, ls[lsidx + 1], dist)

    debug.print({
        "prevvtx": geojson.ll(ls[lsidx]),
        "startp": geojson.ll(currpos),
        "nextvtx": geojson.ll(ls[lsidx + 1]),
        "nextpos": geojson.ll(nextpos),
        "totald": totald,
        "covered": partiald,
        "lefd": leftd,
        "prevspeed": speeds[lsidx],
        "nextspeed": speeds[lsidx + 1],
        "currspeed": v0,
        "accel": acc,
        "rate": rate,
        "rate/h": rate / 3600,
        "dist": dist,
        "ctr dist": turf.distance(currpos, nextpos),
        "leftvtx": turf.distance(nextpos, ls[lsidx + 1])
    })

    return nextpos
}

function lookupSyncAtVertex(newidx, syncVertices, idx) {
    let syncprop = {}
    const f = geojson.findFeature(idx, syncVertices, "idx")
    if (f && f.hasOwnProperty("properties") && f.properties.hasOwnProperty("sync") && !f.properties.hasOwnProperty("synced")) {
        let allProps = geojson.cleanCopy(f.properties)
        syncprop = geojson.mergeProperties({
            "sync": f.properties.sync,
            "newlsidx": newidx //  just a ref toLineString coordinate index.
        }, allProps)
        f.properties.synced = true
    }
    return syncprop
}

// BEFORE emit(options, newls, t, p, s, pts, spd, cmt, idx, alt = false, props = {}) { //s=(s)tart, (e)dge, (v)ertex, (f)inish
/* NOW
emit({
    options: options,
    newls: newls,
    oldls: ls,
    t: timing.time + timing.left,
    p: pos,
    s: "w",
    pts: points,
    spd: 0,
    cmt: (lsidx == (lsmax - 1)) ? "at last vertex while pauseing " + counter : "at vertex while pauseing " + counter,
    idx: lsidx,
    alt: false,
    props: {device:, flight_name,operator:, movement:,handler: }
})
*/
function emit(args) { //s=(s)tart, (e)dge, (v)ertex, (f)inish
    let k = args.s.charAt(0) // markers are at vertices which cannnot occur on edges.
    let syncprop = k != "e" ? lookupSyncAtVertex(args.newls.length - 1, args.options._syncers, args.idx) : {}
    let hasSync = syncprop.hasOwnProperty("sync")
    if ((k == "s" || k == "e") // normal emit: (S)tart or on (E)dge
        ||
        (k == "w" && (!args.options.quiet || hasSync)) // Paused. Does not emit if silent, unless there is a sync
        ||
        (k == "v" && (args.options.vertices || hasSync)) || // At vertex: If there is a marker on the vertex, we add a point it with sync info.
        (k == "f" && (args.options.lastPoint || hasSync)) // For this point, emit is true or false whether we should emit this vertex. 
        // (note: the last point is also a vertex, and has an extra option to emit it.)         
    ) { // from now on, we will "write" the point, but emit can be either true or false.

        let color = "#888888"
        switch (k) {
            case "s":
                color = "#eeeeee"
                break
            case "e":
                color = "#ff2600"
                break
            case "v":
                color = "#fffc00"
                break
            case "f":
                color = "#111111"
                break
            case "w":
                color = "#00fa00"
                break
            default:
                color = "#888888"
        }


        let brng = (args.newls.length > 0) ? turf.bearing(args.newls[args.newls.length - 1], args.p) : 0

        if (args.pts.length == 1) { // retro add bearing of first element
            let b = Math.round(turf.bearing(args.newls[0], args.p) * 10) / 10
            while(b<0) {b += 360}
            args.pts[0].properties.bearing = b
        }

        if (brng < 0) brng += 360
        brng = Math.round(brng * 10) / 10
        // debug.print(k, args.idx, args.newls[args.idx], args.p, brng)

        if (args.newls.length > 0) { // invalidate bearing if distance is too small
            const d = turf.distance(args.newls[args.newls.length - 1], args.p) // kilometer
            if (d < 0.010) { // less than 10 meters
                brng = null // invalidate bearing (device stoped? so left as it was)
            }
        }

        const jp = jitter(args.p, args.options.jitter)

        if (args.options.altitude && args.alt !== false) {
            jp[2] = args.alt
        }
        args.newls.push(jp)

        let properties = geojson.mergeProperties({ // we first merge "our" properties from here
            "emit": !((k == "v" && !args.options.vertices) || (k == "f" && !args.options.lastPoint) || (k == "w" && args.options.quiet)),
            "marker-color": color,
            "marker-size": "medium",
            "marker-symbol": "",
            "nojitter": args.p,
            "elapsed": args.t,
            "vertex": args.idx,
            "sequence": args.pts.length,
            "category": args.s, // (s)tart, (e)dge, (v)ertex, (f)inish, (w)ait
            "speed": args.spd,
            "bearing": brng,
            "note": args.cmt
        }, args.props)

        if (args.options.altitude && args.alt !== false) {
            properties.alt = args.alt
        }

        debug.print(args.s, args.idx)
        if (syncprop.hasOwnProperty("sync")) {
            properties = geojson.mergeProperties(properties, syncprop)
            debug.print("adding sync", args.idx, syncprop)
        }

        args.pts.push(geojson.removeTemporaryProperties(geojson.Feature(geojson.Point(jp), properties)))
    }
}

/* Attempt to manage a change of speed between edges.
 *
 */

// Shortcut:
// From a table (vertex index,speed at that vertex) for some vertex only,
// we build a simple table (vertex index, speed at vertex) for all vertices
// we also get a table (vertex index, time at that vertext).
export function fillSpeed(a, len, minval = 0, dftval = 0) {
    fillValues(a, len, minval, dftval)
} //@@todomust check that there are no 2 speeds=0 following each other with d>0


// From a table (vertex index,altitude or gradient at that vertex) for some vertex only,
// we build a simple table (vertex index, altitude at vertex) for all vertices.
// If no altitude is given, ground level is assumed.
// Altitude is spedicifed by a couple (altitude-type, altitude) where altitude type is
// MSL (above (Mean) Sea Level)
// AGL (Above Ground Level)
// BAR (Aircraft Barometric Altitude)
// Note: GeoJSON requires altitude in meter either "with z expressed as metres above mean sea level per WGS84" or "SHALL be the height in meters above the WGS 84 reference ellipsoid"
// Well, for use its either above (airport) ground level, or above mean sea level, whereever level 0 migth be...
// Note that an aircraft's ADS-B transmission broadcasts its "barometric altitude". Oh boy. 
function fillValues(a, len, minval = 0, dftval = 0) {
    function nexta(arr, from, max) { // returns next array item index with non undefined value
        if (from == (max - 1)) {
            return from
        }
        let i = from + 1
        while (i < (max - 1) && typeof(arr[i]) == "undefined")
            i++
        return i
    }

    if (typeof(a[0]) == "undefined")
        a[0] = dftval < minval ? minval : dftval

    for (let i = 1; i < len; i++) {
        if (typeof(a[i]) == "undefined") {
            let j = nexta(a, i, len)
            if ((j == len - 1) && (typeof(a[j]) == "undefined")) { // no last value, stay at constant speed
                for (let k = i; k < len; k++) {
                    a[k] = a[k - 1]
                }
            } else { // change speed to next supplied value
                let d = a[j] < minval ? minval : a[j] // target value
                let s = (d - a[i - 1]) / (j - i + 1) // slope
                for (let k = i; k <= j; k++) {
                    a[k] = a[i - 1] + s * (k - i + 1)
                }
            }
            i = j
        } else {
            a[i] = a[i] < minval ? minval : a[i]
        } // else a is set
    }
} //@@todomust check that there are no 2 speeds=0 following each other with d>0



/*  Altitude functions
 *
 */
function fillAltitude(a, len) {
    fillValues(a, len, 0, 0)
}

// Return altitude MSL
function altitudeMSL(altdef, ground = 0) {
    return altdef.type == "MSL" ? altdef.alt : ground + altdef.alt
}

// nice display of seconds
function sec2hms(i) {
    let totalSeconds = Math.round(i * 3600)
    let hours = Math.floor(totalSeconds / 3600)
    totalSeconds %= 3600
    let minutes = Math.floor(totalSeconds / 60)
    let seconds = totalSeconds % 60
    minutes = String(minutes).padStart(2, "0")
    hours = String(hours).padStart(2, "0")
    seconds = String(seconds).padStart(2, "0")
    let msec = Math.round(totalSeconds * 1000) / 1000
    return hours + ":" + minutes + ":" + seconds // + "." + msec
}

function eta(ls, speed) {
    let eta = []
    eta[0] = 0
    //debug.print(speed)
    debug.print("v0", 0, speed[0], speed[0], 0, "00:00:00", "00:00:00")
    for (let i = 1; i < speed.length; i++) {
        let t = 0
        let d = turf.distance(ls[i - 1], ls[i])
        if (speed[i - 1] != speed[i]) {
            t = 2 * d / Math.abs(speed[i] + speed[i - 1]) // acceleration is uniform, so average speed is OK for segment.
        } else {
            t = d / Math.max(speed[i - 1], speed[i])
        }
        eta[i] = eta[i - 1] + t
        debug.print("v" + i, Math.round(1000 * d) / 1000, speed[i - 1], speed[i], Math.round(3600000 * t) / 1000, sec2hms(t, 2), sec2hms(eta[i], 2))
    }
    return eta
}

function time2vtx(options, p, idx, ls, sp, rate) {
    let d = turf.distance(p, ls[idx + 1])
    let d0 = turf.distance(ls[idx], p)
    let de = turf.distance(ls[idx], ls[idx + 1])
    let vp = 0
    if (d0 == 0)
        vp = sp[idx]
    else if (d == 0)
        vp = sp[idx + 1]
    else
        vp = sp[idx] + (d0 / de) * (sp[idx + 1] - sp[idx]) // speed at point, if linear acceleration

    vp = vp < options.minSpeed ? options.minSpeed : vp

    debug.print("time2vtx ", d, de, sp[idx], sp[idx + 1], vp)

    let t = 0
    if ((vp + sp[idx + 1]) != 0)
        t = 2 * d / (vp + sp[idx + 1]) // again, we assume constant acceleration so avg speed is fine

    let r = Math.round(t * 3600000) / 1000
    debug.print(">>> TO", idx + 1, d + " km left", r + " secs needed")

    /* control */
    let p1 = point_in_rate_sec(options, p, rate, idx, ls, sp)
    let d1 = turf.distance(p1, ls[idx + 1])
    let p2 = point_in_rate_sec(options, p, r, idx, ls, sp)
    let d2 = turf.distance(p2, ls[idx + 1])
    let d3 = turf.distance(p, p1)
    let d4 = turf.distance(p, p2)
    debug.print("CONTROL", {
        "index": idx,
        "d2next": d,
        "dfprev": d0,
        "dtot": de,
        "v0": sp[idx],
        "v1": sp[idx + 1],
        "vp": vp,
        "time2vtx": r,
        "control:d2next(rate)": d1,
        "control:d2next(time2vtx)": d2,
        "control:d3travel(rate)": d3,
        "control:d4travel(time2vtx)": d4
    })

    return r
}


/* When on pause, forces speed to 0
 */
function pauseAtVertex(options, timing, pause, rate, newls, pos, lsidx, lsmax, points, speeds, ls, props) {
    debug.print("IN", pause, lsidx, timing)
    let counter = 0
    if (pause && pause > 0) {
        debug.print("must pause", pause)
        if (pause < rate) {
            if (pause > timing.left) { // will emit here
                emit({
                    options: options,
                    newls: newls,
                    oldls: ls,
                    t: timing.time + timing.left,
                    p: pos,
                    s: "w",
                    pts: points,
                    spd: options.altitude ? 0 : false,
                    cmt: (lsidx == (lsmax - 1)) ? "at last vertex while pauseing " + counter : "at vertex while pauseing " + counter,
                    idx: lsidx,
                    alt: options.altitude ? 0 : false, // if we pause, we're no helicopter, we're on the ground
                    props: props
                })
                counter++
                debug.print("pauseing 1 ...", pause)
                // keep wating but no emit since pause < rate
                timing.time += pause
                timing.left = rate - pause - timing.left
            } else { // will not emit here, we just pause and then continue our trip
                debug.print("paused but carries on", pause)
                timing.time += pause
                timing.left -= pause
            }
        } else { // will emit here, may be more than once. let's first emit once on time left
            emit({
                options: options,
                newls: newls,
                oldls: ls,
                t: timing.time + timing.left,
                p: pos,
                s: "w",
                pts: points,
                spd: 0,
                cmt: (lsidx == (lsmax - 1)) ? "at last vertex while pauseing " + counter : "at vertex while pauseing " + counter,
                idx: lsidx,
                alt: options.altitude ? 0 : false,
                props: props
            })
            counter++
            debug.print("pauseing 2 ...", timing.left)
            timing.time += timing.left

            let totpause = pause - timing.left
            // then let"s emit as many time as we pause
            while (totpause > 0) {
                timing.time += rate
                emit({
                    options: options,
                    newls: newls,
                    oldls: ls,
                    t: timing.time,
                    p: pos,
                    s: "w",
                    pts: points,
                    spd: 0,
                    cmt: (lsidx == (lsmax - 1)) ? "at last vertex while pauseing " + counter : "at vertex while pauseing " + counter,
                    idx: lsidx,
                    alt: options.altitude ? 0 : false,
                    props: props
                })
                counter++
                debug.print("pauseing more ...", totpause)
                totpause -= rate
            }
            // then set time to next emit
            timing.left = totpause + rate
        }
    }
    timing.counter = counter
    debug.print("OUT", timing)
    return timing
}


/** MAIN **/
export const emitGeoJSON = function(f, options) {
    if (!f.hasOwnProperty("type")) {
        debug.error("no type. Not GeoJSON?")
        return false
    }
    if (f.type == "FeatureCollection") {
        return emitCollection(f, options);
    } else if (f.type == "Feature") {
        if (f.geometry && f.geometry.type == "LineString") { // feature can omot geometry
            let fret = emitLineStringFeature(f, options)
            if (fret.points && fret.points.length > 0) { // add points of emission if requested (-p option)
                let fc = {
                    type: "FeatureCollection",
                    features: []
                }
                fc.features.push(fret.feature)
                fc.features = f.features.concat(points)
                return fc
            } else
                return fret.feature
        }
    } else if (f.type == "LineString") {
        let fret = emitLineStringFeature({
            "type": "Feature",
            "geometry": f
        }, options)
        return fret.feature.geometry
    }
    return false // f is no geojson?
};

export const emitCollection = function(fc, options) {
    let markers = []
    let syncers = []
    fc.features.forEach(function(f) {
        if ((f.geometry && f.geometry.type == "Point") &&
            (f.hasOwnProperty("properties") && f.properties.hasOwnProperty("marker") && f.properties.marker)) {
            if (f.properties.hasOwnProperty("nearestPointOnLine")) delete f.properties.nearestPointOnLine
            markers.push(f)
            if (f.properties.hasOwnProperty("sync")) {
                syncers.push(f)
            }
        }
    })
    options._markers = geojson.FeatureCollection(markers)
    options._syncers = geojson.FeatureCollection(syncers)
    fc.features.forEach(function(f, idx) {
        if (f.geometry && f.geometry.type == "LineString") {
            let fret = emitLineStringFeature(f, options)
            if (fret.feature)
                fc.features[idx] = fret.feature
            if (fret.points && fret.points.length > 0) { // add points of emission if requested (-p option)
                fc.features = fc.features.concat(fret.points)
            }
        }
    })
    return fc
};

function mkAltsAtVertices(ls) {
    let a = []
    ls.forEach((p, idx) => {
        if (p.length == 3) {
            a.push({
                idx: idx,
                alt: p[2]
            })
        }
    })
    return a
}

export const emitLineStringFeature = function(f, o) {
    const options = o;
    let speedsAtVertices = (f.hasOwnProperty("properties") && f.properties.hasOwnProperty("speedsAtVertices")) ? f.properties.speedsAtVertices : null
    let pausesAtVertices = (f.hasOwnProperty("properties") && f.properties.hasOwnProperty("pausesAtVertices")) ? f.properties.pausesAtVertices : null
    let altsAtVertices = (f.hasOwnProperty("properties") && f.properties.hasOwnProperty("altsAtVertices")) ? f.properties.altsAtVertices : null
    let ls = f.geometry.coordinates // linestring
    let lsidx = 0 // index in linestring
    let newls = [] // coordinates of new linestring
    let time = 0 // ticker
    let points = [] // points where broacasting position

    let speeds = []
    let pauses = []
    let alts = []
    let staticProperties = {}
    copyProps(f.properties, staticProperties, [ "device", "adsb", "model", "registration", "movement", "handler", "operator" ], true)

    const speed = parseFloat(options.speed)
    const rate = parseFloat(options.rate)

    if (Array.isArray(speedsAtVertices)) {
        speedsAtVertices.forEach(function(sp) {
            if (sp.idx < ls.length)
                speeds[sp.idx] = sp.speed
        })
    } else {
        speeds[ls.length - 1] = speed
    }
    fillSpeed(speeds, ls.length, parseFloat(options.minSpeed), speed) // init speed array
    eta(ls, speeds)

    if (Array.isArray(pausesAtVertices)) {
        pausesAtVertices.forEach(function(wt) {
            if (wt.idx < ls.length)
                pauses[wt.idx] = wt.pause
        })
    }

    if (options.altitude && (!Array.isArray(altsAtVertices) || !(altsAtVertices.length > 0))) {
        altsAtVertices = mkAltsAtVertices(ls)
    }

    if (options.altitude && Array.isArray(altsAtVertices)) {
        altsAtVertices.forEach(function(wt) {
            if (wt.idx < ls.length)
                alts[wt.idx] = wt.alt
        })
        //console.log("Altitude::BEFORE", util.inspect(alts, {depth: null, colors: true, maxArrayLength: null}))
        fillAltitude(alts, ls.length) // init altitude array
        //console.log("Altitude::AFTER", util.inspect(alts, {depth: null, colors: true, maxArrayLength: null}))
        // place altitude on points
        ls.forEach(function(p, idx) {
            if (p.length == 2) { // has only 2 coord, so we add alt
                p[2] = alts[idx]
            }
        })
    }

    debug.print("arrays:" + ls.length + ":" + speeds.length + ":" + pauses.length + ":" + alts.length)


    //console.log("Altitude::ORIGINAL", util.inspect(alts, {depth: null, colors: true, maxArrayLength: null}))
    if (options.smooth) {
        let f1 = smoothTurns(ls, speeds, alts, pauses)

        f1.properties._smooth = true
        // fs.writeFileSync("smooth" + movement + ".json", JSON.stringify(f1, null, 2), { mode: 0o644 })

        // redo everything on smooth path
        speedsAtVertices = (f1.hasOwnProperty("properties") && f1.properties.hasOwnProperty("speedsAtVertices")) ? f1.properties.speedsAtVertices : null
        pausesAtVertices = (f1.hasOwnProperty("properties") && f1.properties.hasOwnProperty("pausesAtVertices")) ? f1.properties.pausesAtVertices : null
        altsAtVertices = (f1.hasOwnProperty("properties") && f1.properties.hasOwnProperty("altsAtVertices")) ? f1.properties.altsAtVertices : null
        ls = f1.geometry.coordinates // linestring

        speeds = []
        pauses = []
        alts = []

        if (Array.isArray(speedsAtVertices)) {
            speedsAtVertices.forEach(function(sp) {
                if (sp.idx < ls.length)
                    speeds[sp.idx] = sp.speed
            })
        } else {
            speeds[ls.length - 1] = speed
        }
        fillSpeed(speeds, ls.length, parseFloat(options.minSpeed), speed) // init speed array
        eta(ls, speeds)

        if (Array.isArray(pausesAtVertices)) {
            pausesAtVertices.forEach(function(wt) {
                if (wt.idx < ls.length)
                    pauses[wt.idx] = wt.pause
            })
        }

        if (options.altitude && (!Array.isArray(altsAtVertices) || !(altsAtVertices.length > 0))) {
            altsAtVertices = mkAltsAtVertices(ls)
        }

        if (options.altitude && Array.isArray(altsAtVertices)) {
            altsAtVertices.forEach(function(wt) {
                if (wt.idx < ls.length)
                    alts[wt.idx] = wt.alt
            })
            //console.log("Altitude::BEFORE", util.inspect(alts, {depth: null, colors: true, maxArrayLength: null}))
            fillAltitude(alts, ls.length) // init altitude array
            //console.log("Altitude::AFTER", util.inspect(alts, {depth: null, colors: true, maxArrayLength: null}))
            // place altitude on points
            ls.forEach(function(p, idx) {
                if (p.length == 2) { // has only 2 coord, so we add alt
                    p[2] = alts[idx]
                }
            })
        }
    }

    let maxstep = speed * rate / 3600
    let currpos = ls[lsidx] // start pos
    emit({
        options: options,
        newls: newls,
        oldls: ls,
        t: time,
        p: currpos,
        s: "s",
        pts: points,
        spd: speeds[0],
        cmt: "start",
        idx: lsidx,
        alt: options.altitude ? linear_interpolate(currpos, lsidx, ls, alts) : false,
        props: staticProperties
    })
    let timeleft2vtx = 0 // time to next point
    let to_next_emit = rate

    while (lsidx < ls.length - 1) { // note: currpos is between ls[lsidx] and ls[lsidx+1]
        let nextvtx = ls[lsidx + 1] // next point (local target)
        timeleft2vtx = time2vtx(options, currpos, lsidx, ls, speeds, rate) // time to next point
        debug.print(timeleft2vtx + " sec to next vertex", rate, to_next_emit)

        if ((to_next_emit > 0) && (to_next_emit < rate) && (timeleft2vtx > to_next_emit)) { // If next vertex far away, we move during to_next_emit on edge and emit
            debug.print("moving from vertex with time remaining.. (" + lsidx + ")", nextvtx, to_next_emit, timeleft2vtx) // if we are here, we know we will not reach the next vertex
            time += to_next_emit // during this to_next_emit time 
            let p = point_in_rate_sec(options, currpos, to_next_emit, lsidx, ls, speeds, maxstep)
            emit({
                options: options,
                newls: newls,
                oldls: ls,
                t: time,
                p: p,
                s: "e",
                pts: points,
                spd: linear_interpolate(p, lsidx, ls, speeds),
                cmt: "moving from vertex with time remaining",
                idx: lsidx,
                alt: options.altitude ? linear_interpolate(currpos, lsidx, ls, alts) : false,
                props: staticProperties
            })
            //let d0 = distance(currpos,p)
            //debug.print("..done moving from vertex with time remaining. Moved ", d0+" in "+to_next_emit+" secs.", rate + " sec left before next emit, NOT jumping to next vertex")
            currpos = p
            to_next_emit = rate // time before next emit reset to standard rate
            timeleft2vtx = time2vtx(options, currpos, lsidx, ls, speeds, rate) // time to next point
            debug.print(timeleft2vtx + " sec to next vertex (new eval)", rate, to_next_emit)
        }

        if ((to_next_emit < rate) && (to_next_emit > 0) && (timeleft2vtx < to_next_emit)) { // may be portion of segment left
            debug.print("moving to next vertex with time left.. (" + lsidx + ")", nextvtx, to_next_emit, timeleft2vtx)
            time += timeleft2vtx
            emit({
                options: options,
                newls: newls,
                oldls: ls,
                t: time,
                p: nextvtx,
                s: (lsidx == (ls.length - 2)) ? "f" : "v" + (lsidx + 1),
                pts: points,
                spd: speeds[lsidx + 1],
                cmt: "moving on edge with time remaining to next vertex",
                idx: lsidx,
                alt: options.altitude ? linear_interpolate(currpos, lsidx, ls, alts) : false,
                props: staticProperties
            })
            currpos = nextvtx
            to_next_emit -= timeleft2vtx // time left before next emit
            let timing = pauseAtVertex(options, { "time": time, "left": to_next_emit }, pauses[lsidx + 1] ? pauses[lsidx + 1] : null, rate, newls, nextvtx, lsidx + 1, ls.length, points, speeds, ls, staticProperties)
            time = timing.time
            to_next_emit = timing.left
            //debug.print("..done moving to next vertex with time left.", to_next_emit + " sec left before next emit, moving to next vertex")
        } else {
            while (rate < timeleft2vtx) { // we will report position(s) along the edge before reaching the vertex
                debug.print("moving on edge..", rate, timeleft2vtx)
                time += rate
                let p = point_in_rate_sec(options, currpos, rate, lsidx, ls, speeds, maxstep)
                emit({
                    options: options,
                    newls: newls,
                    oldls: ls,
                    t: time,
                    p: p,
                    s: "e",
                    pts: points,
                    spd: linear_interpolate(p, lsidx, ls, speeds),
                    cmt: "en route",
                    idx: lsidx,
                    alt: options.altitude ? linear_interpolate(currpos, lsidx, ls, alts) : false,
                    props: staticProperties
                })
                //debug.print("in "+ rate + " sec moved",distance(currpos,p)+" km")
                currpos = p
                timeleft2vtx = time2vtx(options, currpos, lsidx, ls, speeds, rate)
                //debug.print("..done moving on edge", rate, timeleft2vtx)
            }

            if (timeleft2vtx > 0) { // may be portion of segment left
                let d0 = turf.distance(currpos, nextvtx)
                debug.print("jumping to next vertex..", nextvtx, d0 + " km", timeleft2vtx + " secs")
                time += timeleft2vtx
                emit({
                    options: options,
                    newls: newls,
                    oldls: ls,
                    t: time,
                    p: nextvtx,
                    s: (lsidx == (ls.length - 2)) ? "f" : "v" + (lsidx + 1),
                    pts: points,
                    spd: speeds[lsidx + 1],
                    cmt: (lsidx == (ls.length - 2)) ? "at last vertex" : "at vertex",
                    idx: lsidx,
                    alt: options.altitude ? linear_interpolate(currpos, lsidx, ls, alts) : false,
                    props: staticProperties
                })
                currpos = nextvtx
                to_next_emit = rate - timeleft2vtx // time left before next emit
                let timing = pauseAtVertex(options, { "time": time, "left": to_next_emit }, pauses[lsidx + 1] ? pauses[lsidx + 1] : null, rate, newls, nextvtx, lsidx + 1, ls.length, points, speeds, ls, staticProperties)
                time = timing.time
                to_next_emit = timing.left
                //debug.print(".. done jumping to next vertex.", to_next_emit + " sec left before next emit")
            }
        }

        lsidx += 1
    }
    f.geometry.coordinates = newls
    // they are no longer valid:
    if (f.properties.hasOwnProperty("speedsAtVertices"))
        delete(f.properties.speedsAtVertices)
    if (f.properties.hasOwnProperty("pausesAtVertices"))
        delete(f.properties.pausesAtVertices)
    if (f.properties.hasOwnProperty("altsAtVertices"))
        delete(f.properties.altsAtVertices)
    debug.print("new ls length", newls.length)
    return { "feature": f, "points": points }
};