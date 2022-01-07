"""
Turnaround activities
"""

class Task:
    pass


class RelatedTask:
    def __init__(self, task: Task, relation: str, delay: int):
        self.task = task
        self.relation = relation
        self.delay = delay

    @staticmethod
    def inverse(relation: str):
        """
        Relation = {SE, ES, SS, EE} for Start and End

        :param      relation:  The relation
        :type       relation:  str
        """
        return relation if relation[0] == relation[1] else relation[1] + relation[0]


class Task:
    """
    Turnaround activity
    """
    def __init__(self, name: str, duration: int = None, parent: Task = None):
        self.parent = None
        self.children = []
        self.name = name
        self.duration = duration
        self.predecessors = []
        self.successors = []
        self.scheduled = None
        self.planned = None
        self.actual = None

        if parent is not None:
            parent.children.append(self)

    def setParent(self, parent: Task):
        if self.parent is not None:  # reparenting...
            self.parent.children.remove(self)
        self.parent = parent
        self.parent.children.append(self)

    def isGroup(self):
        return self.duration is None

    def isMilestone(self):
        return self.duration == 0

    def before(self, task: Task, relation: str, delay: int):
        """
        This task should occur before the supplied task

        :param      task:      The task
        :type       task:      Task
        :param      relation:  The relation
        :type       relation:  str
        :param      delay:     The delay
        :type       delay:     int
        """
        self.successors.append(RelatedTask(task, relation, delay))
        task.predecessors.append(RelatedTask(self, RelatedTask.inverse(relation), -delay))

    def after(self, task: Task, relation: str, delay: int):
        """
        This task should occur after the supplied task

        :param      task:      The task
        :type       task:      Task
        :param      relation:  The relation
        :type       relation:  str
        :param      delay:     The delay
        :type       delay:     int
        """
        self.predecessors.append(RelatedTask(task, relation, delay))
        task.successors.append(RelatedTask(self, RelatedTask.inverse(relation), -delay))


class Project:
    """
    A container for tasks.
    """
    def __init__(self, name: str):
        self.name = name
        self.tasks = []

    def add(self, task: Task):
        if task.isGroup():
            for t in task.children:
                self.tasks.append(t)
        self.tasks.append(task)

    def level(self):
        pass

    def print(self):
        pass
