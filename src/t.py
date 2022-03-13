import time


class Ex:

    def __init__(self):
        self.inited = False
        self.bigarr = []

    def init(self):
        time.sleep(100)
        self.bigarr[0] = 0
        self.inited = True

    def do_it(self):
        if self.inited:
            time.sleep(100)
            print(self.bigarr[0])
