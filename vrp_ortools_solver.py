"""
Anbindung an Googles Open-Source-Solver OR-Tools als fünfte, unabhängige
Lösungsmethode zum Vergleich mit den vier selbst implementierten Heuristiken.
"""

from ortools.constraint_solver import pywrapcp, routing_enums_pb2


def solve_with_ortools(n_stops, D, demands, capacity, n_vehicles, earliest, latest, service, tw_enabled, time_limit_s):
    """Löst dasselbe Problem (gleiche Distanzmatrix, gleiche Nebenbedingungen)
    mit Googles OR-Tools-Routing-Solver (Guided Local Search). Zeitfenster
    werden als weiche Obergrenze modelliert (Strafkosten statt harter
    Unzulässigkeit), damit der Solver – wie unsere eigene Heuristik – auch
    bei knappen Fenstern eine Lösung liefert. Gibt None zurück, wenn keine
    Lösung gefunden wurde (z. B. Kapazität strukturell zu gering)."""
    manager = pywrapcp.RoutingIndexManager(n_stops + 1, n_vehicles, 0)
    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index, to_index):
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        return int(round(D[i][j]))

    transit_idx = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

    def demand_callback(from_index):
        i = manager.IndexToNode(from_index)
        return int(demands[i - 1]) if i > 0 else 0

    demand_idx = routing.RegisterUnaryTransitCallback(demand_callback)
    routing.AddDimensionWithVehicleCapacity(demand_idx, 0, [int(capacity)] * n_vehicles, True, "Capacity")

    if tw_enabled:
        service_arr = [0.0] + list(service)

        def time_callback(from_index, to_index):
            i = manager.IndexToNode(from_index)
            j = manager.IndexToNode(to_index)
            return int(round(D[i][j])) + int(round(service_arr[i]))

        time_idx = routing.RegisterTransitCallback(time_callback)
        horizon = int(max(200.0, float(latest.max()) if len(latest) else 200.0) * 2)
        routing.AddDimension(time_idx, horizon, horizon, True, "Time")
        time_dimension = routing.GetDimensionOrDie("Time")
        penalty = 1000
        for s in range(n_stops):
            node_index = manager.NodeToIndex(s + 1)
            # Früheste Startzeit als harte Untergrenze: erzwingt Warten, falls das
            # Fahrzeug zu früh ankommt - genau wie in unserer eigenen Bewertung
            # (evaluate_route). Ohne diese Zeile kennt der Solver nur die späteste
            # Grenze und kann einen "spät gewünschten" Stopp an den Tourbeginn
            # legen, was in der Nachbewertung zu unnötigen Verletzungen führt.
            time_dimension.CumulVar(node_index).SetMin(int(round(earliest[s])))
            time_dimension.SetCumulVarSoftUpperBound(node_index, int(round(latest[s])), penalty)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    search_parameters.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    search_parameters.time_limit.FromSeconds(int(time_limit_s))

    solution = routing.SolveWithParameters(search_parameters)
    if solution is None:
        return None

    routes = []
    for v in range(n_vehicles):
        index = routing.Start(v)
        route = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                route.append(node - 1)
            index = solution.Value(routing.NextVar(index))
        routes.append(route)
    return routes
