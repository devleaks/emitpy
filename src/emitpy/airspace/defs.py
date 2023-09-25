# These short cuts, acronyms, etc. are necessary to decode ARINC or CIFP files.
#
#
# ARINC 424 LEG TYPES

# LEG TYPE                                        CODE

# Heading to Altitude                              VA
# Heading to DME Distance                          VD
# Heading to Next Leg Intercept                    VI
# Heading to Manual Termination                    VM
# Heading to a Radial Termination                  VR
# Course to Altitude                               CA
# Course to DME Distance                           CD
# Course to Next Leg Intercept                     CI
# Course to Radial Termination                     CR
# Course to a Fix                                  CF
# Tracking Between Two Fixes                       TF
# Direct to a Fix                                  DF
# Course from a Fix to an Altitude                 FA
# Course from a Fix to an Along Track Distance     FC
# Course from a Fix to a DME Distance              FD
# Course from a Fix to a Manual Termination        FM
# Constant DME Arc to a Fix                        AF
# Hold to a Fix                                    HF
# Hold to an Altitude                              HA
# Hold to a Manual Termination                     HM
# Initial Fix                                      IF
# Procedure Turn to Intercept                      PI
# Radius to a Fix                                  RF
#
#
from enum import Enum


AIRSPACE_TYPES = {
    "AIRSPACE_NONE": "No Airspace",
    "CENTER": "",
    "CLASS_A": "Controlled, above 18,000 ft MSL, IFR, no VFR, ATC clearance required.",
    "CLASS_B": "Controlled, IFR and VFR, ATC clearance required.",
    "CLASS_C": "Controlled, IFR and VFR, ATC clearance required, transponder required.",
    "CLASS_D": "Controlled, IFR and VFR, ATC clearance required.",
    "CLASS_E": "Controlled, IFR and VFR, ATC clearance required for IFR only.",
    "CLASS_F": "Uncontrolled, IFR and VFR, ATC clearance not required.",
    "CLASS_G": "Uncontrolled, IFR and VFR, ATC clearance not required.",
    "FIR": "Uncontrolled, IFR and VFR, ATC clearance not required.",
    "UIR": "Uncontrolled, IFR and VFR, ATC clearance not required.",
    "TOWER": "",
    "CLEARANCE": "",
    "GROUND": "",
    "DEPARTURE": "",
    "APPROACH": "",
    "MOA": "Military operations area. Needs clearance for IFR if active. Check for traffic advisories.",
    "RESTRICTED": "Needs authorization.",
    "PROHIBITED": "No flight allowed.",
    "WARNING": "Contains activity that may be hazardous to aircraft.",
    "CAUTION": "",
    "ALERT": "High volume of pilot training or an unusual type of aerial activity.",
    "DANGER": "Avoid or proceed with caution.",
    "NATIONAL_PARK": "",
    "MODEC": "Needs altitude aware transponder.",
    "RADAR": "Terminal radar area. Not controlled.",
    "GCA": "",
    "MCTR": "",
    "TRSA": "",
    "TRAINING": "",
    "GLIDERPROHIBITED": "",
    "WAVEWINDOW": "Sailplane Area.",
    "ONLINE_OBSERVER": "Online network observer",
}

APPROACH_FIX_TYPES = {
    "IAF": "Initial Approach Fix",
    "FAF": "Final Approach Fix",
    "FACF": "Final Approach Course Fix",
    "MAP": "Missed Approach Point",
    "FEP": "Final Endpoint Fix",
}

APPROACH_FIX = {
    "NONE": "NONE",
    "L": "Localizer",
    "V": "VOR",
    "N": "NDB",
    "TN": "Terminal NDB",
    "W": "Waypoint",
    "TW": "Terminal Waypoint",
    "R": "Runway",
    "CST": "Custom Fix",
}

APPROACH_TYPE = {
    "GPS": "GPS",
    "VOR": "VOR",
    "NDB": "NDB",
    "ILS": "ILS",
    "LOC": "Localizer",
    "SDF": "SDF",
    "LDA": "LDA",
    "VORDME": "VORDME",
    "NDBDME": "NDBDME",
    "RNAV": "RNAV",
    "LOCB": "Localizer Backcourse",
    # Additional types from X-Plane
    "FMS": "FMS",
    "IGS": "IGS",
    "GNSS": "GLS",
    "TCN": "TACAN",
    "CTL": "Circle to Land",
    "MLS": "MLS",
    # User defined approach procedure
    "CUSTOM": "Approach",
    "CUSTOMDEPART": "Departure",
}

