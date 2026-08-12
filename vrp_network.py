"""
Synthetisches Straßennetz für die VRP-Demo: Aufbau des Graphen (optional
asymmetrisch), kürzeste-Wege-Distanzmatrix und Hilfsfunktionen für die
Visualisierung des Netzes und der Routen darauf.
"""

import networkx as nx
import numpy as np
import streamlit as st


@st.cache_data(show_spinner=False)
def build_road_network(depot_xy, stops_xy, n_extra, k_neighbors, seed, asymmetric=False):
    """Baut ein synthetisches, stark zusammenhängendes Straßennetz: Depot + Stopps
    + zusätzliche 'Kreuzungen' als Knoten, verbunden mit ihren k nächsten Nachbarn.
    Ist `asymmetric` aktiv, wird für einen Teil der Kantenpaare eine Richtung
    künstlich verlängert (Faktor 1.4–2.5) – simuliert Einbahnstraßen bzw. Umwege,
    ohne die starke Zusammenhangskomponente zu gefährden (beide Richtungen bleiben
    befahrbar, nur unterschiedlich lang)."""
    rng = np.random.default_rng(int(seed) + 1000)
    extra = rng.uniform(2, 98, size=(int(n_extra), 2))
    all_pts = np.vstack([np.array(depot_xy).reshape(1, 2), np.array(stops_xy), extra])
    n_all = len(all_pts)

    G = nx.DiGraph()
    for idx, (x, y) in enumerate(all_pts):
        G.add_node(idx, pos=(float(x), float(y)))

    k = max(2, min(int(k_neighbors), n_all - 1))
    for i in range(n_all):
        dists = np.linalg.norm(all_pts - all_pts[i], axis=1)
        nearest = np.argsort(dists)[1 : k + 1]
        for j in nearest:
            j = int(j)
            base = float(dists[j])
            if not G.has_edge(i, j):
                G.add_edge(i, j, weight=base)
            if not G.has_edge(j, i):
                G.add_edge(j, i, weight=base)

    asymmetric_edges = set()
    if asymmetric:
        edge_pairs = [(a, b) for a, b in G.edges() if a < b and G.has_edge(b, a)]
        n_asym = max(1, int(len(edge_pairs) * 0.25))
        if edge_pairs:
            chosen = rng.choice(len(edge_pairs), size=min(n_asym, len(edge_pairs)), replace=False)
            for idx in chosen:
                a, b = edge_pairs[idx]
                factor = float(rng.uniform(1.4, 2.5))
                if rng.random() < 0.5:
                    G[a][b]["weight"] *= factor
                    asymmetric_edges.add((a, b))
                else:
                    G[b][a]["weight"] *= factor
                    asymmetric_edges.add((b, a))

    # Starke Zusammenhangskomponente sicherstellen (beide Richtungen erreichbar)
    while not nx.is_strongly_connected(G):
        components = list(nx.strongly_connected_components(G))
        comp_a, comp_b = components[0], components[1]
        best = None
        for a in comp_a:
            diffs = np.linalg.norm(all_pts[list(comp_b)] - all_pts[a], axis=1)
            j = int(np.argmin(diffs))
            b = list(comp_b)[j]
            d = float(diffs[j])
            if best is None or d < best[0]:
                best = (d, a, b)
        G.add_edge(best[1], best[2], weight=best[0])
        G.add_edge(best[2], best[1], weight=best[0])

    return G, all_pts, asymmetric_edges


@st.cache_data(show_spinner=False)
def compute_network_distances(_G, n_stops, cache_key):
    """Kürzeste-Wege-Distanzmatrix und -Pfade zwischen Depot (Knoten 0) und
    allen Stopps (Knoten 1..n_stops). Bei einem gerichteten Netz mit asymmetrischen
    Kantengewichten ist die Matrix im Allgemeinen NICHT symmetrisch (D[i][j] !=
    D[j][i]) - jede Distanzabfrage im restlichen Code respektiert das, da immer
    gerichtet (von -> nach) nachgeschlagen wird."""
    key_nodes = list(range(n_stops + 1))
    n = len(key_nodes)
    dist_matrix = np.zeros((n, n))
    paths = {}
    for i in key_nodes:
        lengths, node_paths = nx.single_source_dijkstra(_G, i, weight="weight")
        for j in key_nodes:
            dist_matrix[i][j] = lengths.get(j, np.inf)
            paths[(i, j)] = node_paths.get(j, [i, j])
    return dist_matrix, paths


def road_edges_xy(G, asymmetric_edges=None):
    """Trennt das Hintergrundnetz in normale (symmetrische) und asymmetrische
    Kanten für die Visualisierung (unterschiedliche Farben). Jedes ungerichtete
    Kantenpaar wird nur einmal gezeichnet."""
    pos = nx.get_node_attributes(G, "pos")
    asymmetric_edges = asymmetric_edges or set()
    normal_xs, normal_ys, asym_xs, asym_ys = [], [], [], []
    seen = set()
    for a, b in G.edges():
        pair = (min(a, b), max(a, b))
        if pair in seen:
            continue
        seen.add(pair)
        is_asym = (a, b) in asymmetric_edges or (b, a) in asymmetric_edges
        xs, ys = (asym_xs, asym_ys) if is_asym else (normal_xs, normal_ys)
        xs += [pos[a][0], pos[b][0], None]
        ys += [pos[a][1], pos[b][1], None]
    return normal_xs, normal_ys, asym_xs, asym_ys


def route_polyline(route, paths_lookup, node_positions):
    """Baut die tatsächliche (Straßennetz-)Polylinie einer Tour für die
    Kartendarstellung, indem die kürzesten-Wege-Pfade zwischen aufeinander
    folgenden Stopps aneinandergehängt werden."""
    node_seq = [0] + [s + 1 for s in route] + [0]
    xs, ys = [], []
    for k in range(len(node_seq) - 1):
        path_nodes = paths_lookup[(node_seq[k], node_seq[k + 1])]
        for node in path_nodes[:-1]:
            x, y = node_positions[node]
            xs.append(x)
            ys.append(y)
    last = node_positions[node_seq[-1]]
    xs.append(last[0])
    ys.append(last[1])
    return xs, ys
