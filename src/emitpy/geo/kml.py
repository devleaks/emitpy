# Creates KML 3D flight path for visualisation in Google Earth or alike
from typing import List
from emitpy.geo.turf import Feature


def header(name: str, desc: str) -> str:
    """Create XML header for KML
    Args:
        name (str): Title of KML file
        desc (str): Optional description of file content

    Returns:
        str: KML formatted string (XML)
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
    <Document>
        <name>{ name }</name>
        <description>
            <![CDATA[{ desc }]]>
        </description>
        <Style id="emitpysty">
            <LineStyle><color>7f00ffff</color><width>4</width></LineStyle>
            <PolyStyle><color>7f00ff00</color></PolyStyle>
        </Style>
        <Placemark>
            <name>{ name }</name>
            <description>{ desc }</description>
            <styleUrl>#emitpysty</styleUrl>
            <LineString>
                <extrude>1</extrude>
                <tesselate>1</tesselate>
                <altitudeMode>absolute</altitudeMode>
                <coordinates>
"""


def footer() -> str:
    """Create XML footer for KML
    Returns:
        str: KML formatted string (XML)
    """
    return """                </coordinates>
            </LineString>
        </Placemark>
    </Document>
</kml>
"""


def toKML(path: List[Feature], name: str = "Flight Path", desc: str = "Emitpy Flight Path") -> str:
    """Convert list of features to KML for Google Earth
    Args:
        path (List[Feature]): List of Features to convert

    Returns:
        str: KML string
    """
    kml = header(name, desc)
    for f in path:
        # -117.184650,34.627964,980
        if f.geometry.type == "Point" and len(f.geometry.coordinates) > 2:
            c = f.geometry.coordinates
            kml = kml + f"{c[0]},{c[1]},{round(c[2], 3)}\n"
    kml = kml + footer()
    return kml
