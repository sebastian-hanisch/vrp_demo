"""
Kombinierte lokale Suche (2-opt + Or-opt), lexikografisch zuerst nach
Zeitfenster-Verletzungen, dann nach Distanz optimiert. Wird von allen vier
eigenen Konstruktionsheuristiken (Sweep, Savings, Beam Search, GA) im
Anschluss an die Konstruktion verwendet, um eine gemeinsame, faire
Vergleichsgrundlage zu schaffen.
"""

from vrp_constants import EPS, LOCAL_SEARCH_MAX_MOVES, OR_OPT_SEG_LENGTHS
from vrp_evaluation import evaluate_route, solution_totals


def find_two_opt_move(routes, D, earliest, latest, service, tw_enabled):
    """Sucht EINE verbessernde 2-opt-Vertauschung innerhalb einer beliebigen
    Fahrzeugtour (erste gefundene Verbesserung)."""
    for v, route in enumerate(routes):
        if len(route) < 2:
            continue
        base_dist, base_viol, _ = evaluate_route(route, D, earliest, latest, service, tw_enabled)
        for i in range(len(route) - 1):
            for j in range(i + 1, len(route)):
                cand = route[:i] + route[i : j + 1][::-1] + route[j + 1 :]
                cand_dist, cand_viol, _ = evaluate_route(cand, D, earliest, latest, service, tw_enabled)
                if cand_viol < base_viol or (cand_viol == base_viol and cand_dist < base_dist - EPS):
                    new_routes = [r[:] for r in routes]
                    new_routes[v] = cand
                    return new_routes, True
    return routes, False


def find_or_opt_move(routes, D, demands, capacity, earliest, latest, service, tw_enabled, seg_lengths=OR_OPT_SEG_LENGTHS):
    """Sucht EINEN verbessernden Or-opt-Zug: ein kurzes Segment (1-2 Stopps)
    wird aus einer Tour entfernt und an der besten Position wieder
    eingefügt - auch in einer anderen Fahrzeugtour, sofern die Kapazität
    reicht. Das behebt die zentrale Schwäche von reinem 2-opt, das Stopps
    nie zwischen Fahrzeugen verschieben kann."""
    n_vehicles = len(routes)
    for v_from in range(n_vehicles):
        route_from = routes[v_from]
        for seg_len in seg_lengths:
            if seg_len > len(route_from):
                continue
            for start in range(len(route_from) - seg_len + 1):
                segment = route_from[start : start + seg_len]
                remainder = route_from[:start] + route_from[start + seg_len :]
                seg_demand = sum(demands[s] for s in segment)
                base_from_dist, base_from_viol, _ = evaluate_route(route_from, D, earliest, latest, service, tw_enabled)

                for v_to in range(n_vehicles):
                    if v_to == v_from:
                        target = remainder
                        base_dist, base_viol = base_from_dist, base_from_viol
                    else:
                        target = routes[v_to]
                        target_load = sum(demands[s] for s in target)
                        if target_load + seg_demand > capacity:
                            continue
                        base_to_dist, base_to_viol, _ = evaluate_route(target, D, earliest, latest, service, tw_enabled)
                        base_dist, base_viol = base_from_dist + base_to_dist, base_from_viol + base_to_viol

                    for pos in range(len(target) + 1):
                        if v_to == v_from and pos == start:
                            continue  # entspricht exakt der Ursprungsposition -> kein echter Zug
                        new_target = target[:pos] + segment + target[pos:]
                        if v_to == v_from:
                            new_dist, new_viol, _ = evaluate_route(new_target, D, earliest, latest, service, tw_enabled)
                        else:
                            rem_dist, rem_viol, _ = evaluate_route(remainder, D, earliest, latest, service, tw_enabled)
                            tgt_dist, tgt_viol, _ = evaluate_route(new_target, D, earliest, latest, service, tw_enabled)
                            new_dist, new_viol = rem_dist + tgt_dist, rem_viol + tgt_viol

                        better = new_viol < base_viol or (new_viol == base_viol and new_dist < base_dist - EPS)
                        if better:
                            new_routes = [r[:] for r in routes]
                            if v_to == v_from:
                                new_routes[v_from] = new_target
                            else:
                                new_routes[v_from] = remainder
                                new_routes[v_to] = new_target
                            return new_routes, True
    return routes, False


def local_search_history(routes, D, demands, capacity, earliest, latest, service, tw_enabled, max_moves=LOCAL_SEARCH_MAX_MOVES):
    """Kombinierte lokale Suche: versucht in jedem Schritt zuerst einen
    günstigeren 2-opt-Zug (billiger), erst wenn keiner mehr gefunden wird,
    einen Or-opt-Zug (teurer, aber kann Stopps zwischen Fahrzeugen
    verschieben). Stoppt, wenn keine der beiden Nachbarschaften mehr eine
    Verbesserung liefert."""
    current = [r[:] for r in routes]
    total_dist, total_viol = solution_totals(current, D, earliest, latest, service, tw_enabled)
    history = [([r[:] for r in current], total_dist, total_viol)]
    moves = 0

    while moves < max_moves:
        new_routes, found = find_two_opt_move(current, D, earliest, latest, service, tw_enabled)
        if not found:
            new_routes, found = find_or_opt_move(current, D, demands, capacity, earliest, latest, service, tw_enabled)
        if not found:
            break
        current = new_routes
        moves += 1
        total_dist, total_viol = solution_totals(current, D, earliest, latest, service, tw_enabled)
        history.append(([r[:] for r in current], total_dist, total_viol))

    return history
