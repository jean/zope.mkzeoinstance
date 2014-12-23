##############################################################################
#
# Copyright (c) 2003 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""%(program)s -- create a ZEO instance.

Usage: %(program)s home [[host:]port]

Given an "instance home directory" <home> and some configuration
options (all of which have default values), create the following:

<home>/etc/zeo.conf     -- ZEO config file
<home>/var/             -- Directory for data files: Data.fs etc.
<home>/log/             -- Directory for log files: zeo.log and zeoctl.log
<home>/bin/runzeo       -- the zeo server runner
<home>/bin/zeoctl       -- start/stop script (a shim for zeoctl.py)

The script will not overwrite existing files; instead, it will issue a
warning if an existing file is found that differs from the file that
would be written if it didn't exist.
"""

# WARNING!  Several templates and functions here are reused by ZRS.
# So be careful with changes.

import os
import sys
import stat
import getopt

import zdaemon

try:
    text_type = unicode
except NameError:  # pragma: NO COVER Py3k
    text_type = str

zeo_conf_template = """\
# ZEO configuration file

%%define INSTANCE %(instance_home)s

<zeo>
  address %(address)s
  read-only false
  invalidation-queue-size 100
  # pid-filename $INSTANCE/var/ZEO.pid
  # monitor-address PORT
  # transaction-timeout SECONDS
</zeo>

<filestorage 1>
  path $INSTANCE/var/Data.fs
</filestorage>

<eventlog>
  level info
  <logfile>
    path $INSTANCE/log/zeo.log
  </logfile>
</eventlog>

<runner>
  program $INSTANCE/bin/runzeo
  socket-name $INSTANCE/var/%(package)s.zdsock
  daemon true
  forever false
  backoff-limit 10
  exit-codes 0, 2
  directory $INSTANCE
  default-to-interactive true
  # user zope
  python %(python)s
  zdrun %(zdaemon_home)s/zdaemon/zdrun.py

  # This logfile should match the one in the %(package)s.conf file.
  # It is used by zdctl's logtail command, zdrun/zdctl doesn't write it.
  logfile $INSTANCE/log/%(package)s.log
</runner>
"""

zeoctl_template = """\
#!/bin/sh
# %(PACKAGE)s instance control script

# The following two lines are for chkconfig.  On Red Hat Linux (and
# some other systems), you can copy or symlink this script into
# /etc/rc.d/init.d/ and then use chkconfig(8) to automatically start
# %(PACKAGE)s at boot time.

# chkconfig: 345 90 10
# description: start a %(PACKAGE)s server

PYTHON="%(python)s"
INSTANCE_HOME="%(instance_home)s"
ZODB3_HOME="%(zodb3_home)s"

CONFIG_FILE="%(instance_home)s/etc/%(package)s.conf"

PYTHONPATH="$ZODB3_HOME"
export PYTHONPATH INSTANCE_HOME

ZEOCTL="$ZODB3_HOME/ZEO/zeoctl.py"

exec "$PYTHON" "$ZEOCTL" -C "$CONFIG_FILE" ${1+"$@"}
"""

runzeo_template = """\
#!/bin/sh
# %(PACKAGE)s instance start script

PYTHON="%(python)s"
INSTANCE_HOME="%(instance_home)s"
ZODB3_HOME="%(zodb3_home)s"

CONFIG_FILE="%(instance_home)s/etc/%(package)s.conf"

PYTHONPATH="$ZODB3_HOME"
export PYTHONPATH INSTANCE_HOME

RUNZEO="$ZODB3_HOME/ZEO/runzeo.py"

exec "$PYTHON" "$RUNZEO" -C "$CONFIG_FILE" ${1+"$@"}
"""

def print_(msg, *args, **kw):
    if args:
        msg = msg % args
    if kw:
        msg = msg % kw
    if not isinstance(msg, text_type):
        msg = msg.decode('utf8')
    sys.stdout.write('%s\n' % msg)

def main():
    ZEOInstanceBuilder().run()
    print_("All done.")

class ZEOInstanceBuilder:

    def run(self):
        try:
            opts, args = getopt.getopt(sys.argv[1:], "h", ["help"])
        except getopt.error as msg:
            print_(msg)
            sys.exit(2)
        program = os.path.basename(sys.argv[0])
        if opts:
            # There's only the help options, so just dump some help:
            msg = __doc__ % {"program": program}
            print_(msg)
            sys.exit()
        if len(args) not in [1, 2]:
            print_("Usage: %s home [[host:]port]", program)
            sys.exit(2)

        instance_home = args[0]
        if not os.path.isabs(instance_home):
            instance_home = os.path.abspath(instance_home)

        zodb3_home = None
        for entry in sys.path:
            if os.path.exists(os.path.join(entry, 'ZODB')):
                zodb3_home = entry
                break
        if zodb3_home is None:
            print_("Can't find ZODB software (not in sys.path)")
            sys.exit(2)

        zdaemon_home = os.path.split(zdaemon.__path__[0])[0]

        host = None
        port = 9999
        if args[1:]:
            addr_string = args[1]
            if ':' in addr_string:
                host, port = addr_string.split(':', 1)
            else:
                port = addr_string
            port = int(port)
        address = port
        if host:
            address = host + ':' + str(port)

        params = self.get_params(zodb3_home, zdaemon_home,
                                 instance_home, address)
        self.create(instance_home, params)

    def get_params(self, zodb3_home, zdaemon_home, instance_home, address):
        return {
            "package": "zeo",
            "PACKAGE": "ZEO",
            "zodb3_home": zodb3_home,
            "zdaemon_home": zdaemon_home,
            "instance_home": instance_home,
            "address": address,
            "python": sys.executable,
            }

    def create(self, home, params):
        makedir(home)
        makedir(home, "etc")
        makedir(home, "var")
        makedir(home, "log")
        makedir(home, "bin")
        makefile(zeo_conf_template, home, "etc", "zeo.conf", **params)
        makexfile(zeoctl_template, home, "bin", "zeoctl", **params)
        makexfile(runzeo_template, home, "bin", "runzeo", **params)


def makedir(*args):
    path = ""
    for arg in args:
        path = os.path.join(path, arg)
    mkdirs(path)
    return path

def mkdirs(path):
    if os.path.isdir(path):
        return
    head, tail = os.path.split(path)
    if head and tail and not os.path.isdir(head):
        mkdirs(head)
    os.mkdir(path)
    print_("Created directory %s", path)

def makefile(template, *args, **kwds):
    path = makedir(*args[:-1])
    path = os.path.join(path, args[-1])
    data = template % kwds
    if os.path.exists(path):
        with open(path) as f:
            olddata = f.read().strip()
        if olddata:
            if olddata != data.strip():
                print_("Warning: not overwriting existing file %r", path)
            return path
    with open(path, "w") as f:
        f.write(data)
    print_("Wrote file %s", path)
    return path

def makexfile(template, *args, **kwds):
    path = makefile(template, *args, **kwds)
    umask = os.umask(0o022)
    os.umask(umask)
    mode = 0o0777 & ~umask
    if stat.S_IMODE(os.stat(path)[stat.ST_MODE]) != mode:
        os.chmod(path, mode)
        print_("Changed mode for %s to %o", path, mode)
    return path
