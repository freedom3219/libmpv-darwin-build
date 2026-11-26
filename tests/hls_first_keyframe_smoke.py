"""Test the packaged libmpv against two fMP4 HLS time bases.

Set DYLD_FRAMEWORK_PATH to the bundle's Contents/Frameworks and pass its
Mpv.framework/Mpv as the argument. Fixtures require ffmpeg with libx264.
"""
import ctypes as ct
import functools
import http.server
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def make_fixture(root, rate):
    root.mkdir()
    for track, source, codec in [
        ("video", f"color=s=64x64:r={rate}", ["-c:v", "libx264", "-bf", "2", "-g", "194"]),
        ("audio", "anullsrc=r=48000:cl=mono", ["-c:a", "aac"]),
    ]:
        subprocess.run([
            "ffmpeg", "-v", "error", "-f", "lavfi", "-i", source, "-t", "22",
            *codec, "-hls_time", "16", "-hls_segment_type", "fmp4",
            "-hls_fmp4_init_filename", f"{track}.mp4",
            "-hls_segment_filename", f"{track}%d.m4s", f"{track}.m3u8",
        ], cwd=root, check=True)
    master = root / "index.m3u8"
    master.write_text(
        '#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=16000,AUDIO="a"\nvideo.m3u8\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="a",NAME="Audio",DEFAULT=YES,URI="audio.m3u8"\n'
    )
    return master


def check(mpv, uri):
    handle = mpv.mpv_create()
    if not handle:
        raise RuntimeError("mpv_create failed")

    def read(name):
        ptr = mpv.mpv_get_property_string(handle, name.encode())
        if ptr is None:
            return None
        try:
            return ct.string_at(ptr).decode()
        finally:
            mpv.mpv_free(ptr)

    def command(*args):
        values = (ct.c_char_p * (len(args) + 1))(*(str(arg).encode() for arg in args), None)
        if mpv.mpv_command(handle, values) < 0:
            raise RuntimeError(args)

    def until(predicate, description):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        raise AssertionError(f"{uri}: {description}; time-pos={read('time-pos')}")

    def at(target):
        until(lambda: read("seeking") == "no" and
              abs(float(read("time-pos") or "-100") - target) < 0.15, f"expected {target}s")

    try:
        for name, value in {
            "config": "no", "vo": "null", "ao": "null", "pause": "yes",
            "keep-open": "yes", "start": "0", "cache": "no",
        }.items():
            if mpv.mpv_set_option_string(handle, name.encode(), value.encode()) < 0:
                raise RuntimeError(name)
        if mpv.mpv_initialize(handle) < 0:
            raise RuntimeError("mpv_initialize failed")
        command("loadfile", uri)
        until(lambda: read("video-out-params/w") == "64", "first frame")
        at(0)
        aid = read("aid")
        assert read("audio-codec-name") == "aac" and aid
        for target in [18, 0, 3, 7, 9, 18, 21]:
            command("seek", target, "absolute+exact")
            at(target)
        command("set", "pause", "no")
        until(lambda: read("eof-reached") == "yes", "natural EOF")
        command("seek", 0, "absolute")
        command("set", "pause", "no")
        until(lambda: 0.1 < float(read("time-pos") or "-1") < 1 and read("pause") == "no",
              "advancing in first second after EOF")
        assert read("aid") == aid
    finally:
        mpv.mpv_terminate_destroy(handle)


def main():
    mpv = ct.CDLL(sys.argv[1])
    mpv.mpv_create.restype = ct.c_void_p
    mpv.mpv_get_property_string.restype = ct.c_void_p
    mpv.mpv_get_property_string.argtypes = [ct.c_void_p, ct.c_char_p]
    mpv.mpv_set_option_string.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p]
    mpv.mpv_command.argtypes = [ct.c_void_p, ct.POINTER(ct.c_char_p)]
    for name in ["mpv_free", "mpv_initialize", "mpv_terminate_destroy"]:
        getattr(mpv, name).argtypes = [ct.c_void_p]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=tmp)
        with http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                for rate, name in [("24000/1001", "control"), ("1199/50", "rounding")]:
                    master = make_fixture(root / name, rate)
                    for uri in [str(master), f"http://127.0.0.1:{server.server_port}/{name}/index.m3u8"]:
                        check(mpv, uri)
                        print(f"PASS: {uri}", flush=True)
            finally:
                server.shutdown()
                thread.join()


if __name__ == "__main__":
    main()
