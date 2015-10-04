#!/usr/bin/python
# encoding = UTF-8

"""
cat.py channel management bot
make sure your conf.py is formatted like so:
	nick = "cat"
	dbfile = "cat.db"
	server = ("irc.example.net", 6667)
	high_op = "q" #usually q or o, check 005 PREFIX numeric
	username = "CatServ"
	password = "enterpw"
	services_command = "NS ID %s" % password
	services_expect = "^:[^ ]+ 376"
"""

import conf
import difflib
import os
import re
import signal
import socket
import sys
from time import time, sleep
uptime = time()

def icompare (one, two):
	return one.lower() == two.lower()

def split_sender (sender):
	return re.match(':(.*)!(.*)@(.*)', sender).groups()

def log_debug (line):
	print "[%f] %s" % (time(), line)

def glob_match (haystack, needle):
	return re.search(("^"+re.escape(haystack)+"$").replace(r'\?', '.').replace(r'\*', '.*?'), needle)

with open("/tmp/cat.pid", "w") as fh: fh.write("%d\n" % os.getpid())

class Moderator ():
	def __init__ (self):
		pass

	def handle_line (self, line):
		pass

class Channel ():

	def __init__ (self, name, prefix = '.', limit = None, topic = None):
		self.name = name.lower()
		self.prefix = prefix
		self.ops = {}
		self.users = set()
		self.registered = None
		self.topic = topic
		self.modes = set()
		self.lists = []
		self.lastmsgs = []
		self.lasttopics = (time(), 0)
		self.uniq = {}
		self.moderator = Moderator()
		self.protect = False
		self.limit = limit
		self.currentlimit = 0

		self.roles = {} # {role name, flags}
		self.masks = {} # {hostmask, role}
		self.akicks = {} # {hostmask, role}

	def set_topic (self, topic):
		self.topic = topic

	def prime_ops (self, op_modes):
		for mode in op_modes:
			self.ops[mode] = set()

	def is_banned (self, hostmask):
		hostmask = hostmask.lower().lstrip(":").split("!", 1)
		hostmask = [hostmask[0]] + hostmask[1].split("@", 1)

		for chanmask, reason in self.akicks.iteritems():
			chanmask = chanmask.split("!", 1)
			chanmask = [chanmask[0]] + chanmask[1].split("@", 1)
			if len(chanmask[0]) and not glob_match(chanmask[0], hostmask[0]):
				continue
			if len(chanmask[1]) and not glob_match(chanmask[1], hostmask[1]):
				continue
			if len(chanmask[2]) and not glob_match(chanmask[2], hostmask[2]):
				continue
			return reason

		return False

	def has_flag (self, hostmask, flag):
		hostmask = hostmask.lower().lstrip(":").split("!", 1)
		hostmask = [hostmask[0]] + hostmask[1].split("@", 1)

		if not self.registered and hostmask[0] in self.ops[conf.high_op] and flag not in "i":
			return True

		for chanmask, role in self.masks.iteritems():
			chanmask = chanmask.split("!", 1)
			chanmask = [chanmask[0]] + chanmask[1].split("@", 1)
			if len(chanmask[0]) and not glob_match(chanmask[0], hostmask[0]):
				continue
			if len(chanmask[1]) and not glob_match(chanmask[1], hostmask[1]):
				continue
			if len(chanmask[2]) and not glob_match(chanmask[2], hostmask[2]):
				continue
			if flag in self.roles[role].split("+", 1)[0].split("*")[0]:
				return True

		return False

	def can_op (self, hostmask, opmode):
		hostmask = hostmask.lower().lstrip(":").split("!", 1)
		hostmask = [hostmask[0]] + hostmask[1].split("@", 1)

		for chanmask, role in self.masks.iteritems():
			chanmask = chanmask.split("!", 1)
			chanmask = [chanmask[0]] + chanmask[1].split("@", 1)
			if len(chanmask[0]) and not glob_match(chanmask[0], hostmask[0]):
				continue
			if len(chanmask[1]) and not glob_match(chanmask[1], hostmask[1]):
				continue
			if len(chanmask[2]) and not glob_match(chanmask[2], hostmask[2]):
				continue
			if "+" not in self.roles[role]:
				pass
			elif opmode in self.roles[role].split("+", 1)[1]:
				return True
			if "*" not in self.roles[role]:
				pass
			elif opmode in self.roles[role].split("*", 1)[1]:
				return True

	def add_role (self, role, flags):
		self.roles[role.lower()] = flags

		return self.roles[role.lower()]

	def del_role (self, role):
		if role not in self.roles:
			return False

		prune = []
		for mask, maskrole in self.masks.iteritems():
			if maskrole == role: prune.append(mask)
		for mask in prune:
			del self.masks[mask]
		del prune

		del self.roles[role]

		return True

	def del_flags (self, role, flags):
		if role not in self.roles:
			return False

		for flag in flags:
			self.roles[role] = flags[:self.roles[role].find(flag)] + flags[self.roles[role].find(flag)+1:]

		return self.roles[role]

	def add_mask (self, hostmask, role):
		if role.lower() not in self.roles:
			return False

		if "!" not in hostmask and "@" in hostmask:
			hostmask = "!" + hostmask
		elif "!" in hostmask and "@" not in hostmask:
			hostmask += "@"
		elif "!" not in hostmask and "@" not in hostmask:
			hostmask += "!@"

		self.masks[hostmask.lower()] = role.lower()

		return hostmask.lower()

	def del_mask (self, hostmask):
		if hostmask not in self.masks:
			return False

		del self.masks[hostmask.lower()]
		return True

	def add_akick (self, hostmask, reason):
		if "!" not in hostmask and "@" in hostmask:
			hostmask = "!" + hostmask
		elif "!" in hostmask and "@" not in hostmask:
			hostmask += "@"
		elif "!" not in hostmask and "@" not in hostmask:
			hostmask += "!@"

		self.akicks[hostmask.lower()] = reason
		return hostmask.lower()

	def del_akick (self, hostmask):
		if hostmask not in self.akicks:
			return False

		del self.akicks[hostmask.lower()]
		return True

	def automodes (self, hostmask):
		hostmask = hostmask.lower().split("!", 1)
		hostmask = [hostmask[0]] + hostmask[1].split("@", 1)

		modes = ""

		for chanmask, role in self.masks.iteritems():
			if "*" not in self.roles[role]:
				continue
			chanmask = chanmask.split("!", 1)
			chanmask = [chanmask[0]] + chanmask[1].split("@", 1)
			if len(chanmask[0]) and not glob_match(chanmask[0], hostmask[0]):
				continue
			if len(chanmask[1]) and not glob_match(chanmask[1], hostmask[1]):
				continue
			if len(chanmask[2]) and not glob_match(chanmask[2], hostmask[2]):
				continue
			modes += self.roles[role].split("*")[1].split("+")[0]
		return modes

