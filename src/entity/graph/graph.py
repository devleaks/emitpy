# Graph (vertices and edges) wrapper functions.
# Loose Vertex, Edge, and Graph definition customized for our need.
# Can be later hooked to more comprehensive Graph library.
# Dijkstra stolen at https://www.bogotobogo.com/python/python_graph_data_structures.php
#
import logging
import math
import time

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Graph")

from geojson import Point, LineString, Feature
from turfpy.measurement import distance, boolean_point_in_polygon, point_to_line_distance


class Vertex(Feature):

    def __init__(self, node: str, point: Point, usage: [str]=[], name: str=None):
        Feature.__init__(self, geometry=point, id=node)
        self.name = name
        self.usage = usage
        self.adjacent = {}
        self.connected = False

    def add_neighbor(self, neighbor, weight=0):
        self.adjacent[neighbor] = weight

    def get_connections(self):
        return self.adjacent.keys()

    def get_neighbors(self):
        return list(map(lambda a: (a, self.adjacent[a]), self.adjacent))

class Edge(Feature):

    def __init__(self, src: Vertex, dst: Vertex, weight: float, directed: bool, usage: [str]=[], name=None):
        Feature.__init__(self, geometry=LineString([src.geometry.coordinates, dst.geometry.coordinates]))
        # Feature.__init__(self, geometry=Line([src.geometry, dst.geometry]))
        self.start = src
        self.end = dst
        self.name = name        # segment name, not unique!
        self.weight = weight    # weight = distance to next vertext
        self.directed = directed  # if edge is directed src to dst, False = twoway
        self.usage = usage      # type of vertex: runway or taxiway or taxiway_X where X is width code (A-F)
        self.widthCode = None
        for s in self.usage:
            if str.lower(str(self.usage[:8])) == "taxiway_" and len(self.usage) == 9:
                self.widthCode = str.upper(self.usage[8])  # should check for A-F return...

    def use(self, what: str, mode: bool = None):
        if mode is None:  # Query
            return what in self.usage

        # Else: set what
        if mode and what not in self.usage:
            self.usage.append(what)
        elif mode and what in self.usage:
            self.usage.remove(what)

        return what in self.usage

    def widthCode(self, default: str = None):
        return self.widthCode if not None else default


class Graph:  # Graph(FeatureCollection)?

    def __init__(self):
        self.vert_dict = {}
        self.edges_arr = []


    def add_vertex(self, vertex: Vertex):
        if vertex.id in self.vert_dict.keys():
            logging.warning("Graph::add_vertex: duplicate %s" % vertex.id)
        self.vert_dict[vertex.id] = vertex
        return vertex


    def get_vertex(self, ident: str):
        if ident in self.vert_dict:
            return self.vert_dict[ident]
        return None


    def get_vertices(self, connected_only: bool = False, bbox: Feature = None):
        varr = filter(lambda x: x.connected, self.vert_dict.values()) if connected_only else self.vert_dict.values()
        if bbox is not None:
            ret = list(map(lambda x: x.id, filter(lambda x: boolean_point_in_polygon(Feature(geometry=Point(x["geometry"]["coordinates"])), bbox), varr)))
            logging.debug("Graph::get_vertices: box bounded from %d to %d.", len(self.vert_dict), len(ret))
            return ret
        return list(varr)


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
                    txyOk = ("taxiwayOnly" in options and options["taxiwayOnly"] and not v.use("runway")) or ("taxiwayOnly" not in options)
                if txyOk:
                    scdOk = True
                    if "minSizeCode" in options:
                        code = v.widthCode("F")
                        scdOk = ("minSizeCode" in options and options["minSizeCode"] <= code) or ("minSizeCode" not in options)
                    if scdOk:
                        bbOk = True
                        if "bbox" in options:
                            dstp = self.get_vertex(dst)
                            bbOk = boolean_point_in_polygon(dstp, options["bbox"])
                        # logging.debug("%s %s %s %s %s" % (dst, v.usage, code, txyOk, scdOk))
                        if bbOk:
                            connectionKeys.append(dst)
                        # else:
                        #     logging.debug("Graph::get_connections: excluded.")

            return connectionKeys

        return src.adjacent.keys()


    def add_edge(self, edge: Edge):
        if edge.start.id in self.vert_dict and edge.end.id in self.vert_dict:
            self.edges_arr.append(edge)
            self.vert_dict[edge.start.id].add_neighbor(self.vert_dict[edge.end.id].id, edge.weight)
            self.vert_dict[edge.start.id].connected = True
            self.vert_dict[edge.end.id].connected = True

            if not edge.directed:
                self.vert_dict[edge.end.id].add_neighbor(self.vert_dict[edge.start.id].id, edge.weight)

        else:
            logging.critical("Graph::add_edge: vertex not found when adding edges %s,%s", edge.start, edge.end)


    def get_edge(self, src: str, dst: str):
        arr = list(filter(lambda x: x.start.id == src and x.end.id == dst, self.edges_arr))  # src to dst, directed or not
        if len(arr) > 0:
            return arr[0]

        arr = list(filter(lambda x: x.start.id == dst and x.end.id == src and not x.directed, self.edges_arr)) # dst to src not directed
        if len(arr) > 0:
            return arr[0]

        return None


    def nearest_point_on_edge(self, point: Feature, with_connection: bool = False):  # @todo: construct array of lines on "add_edge"
        closest = None
        edge = None
        nconn = (0, 0)
        dist = math.inf
        for e in self.edges_arr:
            if (not with_connection) or (with_connection and (len(e.start.adjacent) > 0 or len(e.end.adjacent) > 0)):
                d = point_to_line_distance(point, Feature(geometry=e["geometry"]))
                if d < dist:
                    dist = d
                    edge = e
                    nconn = (len(e.start.adjacent), len(e.end.adjacent))
        return [closest, dist, edge, nconn]


    def nearest_vertex(self, point: Feature, with_connection: bool = False):
        closest = None
        nconn = 0
        dist = math.inf
        for p in self.vert_dict.values():
            if (not with_connection) or (with_connection and len(p.adjacent) > 0):
                d = distance(point, p)
                if d < dist:
                    dist = d
                    closest = p
                    nconn = len(p.adjacent)
        return [closest, dist, nconn]

        # fc = list(map(lambda x: Feature(geometry=x.geometry, id=x.id), self.vert_dict.values()))
        # print(len(fc))
        # print(fc[0])
        # fc.reverse()
        # return nearest_point(point, FeatureCollection(features=fc))


