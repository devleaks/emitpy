"""
A Transporter is company that organize transport of goods from a departure location to an arrival location in Transport Vehicles.

"""
from company import Company

from constants import TRANSPORTER, BULK


class Transporter(Company):

    def __init__(self, name: str):
        Company.__init__(self, name, TRANSPORTER, BULK, name)
