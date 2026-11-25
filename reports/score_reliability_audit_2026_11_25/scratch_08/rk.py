import numpy as np
def rankdata(a):
    a = np.asarray(a, float); order = a.argsort(kind='mergesort'); r = np.empty(len(a)); r[order] = np.arange(len(a))
    # average ties
    s = a[order]; i = 0
    while i < len(a):
        j = i
        while j + 1 < len(a) and s[j + 1] == s[i]: j += 1
        if j > i: r[order[i:j + 1]] = (i + j) / 2
        i = j + 1
    return r
def spearmanr(a, b):
    ra, rb = rankdata(a), rankdata(b)
    if ra.std() == 0 or rb.std() == 0: return (float('nan'), None)
    return (float(np.corrcoef(ra, rb)[0, 1]), None)
