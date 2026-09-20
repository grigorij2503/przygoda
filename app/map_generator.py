import random
from typing import Any

from app.worlds.models import MapProfile, MapRoomDefinition
from app.worlds.registry import get_default_world_pack


GENERATOR_VERSION = 1


def _default_profile() -> MapProfile:
    return get_default_world_pack().map_profile


def generate_campaign_map(
    seed: int,
    title: str,
    theme: str,
    map_profile: MapProfile | None = None,
) -> dict[str, Any]:
    """Build a deterministic graph using only the selected world's map profile."""
    profile = map_profile or _default_profile()
    rng = random.Random(seed)
    main_count = rng.randint(6, 8)
    branch_count = rng.randint(3, min(5, (main_count - 2) * 2))
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    definitions = {room.id: room for room in profile.room_types}

    entrance = definitions["entrance"]
    finale = definitions["finale"]
    main_rooms = [
        (room, name)
        for room in profile.room_types
        if room.id not in {"entrance", "finale"} and not room.branch
        for name in room.names
    ]
    branch_rooms = [
        (room, name)
        for room in profile.room_types
        for name in (room.branch_names or (room.names if room.branch else ()))
    ]
    if len(main_rooms) < main_count - 2 or not branch_rooms:
        raise ValueError(f"map profile {profile.generator_id} does not define enough rooms")
    rng.shuffle(main_rooms)

    for index in range(main_count):
        x = 95 + index * 155
        y = 245 + rng.choice((-20, 0, 20))
        if index == 0:
            room, name = entrance, profile.start_location_name
        elif index == main_count - 1:
            room, name = finale, profile.finale_location_name
        else:
            room, name = main_rooms[index - 1]
        nodes.append(_node(f"room-{index + 1:02d}", x, y, room, name, rng, True))
        if index:
            edges.append(_edge(f"room-{index:02d}", f"room-{index + 1:02d}", rng))

    branch_slots = [
        (anchor, direction)
        for anchor in range(1, main_count - 1)
        for direction in (-1, 1)
    ]
    rng.shuffle(branch_slots)
    rng.shuffle(branch_rooms)
    branch_ids: list[tuple[str, int, int]] = []

    for branch_index, (anchor, direction) in enumerate(branch_slots[:branch_count]):
        node_id = f"side-{branch_index + 1:02d}"
        x = 95 + anchor * 155 + rng.choice((-30, 0, 30))
        y = 245 + direction * 155
        room, name = branch_rooms[branch_index % len(branch_rooms)]
        nodes.append(_node(node_id, x, y, room, name, rng, False))
        edges.append(_edge(f"room-{anchor + 1:02d}", node_id, rng))
        branch_ids.append((node_id, anchor, direction))

    rng.shuffle(branch_ids)
    for node_id, anchor, direction in branch_ids[: rng.randint(0, 2)]:
        neighbor_anchor = anchor + rng.choice((-1, 1))
        if 0 < neighbor_anchor < main_count - 1:
            candidate = next(
                (
                    other_id
                    for other_id, other_anchor, other_direction in branch_ids
                    if other_anchor == neighbor_anchor and other_direction == direction
                ),
                None,
            )
            if candidate and not _has_edge(edges, node_id, candidate):
                edges.append(_edge(node_id, candidate, rng))

    return {
        "title": title,
        "theme": theme,
        "generator_id": profile.generator_id,
        "generator_version": profile.generator_version,
        "undiscovered_location_name": profile.undiscovered_location_name,
        "width": 190 + (main_count - 1) * 155,
        "height": 500,
        "start_node_id": "room-01",
        "final_node_id": f"room-{main_count:02d}",
        "nodes": nodes,
        "edges": edges,
    }


