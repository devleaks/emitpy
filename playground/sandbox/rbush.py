import math
from quickselect import quickselect


class BBox:
    """
    Bounding box utility class
    """
    def __init__(self, minX, maxX, minY, maxY):
        self.minX = minX
        self.minY = minY
        self.maxX = maxX
        self.maxY = maxY

    def __str__(self):
        return "x=%f,%f y=%f,%f" % (self.minX, self.maxX, self.minY, self.maxY)


class Node(BBox):
    """
    Node box utility class. A Node is a bounding box with attributes
    """
    def __init__(self, minX, maxX, minY, maxY, children, height, leaf=True):
        BBox.__init__(self, minX, maxX, minY, maxY)
        self.children = children
        self.height = height
        self.leaf = leaf


class RBush:
    """
    RBush index.
    """
    def __init__(self, maxEntries=9):
        """
         max entries in a node is 9 by default; min node fill is 40% for best performance
        """
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

        while node:
            for i in range(len(node.children)):
                child = node.children[i]
                childBBox = toBBox(child) if node.leaf else child

                if intersects(bbox, childBBox):
                    if node.leaf:
                        result.append(child)
                    elif contains(bbox, childBBox):
                        self._all(child, result)
                    else:
                        nodesToSearch.append(child)
            node = nodesToSearch.pop()

        return result

    def collides(self, bbox):
        node = self.data
        if not intersects(bbox, node):
            return False
        nodesToSearch = []

        while node:
            for i in range(len(node.children)):
                child = node.children[i]
                childBBox = toBBox(child) if node.leaf else child

                if intersects(bbox, childBBox):
                    if node.leaf or contains(bbox, childBBox):
                        return True
                    nodesToSearch.append(child)
            node = nodesToSearch.pop()

        return False

    def load(self, data):
        if not data or len(data) == 0:
            return self
        if len(data) < self._minEntries:
            for i in range(len(data)):
                self.insert(data[i])
            return self

        # recursively build the tree with the given data from scratch using OMT algorithm
        node = self._build(data.copy(), 0, len(data) - 1, 0)
        if len(self.data.children) == 0:
            # save as is if tree is empty
            self.data = node
        elif self.data.height == node.height:
            self._splitRoot(self.data, node)
        else:
            if self.data.height < node.height:
                #  swap trees if inserted one is bigger
                tmpNode = self.data
                self.data = node
                node = tmpNode
            # insert the small tree into the large tree at appropriate level
            self._insert(node, self.data.height - node.height - 1, True)
        return self

    def insert(self, item):
        if item:
            self._insert(item, self.data.height - 1)
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
        goingUp = None
        parent = None
        i = 0

        # depth-first iterative tree traversal
        while node or len(path) > 0:

            if not node:  # go up
                node = path.pop()
                parent = path[len(path) - 1]
                i = indexes.pop()
                goingUp = True

            if node.leaf:  # check current node
                index = findItem(item, node.children, equalsFn)

                if index != -1:
                    # item found, remove the item and condense tree upwards
                    node.children = node.children[index:index + 1]
                    path.append(node)
                    self._condense(path)
                    return self

            if not goingUp and not node.leaf and contains(node,
                                                          bbox):  # go down
                path.append(node)
                indexes.append(i)
                i = 0
                parent = node
                node = node.children[0]

            elif parent:  # go right
                i += 1
                node = parent.children[i]
                goingUp = False

            else:
                node = None  # nothing found

        return self

    def toBBox(self, item):
        return item

    def compareMinX(self, a, b):
        return a.minX - b.minX

    def compareMinY(self, a, b):
        return a.minY - b.minY

    def toJSON(self):
        return self.data

    def fromJSON(self, data):
        self.data = data
        return self

    def _all(self, node, result):
        nodesToSearch = []
        while node:
            if node.leaf:
                for e in node.children:
                    result.append(e)
            else:
                for e in node.children:
                    nodesToSearch.append(e)

            node = nodesToSearch.pop()
        return result

    def _build(self, items, left, right, height):
        N = (right - left) + 1
        M = self._maxEntries
        node = None

        if N <= M:
            # reached leaf level; return leaf
            node = createNode(items[left:right + 1].copy())
            calcBBox(node, self.toBBox)
            return node
        if not height:
            # target height of the bulk-loaded tree
            height = math.ceil(math.log(N) / math.log(M))
            # target number of root entries to maximize storage utilization
            M = math.ceil(N / math.pow(M, height - 1))
        node = createNode([])
        node.leaf = False
        node.height = height
        # split the items into M mostly square tiles
        N2 = math.ceil(N / M)
        N1 = N2 * math.ceil(math.sqrt(M))
        multiSelect(items, left, right, N1, self.compareMinX)
        for i in range(left, right):
            right2 = min([(i + N1) - 1, right])
            multiSelect(items, i, right2, N2, self.compareMinY)
            for j in range(i, right2):
                right3 = min([(j + N2) - 1, right2])
                # pack each entry recursively
                node.children.append(self._build(items, j, right3, height - 1))
        calcBBox(node, self.toBBox)
        return node

    def _chooseSubtree(self, bbox, node, level, path):

        while True:
            path.append(node)

            if node.leaf or len(path) - 1 == level:
                break

            minArea = math.inf
            minEnlargement = math.inf
            targetNode = None

            for i in len(node.children):
                child = node.children[i]
                area = bboxArea(child)
                enlargement = enlargedArea(bbox, child) - area

                # choose entry with the least area enlargement
                if enlargement < minEnlargement:
                    minEnlargement = enlargement
                    minArea = area if area < minArea else minArea
                    targetNode = child

                elif enlargement == minEnlargement:
                    # otherwise choose one with the smallest area
                    if area < minArea:
                        minArea = area
                        targetNode = child

            node = targetNode if targetNode else node.children[0]

        return node

    def _insert(self, item, level, isNode=False):
        bbox = item if isNode else self.toBBox(item)
        insertPath = []
        # find the best node for accommodating the item, saving all nodes along the path too
        node = self._chooseSubtree(bbox, self.data, level, insertPath)
        # put the item into the node
        node.children.append(item)
        extend(node, bbox)
        # split on node overflow; propagate upwards if necessary
        while level >= 0:
            if insertPath[level].children.length > self._maxEntries:
                self._split(insertPath, level)
                level -= 1
            else:
                break
        # adjust bboxes along the insertion path
        self._adjustParentBBoxes(bbox, insertPath, level)

    def _split(self, insertPath, level):
        node = insertPath[level]
        M = len(node.children)
        m = self._minEntries
        self._chooseSplitAxis(node, m, M)
        splitIndex = self._chooseSplitIndex(node, m, M)
        newNode = createNode(
            node.children.splice(splitIndex,
                                 len(node.children) - splitIndex))
        newNode.height = node.height
        newNode.leaf = node.leaf
        calcBBox(node, self.toBBox)
        calcBBox(newNode, self.toBBox)
        if level:
            insertPath[level - 1].children.append(newNode)
        else:
            self._splitRoot(node, newNode)

    def _splitRoot(self, node, newNode):
        self.data = createNode([node, newNode])
        self.data.height = node.height + 1
        self.data.leaf = False
        calcBBox(self.data, self.toBBox)

    def _chooseSplitIndex(self, node, m, M):

        minOverlap = math.inf
        minArea = math.inf
        for i in range(m, M - m):
            bbox1 = distBBox(node, 0, i, self.toBBox)
            bbox2 = distBBox(node, i, M, self.toBBox)
            overlap = intersectionArea(bbox1, bbox2)
            area = bboxArea(bbox1) + bboxArea(bbox2)
            # choose distribution with minimum overlap
            if overlap < minOverlap:
                minOverlap = overlap
                index = i
                minArea = area if area < minArea else minArea
            elif overlap == minOverlap:
                # otherwise choose distribution with minimum area
                if area < minArea:
                    minArea = area
                    index = i
        return index or M - m

    def _chooseSplitAxis(self, node, m, M):
        """
        sorts node children by the best axis for split
        """
        compareMinX = self.compareMinX if node.leaf else compareNodeMinX
        compareMinY = self.compareMinY if node.leaf else compareNodeMinY
        xMargin = self._allDistMargin(node, m, M, compareMinX)
        yMargin = self._allDistMargin(node, m, M, compareMinY)
        if xMargin < yMargin:
            node.children.sort(compareMinX)

    def _allDistMargin(self, node, m, M, compare):
        """
        total margin of all possible split distributions where each node is at least m full
        """
        node.children.sort(compare)
        toBBox = self.toBBox
        leftBBox = distBBox(node, 0, m, toBBox)
        rightBBox = distBBox(node, M - m, M, toBBox)
        margin = bboxMargin(leftBBox) + bboxMargin(rightBBox)
        for i in range(m, M - m):
            child = node.children[i]
            extend(leftBBox, toBBox(child) if node.leaf else child)
            margin += bboxMargin(leftBBox)
        i = (M - m) - 1
        while i >= m:
            child = node.children[i]
            extend(rightBBox, toBBox(child) if node.leaf else child)
            margin += bboxMargin(rightBBox)
        return margin

    def _adjustParentBBoxes(self, bbox, path, level):
        """
        adjust bboxes along the given tree path
        """
        i = level
        while i >= 0:
            extend(path[i], bbox)

    def _condense(self, path):
        """
        go through the path, removing empty nodes and updating bboxes
        """
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
    """
    calculate node's bbox from bboxes of its children
    """
    distBBox(node, 0, len(node.children), toBBox, node)


