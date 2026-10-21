"""Optional RMF telemetry connection; task/control behavior stays in RMF."""


def add_fleet(adapter, fleet_name, traits, graph, server_uri=''):
    if server_uri == '':
        # Retain the original call, including its native default of None.
        return adapter.add_fleet(fleet_name, traits, graph)
    return adapter.add_fleet(fleet_name, traits, graph, server_uri)
