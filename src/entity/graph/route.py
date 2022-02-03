"""
A Route is a collection of ordered graph vertices.
"""
import logging
logger = logging.getLogger("Route")


class Route:
    # Container for route from src to dst on graph
    def __init__(self, graph, src, dst, move, options):
        self.graph = graph
        self.src = src
        self.dst = dst
        self.move = move
        self.options = options
        self.route = []
        self.vertices = None
        self.edges = None
        self.smoothed = None

    def __str__(self):
        if self.found():
            return ">" + "-".join(self.route) + "."
        return ""

    def find(self):
        self.route = self.graph.AStar(self.src, self.dst, self.options)
        return self

    def found(self):
        return self.route and len(self.route) > 2

    def get_edges(self):
        # From liste of vertices, build list of edges
        # but also set the size of the taxiway in the vertex
        self.edges = []
        for i in range(len(self.route) - 1):
            e = self.graph.get_edge(self.route[i], self.route[i + 1])
            self.edges.append(e)

    def get_vertices(self):
        self.vertices = list(map(lambda x: self.graph.get_vertex(x), self.route))
