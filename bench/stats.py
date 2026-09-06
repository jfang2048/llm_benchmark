"""Statistical helpers for benchmark result aggregation.

Deliberately small. For repeat-level performance metrics, exposes
mean/median/stddev and percentiles; for success/failure proportions, the
Wilson score interval. No significance claims are invented here — callers
decide what a sample size supports.
"""
import math
import statistics


def mean_median_stddev(values):
    """Return (mean, median, stddev) for a list of numeric values."""
    values = [float(v) for v in values]
    n = len(values)
    if n == 0:
        return None, None, None
    mean = statistics.mean(values)
    median = statistics.median(values)
    stddev = statistics.stdev(values) if n >= 2 else 0.0
    return mean, median, stddev


def percentile(values, p):
    """Return the p-th percentile (0-100) of a list of numeric values."""
    values = sorted(float(v) for v in values)
    if not values:
        return None
    k = (len(values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return d0 + d1


def wilson_interval(successes, trials, z=1.96):
    """Wilson score interval for a binomial proportion.

    Returns (lower, upper) in [0, 1]. Robust for small samples and proportions
    near 0 or 1, unlike the normal approximation.
    """
    if trials <= 0:
        return (0.0, 0.0)
    n = float(trials)
    phat = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (phat + z2 / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z2 / (4 * n * n))) / denom
    return (centre - half, centre + half)
