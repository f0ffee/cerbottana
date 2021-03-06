def test_locations(mock_connection, veekun_database):
    conn, recv_queue, send_queue = mock_connection()

    recv_queue.add_user_join("room1", "user1")
    recv_queue.add_user_join("room1", "cerbottana", "*")
    send_queue.get_all()

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.locations abc",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " not in next(iter(reply))

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.locations pikachu",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " in next(iter(reply))

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.locations nidoranf",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " in next(iter(reply))

    recv_queue.close()


def test_encounters(mock_connection, veekun_database):
    conn, recv_queue, send_queue = mock_connection()

    recv_queue.add_user_join("room1", "user1")
    recv_queue.add_user_join("room1", "cerbottana", "*")
    send_queue.get_all()

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.encounters abc",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " not in next(iter(reply))

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.encounters kantoroute1",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " in next(iter(reply))

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.encounters sootopolis city",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " in next(iter(reply))

    recv_queue.close()
