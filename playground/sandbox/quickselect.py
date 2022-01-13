"""
Implementation of QuickSelect (https://en.wikipedia.org/wiki/Floyd–Rivest_algorithm) algorithm.
Code copied form https://github.com/mourner/quickselect and converted to python.
"""
import math


def swap(arr, i, j):
    tmp = arr[i]
    arr[i] = arr[j]
    arr[j] = tmp


def default_compare(a, b):
    return -1 if a < b else 1 if a > b else 0


def quickselect(arr, k, left=None, right=None, compare=None):
    return quickselect_step(arr, k, left if left is not None else 0,
                            right if right is not None else len(arr) - 1,
                            compare if compare is not None else default_compare)


def quickselect_step(arr, k, left, right, compare):

    while right > left:
        if right - left > 600:
            n = right - left + 1
            m = k - left + 1
            z = math.log(n)
            s = 0.5 * math.exp(2 * z / 3)
            sd = 0.5 * math.sqrt(z * s *
                                 (n - s) / n) * (-1 if m - n / 2 < 0 else 1)
            newLeft = max(left, math.floor(k - m * s / n + sd))
            newRight = min(right, math.floor(k + (n - m) * s / n + sd))
            quickselect_step(arr, k, newLeft, newRight, compare)

        t = arr[k]
        i = left
        j = right

        swap(arr, left, k)
        if compare(arr[right], t) > 0:
            swap(arr, left, right)

        while i < j:
            swap(arr, i, j)
            i += 1
            j -= 1
            while compare(arr[i], t) < 0:
                i += 1
            while compare(arr[j], t) > 0:
                j -= 1

        if compare(arr[left], t) == 0:
            swap(arr, left, j)
        else:
            j += 1
            swap(arr, j, right)

        if j <= k:
            left = j + 1
        if k <= j:
            right = j - 1

    return arr


# test
# print(quickselect([65, 28, 59, 33, 21, 56, 22, 95, 50, 12, 90, 53, 28, 77, 39], 8))
# arr is [39, 28, 28, 33, 21, 12, 22, 50, 53, 56, 59, 65, 90, 77, 95]
#                                         ^^ middle index
