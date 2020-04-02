#  Project: tnotify
#  Description: A tray notification script for weechat. Uses
#  weechat APIs to fork a (Py)Qt system tray.
#  Forked from lnotify-0.3.1
#  Author: NP-Hardass <NP.Hardass@gmail.com>
#  License: GPL3
#

#  Example configuration:
#
#  Spawns a new terminal that auto attaches to an existing weechat session
#  onclick_exec:
#	   mate-terminal -x tmux attach -t weechat
#
#  Single instance terminal:
#  /usr/local/bin/weechat-tmux:
#	   #!/bin/sh
#	   tmux attach -dt weechat || \
#	   tmux new-session -s weechat "/usr/bin/weechat $@" && \
#	   exit
#  onclick_exec:
#	   mate-terminal -e /usr/local/bin/weechat-tmux

# ChangeLog:
#
# 0.1.0
# Initial release

WEECHAT_ICON_URL="https://raw.githubusercontent.com/weechat/weechat/v1.7/weechat.png"
WEECHAT_ICON_SHA512="4784b22a6edc63ed2083cc2cb1cec843d490ad210bc587e691e1b09a3dcb8dbf54a75d1f94f404d40a32d9c9e8b242e2294e373e768a6bfe28cd560271d3d886"
NULL_ICON_URL="https://raw.githubusercontent.com/NP-Hardass/blinking-pyqt-tray/0.1.0/null.png"
NULL_ICON_SHA512="66e293276a50b2a88e87df2dec5f26ab26be69f26f36db1af96426a5ee355901f67ad307a59c3429eb915494cc53a97ae2942d867b89e5159c2d8011fed503eb"
SYSTRAY_PY_URL="https://raw.githubusercontent.com/NP-Hardass/blinking-pyqt-tray/0.1.0/systray.py"
SYSTRAY_PY_SHA512="26e61540470dfd86aee239cf7b9e663a40b6ef2cfd990ef593875779d40ff2e4c3a284e87d2b0a821cb0e6540c3b91b4f26c47cf873f725a839fae565f1b884f"

import weechat as weechat
from os import environ, path, kill, rename, remove
import signal
import hashlib
import time
from builtins import object

SCRIPT_NAME = "tnotify"
SCRIPT_VERSION = "0.1.0"
SCRIPT_LICENSE = "GPL3"
SCRIPT_AUTHOR = "NP-Hardass <NP.Hardass@gmail.com>"
SCRIPT_DESC = "System tray notification in (Py)Qt"

# convenient table checking for bools
true = { "on": True, "off": False }

# declare this here, will be global config() object
# but is initialized in __main__
cfg = None
hooks = None
state = None

# Initialized in __main__
plugin_dir = None

class hook_table(object):
	def __init__(self):
		self.hooks = {
			"config": None,
			"focus": None,
			"notify": None,
			"print": None,
			"tray": None,
		}
	def __getitem__(self, key):
		return self.hooks[key]

class state(object):
	def __init__(self, config):
		self.UNHOOK_TRAY = None
		self.BOOTSTRAPPED = False

	def unhook(self, boolean):
		self.UNHOOK_TRAY = boolean

	def unhooked(self):
		return self.UNHOOK_TRAY


class config(object):
	def __init__(self):
		# default options for tnotify
		self.opts = {
			"highlight": "on",
			"query": "on",
			"notify_away": "off",
			"icon": "weechat",
			"alt-icon": "null",
			"onclick_exec": "",
		}

		self.init_config()
		self.check_config()
		self.verify_qt()

	def init_config(self):
		for opt, value in list(self.opts.items()):
			temp = weechat.config_get_plugin(opt)
			if not len(temp):
				weechat.config_set_plugin(opt, value)

	def check_config(self):
		for opt in self.opts:
			self.opts[opt] = weechat.config_get_plugin(opt)

	def verify_qt(self):
		from pkgutil import find_loader
		if find_loader('PyQt4') is None or \
				find_loader('PyQt5') is None or \
				find_loader('PySide') is None:
			return False
		return True

	def __getitem__(self, key):
		return self.opts[key]

def printc(msg):
	weechat.prnt("", msg)

def handle_msg(data, pbuffer, date, tags, displayed, highlight, prefix, message):
	highlight = bool(highlight) and weechat.config_get_plugin("highlight")
	query = true[weechat.config_get_plugin("query")]
	notify_away = true[weechat.config_get_plugin("notify_away")]
	buffer_type = weechat.buffer_get_string(pbuffer, "localvar_type")
	away = weechat.buffer_get_string(pbuffer, "localvar_away")
	x_focus = False
	window_name = ""
	my_nickname = "nick_" + weechat.buffer_get_string(pbuffer, "localvar_nick")

	# Check to make sure we're in X and xdotool exists.
	# This is kinda crude, but I'm no X master.
	if (environ.get('DISPLAY') != None) and path.isfile("/bin/xdotool"):
		window_name = subprocess.check_output(["xdotool", "getwindowfocus", "getwindowname"])

	if "WeeChat" in window_name:
		x_focus = True

	if pbuffer == weechat.current_buffer() and x_focus:
		return weechat.WEECHAT_RC_OK

	if away and not notify_away:
		return weechat.WEECHAT_RC_OK

	if my_nickname in tags:
		return weechat.WEECHAT_RC_OK

	buffer_name = weechat.buffer_get_string(pbuffer, "short_name")


	if buffer_type == "private" and query:
		update_tray('start')
	elif buffer_type == "channel" and highlight:
		update_tray('start')

	return weechat.WEECHAT_RC_OK

