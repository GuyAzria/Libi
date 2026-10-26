"""Windows-only test shim: homeassistant.util.resource raises the fd limit at startup; tests never call it."""
RLIMIT_NOFILE = 7

def getrlimit(_):
    return (2048, 2048)

def setrlimit(*a, **k):
    return None