# #################
#
# DIJKSTRA ROUTING ALGORITHM
#
#
    def Dijkstra(self, source, target, options={}):
        # This will store the Shortest path between source and target node
        route = []
        if not source or not target:
            logging.debug("Graph::Dijkstra: source or target missing")
            return route

        # These are all the nodes which have not been visited yet
        unvisited_nodes = None
        if "bbox" in options:
            unvisited_nodes = list(self.get_vertices(bbox=options["bbox"]))
        else:
            unvisited_nodes = list(self.get_vertices())

        # logging.debug("Unvisited nodes", unvisited_nodes)
        # It will store the shortest distance from one node to another
        shortest_distance = {}
        # It will store the predecessors of the nodes
        predecessor = {}

        # Iterating through all the unvisited nodes
        for nodes in unvisited_nodes:
            # Setting the shortest_distance of all the nodes as infinty
            shortest_distance[nodes] = math.inf

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
                    #min_node as current_node
                    min_node = current_node

            # Iterating through the connected nodes of current_node (for
            # example, a is connected with b and c having values 10 and 3
            # respectively) and the weight of the edges
            min_vertex = self.get_vertex(min_node)
            connected = self.get_connections(min_vertex, options)
            # logging.debug("connected %s: %f %d/%d", min_node, shortest_distance[min_node], len(min_vertex.adjacent), len(connected))
            for child_node in connected:
                e = self.get_edge(min_node, child_node) # should always be found...
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
        # logging.debug("Graph::Dijkstra: predecessor %s", predecessor)
        while node and node != source and len(predecessor.keys()) > 0:
            # As it is not necessary that the target node can be reached from # the source node, we must enclose it in a try block
            route.insert(0, node)
            if node in predecessor:
                node = predecessor[node]
            else:
                node = False

        if len(route) == 0:
            logger.debug("Graph::Dijkstra: could not find route from %s to %s", source, target)
            return None
        else:
            # Including the source in the path
            route.insert(0, source)
            logger.debug("Graph::Dijkstra: route: %s", "-".join(route))
            return route


# #################
#
# A * STAR ROUTING ALGORITHM
#
#
    def heuristic(self, a, b):  # On demand
        """
        Heuristic function is straight distance (to goal)
        """
        return distance(self.get_vertex(a), self.get_vertex(b))


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
                logger.warning("Graph::AStart: path not found")
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

                logger.debug("Graph::AStart: path found: %s (%f sec)" % (reconst_path, (time.perf_counter() - ss)))
                return reconst_path

            # for all neighbors of the current node do
            for (m, weight) in self.get_neighbors(n):
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

        logger.warning("Graph::AStart: path not found")
        return None
