#!/usr/bin/env python3
"""Ridge regression + honest out-of-sample evaluation. Stdlib only.

Everything is leave-one-out cross-validated: with 66 decks and a handful of
features, in-sample fit is meaningless and will happily report a moat that
does not exist. LOO refits the model 66 times, each time predicting a deck the
fit has never seen. Feature standardisation is refit INSIDE each fold too,
because standardising on the full set leaks the held-out deck.
"""
from __future__ import annotations

import math


def pearson(x, y):
    n = len(x)
    if n < 3:
        return float("nan")
    mx, my = sum(x) / n, sum(y) / n
    sx = math.sqrt(sum((a - mx) ** 2 for a in x))
    sy = math.sqrt(sum((b - my) ** 2 for b in y))
    if sx == 0 or sy == 0:
        return float("nan")
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (sx * sy)


def _ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    r = [0.0] * len(v)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            r[order[k]] = avg
        i = j + 1
    return r


def spearman(x, y):
    return pearson(_ranks(x), _ranks(y))


def _solve(A, b):
    """Gaussian elimination with partial pivoting."""
    n = len(A)
    M = [row[:] + [b[i]] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            return None
        M[c], M[p] = M[p], M[c]
        pv = M[c][c]
        for r in range(n):
            if r == c:
                continue
            fac = M[r][c] / pv
            if fac:
                for k in range(c, n + 1):
                    M[r][k] -= fac * M[c][k]
    return [M[i][i + 1] / M[i][i] if False else M[i][n] / M[i][i] for i in range(n)]


def fit_ridge(X, y, lam=1.0):
    """Standardise, then ridge. Returns a predict() closure carrying its own
    scaler so a fold can never see the held-out row."""
    n, p = len(X), len(X[0]) if X else 0
    if n == 0 or p == 0:
        my = sum(y) / max(1, len(y))
        return lambda row: my
    mu = [sum(r[j] for r in X) / n for j in range(p)]
    sd = []
    for j in range(p):
        v = math.sqrt(sum((r[j] - mu[j]) ** 2 for r in X) / n)
        sd.append(v if v > 1e-9 else 1.0)
    Z = [[(r[j] - mu[j]) / sd[j] for j in range(p)] for r in X]
    my = sum(y) / n
    yc = [v - my for v in y]
    A = [[sum(Z[i][a] * Z[i][b] for i in range(n)) + (lam if a == b else 0.0)
          for b in range(p)] for a in range(p)]
    rhs = [sum(Z[i][a] * yc[i] for i in range(n)) for a in range(p)]
    w = _solve(A, rhs)
    if w is None:
        return lambda row: my
    def predict(row):
        z = [(row[j] - mu[j]) / sd[j] for j in range(p)]
        return my + sum(w[j] * z[j] for j in range(p))
    predict.weights = w
    predict.mu, predict.sd, predict.intercept = mu, sd, my
    return predict


def loo(X, y, lam=1.0):
    """Leave-one-out predictions. The only number worth quoting."""
    out = []
    for i in range(len(X)):
        Xtr = X[:i] + X[i + 1:]
        ytr = y[:i] + y[i + 1:]
        out.append(fit_ridge(Xtr, ytr, lam)(X[i]))
    return out


def report(name, pred, y, weights=None):
    n = len(y)
    err = [abs(a - b) for a, b in zip(pred, y)]
    mae = sum(err) / n
    rmse = math.sqrt(sum((a - b) ** 2 for a, b in zip(pred, y)) / n)
    if weights:
        wsum = sum(weights)
        wmae = sum(w * e for w, e in zip(weights, err)) / wsum
    else:
        wmae = mae
    return {"name": name, "mae": mae, "wmae": wmae, "rmse": rmse,
            "pearson": pearson(pred, y), "spearman": spearman(pred, y)}


def fmt(r):
    return (f"{r['name']:<34} MAE {r['mae']:5.2f}pp  wMAE {r['wmae']:5.2f}pp  "
            f"RMSE {r['rmse']:5.2f}  r {r['pearson']:+.3f}  rho {r['spearman']:+.3f}")
