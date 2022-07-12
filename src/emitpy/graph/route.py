"""
A Route is a collection of ordered graph vertices.
"""
import logging
from networkx import shortest_path, exception

# from geojson import Point, Feature
from turfpy.measurement import distance

logger = logging.getLogger("Route")


class Route:
    # Container for route from src to dst on graph
    def __init__(self, graph, src, dst, auto=True, options=None):
        self.graph = graph
        self.src = src
        self.dst = dst
        self.options = options
        self.route = []
        self.vertices = None
        self.edges = None
        self.smoothed = None

        if auto:  # auto route
            self.find()

    def __str__(self):
        if self.found():
            return ">" + "-".join(self.route) + "."
        return ""

    def find(self):
        def heuristic_distance(src, dst):
            n0 = self.graph.nx.nodes[src]
            n1 = self.graph.nx.nodes[dst]
            d = distance(n0['v'], n1['v'])
            # logger.debug(":find:heuristic: %s->%s=%f" % (i0, i1, d))
            return d

        logger.debug(":find: trying networkx shortest_path..")
        try:
            self.route = shortest_path(self.graph.nx, source=self.src, target=self.dst, weight="weight")
            logger.debug(":find: .. found")
            # logger.debug(":find: .. found %s", self.route)
            return self.route
        except exception.NetworkXNoPath:
            logger.debug(":find: .. not found")

        logger.debug(":find: trying local AStar..")
        atry = self.graph.AStar(self.src, self.dst)
        if atry is not None:
            logger.debug(":find: .. found")
            self.route = atry
            return

        logger.warning(":find: route not found")
        # logger.debug(":find: trying AStar.. (reverse)")
        # atry = self.graph.AStar(self.dst, self.src)
        # if atry is not None:
        #     logger.debug(":find: .. found")
        #     atry.reverse()
        #     self.route = atry
        #     return
        # logger.debug(":find: trying Dijkstra..")
        # atry = self.graph.Dijkstra(self.src, self.dst)
        # if atry is not None and len(atry) > 2:
        #     logger.debug(":find: .. found (%d)", len(atry))
        #     self.route = atry
        #     return
        # logger.debug(":find: trying Dijkstra.. (reverse)")
        # atry = self.graph.Dijkstra(self.dst, self.src)
        # if atry is not None and len(atry) > 2:
        #     logger.debug(":find: .. found (%d)", len(atry))
        #     atry.reverse()
        #     self.route = atry


    def found(self):
        return self.route and len(self.route) > 2

    def get_edges(self):
        # From liste of vertices, build list of edges
        # but also set the size of the taxiway in the vertex
        if self.edges is None:
            self.edges = []
            for i in range(len(self.route) - 1):
                e = self.graph.get_edge(self.route[i], self.route[i + 1])
                self.edges.append(e)
        return self.edges

    def get_vertices(self):
        if self.vertices is None:
            self.vertices = list(map(lambda x: self.graph.get_vertex(x), self.route))
        return self.vertices
