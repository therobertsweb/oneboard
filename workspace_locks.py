"""Reentrant, nonblocking locks shared by threads and server processes."""

import hashlib
import os
import threading
from contextlib import contextmanager

if os.name == "nt":
    import msvcrt
else:
    import fcntl

_held = threading.local()


@contextmanager
def process_lock(directory, key):
    os.makedirs(directory, mode=0o700, exist_ok=True)
    path = os.path.join(directory, hashlib.sha256(key.encode()).hexdigest() + ".lock")
    held = getattr(_held, "locks", None)
    if held is None:
        held = _held.locks = {}
    if path in held:
        yield
        return
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    acquired = False
    try:
        if os.name == "nt":
            if os.fstat(fd).st_size == 0:
                os.write(fd, b"0")
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        held[path] = fd
        yield
    finally:
        if acquired:
            held.pop(path, None)
            if os.name == "nt":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
