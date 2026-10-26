"""Windows-only test shim: homeassistant.runner imports fcntl for its lock file, which tests never use."""
LOCK_EX = LOCK_NB = LOCK_UN = 0

def flock(*a, **k):
    return None

def lockf(*a, **k):
    return None
