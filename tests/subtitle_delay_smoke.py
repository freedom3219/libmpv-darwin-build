"""Exercise the actual libmpv decoder timeline with two external subtitles.

Run with DYLD_FRAMEWORK_PATH pointing at the packaged framework directory.
The first argument is the path to the Mpv framework binary.
An optional second argument selects ass or embedded fixtures (requires ffmpeg).
"""
import ctypes as ct
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time


def main():
    mpv = ct.CDLL(sys.argv[1])
    mpv.mpv_create.restype = ct.c_void_p
    mpv.mpv_initialize.argtypes = [ct.c_void_p]
    mpv.mpv_terminate_destroy.argtypes = [ct.c_void_p]
    mpv.mpv_free.argtypes = [ct.c_void_p]
    for name in ('mpv_set_property_string', 'mpv_set_option_string'):
        getattr(mpv, name).argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p]
    mpv.mpv_get_property_string.argtypes = [ct.c_void_p, ct.c_char_p]
    mpv.mpv_get_property_string.restype = ct.c_void_p
    mpv.mpv_command.argtypes = [ct.c_void_p, ct.POINTER(ct.c_char_p)]
    handle = mpv.mpv_create()
    assert handle

    def read(name):
        result = mpv.mpv_get_property_string(handle, name.encode())
        if not result:
            return None
        try:
            return ct.string_at(result).decode()
        finally:
            mpv.mpv_free(result)

    def write(name, value):
        result = mpv.mpv_set_property_string(handle, name.encode(), str(value).encode())
        assert result >= 0, (name, result)

    def command(*args):
        values = (ct.c_char_p * (len(args) + 1))(
            *[str(value).encode() for value in args], None
        )
        result = mpv.mpv_command(handle, values)
        assert result >= 0, (args, result)

    def until(predicate, description):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        raise AssertionError((description, read('time-pos'), read('sub-text'),
                              read('secondary-sub-text'), read('track-list')))

    try:
        for name, value in [('config', 'no'), ('vo', 'null'), ('ao', 'null'),
                            ('pause', 'yes'), ('idle', 'yes'), ('terminal', 'no')]:
            assert mpv.mpv_set_option_string(handle, name.encode(), value.encode()) >= 0
        assert mpv.mpv_initialize(handle) >= 0
        print('Native engine:', read('mpv-version'), flush=True)
        write('sub-delay', 1)
        write('secondary-sub-delay', -1)
        assert float(read('sub-delay')) == 1
        assert float(read('secondary-sub-delay')) == -1
        write('secondary-sub-delay', 0)
        assert float(read('sub-delay')) == 1
        write('secondary-sub-delay', -1)

        with tempfile.TemporaryDirectory(prefix='subtitle-delay-') as directory:
            root = Path(directory)
            video = root / 'timeline.y4m'
            # Six seconds of small, uncompressed video, without an ffmpeg dependency.
            video.write_bytes(b'YUV4MPEG2 W16 H16 F10:1 Ip A1:1 C420jpeg\n' +
                              (b'FRAME\n' + bytes([16] * 256 + [128] * 128)) * 60)
            for label in ['PRIMARY', 'SECONDARY']:
                (root / f'{label}.srt').write_text(
                    f'1\n00:00:02,000 --> 00:00:04,000\n{label}\n', encoding='utf-8')
            mode = sys.argv[2] if len(sys.argv) > 2 else 'srt'
            assert mode in ['srt', 'ass', 'embedded']
            if mode == 'embedded':
                embedded = root / 'timeline.mkv'
                subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video),
                                '-i', str(root / 'PRIMARY.srt'),
                                '-i', str(root / 'SECONDARY.srt'),
                                '-map', '0:v', '-map', '1:s', '-map', '2:s',
                                '-c:v', 'libx264', '-c:s', 'srt', str(embedded)], check=True)
                video = embedded
            elif mode == 'ass':
                for label in ['PRIMARY', 'SECONDARY']:
                    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(root / f'{label}.srt'),
                                    str(root / f'{label}.ass')], check=True)
            command('loadfile', video)
            until(lambda: read('time-pos') is not None, 'video loaded')
            if mode != 'embedded':
                command('sub-add', root / f'PRIMARY.{mode}', 'select')
                command('sub-add', root / f'SECONDARY.{mode}', 'auto')
            until(lambda: len([t for t in json.loads(read('track-list') or '[]')
                               if t['type'] == 'sub']) == 2, 'subtitles loaded')
            tracks = [t for t in json.loads(read('track-list')) if t['type'] == 'sub']
            write('sid', tracks[0]['id'])
            write('secondary-sid', tracks[1]['id'])

            def assert_text(position, primary, secondary):
                command('seek', position, 'absolute+exact')
                until(lambda: abs(float(read('time-pos') or '-100') - position) < 0.15
                      and (read('sub-text') or '').strip() == primary
                      and (read('secondary-sub-text') or '').strip() == secondary,
                      f'text at {position}: {primary!r}, {secondary!r}')

            # Original cue: [2, 4). Primary +1 => [3, 5); secondary -1 => [1, 3).
            assert_text(2.5, '', 'SECONDARY')
            assert_text(3.5, 'PRIMARY', '')
            write('secondary-sub-delay', 0)
            assert float(read('sub-delay')) == 1
            assert_text(3.5, 'PRIMARY', 'SECONDARY')
            write('sub-delay', -1)
            assert float(read('secondary-sub-delay')) == 0
            assert_text(3.5, '', 'SECONDARY')
            # Switching either slot off must not change the other's delay.
            write('sid', 'no')
            assert float(read('secondary-sub-delay')) == 0
            assert_text(2.5, '', 'SECONDARY')
        print(f'PASS ({mode}): independent properties, reset, paused seek and decoder timing.', flush=True)
    finally:
        mpv.mpv_terminate_destroy(handle)


if __name__ == '__main__':
    main()
