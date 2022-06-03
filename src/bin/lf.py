import os
import sys
import json
import redis
from redis.commands.json.path import Path

r = redis.StrictRedis()


class Flight(object):

    __default_text = "N/A"

    def __init__(self, flight_id, info):

        self.id = flight_id
        self.icao_24bit = self.__get_info(info[0])
        self.latitude = self.__get_info(info[1])
        self.longitude = self.__get_info(info[2])
        self.heading = self.__get_info(info[3])
        self.altitude = self.__get_info(info[4])
        self.ground_speed = self.__get_info(info[5])
        self.squawk = self.__get_info(info[6])
        self.aircraft_code = self.__get_info(info[8])
        self.registration = self.__get_info(info[9])
        self.time = self.__get_info(info[10])
        self.origin_airport_iata = self.__get_info(info[11])
        self.destination_airport_iata = self.__get_info(info[12])
        self.number = self.__get_info(info[13])
        self.airline_iata = self.__get_info(info[13][:2])
        self.on_ground = self.__get_info(info[14])
        self.vertical_speed =self.__get_info(info[15])
        self.callsign = self.__get_info(info[16])
        self.airline_icao = self.__get_info(info[18])


kn = sys.argv[1]
fn = sys.argv[2]  # os.path.join("..", "..", "data", "aircraft_types", "aircraft-performances.json")
with open(fn) as data_file:
    test_data = json.load(data_file)
r.json().set(kn, Path.root_path(), test_data)