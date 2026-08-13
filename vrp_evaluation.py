"""
Bewertungsfunktionen für Touren: Distanz, Zeitfenster-Verletzungen, sowie die
Umrechnung von Distanz in geschäftliche Kennzahlen (Fahrzeit, Kosten, CO2).
Diese Funktionen sind die gemeinsame, einheitliche Bewertungsgrundlage für
alle fünf Lösungsmethoden (Sweep, Savings, Beam Search, GA, OR-Tools) - das
macht den Vergleich zwischen ihnen fair.
"""

from vrp_constants import DEFAULT_CO2_PER_KM, EPS


def route_cost(route, D):
    """Distanz einer einzelnen Tour: Depot -> Stopps in Reihenfolge -> Depot."""
    if not route:
        return 0.0
    nodes = [0] + [s + 1 for s in route] + [0]
    return sum(D[nodes[k]][nodes[k + 1]] for k in range(len(nodes) - 1))


def route_capacity_excess(route, demands, capacity):
    """Wie stark eine einzelne Tour die Kapazität überschreitet (0, wenn sie
    sie einhält). Auf Nutzeranfrage ergänzt: vorher kannte die lokale Suche
    Kapazität nur als Freigabefilter für Or-opt-Zielrouten, nicht als eigene
    Optimierungsgröße - siehe find_or_opt_move und local_search_history."""
    load = sum(demands[s] for s in route)
    return max(0.0, load - capacity)


def solution_capacity_excess(routes, demands, capacity):
    """Summe der Kapazitätsüberschreitung über alle Fahrzeugtouren."""
    return sum(route_capacity_excess(r, demands, capacity) for r in routes)


def route_timeline(route, D, earliest, latest, service):
    """Simuliert Ankunft/Wartezeit/Start je Stopp entlang einer Tour und
    markiert Zeitfenster-Verletzungen (Ankunft nach dem spätesten Start)."""
    t = 0.0
    prev = 0
    timeline = []
    for s in route:
        node = s + 1
        travel = D[prev][node]
        arrival = t + travel
        start = max(arrival, earliest[s])
        violation = start > latest[s] + EPS
        timeline.append(
            {"stop": s, "arrival": arrival, "start": start, "wait": start - arrival, "violation": violation}
        )
        t = start + service[s]
        prev = node
    return timeline


def evaluate_route(route, D, earliest, latest, service, tw_enabled):
    """Distanz und Anzahl Zeitfenster-Verletzungen einer Tour (Verletzungen
    nur berechnet, wenn tw_enabled aktiv ist - spart unnötige Arbeit sonst)."""
    dist = route_cost(route, D)
    if not tw_enabled or not route:
        return dist, 0, []
    timeline = route_timeline(route, D, earliest, latest, service)
    violations = sum(1 for t in timeline if t["violation"])
    return dist, violations, timeline


def solution_totals(routes, D, earliest, latest, service, tw_enabled):
    """Summe aus Distanz und Zeitfenster-Verletzungen über alle Fahrzeugtouren."""
    total_dist, total_viol = 0.0, 0
    for r in routes:
        d, v, _ = evaluate_route(r, D, earliest, latest, service, tw_enabled)
        total_dist += d
        total_viol += v
    return total_dist, total_viol


def distance_to_business(distance_km, speed_kmh, cost_per_km, co2_per_km=DEFAULT_CO2_PER_KM):
    """Rechnet eine Distanz (interpretiert als km) in Fahrzeit (h), Kraftstoffkosten
    (€) und CO2-Ausstoß (kg) um - macht den Business-/Nachhaltigkeits-Case greifbar
    statt nur abstrakte Zahlen zu zeigen."""
    hours = distance_km / speed_kmh if speed_kmh > 0 else 0.0
    cost = distance_km * cost_per_km
    co2 = distance_km * co2_per_km
    return hours, cost, co2
