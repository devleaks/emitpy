
def select(inlist: list, criteria: dict) -> list:
    pre = []

    # At least one criteria:
    for e in inlist:
        good = False

        for k,v in criteria:
            val = e.get(k)
            if val is not None and val == v:
                good = True

        if good:
            pre.append(e)


    # All criteria:
    for e in inlist:
        good = True

        for k,v in criteria:
            val = e.get(k)
            if val is None or val != v:
                good = False

        if good:
            pre.append(e)


    # Inspect criteria:
    pre = []
    for e in inlist:
        matched = []
        unmatched = []
        res = {}
        cnt = 0

        for k,v in criteria:
            val = e.get(k)
            if val is not None and val == v:
                matched.append(k)
                res[k] = True
                cnt = cnt + 1
            else:
                unmatched.append(k)
                res[k] = False

            pre.append({
                "value": e,
                "count": cnt,
                "result": res,
                "matches": matched,
                "unmatched": unmatched
            })
