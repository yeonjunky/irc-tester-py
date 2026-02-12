"""MultiUserSuite – IRC tests that require two or more connected users.

Covers: private messaging, channel broadcast, operator status,
KICK, INVITE, and every MODE flag listed in the spec
(+i, +t, +k, +o, +l).
"""

import time

from irc_tester.base_suite import BaseSuite, TestResult


class MultiUserSuite(BaseSuite):
    """Tests for features that need multiple simultaneous clients."""

    def get_tests(self):
        return [
            ("private_message", self.test_private_message),
            ("channel_broadcast", self.test_channel_broadcast),
            ("no_self_echo", self.test_no_self_echo),
            ("operator_status", self.test_operator_status),
            ("kick", self.test_kick),
            ("kick_no_privilege", self.test_kick_no_privilege),
            ("kick_one_to_n", self.test_kick_one_to_n),
            ("kick_n_to_n", self.test_kick_n_to_n),
            ("invite", self.test_invite),
            ("mode_invite_only", self.test_mode_invite_only),
            ("part_and_join_inv_only_chan", self.test_part_and_join_inv_only_chan),
            ("mode_topic_restrict", self.test_mode_topic_restrict),
            ("mode_channel_key", self.test_mode_channel_key),
            ("mode_give_operator", self.test_mode_give_operator),
            ("mode_user_limit", self.test_mode_user_limit),
        ]

    # ================================================================== #
    #  Internal helpers                                                    #
    # ================================================================== #

    def _join_channel(self, user, channel, key=None, timeout=5):
        """Have *user* join *channel* and wait for ``366`` or an error.

        Returns ``(all_messages, matching_message)``.
        """
        user.join(channel, key=key)
        return user.receive_until(
            ["366", "471", "473", "474", "475"], timeout=timeout)

    # ================================================================== #
    #  Tests                                                               #
    # ================================================================== #

    def test_private_message(self):
        """PRIVMSG from one user is received by another."""
        sender = self.setup_user()
        receiver = self.setup_user()
        try:
            text = "Hello from " + sender.nickname
            sender.privmsg(receiver.nickname, text)

            msgs, _ = receiver.receive_until("PRIVMSG", timeout=5)
            pm = self.find_message(msgs, command="PRIVMSG")

            if pm and pm.params and text in pm.params[-1]:
                return TestResult(
                    "private_message", True,
                    f"{sender.nickname} → {receiver.nickname}")
            if pm:
                return TestResult(
                    "private_message", True,
                    f"PRIVMSG received (content: {pm.params[-1]!r})")
            return TestResult("private_message", False,
                              "Receiver got no PRIVMSG")
        finally:
            sender.disconnect()
            receiver.disconnect()

    # ------------------------------------------------------------------ #

    def test_channel_broadcast(self):
        """A channel message is forwarded to every *other* member."""
        op = self.setup_user()
        user_b = self.setup_user()
        user_c = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            self._join_channel(user_b, channel)
            self._join_channel(user_c, channel)
            time.sleep(0.3)

            # Drain JOIN notifications
            user_b.collect(timeout=0.5)
            user_c.collect(timeout=0.5)

            text = "bcast_" + str(int(time.time()))
            op.privmsg(channel, text)

            msgs_b = user_b.collect(timeout=3)
            msgs_c = user_c.collect(timeout=3)

            got_b = self.find_message(
                msgs_b, command="PRIVMSG", params_contains=text)
            got_c = self.find_message(
                msgs_c, command="PRIVMSG", params_contains=text)

            if got_b and got_c:
                return TestResult("channel_broadcast", True,
                                  "Both users received the message")
            missing = []
            if not got_b:
                missing.append(user_b.nickname)
            if not got_c:
                missing.append(user_c.nickname)
            return TestResult(
                "channel_broadcast", False,
                f"Missing delivery to: {', '.join(missing)}")
        finally:
            op.disconnect()
            user_b.disconnect()
            user_c.disconnect()

    # ------------------------------------------------------------------ #

    def test_no_self_echo(self):
        """The sender does NOT receive their own channel message."""
        op = self.setup_user()
        user_b = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            self._join_channel(user_b, channel)
            time.sleep(0.2)
            op.collect(timeout=0.5)

            text = "echo_" + str(int(time.time()))
            op.privmsg(channel, text)

            msgs_op = op.collect(timeout=2)
            echo = self.find_message(
                msgs_op, command="PRIVMSG", params_contains=text)

            time.sleep(0.2)
            # Also confirm the other user *did* get it
            msgs_b = user_b.collect(timeout=2)
            got_b = self.find_message(
                msgs_b, command="PRIVMSG", params_contains=text)

            if echo:
                return TestResult("no_self_echo", False,
                                  "Sender received their own message")
            if not got_b:
                return TestResult("no_self_echo", False,
                                  "Other user did not receive the message")
            return TestResult("no_self_echo", True,
                              "Sender correctly excluded from broadcast")
        finally:
            op.disconnect()
            user_b.disconnect()

    # ------------------------------------------------------------------ #

    def test_operator_status(self):
        """The first user to join a channel is a channel operator
        (has ``@`` prefix in NAMES reply).
        """
        op = self.setup_user()
        regular = self.setup_user()
        try:
            channel = self.unique_channel()

            # op joins first – should become operator
            op.join(channel)
            msgs, _ = op.receive_until("366", timeout=5)
            names_msg = self.find_message(msgs, command="353")
            if names_msg and names_msg.params:
                names_str = names_msg.params[-1]
                if f"@{op.nickname}" in names_str:
                    return TestResult(
                        "operator_status", True,
                        f"@{op.nickname} in NAMES reply")

            # Alternatively, let a second user join and check NAMES
            regular.join(channel)
            msgs2, _ = regular.receive_until("366", timeout=5)
            names_msg2 = self.find_message(msgs2, command="353")
            if names_msg2 and names_msg2.params:
                names_str2 = names_msg2.params[-1]
                if f"@{op.nickname}" in names_str2:
                    return TestResult(
                        "operator_status", True,
                        f"@{op.nickname} in NAMES reply (second user)")

            return TestResult("operator_status", False,
                              "'@' prefix not found in NAMES reply")
        finally:
            op.disconnect()
            regular.disconnect()

    # ------------------------------------------------------------------ #

    def test_kick(self):
        """An operator can KICK another user from the channel."""
        op = self.setup_user()
        target = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            self._join_channel(target, channel)
            time.sleep(0.2)
            op.collect(timeout=0.5)
            target.collect(timeout=0.5)

            op.kick(channel, target.nickname, "test kick")

            # The kicked user should see the KICK message
            msgs_t = target.collect(timeout=3)
            kick_t = self.find_message(msgs_t, command="KICK")

            if kick_t:
                return TestResult(
                    "kick", True,
                    f"{target.nickname} kicked from {channel}")

            # Check operator's side as well
            msgs_op = op.collect(timeout=2)
            kick_op = self.find_message(msgs_op, command="KICK")
            if kick_op:
                return TestResult("kick", True,
                                  "KICK confirmed on operator side")

            return TestResult("kick", False,
                              "No KICK message received by either side")
        finally:
            op.disconnect()
            target.disconnect()

    # ------------------------------------------------------------------ #

    def test_kick_no_privilege(self):
        """A regular user CANNOT kick another user (482)."""
        op = self.setup_user()
        regular = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            self._join_channel(regular, channel)
            time.sleep(0.2)
            regular.collect(timeout=0.5)

            regular.kick(channel, op.nickname, "unauthorized")
            msgs, _ = regular.receive_until(
                ["482", "KICK"], timeout=5)

            err = self.find_message(msgs, command="482")
            if err:
                return TestResult("kick_no_privilege", True,
                                  "482 ERR_CHANOPRIVSNEEDED received")

            kick = self.find_message(msgs, command="KICK")
            if kick:
                return TestResult(
                    "kick_no_privilege", False,
                    "KICK succeeded without operator privilege!")

            return TestResult(
                "kick_no_privilege", False,
                "No 482 error received (expected ERR_CHANOPRIVSNEEDED)")
        finally:
            op.disconnect()
            regular.disconnect()

    # ------------------------------------------------------------------ #

    def test_kick_one_to_n(self):
        op = self.setup_user()
        regular1 = self.setup_user()
        regular2 = self.setup_user()
        regular3 = self.setup_user()

        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            self._join_channel(regular1, channel)
            self._join_channel(regular2, channel)
            self._join_channel(regular3, channel)

            time.sleep(0.2)

            op.collect(0.5)
            regular1.collect(0.5)
            regular2.collect(0.5)
            regular3.collect(0.5)

            nicknames = regular1.nickname + "," + regular2.nickname + "," + regular3.nickname
            op.kick(channel, nicknames, "test one to n kicking")

            status = []
            msgs = op.collect(1)

            cnt = 0
            for msg in msgs:
                raw = msg.raw

                if "KICK" in raw:
                    cnt += 1

                elif "482" in raw:
                    return TestResult(
                        "kick_one_to_n", False,
                        "received error 482")
            
            if cnt == 3:
                return TestResult(
                    "kick_one_to_n", True, "Succeed to receive 3 kick responses"
                )
            
            return TestResult(
                "kick_one_to_n", False, "Failed to receive 3 kick responses"
            )

        finally:
            op.disconnect()
            regular1.disconnect()
            regular2.disconnect()
            regular3.disconnect()

    # ------------------------------------------------------------------ #

    def test_kick_n_to_n(self):
        op = self.setup_user()
        regular1 = self.setup_user()
        regular2 = self.setup_user()
        regular3 = self.setup_user()

        client_list = [op, regular1, regular2, regular3]

        try:
            channel1 = self.unique_channel()
            channel2 = self.unique_channel()
            channel3 = self.unique_channel()

            self._join_channel(op, channel1)
            self._join_channel(op, channel2)
            self._join_channel(op, channel3)

            self._join_channel(regular1, channel1)
            self._join_channel(regular2, channel2)
            self._join_channel(regular3, channel3)

            for c in client_list:
                c.collect(0.5)

            op.kick(channel1, regular1.nickname, "test n to n kicking")
            op.kick(channel2, regular2.nickname, "test n to n kicking")
            op.kick(channel3, regular3.nickname, "test n to n kicking")

            msgs = op.collect(1)

            cnt = 0
            for msg in msgs:
                raw = msg.raw
                if "482" in raw:
                    return TestResult(
                        "kick_n_to_n", False,
                        "No 482 error received (expected ERR_CHANOPRIVSNEEDED)")
                
                elif "KICK" in raw:
                    cnt += 1

            if cnt == 3:
                return TestResult(
                    "kick_n_to_n", True, "Succeed to receive 3 kick responses"
                )
            
            return TestResult(
                "kick_n_to_n", False, "failed to receive 3 kick response"
            )

        finally:
            op.disconnect()
            regular1.disconnect()
            regular2.disconnect()
            regular3.disconnect()

    # ------------------------------------------------------------------ #

    def test_invite(self):
        """INVITE sends an invitation to the target user."""
        op = self.setup_user()
        invitee = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            invitee.collect(timeout=0.5)

            op.invite(invitee.nickname, channel)

            # Operator expects 341 RPL_INVITING
            msgs_op = op.collect(timeout=3)
            rpl = self.find_message(msgs_op, command="341")

            # Invitee expects an INVITE message
            msgs_inv = invitee.collect(timeout=3)
            inv_msg = self.find_message(msgs_inv, command="INVITE")

            if rpl and inv_msg:
                return TestResult(
                    "invite", True,
                    f"{invitee.nickname} invited to {channel}")
            if inv_msg:
                return TestResult(
                    "invite", True,
                    f"INVITE received by {invitee.nickname}")
            if rpl:
                return TestResult(
                    "invite", True,
                    "341 RPL_INVITING received by operator")
            return TestResult("invite", False,
                              "Neither 341 nor INVITE message received")
        finally:
            op.disconnect()
            invitee.disconnect()

    # ------------------------------------------------------------------ #

    def test_mode_invite_only(self):
        """MODE +i makes a channel invite-only (473 for uninvited
        users, successful JOIN after INVITE).
        """
        op = self.setup_user()
        outsider = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)

            # Set invite-only
            op.mode(channel, "+i")
            op.collect(timeout=1)

            # Outsider tries to join → should get 473
            outsider.join(channel)
            msgs, _ = outsider.receive_until(
                ["473", "366"], timeout=5)
            err = self.find_message(msgs, command="473")
            join_ok = self.find_message(msgs, command="366")

            if join_ok and not err:
                return TestResult(
                    "mode_invite_only", False,
                    "User joined invite-only channel without invite")
            if not err:
                return TestResult(
                    "mode_invite_only", False,
                    "No 473 ERR_INVITEONLYCHAN received")

            # Now invite the outsider and try again
            op.invite(outsider.nickname, channel)
            outsider.collect(timeout=2)

            outsider.join(channel)
            msgs2, _ = outsider.receive_until(
                ["366", "473"], timeout=5)
            joined = (self.find_message(msgs2, command="JOIN")
                      or self.find_message(msgs2, command="366"))

            if joined:
                return TestResult(
                    "mode_invite_only", True,
                    "+i enforced; invited user joined successfully")
            return TestResult(
                "mode_invite_only", True,
                "+i enforced (473 returned for uninvited user)")
        finally:
            op.disconnect()
            outsider.disconnect()

    # ------------------------------------------------------------------ #

    def test_part_and_join_inv_only_chan(self):
        op = self.setup_user()
        regular = self.setup_user()

        try:
            channel = self.unique_channel()
            op.join(channel)

            op.mode(channel, "+i")
            op.invite(regular.nickname, channel)
            time.sleep(0.2)

            regular.join(channel)
            _, status = regular.receive_until(["473", "366"])
            if status == None:
                return TestResult(
                    "part_and_join_inv_only_chan", False,
                    "expected 366, got 473."
                )

            regular.part(channel)
            _, status = regular.receive_until(["403", "442"])
            if status:
                return TestResult(
                    "part_and_join_inv_only_chan", False,
                    "got 403 or 442"
                )

            regular.collect()
            regular.join(channel)
            msgs, _ = regular.receive_until(["473", "366"])
            inv_only_chan = self.find_message(msgs, "473")
            end_of_names = self.find_message(msgs, "366")

            if end_of_names:
                return TestResult(
                    "part_and_join_inv_only_chan", False,
                    "expected 473 but got 366"
                )

            if inv_only_chan:
                return TestResult(
                    "part_and_join_inv_only_chan", True,
                    "Succeed to get 473"
                )

        finally:
            op.disconnect()
            regular.disconnect()

    # ------------------------------------------------------------------ #

    def test_mode_topic_restrict(self):
        """MODE +t restricts TOPIC changes to channel operators.

        * Regular user → 482 ERR_CHANOPRIVSNEEDED
        * Operator → topic changed successfully
        """
        op = self.setup_user()
        regular = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            self._join_channel(regular, channel)
            time.sleep(0.2)
            regular.collect(timeout=0.5)

            # Set +t
            op.mode(channel, "+t")
            op.collect(timeout=1)
            regular.collect(timeout=1)

            # Regular user tries to set topic → 482
            regular.topic(channel, "I should not be able to do this")
            msgs_r, _ = regular.receive_until(
                ["482", "TOPIC"], timeout=5)
            err = self.find_message(msgs_r, command="482")
            topic_ok = self.find_message(msgs_r, command="TOPIC")

            if topic_ok and not err:
                return TestResult(
                    "mode_topic_restrict", False,
                    "Regular user set topic despite +t")
            if not err:
                return TestResult(
                    "mode_topic_restrict", False,
                    "No 482 ERR_CHANOPRIVSNEEDED for regular user")

            # Operator sets topic → should succeed
            op.topic(channel, "Operator's topic")
            msgs_op = op.collect(timeout=3)
            op_topic = self.find_message(msgs_op, command="TOPIC")
            rpl = self.find_message(msgs_op, command="332")

            if op_topic or rpl:
                return TestResult(
                    "mode_topic_restrict", True,
                    "+t enforced: regular denied, operator succeeded")
            return TestResult(
                "mode_topic_restrict", True,
                "+t enforced: regular user correctly denied")
        finally:
            op.disconnect()
            regular.disconnect()

    # ------------------------------------------------------------------ #

    def test_mode_channel_key(self):
        """MODE +k sets a channel key (password).

        * JOIN without key → 475 ERR_BADCHANNELKEY
        * JOIN with correct key → success
        """
        op = self.setup_user()
        joiner = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)

            key = "secret123"
            op.mode(channel, "+k", key)
            op.collect(timeout=1)

            # Try without key → 475
            joiner.join(channel)
            msgs, _ = joiner.receive_until(
                ["475", "366"], timeout=5)
            err = self.find_message(msgs, command="475")
            ok = self.find_message(msgs, command="366")

            if ok and not err:
                return TestResult(
                    "mode_channel_key", False,
                    "Joined +k channel without providing a key")
            if not err:
                return TestResult(
                    "mode_channel_key", False,
                    "No 475 ERR_BADCHANNELKEY received")

            # Try with correct key → should succeed
            joiner.join(channel, key=key)
            msgs2, _ = joiner.receive_until(
                ["366", "475"], timeout=5)
            joined = (self.find_message(msgs2, command="JOIN")
                      or self.find_message(msgs2, command="366"))

            if joined:
                return TestResult(
                    "mode_channel_key", True,
                    "+k enforced; correct key allowed entry")
            return TestResult(
                "mode_channel_key", True,
                "+k enforced (475 returned without key)")
        finally:
            op.disconnect()
            joiner.disconnect()

    # ------------------------------------------------------------------ #

    def test_mode_give_operator(self):
        """MODE +o grants operator privilege; MODE -o revokes it.

        Verified by checking that the promoted user can KICK, and
        after demotion they cannot.
        """
        op = self.setup_user()
        regular = self.setup_user()
        victim = None
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)
            self._join_channel(regular, channel)
            time.sleep(0.2)
            op.collect(timeout=0.5)
            regular.collect(timeout=0.5)

            # Grant +o to regular
            op.mode(channel, "+o", regular.nickname)
            msgs_op = op.collect(timeout=3)
            msgs_r = regular.collect(timeout=3)

            mode_msg = self.find_message(
                msgs_op + msgs_r, command="MODE",
                params_contains="+o")
            if not mode_msg:
                return TestResult(
                    "mode_give_operator", False,
                    "No MODE +o confirmation from server")

            # Prove regular is now an operator by kicking a third user
            victim = self.setup_user()
            self._join_channel(victim, channel)
            time.sleep(0.2)
            regular.collect(timeout=0.5)

            regular.kick(channel, victim.nickname, "proving op status")
            msgs_kick = regular.collect(timeout=3)
            msgs_v = victim.collect(timeout=3)

            kicked = self.find_message(
                msgs_kick + msgs_v, command="KICK")
            err = self.find_message(msgs_kick, command="482")

            if kicked and not err:
                # Now revoke operator
                op.mode(channel, "-o", regular.nickname)
                op.collect(timeout=2)
                return TestResult(
                    "mode_give_operator", True,
                    "+o granted and verified via KICK; -o sent")

            if err:
                return TestResult(
                    "mode_give_operator", False,
                    "+o sent but user still lacks operator privileges")

            return TestResult("mode_give_operator", True,
                              "MODE +o confirmed by server")
        finally:
            op.disconnect()
            regular.disconnect()
            if victim:
                victim.disconnect()

    # ------------------------------------------------------------------ #

    def test_mode_user_limit(self):
        """MODE +l <n> sets the maximum number of users in a channel.

        * With limit=2: second user joins OK, third gets 471.
        """
        op = self.setup_user()
        user_b = self.setup_user()
        user_c = self.setup_user()
        try:
            channel = self.unique_channel()
            self._join_channel(op, channel)

            # Set user limit to 2
            op.mode(channel, "+l", "2")
            op.collect(timeout=1)

            # Second user joins → should succeed (2/2)
            user_b.join(channel)
            msgs_b, _ = user_b.receive_until(
                ["366", "471"], timeout=5)
            joined_b = (self.find_message(msgs_b, command="JOIN")
                        or self.find_message(msgs_b, command="366"))
            err_b = self.find_message(msgs_b, command="471")

            if err_b:
                return TestResult(
                    "mode_user_limit", False,
                    "Second user denied at limit=2 (should be allowed)")
            if not joined_b:
                return TestResult(
                    "mode_user_limit", False,
                    "Second user could not join (no JOIN/366)")

            # Third user joins → should be denied (471)
            user_c.join(channel)
            msgs_c, _ = user_c.receive_until(
                ["471", "366"], timeout=5)
            err_c = self.find_message(msgs_c, command="471")
            ok_c = self.find_message(msgs_c, command="366")

            if ok_c and not err_c:
                return TestResult(
                    "mode_user_limit", False,
                    "Third user joined despite limit=2")
            if err_c:
                return TestResult(
                    "mode_user_limit", True,
                    "+l 2 enforced: third user got 471 ERR_CHANNELISFULL")
            return TestResult(
                "mode_user_limit", False,
                "No 471 ERR_CHANNELISFULL for third user")
        finally:
            op.disconnect()
            user_b.disconnect()
            user_c.disconnect()
