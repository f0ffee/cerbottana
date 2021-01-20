from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Column
from typing_extensions import Protocol

import databases.veekun as v
import utils
from database import Database
from plugins import command_wrapper

if TYPE_CHECKING:
    from models.message import Message


class Translatable(Protocol):
    # pylint: disable=too-few-public-methods,unsubscriptable-object
    local_language_id: Column[int]
    name: Column[str]
    name_normalized: Column[str | None]


@command_wrapper(
    aliases=("translation", "trad"), helpstr="Traduce abilità, mosse e strumenti."
)
async def translate(msg: Message) -> None:
    if len(msg.args) > 3:
        return

    parola = utils.to_user_id(utils.remove_accents(msg.args[0]))
    if parola == "":
        await msg.reply("Cosa devo tradurre?")
        return

    languages_list: list[int] = []
    for lang in msg.args[1:]:  # Get language ids from the command parameters
        languages_list.append(utils.get_language_id(lang))
    languages_list.append(msg.language_id)  # Add the room language
    languages_list.extend([9, 8])  # Hardcode english and italian as fallbacks

    # Get the first two unique languages
    languages = tuple(dict.fromkeys(languages_list))[:2]

    results: list[tuple[str, str]] = []

    db = Database.open("veekun")

    with db.get_session() as session:

        tables: dict[str, type[Translatable]] = {
            "ability": v.AbilityNames,
            "item": v.ItemNames,
            "move": v.MoveNames,
            "nature": v.NatureNames,
        }

        for category_name, names_table in tables.items():
            rs = (
                session.query(names_table)
                .filter(
                    names_table.local_language_id.in_(languages),
                    names_table.name_normalized == parola,
                )
                .all()
            )
            for row in rs:
                translation = next(
                    (
                        name.name
                        for name in getattr(
                            getattr(row, category_name), f"{category_name}_names"
                        )
                        if name.local_language_id in languages
                        and name.local_language_id != row.local_language_id
                    ),
                    None,
                )
                if translation is not None:
                    res = (category_name, translation)
                    if res not in results:
                        results.append(res)

    if results:
        if len(results) == 1:
            await msg.reply(results[0][1])
            return
        resultstext = ""
        for k in results:
            if resultstext != "":
                resultstext += ", "
            resultstext += "{trad} ({cat})".format(trad=k[1], cat=k[0])
        await msg.reply(resultstext)
        return

    await msg.reply("Non trovato")
