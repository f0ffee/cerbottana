from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from sqlalchemy import func

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

    db = Database.open("veekun")

    with db.get_session() as session:
        version_group_id: int | None = (
            session.query(v.VersionGroups.id)  # type: ignore  # sqlalchemy
            .filter_by(identifier=version)
            .scalar()
        )

        if version_group_id is None:
            version_group_id = (
                session.query(v.Versions.version_group_id)  # type: ignore  # sqlalchemy
                .filter_by(identifier=version)
                .scalar()
            )
            if version_group_id is None:
                return

        class MovesDict(TypedDict):
            name: str
            level: int | None
            machine: str | None
            forms: set[int]

        class ResultsDict(TypedDict):
            name: str
            moves: dict[str, MovesDict]
            form_column: bool

        results: dict[int, ResultsDict] = {}

        all_forms = {
            i[0]: i[1]
            for i in (
                session.query(
                    v.Pokemon.id,
                    func.ifnull(
                        v.PokemonFormNames.pokemon_name, v.PokemonSpeciesNames.name
                    ),
                )
                .select_from(v.PokemonSpecies)  # type: ignore  # sqlalchemy
                .join(v.PokemonSpecies.pokemon)
                .outerjoin(
                    v.PokemonSpecies.pokemon_species_names.and_(
                        v.PokemonSpeciesNames.local_language_id == 9
                    )
                )
                .outerjoin(v.Pokemon.pokemon_forms.and_(v.PokemonForms.is_default))
                .outerjoin(
                    v.PokemonForms.pokemon_form_names.and_(
                        v.PokemonFormNames.local_language_id == 9
                    )
                )
                .filter(v.PokemonSpecies.identifier == pokemon_id)
                .all()
            )
        }
        all_forms_ids = all_forms.keys()

        rs = (
            session.query(
                v.PokemonMoveMethods.id.label("method_id"),
                v.PokemonMoveMethodProse.name.label("method_name"),
                v.Moves.id.label("move_id"),
                v.MoveNames.name.label("move_name"),
                v.PokemonMoves.level,
                v.ItemNames.name.label("machine"),
                v.Pokemon.id.label("pokemon_id"),
            )
            .select_from(v.PokemonSpecies)  # type: ignore  # sqlalchemy
            .join(v.PokemonSpecies.pokemon)
            .join(
                v.Pokemon.pokemon_moves.and_(
                    v.PokemonMoves.version_group_id == version_group_id
                )
            )
            .join(v.PokemonMoves.move)
            .outerjoin(v.Moves.move_names.and_(v.MoveNames.local_language_id == 9))
            .join(v.PokemonMoves.pokemon_move_method)
            .outerjoin(
                v.PokemonMoveMethods.pokemon_move_method_prose.and_(
                    v.PokemonMoveMethodProse.local_language_id == 9
                )
            )
            .outerjoin(
                v.Moves.machines.and_(
                    v.Machines.version_group_id == v.PokemonMoves.version_group_id
                )
            )
            .outerjoin(v.Machines.item)
            .outerjoin(v.Items.item_names.and_(v.ItemNames.local_language_id == 9))
            .filter(v.PokemonSpecies.identifier == pokemon_id)
            .order_by(
                v.PokemonMoveMethods.id,
                v.PokemonMoves.level,
                v.PokemonMoves.order,
                v.Machines.machine_number,
                v.Pokemon.id,
                v.MoveNames.name,
            )
            .all()
        )

        for row in rs:
            if row.method_id not in results:
                results[row.method_id] = {
                    "name": row.method_name,
                    "moves": {},
                    "form_column": False,
                }

            if row.move_id not in results[row.method_id]["moves"]:
                results[row.method_id]["moves"][row.move_id] = {
                    "name": row.move_name,
                    "level": int(row.level),
                    "machine": row.machine,
                    "forms": set(),
                }
            results[row.method_id]["moves"][row.move_id]["forms"].add(row.pokemon_id)

        for method_id in results:
            for move_id in results[method_id]["moves"]:
                if results[method_id]["moves"][move_id]["forms"] == all_forms_ids:
                    results[method_id]["moves"][move_id]["forms"] = set()
                else:
                    results[method_id]["form_column"] = True

        html = utils.render_template(
            "commands/learnsets.html", results=results, all_forms=all_forms
        )

        if not html:
            await msg.reply("Nessun dato")
            return

        await msg.reply_htmlbox('<div class="ladder">' + html + "</div>")
