from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypedDict

from sqlalchemy import func
from sqlalchemy.orm import selectinload

import databases.veekun as v
import utils
from database import Database
from plugins import command_wrapper

if TYPE_CHECKING:
    from models.message import Message


@command_wrapper(aliases=("location",))
async def locations(msg: Message) -> None:
    if len(msg.args) < 1:
        return

    pokemon_id = utils.to_user_id(utils.remove_diacritics(msg.args[0].lower()))

    language_id = msg.language_id
    if len(msg.args) >= 2:
        language_id = utils.get_language_id(msg.args[1], fallback=language_id)

    db = Database.open("veekun")

    with db.get_session(language_id) as session:

        class SlotsKeyTuple(NamedTuple):
            area: v.LocationAreas
            method: v.EncounterMethods
            min_level: int
            max_level: int
            conditions: frozenset[v.EncounterConditionValues]

        class SlotsDict(TypedDict):
            route_number: int
            location: str
            rarity: int

        class ResultsDict(TypedDict):
            slots: dict[SlotsKeyTuple, SlotsDict]

        pokemon_species: v.PokemonSpecies | None = (
            session.query(v.PokemonSpecies)
            .options(  # type: ignore  # sqlalchemy
                selectinload(v.PokemonSpecies.pokemon)
                .selectinload(v.Pokemon.encounters)
                .options(
                    selectinload(v.Encounters.version).selectinload(
                        v.Versions.version_names
                    ),
                    selectinload(v.Encounters.location_area).options(
                        selectinload(v.LocationAreas.location_area_prose),
                        selectinload(v.LocationAreas.location).selectinload(
                            v.Locations.location_names
                        ),
                    ),
                    selectinload(v.Encounters.encounter_slot)
                    .selectinload(v.EncounterSlots.encounter_method)
                    .selectinload(v.EncounterMethods.encounter_method_prose),
                    selectinload(v.Encounters.encounter_condition_value_map)
                    .selectinload(
                        v.EncounterConditionValueMap.encounter_condition_value
                    )
                    .selectinload(
                        v.EncounterConditionValues.encounter_condition_value_prose
                    ),
                )
            )
            .filter_by(identifier=pokemon_id)
            .one_or_none()
        )
        if pokemon_species is None:
            await msg.reply("Pokémon not found.")
            return

        results: dict[v.Versions, ResultsDict] = {}

        for pokemon in pokemon_species.pokemon:
            for encounter in pokemon.encounters:

                version = encounter.version
                if version not in results:
                    results[version] = {"slots": {}}

                area = encounter.location_area
                location = area.location
                full_location_name = ""
                if location.name:
                    full_location_name += location.name
                if location.subtitle:
                    full_location_name += " - " + location.subtitle
                if area.name:
                    full_location_name += " (" + area.name + ")"

                conditions = frozenset(
                    i.encounter_condition_value
                    for i in encounter.encounter_condition_value_map
                )

                slots_key = SlotsKeyTuple(
                    area,
                    encounter.encounter_slot.encounter_method,
                    encounter.min_level,
                    encounter.max_level,
                    conditions,
                )

                if slots_key not in results[version]["slots"]:
                    results[version]["slots"][slots_key] = {
                        "route_number": location.route_number or 0,
                        "location": full_location_name,
                        "rarity": 0,
                    }

                results[version]["slots"][slots_key][
                    "rarity"
                ] += encounter.encounter_slot.rarity

        html = utils.render_template("commands/locations.html", results=results)

        if not html:
            await msg.reply("No data available.")
            return

        await msg.reply_htmlbox('<div class="ladder">' + html + "</div>")


