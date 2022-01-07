import math
from quickselect import quickselect


class RBush:
    def __init__(self, maxEntries=9):
        self._maxEntries = max([4, maxEntries])
        self._minEntries = max([2, math.ceil(self._maxEntries * 0.4)])
        self.data = None
        self.clear()

    def all(self):
        return self._all(self.data, [])

    def search(self, bbox):
        node = self.data
        result = []
        if not intersects(bbox, node):
            return result
        toBBox = self.toBBox
        nodesToSearch = []

        return result

    def collides(self, bbox):
        node = self.data
        if not intersects(bbox, node):
            return False
        nodesToSearch = []

        return False

    def load(self, data):
        if not data and len(data):
            return self
        if len(data) < self._minEntries:
            for i in range(0, len(data)):
                self.insert(data[i])
            return self
        node = self._build(data.copy(), 0, len(data) - 1, 0)
        if not len(self.data["children"]):
            self.data = node
        elif self.data["height"] == node["height"]:
            self._splitRoot(self.data, node)
        else:
            if self.data["height"] < node["height"]:
                tmpNode = self.data
                self.data = node
                node = tmpNode
            self._insert(node, (self.data["height"] - node["height"]) - 1, True)
        return self

    def insert(self, item):
        if item:
            self._insert(item, self.data["height"] - 1)
        return self

    def clear(self):
        self.data = createNode([])
        return self

    def remove(self, item, equalsFn):
        if not item:
            return self
        node = self.data
        bbox = self.toBBox(item)
        path = []
        indexes = []
        return self

    def toBBox(self, item):
        return item

    def compareMinX(self, a, b):
        return a["minX"] - b["minX"]

    def compareMinY(self, a, b):
        return a["minY"] - b["minY"]

    def toJSON(self):
        return self.data

    def fromJSON(self, data):
        self.data = data
        return self

    def _all(self, node, result):
        nodesToSearch = []

        return result

    def _build(self, items, left, right, height):
        N = (right - left) + 1
        M = self._maxEntries

        if N <= M:
            node = createNode(items[left:right + 1].copy())
            calcBBox(node, self.toBBox)
            return node
        if not height:
            height = math.ceil(math.log(N) / math.log(M))
            M = math.ceil(N / math.pow(M, height - 1))
        node = createNode([])
        node["leaf"] = False
        node["height"] = height
        N2 = math.ceil(N / M)
        N1 = N2 * math.ceil(math.sqrt(M))
        multiSelect(items, left, right, N1, self.compareMinX)
        for i in range(left, right):
            right2 = min([(i + N1) - 1, right])
            multiSelect(items, i, right2, N2, self.compareMinY)
            for j in range(i, right2):
                right3 = min([(j + N2) - 1, right2])
                node["children"].append(self._build(items, j, right3, height - 1))
        calcBBox(node, self.toBBox)
        return node

    def _chooseSubtree(self, bbox, node, level, path):

        return node

    def _insert(self, item, level, isNode=False):
        bbox = item if isNode else self.toBBox(item)
        insertPath = []
        node = self._chooseSubtree(bbox, self.data, level, insertPath)
        node["children"].append(item)
        extend(node, bbox)

        self._adjustParentBBoxes(bbox, insertPath, level)

    def _split(self, insertPath, level):
        node = insertPath[level]
        M = len(node["children"])
        m = self._minEntries
        self._chooseSplitAxis(node, m, M)
        splitIndex = self._chooseSplitIndex(node, m, M)
        newNode = createNode(node["children"].splice(splitIndex, len(node["children"]) - splitIndex))
        newNode["height"] = node["height"]
        newNode.leaf = node["leaf"]
        calcBBox(node, self.toBBox)
        calcBBox(newNode, self.toBBox)
        if level:
            insertPath[level - 1].children.append(newNode)
        else:
            self._splitRoot(node, newNode)

    def _splitRoot(self, node, newNode):
        self.data = createNode([node, newNode])
        self.data["height"] = node["height"] + 1
        self.data["leaf"] = False
        calcBBox(self.data, self.toBBox)

    def _chooseSplitIndex(self, node, m, M):

        minOverlap = math.inf
        minArea = math.inf
        for i in range(m, M - m):
            bbox1 = distBBox(node, 0, i, self.toBBox)
            bbox2 = distBBox(node, i, M, self.toBBox)
            overlap = intersectionArea(bbox1, bbox2)
            area = bboxArea(bbox1) + bboxArea(bbox2)
            if overlap < minOverlap:
                minOverlap = overlap
                index = i
                minArea = area if area < minArea else minArea
            elif overlap == minOverlap:
                if area < minArea:
                    minArea = area
                    index = i
        return index or M - m

    def _chooseSplitAxis(self, node, m, M):
        compareMinX = self.compareMinX if node["leaf"] else compareNodeMinX
        compareMinY = self.compareMinY if node["leaf"] else compareNodeMinY
        xMargin = self._allDistMargin(node, m, M, compareMinX)
        yMargin = self._allDistMargin(node, m, M, compareMinY)
        if xMargin < yMargin:
            node["children"].sort(compareMinX)

    def _allDistMargin(self, node, m, M, compare):
        node["children"].sort(compare)
        toBBox = self.toBBox
        leftBBox = distBBox(node, 0, m, toBBox)
        rightBBox = distBBox(node, M - m, M, toBBox)
        margin = bboxMargin(leftBBox) + bboxMargin(rightBBox)
        for i in range(m, M - m):
            child = node["children"][i]
            extend(leftBBox, toBBox(child) if node["leaf"] else child)
            margin += bboxMargin(leftBBox)
        i = (M - m) - 1
        while i >= m:
            child = node["children"][i]
            extend(rightBBox, toBBox(child) if node["leaf"] else child)
            margin += bboxMargin(rightBBox)
        return margin

    def _adjustParentBBoxes(self, bbox, path, level):
        i = level
        while i >= 0:
            extend(path[i], bbox)

    def _condense(self, path):
        i = len(path) - 1

        while i >= 0:
            if len(path[i].children) == 0:
                if i > 0:
                    siblings = path[i - 1].children
                    del siblings[siblings.indexOf(path[i])]
                else:
                    self.clear()
            else:
                calcBBox(path[i], self.toBBox)


