class A:
    def __init__(self):
        print('a')

class B(A):
    def __init__(self):
        A.__init__(self)
        print('b')


a = A()
b = B()

print(type(a).__name__, type(b).__name__)
