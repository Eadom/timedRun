#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import signal
import subprocess
import sys
import time
import subprocesses as sps

import envVars

ASAN_EXIT_CODE = 77

# (RC_CRASHED, RC_TIMEOUT, RC_NORMAL, RC_ABNORMAL, RC_NONE) = range(5)
class Status(object):
    CRASHED = 0
    TIMEOUT = 1
    NORMAL = 2
    ABNORMAL =3
    NONE = 4


def getSignalName(num, default=None):
    for p in dir(signal):
        if p.startswith("SIG") and not p.startswith("SIG_"):
            if getattr(signal, p) == num:
                return p
    return default


class rundata(object):
    """Define struct that contains data from a process that has already ended."""

    def __init__(self, sta, rc, msg, elapsedtime, killed, pid, out, err):
        """Initialize with given parameters."""
        self.sta = sta
        self.rc = rc
        self.msg = msg
        self.elapsedtime = elapsedtime
        self.killed = killed
        self.pid = pid
        self.out = out
        self.err = err
    def __str__(self):
        return self.msg


def xpkill(p):
    """Based on mozilla-central/source/build/automation.py.in ."""
    try:
        p.kill()
    except WindowsError:
        if p.poll() == 0:
            try:
                print 'Trying to kill the process the first time...'
                p.kill()  # Verify that the process is really killed.
            except WindowsError:
                if p.poll() == 0:
                    print 'Trying to kill the process the second time...'
                    p.kill()  # Re-verify that the process is really killed.


def makeEnv(binPath):
    env = envVars.envWithPath(os.path.abspath(os.path.dirname(binPath)))
    if 'ASAN_OPTIONS' in env:
        env['ASAN_OPTIONS'] += ':exitcode=' + str(ASAN_EXIT_CODE)
    else:
        env['ASAN_OPTIONS'] = 'exitcode=' + str(ASAN_EXIT_CODE)
    symbolizer_path = envVars.findLlvmBinPath()
    if symbolizer_path is not None:
        env['ASAN_SYMBOLIZER_PATH'] = os.path.join(symbolizer_path, 'llvm-symbolizer')
    return env


def timed_run(commandWithArgs, timeout, logPrefix, inp=None, preexec_fn=None):
    """If logPrefix is None, uses pipes instead of files for all output."""
    if not isinstance(commandWithArgs, list):
        raise TypeError("commandWithArgs should be a list (of strings).")
    if not isinstance(timeout, int):
        raise TypeError("timeout should be an int.")

    useLogFiles = isinstance(logPrefix, str)

    commandWithArgs[0] = os.path.expanduser(commandWithArgs[0])
    progname = commandWithArgs[0].split(os.path.sep)[-1]

    starttime = time.time()

    if useLogFiles:
        childStdOut = open(logPrefix + "-out.txt", 'w')
        childStdErr = open(logPrefix + "-err.txt", 'w')

    try:
        child = subprocess.Popen(
            commandWithArgs,
            stdin=(None if (inp is None) else subprocess.PIPE),
            stderr=(childStdErr if useLogFiles else subprocess.PIPE),
            stdout=(childStdOut if useLogFiles else subprocess.PIPE),
            close_fds=(os.name == "posix"),  # close_fds should not be changed on Windows
            env=makeEnv(commandWithArgs[0]),
            preexec_fn=preexec_fn
        )
    except OSError, e:
        print "Tried to run:"
        print "  " + repr(commandWithArgs)
        print "but got this error:"
        print "  " + str(e)
        sys.exit(2)

    if inp is not None:
        child.stdin.write(inp)
        child.stdin.close()

    sta = Status.NONE
    msg = ''

    killed = False

    # It would be nice to have a timeout with less polling, but apparently that's hard
    # http://mail.python.org/pipermail/python-bugs-list/2009-April/075008.html
    # http://bugs.python.org/issue5673
    # http://benjamin.smedbergs.us/blog/2006-11-09/adventures-in-python-launching-subprocesses/
    # http://benjamin.smedbergs.us/blog/2006-12-11/killableprocesspy/

    # This part is a bit like subprocess.communicate, but with a timeout
    while 1:
        rc = child.poll()
        elapsedtime = time.time() - starttime
        if rc is None:
            if elapsedtime > timeout and not killed:
                if progname == 'gdb':
                    raise Exception('Do not use this with gdb, because xpkill in timedRun will ' +
                                    'kill gdb but leave the process within gdb still running')
                xpkill(child)
                # but continue looping, because maybe kill takes a few seconds or maybe it's busy crashing!
                killed = True
            else:
                time.sleep(0.010)
        else:
            break

    if killed and (os.name != "posix" or rc == -signal.SIGKILL):
        msg = 'TIMED OUT'
        sta = Status.TIMEOUT
    elif rc == 0:
        msg = 'NORMAL'
        sta = Status.NORMAL
    elif rc == ASAN_EXIT_CODE:
        msg = 'CRASHED (Address Sanitizer fault)'
        sta = Status.CRASHED
    elif rc > 0:
        msg = 'ABNORMAL exit code ' + str(rc)
        sta = Status.ABNORMAL
    else:
        # rc < 0
        # The program was terminated by a signal, which usually indicates a crash.
        # Mac/Linux only!
        signum = -rc
        msg = 'CRASHED signal %d (%s)' % (signum, getSignalName(signum, "Unknown signal"))
        sta = Status.CRASHED

    if sta == Status.CRASHED:
        if sps.grabCrashLog(commandWithArgs[0], child.pid, logPrefix, True):
                with open(logPrefix + "-crash.txt") as f:
                    auxCrashData = [line.strip() for line in f.readlines()]

    if useLogFiles:
        # Am I supposed to do this?
        childStdOut.close()
        childStdErr.close()

    return rundata(
        sta,
        rc,
        msg,
        elapsedtime,
        killed,
        child.pid,
        logPrefix + "-out.txt" if useLogFiles else child.stdout.read(),
        logPrefix + "-err.txt" if useLogFiles else child.stderr.read()
    )

if __name__ == '__main__':
    rdata = timed_run(['./crash'], 5, 'a')
    print rdata
    rdata = timed_run(['ls', '-l'], 5, None)
    print rdata