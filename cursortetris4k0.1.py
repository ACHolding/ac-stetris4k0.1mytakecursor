"""AC's Tetris My Take v0.1 — single-file pygame (files=off). Game Boy @ 60 FPS.

Main menu • Play / Help / Sound Settings / Exit. P pause to menu, R reset run.
Full Korobeiniki OST — procedural GB chiptune via math, files=off.
"""
import array
import math
import random

import pygame

# ---------------- CONFIG ----------------
WIDTH, HEIGHT = 600, 400
FPS = 60

COLS, ROWS = 10, 20
BLOCK = 18

PLAY_W = COLS * BLOCK
PLAY_H = ROWS * BLOCK

TOP_X = (WIDTH - PLAY_W) // 2
TOP_Y = (HEIGHT - PLAY_H) // 2

# Game Boy Tetris gravity — ROM table (Tetris Wiki), scaled from 59.73 Hz → 60 FPS
GB_REFRESH = 59.7275
GB_GRAVITY_ROM = (
    53, 49, 45, 41, 37, 33, 28, 22, 17, 11,
    10, 9, 8, 7, 6, 6, 5, 5, 4, 4, 3,
)
GB_BG = (155, 188, 15)
GB_GRID = (48, 98, 48)
GB_INK = (15, 56, 15)

SAMPLE_RATE = 22050
_KORO_BPM = 132
_BEAT_SEC = 60.0 / _KORO_BPM
_DUR = {"w": 4.0, "h": 2.0, "q": 1.0, "e": 0.5, "s": 0.25}

# Full Korobeiniki (Коробейники) — Russian folk song / Tetris theme, MuseScore-style layout
# Tokens: NOTE + duration letter (w h q e s) or rest (.q .e …). No MIDI — pure Python.
_KORO_SCORE = """
E5h B4e C5e D5h C5e B4e A4h A4h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4e A4h
E5h B4e C5e D5h C5e B4e A4h A4h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4e A4h
D5h F5e A5e A5h G5e F5e E5h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4e A4h
D5h F5e A5e A5h G5e F5e E5h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4e A4h
E5h B4e C5e D5h C5e B4e A4h A4h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4e A4h
E5h C5e D5e B4e C5e A4e Ab4e B4h E5h C5e D5e B4e C5e E5h A4e Ab4e Ab4h
C5h E5e A5e A5h G5e F5e G5e A5e B5h C6h B5e A5e G5e E5e G5e E5h C5h
A4h E4e C5e A4h B4e G4e A4h E4e C5e D5h B4e G4e C5h A4e F4e D5h B4e G4e G4h
E5h B4e C5e D5h C5e B4e A4h A4h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4e A4h
D5h F5e A5e A5h G5e F5e E5h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4e A4h
E4h G4e B4e C5h B4e A4e G4h E4e C5e D5h B4e A4e A4h E4e Ab4e B4h
C5h E5e A5e G5e F5e E5h C5e E5e D5h C5e B4q C5e D5e E5h C5e A4q A4h
E5e B4e C5e D5e C5e B4e A4q E5e B4e C5e D5e C5e B4e A4e
E5e B4e C5e D5s C5s B4s B4s A4e A4e A4q A4w
"""

_PITCH = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "F": 5,
    "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}
_HARMONY = {
    "E5": "B4", "B4": "G#4", "C5": "A4", "D5": "B4", "A4": "E4", "F5": "A4",
    "A5": "C5", "G5": "B4", "E4": "B3", "G4": "D4", "Ab4": "E4", "C6": "G5",
    "B5": "G4", "D5": "B4", "F4": "A3",
}
_BASS_ROOT = {
    "E": ("E1", "E2"), "B": ("B0", "B1"), "C": ("C1", "C2"), "D": ("D1", "D2"),
    "A": ("A1", "A2"), "F": ("F1", "F2"), "G": ("G1", "G2"), "Ab": ("G#1", "G#2"),
}


