"""Unabhängiges Orakel für die VRP-Kernroutinen: Distanzmatrix gegen Floyd-Warshall (scipy), Tourbewertung gegen
eine eigene Zeitsimulation, Konstruktionen + lokale Suche gegen die per Teilmengen-DP berechnete exakte Lösung
(lexikografisch: Kapazitätsüberschreitung, Zeitfenster-Verletzungen, Distanz), optimaler Split und Savings gegen
Neuimplementierungen."""

import itertools
import math
import os
import random
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vrp_construction import (
    beam_savings,
    decode_giant_tour_optimal_split,
    genetic_algorithm_construction,
    savings_construction,
    sweep_construction,
)
from vrp_evaluation import evaluate_route
from vrp_local_search import local_search_history
from vrp_network import build_road_network, compute_network_distances

csgraph = pytest.importorskip("scipy.sparse.csgraph")


def _instance(seed, n, asym):
    rng = np.random.default_rng(seed)
    coords = rng.uniform(5, 95, size=(n, 2)).round(1)
    earliest = rng.uniform(0, 120, size=n).round(0)
    graph, _pts, _asym = build_road_network((50.0, 50.0), tuple(map(tuple, coords)), 12, 5, seed, asymmetric=asym)
    dist, _paths = compute_network_distances(graph, n, ("oracle", seed, n, asym))
    return dict(
        n=n, coords=coords, depot=np.array([50.0, 50.0]), D=dist, graph=graph,
        demands=rng.integers(1, 10, size=n).astype(float), earliest=earliest,
        latest=earliest + rng.uniform(20, 60, size=n).round(0), service=rng.integers(0, 6, size=n).astype(float),
    )


def _route(route, inst, tw):
    """Distanz und Zeitfenster-Verletzungen einer Tour per eigener Zeitsimulation."""
    if not route:
        return 0.0, 0
    t = dist = 0.0
    pos, viol = 0, 0
    for stop in route:
        leg = inst["D"][pos][stop + 1]
        dist += leg
        t = max(t + leg, inst["earliest"][stop]) if tw else t + leg
        if tw:
            viol += t > inst["latest"][stop] + 1e-9
            t += inst["service"][stop]
        pos = stop + 1
    return dist + inst["D"][pos][0], int(viol)


def _key(routes, inst, cap, tw):
    excess = sum(max(0.0, sum(inst["demands"][s] for s in r) - cap) for r in routes)
    parts = [_route(r, inst, tw) for r in routes]
    return excess, sum(p[1] for p in parts), sum(p[0] for p in parts)


def _less(a, b):
    if abs(a[0] - b[0]) > 1e-9:
        return a[0] < b[0]
    if a[1] != b[1]:
        return a[1] < b[1]
    return a[2] < b[2] - 1e-9


def _exact(inst, cap, n_veh, tw):
    """Exakte lexikografische Lösung: beste Reihenfolge je Stoppmenge, dann Teilmengen-DP über die Fahrzeuge."""
    n = inst["n"]
    best_route = {}
    for mask in range(1, 1 << n):
        stops = [i for i in range(n) if mask >> i & 1]
        excess = max(0.0, sum(inst["demands"][i] for i in stops) - cap)
        options = []
        for perm in itertools.permutations(stops):
            dist, viol = _route(list(perm), inst, tw)
            options.append((excess, viol, dist))
        best_route[mask] = min(options, key=lambda c: (c[1], c[2]))
    f = [(float("inf"),) * 3] * (1 << n)
    f[0] = (0.0, 0, 0.0)
    for _ in range(n_veh):
        g = list(f)
        for mask in range(1 << n):
            sub = mask
            while sub:
                prev = f[mask ^ sub]
                if prev[0] != float("inf"):
                    c = best_route[sub]
                    cand = (prev[0] + c[0], prev[1] + c[1], prev[2] + c[2])
                    if _less(cand, g[mask]):
                        g[mask] = cand
                sub = (sub - 1) & mask
        f = g
    return f[(1 << n) - 1]


def test_distance_matrix_matches_floyd_warshall():
    for seed in range(40):
        n = random.Random(seed).randint(3, 12)
        inst = _instance(seed, n, asym=bool(seed % 2))
        graph = inst["graph"]
        adj = np.zeros((graph.number_of_nodes(), graph.number_of_nodes()))
        for u, v, data in graph.edges(data=True):
            adj[u][v] = data["weight"]
        fw = csgraph.floyd_warshall(adj, directed=True)
        assert np.allclose(fw[: n + 1, : n + 1], inst["D"], atol=1e-9)