@command_wrapper(aliases=("encounter",))
async def encounters(msg: Message) -> None:
    location_id = utils.to_user_id(utils.remove_diacritics(msg.arg.lower()))

    db = Database.open("veekun")

    with db.get_session() as session:

        class SlotsDict(TypedDict):
            pokemon: str
            method: str
            min_level: int
            max_level: int
            conditions: frozenset[int]
            rarity: int

        class AreasDict(TypedDict):
            name: str
            slots: dict[tuple[int, int, int, int, frozenset[int]], SlotsDict]

        class ResultsDict(TypedDict):
            name: str
            areas: dict[int, AreasDict]

        results: dict[int, ResultsDict] = {}

        all_conditions = {
            i[0]: i[1]
            for i in (
                session.query(
                    v.EncounterConditionValueProse.encounter_condition_value_id,
                    v.EncounterConditionValueProse.name,
                )
                .select_from(
                    v.EncounterConditionValueProse
                )  # type: ignore  # sqlalchemy
                .filter_by(local_language_id=9)
            )
        }

        rs = (
            session.query(
                v.LocationAreas.id.label("area_id"),
                v.LocationAreaProse.name.label("area_name"),
                v.Versions.id.label("version_id"),
                v.VersionNames.name.label("version_name"),
                v.Pokemon.id.label("pokemon_id"),
                v.PokemonSpeciesNames.name.label(
                    "pokemon_species_name"
                ),  # DA GUARDARE PERCHÈ SÌ
                v.EncounterSlots.rarity,
                v.EncounterMethods.id.label("method_id"),
                v.EncounterMethodProse.name.label("method_name"),
                v.Encounters.min_level,
                v.Encounters.max_level,
                func.group_concat(
                    v.EncounterConditionValueMap.encounter_condition_value_id
                ).label("conditions"),
            )
            .select_from(v.Locations)  # type: ignore  # sqlalchemy
            .join(v.Locations.location_areas)
            .outerjoin(
                v.LocationAreas.location_area_prose.and_(
                    v.LocationAreaProse.local_language_id == 9
                )
            )
            .join(v.LocationAreas.encounters)
            .join(v.Encounters.version)
            .outerjoin(
                v.Versions.version_names.and_(v.VersionNames.local_language_id == 9)
            )
            .join(v.Encounters.pokemon)
            .join(v.Pokemon.species)
            .outerjoin(
                v.PokemonSpecies.pokemon_species_names.and_(
                    v.PokemonSpeciesNames.local_language_id == 9
                )
            )
            .join(v.Encounters.encounter_slot)
            .join(v.EncounterSlots.encounter_method)
            .outerjoin(
                v.EncounterMethods.encounter_method_prose.and_(
                    v.EncounterMethodProse.local_language_id == 9
                )
            )
            .outerjoin(v.Encounters.encounter_condition_value_map)
            .filter(v.Locations.identifier == location_id)
            .group_by(v.Encounters.id)
            .order_by(
                v.Versions.id,
                v.LocationAreaProse.name,
                v.PokemonSpecies.order,
                v.Pokemon.order,
                v.EncounterMethods.id,
                v.Encounters.min_level,
                v.Encounters.max_level,
                v.EncounterSlots.rarity.desc(),
            )
            .all()
        )

        for row in rs:
            if row.version_id not in results:
                results[row.version_id] = {"name": row.version_name, "areas": {}}

            if row.area_id not in results[row.version_id]["areas"]:
                results[row.version_id]["areas"][row.area_id] = {
                    "name": row.area_name,
                    "slots": {},
                }

            conditions = (
                frozenset(int(i) for i in row.conditions.split(","))
                if row.conditions
                else frozenset()
            )

            slots_key = (
                row.pokemon_id,
                row.method_id,
                row.min_level,
                row.max_level,
                conditions,
            )

            if slots_key not in results[row.version_id]["areas"][row.area_id]["slots"]:
                results[row.version_id]["areas"][row.area_id]["slots"][slots_key] = {
                    "pokemon": row.pokemon_species_name,
                    "method": row.method_name,
                    "min_level": 100,
                    "max_level": 0,
                    "conditions": conditions,
                    "rarity": 0,
                }

            results[row.version_id]["areas"][row.area_id]["slots"][slots_key][
                "min_level"
            ] = min(
                results[row.version_id]["areas"][row.area_id]["slots"][slots_key][
                    "min_level"
                ],
                row.min_level,
            )
            results[row.version_id]["areas"][row.area_id]["slots"][slots_key][
                "max_level"
            ] = max(
                results[row.version_id]["areas"][row.area_id]["slots"][slots_key][
                    "max_level"
                ],
                row.max_level,
            )

            results[row.version_id]["areas"][row.area_id]["slots"][slots_key][
                "rarity"
            ] += row.rarity

    html = utils.render_template(
        "commands/encounters.html", results=results, all_conditions=all_conditions
    )

    if not html:
        await msg.reply("Nessun dato")
        return

    await msg.reply_htmlbox('<div class="ladder">' + html + "</div>")