def _note_midi(name: str) -> int:
    if len(name) == 2:
        pitch, octave = name[0], int(name[1])
    else:
        pitch, octave = name[:2], int(name[2])
    return (octave + 1) * 12 + _PITCH[pitch]


def _note_hz(name: str) -> float:
    return 440.0 * math.pow(2.0, (_note_midi(name) - 69) / 12.0)


def _midi_name(n: int) -> str:
    names = "C C# D D# E F F# G G# A A# B".split()
    return f"{names[n % 12]}{n // 12 - 1}"


def _parse_token(tok: str) -> tuple[float, str | None]:
    if tok[0] == ".":
        return _DUR[tok[1]] * _BEAT_SEC, None
    return _DUR[tok[-1]] * _BEAT_SEC, tok[:-1]


def _harmony(note: str | None) -> str | None:
    if not note:
        return None
    if note in _HARMONY:
        return _HARMONY[note]
    low = _midi_name(_note_midi(note) - 7)
    return low if _note_midi(low) >= 55 else None


def _bass(note: str | None, flip: int) -> str | None:
    if not note:
        return None
    root = note[0] if note[1] != "#" and note[1] != "b" else note[:2]
    pair = _BASS_ROOT.get(root)
    if not pair:
        return _midi_name(max(28, _note_midi(note) - 36))
    return pair[flip % 2]


def _build_korobeiniki_segments() -> list[tuple[float, str | None, str | None, str | None]]:
    segs: list[tuple[float, str | None, str | None, str | None]] = []
    bass_flip = 0
    for tok in _KORO_SCORE.split():
        dur, note = _parse_token(tok)
        har = _harmony(note)
        bas = _bass(note, bass_flip)
        if note:
            bass_flip += 1
        segs.append((dur, note, har, bas))
    return segs


_KORO_SEGMENTS = _build_korobeiniki_segments()


def _gb_square(freq: float, t: float, duty: float) -> float:
    if freq <= 0.0:
        return 0.0
    return 1.0 if (freq * t) % 1.0 < duty else -1.0


def _gb_triangle(freq: float, t: float) -> float:
    if freq <= 0.0:
        return 0.0
    x = (freq * t) % 1.0
    return 4.0 * abs(x - 0.5) - 1.0


def _gb_envelope(t: float, duration: float) -> float:
    attack = min(1.0, t * 180.0)
    release = min(1.0, (duration - t) * 100.0)
    return min(attack, release)


def _render_ost_seg(sq1: str | None, sq2: str | None, wave: str | None, duration: float) -> array.array:
    n = max(1, int(SAMPLE_RATE * duration))
    buf = array.array("h")
    f1 = _note_hz(sq1) if sq1 else 0.0
    f2 = _note_hz(sq2) if sq2 else 0.0
    fw = _note_hz(wave) if wave else 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        env = _gb_envelope(t, duration)
        m1 = _gb_square(f1, t, 0.125) * 0.24
        m2 = _gb_square(f2, t, 0.25) * 0.16
        wv = _gb_triangle(fw, t) * 0.28
        sample = (m1 + m2 + wv) * env
        buf.append(int(max(-32767, min(32767, sample * 32767))))
    return buf


def _mono_to_stereo(mono: array.array) -> array.array:
    """pygame-ce treats raw buffers as stereo interleaved — duplicate L/R or playback runs 2x."""
    stereo = array.array("h")
    for sample in mono:
        stereo.append(sample)
        stereo.append(sample)
    return stereo


def _samples_to_sound(mono: array.array) -> pygame.mixer.Sound:
    return pygame.mixer.Sound(buffer=_mono_to_stereo(mono))


def _build_ost_sound() -> pygame.mixer.Sound:
    parts = [_render_ost_seg(s1, s2, w, d) for d, s1, s2, w in _KORO_SEGMENTS]
    total = sum(len(p) for p in parts)
    mixed = array.array("h", [0] * total)
    pos = 0
    for part in parts:
        mixed[pos : pos + len(part)] = part
        pos += len(part)
    return _samples_to_sound(mixed)


