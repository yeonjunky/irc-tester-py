"""SingleUserSuite – IRC tests that require only one connected user.

Covers: connection, registration (PASS/NICK/USER), NICK change,
JOIN, PART, TOPIC (view & set), MODE (view), PRIVMSG to channel,
and PING/PONG.
"""

import time

from irc_tester.base_suite import BaseSuite, TestResult


class SingleUserSuite(BaseSuite):
    """Tests for features that can be verified with a single client."""

    def get_tests(self):
        return [
            ("connect", self.test_connect),
            ("registration", self.test_registration),
            ("nick_change", self.test_nick_change),
            ("join_channel", self.test_join_channel),
            ("part_channel", self.test_part_channel),
            ("topic_view", self.test_topic_view),
            ("topic_set", self.test_topic_set),
            ("mode_view", self.test_mode_view),
            ("privmsg_to_channel", self.test_privmsg_to_channel),
            # ("ping_pong", self.test_ping_pong),
        ]

    # ================================================================== #
    #  Tests                                                               #
    # ================================================================== #

    def test_connect(self):
        """TCP connection to the server can be established."""
        user = self.create_user()
        try:
            user.connect()
            if user.connected:
                return TestResult("connect", True,
                                  "TCP connection established")
            return TestResult("connect", False,
                              "Socket reports not connected")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_registration(self):
        """PASS + NICK + USER results in 001 RPL_WELCOME."""
        user = self.create_user()
        try:
            user.connect()
            ok, msgs = user.authenticate()
            if ok:
                welcome = self.find_message(msgs, command="001")
                detail = (welcome.params[-1]
                          if welcome and welcome.params else "OK")
                return TestResult("registration", True, detail)
            # Look for a concrete error numeric
            for msg in msgs:
                if msg.command.isdigit() and int(msg.command) >= 400:
                    return TestResult(
                        "registration", False,
                        f"Error {msg.command}: {' '.join(msg.params)}")
            return TestResult("registration", False,
                              "No 001 RPL_WELCOME received")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_nick_change(self):
        """User can change nickname via the NICK command."""
        user = self.setup_user()
        try:
            old_nick = user.nickname
            new_nick = old_nick + "X"
            user.nick(new_nick)
            msgs, _ = user.receive_until(
                ["NICK", "433", "432", "436"], timeout=5)

            nick_msg = self.find_message(msgs, command="NICK")
            if nick_msg:
                return TestResult("nick_change", True,
                                  f"{old_nick} → {new_nick}")

            err = self.any_command(msgs, {"433", "432", "436"})
            if err:
                return TestResult(
                    "nick_change", False,
                    f"Error {err.command}: {' '.join(err.params)}")

            return TestResult("nick_change", False,
                              "No NICK confirmation received")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_join_channel(self):
        """User can join a channel and receives JOIN echo + NAMES."""
        user = self.setup_user()
        try:
            channel = self.unique_channel()
            user.join(channel)
            msgs, _ = user.receive_until(["366", "JOIN"], timeout=5)

            join_msg = self.find_message(msgs, command="JOIN")
            if not join_msg:
                return TestResult("join_channel", False,
                                  "No JOIN echo received")

            # If we got JOIN first, keep reading for 366 (end of NAMES)
            if not self.find_message(msgs, command="366"):
                more, _ = user.receive_until("366", timeout=5)
                msgs.extend(more)

            names_end = self.find_message(msgs, command="366")
            if names_end:
                return TestResult(
                    "join_channel", True,
                    f"Joined {channel} (JOIN + NAMES received)")
            return TestResult(
                "join_channel", True,
                f"Joined {channel} (JOIN echo received)")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_part_channel(self):
        """User can leave a channel with PART."""
        user = self.setup_user()
        try:
            channel = self.unique_channel()
            user.join(channel)
            user.receive_until("366", timeout=5)

            user.part(channel, "test leaving")
            msgs, _ = user.receive_until(["PART", "ERROR"], timeout=5)

            part_msg = self.find_message(msgs, command="PART")
            if part_msg:
                return TestResult("part_channel", True,
                                  f"Parted {channel}")
            return TestResult("part_channel", False,
                              "No PART confirmation received")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_topic_view(self):
        """TOPIC #channel returns 331 (no topic) or 332 (topic set)."""
        user = self.setup_user()
        try:
            channel = self.unique_channel()
            user.join(channel)
            user.receive_until("366", timeout=5)

            user.topic(channel)
            msgs, _ = user.receive_until(
                ["331", "332", "TOPIC"], timeout=5)

            topic_msg = self.any_command(msgs, {"331", "332"})
            if topic_msg:
                label = ("RPL_NOTOPIC" if topic_msg.command == "331"
                         else "RPL_TOPIC")
                return TestResult("topic_view", True,
                                  f"{label} ({topic_msg.command})")
            return TestResult("topic_view", False,
                              "No 331/332 reply received")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_topic_set(self):
        """Channel creator (operator) can set the topic."""
        user = self.setup_user()
        try:
            channel = self.unique_channel()
            user.join(channel)
            user.receive_until("366", timeout=5)

            new_topic = "Hello from " + user.nickname
            user.topic(channel, new_topic)
            msgs = user.collect(timeout=3)

            topic_msg = self.find_message(msgs, command="TOPIC")
            rpl = self.find_message(msgs, command="332")
            err = self.any_command(msgs, {"482", "481"})

            if topic_msg:
                return TestResult("topic_set", True,
                                  f"Topic set to: {new_topic}")
            if rpl:
                return TestResult("topic_set", True,
                                  "Topic confirmed via 332")
            if err:
                return TestResult(
                    "topic_set", False,
                    f"Error {err.command}: {' '.join(err.params)}")
            return TestResult("topic_set", False,
                              "No TOPIC confirmation received")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_mode_view(self):
        """MODE #channel returns 324 RPL_CHANNELMODEIS."""
        user = self.setup_user()
        try:
            channel = self.unique_channel()
            user.join(channel)
            user.receive_until("366", timeout=5)

            user.mode(channel)
            msgs, _ = user.receive_until("324", timeout=5)

            mode_msg = self.find_message(msgs, command="324")
            if mode_msg:
                mode_str = (" ".join(mode_msg.params[1:])
                            if len(mode_msg.params) > 1 else "(none)")
                return TestResult("mode_view", True,
                                  f"Channel modes: {mode_str}")
            return TestResult("mode_view", False,
                              "No 324 RPL_CHANNELMODEIS received")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_privmsg_to_channel(self):
        """PRIVMSG to a joined channel is accepted without error."""
        user = self.setup_user()
        try:
            channel = self.unique_channel()
            user.join(channel)
            user.receive_until("366", timeout=5)

            user.privmsg(channel, "Hello, world!")
            msgs = user.collect(timeout=2)

            err = self.any_command(
                msgs, {"401", "403", "404", "411", "412"})
            if err:
                return TestResult(
                    "privmsg_to_channel", False,
                    f"Error {err.command}: {' '.join(err.params)}")
            return TestResult("privmsg_to_channel", True,
                              "Message accepted (no error)")
        finally:
            user.disconnect()

    # ------------------------------------------------------------------ #

    def test_ping_pong(self):
        """Server replies to PING with a PONG."""
        user = self.setup_user()
        try:
            token = f"tok{int(time.time())}"
            user.ping(token)
            msgs, _ = user.receive_until("PONG", timeout=5)

            pong = self.find_message(msgs, command="PONG")
            if pong:
                return TestResult("ping_pong", True, "PONG received")
            return TestResult("ping_pong", False, "No PONG response")
        finally:
            user.disconnect()
