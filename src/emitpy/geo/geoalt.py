import struct
import os

from osgeo import gdal, gdalconst

# from ..parameters import XPLANE_DIR
XPLANE_DIR = "/Users/pierre/Developer/aero/emit/emitpy/data/x-plane"

# DATA:
# source_url='http://www.ngdc.noaa.gov/mgg/topo/DATATILES/elev/',
# header_url='http://www.ngdc.noaa.gov/mgg/topo/elev/esri/hdr/',
# dem_files='a10g,b10g,c10g,d10g,e10g,f10g,g10g,h10g,i10g,j10g,k10g,l10g,m10g,n10g,o10g,p10g',
#
# for emitpy, files are located in x-plane folder, globe subfolder.
# files are shared/used by little navmap to estimate ground profile.
#


class GeoAlt:
    def __init__(self, globe_location) -> None:
        self.dem_paths = {c: os.path.join(globe_location, c + "10g") for c in "abcdefghijklmnop"}
        for f in self.dem_paths.values():
            if not os.path.exists(f):
                print(f"{f} not found")

    def find_dem(self, lon, lat) -> str:
        """
        Given a particular longitude and latitude, finds the file that contains data on that point
        """
        x = 3
        if lon < -90:
            x = 0
        elif lon < 0:
            x = 1
        elif lon < 90:
            x = 2
        y = 0
        if lat < -50:
            y = 3
        elif lat < 0:
            y = 2
        elif lat < 50:
            y = 1
        xy = y * 4 + x
        return chr(97 + xy)

    def get_dataset(self, lon, lat):
        c = self.find_dem(lon, lat)
        return gdal.Open(self.dem_paths[c])

    def altitude_at_raster_range(self, x1, y1, dataset1, x2, y2, dataset2):
        """
        Returns a two dimensional matrix of altitudes, in meters, for a range of two x", "y raster points.
        Requires a DEM dataset with corresponding data for the given x", "y points
        """

        # the altitude data will be stored in raster band 1
        dem_band = dataset1.GetRasterBand(1)

        min_x = int(min(x1, x2))
        max_x = int(max(x1, x2))
        min_y = int(min(y1, y2))
        max_y = int(max(y1, y2))

        scanline_width = max_x - min_x + 1
        scanline_data_format = "<" + ("h" * scanline_width)

        data = []
        for y in range(min_y, max_y + 1):
            scanline = dem_band.ReadRaster(min_x, y, scanline_width, 1, scanline_width, 1, gdalconst.GDT_Int16)
            values = struct.unpack(scanline_data_format, scanline)
            data.append(values)
        return data

    def altitude_at_raster_point(self, x, y, dataset):
        """
        Returns the altitude, in meters, for a given x/y raster point. Requires a DEM dataset with
        corresponding data for the given x/y point
        """
        values = self.altitude_at_raster_range(x, y, dataset, x, y, dataset)
        return values[0][0]

    def altitude_at_geographic_range(self, lon1, lat1, lon2, lat2):
        """
        Returns a two dimensional matrix of altitudes, in meters, for a given longitude/latitude range.
        Requires a DEM dataset with corresponding data for the given lon/lat values
        """
        x1, y1, dataset1 = self.geographic_coordinates_to_raster_points(lon1, lat1)
        x2, y2, dataset2 = self.geographic_coordinates_to_raster_points(lon2, lat2)
        return self.altitude_at_raster_range(x1, y1, dataset1, x2, y2, dataset2)

    def altitude_at_geographic_coordinates(self, lon, lat):
        """
        Returns the altitude, in meters, for a given longitude/latitude coordinate. Requires a DEM dataset with
        corresponding data for the given lon/lat
        """
        x, y, dataset = self.geographic_coordinates_to_raster_points(lon, lat)
        return self.altitude_at_raster_point(x, y, dataset)

    def geographic_coordinates_to_raster_points(self, lon, lat):
        """
        Converts a set of lon/lat points to x/y points using affine transformation. Note that the conversion is tied to the
        particular dataset. A particular lon/lat value will result in a different x/y point accross different datasets
        """
        dataset = self.get_dataset(lon, lat)
        transform = dataset.GetGeoTransform()
        # invert transformation so we can convert lat/lon to x/y
        transform_inverse = gdal.InvGeoTransform(transform)  # success, transform_inverse
        # apply transformation
        x, y = gdal.ApplyGeoTransform(transform_inverse, lon, lat)
        return (x, y, dataset)


# TEST

# coord_list = [[50.5, 6.1], [50.81, 4.33], [51.26, 3.0]]  # ~ 625m, 88m, 3m.
# g = GeoAlt(globe_location=os.path.join(XPLANE_DIR, "globe"))

# for coords in coord_list:
#     print(coords, f"{g.altitude_at_geographic_coordinates(lat=coords[0], lon=coords[1])} m")
