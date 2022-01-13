# Graph (vertices and edges) wrapper functions.
# Loose Vertex, Edge, and Graph definition customized for our need.
# Can be later hooked to more comprehensive Graph library.
# Dijkstra stolen at https://www.bogotobogo.com/python/python_graph_data_structures.php
#
import logging
import math


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

        self.graph = None
        self._heuristic = None
        self._heurcalc = 0
        self._heurcalc2 = 0


    def add_vertex(self, vertex: Vertex):
        self.vert_dict[vertex.id] = vertex
        self.resetAStarMatrices()
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

            self.resetAStarMatrices()
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
            logging.debug("Graph::Dijkstra: could not find route from %s to %s", source, target)
            return None
        else:
            # Including the source in the path
            route.insert(0, source)
            logging.debug("Graph::Dijkstra: route: %s", "-".join(route))
            return route


    def mkAStarMatrices(self, vertices):
        if self.graph is None or self._heuristic is None:
            numvtx = len(vertices)

            self._heuristic = [0] * numvtx
            self.graph = [0] * numvtx
            for i in range(numvtx):
                self.graph[i] = [0] * numvtx
                self._heuristic[i] = [None] * numvtx
                for j in range(numvtx):
                    e = self.get_edge(vertices[i], vertices[j])
                    self.graph[i][j] = e.weight if e is not None else 0

    def resetAStarMatrices(self):
        self.graph = None
        self._heuristic = None


    def heuristic(self, vertices, i, j):  # On demand
        if self._heuristic[i][j] is None:
            src = self.get_vertex(vertices[i])
            dst = self.get_vertex(vertices[j])
            d = distance(src, dst)
            self._heuristic[i][j] = d
            if self.get_edge(dst, src) is not None:
                self._heuristic[j][i] = d
                self._heurcalc2 = self._heurcalc2 + 1
            self._heurcalc = self._heurcalc + 1
        return self._heuristic[i][j]


    def AStar(self, source, target, options={}):
    # def a_star(graph, heuristic, start, goal):
        """
        Finds the shortest distance between two nodes using the A-star (A*) algorithm
        :param graph: an adjacency-matrix-representation of the graph where (x,y) is the weight of the edge or 0 if there is no edge.
        :param heuristic: an estimation of distance from node x to y that is guaranteed to be lower than the actual distance. E.g. straight-line distance
        :param start: the node to start from.
        :param goal: the node we're searching for
        :return: The shortest distance to the goal node. Can be easily modified to return the path.

        MODIFIED FROM https://www.algorithms-and-technologies.com/a_star/python
        Algorithm would loop infinitely on reaching nodes with no outgoing connection.
        I modified algorithm so that it stops searching in this case, which is wrong.
        It should backtrack to the last node with outgoing connections and visit other nodes.
        Best implementation: https://github.com/anvaka/ngraph.path
        """
        def numTrues(arr):
            return sum(map(lambda x: 1 if x else 0, arr))
        loop = 30
        path = []
        vertices = list(self.vert_dict.keys())
        self.mkAStarMatrices(vertices)

        start = vertices.index(source)
        goal = vertices.index(target)

        # This contains the distances from the start node to all other nodes, initialized with a distance of "Infinity"
        distances = [float("inf")] * len(self.graph)

        # The distance from the start node to itself is of course 0
        distances[start] = 0

        # This contains the priorities with which to visit the nodes, calculated using the heuristic.
        priorities = [float("inf")] * len(self.graph)

        # start node has a priority equal to straight line distance to goal. It will be the first to be expanded.
        priorities[start] = self.heuristic(vertices, start, goal)

        # This contains whether a node was already visited
        visited = [False] * len(self.graph)

        # While there are nodes left to visit...
        num_connection = numTrues(self.graph[start])
        while num_connection > 0:  # loop > 0 and num_connection > 0:
            loop = loop - 1
            # ... find the node with the currently lowest priority...
            lowest_priority = float("inf")
            lowest_priority_index = -1
            for i in range(len(priorities)):
                # ... by going through all nodes that haven't been visited yet
                if priorities[i] < lowest_priority and not visited[i]:
                    lowest_priority = priorities[i]
                    lowest_priority_index = i

            if lowest_priority_index == -1:
                # There was no node not yet visited --> Node not found
                logging.warning("Graph::AStar: destination unreachable")
                return None

            elif lowest_priority_index == goal:
                # Goal node found
                # print("Goal node found!")
                path.append(goal)
                return list(map(lambda x: self.get_vertex(vertices[x]).id, path))

            # print("Visiting node %d with currently lowest priority of %d" % (lowest_priority_index, lowest_priority))
            path.append(lowest_priority_index)

            # ...then, for all neighboring nodes that haven't been visited yet....
            for i in range(len(self.graph[lowest_priority_index])):
                if self.graph[lowest_priority_index][i] != 0 and not visited[i]:
                    # ...if the path over this edge is shorter...
                    if distances[lowest_priority_index] + self.graph[lowest_priority_index][i] < distances[i]:
                        # ...save this path as new shortest path
                        distances[i] = distances[lowest_priority_index] + self.graph[lowest_priority_index][i]
                        # ...and set the priority with which we should continue with this node
                        priorities[i] = distances[i] + self.heuristic(vertices, i, goal)
                        print("Updating distance of node %d to %f and priority to %f, heuristic distance=%d" % (i, distances[i], priorities[i], self._heurcalc))

                    # Lastly, note that we are finished with this node.
                    visited[lowest_priority_index] = True
                    print("Visited nodes: %s" % visited)
                    # print("Currently lowest distances: %s" % distances)

                # we reached an end node, it has no more connection
                # shouldn't we backtrack?
                # for now we stop the algorithm with a failure
                num_connection = numTrues(self.graph[lowest_priority_index])
                # print("number of connections of lowest_priority_index node is %d" % num_connection)

        logging.warning("Graph::AStar: visited=%s, #connections=%d, heuristic distance=%d", visited, num_connection, self._heurcalc)

        return -1