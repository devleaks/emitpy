"""
A Queue is an abstraction of a resource to allow for resource usage of consumpsion one after the other, in turn.
"""

class QueueElem():

    def __init__(self, elem: object, datetime: str, servicetime: int, priority: float = None):
        self.elem = elem
        self.servicetime = servicetime
        self.datetime = datetime
        self.priority = priority


class Queue:

    PRIORITY_INCREASE = 0.25

    def __init__(self, name: str, queueing: str):
        self.name = name
        self.queueing = queueing
        self.queue = []

    def enqueue(self, client: QueueElem):
        self.queue.append(client)

    def pop(self) -> QueueElem:
        """
        Priority dequeuing is done like this:
         - Highest priority is dequeued first.
         - At equal priority, first come, first served.
         - At each dequeueing, the priority of unserved elements raises.

        :returns:   The queue element.
        :rtype:     QueueElem
        """
        # sort queue
        self.queue.sort(key=lambda x: (x.property, x.datetime), reverse=True)
        # get top element
        nexte = self.queue.pop()
        # increase priority of unserved elements
        self.increasePriority()

        return nexte

    def increasePriority(self):
        for e in self.queue:
            e.priority = self.PRIORITY_INCREASE
            if e.priority < 1:
                e.priority = 1