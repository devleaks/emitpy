# Graph (vertices and edges) wrapper functions.
# Loose Vertex, Edge, and Graph definition customized for our need.
# Can be later hooked to more comprehensive Graph library.
# Dijkstra stolen at https://www.bogotobogo.com/python/python_graph_data_structures.php
#
import logging
import math
import json
from functools import reduce

from geojson import Point, LineString, Feature, FeatureCollection
from turfpy.measurement import distance, nearest_point, boolean_point_in_polygon, point_to_line_distance

from .geoline import Line


class Vertex(Feature):

    def __init__(self, node: str, point: Point, usage: [str]=[], name: str=None):
        Feature.__init__(self, geometry=point, id=node)
        self.name = name
        self.usage = usage
        self.adjacent = {}

    def add_neighbor(self, neighbor, weight=0):
        self.adjacent[neighbor] = weight

    def get_connections(self):
        return self.adjacent.keys()


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
            if str.lower(self.usage[:8]) == "taxiway_" and len(self.usage) == 9:
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

    def widthCode(self, default: str=None):
        return self.widthCode if not None else default


class Graph:  # Graph(FeatureCollection)?

    def __init__(self):
        self.vert_dict = {}
        self.edges_arr = []

    # Vertices
    def add_vertex(self, vertex: Vertex):
        self.vert_dict[vertex.id] = vertex
        return vertex

    def get_vertex(self, ident: str):
        if ident in self.vert_dict:
            return self.vert_dict[ident]
        return None

    def get_vertices(self, bbox: Feature = None):
        if bbox is not None:
            ret = list(map(lambda x: x.id, filter(lambda x: boolean_point_in_polygon(Feature(geometry=Point(x["geometry"]["coordinates"])), bbox), self.vert_dict.values())))
            logging.debug("Graph::get_vertices: box bounded from %d to %d.", len(self.vert_dict), len(ret))
            return ret
        return list(self.vert_dict.keys())

    # Options taxiwayOnly = True|False, minSizeCode = {A,B,C,D,E,F}
    def get_connections(self, src, options={}):
        """
        Returns connected vertices with optional condition on connecting edge.
        "taxiwayOnly": edge.usage must contain taxiway or taxiway_x
        "minSizeCode": edge.usage must contain either runway or taxiway_x with x > minsizecode.
        "bbox": src adjacent vertices must be within supplied bounding box.
        """
        if len(options) > 0:
            connectionKeys = []
            for dst in src.adjacent.keys():
                v = self.get_edge(src.id, dst)
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

    # Edges
    def add_edge(self, edge: Edge):
        if edge.start.id in self.vert_dict and edge.end.id in self.vert_dict:
            self.edges_arr.append(edge)
            self.vert_dict[edge.start.id].add_neighbor(self.vert_dict[edge.end.id].id, edge.weight)

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


    def get_connected_vertices(self, options={}):
        # List of vertices may contain unconnected vertices.
        # Same options as get_connections
        connected = []

        for edge in self.edges_arr:
            code = edge.widthCode("F")  # default all ok.
            txyOk = ("taxiwayOnly" not in options) or ("taxiwayOnly" in options and options["taxiwayOnly"] and not edge.use("runway"))
            scdOk = ("minSizeCode" not in options) or ("minSizeCode" in options and options["minSizeCode"] <= code)
            bbOk = ("bbox" not in options) or ("bbox" in options and boolean_point_in_polygon(edge.start, options["bbox"]) and boolean_point_in_polygon(edge.end, options["bbox"]))

            # logging.debug("%s %s %s %s %s" % (dst, v.usage, code, txyOk, scdOk))
            if txyOk and scdOk and bbOk:
                if edge.start not in connected:
                    connected.append(edge.start)
                if edge.end not in connected:
                    connected.append(edge.end)

        return connected


    def nearest_point_on_edges(self, point: Feature):  # @todo: construct array of lines on "add_edge"
        closest = None
        e = None
        dist = math.inf
        for edge in self.edges_arr:
            print(edge["geometry"])
            d = point_to_line_distance(point, Feature(geometry=edge["geometry"]))
            if d < dist:
                dist = d
                e = edge
        return [closest, dist, e]


    def nearest_vertex(self, point: Feature):
        closest = None
        dist = float(math.inf)
        for p in self.vert_dict.values():
            d = distance(point, p)
            if d < dist:
                dist = d
                closest = p
        return [closest, dist]

        # fc = list(map(lambda x: Feature(geometry=x.geometry, id=x.id), self.vert_dict.values()))
        # print(len(fc))
        # print(fc[0])
        # fc.reverse()
        # return nearest_point(point, FeatureCollection(features=fc))


    def Dijkstra(self, source, target, options={}):
        # This will store the Shortest path between source and target node
        route = []
        if not source or not target:
            logging.debug("Graph::Dijkstra: source or target missing")
            return route

        # These are all the nodes which have not been visited yet
        unvisited_nodes = None
        if "bbox" in options:
            unvisited_nodes = list(self.get_vertices(options["bbox"]))
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
        while(unvisited_nodes):
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
            connected = self.get_connections(self.get_vertex(min_node), options)
            logging.debug("connected %s %d", min_node, len(connected))
            # logging.debug("connected %s %s", min_node, connected)
            for child_node in connected:
                e = self.get_edge(min_node, child_node) # should always be found...
                cost = e.weight

                # checking if the value of the current_node + value of the edge
                # that connects this neighbor node with current_node
                # is lesser than the value that distance between current nodes
                # and its connections
                #
                logging.debug("test %s: %f < %f", child_node, cost + shortest_distance[min_node], shortest_distance[child_node])
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
        logging.debug("Graph::Dijkstra: predecessor %s", predecessor)
        while node and node != source and len(predecessor.keys()) > 0:
            # As it is not necessary that the target node can be reached from # the source node, we must enclose it in a try block
            route.insert(0, node)
            if node in predecessor:
                node = predecessor[node]
            else:
                node = False

        if len(route) == 0:
            logging.debug("Graph::Dijkstra: could not find route from %s to %s", source, target)
            return None
        else:
            # Including the source in the path
            route.insert(0, source)
            logging.debug("Graph::Dijkstra: route: %s", "-".join(route))
            return route
