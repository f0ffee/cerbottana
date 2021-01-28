from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import func
from sqlalchemy.orm import joinedload

import databases.veekun as v
import utils
from database import Database
from plugins import command_wrapper

if TYPE_CHECKING:
    from models.message import Message


@command_wrapper(aliases=("location",))
async def locations(msg: Message) -> None:
    pokemon_id = utils.to_user_id(utils.remove_diacritics(msg.arg.lower()))

    db = Database.open("veekun")

    with db.get_session() as session:

        class SlotsDict(TypedDict):
            location: str
            method: str
            min_level: int
            max_level: int
            conditions: frozenset[int]
            rarity: int

        class ResultsDict(TypedDict):
            name: str
            slots: dict[tuple[int, int, int, int, frozenset[int]], SlotsDict]

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
                v.Versions.id.label("version_id"),
                v.VersionNames.name.label("version_name"),
                v.LocationAreas.id.label("area_id"),
                v.LocationAreaProse.name.label("area_name"),
                v.LocationNames.name.label("location_name"),
                v.LocationNames.subtitle.label("location_subtitle"),
                v.EncounterSlots.rarity,
                v.EncounterMethods.id.label("method_id"),
                v.EncounterMethodProse.name.label("method_name"),
                v.Encounters.min_level,
                v.Encounters.max_level,
                func.group_concat(
                    v.EncounterConditionValueMap.encounter_condition_value_id
                ).label("conditions"),
            )
            .select_from(v.PokemonSpecies)  # type: ignore  # sqlalchemy
            .join(v.PokemonSpecies.pokemon)
            .join(v.Pokemon.encounters)
            .join(v.Encounters.version)
            .outerjoin(
                v.Versions.version_names.and_(v.VersionNames.local_language_id == 9)
            )
            .join(v.Encounters.location_area)
            .outerjoin(
                v.LocationAreas.location_area_prose.and_(
                    v.LocationAreaProse.local_language_id == 9
                )
            )
            .join(v.LocationAreas.location)
            .outerjoin(
                v.Locations.location_names.and_(v.LocationNames.local_language_id == 9)
            )
            .join(v.Encounters.encounter_slot)
            .join(v.EncounterSlots.encounter_method)
            .outerjoin(
                v.EncounterMethods.encounter_method_prose.and_(
                    v.EncounterMethodProse.local_language_id == 9
                )
            )
            .outerjoin(v.Encounters.encounter_condition_value_map)
            .filter(v.PokemonSpecies.identifier == pokemon_id)
            .group_by(v.Encounters.id)
            .order_by(
                v.Versions.id,
                v.Locations.route_number,
                v.LocationNames.name,
                v.LocationNames.subtitle,
                v.LocationAreaProse.name,
                v.EncounterMethods.id,
                v.Encounters.min_level,
                v.Encounters.max_level,
                v.EncounterSlots.rarity.desc(),
            )
            .all()
        )

        for row in rs:
            if row.version_id not in results:
                results[row.version_id] = {"name": row.version_name, "slots": {}}

            full_location_name = ""
            if row.location_name:
                full_location_name += row.location_name
            if row.location_subtitle:
                full_location_name += " - " + row.location_subtitle
            if row.area_name:
                full_location_name += " (" + row.area_name + ")"

            conditions = (
                frozenset(int(i) for i in row.conditions.split(","))
                if row.conditions
                else frozenset()
            )

            slots_key = (
                row.area_id,
                row.method_id,
                row.min_level,
                row.max_level,
                conditions,
            )

            if slots_key not in results[row.version_id]["slots"]:
                results[row.version_id]["slots"][slots_key] = {
                    "location": full_location_name,
                    "method": row.method_name,
                    "min_level": 100,
                    "max_level": 0,
                    "conditions": conditions,
                    "rarity": 0,
                }

            results[row.version_id]["slots"][slots_key]["min_level"] = min(
                results[row.version_id]["slots"][slots_key]["min_level"],
                row.min_level,
            )
            results[row.version_id]["slots"][slots_key]["max_level"] = max(
                results[row.version_id]["slots"][slots_key]["max_level"],
                row.max_level,
            )

            results[row.version_id]["slots"][slots_key]["rarity"] += row.rarity

    html = utils.render_template(
        "commands/locations.html", results=results, all_conditions=all_conditions
    )

    if not html:
        await msg.reply("Nessun dato")
        return

    await msg.reply_htmlbox('<div class="ladder">' + html + "</div>")


