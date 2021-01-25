from __future__ import annotations

import asyncio
import signal
import threading
from types import FrameType

from environs import Env

from connection import Connection
from server import initialize_server


def main() -> None:
    def shutdown(
        sig: signal.Signals, frame_type: FrameType  # pylint: disable=no-member
    ) -> None:
        if conn.websocket is not None and conn.loop is not None:
            for task in asyncio.all_tasks(conn.loop):
                task.cancel()
            coro = conn.websocket.close()
            asyncio.run_coroutine_threadsafe(coro, conn.loop)

    env = Env()
    env.read_env()

    server = initialize_server(env("FLASK_SECRET_KEY"))

    conn = Connection(
        url=(
            ("wss" if env("SHOWDOWN_PORT") == "443" else "ws")
            + "://"
            + env("SHOWDOWN_HOST")
            + ":"
            + env("SHOWDOWN_PORT")
            + "/showdown/websocket"
        ),
        username=env("USERNAME"),
        password=env("PASSWORD"),
        avatar=env("AVATAR", ""),
        statustext=env("STATUSTEXT", ""),
        rooms=env.list("ROOMS", []),
        main_room=env("MAIN_ROOM"),
        command_character=env("COMMAND_CHARACTER"),
        administrators=env.list("ADMINISTRATORS", []),
        domain=env("DOMAIN"),
    )

    signal.signal(signal.SIGINT, shutdown)

    threading.Thread(
        target=server.serve_forever,
        args=(
            env.int("PORT"),
            conn,
        ),
        daemon=True,
    ).start()
    threading.Thread(target=conn.open_connection).start()


if __name__ == "__main__":

    main()