APPROACH_LEG_TYPE = {
    "ARC_TO_FIX": "Arc to fix",
    "COURSE_TO_ALTITUDE": "Course to altitude",
    "COURSE_TO_DME_DISTANCE": "Course to DME distance",
    "COURSE_TO_FIX": "Course to fix",
    "COURSE_TO_INTERCEPT": "Course to intercept",
    "COURSE_TO_RADIAL_TERMINATION": "Course to radial termination",
    "DIRECT_TO_FIX": "Direct to fix",
    "FIX_TO_ALTITUDE": "Fix to altitude",
    "TRACK_FROM_FIX_FROM_DISTANCE": "Track from fix from distance",
    "TRACK_FROM_FIX_TO_DME_DISTANCE": "Track from fix to DME distance",
    "FROM_FIX_TO_MANUAL_TERMINATION": "From fix to manual termination",
    "HOLD_TO_ALTITUDE": "Hold to altitude",
    "HOLD_TO_FIX": "Hold to fix",
    "HOLD_TO_MANUAL_TERMINATION": "Hold to manual termination",
    "INITIAL_FIX": "Initial fix",
    "PROCEDURE_TURN": "Procedure turn",
    "CONSTANT_RADIUS_ARC": "Constant radius arc",
    "TRACK_TO_FIX": "Track to fix",
    "HEADING_TO_ALTITUDE_TERMINATION": "Heading to altitude termination",
    "HEADING_TO_DME_DISTANCE_TERMINATION": "Heading to DME distance termination",
    "HEADING_TO_INTERCEPT": "Heading to intercept",
    "HEADING_TO_MANUAL_TERMINATION": "Heading to manual termination",
    "HEADING_TO_RADIAL_TERMINATION": "Heading to radial termination",
    "DIRECT_TO_RUNWAY": "Proceed to runway",
    "CIRCLE_TO_LAND": "Circle to land",
    "STRAIGHT_IN": "Straight in",
    "START_OF_PROCEDURE": "Start of procedure",
    "VECTORS": "Vectors",
    "CUSTOM_APP_START": "Start of final",
    "CUSTOM_APP_RUNWAY": "Final leg",
    "CUSTOM_DEP_END": "Departure leg",
    "CUSTOM_DEP_RUNWAY": "Proceed to runway",
}

APPROACH_LEG_TYPE_ABBREV = {
    "AF": "ARC_TO_FIX",
    "CA": "COURSE_TO_ALTITUDE",
    "CD": "COURSE_TO_DME_DISTANCE",
    "CF": "COURSE_TO_FIX",
    "CI": "COURSE_TO_INTERCEPT",
    "CR": "COURSE_TO_RADIAL_TERMINATION",
    "DF": "DIRECT_TO_FIX",
    "FA": "FIX_TO_ALTITUDE",
    "FC": "TRACK_FROM_FIX_FROM_DISTANCE",
    "FD": "TRACK_FROM_FIX_TO_DME_DISTANCE",
    "FM": "FROM_FIX_TO_MANUAL_TERMINATION",
    "HA": "HOLD_TO_ALTITUDE",
    "HF": "HOLD_TO_FIX",
    "HM": "HOLD_TO_MANUAL_TERMINATION",
    "IF": "INITIAL_FIX",
    "PI": "PROCEDURE_TURN",
    "RF": "CONSTANT_RADIUS_ARC",
    "TF": "TRACK_TO_FIX",
    "VA": "HEADING_TO_ALTITUDE_TERMINATION",
    "VD": "HEADING_TO_DME_DISTANCE_TERMINATION",
    "VI": "HEADING_TO_INTERCEPT",
    "VM": "HEADING_TO_MANUAL_TERMINATION",
    "VR": "HEADING_TO_RADIAL_TERMINATION",
    "RX": "DIRECT_TO_RUNWAY",
    "CX": "CIRCLE_TO_LAND",
    "TX": "STRAIGHT_IN",
    "SX": "START_OF_PROCEDURE",
    "VX": "VECTORS",
    "CFX": "CUSTOM_APP_START",
    "CRX": "CUSTOM_APP_RUNWAY",
    "CDX": "CUSTOM_DEP_END",
    "CDR": "CUSTOM_DEP_RUNWAY",
}


# EN ROUTE LEG TYPES
#
# (VA) Heading To Altitude
# (VD) Heading To DME
# (VI) Heading To Next Leg Intercept
# (VM) Heading To Manual Termination
# (VR) Heading To a Radial
# (CA) Course To Altitude
# (CD) Course To a DME
# (CI) Course To Next Leg Intercept
# (CR) Course To a Radial
# (CF) Course To a Fix
# (TF) Track To a Fix
# (DF) Direct To a Fix
# (FA) Fix To Altitude
# (FC) Fix To a Distance on Course
# (FD) Fix To a DME Termination
# (FM) Fix To a Manual Termination
#

RNAV_LEG_TYPE = {
    "CF": "COURSE_TO_FIX",
    "DF": "DIRECT_TO_FIX",
    "RF": "CONSTANT_RADIUS_ARC",
    "TF": "TRACK_TO_FIX",
}