def process_download_cb(data, command, rc, out, err):
	if int(rc) >= 0:
		weechat.prnt("", "End of transfer (rc=%s)" % rc)
	return weechat.WEECHAT_RC_OK

def config_cb(data, option, value):
	if option == 'plugins.var.python.tnotify.icon':
		if value != "weechat":
			if not path.exists( value ):
				return weechat.WEECHAT_RC_ERROR
		kill_tray()
		spawn_tray()
	if option == 'plugins.var.python.tnotify.alt-icon':
		if value != "weechat":
			if not path.exists( value ):
				return weechat.WEECHAT_RC_ERROR
		kill_tray()
		spawn_tray()

	if option == 'plugins.var.python.tnotify.onclick_exec':
		kill_tray()
		spawn_tray()

	return weechat.WEECHAT_RC_OK

def bootstrap_tray():
	BUF_SIZE = 65536
	weechat.mkdir_parents(plugin_dir, 0o755)

	if weechat.config_get_plugin("icon") == "weechat":
		# Download icon
		icon = plugin_dir + "/icons/weechat.png"
		if not path.exists( icon ):
			weechat.mkdir_parents( plugin_dir + "/icons" , 0o755)
			weechat.hook_process_hashtable("url:" + WEECHAT_ICON_URL,
					{"file_out": icon + ".tmp"}, 30 * 1000, "process_download_cb", "")
			time.sleep(0.5)
			sha512 = hashlib.sha512()
			f = open (icon + ".tmp", 'rb')
			sha512.update(f.read())
			if sha512.hexdigest() != WEECHAT_ICON_SHA512:
				printc("weechat icon failed sha512sum; got " +
						sha512.hexdigest())
				return 1
			else:
				rename(icon + ".tmp", icon)

	if weechat.config_get_plugin("alt-icon") == "null":
		icon = plugin_dir + "/icons/null.png"
		if not path.exists( icon ):
			weechat.mkdir_parents( plugin_dir + "/icons" , 0o755)
			weechat.hook_process_hashtable("url:" + NULL_ICON_URL,
					{"file_out": icon + ".tmp"}, 30 * 1000, "process_download_cb", "")
			time.sleep(0.5)
			sha512 = hashlib.sha512()
			f = open (icon + ".tmp", 'rb')
			sha512.update(f.read())
			if sha512.hexdigest() != NULL_ICON_SHA512:
				printc("null icon failed sha512sum; got " +
						sha512.hexdigest())
				return 1
			else:
				rename(icon + ".tmp", icon)

	# Download tray icon script
	script = plugin_dir + "/systray.py"
	if not path.exists( script ):
		weechat.hook_process_hashtable("url:" + SYSTRAY_PY_URL, {"file_out":
			script + ".tmp"}, 30 * 1000, "process_download_cb", "")
		time.sleep(1)
		sha512 = hashlib.sha512()
		f = open (script + ".tmp", 'rb')
		sha512.update(f.read())
		if sha512.hexdigest() != SYSTRAY_PY_SHA512:
			printc("systray.py failed sha512sum; got " +
				sha512.hexdigest())
			return 1
		else:
			rename(script + ".tmp", script)

	state.BOOTSTRAPPED = True

def tray_process_cb(data, command, return_code, out, err):
	state.unhook(False)
	return weechat.WEECHAT_RC_OK

def tray_focus_cb(data, info):
	update_tray('stop')

def spawn_tray():
	state.unhook(True)
	icon = weechat.config_get_plugin("icon")
	if icon == "weechat":
		icon = plugin_dir + "/icons/weechat.png"
	alt_icon = weechat.config_get_plugin("alt-icon")
	if alt_icon == "null":
		alt_icon = plugin_dir + "/icons/null.png"
	onclick_exec = weechat.config_get_plugin("onclick_exec")
	cmd="python '{0}/systray.py' '{0}/systray.pid' '{1}' '{2}' '{3}'".format(plugin_dir, icon, alt_icon, onclick_exec)
	hooks.hooks['tray'] = weechat.hook_process(cmd, 0, "tray_process_cb", "")

def kill_tray():
	if path.exists( plugin_dir + "/systray.pid" ):
		remove( plugin_dir + "/systray.pid" )
	if state.unhooked():
		weechat.unhook(hooks.hooks['tray'])

def update_tray(status):
	if path.exists( plugin_dir + "/systray.pid" ):
		pidfile = open( plugin_dir + "/systray.pid", 'r')
	else:
		return
	pid = int(pidfile.read())
	pidfile.close()
	if status == 'start':
		hooks.hooks['focus'] = weechat.hook_focus("chat", "tray_focus_cb", "")
		kill(pid, signal.SIGUSR1)
	if status == 'stop':
		if hooks.hooks['focus'] is not None:
			weechat.unhook(hooks.hooks['focus'])
			kill(pid, signal.SIGUSR2)

# execute initializations in order
if __name__ == "__main__":
	weechat.register(SCRIPT_NAME, SCRIPT_AUTHOR, SCRIPT_VERSION, SCRIPT_LICENSE,
		SCRIPT_DESC, "", "")

	plugin_dir = weechat.info_get("weechat_dir", "") + "/tray"

	cfg = config()
	state = state(cfg)
	hooks = hook_table()

	hooks.hooks['print'] = weechat.hook_print("", "", "", 1, "handle_msg", "")

	# handle config because changing some options requires respawning the tray
	# process
	hooks.hooks['config'] = weechat.hook_config("plugins.var.python." + SCRIPT_NAME + ".*", "config_cb", "")

	bootstrap_tray()
	if state.BOOTSTRAPPED != True:
		raise Exception("Failed to bootstrap tray")

	spawn_tray()
