from __future__ import annotations

from collections import deque
from datetime import datetime
from textwrap import shorten
from time import time
from typing import TYPE_CHECKING

import pytz

import utils
from typedefs import RoomId

if TYPE_CHECKING:
    from connection import Connection

    from .user import User


class Room:
    """Represents a PS room.

    Room instances are saved in conn.rooms.

    Attributes:
        conn (Connection): Used to access the websocket.
        roomid (RoomId): Uniquely identifies a room, see utils.to_room_id.
        is_private (bool): True if room is unlisted/private.
        autojoin (bool): Whether the bot should join the room on startup. Defaults to
            False.
        buffer (deque[str]): Fixed list of the last room messages.
        language (str): Room language.
        language_id (int): Veekun id for language.
        modchat (bool): True if modchat level is at least "+".
        roombot (bool): True if cerbottana is roombot in this room.
        title (str): Formatted variant of roomid.
        users (dict[User, str]): User instance, rank string.
        no_mods_online (float | None)
        last_modchat_command (float)

    Todo:
        Rooms should be removed from conn.rooms if they |deinit|.
    """

    def __init__(
        self,
        conn: Connection,
        roomid: RoomId,
        autojoin: bool = False,
    ) -> None:
        # Attributes initialized directly
        self.conn = conn
        self.roomid = roomid
        self.autojoin = autojoin

        # Attributes initialized through handlers
        self.dynamic_buffer: deque[str] = deque(maxlen=20)
        self.language = "English"
        self.modchat = False
        self.roombot = False
        self.title = ""

        # Attributes updated within this instance
        self._users: dict[User, str] = {}  # user, rank
        self.no_mods_online: float | None = None
        self.last_modchat_command: float = 0

        # Register new initialized room
        if self.roomid in self.conn.rooms:
            warn = f"Warning: overriding previous data for {self.roomid}! "
            warn += "You should avoid direct initialization and use Room.get instead."
            print(warn)
        self.conn.rooms[self.roomid] = self

    @property
    def buffer(self) -> deque[str]:
        return self.dynamic_buffer.copy()

    @property
    def is_private(self) -> bool:
        return self.roomid not in self.conn.public_roomids

    @property
    def language_id(self) -> int:
        return utils.get_language_id(self.language)

    @property
    def users(self) -> dict[User, str]:
        return self._users

    def add_user(self, user: User, rank: str | None = None) -> None:
        """Adds a user to the room or updates it if it's already stored.

        If it's the first room joined by the user, it saves its instance in conn.users.

        Args:
            user (User): User to add.
            rank (str | None): Room rank of user. Defaults to None if rank is unchanged.
        """
        if not rank:
            rank = self._users[user] if user in self._users else " "
        self._users[user] = rank

        if user.has_role("driver", self, ignore_grole=True):
            if not user.idle:
                self.no_mods_online = None
            else:
                self._check_no_mods_online()

        # User persistance
        if user.userid not in self.conn.users:
            self.conn.users[user.userid] = user

    def remove_user(self, user: User) -> None:
        """Removes a user from a room.

        If it was the only room the user was in, its instance is deleted.

        Args:
            user (User): User to remove.
        """
        if user in self._users:
            self._users.pop(user)
            self._check_no_mods_online()

    def __str__(self) -> str:
        return self.roomid

    def __contains__(self, user: User) -> bool:
        return user in self.users

    def _check_no_mods_online(self) -> None:
        if self.no_mods_online:
            return
        for user in self._users:
            if user.idle:
                continue
            if user.has_role("driver", self, ignore_grole=True):
                self.no_mods_online = None
                return
            self.no_mods_online = time()

    async def try_modchat(self) -> None:
        """Sets modchat in a specific time frame if the are no mods online."""
        if not self.modchat and self.no_mods_online:
            tz = pytz.timezone("Europe/Rome")
            timestamp = datetime.now(tz)
            minutes = timestamp.hour * 60 + timestamp.minute
            # 00:30 - 08:00
            if (
                30 <= minutes < 8 * 60
                and self.no_mods_online + (7 * 60) < time()
                and self.last_modchat_command + 15 < time()
            ):
                self.last_modchat_command = time()
                await self.send("/modchat +", False)

    async def send(self, message: str, escape: bool = True) -> None:
        """Sends a message to the room.

        Args:
            message (str): Text to be sent.
            escape (bool): True if PS commands should be escaped. Defaults to True.
        """
        if escape:
            if message[0] == "/":
                message = "/" + message
            elif message[0] == "!":
                message = " " + message
        await self.conn.send(f"{self.roomid}|{message}")

    async def send_rankhtmlbox(self, rank: str, message: str) -> None:
        """Sends an HTML box visible only to people with a specific rank.

        Args:
            rank (str): Minimum rank required to see the HTML box.
            message (str): HTML to be sent.
        """
        await self.send(f"/addrankhtmlbox {rank}, {message}", False)

    async def send_htmlbox(self, message: str) -> None:
        """Sends an HTML box visible to every user in the room.

        Args:
            message (str): HTML to be sent.
        """
        await self.send(f"/addhtmlbox {message}", False)

    async def send_htmlpage(self, pageid: str, page_room: Room) -> None:
        """Sends link to an HTML page in a room.

        Args:
            pageid (str): id of the htmlpage.
            page_room (Room): Room to be passed to the function.
        """
        if page_room:
            pageid += "0" + page_room.roomid
        await self.send(f"<<view-bot-{utils.to_user_id(self.conn.username)}-{pageid}>>")

    async def send_modnote(self, action: str, user: User, note: str = "") -> None:
        """Adds a modnote to a room.

        Args:
            action (str): id of the action performed.
            user (User): User who performed the action.
            note (str): additional notes. Defaults to "".
        """
        if not self.roombot:
            return

        arg = f"[{action}] {user.userid}"
        if note:
            arg += f": {note}"
        await self.send(f"/modnote {shorten(arg, 300)}", False)

    @classmethod
    def get(cls, conn: Connection, room: str) -> Room:
        """Safely retrieves a Room instance, if it exists, or creates a new one.

        Args:
            conn (Connection): Used to access the websocket.
            room (str): The room to retrieve.

        Returns:
            Room: Existing instance associated with roomid or newly created one.
        """
        roomid = utils.to_room_id(room)
        if roomid not in conn.rooms:
            conn.rooms[roomid] = cls(conn, roomid)
        return conn.rooms[roomid]
