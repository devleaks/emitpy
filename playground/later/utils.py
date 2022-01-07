from random import random


def randomInt(a: int):
    return int(random() * a)


def randomFromList(a: list):
    return a[randomInt(len(a))]
