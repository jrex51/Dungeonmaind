"""
Data models and API contract for the geographic map (issue #46).

These models are the shared contract that the rest of Release 3 builds on:
spatial relation extraction (#47), map generation (#48), the map API and
storage (#49) and the frontend map (#50/#51). Behaviour lives in those
issues; this module only defines the shape of the data.

Design decisions worth keeping:

* Node and edge ids are **deterministic** (see ``make_node_id`` /
  ``make_edge_id``). The same place mentioned many times must collapse into a
  single node, and a repeated relation into a single edge. Defining that rule
  here - rather than inside the generator - stops each consumer inventing its
  own and producing a different graph.
* ``kind`` mirrors the two entity types the existing extractor already
  produces (``place_candidate`` -> named, ``generic_location`` -> generic), so
  the frontend can render "Waterdeep" differently from "a cave".
* ``aliases`` exists because one real place arrives under several surface
  forms: the transcript says both "Castle Ravenwatch" and "the castle", and
  speech-to-text also garbles proper nouns. Without it, one place becomes
  several nodes.
* Times are transcript seconds (floats), consistent with
  ``TimelineSourceSegment`` - not wall-clock time.
* ``confidence`` is optional: an LLM-based extractor can supply one, a
  rule-based extractor leaves it ``None``.
"""

import re
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class SpatialRelation(str, Enum):
    """
    Relations an edge may express between two locations.

    These nine values are the whole vocabulary, matching what the map view
    accepts. A relation the extractor recognises but cannot place on a map
    ("behind", "above") produces no edge rather than a tenth value: the view
    rejects an entire response that contains a relation it does not know.
    """

    north_of = "north_of"
    south_of = "south_of"
    east_of = "east_of"
    west_of = "west_of"
    near = "near"
    inside = "inside"
    contains = "contains"
    connected_to = "connected_to"
    travelled_to = "travelled_to"


class LocationKind(str, Enum):
    """Whether a location is a proper name or a common noun."""

    named = "named"        # Waterdeep, Castle Ravenwatch
    generic = "generic"    # a cave, the old bridge


def make_node_id(name: str, scope: str | None = None) -> str:
    """
    Build the deterministic id for a location.

    Two mentions of the same place must produce the same id so they merge into
    one node. Keep this the single source of truth for node identity.
    """

    normalized = re.sub(
        r"[^a-z0-9]+",
        "-",
        name.casefold(),
    ).strip("-") or "unknown"

    if scope:
        prefix = re.sub(r"[^a-z0-9]+", "-", scope.casefold()).strip("-")
        if prefix:
            return f"{prefix}:{normalized}"

    return normalized


def make_edge_id(
    source: str,
    relation: "SpatialRelation | str",
    target: str,
) -> str:
    """
    Build the deterministic id for a relation.

    The same relation stated twice must produce the same id so it merges into
    one edge instead of duplicating.
    """

    relation_value = (
        relation.value
        if isinstance(relation, SpatialRelation)
        else str(relation)
    )

    return f"{source}:{relation_value}:{target}"


class MapNode(BaseModel):
    """A single location on the campaign map."""

    id: str = Field(
        ...,
        min_length=1,
        description="Deterministic id from make_node_id(name)",
    )

    name: str = Field(
        ...,
        min_length=1,
        max_length=120,
    )

    kind: LocationKind = LocationKind.generic

    aliases: list[str] = Field(
        default_factory=list,
        description="Other surface forms of the same place",
    )

    mentions: int = Field(
        default=1,
        ge=1,
        description="How often the location was mentioned",
    )

    first_seen: float = Field(
        default=0.0,
        ge=0.0,
        description="Transcript seconds of the first mention",
    )

    last_seen: float = Field(
        default=0.0,
        ge=0.0,
    )


class MapEdge(BaseModel):
    """A spatial relation between two locations."""

    id: str = Field(
        ...,
        min_length=1,
        description="Deterministic id from make_edge_id(...)",
    )

    source: str = Field(
        ...,
        min_length=1,
        description="MapNode.id the relation starts from",
    )

    target: str = Field(
        ...,
        min_length=1,
        description="MapNode.id the relation points to",
    )

    relation: SpatialRelation

    evidence: str = Field(
        default="",
        max_length=2000,
        description="Transcript text that justifies the relation",
    )

    timestamp: float = Field(
        default=0.0,
        ge=0.0,
    )

    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional extractor confidence; None when not available",
    )

    count: int = Field(
        default=1,
        ge=1,
        description="How often this relation was observed (journey traversals)",
    )


class MapData(BaseModel):
    """The complete geographic map built from a session's transcription."""

    nodes: list[MapNode] = Field(
        default_factory=list,
    )

    edges: list[MapEdge] = Field(
        default_factory=list,
    )

    source_segment_count: int = Field(
        default=0,
        ge=0,
        description="Timeline events the map was built from",
    )

    generated_at: str | None = Field(
        default=None,
        description="ISO-8601 UTC timestamp of the last generation",
    )

    @model_validator(mode="after")
    def _edges_must_reference_known_nodes(self) -> "MapData":
        """Every edge endpoint must exist in nodes[].

        Enforced here so a generator cannot silently ship a broken graph;
        during development this caught edges pointing at places the location
        extractor never produced.
        """
        known = {node.id for node in self.nodes}
        unknown = sorted(
            {end for edge in self.edges for end in (edge.source, edge.target)}
            - known
        )
        if unknown:
            raise ValueError(f"edges reference unknown node ids: {unknown}")
        return self


class MapResponse(BaseModel):
    """
    Response for reading the stored map (GET /map).

    Both map endpoints return this same shape. The map view requires
    nodes, edges and source_segment_count on each of them and discards a
    response that is missing any of the three, so source_segment_count
    belongs here rather than only on the generation response. The remaining
    fields are additions the view ignores.
    """

    nodes: list[MapNode] = Field(default_factory=list)
    edges: list[MapEdge] = Field(default_factory=list)

    source_segment_count: int = Field(default=0, ge=0)

    total_nodes: int = Field(default=0, ge=0)
    total_edges: int = Field(default=0, ge=0)

    generated_at: str | None = None


class MapGenerationResponse(MapResponse):
    """Response for regenerating the map (POST /map/generate)."""
