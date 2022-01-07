"""
Manage triple of scheduled/estimated/actual for timed events.
"""


class Datetime:

    def __init__(self, scheduled: str):
        self.__scheduled = scheduled
        self.__estimated = scheduled
        self.__actual = None


    def okToChange(self):
        """
        Should be exceptional

        :param      scheduled:  The scheduled
        :type       scheduled:  str
        """
        if not self.__actual:
            return True
        # should warn actual already set
        return False


    def rescheduled(self, scheduled: str):
        """
        Should be exceptional

        :param      scheduled:  The scheduled
        :type       scheduled:  str
        """
        if self.okToChange():
            self.__scheduled = scheduled
            # should log exceptional event.


    def estimated(self, estimated: str):
        """
        Sets new ETA as computed.

        :param      estimated:  The estimated
        :type       estimated:  str
        """
        if self.okToChange():
            self.__estimated = estimated



    def actual(self, actual: str):
        """
        Setting actual time of event terminates it.

        :param      actual:  The actual
        :type       actual:  str
        """
        if self.okToChange():
            self.__actual = actual
