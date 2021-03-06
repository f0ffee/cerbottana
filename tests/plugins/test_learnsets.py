def test_learnsets(mock_connection, veekun_database):
    conn, recv_queue, send_queue = mock_connection()

    recv_queue.add_user_join("room1", "user1")
    recv_queue.add_user_join("room1", "cerbottana", "*")
    send_queue.get_all()

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.learnset pikachu",
        ]
    )
    assert len(send_queue.get_all()) == 0

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.learnset abc",
        ]
    )
    assert len(send_queue.get_all()) == 0

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.learnset abc, red",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " not in next(iter(reply))

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.learnset pikachu, red",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " in next(iter(reply))

    recv_queue.add_messages(
        [
            f"|pm| user1| {conn.username}|.learnset pichu, red",
        ]
    )
    reply = send_queue.get_all()
    assert len(reply) == 1
    assert "/pminfobox " not in next(iter(reply))

    recv_queue.close()
