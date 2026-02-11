"""IRC message parser following RFC 1459 / RFC 2812.

An IRC message has the general form:
    [:prefix] command [params ...] [:trailing]

Where:
    - prefix   is optional and starts with ':'
    - command  is either a word (PRIVMSG, JOIN …) or a three-digit numeric
    - params   are space-separated tokens
    - trailing is the final parameter, prefixed with ':' and may contain spaces
"""


class IRCMessage:
    """Represents a single parsed IRC protocol message."""

    __slots__ = ("raw", "prefix", "nick", "user", "host", "command", "params")

    def __init__(self, raw="", prefix="", command="", params=None):
        self.raw = raw
        self.prefix = prefix
        self.command = command
        self.params = params if params is not None else []
        self.nick = ""
        self.user = ""
        self.host = ""
        if prefix:
            self._parse_prefix(prefix)

    # ------------------------------------------------------------------ #
    #  Prefix helpers                                                      #
    # ------------------------------------------------------------------ #

    def _parse_prefix(self, prefix):
        """Extract nick, user, host from *nick!user@host* format."""
        if "!" in prefix:
            self.nick, rest = prefix.split("!", 1)
            if "@" in rest:
                self.user, self.host = rest.split("@", 1)
            else:
                self.user = rest
        elif "@" in prefix:
            self.nick, self.host = prefix.split("@", 1)
        else:
            self.nick = prefix

    # ------------------------------------------------------------------ #
    #  Parsing                                                             #
    # ------------------------------------------------------------------ #

    @classmethod
    def parse(cls, line):
        """Parse a raw IRC message line into an :class:`IRCMessage`.

        Parameters
        ----------
        line : str
            A single IRC protocol line **without** the trailing ``\\r\\n``.

        Returns
        -------
        IRCMessage
        """
        if not line:
            return cls()

        raw = line
        prefix = ""
        idx = 0

        # Optional prefix (starts with ':')
        if line[0] == ":":
            space = line.find(" ")
            if space == -1:
                return cls(raw, prefix=line[1:])
            prefix = line[1:space]
            idx = space + 1

        # Trailing parameter (after first ' :')
        trailing_idx = line.find(" :", idx)
        if trailing_idx != -1:
            middle = line[idx:trailing_idx]
            trailing = line[trailing_idx + 2:]
            params = middle.split()
            params.append(trailing)
        else:
            params = line[idx:].split()

        command = params.pop(0).upper() if params else ""
        return cls(raw, prefix, command, params)

    # ------------------------------------------------------------------ #
    #  Representation                                                      #
    # ------------------------------------------------------------------ #

    def __repr__(self):
        return (
            f"IRCMessage(prefix={self.prefix!r}, cmd={self.command!r}, "
            f"params={self.params!r})"
        )

    def __str__(self):
        return self.raw