class TetrisOstPlayer:
    """Full Korobeiniki — sq1 melody + sq2 harmony + wave bass, procedural math synthesis."""

    def __init__(self) -> None:
        self._play = False
        self._ost = _build_ost_sound()
        self._ch = pygame.mixer.Channel(0)
        self._lock = _samples_to_sound(_render_ost_seg("E5", "B4", "E1", 0.05))

    def lock_blip(self, enabled: bool = True) -> None:
        if not enabled:
            return
        try:
            pygame.mixer.Channel(1).play(self._lock)
        except Exception:
            pass

    def start(self, enabled: bool = True) -> None:
        if not enabled:
            self.stop()
            return
        if self._play:
            return
        self._play = True
        self._ch.play(self._ost, loops=-1)

    def stop(self) -> None:
        self._play = False
        self._ch.stop()

# ---------------- SHAPES ----------------
S = [['.....',
      '.....',
      '..00.',
      '.00..',
      '.....'],
     ['.....',
      '..0..',
      '..00.',
      '...0.',
      '.....']]

Z = [['.....',
      '.....',
      '.00..',
      '..00.',
      '.....'],
     ['.....',
      '..0..',
      '.00..',
      '.0...',
      '.....']]

I = [['..0..',
      '..0..',
      '..0..',
      '..0..',
      '.....'],
     ['.....',
      '0000.',
      '.....',
      '.....',
      '.....']]

O = [['.....',
      '.....',
      '.00..',
      '.00..',
      '.....']]

J = [['.....',
      '.0...',
      '.000.',
      '.....',
      '.....'],
     ['.....',
      '..00.',
      '..0..',
      '..0..',
      '.....'],
     ['.....',
      '.....',
      '.000.',
      '...0.',
      '.....'],
     ['.....',
      '..0..',
      '..0..',
      '.00..',
      '.....']]

L = [['.....',
      '...0.',
      '.000.',
      '.....',
      '.....'],
     ['.....',
      '..0..',
      '..0..',
      '..00.',
      '.....'],
     ['.....',
      '.....',
      '.000.',
      '.0...',
      '.....'],
     ['.....',
      '.00..',
      '..0..',
      '..0..',
      '.....']]

T = [['.....',
      '..0..',
      '.000.',
      '.....',
      '.....'],
     ['.....',
      '..0..',
      '..00.',
      '..0..',
      '.....'],
     ['.....',
      '.....',
      '.000.',
      '..0..',
      '.....'],
     ['.....',
      '..0..',
      '.00..',
      '..0..',
      '.....']]

SHAPES = [S, Z, I, O, J, L, T]
COLORS = [(0,255,0),(255,0,0),(0,255,255),(255,255,0),
          (255,165,0),(0,0,255),(128,0,128)]

# ---------------- PIECE ----------------
class Piece:
    def __init__(self, x, y, shape):
        self.x = x
        self.y = y
        self.shape = shape
        self.color = COLORS[SHAPES.index(shape)]
        self.rotation = 0

# ---------------- GRID ----------------
def create_grid(locked):
    grid = [[(0,0,0) for _ in range(COLS)] for _ in range(ROWS)]
    for y in range(ROWS):
        for x in range(COLS):
            if (x, y) in locked:
                grid[y][x] = locked[(x, y)]
    return grid

def convert_shape_format(piece):
    positions = []
    shape = piece.shape[piece.rotation % len(piece.shape)]
    for i, line in enumerate(shape):
        row = list(line)
        for j, col in enumerate(row):
            if col == '0':
                positions.append((piece.x + j - 2, piece.y + i - 4))
    return positions

def valid_space(piece, grid):
    accepted = [[(j, i) for j in range(COLS) if grid[i][j] == (0,0,0)] for i in range(ROWS)]
    accepted = [j for sub in accepted for j in sub]

    formatted = convert_shape_format(piece)

    for pos in formatted:
        if pos not in accepted:
            if pos[1] > -1:
                return False
    return True

