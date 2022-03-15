import time


class Ex:

    PERM = 1

    def __init__(self):
        self.inited = False
        self.bigarr = []

    def init(self):
        time.sleep(1)
        if len(self.bigarr) > 0:
            self.bigarr[0] = self.bigarr[0] + 1
        else:
            self.bigarr.append(2)
        Ex.PERM = Ex.PERM + 10
        self.inited = True

    def do_it(self):
        if not self.inited:
            self.init()
        Ex.PERM = Ex.PERM + 1

        time.sleep(1)
        return (self.bigarr[0], Ex.PERM)
