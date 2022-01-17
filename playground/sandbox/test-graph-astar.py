from geojson import Point
from graph import Graph, Vertex, Edge
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("Test Graph")

g = Graph()

a0 = g.add_vertex( Vertex(node="0", point=Point((0,0)) ))
a1 = g.add_vertex( Vertex(node="1", point=Point((2,2)) ))
a2 = g.add_vertex( Vertex(node="2", point=Point((-2,-2)) ))
a3 = g.add_vertex( Vertex(node="3", point=Point((6, 2)) ))
a4 = g.add_vertex( Vertex(node="4", point=Point((6, -2)) ))
a5 = g.add_vertex( Vertex(node="5", point=Point((8, 0)) ))

g.add_edge(Edge(a0, a1, 2.8, True))
g.add_edge(Edge(a0, a2, 2.8, False))
g.add_edge(Edge(a2, a1, 4, True))
g.add_edge(Edge(a1, a3, 4, True))
g.add_edge(Edge(a2, a4, 4, True))
g.add_edge(Edge(a3, a4, 4, True))
g.add_edge(Edge(a1, a4, 5.6, True))
g.add_edge(Edge(a3, a5, 2.8, True))
g.add_edge(Edge(a4, a5, 2.8, True))

r = g.AStar("2", "5")
print(r)