"""Offline test of speaking on the board's speaker, with a stand-in for
the sound server's TCP port (nothing is actually played).

  pip install espeakng-loader
  python3 test_speech.py
"""
import socket
import threading
import time

from speech import Speaker

failures = 0


def check(name, ok):
    global failures
    print(("ok   " if ok else "FAIL ") + name)
    failures += not ok


def fake_sound_server():
    """Listens like the simple-protocol module and keeps what it's sent."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen()
    got = []

    def serve():
        while True:
            conn, _ = srv.accept()
            data = b""
            while chunk := conn.recv(65536):
                data += chunk
            conn.close()
            if data:
                got.append(data)

    threading.Thread(target=serve, daemon=True).start()
    return srv.getsockname()[1], got


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# No sound server listening: say() says no at once, so the page reads aloud.
nobody = Speaker(port=free_port(), hosts=["127.0.0.1"])
check("no speaker: status says so", nobody.status() == "no speaker")
t = time.time()
check("no speaker: say() returns False quickly", nobody.say("hello") is False and time.time() - t < 0.5)

# A sound server: the speech arrives as raw 16-bit audio.
port, got = fake_sound_server()
speaker = Speaker(port=port, hosts=["10.255.255.1", "127.0.0.1"])   # first host unreachable
check("finds the sound server", speaker.status() == "ready" and speaker.host == "127.0.0.1")
check("say() returns True", speaker.say("Knight from g8 to f6, taking the pawn") is True)
end = time.time() + 15
while not got and time.time() < end:
    time.sleep(0.1)
seconds = len(got[0]) / 2 / speaker.engine.rate if got else 0
check(f"sent {seconds:.1f} s of speech", 2.5 < seconds < 6)
loud = got and sum(1 for i in range(0, len(got[0]) - 1, 2)
                   if abs(int.from_bytes(got[0][i:i + 2], "little", signed=True)) > 500)
check("and it isn't silence", loud and loud / speaker.engine.rate > 0.5)

# Messages are spoken one after another, in order.
speaker.say("one")
speaker.say("two, three, four, five")
end = time.time() + 15
while len(got) < 3 and time.time() < end:
    time.sleep(0.1)
check("queued messages all spoken, in order", len(got) == 3 and len(got[1]) < len(got[2]))

# Speech that won't load: reported, and the page takes over.
def broken():
    raise RuntimeError("espeak-ng didn't start")


bad = Speaker(port=port, hosts=["127.0.0.1"], engine=broken)
time.sleep(1)
check("speech that fails to load is reported", bad.status() == "no voice" and bad.say("hi") is False)

raise SystemExit(1 if failures else 0)
