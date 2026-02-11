"""Base test infrastructure shared by all IRC test suites."""

import time
import traceback

from irc_tester.user import User


# ====================================================================== #
#  TestResult                                                              #
# ====================================================================== #

class TestResult:
    """Outcome of a single test case.

    Attributes
    ----------
    name : str
        Short identifier for the test.
    passed : bool
        Whether the test passed.
    details : str
        Human-readable explanation.
    """

    def __init__(self, name, passed, details=""):
        self.name = name
        self.passed = passed
        self.details = details

    def __repr__(self):
        tag = "PASS" if self.passed else "FAIL"
        return f"[{tag}] {self.name}: {self.details}"


# ====================================================================== #
#  BaseSuite                                                               #
# ====================================================================== #

class BaseSuite:
    """Common helpers for every test suite.

    Sub-classes must override :meth:`get_tests` to return their list of
    ``(name, callable)`` pairs.
    """

    # ANSI escape helpers
    _GREEN = "\033[92m"
    _RED = "\033[91m"
    _RESET = "\033[0m"
    _BOLD = "\033[1m"

    def __init__(self, config):
        self.host = config["host"]
        self.port = config["port"]
        self.password = config["password"]
        self._channel_counter = 0
        self._user_counter = 0
        # Unique prefix to avoid collisions between runs / suites
        self._prefix = str(int(time.time()) % 100000)

    # ------------------------------------------------------------------ #
    #  Factory helpers                                                     #
    # ------------------------------------------------------------------ #

    def unique_channel(self):
        """Return a channel name that has never been used in this suite."""
        self._channel_counter += 1
        return f"#t{self._prefix}c{self._channel_counter}"

    def unique_nick(self, base="T"):
        """Return a unique nickname."""
        self._user_counter += 1
        return f"{base}{self._prefix}u{self._user_counter}"

    def create_user(self, nick_base="T"):
        """Create a :class:`User` with a unique nick (not yet connected)."""
        nick = self.unique_nick(nick_base)
        return User(
            nickname=nick,
            username=nick,
            password=self.password,
            server=self.host,
            port=self.port,
        )

    def setup_user(self, nick_base="T"):
        """Create a :class:`User`, connect, register, and drain the
        welcome / MOTD messages so the user is ready for testing.

        Raises
        ------
        RuntimeError
            If registration does not succeed (no ``001``).
        """
        user = self.create_user(nick_base)
        user.connect()
        ok, msgs = user.authenticate()
        if not ok:
            user.disconnect()
            raise RuntimeError(f"Registration failed for {user.nickname}")
        # Drain remaining MOTD / welcome noise
        user.collect(timeout=1)
        return user

    # ------------------------------------------------------------------ #
    #  Message-search helpers                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def find_message(messages, command=None, nick=None, params_contains=None):
        """Return the first :class:`IRCMessage` matching **all** given
        criteria, or ``None``.
        """
        for msg in messages:
            if command and msg.command != command:
                continue
            if nick and msg.nick.lower() != nick.lower():
                continue
            if params_contains is not None:
                joined = " ".join(msg.params).lower()
                if params_contains.lower() not in joined:
                    continue
            return msg
        return None

    @staticmethod
    def any_command(messages, commands):
        """Return the first message whose command is in *commands*."""
        cmds = set(commands) if not isinstance(commands, set) else commands
        for msg in messages:
            if msg.command in cmds:
                return msg
        return None

    # ------------------------------------------------------------------ #
    #  Test runner                                                         #
    # ------------------------------------------------------------------ #

    def run_test(self, name, func):
        """Execute *func*, catch exceptions, and return a
        :class:`TestResult`.
        """
        try:
            result = func()
            if isinstance(result, TestResult):
                return result
            return TestResult(name, bool(result), "OK" if result else "Failed")
        except Exception as exc:
            return TestResult(name, False, f"{exc}")

    def get_tests(self):
        """Return ``[(name, callable), …]``.  **Override in sub-classes.**"""
        return []

    def run_all(self):
        """Run every test and print coloured per-test results.

        Returns
        -------
        list[TestResult]
        """
        results = []
        for name, func in self.get_tests():
            result = self.run_test(name, func)
            if result.passed:
                sym = f"{self._GREEN}✓{self._RESET}"
            else:
                sym = f"{self._RED}✗{self._RESET}"
            detail = result.details if result.details else ""
            print(f"  {sym} {self._BOLD}{result.name}{self._RESET}  {detail}")
            results.append(result)
        return results