def distBBox(node, k, p, toBBox, destNode=None):
    """
    min bounding rectangle of node children from k to p-1
    """
    if not destNode:
        destNode = createNode(None)
    destNode.minX = math.inf
    destNode.minY = math.inf
    destNode.maxX = -math.inf
    destNode.maxY = -math.inf
    for i in range(k, p):
        child = node.children[i]
        extend(destNode, toBBox(child) if node.leaf else child)
    return destNode


def extend(a, b):
    a.minX = min(a.minX, b.minX)
    a.minY = min(a.minY, b.minY)
    a.maxX = max(a.maxX, b.maxX)
    a.maxY = max(a.maxY, b.maxY)
    return a


def compareNodeMinX(a, b):
    return a.minX - b.minX


def compareNodeMinY(a, b):
    return a.minY - b.minY


def bboxArea(a):
    return (a.maxX - a.minX) * (a.maxY - a.minY)


def bboxMargin(a):
    return (a.maxX - a.minX) + (a.maxY - a.minY)


def enlargedArea(a, b):
    return (max([b.maxX, a.maxX]) - min([b.minX, a.minX])) * (
        max([b.maxY, a.maxY]) - min([b.minY, a.minY]))


def intersectionArea(a, b):
    minX = max(a.minX, b.minX)
    minY = max(a.minY, b.minY)
    maxX = min(a.maxX, b.maxX)
    maxY = min(a.maxY, b.maxY)
    return max(0, maxX - minX) * max(0, maxY - minY)


def contains(a, b):
    return a.minX <= b.minX and a.minY <= b.minY and b.maxX <= a.maxX and b.maxY <= a.maxY


def intersects(a, b):
    return b.minX <= a.maxX and b.minY <= a.maxY and b.maxX >= a.minX and b.maxY >= a.minY


def createNode(children):
    return Node(math.inf, -math.inf, math.inf, -math.inf, children, 1, True)


def multiSelect(arr, left, right, n, compare):
    """
    sort an array so that items come in groups of n unsorted items, with groups sorted between each other;
    combines selection algorithm with binary divide & conquer approach
    """
    stack = [left, right]
    while len(stack) > 0:
        right = stack.pop()
        left = stack.pop()

        if right - left <= n:
            continue

        mid = left + math.ceil((right - left) / n / 2) * n
        quickselect(arr, mid, left, right, compare)

        for e in [left, mid, mid, right]:
            stack.append(e)

