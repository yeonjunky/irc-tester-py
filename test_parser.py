"""Quick smoke test for IRCMessage parser."""
from irc_tester.message import IRCMessage

# Test server numeric with trailing
m1 = IRCMessage.parse(":server 001 nick :Welcome to IRC")
assert m1.command == "001", f"got {m1.command}"
assert m1.params == ["nick", "Welcome to IRC"], f"got {m1.params}"

# Test PING
m2 = IRCMessage.parse("PING :token123")
assert m2.command == "PING"
assert m2.params == ["token123"]

# Test JOIN
m3 = IRCMessage.parse(":nick JOIN #channel")
assert m3.command == "JOIN"
assert m3.params == ["#channel"]

# Test PRIVMSG with prefix details
m4 = IRCMessage.parse(":alice!auser@ahost PRIVMSG #test :Hello world")
assert m4.nick == "alice"
assert m4.user == "auser"
assert m4.host == "ahost"
assert m4.command == "PRIVMSG"
assert m4.params == ["#test", "Hello world"]

# Test MODE
m5 = IRCMessage.parse(":op MODE #chan +o user")
assert m5.command == "MODE"
assert m5.params == ["#chan", "+o", "user"]

# Test KICK with reason
m6 = IRCMessage.parse(":op KICK #chan target :you are kicked")
assert m6.command == "KICK"
assert m6.params == ["#chan", "target", "you are kicked"]

# Test empty line
m7 = IRCMessage.parse("")
assert m7.command == ""

print("All IRCMessage parser tests passed!")
