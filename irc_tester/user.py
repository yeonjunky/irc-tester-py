"""IRC User (client) class for connecting to and communicating with an
IRC server.

Implements the client side of the IRC protocol as specified in
RFC 1459 and RFC 2810-2813.  Uses **only** the Python standard library
(``socket``, ``time``).
"""

import socket
import time

from irc_tester.message import IRCMessage


class User:
    """A single IRC client that can connect to a server and execute
    IRC commands (PASS, NICK, USER, JOIN, PRIVMSG, MODE, …).

    Parameters
    ----------
    nickname : str
        Desired IRC nickname.
    username : str
        Username sent in the USER command.
    password : str
        Server password sent in the PASS command.
    server : str
        Hostname or IP address of the IRC server.
    port : int
        TCP port of the IRC server.
    realname : str | None
        Real-name field for the USER command (defaults to *nickname*).
    """

    def __init__(
        self,
        nickname,
        username,
        password,
        server="127.0.0.1",
        port=6667,
        realname=None,
    ):
        self.nickname = nickname
        self.username = username
        self.password = password
        self.server = server
        self.port = port
        self.realname = realname or nickname
        self._socket = None
        self._buffer = ""
        self._connected = False

    # ================================================================== #
    #  Connection management                                               #
    # ================================================================== #

    def connect(self):
        """Establish a TCP connection to the IRC server."""
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(10)
        self._socket.connect((self.server, self.port))
        self._connected = True
        self._buffer = ""

    def disconnect(self):
        """Gracefully close the connection."""
        if self._socket:
            try:
                self.send_raw("QUIT :Leaving")
            except Exception:
                pass
            try:
                self._socket.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self._socket.close()
            except Exception:
                pass
        self._socket = None
        self._connected = False
        self._buffer = ""

    @property
    def connected(self):
        """``True`` if the socket is believed to be open."""
        return self._connected

    # ================================================================== #
    #  Low-level send / receive                                            #
    # ================================================================== #

    def send_raw(self, message):
        r"""Send a raw IRC line.  ``\r\n`` is appended automatically."""
        if not self._connected or not self._socket:
            raise ConnectionError("Not connected to server")
        data = (message + "\r\n").encode("utf-8")
        self._socket.sendall(data)

    # ------------------------------------------------------------------ #

    def receive(self, timeout=5):
        """Read available data and return a list of parsed
        :class:`~irc_tester.message.IRCMessage` objects.

        * Automatically responds to ``PING`` messages.
        * Returns as soon as at least one complete message is available,
          or when *timeout* seconds have elapsed.
        """
        messages = self._flush_buffer()
        if messages:
            return messages

        try:
            self._socket.settimeout(timeout)
            data = self._socket.recv(4096)
            if not data:
                self._connected = False
                return []
            self._buffer += data.decode("utf-8", errors="replace")
        except socket.timeout:
            return []
        except OSError:
            self._connected = False
            return []

        return self._flush_buffer()

    def _flush_buffer(self):
        """Extract and parse all complete ``\\r\\n``-terminated lines
        currently sitting in the internal buffer.
        """
        msgs = []
        while "\r\n" in self._buffer:
            line, self._buffer = self._buffer.split("\r\n", 1)
            line = line.strip()
            if not line:
                continue
            msg = IRCMessage.parse(line)
            if msg.command == "PING":
                token = msg.params[0] if msg.params else ""
                try:
                    self.send_raw(f"PONG :{token}")
                except Exception:
                    pass
            msgs.append(msg)
        return msgs

    # ------------------------------------------------------------------ #

    def receive_until(self, commands, timeout=10):
        """Keep receiving until a message with a matching command arrives.

        Parameters
        ----------
        commands : str | list[str]
            One or more IRC command names / numeric reply codes to wait for.
        timeout : float
            Maximum seconds to wait.

        Returns
        -------
        tuple[list[IRCMessage], IRCMessage | None]
            All messages received so far, and the first matching message
            (or ``None`` if the timeout expired).
        """
        if isinstance(commands, str):
            commands = {commands}
        else:
            commands = set(commands)

        all_msgs = []
        end_time = time.time() + timeout

        while True:
            remaining = end_time - time.time()
            if remaining <= 0:
                break
            batch = self.receive(timeout=min(remaining, 1.0))
            for msg in batch:
                all_msgs.append(msg)
                if msg.command in commands:
                    return all_msgs, msg

        return all_msgs, None

    def collect(self, timeout=2):
        """Collect **every** message arriving within *timeout* seconds.

        Unlike :meth:`receive`, this method keeps reading for the full
        duration instead of returning after the first batch.
        """
        all_msgs = []
        end_time = time.time() + timeout
        while True:
            remaining = end_time - time.time()
            if remaining <= 0:
                break
            batch = self.receive(timeout=min(remaining, 0.5))
            all_msgs.extend(batch)
        return all_msgs

    # ================================================================== #
    #  IRC registration                                                    #
    # ================================================================== #

    def authenticate(self):
        """Send ``PASS`` / ``NICK`` / ``USER`` and wait for ``001``
        (:rfc:`2812` RPL_WELCOME).

        Returns
        -------
        tuple[bool, list[IRCMessage]]
            Whether registration succeeded and all received messages.
        """
        self.send_raw(f"PASS {self.password}")
        self.send_raw(f"NICK {self.nickname}")
        self.send_raw(f"USER {self.username} 0 * :{self.realname}")
        all_msgs, welcome = self.receive_until("001", timeout=10)
        return welcome is not None, all_msgs

    # ================================================================== #
    #  IRC commands                                                        #
    # ================================================================== #

    def nick(self, new_nickname):
        """Send ``NICK`` and update the local nickname.

        Returns the **previous** nickname.
        """
        old = self.nickname
        self.send_raw(f"NICK {new_nickname}")
        self.nickname = new_nickname
        return old

    def join(self, channel, key=None):
        """Send ``JOIN`` for *channel*, optionally with *key*."""
        if key:
            self.send_raw(f"JOIN {channel} {key}")
        else:
            self.send_raw(f"JOIN {channel}")

    def part(self, channel, reason=None):
        """Send ``PART`` for *channel*."""
        if reason:
            self.send_raw(f"PART {channel} :{reason}")
        else:
            self.send_raw(f"PART {channel}")

    def privmsg(self, target, message):
        """Send ``PRIVMSG`` to *target* (nick or channel)."""
        self.send_raw(f"PRIVMSG {target} :{message}")

    def notice(self, target, message):
        """Send ``NOTICE`` to *target*."""
        self.send_raw(f"NOTICE {target} :{message}")

    def kick(self, channel, target, reason=None):
        """Send ``KICK`` to remove *target* from *channel*."""
        if reason:
            self.send_raw(f"KICK {channel} {target} :{reason}")
        else:
            self.send_raw(f"KICK {channel} {target}")

    def invite(self, nickname, channel):
        """Send ``INVITE`` for *nickname* to *channel*."""
        self.send_raw(f"INVITE {nickname} {channel}")

    def topic(self, channel, new_topic=None):
        """Send ``TOPIC`` to view or set the channel topic."""
        if new_topic is not None:
            self.send_raw(f"TOPIC {channel} :{new_topic}")
        else:
            self.send_raw(f"TOPIC {channel}")

    def mode(self, target, flags=None, params=None):
        """Send ``MODE`` to view or change modes on *target*."""
        if flags is None:
            self.send_raw(f"MODE {target}")
        elif params:
            self.send_raw(f"MODE {target} {flags} {params}")
        else:
            self.send_raw(f"MODE {target} {flags}")

    def quit(self, message=None):
        """Send ``QUIT``."""
        if message:
            self.send_raw(f"QUIT :{message}")
        else:
            self.send_raw("QUIT")

    def ping(self, token="test"):
        """Send ``PING`` with the given *token*."""
        self.send_raw(f"PING :{token}")
