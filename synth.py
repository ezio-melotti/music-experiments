import wave

from contextlib import contextmanager
from functools import lru_cache, partial

import numpy as np
import soundcard as sc


SAMPLERATE = 44100  # default sample rate


def sine_wave(duration, frequency, ampl=1.0, samplerate=SAMPLERATE):
    frames = int(duration * samplerate)
    x = np.linspace(0, duration, frames)
    assert len(x) == frames
    return (0.5 * ampl) * np.sin(x * frequency * np.pi * 2)


def envelope(attack_time, decay_time, sustain_level, release_time, frames):
    assert isinstance(frames, int)
    attack_frames = int(frames * attack_time)
    decay_frames = int(frames * decay_time)
    release_frames = int(frames * release_time)
    sustain_frames = frames - attack_frames - decay_frames - release_frames
    return np.concatenate([
        np.linspace(0, 1, attack_frames),
        np.linspace(1, sustain_level, decay_frames),
        np.linspace(sustain_level, sustain_level, sustain_frames),
        np.linspace(sustain_level, 0, release_frames),
    ])


@lru_cache()
def play_tone(freq, duration, samplerate=SAMPLERATE):
    # # high freq att:
    # # 0.0 : 0.99 = 110 : 880
    # attenuation = min(max((freq - 110) / 770 * 0.99, 0.0), 0.99)
    # ampl = 1 - attenuation
    ampl = 0.5
    harmonics = [
        # (freqmult, amplmult)
        (1.0, 0.5),
        # (2.0, 0.2),
        # (4.0, 0.1),
        (1.01, 0.3),
        (0.2, 0.3),
        (0.5, 0.2),
        (0.25, 0.1),
    ]
    wave = sine_wave(duration, 0, 0)
    for fm, am in harmonics:
        wave += sine_wave(duration, freq * fm, ampl * am, samplerate)
    env = envelope(0.1, 0.2, 0.6, 0.2, len(wave))
    wave *= env
    return wave


@lru_cache()
def lowpass_noise(cutoff, duration, samplerate=SAMPLERATE):
    frames = int(duration*samplerate)

    print('generating some noise frames', frames)
    # # low pass filter implementation without fft
    # # len(convolution) = len(signal) + len(kernel) - 1
    # kernel_half_duration = 1
    # t = np.linspace(
    #     -kernel_half_duration,
    #     kernel_half_duration,
    #     2 * kernel_half_duration * samplerate
    # )
    # kernel = 2 * cutoff * np.sinc(2 * cutoff * t)

    noise = np.random.normal(0, 0.2, frames)
    print('fft...')
    fd_noise = np.fft.rfft(noise)
    freq = np.fft.rfftfreq(noise.size, d=1/samplerate)
    print(len(freq[freq < cutoff]))
    fd_noise[freq > cutoff] = 0
    noise = np.fft.irfft(fd_noise)
    # noise = np.convolve(noise, kernel)
    print('got some noise')
    return noise


@lru_cache()
def play_drum(duration, samplerate=SAMPLERATE):
    frames = int(duration*samplerate)
    some_noise = 48 * lowpass_noise(1000, 10.0, samplerate)
    noise = some_noise[:frames]
    env = envelope(0.01, 0.1, 0.1, 0.4, frames)
    wave = env * noise
    return wave


@lru_cache()
def play_drum2(duration, samplerate=SAMPLERATE):
    frames = int(duration*samplerate)
    wave = 0.2 * np.sign(sine_wave(duration, 20, 1, samplerate))

    some_noise = lowpass_noise(4000, 10.0, samplerate)
    noise = some_noise[:frames]
    wave += noise

    env = envelope(0.1, 0.1, 1, 0.7, frames)
    wave *= env
    return wave


@lru_cache()
def silence(duration, samplerate=SAMPLERATE):
    return np.zeros(int(duration*samplerate))


class Synth:
    def __init__(self, output):
        self.output = output

    def play(self, *args):
        self.play_mix(args)

    def play_mix(self, mix):
        wave = sum(np.concatenate(list(map(list, waves))) for waves in mix)
        self.output.play_wave(wave)

    def play_wave(self, wave):
        self.output.play_wave(wave)


class SoundcardOutput:
    def __init__(self, speaker):
        self.speaker = speaker

    def play_wave(self, wave):
        self.speaker.play(wave)


@contextmanager
def open_sc_stream(samplerate=SAMPLERATE):
    speaker = sc.default_speaker()
    print(speaker)
    with speaker.player(samplerate=samplerate) as player:
        # player.channels = [-1]
        yield SoundcardOutput(player)


class MyBuffer(bytearray):
    write = bytearray.extend


def _write_wav_file(filename, sample_rate, stream):
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.setnframes(len(stream))
        wf.writeframes(stream)


@contextmanager
def create_wav_file(filename, sample_rate=SAMPLERATE):
    stream = MyBuffer()
    yield Synth(stream)
    _write_wav_file(stream)


@contextmanager
def open_soundcard_synth(sample_rate=SAMPLERATE):
    with open_sc_stream() as stream:
        yield Synth(stream)


def run_synth(callable, output=None, **kwargs):
    if output is None:
        context_function = open_soundcard_synth
    elif isinstance(output, str):
        context_function = partial(create_wav_file, output)
    try:
        with context_function(**kwargs) as synth:
            callable(synth)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 2:
        module = sys.argv[1]
        run_synth(__import__(module).make_music)
