from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypedDict

from sqlalchemy.orm import joinedload, selectinload

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

    pokemon_id = utils.to_id(utils.remove_diacritics(msg.args[0].lower()))

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

                results[version]["slots"][slots_key]["rarity"] += (
                    encounter.encounter_slot.rarity or 0
                )

        html = utils.render_template("commands/locations.html", results=results)

        if not html:
            await msg.reply("No data available.")
            return

        await msg.reply_htmlbox('<div class="ladder">' + html + "</div>")


@command_wrapper(aliases=("encounter",))
async def encounters(msg: Message) -> None:
    location_id = utils.to_id(utils.remove_diacritics(msg.arg.lower()))

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