def findItem(item, items, equalsFn):
    if not equalsFn:
        return items.indexOf(item)
    for i in range(0, len(items)):
        if equalsFn(item, items[i]):
            return i
    return -1


def calcBBox(node, toBBox):
    distBBox(node, 0, len(node["children"]), toBBox, node)


def distBBox(node, k, p, toBBox, destNode=None):
    if not destNode:
        destNode = createNode(None)
    destNode["minX"] = math.inf
    destNode["minY"] = math.inf
    destNode["maxX"] = -math.inf
    destNode["maxY"] = -math.inf
    for i in range(k, p):
        child = node["children"][i]
        extend(destNode, toBBox(child) if "leaf" in node and node["leaf"] else child)
    return destNode


def extend(a, b):
    a["minX"] = min([a["minX"], b["minX"]])
    a["minY"] = min([a["minY"], b["minY"]])
    a["maxX"] = max([a["maxX"], b["maxX"]])
    a["maxY"] = max([a["maxY"], b["maxY"]])
    return a


def compareNodeMinX(a, b):
    return a["minX"] - b["minX"]


def compareNodeMinY(a, b):
    return a["minY"] - b["minY"]


def bboxArea(a):
    return (a["maxX"] - a["minX"]) * (a["maxY"] - a["minY"])


def bboxMargin(a):
    return (a["maxX"] - a["minX"]) + (a["maxY"] - a["minY"])


def enlargedArea(a, b):
    return (max([b["maxX"], a["maxX"]]) - min([b["minX"], a["minX"]])) * (max([b["maxY"], a["maxY"]]) - min([b["minY"], a["minY"]]))


def intersectionArea(a, b):
    minX = max([a["minX"], b["minX"]])
    minY = max([a["minY"], b["minY"]])
    maxX = min([a["maxX"], b["maxX"]])
    maxY = min([a["maxY"], b["maxY"]])
    return max([0, maxX - minX]) * max([0, maxY - minY])


def contains(a, b):
    return a["minX"] <= b["minX"] and a["minY"] <= b["minY"] and b["maxX"] <= a["maxX"] and b["maxY"] <= a["maxY"]


def intersects(a, b):
    return b["minX"] <= a["maxX"] and b["minY"] <= a["maxY"] and b["maxX"] >= a["minX"] and b["maxY"] >= a["minY"]


def createNode(children):
    return {
      'children': children,
      'height': 1,
      'leaf': True,
      'minX': math.inf,
      'minY': math.inf,
      'maxX': -math.inf,
      'maxY': -math.inf
    }


def multiSelect(arr, left, right, n, compare):
    stack = [left, right]


def arrToBBox(arr):
    minX, minY, maxX, maxY = arr
    return {"minX": minX, "minY": minY, "maxX": maxX, "maxY": maxY}


data = [[0,0,0,0],[10,10,10,10],[20,20,20,20],[25,0,25,0],[35,10,35,10],[45,20,45,20],[0,25,0,25],[10,35,10,35],
    [20,45,20,45],[25,25,25,25],[35,35,35,35],[45,45,45,45],[50,0,50,0],[60,10,60,10],[70,20,70,20],[75,0,75,0],
    [85,10,85,10],[95,20,95,20],[50,25,50,25],[60,35,60,35],[70,45,70,45],[75,25,75,25],[85,35,85,35],[95,45,95,45],
    [0,50,0,50],[10,60,10,60],[20,70,20,70],[25,50,25,50],[35,60,35,60],[45,70,45,70],[0,75,0,75],[10,85,10,85],
    [20,95,20,95],[25,75,25,75],[35,85,35,85],[45,95,45,95],[50,50,50,50],[60,60,60,60],[70,70,70,70],[75,50,75,50],
    [85,60,85,60],[95,70,95,70],[50,75,50,75],[60,85,60,85],[70,95,70,95],[75,75,75,75],[85,85,85,85],[95,95,95,95]]

databb = list(map(lambda x: arrToBBox(x), data))

## print(databb)

b = RBush()

b.load(databb)
print("loaded")
