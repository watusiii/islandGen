"""Tiny seeded noise. No dependencies."""
import math
import random


def loop_noise(rng: random.Random, knots: int):
    """Return f(t) for t in [0,1) that loops smoothly (f(0) == f(1)).

    Used to wobble a circle into a blob. More knots = more bumps.
    Output is roughly in [-1, 1].
    """
    values = [rng.uniform(-1.0, 1.0) for _ in range(knots)]

    def f(t: float) -> float:
        x = (t % 1.0) * knots
        i = int(x)
        frac = x - i
        a = values[i % knots]
        b = values[(i + 1) % knots]
        s = (1 - math.cos(frac * math.pi)) * 0.5  # smooth blend
        return a + (b - a) * s

    return f


def layered_loop_noise(rng: random.Random, base_knots: int, octaves: int):
    """Big bumps plus smaller bumps on top (like layered p5 noise)."""
    layers = [loop_noise(rng, base_knots * (2 ** o)) for o in range(octaves)]

    def f(t: float) -> float:
        total, amp, norm = 0.0, 1.0, 0.0
        for layer in layers:
            total += layer(t) * amp
            norm += amp
            amp *= 0.5
        return total / norm

    return f
