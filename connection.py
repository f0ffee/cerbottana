from __future__ import annotations

import asyncio
import re
from time import time
from typing import TYPE_CHECKING
from weakref import WeakValueDictionary

import websockets

import utils
from handlers import handlers
from models.room import Room
from models.user import User
from plugins import commands
from tasks import init_tasks
from typedefs import RoomId, UserId

if TYPE_CHECKING:
    from typedefs import TiersDict


class Connection:
    def __init__(
        self,
        *,
        url: str,
        username: str,
        password: str,
        avatar: str,
        statustext: str,
        rooms: list[str],
        main_room: str,
        command_character: str,
        administrators: list[str],
        domain: str,
        unittesting: bool = False,
    ) -> None:
        self.url = url
        self.username = username
        self.password = password
        self.avatar = avatar
        self.statustext = statustext
        self.rooms: dict[RoomId, Room] = {}  # roomid, Room
        for roomname in rooms:
            roomid = utils.to_room_id(roomname)
            self.rooms[roomid] = Room(self, roomid, autojoin=True)
        self.main_room = Room.get(self, main_room)
        self.command_character = command_character
        self.administrators = [utils.to_user_id(user) for user in administrators]
        self.domain = domain
        self.unittesting = unittesting
        self.public_roomids: set[str] = set()
        self.users: WeakValueDictionary[UserId, User] = WeakValueDictionary()
        self.init_tasks = init_tasks
        self.handlers = handlers
        self.commands = commands
        self.timestamp: float = 0
        self.lastmessage: float = 0
        self.loop: asyncio.AbstractEventLoop | None = None
        self.websocket: websockets.client.WebSocketClientProtocol | None = None
        self.connection_start: float | None = None
        self.tiers: list[TiersDict] = []

    def open_connection(self) -> None:
        try:
            asyncio.run(self._start_websocket())
        except asyncio.CancelledError:
            pass

    async def _start_websocket(self) -> None:
        self.loop = asyncio.get_running_loop()
        itasks: list[asyncio.Task[None]]
        for prio in range(5):
            itasks = []
            for func, skip_unittesting in [
                t[1:3] for t in self.init_tasks if t[0] == prio + 1
            ]:
                if self.unittesting and skip_unittesting:
                    continue
                itasks.append(asyncio.create_task(func(self)))
            for itask in itasks:
                await itask

        try:
            async with websockets.connect(
                self.url,
                # these two should be fixed by the next websockets release
                # https://github.com/aaugustin/websockets/commit/93ad88a9a8fe2ea8d96fb1d2a0f1625a3c5fee7c
                ping_interval=None,  # type: ignore
                max_size=None,  # type: ignore
            ) as websocket:
                self.websocket = websocket
                self.connection_start = time()
                async for message in websocket:
                    if isinstance(message, str):
                        print(f"<< {message}")
                        asyncio.create_task(self._parse_message(message))
        except (
            websockets.exceptions.WebSocketException,
            OSError,  # https://github.com/aaugustin/websockets/issues/593
        ):
            pass

    async def _parse_message(self, message: str) -> None:
        """Extracts a Room object from a raw message.

        Args:
            message (str): Raw message received from the websocket.
        """
        if not message:
            return

        init = False

        roomname = ""
        if message[0] == ">":
            roomname = message.split("\n")[0]
        roomid = utils.to_room_id(roomname)
        room = Room.get(self, roomid)

        # Try to set modchat if it's a public room and cerbottana has relevant auth
        if room.roombot and not room.is_private:
            await room.try_modchat()

        for msg in message.split("\n"):

            if language := re.match(r"This room's primary language is (.*)", msg):
                room.language = language.group(1)
                continue

            if not msg or msg[0] != "|":
                continue

            parts = msg.split("|")

            command = parts[1]

            if command == "init":
                init = True

            if init and command in ["tournament"]:
                return

            if command in self.handlers:
                tasks: list[asyncio.Task[None]] = []
                for func in self.handlers[command]:
                    tasks.append(asyncio.create_task(func(self, room, *parts[2:])))
                for task in tasks:
                    await task

    async def send(self, message: str) -> None:
        """Sends a raw unescaped message to the websocket.

        Args:
            message (str): String to send.
        """
        print(f">> {message}")
        now = time()
        if now - self.lastmessage < 0.1:
            await asyncio.sleep(0.1)
        self.lastmessage = now
        if self.websocket is not None:
            await self.websocket.send(message)