class Bot ():
	def __init__ (self):
		self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.nick = conf.nick
		self.dbfile = conf.dbfile
		self.channels = {}
		self.buffer = ""
		self.op_modes = {}
		self.list_modes = ""
		self.password_modes = ""
		self.param_modes = ""
		self.ratelimit = {}
		self.sendlines_h = []
		self.sendlines_l = []
		self.sendmodes = {}
		self.sendlimits = {}
		self.stackmodes = {}
		self.lastsent = time()

		self.load_db(self.dbfile)
		self.sock.connect(conf.server)
		self.sock.setblocking(0)
		self.send_line(
		 "USER %s * * :%s\r\n"
		 "NICK %s"
		 % (self.nick, self.nick, self.nick), prio=True)

	def send_line (self, line, prio = False):
		if prio:
			self.sendlines_h.append(line)
		else:
			self.sendlines_l.append(line)

	def time_mode (self, channel, mode, params, seconds):
		self.send_line("MODE %s +%s %s" % (channel, mode, params))
		self.sendmodes[(channel, mode, params.lower())] = time()+seconds

	def time_limit (self, channel, limit, seconds):
		self.sendlimits[channel] = (time()+seconds, limit)

	def mode_stack (self, channel, modes, nick):
		if not channel in self.stackmodes:
			self.stackmodes[channel] = [time()+5]
		for mode in modes:
			self.stackmodes[channel].append((mode, nick.lower()))

	def load_db (self, file):
		try:
			log_debug("Opening database <%s> for reading" % file)
			timer = time()
			current = None

			for line in open(file):
				arg = line.split()

				if arg[0][0] in "#&" and len(arg) >= 2:
					self.channels[arg[0].lower()] = Channel(
					 name = arg[0],
					 prefix = arg[1],
					 limit = (int(arg[2]), int(arg[3])) if arg[2] != "0" else None,
					 topic = None if len(arg) == 5 and arg[4] == ":" else " ".join(arg[4:])
					)
					current = arg[0].lower()
				elif current is None:
					log_debug("Role/mask comes before first channel definition. Not going to parse anymore.")
					break
				elif arg[0] == "R" and len(arg) == 3:
					self.channels[current].add_role(arg[1], arg[2])
				elif arg[0] == "M" and len(arg) == 3:
					self.channels[current].add_mask(arg[1], arg[2])
				elif arg[0] == "K" and len(arg) >= 3:
					self.channels[current].add_akick(arg[1], " ".join(arg[2:]))

			log_debug("Database <%s> parsed in %f seconds" %
			 (file, time() - timer))

		except IOError:
			log_debug("Database <%s> cannot be opened for writing" % file)

	def save_db (self, file):
		try:
			log_debug("Opening database <%s> for writing" % file)
			timer = time()

			with open(file, "w") as fh:
				for channel in self.channels.itervalues():
					fh.write("%s %c %d %d %s\n" % (
					 channel.name,
					 channel.prefix,
					 channel.limit[0] if channel.limit else 0,
					 channel.limit[1] if channel.limit else 0,
					 channel.topic if channel.topic else ":"
					))

					for role, flags in channel.roles.iteritems():
						fh.write("R %s %s\n" % (role, flags))

					for mask, role in channel.masks.iteritems():
						fh.write("M %s %s\n" % (mask, role))

					for mask, reason in channel.akicks.iteritems():
						fh.write("K %s %s\n" % (mask, reason))

			log_debug("Database <%s> written in %f seconds" %
			 (file, time() - timer))

		except IOError:
			log_debug("Database <%s> cannot be opened for writing" % file)

	def handle_hup (self, sig, frame):
		log_debug("Caught hup")
		self.save_db(self.dbfile)

	def loop (self):
		now = time()
		try:
			self.buffer += self.sock.recv(512)
			if not "\r\n" in self.buffer:
				return
			data = self.buffer.split("\r\n")
			self.buffer = data.pop()
			if self.sendlines_h:
				self.sock.send("%s\r\n" % self.sendlines_h.pop(0))
				self.lastsent = now
		except socket.error:
			for (channel, mode, param), when in self.sendmodes.items():
				if now < when: continue
				self.send_line("MODE %s -%s %s" % (channel, mode, param),
				 True)
				del self.sendmodes[(channel, mode, param)]
			for channel, (when, limit) in self.sendlimits.items():
				if now < when: continue
				if limit != self.channels[channel].currentlimit:
					self.send_line("MODE %s +l %d" % (channel, limit), True)
				del self.sendlimits[channel]
			for channel, modes in self.stackmodes.items():
				if now < modes[0] and len(modes) < 5: continue
				modes.pop(0)
				for (mode, nick) in modes[:]:
					if nick not in self.channels[channel].users:
						modes.remove((mode, nick))
				if not modes: continue
				while modes:
					self.send_line("MODE %s +%s %s" %
					 (channel, "".join(mode[0] for mode in modes[:4]),
					 " ".join(mode[1] for mode in modes[:4])), True)
					for i in xrange(len(modes[:4])):
						modes.pop(0)
				del self.stackmodes[channel]
				
