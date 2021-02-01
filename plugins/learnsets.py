from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from sqlalchemy.orm import selectinload

import databases.veekun as v
import utils
from database import Database
from plugins import command_wrapper

if TYPE_CHECKING:
    from models.message import Message


@command_wrapper()
async def learnset(msg: Message) -> None:
    if len(msg.args) < 2:
        return

    pokemon_id = utils.to_user_id(utils.remove_diacritics(msg.args[0].lower()))
    version = utils.to_user_id(utils.remove_diacritics(msg.args[1].lower()))

    language_id = 9  # TEMP

    db = Database.open("veekun")

    with db.get_session() as session:

        class MovesDict(TypedDict):
            name: str
            level: int
            order: int
            machine_id: int | None
            machine: str | None
            forms: set[int]

        class ResultsDict(TypedDict):
            name: str
            moves: dict[str, MovesDict]
            form_column: bool

        version_group = (
            session.query(v.VersionGroups)
            .filter_by(identifier=version_id)
            .one_or_none()
        )

        if version_group is None:
            version = (
                session.query(v.Versions)
                .filter(v.Versions.identifier == version_id)
                .one_or_none()
            )
            if version is None:
                await msg.reply("Game version not found.")
                return
            version_group = version.version_group

        pokemon_species = (
            session.query(v.PokemonSpecies)
            .options(  # type: ignore  # sqlalchemy
                selectinload(v.PokemonSpecies.pokemon)
                .selectinload(
                    v.Pokemon.pokemon_moves.and_(
                        v.PokemonMoves.version_group_id == version_group.id
                    )
                )
                .options(
                    selectinload(v.PokemonMoves.move).options(
                        selectinload(v.Moves.move_names),
                        selectinload(
                            v.Moves.machines.and_(
                                v.Machines.version_group_id == version_group.id
                            )
                        )
                        .selectinload(v.Machines.item)
                        .selectinload(v.Items.item_names),
                    ),
                    selectinload(v.PokemonMoves.pokemon_move_method).selectinload(
                        v.PokemonMoveMethods.pokemon_move_method_prose
                    ),
                )
            )
            .filter_by(identifier=pokemon_id)
            .one_or_none()
        )
        if pokemon_species is None:
            await msg.reply("Pokémon not found.")
            return

        results: dict[int, ResultsDict] = {}

        all_forms = pokemon_species.all_forms(language_id)
        all_forms_ids = all_forms.keys()

        for pokemon in pokemon_species.pokemon:
            for pokemon_move in pokemon.pokemon_moves:

                method = pokemon_move.pokemon_move_method
                if method.id not in results:
                    results[method.id] = {
                        "name": method.get_translation(language_id),
                        "moves": {},
                        "form_column": False,
                    }

                move = pokemon_move.move
                if move.id not in results[method.id]["moves"]:
                    if move.machines:
                        machine_id = move.machines[0].machine_number
                        machine = move.machines[0].item.get_translation(language_id)
                    else:
                        machine_id = None
                        machine = None
                    results[method.id]["moves"][move.id] = {
                        "name": move.get_translation(language_id),
                        "level": int(pokemon_move.level),
                        "order": int(pokemon_move.order or 0),
                        "machine_id": machine_id,
                        "machine": machine,
                        "forms": set(),
                    }
                results[method.id]["moves"][move.id]["forms"].add(pokemon.id)

        for method_id in results:
            for move_id in results[method_id]["moves"]:
                if results[method_id]["moves"][move_id]["forms"] == all_forms_ids:
                    results[method_id]["moves"][move_id]["forms"] = set()
                else:
                    results[method_id]["form_column"] = True

        results = dict(sorted(results.items()))
        for method_id in results.keys():
            results[method_id]["moves"] = dict(
                sorted(
                    results[method_id]["moves"].items(),
                    key=lambda x: (
                        x[1]["level"],
                        x[1]["order"],
                        x[1]["machine_id"],
                        x[1]["name"],
                    ),
                )
            )

        html = utils.render_template(
            "commands/learnsets.html", results=results, all_forms=all_forms
        )

        if not html:
            await msg.reply("No data available.")
            return

        await msg.reply_htmlbox('<div class="ladder">' + html + "</div>")
