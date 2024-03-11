# Graph (vertices and edges) wrapper functions.
# Loose Vertex, Edge, and Graph definition customized for our need.
# Can be later hooked to more comprehensive Graph library.
# Dijkstra stolen at https://www.bogotobogo.com/python/python_graph_data_structures.php
#
import logging
import time
from math import inf
from typing import List, Dict
import networkx as nx

from emitpy.geo.turf import Point, LineString, Feature, FeatureCollection
from emitpy.geo.turf import distance, destination, bearing, point_in_polygon, point_to_line_distance

from emitpy.geo import FeatureWithProps, line_intersect, printFeatures


logger = logging.getLogger("Graph")

USAGE_TAG = "usage"


class Vertex(FeatureWithProps):
    def __init__(self, node: str, point: Point, usage: List[str] = [], name: str | None = None):
        FeatureWithProps.__init__(self, id=node, geometry=point, properties={"name": name})
        self.name = name
        self.usage = usage
        self.adjacent: Dict[str, float] = {}
        self.connected = False
        self.restriction: "Restriction" | None = None

    def set_restriction(self, restriction: "Restriction"):
        self.restriction = restriction

    def has_restriction(self) -> bool:
        return self.restriction is not None

    def add_neighbor(self, neighbor, weight: float = 0.0):
        self.adjacent[neighbor] = weight

    def get_connections(self):
        return self.adjacent.keys()

    def get_neighbors(self):
        return list(map(lambda a: (a, self.adjacent[a]), self.adjacent))

    def getKey(self):
        return self.getId()

    def getInfo(self):
        a = FeatureWithProps.new(self)
        a["vertex"] = {"name": self.name, "usage": self.usage, "adjacent": self.adjacent, "connected": self.connected}
        return a

    def get_nxattrs(self):
        a = {"lat": self.lat(), "lon": self.lon(), "id": self.getId(), "v": self}  # , "alt": self.alt()
        if self.restriction is not None:
            a["base"] = self.restriction.alt1
            a["ceil"] = self.restriction.alt2
        return a

    @classmethod
    def new(cls, info):
        return info


class Edge(FeatureWithProps):
    def __init__(
        self, src: Vertex, dst: Vertex, weight: float, directed: bool, usage: str | List[str] = [], name: str | None = None, linestring: LineString = None
    ):
        ls = linestring if linestring is not None else LineString([src.geometry.coordinates, dst.geometry.coordinates])
        FeatureWithProps.__init__(self, geometry=ls)
        self.start: Vertex = src
        self.end: Vertex = dst
        self.name = name  # segment name, not unique!
        self.weight = weight  # weight = distance to next vertext
        self.directed = directed  # if edge is directed src to dst, False = twoway
        self.widthCode: str | None = None
        self.restriction: "Restriction" | None = None

        if isinstance(usage, str):
            usage = [usage]

        for s in usage:
            if s.lower().startswith("taxiway_") and len(s) == 9:
                w = str.upper(s[8])  # should check for A-F return...
                self.setProp("width-code", w)
                if w not in list("ABCDEF"):
                    logger.warning(f"invalid runway widthcode '{w}', ignoring")
            if s.lower().startswith("taxiway"):
                self.setTag(USAGE_TAG, "taxiway")
            if s.lower().startswith("runway"):
                self.setTag(USAGE_TAG, "runway")

    def set_restriction(self, restriction: "Restriction"):
        self.restriction = restriction

    def has_restriction(self) -> bool:
        return self.restriction is not None

    def getKey(self):
        prefix = ""
        if type(self).__name__ == "AirwaySegment":
            if self.lowhigh == 2:  # the same airway may exist for hi and lo
                prefix = "U"
        return prefix + self.start.getId() + "-" + self.end.getId()

    def setColor(self, color: str):
        # geojson.io specific
        self.setStrokeColor(color)

    def getWidthCode(self, default: str | None = None):
        return self.widthCode if not None else default

    def getPoints(self):
        # returns array of Feature<Point>.
        # If an edge is a linestring rather than a straight line from src to end, returns all intermediate points.
        pts = []
        pts.append(self.start)  # extremity points have their own props from vertex
        coords = self.geometry.coordinates
        if len(coords) > 2:
            props = self.props()  # copies edge props to each "inner" point
            if props is None:
                props = {}
            props["inner-edge"] = True
            for p in coords[1:-1]:
                pt = FeatureWithProps(geometry=Point(p), properties=props)
                pts.append(pt)
        pts.append(self.end)
        return pts

    def get_nxattrs(self):
        # self.lowhigh = lowhigh
        # self.fl_floor = fl_floor
        # self.fl_ceil = fl_ceil
        a = {}
        if type(self).__name__ == "AirwaySegment":
            a["hilo"] = self.lowhigh
            if self.restriction is not None:
                a["base"] = self.restriction.alt1
                a["ceil"] = self.restriction.alt2
        return a