def check_lost(positions):
    for pos in positions:
        x, y = pos
        if y < 1:
            return True
    return False

def clear_rows(grid, locked):
    inc = 0
    for i in range(ROWS-1, -1, -1):
        row = grid[i]
        if (0,0,0) not in row:
            inc += 1
            ind = i
            for j in range(COLS):
                try:
                    del locked[(j, i)]
                except:
                    pass

    if inc > 0:
        for key in sorted(list(locked), key=lambda x: x[1])[::-1]:
            x, y = key
            if y < ind:
                new_key = (x, y + inc)
                locked[new_key] = locked.pop(key)

    return inc

def draw_grid(surface, grid):
    for i in range(ROWS):
        for j in range(COLS):
            c = grid[i][j]
            if c == (0, 0, 0):
                c = GB_INK
            pygame.draw.rect(surface, c, (TOP_X + j * BLOCK, TOP_Y + i * BLOCK, BLOCK, BLOCK), 0)
            if grid[i][j] != (0, 0, 0):
                pygame.draw.rect(surface, (255, 255, 255), (TOP_X + j * BLOCK + 2, TOP_Y + i * BLOCK + 2, 4, 4))

    for i in range(ROWS):
        pygame.draw.line(surface, GB_GRID, (TOP_X, TOP_Y + i * BLOCK), (TOP_X + PLAY_W, TOP_Y + i * BLOCK))
    for j in range(COLS):
        pygame.draw.line(surface, GB_GRID, (TOP_X + j * BLOCK, TOP_Y), (TOP_X + j * BLOCK, TOP_Y + PLAY_H))

def draw_window(surface, grid, score=0, level=1, lines=0):
    surface.fill(GB_BG)
    draw_grid(surface, grid)

    font = pygame.font.SysFont("consolas", 20, bold=True)
    surface.blit(font.render(f"SCORE {score}", True, GB_INK), (20, 16))
    surface.blit(font.render(f"LV {level}", True, GB_INK), (20, 40))
    surface.blit(font.render(f"LINE {lines}", True, GB_INK), (20, 64))

MENU_OPTIONS = (
    "PLAY GAME",
    "EXIT GAME",
    "HELP",
    "SOUND SETTINGS",
    "EXIT",
)

_LOGO_BLOCKS = (
    ((0, 0), (1, 0), (0, 1), (1, 1), (48, 120, 48)),
    ((0, 0), (1, 0), (1, 1), (2, 1), (15, 56, 15)),
    ((0, 0), (0, 1), (0, 2), (0, 3), (48, 98, 48)),
    ((0, 0), (1, 0), (2, 0), (1, 1), (15, 56, 15)),
)


def _draw_logo_blocks(surface, cx: int, cy: int) -> None:
    size = 10
    gap = 4
    shapes = _LOGO_BLOCKS
    total_w = len(shapes) * (2 * size + gap) - gap
    x0 = cx - total_w // 2
    for si, shape in enumerate(shapes):
        ox = x0 + si * (2 * size + gap)
        color = shape[-1]
        for dx, dy in shape[:-1]:
            pygame.draw.rect(surface, color, (ox + dx * size, cy + dy * size, size - 1, size - 1))