@command_wrapper(aliases=("encounter",))
async def encounters(msg: Message) -> None:
    location_id = utils.to_user_id(utils.remove_diacritics(msg.arg.lower()))

    db = Database.open("veekun")

    with db.get_session() as session:

        class ConditionsDict(TypedDict):
            rarity: int
            description: str

        class SlotsDict(TypedDict):
            pokemon: str
            method: str
            min_level: int
            max_level: int
            conditions: dict[tuple[int, ...], ConditionsDict]
            rarity: int

        class AreasDict(TypedDict):
            name: str
            slots: dict[tuple[int, int], SlotsDict]

        class ResultsDict(TypedDict):
            name: str
            areas: dict[int, AreasDict]

        results: dict[int, ResultsDict] = {}

        location = (
            session.query(v.Locations)  # type: ignore  # sqlalchemy
            .options(
                joinedload(v.Locations.location_areas)
                .joinedload(v.LocationAreas.location_area_prose)
                .raiseload("*")
            )
            .filter_by(identifier=location_id)
            .first()
        )

        if location:

            for area in location.location_areas:

                area_name = next(
                    (
                        i.name
                        for i in area.location_area_prose
                        if i.local_language_id == 9
                    ),
                    "",
                )

                for encounter in area.encounters:

                    version = encounter.version
                    version_name = next(
                        (
                            i.name
                            for i in version.version_names
                            if i.local_language_id == 9
                        ),
                        "",
                    )

                    pokemon = encounter.pokemon
                    pokemon_species = pokemon.species
                    pokemon_species_name = next(
                        (
                            i.name
                            for i in pokemon_species.pokemon_species_names
                            if i.local_language_id == 9
                        ),
                        "",
                    )

                    encounter_slot = encounter.encounter_slot

                    method = encounter_slot.encounter_method
                    method_name = next(
                        (
                            i.name
                            for i in method.encounter_method_prose
                            if i.local_language_id == 9
                        ),
                        "",
                    )

                    condition_names = {}
                    for condition_value_map in encounter.encounter_condition_value_map:
                        condition = condition_value_map.encounter_condition_value
                        condition_names[condition.id] = next(
                            (
                                i.name
                                for i in condition.encounter_condition_value_prose
                                if i.local_language_id == 9
                            ),
                            "",
                        )

                    if version.id not in results:
                        results[version.id] = {"name": version_name, "areas": {}}

                    if area.id not in results[version.id]["areas"]:
                        results[version.id]["areas"][area.id] = {
                            "name": area_name,
                            "slots": {},
                        }

                    key = (method.id, pokemon.id)

                    if key not in results[version.id]["areas"][area.id]["slots"]:
                        results[version.id]["areas"][area.id]["slots"][key] = {
                            "pokemon": pokemon_species_name,
                            "method": method_name,
                            "min_level": 100,
                            "max_level": 0,
                            "conditions": {},
                            "rarity": 0,
                        }

                    results[version.id]["areas"][area.id]["slots"][key][
                        "min_level"
                    ] = min(
                        results[version.id]["areas"][area.id]["slots"][key][
                            "min_level"
                        ],
                        encounter.min_level,
                    )
                    results[version.id]["areas"][area.id]["slots"][key][
                        "max_level"
                    ] = max(
                        results[version.id]["areas"][area.id]["slots"][key][
                            "max_level"
                        ],
                        encounter.max_level,
                    )

                    if condition_names:
                        key_conditions = tuple(sorted(condition_names.keys()))
                        if (
                            key_conditions
                            not in results[version.id]["areas"][area.id]["slots"][key][
                                "conditions"
                            ]
                        ):
                            results[version.id]["areas"][area.id]["slots"][key][
                                "conditions"
                            ][key_conditions] = {
                                "rarity": 0,
                                "description": ", ".join(condition_names.values()),
                            }
                        results[version.id]["areas"][area.id]["slots"][key][
                            "conditions"
                        ][key_conditions]["rarity"] += encounter_slot.rarity
                    else:
                        results[version.id]["areas"][area.id]["slots"][key][
                            "rarity"
                        ] += encounter_slot.rarity

    for version_id in sorted(results.keys()):
        results[version_id]["areas"] = dict(
            sorted(results[version_id]["areas"].items())
        )
        for area_id in results[version_id]["areas"].keys():
            results[version_id]["areas"][area_id]["slots"] = dict(
                sorted(results[version_id]["areas"][area_id]["slots"].items())
            )

    html = utils.render_template(
        "commands/encounters.html", versions=sorted(results.keys()), results=results
    )

    if not html:
        await msg.reply("Nessun dato")
        return

    await msg.reply_htmlbox('<div class="ladder">' + html + "</div>")