def _node(
    node_id: str,
    x: int,
    y: int,
    room: MapRoomDefinition,
    name: str,
    rng: random.Random,
    main_path: bool,
) -> dict[str, Any]:
    return {
        "id": node_id,
        "x": x,
        "y": y,
        "width": rng.choice((118, 128, 138)),
        "height": rng.choice((70, 78, 86)),
        "type": room.id,
        "name": name,
        "description": room.description,
        "contents": list(room.contents),
        "discovered_turn": 0 if room.id == "entrance" else None,
        "main_path": main_path,
    }


def _edge(source: str, target: str, rng: random.Random) -> dict[str, Any]:
    return {
        "from": source,
        "to": target,
        "kind": "door" if rng.random() < 0.62 else "passage",
        "locked": False,
    }


def _has_edge(edges: list[dict[str, Any]], source: str, target: str) -> bool:
    expected = {source, target}
    return any({edge["from"], edge["to"]} == expected for edge in edges)


def adjacent_node_ids(layout: dict[str, Any], node_id: str) -> set[str]:
    adjacent: set[str] = set()
    for edge in layout.get("edges", []):
        if edge.get("locked"):
            continue
        if edge.get("from") == node_id:
            adjacent.add(str(edge.get("to")))
        elif edge.get("to") == node_id:
            adjacent.add(str(edge.get("from")))
    return adjacent


def serialize_campaign_map(campaign_map: Any) -> dict[str, Any]:
    layout = campaign_map.layout or {}
    current_node_id = campaign_map.current_node_id or layout.get("start_node_id")
    discovered_history = list(campaign_map.discovered_node_ids or [])
    if current_node_id not in discovered_history:
        discovered_history.append(current_node_id)
    discovered = set(discovered_history)
    available = adjacent_node_ids(layout, current_node_id)

    nodes = []
    discovery_order = {
        node_id: index + 1 for index, node_id in enumerate(discovered_history)
    }
    for raw_node in layout.get("nodes", []):
        node = dict(raw_node)
        node_id = node.get("id")
        if node_id == current_node_id:
            visibility = "current"
        elif node_id in discovered:
            visibility = "visited"
        elif node_id in available:
            visibility = "available"
        else:
            visibility = "hidden"
        node["visibility"] = visibility
        node["visit_order"] = discovery_order.get(node_id)
        if visibility in {"hidden", "available"}:
            node["name"] = layout.get("undiscovered_location_name", "Nieodkryta lokacja")
            node["type"] = "unknown"
            node["custom_name"] = None
            node["system_name"] = None
            node["named_by"] = None
            node["description"] = "To miejsce nie zostało jeszcze odwiedzone."
            node["contents"] = []
            node["discovered_turn"] = None
        else:
            system_name = node.get("system_name") or node.get("name") or "Odwiedzone miejsce"
            custom_name = node.get("custom_name")
            node["name"] = custom_name or system_name
            node["system_name"] = system_name if custom_name else None
            node["description"] = (
                node.get("exploration_summary")
                or node.get("description")
                or "Odwiedzone miejsce wyprawy."
            )
            node["contents"] = node.get("notable_elements") or node.get("contents") or []
            if node.get("discovered_turn") is None and node["visit_order"] == 1:
                node["discovered_turn"] = 0
        nodes.append(node)

    edges = []
    for raw_edge in layout.get("edges", []):
        edge = dict(raw_edge)
        endpoints = {edge.get("from"), edge.get("to")}
        if endpoints.issubset(discovered):
            edge["visibility"] = "visited"
        elif current_node_id in endpoints and endpoints.intersection(available):
            edge["visibility"] = "available"
        else:
            edge["visibility"] = "hidden"
        edges.append(edge)

    return {
        "seed": campaign_map.seed,
        "generator_id": layout.get("generator_id"),
        "generator_version": campaign_map.generator_version,
        "width": layout.get("width", 1100),
        "height": layout.get("height", 500),
        "current_node_id": current_node_id,
        "available_node_ids": sorted(available),
        "discovered_count": len(discovered),
        "total_nodes": len(nodes),
        "nodes": nodes,
        "edges": edges,
    }