def test_route_evaluation_matches_independent_time_simulation():
    rng = random.Random(5)
    for seed in range(150):
        n = rng.randint(2, 9)
        inst = _instance(seed + 500, n, asym=bool(seed % 2))
        route = rng.sample(range(n), rng.randint(1, n))
        for tw in (True, False):
            dist, viol, _tl = evaluate_route(route, inst["D"], inst["earliest"], inst["latest"], inst["service"], tw)
            my_dist, my_viol = _route(route, inst, tw)
            assert dist == pytest.approx(my_dist) and viol == my_viol


def test_pipeline_against_exact_optimum_on_small_instances():
    rng = random.Random(31)
    for k in range(20):
        n, n_veh, tw = rng.randint(3, 6), rng.randint(1, 3), rng.random() < 0.5
        inst = _instance(1000 + k, n, asym=rng.random() < 0.5)
        cap = max(9, int(math.ceil(inst["demands"].sum() / n_veh * rng.choice([0.9, 1.0, 1.15, 1.4]))))
        opt = _exact(inst, cap, n_veh, tw)
        args = (inst["D"], inst["demands"], cap)
        tw_args = (inst["earliest"], inst["latest"], inst["service"], tw)
        constructions = {
            "sweep": sweep_construction(inst["depot"], inst["coords"], inst["demands"], n_veh, cap),
            "savings": savings_construction(n, args[0], args[1], cap, n_veh),
            "beam": beam_savings(n, args[0], args[1], cap, n_veh, *tw_args),
            "ga": genetic_algorithm_construction(n, args[0], args[1], cap, n_veh, *tw_args, seed=k),
        }
        for name, (routes, _infeasible) in constructions.items():
            assert sorted(s for r in routes for s in r) == list(range(n)), name
            final, dist, _viol, excess = local_search_history(routes, *args, *tw_args)[-1]
            assert sorted(s for r in final for s in r) == list(range(n)), name
            mine = _key(final, inst, cap, tw)
            assert excess == pytest.approx(mine[0]) and dist == pytest.approx(mine[2]), name
            assert not _less((mine[0], mine[1] if tw else 0, mine[2]), (opt[0], opt[1] if tw else 0, opt[2])), name


def test_optimal_split_matches_enumeration_of_all_cut_points():
    rng = random.Random(8)
    for k in range(60):
        n, n_veh, tw = rng.randint(2, 7), rng.randint(1, 3), rng.random() < 0.5
        inst = _instance(3000 + k, n, asym=bool(k % 2))
        cap = max(9, int(math.ceil(inst["demands"].sum() / n_veh * rng.choice([1.0, 1.2, 1.5]))))
        tour = rng.sample(range(n), n)
        routes, _ = decode_giant_tour_optimal_split(
            tour, inst["D"], inst["demands"], cap, n_veh, inst["earliest"], inst["latest"], inst["service"], tw)
        best = None
        for n_cuts in range(n_veh):
            for cuts in itertools.combinations(range(1, n), n_cuts):
                segs = [tour[a:b] for a, b in zip((0,) + cuts, cuts + (n,))]
                if any(sum(inst["demands"][s] for s in seg) > cap for seg in segs):
                    continue
                key = _key(segs, inst, cap, tw)
                key = (key[1] if tw else 0, key[2])
                best = key if best is None or key < best else best
        if best is None:
            continue
        got = _key(routes, inst, cap, tw)
        assert sorted(s for r in routes for s in r) == list(range(n))
        assert (got[1] if tw else 0) == best[0] and got[2] == pytest.approx(best[1])


def test_savings_matches_independent_directed_clarke_wright():
    rng = random.Random(12)
    for k in range(60):
        n, n_veh = rng.randint(2, 10), rng.randint(1, 4)
        inst = _instance(5000 + k, n, asym=bool(k % 2))
        cap = max(9, int(math.ceil(inst["demands"].sum() / n_veh * rng.choice([1.0, 1.3]))))
        dist, dem = inst["D"], inst["demands"]
        order = []
        for i in range(n):
            for j in range(i + 1, n):
                order.append((dist[i + 1][0] + dist[0][j + 1] - dist[i + 1][j + 1], i, j))
                order.append((dist[j + 1][0] + dist[0][i + 1] - dist[j + 1][i + 1], j, i))
        order.sort(key=lambda t: -t[0])
        chains = [[i] for i in range(n)]
        for _s, i, j in order:
            ci = next(c for c in chains if i in c)
            cj = next(c for c in chains if j in c)
            if ci is cj or ci[-1] != i or cj[0] != j or sum(dem[x] for x in ci + cj) > cap:
                continue
            chains.remove(ci)
            chains.remove(cj)
            chains.append(ci + cj)
        if len(chains) <= n_veh:
            routes, _ = savings_construction(n, dist, dem, cap, n_veh)
            assert sorted(tuple(r) for r in routes if r) == sorted(tuple(c) for c in chains)
