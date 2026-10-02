"""Speak the app's messages through a speaker on the UNO Q.

App Lab's container can't install programs or reach the board's sound
system directly, so:

* the speech is made in-process by espeak-ng, which comes as a pip package
  (espeakng-loader) with its library and voices: no apt, no root;
* it's played by the board's sound server (PipeWire or PulseAudio, where a
  Bluetooth speaker lives), which takes raw audio on a TCP port once its
  "simple protocol" module is loaded. See the README for the one-off setup.

    speaker = Speaker()
    speaker.say("Your move")      # True if the board's speaker will say it
"""
import ctypes
import os
import queue
import socket
import struct
import threading
import time

PORT = int(os.environ.get("SPEAKER_PORT", 4712))
VOICE = os.environ.get("SPEAKER_VOICE", "en")       # espeak-ng "en" is British English
SPEED = int(os.environ.get("SPEAKER_SPEED", 150))       # words per minute
RECHECK = 10                                             # seconds between looks for the speaker port

# espeak-ng's C API (speak_lib.h)
AUDIO_OUTPUT_SYNCHRONOUS = 2
POS_CHARACTER = 1
espeakCHARS_UTF8 = 1
espeakRATE = 1
SYNTH_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_short),
                                  ctypes.c_int, ctypes.c_void_p)


class Espeak:
    """espeak-ng turning text into 16-bit mono samples at self.rate Hz."""

    def __init__(self, voice=VOICE, speed=SPEED):
        import espeakng_loader
        self.lib = ctypes.cdll.LoadLibrary(espeakng_loader.get_library_path())
        data = espeakng_loader.get_data_path().encode()      # the bundled espeak-ng-data folder
        self.rate = self.lib.espeak_Initialize(AUDIO_OUTPUT_SYNCHRONOUS, 0, data, 0)
        if self.rate <= 0:
            raise RuntimeError("espeak-ng didn't start")
        if self.lib.espeak_SetVoiceByName(voice.encode()) != 0:
            raise RuntimeError(f"espeak-ng has no voice called {voice}")
        self.lib.espeak_SetParameter(espeakRATE, speed, 0)
        self._chunks = []
        self._lock = threading.Lock()
        self._callback = SYNTH_CALLBACK(self._collect)      # keep a reference while espeak holds it
        self.lib.espeak_SetSynthCallback(self._callback)

    def _collect(self, wav, n, events):
        if wav and n > 0:
            self._chunks.append(ctypes.string_at(wav, n * 2))
        return 0

    def pcm(self, text):
        """Raw signed 16-bit little-endian mono audio for text."""
        with self._lock:
            self._chunks = []
            data = text.encode("utf-8")
            self.lib.espeak_Synth(ctypes.c_char_p(data), len(data) + 1, 0, POS_CHARACTER, 0,
                                  espeakCHARS_UTF8, None, None)
            return b"".join(self._chunks)


_espeak = None
_espeak_lock = threading.Lock()


def shared_espeak():
    """espeak-ng keeps global state, so the whole app shares one."""
    global _espeak
    with _espeak_lock:
        if _espeak is None:
            _espeak = Espeak()
        return _espeak


def sound_server_hosts():
    """Where the board's sound server might be from inside the container:
    the container's gateway (the board itself), then this machine."""
    hosts = []
    if os.environ.get("SPEAKER_HOST"):
        hosts.append(os.environ["SPEAKER_HOST"])
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                fields = line.split()
                if fields[1] == "00000000" and int(fields[3], 16) & 2:   # default route via a gateway
                    hosts.append(socket.inet_ntoa(struct.pack("<L", int(fields[2], 16))))
    except (OSError, ValueError, IndexError):
        pass
    return hosts + ["127.0.0.1"]


class Speaker:
    """Speaks text on the board's speaker in a background thread, one
    message at a time. say() never blocks the game for long."""

    def __init__(self, port=PORT, hosts=None, engine=shared_espeak):
        self.port = port
        self.hosts = hosts or sound_server_hosts()
        self._engine_factory = engine
        self.engine = None
        self.error = None
        self.host = None
        self._checked = 0.0
        self._todo = queue.Queue(maxsize=20)
        threading.Thread(target=self._run, daemon=True).start()

    def _find_server(self):
        """The host whose speaker port is open, rechecked every RECHECK s."""
        if time.monotonic() - self._checked < RECHECK:
            return self.host
        self._checked = time.monotonic()
        self.host = None
        for host in self.hosts:
            try:
                socket.create_connection((host, self.port), timeout=0.3).close()
                self.host = host
                break
            except OSError:
                continue
        return self.host

    def status(self):
        """'ready', 'no speaker' (sound server port not open) or 'no voice'
        (espeak-ng didn't load)."""
        if self.error:
            return "no voice"
        return "ready" if self._find_server() else "no speaker"

    def say(self, text):
        if self.status() != "ready":
            return False
        try:
            self._todo.put_nowait(text)
            return True
        except queue.Full:
            return False

    def _run(self):
        try:
            self.engine = self._engine_factory()
        except Exception as e:
            self.error = str(e)
            return
        while True:
            text = self._todo.get()
            try:
                self._play(self.engine.pcm(text))
            except Exception as e:
                self._checked = 0.0                 # look for the speaker again next time
                print(f"Couldn't speak on the board: {e}", flush=True)

    def _play(self, pcm):
        """Stream the audio to the sound server, then half a second of
        silence so the end isn't cut off when the connection closes."""
        silence = b"\0\0" * (self.engine.rate // 2)
        with socket.create_connection((self.host or self.hosts[0], self.port), timeout=5) as s:
            s.sendall(pcm + silence)
            time.sleep(0.5)
