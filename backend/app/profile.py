"""Combined community taste profile: which entities, and who named them."""
from dataclasses import dataclass, field

from .models import ResolvedTaste, SlimEntity

MAX_SIGNAL_IDS = 25  # cap on signal.interests.entities per request


def short_type(entity: SlimEntity) -> str:
    return entity.type.rsplit(":", 1)[-1]


@dataclass
class ProfileEntity:
    entity: SlimEntity
    members: list[str] = field(default_factory=list)
    display: str = ""  # what to call it in text: the member's own spelling when it differs from Qloo's only by case

    @property
    def weight(self) -> int:  # client-side weight = number of members who named it
        return len(self.members)


@dataclass
class Profile:
    members: list[str]
    entities: dict[str, ProfileEntity]  # keyed by entity id, in first-seen order

    def ids(self, cap: int = MAX_SIGNAL_IDS, types: set[str] | None = None) -> list[str]:
        """Signal ids for a Qloo query. `types` (short names like "artist") restricts which entities
        are used; if that leaves nothing, all entities are used instead.
        Entities named by several members first (highest weight), then round-robin across members
        so a big group can't crowd out the people who happened to be listed last."""
        pool = [pe for pe in self.entities.values() if types is None or short_type(pe.entity) in types]
        pool = pool or list(self.entities.values())
        shared = sorted((pe for pe in pool if pe.weight > 1), key=lambda pe: -pe.weight)
        chosen = [pe.entity.id for pe in shared][:cap]
        queues = {
            m: [pe.entity.id for pe in pool if pe.weight == 1 and pe.members == [m]]
            for m in self.members
        }
        while len(chosen) < cap and any(queues.values()):
            for m in self.members:
                if queues[m] and len(chosen) < cap:
                    chosen.append(queues[m].pop(0))
        return chosen

    def member_ids(self, member: str) -> list[str]:
        return [i for i, pe in self.entities.items() if member in pe.members]

    def name_of(self, entity_id: str) -> str:
        pe = self.entities.get(entity_id)
        return pe.entity.name if pe else entity_id


def _display_name(typed: str, entity: SlimEntity) -> str:
    """"Tems", not Qloo's "TEms": keep the member's text when it is a case-insensitive match."""
    t = typed.strip()
    return t if t and t.lower() == entity.name.lower() else entity.name


def build_profile(resolved: list[ResolvedTaste]) -> Profile:
    members: list[str] = []
    entities: dict[str, ProfileEntity] = {}
    for r in resolved:
        if r.member not in members:
            members.append(r.member)
        if r.entity is None:
            continue
        pe = entities.setdefault(r.entity.id, ProfileEntity(entity=r.entity, display=_display_name(r.input, r.entity)))
        if r.member not in pe.members:  # one member naming it twice still counts once
            pe.members.append(r.member)
    return Profile(members=members, entities=entities)