def draw_menu_logo(surface) -> None:
    surface.fill(GB_BG)
    _draw_logo_blocks(surface, WIDTH // 2, 28)

    title_font = pygame.font.SysFont("consolas", 34, bold=True)
    sub_font = pygame.font.SysFont("consolas", 20, bold=True)
    tag_font = pygame.font.SysFont("consolas", 16)

    title = title_font.render("AC'S TETRIS", True, GB_INK)
    surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 58))
    take = sub_font.render("MY TAKE v0.1", True, GB_GRID)
    surface.blit(take, (WIDTH // 2 - take.get_width() // 2, 96))
    tag = tag_font.render("GAME BOY STYLE • FILES=OFF", True, GB_GRID)
    surface.blit(tag, (WIDTH // 2 - tag.get_width() // 2, 122))


def draw_main_menu(surface, selected: int) -> None:
    draw_menu_logo(surface)
    menu_font = pygame.font.SysFont("consolas", 22, bold=True)
    for i, opt in enumerate(MENU_OPTIONS):
        color = GB_INK if i == selected else GB_GRID
        prefix = "> " if i == selected else "  "
        text = menu_font.render(prefix + opt, True, color)
        surface.blit(text, (WIDTH // 2 - text.get_width() // 2, 158 + i * 34))

    hint = pygame.font.SysFont("consolas", 16).render("↑↓ SELECT   ENTER CONFIRM", True, (140, 140, 160))
    surface.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 36))


def draw_help_screen(surface) -> None:
    surface.fill(GB_BG)
    title = pygame.font.SysFont("consolas", 28, bold=True).render("HELP", True, GB_INK)
    surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 24))
    body_font = pygame.font.SysFont("consolas", 17)
    lines = (
        "GOAL: Clear lines by filling rows.",
        "SCORE: +10 per block, +100 per line.",
        "LEVEL: Up every 10 lines (faster drop).",
        "",
        "← →  MOVE PIECE",
        "↑     ROTATE",
        "↓     SOFT DROP",
        "P     PAUSE → MAIN MENU",
        "R     RESET RUN",
        "",
        "ESC / ENTER  BACK TO MENU",
    )
    for i, line in enumerate(lines):
        if line:
            surface.blit(body_font.render(line, True, GB_INK if i < 4 else GB_GRID), (48, 68 + i * 22))


def draw_sound_screen(surface, music_on: bool, sfx_on: bool, selected: int) -> None:
    surface.fill(GB_BG)
    title = pygame.font.SysFont("consolas", 28, bold=True).render("SOUND SETTINGS", True, GB_INK)
    surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 40))

    opts = (
        f"MUSIC: {'ON' if music_on else 'OFF'}",
        f"SFX:   {'ON' if sfx_on else 'OFF'}",
        "BACK",
    )
    font = pygame.font.SysFont("consolas", 24, bold=True)
    for i, opt in enumerate(opts):
        color = GB_INK if i == selected else GB_GRID
        prefix = "> " if i == selected else "  "
        surface.blit(font.render(prefix + opt, True, color), (WIDTH // 2 - 90, 130 + i * 44))

    hint = pygame.font.SysFont("consolas", 16).render("←→ TOGGLE   ↑↓ SELECT   ENTER", True, (140, 140, 160))
    surface.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 36))

# ---------------- GAME ----------------
def new_pieces():
    cur = Piece(5, 0, random.choice(SHAPES))
    nxt = Piece(5, 0, random.choice(SHAPES))
    return cur, nxt

