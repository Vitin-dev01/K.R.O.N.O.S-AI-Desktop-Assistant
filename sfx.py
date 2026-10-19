import numpy as np
import pygame

if not pygame.mixer.get_init():
    pygame.mixer.init()

def _make_tone(f_start, f_end, dur, vol=0.25, wave='sine'):
    sr = 44100
    n = int(sr * dur)
    freqs = np.linspace(f_start, f_end, n)
    phases = 2 * np.pi * np.cumsum(freqs) / sr
    
    if wave == 'sawtooth':
        w = 2 * (phases / (2 * np.pi) - np.floor(0.5 + phases / (2 * np.pi)))
    elif wave == 'triangle':
        w = 2 * np.abs(2 * (phases / (2 * np.pi) - np.floor(phases / (2 * np.pi) + 0.5))) - 1
    else:
        w = np.sin(phases)
        
    fade = np.linspace(1, 0, n) ** 2
    raw = (w * fade * vol * 32767).astype(np.int16)
    stereo = np.column_stack((raw, raw))
    return pygame.sndarray.make_sound(stereo)

SFX_STARTUP = _make_tone(180, 840, 0.50, vol=0.28, wave='sine')
SFX_WAKE = _make_tone(420, 920, 0.12, vol=0.22, wave='sine')
SFX_CONFIRM = _make_tone(580, 880, 0.18, vol=0.20, wave='triangle')

def play_sfx(name: str):
    try:
        if name == 'startup':
            SFX_STARTUP.play()
        elif name == 'wake':
            SFX_WAKE.play()
        elif name == 'confirm':
            SFX_CONFIRM.play()
    except Exception:
        pass