class Graph:  # Graph(FeatureCollection)?
    def __init__(self):
        self.vert_dict = {}
        self.edges_arr = []
        self.nx = nx.DiGraph()

    def print(self, vertex: bool = True, edge: bool = True):
        allitems: List[Vertex | Edge] = []
        txt = ""
        if vertex:
            allitems = allitems + list(self.vert_dict.values())
            txt = "vertices"
        if edge:
            allitems = allitems + self.edges_arr
            txt = txt + ", edges"
        printFeatures(allitems, f"graph {txt}")

    def to_geojson(self, vertices: bool = False, edges: bool = True):
        fc = []
        if vertices:
            fc = [v.to_geojson() for v in self.vert_dict.values()]
        if edges:
            fc = fc + [e.to_geojson() for e in self.edges_arr]
        return FeatureCollection(features=fc).to_geojson()

    def add_vertex(self, vertex: Vertex):
        if vertex.id in self.vert_dict.keys():
            logger.warning(f"duplicate {vertex.id}")
        self.vert_dict[vertex.id] = vertex
        self.nx.add_node(vertex.id, **vertex.get_nxattrs())  # node attributes unused, only vertex.id to identify the vertex
        return vertex

    def get_vertex(self, ident: str):
        return self.vert_dict.get(ident)

    def get_vertices(self, connected_only: bool = False, bbox: Feature | None = None):
        varr = filter(lambda x: x.connected, self.vert_dict.values()) if connected_only else self.vert_dict.values()
        if bbox is not None:
            ret = list(map(lambda x: x.id, filter(lambda x: point_in_polygon(Feature(geometry=Point(x.geometry.coordinates)), bbox), varr)))
            logger.debug("box bounded from %d to %d.", len(self.vert_dict), len(ret))
            return ret
        return list(map(lambda x: x.id, varr))

    def get_connections(self, src, options={}):
        """
        Returns connected vertices with optional condition on connecting edge.
        "taxiwayOnly": edge.usage must contain taxiway or taxiway_x. taxiwayOnly = True|False.
        "minSizeCode": edge.usage must contain either runway or taxiway_x with x > minsizecode.minSizeCode = {A,B,C,D,E,F}.
        "bbox": src adjacent vertices must be within supplied bounding box.
        """
        if len(options) > 0:
            connectionKeys = []
            for dst in src.adjacent.keys():
                v = self.get_edge(src.id, dst)
                d = self.get_vertex(dst)
                txyOk = True
                if "taxiwayOnly" in options:
                    txyOk = ("taxiwayOnly" in options and options["taxiwayOnly"] and not v.hasTag(USAGE_TAG, "runway")) or ("taxiwayOnly" not in options)
                if txyOk:
                    scdOk = True
                    if "minSizeCode" in options:
                        code = v.getWidthCode("F")
                        scdOk = ("minSizeCode" in options and options["minSizeCode"] <= code) or ("minSizeCode" not in options)
                    if scdOk:
                        bbOk = True
                        if "bbox" in options:
                            dstp = self.get_vertex(dst)
                            bbOk = point_in_polygon(dstp, options["bbox"])
                        # logger.debug("%s %s %s %s %s" % (dst, v.usage, code, txyOk, scdOk))
                        if bbOk:
                            connectionKeys.append(dst)
                        # else:
                        #     logger.debug("excluded.")

            return connectionKeys

        return src.adjacent.keys()

    def add_edge(self, edge: Edge):
        if edge.start.id in self.vert_dict and edge.end.id in self.vert_dict:
            self.edges_arr.append(edge)
            self.vert_dict[edge.start.id].add_neighbor(self.vert_dict[edge.end.id].id, edge.weight)
            self.vert_dict[edge.start.id].connected = True
            self.vert_dict[edge.end.id].connected = True
            self.nx.add_edge(edge.start.id, edge.end.id, weight=edge.weight, **edge.get_nxattrs())
            if not edge.directed:
                self.nx.add_edge(edge.end.id, edge.start.id, weight=edge.weight, **edge.get_nxattrs())
                self.vert_dict[edge.end.id].add_neighbor(self.vert_dict[edge.start.id].id, edge.weight)

        else:
            logger.critical(":add_edge: vertex not found when adding edges %s,%s", edge.start, edge.end)

    def get_edge(self, src: str, dst: str):
        arr = list(filter(lambda x: x.start.id == src and x.end.id == dst, self.edges_arr))  # src to dst, directed or not
        if len(arr) > 0:
            return arr[0]

        arr = list(filter(lambda x: x.start.id == dst and x.end.id == src and not x.directed, self.edges_arr))  # dst to src not directed
        if len(arr) > 0:
            return arr[0]

        return None

    def purge(self):
        # Only keeps edge start/end vertices, delete vertices with no edge
        n = len(self.vert_dict)
        v = [e.start.id for e in self.edges_arr] + [e.end.id for e in self.edges_arr]
        v = set(v)
        nd = dict((v.id, v) for v in filter(lambda i: i.id in v, self.vert_dict.values()))
        # for ident in v:
        #     nd[ident] = self.vert_dict[ident]
        self.vert_dict = nd
        logger.debug(f"purged {n - len(self.vert_dict)} vertices, {len(self.vert_dict)} left")
        newnx = nx.DiGraph()
        for ident, vertex in self.vert_dict.items():
            newnx.add_node(ident, v=vertex)
        for edge in self.edges_arr:
            newnx.add_edge(edge.start.id, edge.end.id, weight=edge.weight)
            if not edge.directed:
                self.nx.add_edge(edge.end.id, edge.start.id, weight=edge.weight)
        self.nx = newnx
        logger.debug(f"networkx graph recreated: {len(nx.nodes(self.nx))} vertices, {len(nx.edges(self.nx))} edges")

    def nearest_point_on_edge(self, point: Feature, with_connection: bool = False):  # @todo: construct array of lines on "add_edge"
        def nearest_point_on_line(point, line, dist):
            LINE_LENGTH = 0.5  # km
            # extends original line, segments can sometimes be very short (openstreetmap)
            brng = bearing(Feature(geometry=Point(line.geometry.coordinates[0])), Feature(geometry=Point(line.geometry.coordinates[1])))
            p0 = destination(line.geometry.coordinates[0], 2 * max(dist, LINE_LENGTH), brng)
            p1 = destination(line.geometry.coordinates[1], 2 * max(dist, LINE_LENGTH), brng - 180)
            linext = Feature(geometry=LineString([p0.geometry.coordinates, p1.geometry.coordinates]))
            # make perpendicular, long enough
            brng = bearing(Feature(geometry=Point(line.geometry.coordinates[0])), Feature(geometry=Point(line.geometry.coordinates[1])))
            p0 = destination(point, 2 * max(dist, LINE_LENGTH), brng + 90)
            p1 = destination(point, 2 * max(dist, LINE_LENGTH), brng - 90)
            perp = Feature(geometry=LineString([p0.geometry.coordinates, p1.geometry.coordinates]))
            # printFeatures([linext, perp], "nearest_point_on_line")
            return line_intersect(linext, perp)

        closest = None
        edge = None
        nconn = (0, 0)
        dist = inf
        for e in self.edges_arr:
            if (not with_connection) or (with_connection and (len(e.start.adjacent) > 0 or len(e.end.adjacent) > 0)):
                d = point_to_line_distance(point, Feature(geometry=e.geometry))
                if d < dist:
                    dist = d
                    edge = e
                    nconn = (len(e.start.adjacent), len(e.end.adjacent))
        if dist == 0 and edge is not None:
            d = distance(point, Feature(geometry=Point(edge.start.geometry.coordinates)))
            if d == 0:
                logger.debug("nearest point is start of edge")
                return (edge.start, 0, edge, nconn)
            d = distance(point, Feature(geometry=Point(edge.end.geometry.coordinates)))
            if d == 0:
                logger.debug("nearest point is end of edge")
                return (edge.end, 0, edge, nconn)
            logger.debug("nearest point is on edge")
            closest = point
        elif edge is not None:
            closest = nearest_point_on_line(point, edge, dist)

        if closest is not None and not isinstance(closest, FeatureWithProps):
            closest = FeatureWithProps.new(closest)

        return [closest, dist, edge, nconn]

    def nearest_vertex(self, point: Feature, with_connection: bool = False):
        closest = None
        nconn = 0
        dist = inf
        for p in self.vert_dict.values():
            if (not with_connection) or (with_connection and len(p.adjacent) > 0):
                d = distance(point, p)
                if d < dist:
                    dist = d
                    closest = p
            #         nconn = len(p.adjacent)
            #         logger.debug("closer: %s, %d conn, %d km" % (p.id, len(p.adjacent), d))
            # if p.id.startswith(point.id[0:3]) and len(p.adjacent) > 0:
            #     d = distance(point, p)
            #     logger.debug("%s, %d conn, %d km" % (p.id, len(p.adjacent), d))
        # logger.debug("returning %s" % (closest.name if closest is not None else "None"))
        return [closest, dist, nconn]

    # #################
    #
    # DIJKSTRA ROUTING ALGORITHM
    #
    #
    def Dijkstra(self, source, target, opts=None):
        # This will store the Shortest path between source and target node
        ss = time.perf_counter()
        route = []
        if not source or not target:
            logger.debug("source or target missing")
            return route

        options = {}
        if opts is not None:
            options = opts

        # These are all the nodes which have not been visited yet
        unvisited_nodes = None
        if "bbox" in options:
            unvisited_nodes = self.get_vertices(bbox=options["bbox"])
        else:
            unvisited_nodes = self.get_vertices()

        # logger.debug("Unvisited nodes", unvisited_nodes)
        # It will store the shortest distance from one node to another
        shortest_distance = {}
        # It will store the predecessors of the nodes
        predecessor = {}

        # Iterating through all the unvisited nodes
        for node in unvisited_nodes:
            # Setting the shortest_distance of all the nodes as infinty
            shortest_distance[node] = inf

        # The distance of a point to itself is 0.
        shortest_distance[str(source)] = 0

        # Running the loop while all the nodes have been visited
        while unvisited_nodes:
            # setting the value of min_node as None
            min_node = None
            # iterating through all the unvisited node
            for current_node in unvisited_nodes:
                # For the very first time that loop runs this will be called
                if min_node is None:
                    # Setting the value of min_node as the current node
                    min_node = current_node
                elif shortest_distance[min_node] > shortest_distance[current_node]:
                    # I the value of min_node is less than that of current_node, set
                    # min_node as current_node
                    min_node = current_node

            # Iterating through the connected nodes of current_node (for
            # example, a is connected with b and c having values 10 and 3
            # respectively) and the weight of the edges
            min_vertex = self.get_vertex(min_node)
            connected = self.get_connections(min_vertex, options)
            # logger.debug("connected %s: %f %d/%d", min_node, shortest_distance[min_node], len(min_vertex.adjacent), len(connected))
            for child_node in connected:
                e = self.get_edge(min_node, child_node)  # should always be found...
                cost = e.weight

                # checking if the value of the current_node + value of the edge
                # that connects this neighbor node with current_node
                # is lesser than the value that distance between current nodes
                # and its connections
                #
                if (cost + shortest_distance[min_node]) < shortest_distance[child_node]:
                    # If true  set the new value as the minimum distance of that connection
                    shortest_distance[child_node] = cost + shortest_distance[min_node]
                    # Adding the current node as the predecessor of the child node
                    predecessor[child_node] = min_node

            # After the node has been visited (also known as relaxed) remove it from unvisited node
            unvisited_nodes.remove(min_node)

        # Till now the shortest distance between the source node and target node
        # has been found. Set the current node as the target node
        node = target
        # Starting from the goal node, we will go back to the source node and
        # see what path we followed to get the smallest distance
        # logger.debug("predecessor %s", predecessor)
        while node and node != source and len(predecessor.keys()) > 0:
            # As it is not necessary that the target node can be reached from # the source node, we must enclose it in a try block
            route.insert(0, node)
            if node in predecessor:
                node = predecessor[node]
            else:
                node = False

        if len(route) == 0:
            logger.debug("route not found")
            return None
        else:
            # Including the source in the path
            route.insert(0, source)
            if len(route) > 2:
                logger.debug(f"route: {'-'.join(route)} ({time.perf_counter() - ss:f} sec)")
                return route
            logger.debug("route not found")
            return None

    # #################
    #
    # A * STAR ROUTING ALGORITHM
    #
    #
    def heuristic(self, a, b):  # On demand
        """
        Heuristic function is straight distance (to goal)
        """
        va = self.get_vertex(a)
        if va is None:
            logger.warning(f"invalid vertex id a={a}")
            return inf
        vb = self.get_vertex(b)
        if vb is None:
            logger.warning(f"invalid vertex id b={b}")
            return inf
        return distance(va, vb)

    def get_neighbors(self, a):
        """
        Returns a vertex's neighbors with weight to reach.
        """
        return self.get_vertex(a).get_neighbors()

    def AStar(self, start_node, stop_node):
        # open_list is a list of nodes which have been visited, but who's neighbors
        # haven't all been inspected, starts off with the start node
        # closed_list is a list of nodes which have been visited
        # and who's neighbors have been inspected
        #
        # Stolen here: https://stackabuse.com/basic-ai-concepts-a-search-algorithm/
        # Heuristics adjusted for geography (direct distance to target, necessarily smaller or equal to goal)
        #
        # Returns list of vertices (path) or None
        #
        ss = time.perf_counter()
        open_list = set([start_node])
        closed_list = set([])

        # g contains current distances from start_node to all other nodes
        # the default value (if it's not found in the map) is +infinity
        g = {}

        g[start_node] = 0

        # parents contains an adjacency map of all nodes
        parents = {}
        parents[start_node] = start_node

        while len(open_list) > 0:
            n = None

            # find a node with the lowest value of f() - evaluation function
            for v in open_list:
                if n == None or g[v] + self.heuristic(v, stop_node) < g[n] + self.heuristic(n, stop_node):
                    n = v

            if n == None:
                logger.warning("route not found")
                return None

            # if the current node is the stop_node
            # then we begin reconstructin the path from it to the start_node
            if n == stop_node:
                reconst_path = []
                while parents[n] != n:
                    reconst_path.append(n)
                    n = parents[n]
                reconst_path.append(start_node)
                reconst_path.reverse()

                logger.debug(f"route: {reconst_path} ({time.perf_counter() - ss:f} sec)")
                return reconst_path

            # for all neighbors of the current node do
            for m, weight in self.get_neighbors(n):
                # if the current node isn't in both open_list and closed_list
                # add it to open_list and note n as it's parent
                if m not in open_list and m not in closed_list:
                    open_list.add(m)
                    parents[m] = n
                    g[m] = g[n] + weight

                # otherwise, check if it's quicker to first visit n, then m
                # and if it is, update parent data and g data
                # and if the node was in the closed_list, move it to open_list
                else:
                    if g[m] > g[n] + weight:
                        g[m] = g[n] + weight
                        parents[m] = n

                        if m in closed_list:
                            closed_list.remove(m)
                            open_list.add(m)

            # remove n from the open_list, and add it to closed_list
            # because all of his neighbors were inspected
            open_list.remove(n)
            closed_list.add(n)

        logger.warning("route not found")
        return None
