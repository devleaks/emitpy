#  Python classes to format features for output to different channel requirements
#
import logging
import datetime
import json

from emitpy.constants import FEATPROP
from emitpy.airport import Airport
from emitpy.utils import FT, NAUTICAL_MILE

from .format import Formatter

logger = logging.getLogger("IATAMessageFormatter")


XML_TEMPLATE = f"""
<IATA_OperationalAircraftTurnaroundTimestampNotifRQ xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns="http://www.iata.org/IATA/2015/00/2021.1/IATA_OperationalAircraftTurnaroundTimeStampNotifRQ">
  <Payload>
    <DatedOperatingFlight>
      <operationalSuffixTextField>{a.OperatingAirline}</operationalSuffixTextField>
      <AdministratingCarrierFlightNumberText>{a.FlightNumber}</AdministratingCarrierFlightNumberText>
      <AirlineDesigCode>AirlineDesigCode</AirlineDesigCode>
      <DatedOperatingLeg>
        <Aircraft>
          <aircraftRegistrationIDField>AircraftRegistrationID</aircraftRegistrationIDField>
          <AircraftRegistrationID>{a.AircraftRegistation}</AircraftRegistrationID>
        </Aircraft>
      </DatedOperatingLeg>
      <FlightID_Date>{a.FlightID_Date}</FlightID_Date>
      <OperationalSuffixText>A</OperationalSuffixText>
    </DatedOperatingFlight>
    <SupplementaryInfo>
      <RemarkText>RemarkText</RemarkText>
    </SupplementaryInfo>
    <TimeModeCode>UTC</TimeModeCode>
    <TurnaroundTimestamp>
      <ActualDateTime>{a.ActualDateTime}</ActualDateTime>
      <Event>
        <DelayCode>DelayCode</DelayCode>
        <EventTypeCode>Event</EventTypeCode>
        <ReasonText>ReasonText</ReasonText>
      </Event>
      <Resource>
        <ResourceCode>ResourceCode</ResourceCode>
        <ResourceID>ResourceID1</ResourceID>
        <ResourceID>ResourceID2,</ResourceID>
        <ResourceNumber>ResourceNumber</ResourceNumber>
      </Resource>
      <ScheduledDateTime>{a.ScheduledDateTime}</ScheduledDateTime>
      <TimestampCategoryID>1</TimestampCategoryID>
      <TimestampCodeID>2</TimestampCodeID>
      <TimestampTypeID>1</TimestampTypeID>
      <TurnaroundPhaseID>6</TurnaroundPhaseID>
    </TurnaroundTimestamp>
  </Payload>
  <PayloadAttributes>
    <TrxID>TrxID</TrxID>
    <VersionNumber>20.12</VersionNumber>
  </PayloadAttributes>
  <SenderInfo>
    <ContactInfoText>ContactInfoText</ContactInfoText>
    <ContactName>ContactName</ContactName>
    <OriginAddressText>OriginAddressText</OriginAddressText>
    <OriginSystemName>OriginSystemName</OriginSystemName>
  </SenderInfo>
</IATA_OperationalAircraftTurnaroundTimestampNotifRQ>
"""

class RTTFCFormatter(Formatter):

    FILE_FORMAT = "csv"

    def __init__(self, feature: "FeatureWithProps"):
        Formatter.__init__(self, feature=feature)
        self.name = "rttfc"

    def __str__(self):
        # RTTFC,hexid, lat, lon, baro_alt, baro_rate, gnd, track, gsp, cs_icao, ac_type, ac_tailno,
        #       from_iata, to_iata, timestamp, source, cs_iata, msg_type, alt_geom, IAS, TAS, Mach,
        #       track_rate, roll, mag_heading, true_heading, geom_rate, emergency, category,
        #       nav_qnh, nav_altitude_mcp, nav_altitude_fms, nav_heading, nav_modes, seen, rssi,
        #       winddir, windspd, OAT, TAT, isICAOhex,augmentation_status,authentication
        f = self.feature

        icao24x = f.getProp("icao24")
        hexid = int(icao24x, 16)

        coords = f.coords()
        lat= coords[1]
        lon= coords[0]

        baro_alt = f.altitude(0) / FT  # m -> ft
        baro_rate = f.getProp("")

        airborne = (alt > 0 and speed > 20)
        gnd = not airborne  # :-)

        track = f.getProp("heading")
        gsp = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn
        cs_icao= f.getProp("")
        ac_type= f.getProp("aircraft:actype:actype")  # ICAO
        ac_tailno = f.getProp("aircraft:acreg")
        from_iata = f.getProp("departure:iata")
        to_iata = f.getProp("arrival:iata")

        timestamp = f.getProp(FEATPROP.EMIT_ABS_TIME.value)

        source = "emitpy"

        cs_iata = f.getProp("")
        msg_type = f.getProp("")
        alt_geom = f.getProp("")
        ias = f.getProp("")
        tas = f.getProp("")
        mach = f.getProp("")
        track_rate = f.getProp("")
        roll = f.getProp("")
        mag_heading = f.getProp("")
        true_heading = f.getProp("")
        geom_rate = f.getProp("")
        emergency = f.getProp("")
        category, = f.getProp("")
        nav_qnh = f.getProp("")
        nav_altitude_mcp = f.getProp("")
        nav_altitude_fms = f.getProp("")
        nav_heading = f.getProp("")
        nav_modes = f.getProp("")
        seen = f.getProp("")
        rssi, = f.getProp("")
        winddir = f.getProp("")
        windspd = f.getProp("")
        oat = f.getProp("")
        tat = f.getProp("")
        isicaohex = f.getProp("")
        augmentation_status = f.getProp("")
        authentication = f.getProp("")

        coords = f.coords()

        alt = f.altitude(0) / FT  # m -> ft

        vspeed = f.vspeed(0) * FT * 60  # m/s -> ft/min
        speed = f.speed(0) * 3.6 / NAUTICAL_MILE  # m/s in kn

        heading = f.getProp(FEATPROP.HEADING.value)

        actype = f.getProp("aircraft:actype:actype")  # ICAO
        if f.getProp("service-type") is not None:  # service
            callsign = f.getProp("vehicle:callsign").replace(" ","").replace("-","")
        else:  # fight
            callsign = f.getProp("aircraft:callsign").replace(" ","").replace("-","")
        tailnumber = f.getProp("aircraft:acreg")
        aptfrom = f.getProp("departure:icao")     # IATA
        aptto = f.getProp("arrival:icao")  # IATA
        ts = f.getProp(FEATPROP.EMIT_ABS_TIME.value)

        rttfc = f"RTTFC,{hexid},{lat},{lon},{baro_alt},{baro_rate},{gnd},{track},{gsp},{cs_icao},{ac_type},{ac_tailno},"
              + f"{from_iata},{to_iata},{timestamp},{source},{cs_iata},{msg_type},{alt_geom},{ias},{tas},{mach},"
              + f"{track_rate},{roll},{mag_heading},{true_heading},{geom_rate},{emergency},{category},"
              + f"{nav_qnh},{nav_altitude_mcp},{nav_altitude_fms},{nav_heading},{nav_modes},{seen},{rssi},"
              + f"{winddir},{windspd},{oat},{tat},{isicaohex},{augmentation_status},{authentication}"
        return rttfc.replace("None", "")