def main():
    pygame.init()
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
    win = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("AC's Tetris My Take v0.1")

    clock = pygame.time.Clock()
    music = TetrisOstPlayer()

    screen = "main"  # main | help | sound | play
    selected = 0
    sound_sel = 0
    music_on = True
    sfx_on = True

    locked_positions = {}
    grid = create_grid(locked_positions)

    change_piece = False
    run_game = True
    current_piece, next_piece = new_pieces()

    fall_time = 0
    score = 0
    level = 1
    lines_cleared = 0

    def gravity_frames() -> int:
        idx = min(level - 1, len(GB_GRAVITY_ROM) - 1)
        return max(1, round(GB_GRAVITY_ROM[idx] * FPS / GB_REFRESH))

    def reset_run() -> None:
        nonlocal locked_positions, grid, current_piece, next_piece
        nonlocal change_piece, fall_time, score, level, lines_cleared, screen
        locked_positions = {}
        grid = create_grid(locked_positions)
        current_piece, next_piece = new_pieces()
        change_piece = False
        fall_time = 0
        score = 0
        level = 1
        lines_cleared = 0
        screen = "play"
        music.stop()
        music.start(music_on)

    def to_main_menu() -> None:
        nonlocal screen, selected
        music.stop()
        screen = "main"
        selected = 0

    while run_game:
        clock.tick(FPS)

        if screen == "main":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    run_game = False
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        selected = (selected - 1) % len(MENU_OPTIONS)
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        selected = (selected + 1) % len(MENU_OPTIONS)
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        choice = MENU_OPTIONS[selected]
                        if choice == "PLAY GAME":
                            reset_run()
                        elif choice in ("EXIT GAME", "EXIT"):
                            run_game = False
                        elif choice == "HELP":
                            screen = "help"
                        elif choice == "SOUND SETTINGS":
                            screen = "sound"
                            sound_sel = 0

            draw_main_menu(win, selected)
            pygame.display.update()
            continue

        if screen == "help":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    run_game = False
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_BACKSPACE):
                        to_main_menu()
            draw_help_screen(win)
            pygame.display.update()
            continue

        if screen == "sound":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    run_game = False
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        sound_sel = (sound_sel - 1) % 3
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        sound_sel = (sound_sel + 1) % 3
                    if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                        if sound_sel == 0:
                            music_on = not music_on
                        elif sound_sel == 1:
                            sfx_on = not sfx_on
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if sound_sel == 2:
                            to_main_menu()
                        elif sound_sel == 0:
                            music_on = not music_on
                        elif sound_sel == 1:
                            sfx_on = not sfx_on
                    if event.key == pygame.K_ESCAPE:
                        to_main_menu()
            draw_sound_screen(win, music_on, sfx_on, sound_sel)
            pygame.display.update()
            continue

        grid = create_grid(locked_positions)

        fall_time += 1
        if fall_time >= gravity_frames():
            fall_time = 0
            current_piece.y += 1
            if not valid_space(current_piece, grid):
                current_piece.y -= 1
                change_piece = True

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                run_game = False

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_p:
                    to_main_menu()
                if event.key == pygame.K_r:
                    music.stop()
                    reset_run()
                if event.key == pygame.K_LEFT:
                    current_piece.x -= 1
                    if not valid_space(current_piece, grid):
                        current_piece.x += 1

                if event.key == pygame.K_RIGHT:
                    current_piece.x += 1
                    if not valid_space(current_piece, grid):
                        current_piece.x -= 1

                if event.key == pygame.K_DOWN:
                    current_piece.y += 1
                    if not valid_space(current_piece, grid):
                        current_piece.y -= 1

                if event.key == pygame.K_UP:
                    current_piece.rotation += 1
                    if not valid_space(current_piece, grid):
                        current_piece.rotation -= 1

        shape_pos = convert_shape_format(current_piece)

        for pos in shape_pos:
            x, y = pos
            if y > -1:
                grid[y][x] = current_piece.color

        if change_piece:
            landed = 0
            for pos in shape_pos:
                if pos[1] > -1:
                    locked_positions[(pos[0], pos[1])] = current_piece.color
                    landed += 1
            score += landed * 10
            music.lock_blip(sfx_on)
            current_piece = next_piece
            next_piece = Piece(5, 0, random.choice(SHAPES))
            change_piece = False
            grid = create_grid(locked_positions)
            cleared = clear_rows(grid, locked_positions)
            score += cleared * 100
            lines_cleared += cleared
            if cleared:
                level = 1 + lines_cleared // 10

            if check_lost(locked_positions):
                to_main_menu()
                locked_positions = {}
                score = 0
                level = 1
                lines_cleared = 0
                current_piece, next_piece = new_pieces()
                change_piece = False

        draw_window(win, grid, score, level, lines_cleared)
        pygame.display.update()

    music.stop()
    pygame.quit()

if __name__ == "__main__":
    main()