#			if self.lastsent - now < 1:
#				print "jews"
			if self.sendlines_h:
				self.sock.send("%s\r\n" % self.sendlines_h.pop(0))
				self.lastsent = now
			elif self.sendlines_l:
				self.sock.send("%s\r\n" % self.sendlines_l.pop(0))
				self.lastsent = now

			sleep(.1)
			return

		if not data:
			exit()

		for line in data:
			line = line.split(" ")
			irccmd = line[1].upper()

			if line[0].upper() == "ERROR":
				self.save_db(self.dbfile)
				os._exit(0)

			elif line[0].upper() == "PING":
				self.send_line("PONG %s" % line[1])

			elif len(line) > 1:
				# RPL_WELCOME
				if irccmd == "001":
					log_debug("Logging in to services")
					self.send_line("%s\r\n"
					 "MODE %s -iw+B" % (conf.services_command, line[2]), prio=True)

				elif re.search(conf.services_expect, " ".join(line)):
					joinbuf = ""
					for channel in self.channels:
						if len(joinbuf) + len(channel) > 500:
							log_debug("Joining %s" % joinbuf)
							self.send_line("JOIN :%s" % joinbuf, prio=True)
							joinbuf = ""
						joinbuf += channel + ","
					log_debug("Joining %s" % joinbuf)
					self.send_line("JOIN :%s" % joinbuf, prio=True)

				# RPL_ISUPPORT
				elif irccmd == "005":
					for pair in line:
						if not "=" in pair:
							continue

						(param, value) = pair.split("=", 1)

						if param == "PREFIX":
							length = len(value[1:value.find(")")])

							for i in xrange(length):
								self.op_modes[value[i+1]] = value[i+length+2]

							continue

						if param == "MAXLIST":
							self.maxlist = int(value.split(":")[1])

						if param == "CHANMODES":
							self.list_modes, self.password_modes, self.param_modes, _ = value.split(",")

				# RPL_CHANNELMODEIS
				elif irccmd in ("324", "MODE"):
					params = []

					if line[1] == "324":
						channel = line[3].lower()
						modes = line[4]
						if len(line) > 5:
							params = line[5:]
					else:
						channel = line[2].lower()
						modes = line[3]
						if len(line) > 4:
							params = line[4:]

					if channel not in self.channels:
						continue

					add = True
					param = 0
					for mode in modes:
						if mode == "+":
							add = True
							continue

						if mode == "-":
							add = False
							continue

						if mode == "r":
							if param >= len(params): continue
							if icompare(params[param], conf.username) and add:
								self.send_line("MODE %s +%c %s" % (channel, conf.high_op, self.nick), prio=True)
								self.channels[channel].registered = True

						elif mode == "l" and add:
							if param >= len(params): continue
							self.channels[channel].currentlimit = int(params[param])

						elif mode == "l" and not add:
							self.channels[channel].currentlimit = 0

						if mode in self.op_modes:
							if param >= len(params): continue

							if add and params[param] not in self.channels[channel].ops[mode]:
								self.channels[channel].ops[mode].add(params[param])

							elif params[param] in self.channels[channel].ops[mode]:
								self.channels[channel].ops[mode].remove(params[param])

							param += 1
							continue

						if mode in self.list_modes:
							if add:
								self.channels[channel].lists.append((mode, params[param]))
							elif (mode, params[param]) in self.channels[channel].lists:
								self.channels[channel].lists.remove((mode, params[param]))

							if (add and
							 len(self.channels[channel].lists) == self.maxlist - 1 and
							 self.nick in self.channels[channel].ops[conf.high_op]):
								self.send_line("MODE %s -%c %s" % (channel, mode, self.channels[channel].lists.pop(0)[1]), prio=True)

							if not add and (channel, mode, params[param].lower()) in self.sendmodes:
								del self.sendmodes[(channel, mode, params[param].lower())]

							param += 1
							continue

						if mode in self.password_modes or (mode in self.param_modes and add):
							param += 1

						if add:
							self.channels[channel].modes.add(mode)
						else:
							if mode in self.sendmodes:
								del self.sendmodes[(channel, mode, "")]
							self.channels[channel].modes.discard(mode)

					if self.channels[channel].registered is None:
						self.channels[channel].registered = False

					if not self.channels[channel].registered and not self.channels[channel].ops[conf.high_op]:
						self.send_line("PART %s :Opless channel" % channel)

				# RPL_INVITELIST, RPL_EXCEPTLIST, RPL_BANLIST
				elif irccmd in ("346", "348", "367"):
					channel = line[3].lower()
					mask = line[4].lower()
					mode = {"346": "I", "348": "e", "367": "b"}
					
					self.channels[channel].lists.append((mode[line[1]], mask))

				# RPL_WHOREPLY
				elif irccmd == "352":
					channel = line[3].lower()

					if channel not in self.channels:
						continue

					nick = line[7].lower()
					user = line[4].lower()
					host = line[5].lower()

					ban = self.channels[channel].is_banned("%s!%s@%s" %
					 (nick, user, host))
					if ban:
						self.time_mode(channel, "b", "%s!%s@%s" %
						 (nick, user, host), 60)
						self.send_line("KICK %s %s :%s" % (channel, nick, ban))
						continue

					automode = self.channels[channel].automodes("%s!%s@%s" %
					 (nick, user, host))

					if automode and self.nick in self.channels[channel].ops[conf.high_op]:
						self.mode_stack(channel, automode, nick)

					for mode, prefix in self.op_modes.iteritems():
						if prefix in line[8]:
							self.channels[channel].ops[mode].add(nick)

					self.channels[channel].users.add(nick)
					if self.channels[channel].limit:
						self.time_limit(channel,
						 len(self.channels[channel].users) +
						  self.channels[channel].limit[0],
						 self.channels[channel].limit[1])

				# RPL_ENDOFNAMES
				#elif irccmd == "366":
				#	pass

				# ERR_NICKNAMEINUSE
				elif irccmd == "433":
					self.nick += "_"
					self.send_line("NICK %s" % self.nick, prio=True)

				# ERR_BANLISTFULL
				#elif irccmd == "478":
				#	self.send_line("MODE %s +b" % line[3], prio=True)

				elif irccmd == "NOTICE":
					channel = line[2].lower()

					if channel[0] in "#&":
						self.channels[channel].moderator.handle_line(line)

					if line[0] == ":sv!^services@volatile/bot/sv" and\
					 line[2] == self.nick:
						if icompare(line[3], ":OLDFOUND") and len(line) > 5:
							channel = line[4].lower()

							if channel not in self.channels:
								self.channels[channel] = Channel(line[4])

							self.channels[channel].add_role("founder", "FfAaKkLlD*a")
							self.channels[channel].add_mask("!^%s@" % line[5], "founder")

				elif irccmd == "PRIVMSG" and line[2][0] in "#&":
					nick = split_sender(line[0])[0]

					if nick not in self.ratelimit:
						pass
					elif self.ratelimit[nick] > time():
						print "ratelimit for " + nick
						continue

					channel = line[2].lower()
					channel_obj = self.channels[channel]
					channel_obj.moderator.handle_line(line)
					ident = split_sender(line[0])[1]
					host = split_sender(line[0])[2]
					cmd = line[3].split(":",1)[-1].lower()
					msg = " ".join(line[3:]).split(":",1)[-1]

					# todo
					if msg and msg[0] == "\x01" and msg.find("\x01ACTION") == -1 and channel_obj.protect:
						self.time_mode(channel, "b", "%s!%s@%s" % (nick, ident, host), 60)
						self.send_line("KICK %s %s :CTCPs forbidden in this channel"
						 % (channel, nick))

					#rtn = channel_obj.push_msg(nick, ident, host, "PRIVMSG", msg)
					rtn = True
					if rtn: self.send_line(rtn)

					if cmd.startswith(channel_obj.prefix):
						cb = getattr(self, "cmd_%s" % cmd[1:], None)
						if cb is not None:
							cb(line, nick, channel, ident, channel_obj)
							continue

					if icompare(line[3], ":.help"):
						self.cmd_help(line, nick, channel, ident, channel_obj)

					elif icompare(" ".join(line[3:]), ":.prefix reset"):
						if channel_obj.has_flag(line[0], 'F'):
							channel_obj.prefix = '.'
							self.send_line("NOTICE %s :Command prefix reset to \x02.\x02 in this channel" % channel)

				elif irccmd == "JOIN":
					channel = line[2].lstrip(":").lower()
					nick, user, host = split_sender(line[0])

					if channel not in self.channels:
						self.channels[channel] = Channel(channel)

					self.channels[channel].moderator.handle_line(line)

					ban = self.channels[channel].is_banned(line[0])
					if ban:
						self.time_mode(channel, "b",
						 "%s!%s@%s" % (nick, user, host), 60)
						self.send_line("KICK %s %s :%s" % (channel, nick, ban))
						return

					if self.nick == nick:
						self.channels[channel].prime_ops(self.op_modes)
						self.send_line(
						 "WHO %s\r\n"
						 "MODE %s\r\n"
						 "MODE %s +%s"
						 % (channel,
						 channel,
						 channel, self.list_modes))

					elif self.channels[channel].limit:
						self.time_limit(channel,
						 len(self.channels[channel].users) +
						  self.channels[channel].limit[0] + 1,
						 self.channels[channel].limit[1])

					automode = self.channels[channel].automodes(line[0].lstrip(":"))

					if automode and (self.nick in self.channels[channel].ops[conf.high_op] or self.channels[channel].registered):
						self.mode_stack(channel, automode, nick)

					self.channels[channel].users.add(nick.lower())

				elif line[1] in ("PART", "KICK"):
					channel = line[2].lower()
					nick = split_sender(line[0])[0].lower() if line[1] == "PART" else line[3].lower()

					if nick == self.nick.lower():
						if self.channels[channel].has_flag(line[0], 'F'):
							del self.channels[channel]

						else:
							self.send_line("JOIN :%s" % channel, prio=True)
						return

					for mode in self.channels[channel].ops.values():
						if nick in mode: mode.remove(nick)
					if nick in self.channels[channel].users:
						self.channels[channel].users.remove(nick)

					if self.channels[channel].limit:
						self.time_limit(channel,
						 len(self.channels[channel].users) +
						  self.channels[channel].limit[0],
						 self.channels[channel].limit[1])

				elif irccmd == "QUIT":
					nick = split_sender(line[0])[0].lower()
					for channel in self.channels.itervalues():
						if nick in channel.users:
							channel.users.remove(nick)
							if channel.limit:
								self.time_limit(channel.name,
								 len(channel.users) +
								  channel.limit[0],
								 channel.limit[1])

				elif line[1] == "NICK":
					old_nick = split_sender(line[0])[0].lower()
					new_nick = line[2].lstrip(":").lower()
					for channel in self.channels.itervalues():
						if old_nick not in channel.users: continue
						channel.users.remove(old_nick)
						channel.users.add(new_nick)

				elif irccmd == "TOPIC": # or line[1] == "332":
					channel = line[2].lower()
					channel_obj = self.channels[channel]

					if channel_obj.lasttopics[1] > 4 and channel_obj.protect:
						if "t" not in channel_obj.modes:
							self.time_mode(channel, "t", "", 300)
							self.send_line("MODE %s +t" % channel)

					if len(line) > 3:
						channel_obj.set_topic(" ".join(line[3:]).lstrip(":"))
					else:
						channel_obj.set_topic(None)

				elif irccmd == "INVITE":
					channel = line[3].lstrip(":")
					sender = line[0]

					self.send_line(
					 "JOIN %s\r\n"
					 "PRIVMSG %s :hi! type `.help` for commands"
					 % ((channel,) * 2))

	def cmd_help (self, line, nick, channel, ident, channel_obj):
		if len(line) == 4:
			self.send_line(
			 "NOTICE %s :Commands:\r\n"
			 "NOTICE %s :%crole add <role> <flags>\r\n" #1
			 "NOTICE %s :%crole rm <role> [flags]\r\n" #2
			 "NOTICE %s :%crole list\r\n" #3
			 "NOTICE %s :%cmask add <mask> <role>\r\n" #4
			 "NOTICE %s :%cmask rm <name> <role>\r\n" #5
			 "NOTICE %s :%cmask list\r\n" #6
			 "NOTICE %s :%ctopic <topic>\r\n" #7
			 "NOTICE %s :%cup <opmode>\r\n" #8
			 "NOTICE %s :%ctopiclock\r\n" #9
			 "NOTICE %s :%cmodelock\r\n" #10
			 "NOTICE %s :%ctransfer\r\n" #11
			 "NOTICE %s :%cprefix <prefix>\r\n" #12
			 "NOTICE %s :.prefix reset"
			 % (nick,
			 nick, channel_obj.prefix, #1
			 nick, channel_obj.prefix, #2
			 nick, channel_obj.prefix, #3
			 nick, channel_obj.prefix, #4
			 nick, channel_obj.prefix, #5
			 nick, channel_obj.prefix, #6
			 nick, channel_obj.prefix, #7
			 nick, channel_obj.prefix, #8
			 nick, channel_obj.prefix, #9
			 nick, channel_obj.prefix, #10
			 nick, channel_obj.prefix, #11
			 nick, channel_obj.prefix, #12
			 nick,
			 ))
			self.send_line(
			 "NOTICE %s :\r\n"
			 "NOTICE %s :%chelp\r\n" #1
			 "NOTICE %s :%chelp flags\r\n" #2
			 "NOTICE %s :%chelp masks\r\n" #3
			 "NOTICE %s :%chelp roles" #4
			 % (nick,
			 nick, channel_obj.prefix, #1
			 nick, channel_obj.prefix, #2
			 nick, channel_obj.prefix, #3
			 nick, channel_obj.prefix, #4
			 ))
			self.ratelimit[nick] = time() + 10

		elif icompare(line[4], "flags"):
			self.send_line(
			 "NOTICE %s :Flags:\r\n" #1
			 "NOTICE %s :F can %ctransfer, /kick bot\r\n" #2
			 "NOTICE %s :f can %ctopic, %cmode\r\n" #3
			 "NOTICE %s :A can %crole add/rm/list, %cmask add/rm/list\r\n" #4
			 "NOTICE %s :  cannot modify FfKkb flags without already having them\r\n" #5
			 "NOTICE %s :a can %crole/%cmask list anyone without b flag\r\n" #6
			 "NOTICE %s :K can modify b flag\r\n" #7
			 "NOTICE %s :k can view b autokick list\r\n" #8
			 "NOTICE %s :L can %climit add/rm/list" #9
			 "NOTICE %s :l can %climit list\r\n" #10
			 "NOTICE %s :D can modify defcon system\r\n" #11
			 "NOTICE %s :b gets autokicked and banned" #12
			 % (nick, #1
			 nick, channel_obj.prefix, #2
			 nick, channel_obj.prefix, channel_obj.prefix, #3
			 nick, channel_obj.prefix, channel_obj.prefix, #4
			 nick, #5
			 nick, channel_obj.prefix, channel_obj.prefix, #6
			 nick, #7
			 nick, #8
			 nick, channel_obj.prefix, #9
			 nick, channel_obj.prefix, #10
			 nick, #11
			 nick #12
			 ))
			self.send_line(
			 "NOTICE %s :\r\n"
			 "NOTICE %s :*%s is used for auto-op\r\n"
			 "NOTICE %s :+%s is used for manual op with %cup"
			 % (nick,
			 nick, "".join([i for i in self.op_modes]),
			 nick, "".join([i for i in self.op_modes]), channel_obj.prefix
			 ))
			self.ratelimit[nick] = time() + 10

		elif icompare(line[4], "masks"):
			self.send_line(
			 "NOTICE %s :Masks:\r\n"
			 "NOTICE %s :uses glob matching patterns. examples below\r\n"
			 "NOTICE %s :match all: !@ or *!*@*\r\n"
			 "NOTICE %s :match ident: !^username@ or *!^username@*\r\n"
			 "NOTICE %s :match mask: nick????!~*@host.name"
			 % (nick, nick, nick, nick, nick))
			self.ratelimit[nick] = time() + 10

		elif icompare(line[4], "roles"):
			self.send_line(
			 "NOTICE %s :Roles:\r\n"
			 "NOTICE %s :gives flags to masks with certain roles. examples below\r\n"
			 "NOTICE %s :role 'voice' with flags a*v\r\n"
			 "NOTICE %s :role 'founder' with flags FfAaKkLlD*a+q\r\n"
			 % (nick, nick, nick, nick, nick))
			self.ratelimit[nick] = time() + 10

	def cmd_role (self, line, nick, channel, ident, channel_obj):
		if len(line) < 5: return
		if icompare(line[4], "add") and len(line) == 7 and channel_obj.has_flag(line[0], 'A'):
			channel_obj.add_role(line[5], line[6])
			self.send_line("NOTICE %s :Added role" % channel)

		elif icompare(line[4], "rm") and len(line) == 7 and channel_obj.has_flag(line[0], 'A'):
			if channel_obj.del_flags(line[5], line[6]):
				self.send_line("NOTICE %s :Removed modes" % channel)

		elif icompare(line[4], "rm") and len(line) == 6 and channel_obj.has_flag(line[0], 'A'):
			if channel_obj.del_role(line[5]):
				self.send_line("NOTICE %s :Removed role" % channel)

		elif icompare(line[4], "list") and channel_obj.has_flag(line[0], 'a'):
			for role, flags in channel_obj.roles.iteritems():
				self.send_line("NOTICE %s :Role \x02%s\x0F with flags \x02%s" % (nick, role, flags))
			self.send_line("NOTICE %s :End of `role list`" % nick)

	def cmd_mask (self, line, nick, channel, ident, channel_obj):
		if len(line) < 5: return
		if icompare(line[4], "add") and len(line) == 7 and channel_obj.has_flag(line[0], 'A'):
			mask = channel_obj.add_mask(line[5], line[6])
			if mask:
				self.send_line("NOTICE %s :Added mask %s" % (channel, mask))
			else:
				self.send_line("NOTICE %s :Role does not exist" % (channel))
				self.ratelimit[nick] = time() + 1

		elif icompare(line[4], "rm") and len(line) == 6 and channel_obj.has_flag(line[0], 'A'):
			if channel_obj.del_mask(line[5]):
				self.send_line("NOTICE %s :Removed mask" % channel)

		elif icompare(line[4], "list") and channel_obj.has_flag(line[0], 'a'):
			for mask, role in channel_obj.masks.iteritems():
				self.send_line("NOTICE %s :Mask \x02%s\x0F with role \x02%s" % (nick, mask, role))
			self.send_line("NOTICE %s :End of `mask list`" % nick)
			self.ratelimit[nick] = time() + 1

	def cmd_akick (self, line, nick, channel, ident, channel_obj):
		if len(line) < 5: return
		if icompare(line[4], "add") and len(line) >= 6 and channel_obj.has_flag(line[0], 'K'):
			if len(line) > 6:
				reason = " ".join(line[6:])
			else:
				reason = "User matches an autokick"
			mask = channel_obj.add_akick(line[5], reason)
			self.send_line("NOTICE %s :Added mask %s" % (channel, mask))

		elif icompare(line[4], "rm") and len(line) == 6 and channel_obj.has_flag(line[0], 'K'):
			if channel_obj.del_akick(line[5]):
				self.send_line("NOTICE %s :Removed mask" % channel)

		elif icompare(line[4], "list") and channel_obj.has_flag(line[0], 'k'):
			for mask, reason in channel_obj.akicks.iteritems():
				self.send_line("NOTICE %s :Mask \x02%s\x0F banned: \x02%s" % (nick, mask, reason))
			self.send_line("NOTICE %s :End of `akick list`" % nick)
			self.ratelimit[nick] = time() + 1

	def cmd_prefix (self, line, nick, channel, ident, channel_obj):
		if len(line) != 5: return
		if channel_obj.has_flag(line[0], 'F'):
			if len(line[4]) == 1:
				channel_obj.prefix = line[4]
				self.send_line(
				 "NOTICE %s :Commands now start with \x02%c\x0F in this channel\r\n"
				 "NOTICE %s :Reset with `.prefix reset`"
				 % (channel, line[4], channel))
			else:
				self.send_line("NOTICE %s :Prefix must be one character long" % channel)
				self.ratelimit[nick] = time() + 1

	def cmd_topic (self, line, nick, channel, ident, channel_obj):
		if channel_obj.has_flag(line[0], 'f'):
			if len(line) > 4:
				topic = " ".join(line[4:])
			else:
				topic = self.channels[channel].topic if self.channels[channel].topic else ""
			self.send_line("TOPIC %s :%s" % (channel, topic))

	def cmd_transfer (self, line, nick, channel, ident, channel_obj):
		if channel_obj.has_flag(line[0], 'F') and ident[0] == "^":
			self.send_line("MODE %s +r %s" % (channel, ident[1:]))

	def cmd_topiclock (self, line, nick, channel, ident, channel_obj):
		if channel_obj.has_flag(line[0], 'f'):
			self.send_line("MODE %s %cT" % (channel, "-" if "T" in channel_obj.modes else "+"), prio=True)

	def cmd_modelock (self, line, nick, channel, ident, channel_obj):
		if channel_obj.has_flag(line[0], 'f'):
			self.send_line("MODE %s %cM" % (channel, "-" if "M" in channel_obj.modes else "+"), prio=True)

	def cmd_mode (self, line, nick, channel, ident, channel_obj):
		if len(line) < 5: return
		if channel_obj.has_flag(line[0], 'f'):
			self.send_line("MODE %s %s" % (channel, " ".join(line[4:])), prio=True)

	def cmd_sync (self, line, nick, channel, ident, channel_obj):
		if channel_obj.has_flag(line[0], 'f'):
			self.send_line("WHO %s" % channel, prio=True)

	def cmd_up (self, line, nick, channel, ident, channel_obj):
		modes = ""
		if len(line) == 4:
			for c in self.op_modes:
				if channel_obj.can_op(line[0], c):
					modes += c
		else:
			for c in line[4]:
				if c not in self.op_modes:
					continue
				if channel_obj.can_op(line[0], c):
					modes += c
		if modes:
			self.send_line("MODE %s +%s %s" % (channel, modes, (nick + " ") * len(modes)))

	def cmd_stats (self, line, nick, channel, ident, channel_obj):
		self.send_line(
		 "NOTICE %s :Uptime: %d\r\n"
		 "NOTICE %s :Topics: last %d count %d" %
		  (channel, time() - uptime,
		  channel, self.channels[channel].lasttopics[0], self.channels[channel].lasttopics[1]))
		now = time()
		for (channel, mode, param), when in self.sendmodes.iteritems():
			self.send_line(
			 "NOTICE %s :%s %s %s" % (channel, mode, param, when - now))
		print "High prio queue: %d" % len(self.sendlines_h)
		print "Low prio queue: %d" % len(self.sendlines_l)
		for channel, channel_obj in self.channels.iteritems():
			print channel
			print "\tregistered: %s; protected: %s; prefix: %c" % ("yes" if channel_obj.registered else "no",
			 "yes" if channel_obj.protect else "no", channel_obj.prefix)
			print "\t%s" % channel_obj.topic
			print "\t%s" % channel_obj.lists
			for op, nicks in channel_obj.ops.iteritems():
				if not nicks: continue
				print "\t%s" % op
				for nick in nicks:
					print "\t\t%s" % nick
			for nick in channel_obj.users:
				print "\t%s" % nick

	def cmd_protect (self, line, nick, channel, ident, channel_obj):
		channel_obj.protect = not channel_obj.protect
		self.send_line("NOTICE %s :protect mode %sabled" % (channel, "en" if channel_obj.protect else "dis"))

	def cmd_limit (self, line, nick, channel, ident, channel_obj):
		if len(line) < 5: return
		if not channel_obj.has_flag(line[0], "L"): return
		if line[4] == "joins" and len(line) == 7:
			channel_obj.limit = (int(line[5]), int(line[6]))
			self.send_line("NOTICE %s :limit set" % channel)
		elif line[4] == "joins" and len(line) == 6 and line[5] == "off":
			channel_obj.limit = None
			self.send_line("MODE %s -l" % channel)

if __name__ == "__main__":
	main = Bot()
	signal.signal(signal.SIGHUP, main.handle_hup)

	try:
		while True:
			main.loop()

	except KeyboardInterrupt:
		main.sock.send("QUIT :Interrupted")
		main.save_db(main.dbfile)

#	except BaseException:
#		type, e, tb = sys.exc_info()
#		filename = tb.tb_frame.f_code.co_filename
#		lineno = tb.tb_lineno
#		print "%s error in %s, %d: %s" % (type, filename, lineno, e)
#		main.save_db(main.dbfile)
