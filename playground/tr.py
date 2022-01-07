from collections import namedtuple
from rbush import RBush, BBox


def arrToBBox(arr):
    """
    Convert arrays of 4 values to BBox
    """
    minX, minY, maxX, maxY = arr
    return BBox(minX, maxX, minY, maxY)


def defaultCompare(a, b):
    return (a.minX - b.minX) != 0 or (a.minY - b.minY) != 0 or (
        a.maxX - b.maxX) != 0 or (a.maxY - b.maxY) != 0


def someData(n):
    data = []
    for i in range(n):
        data.append(arrToBBox([i, i, i, i]))
    return data


def moreData():
    return [[0, 0, 0, 0], [10, 10, 10, 10], [20, 20, 20, 20], [25, 0, 25, 0],
            [35, 10, 35, 10], [45, 20, 45, 20], [0, 25, 0,
                                                 25], [10, 35, 10, 35],
            [20, 45, 20, 45], [25, 25, 25, 25], [35, 35, 35, 35],
            [45, 45, 45, 45],
            [50, 0, 50, 0], [60, 10, 60, 10], [70, 20, 70, 20], [75, 0, 75, 0],
            [85, 10, 85, 10], [95, 20, 95, 20], [50, 25, 50, 25],
            [60, 35, 60, 35], [70, 45, 70, 45], [75, 25, 75, 25],
            [85, 35, 85, 35], [95, 45, 95, 45], [0, 50, 0,
                                                 50], [10, 60, 10, 60],
            [20, 70, 20, 70], [25, 50, 25, 50], [35, 60, 35, 60],
            [45, 70, 45, 70], [0, 75, 0, 75], [10, 85, 10,
                                               85], [20, 95, 20, 95],
            [25, 75, 25, 75], [35, 85, 35, 85], [45, 95, 45, 95],
            [50, 50, 50, 50], [60, 60, 60, 60], [70, 70, 70, 70],
            [75, 50, 75, 50], [85, 60, 85, 60], [95, 70, 95, 70],
            [50, 75, 50, 75], [60, 85, 60, 85], [70, 95, 70, 95],
            [75, 75, 75, 75], [85, 85, 85, 85], [95, 95, 95, 95]]


def emptyData():
    return [[-Infinity, -Infinity, Infinity, Infinity],
            [-Infinity, -Infinity, Infinæity, Infinity],
            [-Infinity, -Infinity, Infinity, Infinity],
            [-Infinity, -Infinity, Infinity, Infinity],
            [-Infinity, -Infinity, Infinity, Infinity],
            [-Infinity, -Infinity, Infinity, Infinity]]


def mkBboxFromArr(arr):
    return list(map(lambda x: arrToBBox(x), arr))


# T E S T I N G
#
#
def sortedEqual(a, b, compare):
    compare = compare if compare else defaultCompare
    assert sorted(a.copy(), key=compare) == sorted(b.copy(), key=compare)


# Loading
print("loading..")
rbush = RBush()
mbdata = mkBboxFromArr(moreData())
rbush.load(mbdata)
sortedEqual(rbush.all(), mbdata)
print("..done")

# Bounding box
print("simple bbox..")
class MyRBush(RBush):
    def toBBox(self, a):
        return BBox(a.minLng, a.maxLng, a.minLat, a.maxLat)

    def compareMinX(self, a, b):
        return a.minLng - b.minLng

    def compareMinY(self, a, b):
        return a.minLat - b.minLat;

tree = MyRBush(4)
A = namedtuple("A", "minLng maxLng minLat maxLat")
a = A(1, 2, 3, 4)
sortedEqual(tree.toBBox(a), BBox(1, 2, 3, 4))
print("..done")
