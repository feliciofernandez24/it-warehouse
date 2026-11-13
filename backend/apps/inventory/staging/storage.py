"""POSIX-only, private, content-addressed file storage. No database persistence."""
import hashlib
import os
import secrets
import stat
from pathlib import Path

from .common import StagingError, canonical


def capture(preview, root, *, repository):
    """Create a private immutable-by-convention artifact; never overwrite.

    Caller owns a pre-created 0700 directory outside repository. A same-owner
    attacker can change files; every replay verifies bytes, not just the name.
    """
    if os.name != "posix":
        raise StagingError("POSIX_STORAGE_REQUIRED")
    root = Path(root)
    repository = Path(repository).resolve()
    if not root.is_absolute() or root.resolve() != root:
        raise StagingError("UNSAFE_STORAGE_ROOT")
    if root == repository or repository in root.parents:
        raise StagingError("STORAGE_INSIDE_REPOSITORY")
    payload = canonical(preview)
    key = hashlib.sha256(payload).hexdigest()
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    try:
        fd = os.open(root, flags)
    except OSError:
        raise StagingError("STORAGE_UNAVAILABLE") from None
    temp = None
    try:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise StagingError("INSECURE_STORAGE_PERMISSIONS")
        target = key + ".json"
        try:
            existing = os.open(target, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            with os.fdopen(existing, "rb") as stream:
                info = os.fstat(stream.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) != 0o400
                        or info.st_nlink != 1 or stream.read(len(payload) + 1) != payload):
                    raise StagingError("STORAGE_INTEGRITY_FAILURE")
            return key
        temp = ".capture-" + secrets.token_hex(16)
        out = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                      0o600, dir_fd=fd)
        with os.fdopen(out, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        try:
            # Atomic no-replace publication; concurrent equal captures are verified.
            os.link(temp, target, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        except FileExistsError:
            os.unlink(temp, dir_fd=fd)
            temp = None
            return capture(preview, root, repository=repository)
        os.unlink(temp, dir_fd=fd)
        temp = None
        os.fsync(fd)
        return key
    except StagingError:
        raise
    except OSError:
        raise StagingError("STORAGE_FAILURE") from None
    finally:
        if temp is not None:
            os.unlink(temp, dir_fd=fd)
        os.close(fd)
