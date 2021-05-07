

def fun(a: int, b: str):
    print(b, a)

def fun2(**kwargs):
    for key, value in kwargs.items():
            print(key, '-', value)

fun(1, "a")

fun(b="B",a=2)

o={
    "a": 42,
    "b": "thgttg"
}
fun2(**o)