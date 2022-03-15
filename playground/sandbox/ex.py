import time


class Ex:

    PERM = 1
    inited = False
    bigarr = []

    @staticmethod
    def init():
        time.sleep(1)
        if len(Ex.bigarr) > 0:
            Ex.bigarr[0] = Ex.bigarr[0] + 1
        else:
            Ex.bigarr.append(2)
        Ex.PERM = Ex.PERM + 10
        Ex.inited = True
        print("Ex: inited")

    @staticmethod
    def do_it():
        if not Ex.inited:
            Ex.init()
        Ex.PERM = Ex.PERM + 1

        time.sleep(1)
        return (Ex.bigarr[0], Ex.PERM)
