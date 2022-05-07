import logging

from datetime import datetime, timedelta
from emitpy.resource import Resource

logging.basicConfig(level=logging.DEBUG)

def dt(t):
    # return t  # no debug
    return round((((t+timedelta(seconds=1)) - datetime.now()).seconds) / 6)/10  # debug

r = Resource("test1")

def t(x):
    return datetime.now() + timedelta(minutes=x)

print(r.usage)

for a in [(0, 5), (4, 12), (6, 7), (9, 13), (14, 17), (7.5, 9.5)]:
    b = [t(i) for i in a]
    if not r.isAvailable(*b):
        alt = r.firstAvailable(*b)
        k = r.book(*alt, f"{a[0]}->{a[1]}")
        print("rescheduled", a, list(map(dt, alt)))
    else:
        k = r.book(*b, f"{a[0]}->{a[1]}")

print("--------", r.getId())
[print(x) for x in r.allocations()]
print("--------")

# r.clean(t(10))

# print("--------", "cleaned")
# [print(x) for x in r.allocations()]
# print("--------")
