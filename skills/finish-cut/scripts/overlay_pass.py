#!/usr/bin/env python3
"""overlay_pass.py: the FINISH pass for a chapter that already has a final cut with audio.

It overlays comic speech bubbles, caption boxes and designed transitions on the existing final picture and changes
neither its length nor its audio. Standard library only, no network (except `run-local`, which downloads job inputs), no credits: it writes
`run_ffmpeg` job JSONs, you run them with the Frameo `run_ffmpeg` tool (or locally with `run-local`).

JOB is the job folder (relay.json, speech_urls.json, jobs/starts.json, cut_final.json, face_boxes.json). Everything is
written under JOB/finish/.

  overlay_pass.py ht-jobs  JOB [--size WxH]            8 halftone-wipe clip jobs (once per frame size; reusable by every chapter)
  overlay_pass.py sheet    JOB [--per-sheet 3]         face contact-sheet jobs: 2 frames per shot with a 100 px grid, to read face boxes from
  overlay_pass.py plan     JOB [options]               bubbles + captions (ASS), halftone and zoom/fade schedule, overlay part jobs
  overlay_pass.py window   JOB START END               one short proof job for any time window (view the result with view_image)
  overlay_pass.py outputs  JOB name=URL ...            remember links run_ffmpeg returned (ht_LR=..., ov01=...)
  overlay_pass.py join     JOB                         join job: concat the overlay parts (stream copy) + the ORIGINAL audio (stream copy)
  overlay_pass.py record   JOB URL                     write JOB/cut_finish.json
  overlay_pass.py measure  JOB [--ffmpeg PATH]         local only: find the real cut frames of the final and report drift vs starts.json
  overlay_pass.py run-local JOBFILE [--workdir D]      run job JSONs with a local ffmpeg (fallback and test harness)

Read `references/overlay-pass.md` for file formats and the order of steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import halftone_transition as ht  # noqa: E402

BS = "\\"
DIRS = list(ht.DIRS)


class OverlayError(Exception):
    pass


# ------------------------------------------------------------------ small io helpers
def read_json(path, default=None):
    if not os.path.isfile(path):
        if default is not None:
            return default
        raise OverlayError("missing file: " + path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise OverlayError("%s is not valid JSON: %s" % (path, exc))


def write_json(path, data, **kw):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, **kw)


def write_text(path, text):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# ------------------------------------------------------------------ font metrics (DejaVu Sans Bold, advance / 2048 em)
_ADV = {
    " ": 713, "!": 821, '"': 989, "#": 1716, "$": 1397, "%": 2052, "&": 1749, "'": 568, "(": 855, ")": 855, "*": 1237,
    "+": 1716, ",": 758, "-": 850, ".": 758, "/": 799, "0": 1405, "1": 1405, "2": 1405, "3": 1405, "4": 1405, "5": 1405,
    "6": 1405, "7": 1405, "8": 1405, "9": 1405, ":": 856, ";": 856, "<": 1716, "=": 1716, ">": 1716, "?": 1264, "@": 1948,
    "A": 1585, "B": 1561, "C": 1530, "D": 1739, "E": 1415, "F": 1397, "G": 1739, "H": 1749, "I": 749, "J": 749, "K": 1587,
    "L": 1286, "M": 2024, "N": 1739, "O": 1778, "P": 1475, "Q": 1778, "R": 1620, "S": 1479, "T": 1432, "U": 1698, "V": 1585,
    "W": 2253, "X": 1585, "Y": 1432, "Z": 1491, "[": 855, "\\": 799, "]": 855, "^": 1716, "_": 1024, "`": 1024, "a": 1382,
    "b": 1466, "c": 1219, "d": 1466, "e": 1389, "f": 889, "g": 1466, "h": 1458, "i": 702, "j": 774, "k": 1409, "l": 702,
    "m": 2097, "n": 1458, "o": 1409, "p": 1466, "q": 1466, "r": 998, "s": 1219, "t": 979, "u": 1458, "v": 1356, "w": 1948,
    "x": 1350, "y": 1356, "z": 1212, "{": 1479, "|": 799, "}": 1479, "~": 1716, "’": 568, "‘": 568,
    "“": 989, "”": 989, "—": 2048, "–": 1024, "…": 2048,
}
CELL = 2384.0  # ascent + descent of DejaVu Sans Bold in font units; libass sizes a font by that cell height


def text_w(s, fs, scale=1.0):
    return sum(_ADV.get(ch, 1300) for ch in s) * fs / CELL * 1.03 * scale


def wrap_text(text, fs, maxw, scale=1.0):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w) if cur else w
        if cur and text_w(t, fs, scale) > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines or [text]


def fix_text(s):
    """Repair UTF-8 that was read as cp1252 (an em dash shows up as the three characters a-circumflex, euro, quote)."""
    if "â€" in s or "Ã" in s:
        try:
            return s.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


def ass_escape(s):
    return s.replace(BS, "/").replace("{", "(").replace("}", ")")


# ------------------------------------------------------------------ speakers
PALETTE = ["#D6336C", "#1C6FD1", "#E8590C", "#0B8F7A", "#7048E8", "#2B8A3E", "#C92A2A", "#B8860B", "#0C8599", "#862E9C"]


def hex_bgr(h):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "&H00%02X%02X%02X" % (b, g, r)


def tint(h, k=0.28):
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#%02X%02X%02X" % tuple(int(255 - (255 - c) * k) for c in (r, g, b))


def speaker_table(relay, given):
    """id -> {tag, color}. Names come from the character locks ('Neha Kapoor: ...' -> NEHA); colours from `speakers.json`
    when present, else a stable hash into the palette so the same id gets the same colour in every chapter."""
    out = {}
    for it in relay.get("locks", {}).get("items", []):
        if it.get("kind") == "character":
            if "variant_of" in it:
                continue
            nm = (it.get("description") or it["id"]).split(":")[0].split()[0] if it.get("description") else it["id"]
            out[it["id"]] = {"tag": re.sub(r"[^A-Za-z]", "", nm).upper() or it["id"].upper()}
    for l in relay.get("dialogue", {}).get("lines", []):
        out.setdefault(l["speaker"], {"tag": str(l["speaker"]).upper()})
    for k, v in out.items():
        if "color" not in v:
            idx = int(hashlib.md5(k.encode()).hexdigest(), 16) % len(PALETTE)
            v["color"] = PALETTE[idx]
    for k, v in (given or {}).items():
        if k.startswith("_") or not isinstance(v, dict):
            continue
        out.setdefault(k, {"tag": k.upper(), "color": PALETTE[0]}).update({a: b for a, b in v.items() if a in ("tag", "color")})
    return out


# ------------------------------------------------------------------ timeline
def shots_of(relay):
    return [s for c in relay.get("chains", []) for s in c.get("segments", [])]


def load_starts(path):
    d = read_json(path)
    if "starts" in d and isinstance(d["starts"], dict):
        return {int(k): float(v) for k, v in d["starts"].items()}, d.get("total")
    return {int(k): float(v) for k, v in d.items() if str(k).isdigit()}, None


def place_keys(relay):
    """shot -> frozenset of location locks used (the 'place' of the shot)."""
    kinds = {i["id"]: i.get("kind") for i in relay.get("locks", {}).get("items", [])}
    out = {}
    for n, s in enumerate(shots_of(relay), 1):
        out[n] = frozenset(x for x in s.get("refs_used", []) if kinds.get(x) == "location")
    return out


def classify_cuts(relay, mode, scenes_over):
    """Return {shot n (>=2): 'scene' | 'inscene'} for the cut BEFORE shot n.
    mode scene_ids: chains' scene_ids differ; place: the location locks differ; auto: place when scene_ids are
    (nearly) unique per shot (a book run numbers every shot as its own scene), else scene_ids."""
    shots = shots_of(relay)
    sid = {}
    n = 0
    for c in relay.get("chains", []):
        for _ in c.get("segments", []):
            n += 1
            sid[n] = frozenset(c.get("scene_ids") or [c.get("id")])
    if mode == "auto":
        distinct = len(set(sid.values()))
        mode = "place" if distinct > 0.6 * max(1, len(shots)) else "scene_ids"
    pk = place_keys(relay)
    key = (lambda i: pk[i]) if mode == "place" else (lambda i: sid[i])
    kinds = {}
    for i in range(2, len(shots) + 1):
        kinds[i] = "scene" if key(i) != key(i - 1) else "inscene"
    for i in scenes_over.get("break_before", []):
        kinds[int(i)] = "scene"
    for i in scenes_over.get("same_scene", []):
        kinds[int(i)] = "inscene"
    return kinds, mode


def layout_lines(relay, starts, speech, first_offset, gap, skip_missing=False):
    """Every dialogue line with its start/end in film seconds, by the same rule the cut builder voices them:
    shot start + first_offset, then each measured length + gap."""
    shots = shots_of(relay)
    seg = {}
    for n, s in enumerate(shots, 1):
        seg[s["id"]] = n
    per = {}
    for l in relay.get("dialogue", {}).get("lines", []):
        if l.get("segment") not in seg:
            raise OverlayError("line %s names an unknown segment %r" % (l.get("id"), l.get("segment")))
        per.setdefault(seg[l["segment"]], []).append(l)
    out = []
    for n in sorted(per):
        if n not in starts:
            raise OverlayError("starts has no entry for shot %d" % n)
        t = starts[n] + first_offset
        for l in per[n]:
            sp = speech.get(l["id"])
            if not sp:
                if skip_missing:
                    continue
                raise OverlayError("speech_urls.json has no measured length for line %s" % l["id"])
            dur = float(sp["dur"])
            out.append({"id": l["id"], "shot": n, "speaker": l["speaker"], "text": fix_text(l["text"]),
                        "bubble": l.get("bubble"), "t0": t, "t1": t + dur, "shot_start": starts[n]})
            t += dur + gap
    return out


def split_text(text, max_chars):
    """Chunks at sentence ends first, then at commas/dashes/conjunctions near the middle, never mid-word."""
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return [text]
    parts = [p for p in re.split(r"(?<=[.!?…;:])\s+", text) if p]
    out = []
    for p in parts:
        out += _split_long(p, max_chars)
    merged = []
    for p in out:
        if merged and len(merged[-1]) + 1 + len(p) <= max_chars:
            merged[-1] += " " + p
        else:
            merged.append(p)
    return merged


def _split_long(x, max_chars):
    if len(x) <= max_chars:
        return [x]
    mid = len(x) // 2
    cands = [m.end() for m in re.finditer(r"[,—–;:]\s+| - | (?:and|but|while|because|that|which|so|or) ", x)]
    cands = [c for c in cands if 12 <= c <= len(x) - 12]
    if cands:
        cut = min(cands, key=lambda i: abs(i - mid))
    else:
        cut = x.rfind(" ", 0, mid + 1)
        if cut <= 0:
            cut = x.find(" ", mid)
        if cut <= 0:
            return [x]
    return _split_long(x[:cut].strip(), max_chars) + _split_long(x[cut:].strip(), max_chars)


# ------------------------------------------------------------------ faces
class Faces:
    """face_boxes.json: {"size": [W, H], "shots": {"3": {"faces": [{"who": "neha", "box": [x0,y0,x1,y1]}]}  (static)
                                                          or {"samples": [{"t": 1.5, "faces": [...]}, ...]}  (t = seconds into the shot)}}
    Boxes are in canvas pixels of the final picture. `who` is the speaker id of relay.json (use "?" for a nameless face)."""

    def __init__(self, data, size, grow=0.10):
        self.shots = {}
        self.hints = {}
        sz = data.get("size")
        sx = size[0] / float(sz[0]) if sz else 1.0
        sy = size[1] / float(sz[1]) if sz else 1.0
        for k, v in (data.get("shots") or {}).items():
            samples = v.get("samples") if isinstance(v, dict) and "samples" in v else [{"t": 0.0, "faces": (v.get("faces") if isinstance(v, dict) else v) or []}]
            row = []
            for s in samples:
                fs = []
                for f in s.get("faces", []):
                    b = f["box"]
                    gw, gh = (b[2] - b[0]) * grow + 8, (b[3] - b[1]) * grow + 8       # boxes are read by eye: keep a margin
                    fs.append({"who": f.get("who", "?"), "box": [(b[0] - gw) * sx, (b[1] - gh) * sy, (b[2] + gw) * sx, (b[3] + gh) * sy]})
                row.append((float(s.get("t", 0.0)), fs))
            self.shots[int(k)] = sorted(row, key=lambda r: r[0])
            if isinstance(v, dict) and v.get("side"):
                self.hints[int(k)] = v["side"]

    def has(self, n):
        return n in self.shots

    @staticmethod
    def _track(rows, who):
        return [(t, [f for f in fs if f["who"] == who][0]["box"]) for t, fs in rows if any(f["who"] == who for f in fs)]

    @staticmethod
    def _at(track, t):
        if t <= track[0][0]:
            return list(track[0][1])
        if t >= track[-1][0]:
            return list(track[-1][1])
        for (t0, b0), (t1, b1) in zip(track, track[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
                return [b0[i] + (b1[i] - b0[i]) * k for i in range(4)]
        return list(track[-1][1])

    def window(self, n, a, b, pad=0.3):
        """Faces that may be on screen in the shot-relative window [a, b] (padded by `pad` seconds). A person's box is
        interpolated between the samples that bracket each instant, and the boxes over the window are merged into one
        (their bounding box). Returns (obstacle faces, faces at the middle of the window)."""
        rows = self.shots.get(n)
        if not rows:
            return [], []
        a0, b0 = a - pad, b + pad
        times = [a0, b0] + [r[0] for r in rows if a0 < r[0] < b0]
        mid = (a + b) / 2.0
        whos = []
        for _, fs in rows:
            for k, f in enumerate(fs):
                key = f["who"] if f["who"] != "?" else "?%d" % k
                if key not in whos:
                    whos.append(key)
        obst, near = [], []
        for key in whos:
            if key.startswith("?"):
                k = int(key[1:])
                tr = [(t, fs[k]["box"]) for t, fs in rows if len(fs) > k and fs[k]["who"] == "?"]
            else:
                tr = self._track(rows, key)
            if not tr:
                continue
            boxes = [self._at(tr, t) for t in times]
            u = [min(x[0] for x in boxes), min(x[1] for x in boxes), max(x[2] for x in boxes), max(x[3] for x in boxes)]
            who = "?" if key.startswith("?") else key
            obst.append({"who": who, "box": u})
            near.append({"who": who, "box": self._at(tr, mid)})
        return obst, near


# ------------------------------------------------------------------ geometry for bubbles
def rect_hit(a, b, m=0.0):
    return not (a[2] + m <= b[0] or b[2] + m <= a[0] or a[3] + m <= b[1] or b[3] + m <= a[1])


def seg_hits_rect(p, q, r):
    """Does the segment p-q cross rectangle r (Liang-Barsky)?"""
    x0, y0 = p
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - r[0]), (dx, r[2] - x0), (-dy, y0 - r[1]), (dy, r[3] - y0)):
        if abs(pp) < 1e-9:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def nearest_on_rect(r, px, py):
    return min(max(px, r[0]), r[2]), min(max(py, r[1]), r[3])


class Style:
    def __init__(self, W, H, font="DejaVu Sans", scale=1.0, bubble_fs=None, text_scale=1.0):
        self.W, self.H = W, H
        self.k = W / 720.0
        self.font = font
        self.fs = bubble_fs or int(round(34 * self.k))
        self.tag_fs = int(round(23 * self.k))
        self.cap_fs = int(round(31 * self.k))
        self.pad_x = int(round(24 * self.k))
        self.pad_y = int(round(15 * self.k))
        self.cham = int(round(20 * self.k))
        self.lh = self.fs * 1.08
        self.ts = text_scale
        self.margin = int(round(18 * self.k))
        self.top = int(round(34 * self.k))
        self.bottom_limit = int(H * 0.79)         # bubbles stay out of the lower fifth (caption lane)
        self.shadow = max(5, int(round(7 * self.k)))


def body_polygon(L, T, R, B, c, tail=None):
    """Chamfered rectangle as a point list (clockwise from top-left). `tail` = (edge, base_centre, half_base, tip) inserted
    on the named edge ('top', 'bottom', 'left', 'right')."""
    pts = {
        "top": [(L + c, T), (R - c, T)],
        "right": [(R, T + c), (R, B - c)],
        "bottom": [(R - c, B), (L + c, B)],
        "left": [(L, B - c), (L, T + c)],
    }
    out = []
    for edge in ("top", "right", "bottom", "left"):
        a, b = pts[edge]
        out.append(a)
        if tail and tail[0] == edge:
            _, bc, hb, tip = tail[:4]
            zig = tail[4] if len(tail) > 4 else False
            if edge == "top":
                p1, p2 = (bc - hb, T), (bc + hb, T)
            elif edge == "bottom":
                p1, p2 = (bc + hb, B), (bc - hb, B)
            elif edge == "right":
                p1, p2 = (R, bc - hb), (R, bc + hb)
            else:
                p1, p2 = (L, bc + hb), (L, bc - hb)
            out.append(p1)
            if zig:
                out_zig = []
                for f, sgn in ((0.34, 1), (0.68, -1)):
                    x = p1[0] + (tip[0] - p1[0]) * f
                    y = p1[1] + (tip[1] - p1[1]) * f
                    if edge in ("top", "bottom"):
                        x += 9 * sgn
                    else:
                        y += 9 * sgn
                    out_zig.append((x, y))
                out += out_zig
                out.append(tip)
                for f, sgn in ((0.68, 1), (0.34, -1)):
                    x = p2[0] + (tip[0] - p2[0]) * f
                    y = p2[1] + (tip[1] - p2[1]) * f
                    if edge in ("top", "bottom"):
                        x += 9 * sgn
                    else:
                        y += 9 * sgn
                    out.append((x, y))
            else:
                out.append(tip)
            out.append(p2)
        out.append(b)
    return out


def path(pts):
    return "m %d %d l %s" % (round(pts[0][0]), round(pts[0][1]), " ".join("%d %d" % (round(x), round(y)) for x, y in pts[1:]))


def dots_path(L, T, R, B, c, pitch, rmax, corner="br", limit=9):
    """Halftone shading as small triangles (low-poly dots) that grow toward one corner of the box, kept inside it."""
    hw, hh = (R - L) / 2.0, (B - T) / 2.0
    cx, cy = (L + R) / 2.0, (T + B) / 2.0
    sx = 1 if "r" in corner else -1
    sy = 1 if "b" in corner else -1
    cmds = []
    ins = 6
    row = 0
    y = T + ins
    cand = []
    while y < B - ins:
        x = L + ins + (pitch / 2.0 if row % 2 else 0)
        while x < R - ins:
            u = ((x - cx) * sx / hw + (y - cy) * sy / hh) / 2.0
            r = rmax * min(1.0, max(0.0, (u - 0.28) / 0.62))
            if r >= 1.6:
                dxm, dym = abs(x - cx), abs(y - cy)
                if dxm + r <= hw - ins and dym + r <= hh - ins and dxm + dym + r * 1.5 <= hw + hh - c - 1.5 * ins:
                    cand.append((r, x, y))
            x += pitch
        y += pitch * 0.9
        row += 1
    cand.sort(reverse=True)
    for r, x, y in cand[:limit]:
        cmds.append("m %d %d l %d %d %d %d" % (round(x), round(y - r), round(x + r), round(y + r * 0.8), round(x - r), round(y + r * 0.8)))
    return " ".join(cmds)


def tag_polygon(x0, y0, x1, y1, skew):
    return [(x0 + skew, y0), (x1 + skew, y0), (x1, y1), (x0, y1)]


# ------------------------------------------------------------------ bubble layout
class Layout:
    def __init__(self, style, faces, speakers, hint_default=None, missing="fail"):
        self.st = style
        self.faces = faces
        self.speakers = speakers
        self.placed = []           # (t0, t1, rect) of bubbles/captions already placed, to avoid overlap in time
        self.warnings = []
        self.missing = missing

    def _size(self, lines, tag, phone=False):
        st = self.st
        tw = max(text_w(l, st.fs) for l in lines)
        tagw = text_w(tag, st.tag_fs) + 30 * st.k
        w = max(tw, 0) + 2 * st.pad_x
        h = len(lines) * st.lh + 2 * st.pad_y
        return w, h, tagw

    def place(self, shot, n_start, a, b, speaker, text, kind="speech", forced_side=None, relax=False):
        """Find the best (wrap, centre) for one bubble. a,b are film seconds. Returns the layout dict or None."""
        st = self.st
        W, H = st.W, st.H
        ra, rb = a - n_start, b - n_start
        obstacles, speaker_face, own = [], None, []
        if self.faces.has(shot):
            allf, near = self.faces.window(shot, ra, rb)
            obstacles = [f["box"] for f in allf]
            own = [f["box"] for f in allf if f["who"] == speaker]
            for f in near:
                if f["who"] == speaker:
                    speaker_face = f["box"]
        tag = self.speakers[speaker]["tag"] if speaker in self.speakers else str(speaker).upper()
        if kind == "phone":
            tag = tag + " (PHONE)"
        busy = [r for (t0, t1, r) in self.placed if t0 < b - 1e-6 and a < t1 - 1e-6]
        best = None
        base = int(round(440 * st.k))
        for maxw in (base, int(base * 0.78), int(base * 0.62), int(base * 0.5)):
            lines = wrap_text(text, st.fs, maxw)
            if len(lines) > 7:
                continue
            w, h, tagw = self._size(lines, tag)
            hw, hh = w / 2.0, h / 2.0
            tag_h = 30 * st.k
            ox = obstacles
            xs = range(int(st.margin + hw), int(W - st.margin - hw - st.shadow) + 1, max(8, int(10 * st.k)))
            low = (H * 0.95) if relax else st.bottom_limit      # relax: may dip into the caption lane when nothing fits above
            ys = range(int(st.top + hh + tag_h / 2), int(low - hh) + 1, max(8, int(10 * st.k)))
            if kind == "phone":
                side = forced_side or "left"
                xs = [int(st.margin + hw)] if side == "left" else [int(W - st.margin - hw - st.shadow)]
            for cy in ys:
                for cx in xs:
                    rect = (cx - hw, cy - hh - tag_h / 2, cx + hw + st.shadow, cy + hh + st.shadow)
                    if any(rect_hit(rect, o, 8 * st.k) for o in ox):
                        continue
                    if any(rect_hit(rect, o, 6 * st.k) for o in busy):
                        continue
                    body = (cx - hw, cy - hh, cx + hw, cy + hh)
                    if speaker_face is not None:
                        px, py = nearest_on_rect(speaker_face, cx, cy)
                        dx, dy = cx - px, cy - py
                        nrm = math.hypot(dx, dy) or 1.0
                        tip = (px + dx / nrm * 4, py + dy / nrm * 4)
                        bx, by = nearest_on_rect(body, tip[0], tip[1])
                        tail_len = math.hypot(tip[0] - bx, tip[1] - by)
                        if any(seg_hits_rect((bx, by), tip, o) for o in ox if o not in own):
                            continue
                        score = tail_len + (0 if cy + hh < speaker_face[1] + 20 else 70) + cy * 0.03
                    else:
                        tip = None
                        score = 40 + cy * 0.15 + (0 if kind == "phone" else abs(cx - W / 2) * 0.05)
                    if len(lines) > 4:
                        score += 25 * (len(lines) - 4)
                    if best is None or score < best[0]:
                        best = (score, lines, cx, cy, w, h, tagw, tip, rect, tag)
        if best is None:
            return None
        return best

    def commit(self, a, b, rect):
        self.placed.append((a, b, rect))


# ------------------------------------------------------------------ ASS output
class Ass:
    def __init__(self, W, H, font, speakers, used):
        self.W, self.H, self.font = W, H, font
        self.events = []   # (layer, start, end, style, text)
        self.speakers = speakers
        self.used = used

    def add(self, layer, a, b, style, text):
        self.events.append((layer, a, b, style, text))

    def header(self, st, keep=None):
        f = self.font
        rows = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: %d" % self.W, "PlayResY: %d" % self.H, "WrapStyle: 2",
                "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
                "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding"]

        def sty(name, fs, prim, outl, back, bord, shad, al=7):
            if keep is not None and name not in keep:
                return
            rows.append("Style: %s,%s,%d,%s,%s,%s,%s,1,0,0,0,100,100,0,0,1,%s,%s,%d,0,0,0,1" % (name, f, fs, prim, prim, outl, back, bord, shad, al))

        for sid in sorted(self.used):
            c = self.speakers[sid]["color"]
            sty("B_" + sid, 1, "&H00FFFFFF", "&H00000000", hex_bgr(c), 4, st.shadow)
            sty("D_" + sid, 1, hex_bgr(tint(c, 0.48)), "&H00000000", "&H00000000", 0, 0)
            sty("T_" + sid, 1, hex_bgr(c), "&H00000000", "&H00000000", 3, 0)
        sty("P_B", 1, "&H00FFF2D6", "&H00000000", "&H00000000", 4, st.shadow)
        sty("C_B", 1, "&H004FD9F9", "&H00000000", "&H00000000", 4, st.shadow)
        sty("C_D", 1, "&H002AA6EB", "&H00000000", "&H00000000", 0, 0)
        sty("X", st.fs, "&H00101010", "&H00FFFFFF", "&H00000000", 0, 0, 5)
        sty("XT", st.tag_fs, "&H00FFFFFF", "&H00000000", "&H00000000", 0, 0, 5)
        sty("XC", st.cap_fs, "&H00101010", "&H00FFFFFF", "&H00000000", 0, 0, 5)
        rows += ["", "[Events]", "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text"]
        return "\n".join(rows) + "\n"

    def render(self, st, offset=0.0, t_from=None, t_to=None):
        lo = 0.0 if t_from is None else t_from
        hi = 1e9 if t_to is None else t_to
        evs = [e for e in sorted(self.events, key=lambda e: (e[1], e[0])) if not (e[2] <= lo or e[1] >= hi)]
        lines = [self.header(st, keep={e[3] for e in evs})]
        for layer, a, b, style, text in evs:
            lines.append("Dialogue: %d,%s,%s,%s,,0,0,0,,%s\n" % (layer, ts(max(a, lo) - offset), ts(min(b, hi) - offset), style, text))
        return "".join(lines)


def ts(s):
    s = max(0.0, s)
    cs = int(round(s * 100))
    return "%d:%02d:%02d.%02d" % (cs // 360000, (cs // 6000) % 60, (cs // 100) % 60, cs % 100)


def drawing(layer_style, pts_text):
    return "{" + BS + "p1}" + pts_text          # styles are top-left aligned with zero margins: coordinates are frame pixels


def build_bubble_events(ass, st, lay, spk, best, a, b, kind):
    score, lines, cx, cy, w, h, tagw, tip, rect, tag = best
    hw, hh = w / 2.0, h / 2.0
    L, T, R, B = cx - hw, cy - hh, cx + hw, cy + hh
    c = st.cham if h >= 100 * st.k else int(12 * st.k)      # a one-line bubble gets small chamfers so a side edge can carry the tail
    W = st.W
    tail = None
    zig = kind == "phone"
    if kind == "phone":
        left = cx < W / 2
        ty = cy + hh * 0.2
        tip_p = (max(1, L - st.margin + 4) if left else min(W - 1, R + st.margin - 4), ty + 10)
        # a short zigzag toward the frame edge
        tip_p = (2, ty + 12) if left else (W - 2, ty + 12)
        tail = ("left" if left else "right", ty, 16 * st.k, tip_p, True)
    elif tip is not None:
        dx, dy = (tip[0] - cx) / hw, (tip[1] - cy) / hh
        hb = 15 * st.k
        vert_ok = (B - T - 2 * c) >= 2 * hb + 8          # a side edge long enough to carry the tail base
        if abs(dy) >= abs(dx) or not vert_ok:
            edge = "bottom" if tip[1] > cy else "top"
            bc = min(max(tip[0], L + c + hb + 4), R - c - hb - 4)
        else:
            edge = "right" if dx > 0 else "left"
            bc = min(max(tip[1], T + c + hb + 4), B - c - hb - 4)
        tail = (edge, bc, hb, tip)
    else:
        # speaker not on screen: a short stub down-left or down-right
        bc = L + c + 40 * st.k if cx < W / 2 else R - c - 40 * st.k
        tail = ("bottom", bc, 14 * st.k, (bc + (-18 if cx < W / 2 else 18) * st.k, B + 34 * st.k))
    poly = body_polygon(L, T, R, B, c, tail)
    sid = lay_speaker_id(spk)
    style_b = "P_B" if kind == "phone" else "B_" + sid
    ass.add(1, a, b, style_b, drawing(style_b, path(poly)))
    if kind != "phone":
        dp = dots_path(L, T, R, B, c, 16 * st.k, 6.5 * st.k, "br")
        if dp:
            ass.add(2, a, b, "D_" + sid, drawing("D_" + sid, dp))
    # name tag: skewed parallelogram straddling the top-left of the body
    th = 30 * st.k
    skew = 9 * st.k
    x0 = L + 16 * st.k
    tpoly = tag_polygon(x0, T - th / 2, x0 + tagw, T + th / 2, skew)
    ass.add(3, a, b, "T_" + sid, drawing("T_" + sid, path(tpoly)))
    ass.add(5, a, b, "XT", "{" + BS + "an5" + BS + "pos(%d,%d)" % (round(x0 + tagw / 2 + skew / 2), round(T)) + "}" + ass_escape(tag))
    ass.add(5, a, b, "X", "{" + BS + "an5" + BS + "pos(%d,%d)" % (round(cx), round(cy)) + "}" + (BS + "N").join(ass_escape(x) for x in lines))
    return (L, T - th / 2, R + st.shadow, B + st.shadow)


def lay_speaker_id(sid):
    return re.sub(r"[^A-Za-z0-9_]", "_", str(sid))


def build_caption_events(ass, st, lines, a, b, faces_box, top=False, x_range=None):
    W, H = st.W, st.H
    n = len(lines)
    bh = n * st.cap_fs * 1.1 + 2 * 16 * st.k
    L, R = x_range if x_range else (24 * st.k, W - 24 * st.k - st.shadow)
    if top:
        T = st.top + 6 * st.k
    else:
        T = H - 62 * st.k - bh
    B = T + bh
    c = 16 * st.k
    poly = body_polygon(L, T, R, B, c)
    ass.add(1, a, b, "C_B", drawing("C_B", path(poly)))
    dp = dots_path(L, T, R, B, c, 14 * st.k, 5.0 * st.k, "br", limit=8)
    if dp:
        ass.add(2, a, b, "C_D", drawing("C_D", dp))
    ass.add(5, a, b, "XC", "{" + BS + "an5" + BS + "pos(%d,%d)" % (round((L + R) / 2), round((T + B) / 2)) + "}" + (BS + "N").join(ass_escape(x) for x in lines))
    return (L, T, R + st.shadow, B + st.shadow)


# ------------------------------------------------------------------ the plan
def frame_snap(t, fps):
    return round(t * fps) / float(fps)


def compute_overlays(a):
    job = a.job
    relay = read_json(os.path.join(job, "relay.json"))
    speech = read_json(os.path.join(job, "speech_urls.json"))
    starts, tot0 = load_starts(a.starts or os.path.join(job, "jobs", "starts.json"))
    cut = {}
    cp = a.cut or os.path.join(job, "cut_final.json")
    if os.path.isfile(cp):
        cut = read_json(cp)
    video = a.video or cut.get("final")
    duration = a.duration or cut.get("duration") or tot0
    if not video or not duration:
        raise OverlayError("need the final picture: give --cut cut_final.json ({final, duration}) or --video URL --duration S")
    W, H = (int(x) for x in a.size.lower().split("x")) if a.size else (720, 1280)
    fps = a.fps
    nframes = int(round(float(duration) * fps))
    shots = shots_of(relay)
    speakers = speaker_table(relay, read_json(a.speakers, default={}) if a.speakers else read_json(os.path.join(job, "speakers.json"), default={}))
    faces = Faces(read_json(a.faces or os.path.join(job, "face_boxes.json"), default={}), (W, H))
    st = Style(W, H, font=a.font)
    lines = layout_lines(relay, starts, speech, a.first_offset, a.gap, a.skip_missing)
    warnings = []

    # ---- cuts
    measured = read_json(os.path.join(job, "finish", "cuts_measured.json"), default={}) if not a.no_measured else {}
    scenes_over = read_json(a.scenes, default={}) if a.scenes else read_json(os.path.join(job, "scenes.json"), default={})
    kinds, mode = classify_cuts(relay, a.scene_mode, scenes_over)
    cuts = []
    dirs_iter = None
    inscene = [n for n in sorted(kinds) if kinds[n] == "inscene"]
    dirs = ht.shuffled_directions(len(inscene), a.seed) if inscene else []
    di = {n: d for n, d in zip(inscene, dirs)}
    for n in sorted(kinds):
        if n not in starts:
            continue
        t = float(measured.get(str(n), starts[n]))
        t = frame_snap(t, fps)
        cuts.append({"shot": n, "t": t, "kind": kinds[n], "dir": di.get(n)})
    # no repeated direction back to back (the deck guarantees it; assert)
    last = None
    for c in cuts:
        if c["kind"] == "inscene":
            assert c["dir"] != last
            last = c["dir"]

    # ---- bubbles and captions
    ass = Ass(W, H, a.font, speakers, set(lay_speaker_id(l["speaker"]) for l in lines if l["speaker"] != "narrator"))
    lay = Layout(st, faces, speakers, missing=a.missing_faces)
    items = []
    for l in lines:
        if l["speaker"] == "narrator" or l.get("bubble") == "narration":
            kind = "caption"
        elif l.get("bubble") == "phone":
            kind = "phone"
        else:
            kind = "speech"
        l["kind"] = kind
    for l in lines:
        kind = l["kind"]
        chars = a.max_chars if kind != "caption" else a.caption_chars
        chunks = split_text(l["text"], chars)
        total = float(sum(len(c) for c in chunks))
        t = l["t0"]
        dur = l["t1"] - l["t0"]
        for i, ch in enumerate(chunks):
            ca = t
            cb = t + dur * len(ch) / total
            t = cb
            end = (l["t1"] + a.tail_s) if i == len(chunks) - 1 else cb
            items.append({"line": l["id"], "shot": l["shot"], "shot_start": l["shot_start"], "speaker": l["speaker"], "kind": kind,
                          "text": ch, "a": ca, "b": end, "side": None})
    items.sort(key=lambda x: (x["a"], x["b"]))
    out_items = []
    phone_side = {}
    for it in items:
        if it["kind"] == "caption":
            full_w = W - 48 * st.k - 2 * 26 * st.k
            wl = wrap_text(it["text"], st.cap_fs, full_w)
            if len(wl) > 4:
                warnings.append("caption %s needs %d lines; lower --caption-chars" % (it["line"], len(wl)))
            ra, rb = it["a"] - it["shot_start"], it["b"] - it["shot_start"]
            allf = faces.window(it["shot"], ra, rb)[0] if faces.has(it["shot"]) else []

            def band(lines_, L_, R_, top_):
                h_ = len(lines_) * st.cap_fs * 1.1 + 32 * st.k
                y0 = (st.top + 6 * st.k) if top_ else (H - 62 * st.k - h_)
                return (L_, y0, R_, y0 + h_ + st.shadow)

            L0, R0 = 24 * st.k, W - 24 * st.k - st.shadow
            xr, use_top = None, False
            if any(rect_hit(band(wl, L0, R0, False), f["box"], 6) for f in allf):
                # first try a narrower box beside the faces in the lower band, then the upper band
                lowf = [f["box"] for f in allf if rect_hit(band(wl, L0, R0, False), f["box"], 6)]
                done = False
                for side in ("right", "left"):
                    if side == "right":
                        L1, R1 = min(max(b_[2] for b_ in lowf) + 14, W), R0
                    else:
                        L1, R1 = L0, max(min(b_[0] for b_ in lowf) - 14 - st.shadow, 0)
                    if R1 - L1 >= 400 * st.k:
                        wl2 = wrap_text(it["text"], st.cap_fs, R1 - L1 - 2 * 26 * st.k)
                        if len(wl2) <= 5 and not any(rect_hit(band(wl2, L1, R1, False), f["box"], 6) for f in allf):
                            wl, xr, done = wl2, (L1, R1), True
                            break
                if not done:
                    use_top = not any(rect_hit(band(wl, L0, R0, True), f["box"], 6) for f in allf)
                    if not use_top:
                        warnings.append("caption %s: faces in both the lower and the upper band (shot %d); placed low" % (it["line"], it["shot"]))
            rect = build_caption_events(ass, st, wl, it["a"], it["b"], None, top=use_top, x_range=xr)
            out_items.append({"id": it["line"], "shot": it["shot"], "kind": "caption", "a": round(it["a"], 2), "b": round(it["b"], 2), "text": it["text"],
                              "rect": [round(x) for x in rect], "lines": len(wl), "pos": "top" if use_top else "bottom"})
            continue
        if it["kind"] == "phone":
            sd = phone_side.setdefault(it["speaker"], "left" if len(phone_side) % 2 == 0 else "right")
            side = faces.hints.get(it["shot"], sd)
        else:
            side = None
        if not faces.has(it["shot"]):
            if a.missing_faces == "fail":
                raise OverlayError("no face boxes for shot %d (line %s). Add it to face_boxes.json (see `sheet`), or pass --missing-faces top" % (it["shot"], it["line"]))
            warnings.append("shot %d has no face boxes: bubble for %s placed without a tail target" % (it["shot"], it["line"]))
        def place_any(pc_, side_):
            r = lay.place(pc_["shot"], pc_["shot_start"], pc_["a"], pc_["b"], pc_["speaker"], pc_["text"], pc_["kind"], side_)
            if r is None:
                r = lay.place(pc_["shot"], pc_["shot_start"], pc_["a"], pc_["b"], pc_["speaker"], pc_["text"], pc_["kind"], side_, relax=True)
                if r is not None:
                    warnings.append("bubble %s (shot %d) sits in the lower fifth: nothing else was free" % (pc_["line"], pc_["shot"]))
            return r

        best = place_any(it, side)
        pieces = [it]
        if best is None:
            # split the entry once more at a natural pause and place each half
            halves = split_text(it["text"], max(12, len(it["text"]) // 2 + 6))
            if len(halves) > 1:
                tot = float(sum(len(h) for h in halves))
                tt = it["a"]
                pieces = []
                for k, h in enumerate(halves):
                    nb = tt + (it["b"] - it["a"]) * len(h) / tot
                    pieces.append(dict(it, text=h, a=tt, b=nb if k < len(halves) - 1 else it["b"]))
                    tt = nb
        for pc in pieces:
            bst = best if pc is it else place_any(pc, side)
            if bst is None:
                if not a.allow_overlap:
                    raise OverlayError("no bubble position that avoids every face: shot %d line %s %r. Shorten the line, fix the face boxes, "
                                       "or pass --allow-overlap to accept the least-bad spot" % (pc["shot"], pc["line"], pc["text"][:50]))
                warnings.append("FACE-OVERLAP risk: shot %d line %s" % (pc["shot"], pc["line"]))
                continue
            rect = build_bubble_events(ass, st, lay, pc["speaker"], bst, pc["a"], pc["b"], pc["kind"])
            lay.commit(pc["a"], pc["b"], rect)
            out_items.append({"id": pc["line"], "shot": pc["shot"], "kind": pc["kind"], "speaker": pc["speaker"], "a": round(pc["a"], 2), "b": round(pc["b"], 2),
                              "text": pc["text"], "rect": [round(x) for x in rect], "lines": len(bst[1]), "tip": [round(v) for v in bst[7]] if bst[7] else None})
    return dict(relay=relay, video=video, duration=float(duration), W=W, H=H, fps=fps, nframes=nframes, cuts=cuts, mode=mode,
                st=st, ass=ass, items=out_items, warnings=warnings, lines=lines, speakers=speakers)


# ------------------------------------------------------------------ jobs
def ffjob(reason, inputs, argv, outputs, timeout=600, sidecars=None):
    j = {"reason": reason, "inputs": inputs, "argv": argv, "outputs": outputs, "timeout_seconds": timeout}
    if sidecars:
        j["sidecars"] = sidecars
    return j


def windows_of(cuts, a, fps):
    """[(start, end, cut)] seconds each transition occupies."""
    out = []
    for c in cuts:
        if c["kind"] == "scene":
            h = a.zoom_s
        else:
            h = a.ht_dur / 2.0
        out.append((c["t"] - h - 0.05, c["t"] + h + 0.05, c))
    return out


def choose_parts(nframes, fps, wins, part_s, cut_min):
    """Boundaries (frame numbers) near multiples of part_s that fall outside every transition window."""
    def free(f):
        t = f / float(fps)
        return all(not (w0 <= t <= w1) for w0, w1, _ in wins)
    bounds = [0]
    total = nframes / float(fps)
    pos = 0.0
    while total - pos > part_s * 1.4:
        target = int(round((pos + part_s) * fps))
        pick = None
        for d in range(0, int(part_s * fps * 0.45)):
            for f in (target - d, target + d):
                if bounds[-1] + int(cut_min * fps) <= f <= nframes - int(cut_min * fps) and free(f):
                    pick = f
                    break
            if pick is not None:
                break
        if pick is None:
            break
        bounds.append(pick)
        pos = pick / float(fps)
    bounds.append(nframes)
    return bounds


def zoom_expr(n, z):
    return "if(lt(on,%d),1+%.3f*pow(on/%d,2),1+%.3f*pow(1-(on-%d)/%d,2))" % (n, z, n, z, n, n)


def build_part(ctx, a, f0, f1, name, ht_urls, window_mode=False):
    """One overlay job over frames [f0, f1) of the final picture."""
    fps, W, H = ctx["fps"], ctx["W"], ctx["H"]
    t0 = f0 / float(fps)
    t1 = f1 / float(fps)
    nfr = f1 - f0
    cuts = [c for c in ctx["cuts"] if t0 <= c["t"] - (a.zoom_s if c["kind"] == "scene" else a.ht_dur / 2) - 0.02 and c["t"] + (a.zoom_s if c["kind"] == "scene" else a.ht_dur / 2) + 0.02 <= t1]
    inputs = [{"name": "final.mp4", "url": ctx["video"]}]
    fc = ["[0:v]setpts=PTS-STARTPTS[v0]"]
    cur = "[v0]"
    k = 0
    zn = int(round(a.zoom_s * fps))
    scene_cuts = [c for c in cuts if c["kind"] == "scene"]
    # 1) zoom windows (outgoing zooms in, incoming starts zoomed in and settles)
    for c in scene_cuts:
        lc = c["t"] - t0
        S = lc - zn / float(fps)
        E = lc + zn / float(fps)
        k += 1
        fc.append("%ssplit=2[zb%d][zs%d]" % (cur, k, k))
        fc.append("[zs%d]trim=start=%.4f:end=%.4f,setpts=PTS-STARTPTS,zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=%dx%d:fps=%d,setpts=PTS+%.4f/TB[zz%d]"
                  % (k, S, E, zoom_expr(zn, a.zoom), W, H, fps, S, k))
        fc.append("[zb%d][zz%d]overlay=eof_action=pass:enable='between(t,%.4f,%.4f)'[v%d]" % (k, k, S, E - 0.001, k))
        cur = "[v%d]" % k
    # 2) bubbles and captions
    ass_text = ctx["ass"].render(ctx["st"], offset=t0, t_from=t0, t_to=t1)
    k += 1
    if a.bubbles:
        fc.append("%sass=b.ass[v%d]" % (cur, k))
        cur = "[v%d]" % k
    # 3) fade through black at the scene change
    for c in scene_cuts:
        lc = c["t"] - t0
        S = lc - zn / float(fps)
        E = lc + zn / float(fps)
        k += 1
        d = 2 * zn / float(fps)
        fc.append("color=c=black:s=%dx%d:r=%d:d=%.4f,format=rgba,fade=t=in:st=0:d=%.4f:alpha=1,fade=t=out:st=%.4f:d=%.4f:alpha=1,setpts=PTS+%.4f/TB[dk%d]"
                  % (W, H, fps, d, d / 2, d / 2, d / 2, S, k))
        fc.append("%s[dk%d]overlay=format=auto:eof_action=pass:enable='between(t,%.4f,%.4f)'[v%d]" % (cur, k, S, E - 0.001, k))
        cur = "[v%d]" % k
    # 4) halftone wipes on the cuts inside a scene
    ht_cuts = [c for c in cuts if c["kind"] == "inscene"]
    used = {}
    for c in ht_cuts:
        used.setdefault(c["dir"], []).append(c)
    for d, cs in used.items():
        inputs.append({"name": "ht_%s.mp4" % d, "url": ht_urls.get(d, "HT_URL_" + d)})
        idx = len(inputs) - 1
        labs = ["[hk%s_%d]" % (d, j) for j in range(len(cs))]
        if len(cs) > 1:
            fc.append("[%d:v]format=rgba,colorkey=black:0.12:0.08,split=%d%s" % (idx, len(cs), "".join(labs)))
        else:
            fc.append("[%d:v]format=rgba,colorkey=black:0.12:0.08%s" % (idx, labs[0]))
        for j, c in enumerate(cs):
            lc = c["t"] - t0
            S = lc - a.ht_dur / 2
            k += 1
            fc.append("%ssetpts=PTS-STARTPTS+%.4f/TB[hs%d]" % (labs[j], S, k))
            fc.append("%s[hs%d]overlay=format=auto:eof_action=pass:enable='between(t,%.4f,%.4f)'[v%d]" % (cur, k, S, S + a.ht_dur - 0.001, k))
            cur = "[v%d]" % k
    fc.append("%sformat=yuv420p[vout]" % cur)
    argv = ["-y"]
    if t0 > 0:
        argv += ["-ss", "%.4f" % (t0 - 0.5 / fps)]
    argv += ["-i", "final.mp4"]
    for x in inputs[1:]:
        argv += ["-i", x["name"]]
    argv += ["-filter_complex", ";".join(fc), "-map", "[vout]", "-an", "-frames:v", str(nfr), "-r", str(fps), "-c:v", "libx264", "-preset", a.preset,
             "-crf", str(a.crf), "-pix_fmt", "yuv420p", "-g", str(fps * 2), "-movflags", "+faststart", name]
    job = ffjob("overlay pass %s: frames %d-%d (%.2f-%.2f s) bubbles + transitions" % (name, f0, f1, t0, t1), inputs, argv,
                [{"name": name, "mime_type": "video/mp4"}], 600, [{"name": "b.ass", "content": ass_text}] if a.bubbles else None)
    return job, cuts


def load_ht_urls(a):
    ht_urls = {}
    outs = read_json(os.path.join(a.job, "finish", "outputs.json"), default={})
    for d in DIRS:
        if "ht_" + d in outs:
            ht_urls[d] = outs["ht_" + d]
    if a.ht_clips:
        for k, v in read_json(a.ht_clips).items():
            ht_urls[k.replace("ht_", "")] = v
    return ht_urls


def cmd_plan(a):
    fin = os.path.join(a.job, "finish")
    ht_urls = load_ht_urls(a)
    ctx = compute_overlays(a)
    wins = windows_of(ctx["cuts"] if a.transitions else [], a, ctx["fps"])
    if not a.transitions:
        ctx["cuts"] = []
    bounds = choose_parts(ctx["nframes"], ctx["fps"], wins, a.part_seconds, 12)
    jobs, parts = [], []
    for i in range(len(bounds) - 1):
        name = "ov%02d.mp4" % (i + 1)
        j, cs = build_part(ctx, a, bounds[i], bounds[i + 1], name, ht_urls)
        jobs.append(j)
        parts.append({"name": name, "f0": bounds[i], "f1": bounds[i + 1], "t0": round(bounds[i] / ctx["fps"], 3), "t1": round(bounds[i + 1] / ctx["fps"], 3),
                      "cuts": [(c["shot"], c["kind"], c["dir"]) for c in cs], "bytes": len(json.dumps(j, separators=(",", ":")))})
    os.makedirs(os.path.join(fin, "jobs"), exist_ok=True)
    write_json(os.path.join(fin, "jobs", "overlay_parts.json"), jobs, separators=(",", ":"))
    calls = []
    for c in range(0, len(jobs), 5):
        nm = "ov_call%d.json" % (c // 5 + 1)
        write_json(os.path.join(fin, "jobs", nm), jobs[c:c + 5], separators=(",", ":"))
        calls.append(nm)
    write_text(os.path.join(fin, "overlay.ass"), ctx["ass"].render(ctx["st"]))
    plan = {"video": ctx["video"], "duration": ctx["duration"], "frames": ctx["nframes"], "fps": ctx["fps"], "size": [ctx["W"], ctx["H"]],
            "scene_mode": ctx["mode"], "cuts": ctx["cuts"], "items": ctx["items"], "parts": parts, "calls": calls, "warnings": ctx["warnings"],
            "missing_halftone_clips": [d for d in sorted({c["dir"] for c in ctx["cuts"] if c["kind"] == "inscene"}) if d not in ht_urls]}
    write_json(os.path.join(fin, "overlay_plan.json"), plan, indent=1)
    nb = sum(1 for x in ctx["items"] if x["kind"] in ("speech", "phone"))
    nc = sum(1 for x in ctx["items"] if x["kind"] == "caption")
    ns = sum(1 for c in ctx["cuts"] if c["kind"] == "scene")
    print("%d bubbles, %d captions, %d halftone wipes, %d zoom/fade scene changes; %d parts in %d calls (%s)"
          % (nb, nc, sum(1 for c in ctx["cuts"] if c["kind"] == "inscene"), ns, len(parts), len(calls), ", ".join(calls)))
    print("job sizes (bytes): " + ", ".join(str(p["bytes"]) for p in parts))
    if plan["missing_halftone_clips"]:
        print("NOTE: halftone clips missing for %s: run `ht-jobs`, send them, record with `outputs`, then `plan` again" % plan["missing_halftone_clips"])
    for w in ctx["warnings"]:
        print("WARN: " + w)
    return 1 if any("FACE-OVERLAP" in w for w in ctx["warnings"]) else 0


def cmd_window(a):
    a.bubbles = True
    ctx = compute_overlays(a)
    ht_urls = load_ht_urls(a)
    f0 = int(round(float(a.start) * ctx["fps"]))
    f1 = int(round(float(a.end) * ctx["fps"]))
    name = "win_%d_%d.mp4" % (f0, f1)
    j, _ = build_part(ctx, a, f0, f1, name, ht_urls, True)
    p = os.path.join(a.job, "finish", "jobs", "window_%d_%d.json" % (f0, f1))
    write_json(p, [j], separators=(",", ":"))
    print("wrote %s (%d bytes), output %s; view_image(at_seconds) is relative to the window start (%.2f s)" % (p, os.path.getsize(p), name, f0 / ctx["fps"]))
    return 0


def cmd_ht_jobs(a):
    W, H = (int(x) for x in a.size.lower().split("x")) if a.size else (720, 1280)
    jobs = []
    k = W / 720.0
    pitch = int(round(a.pitch * k))
    hw, hh = W // 2, H // 2
    for d in DIRS:
        m = ht.mask_expr(d, a.dur, pitch // 2, ht.RMAX, hold=a.hold)
        c = ht.mask_expr(d, a.dur, pitch // 2, ht.RMAX, lag=0.07, dx=4, dy=2, hold=a.hold)
        fc = ("color=c=black:s=%dx%d:r=%d:d=%.3f,format=gray,geq=lum='if(%s,255,0)',scale=%d:%d:flags=neighbor,format=gray[mm];"
              "color=c=black:s=%dx%d:r=%d:d=%.3f,format=gray,geq=lum='if(%s,255,0)',scale=%d:%d:flags=neighbor,format=gray[cm];"
              "color=c=0xFF2E93:s=%dx%d:r=%d:d=%.3f,format=rgba[mc];color=c=0x00DEE2:s=%dx%d:r=%d:d=%.3f,format=rgba[cc];"
              "color=c=black:s=%dx%d:r=%d:d=%.3f,format=rgba[bg];"
              "[mc][mm]alphamerge[ml];[cc][cm]alphamerge[cl];[bg][cl]overlay=format=auto[t1];[t1][ml]overlay=format=auto,format=yuv420p[o]"
              % (hw, hh, a.fps, a.dur, m, W, H, hw, hh, a.fps, a.dur, c, W, H, W, H, a.fps, a.dur, W, H, a.fps, a.dur, W, H, a.fps, a.dur))
        # the dots are specified at half pitch because the mask is rendered at half size and scaled up
        name = "ht_%s.mp4" % d
        jobs.append(ffjob("Halftone dot wipe %s (%dx%d, %.2f s, flat peak)" % (d, W, H, a.dur), [],
                          ["-y", "-filter_complex", fc, "-map", "[o]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p", "-r", str(a.fps), name],
                          [{"name": name, "mime_type": "video/mp4"}], 600))
    fin = os.path.join(a.job, "finish", "jobs")
    os.makedirs(fin, exist_ok=True)
    write_json(os.path.join(fin, "ht_call1.json"), jobs[:5], separators=(",", ":"))
    write_json(os.path.join(fin, "ht_call2.json"), jobs[5:], separators=(",", ":"))
    print("wrote ht_call1.json (5 jobs) and ht_call2.json (3 jobs); send each as one run_ffmpeg call, then record ht_LR=URL ... with `outputs`")
    return 0


def cmd_sheet(a):
    relay = read_json(os.path.join(a.job, "relay.json"))
    starts, tot = load_starts(a.starts or os.path.join(a.job, "jobs", "starts.json"))
    cut = read_json(a.cut or os.path.join(a.job, "cut_final.json"), default={})
    video = a.video or cut.get("final")
    duration = a.duration or cut.get("duration") or tot
    shots = sorted(starts)
    nxt = {n: (starts[n + 1] if n + 1 in starts else float(duration)) for n in shots}
    if a.shots:
        want = {int(x) for x in a.shots.split(",")}
        shots = [n for n in shots if n in want]
    fr = [float(x) for x in a.fracs.split(",")]
    sc = a.scale
    tw, th = int(720 * sc), int(1280 * sc)
    grid = int(100 * sc)
    jobs, index = [], []
    per = a.per_sheet
    for si in range(0, len(shots), per):
        grp = shots[si:si + per]
        inputs = [{"name": "final.mp4", "url": video}]
        argv = ["-y"]
        fcs, labs = [], []
        i = 0
        for n in grp:
            for f in fr:
                t = starts[n] + (nxt[n] - starts[n]) * f
                argv += ["-ss", "%.3f" % t, "-i", "final.mp4"]
                fcs.append("[%d:v]select=eq(n\\,0),scale=%d:%d,drawgrid=w=%d:h=%d:t=1:c=white@0.55,drawgrid=w=%d:h=%d:t=2:c=yellow@0.7[g%d]" % (i, tw, th, grid, grid, grid * 5, grid * 5, i))
                labs.append("[g%d]" % i)
                index.append({"sheet": len(jobs) + 1, "shot": n, "t_in_shot": round(t - starts[n], 2), "tile": i})
                i += 1
        cols = len(fr) if len(fr) > 1 else 2
        layout = "|".join("%d_%d" % ((j % cols) * tw, (j // cols) * th) for j in range(len(labs)))
        fcs.append("%sxstack=inputs=%d:layout=%s[o]" % ("".join(labs), len(labs), layout))
        out = "%s%02d.jpg" % (a.prefix, len(jobs) + 1)
        argv += ["-filter_complex", ";".join(fcs), "-map", "[o]", "-frames:v", "1", "-q:v", "3", out]
        jobs.append(ffjob("face sheet %d: shots %s" % (len(jobs) + 1, grp), inputs, argv, [{"name": out, "mime_type": "image/jpeg"}], 300))
    fin = os.path.join(a.job, "finish", "jobs")
    os.makedirs(fin, exist_ok=True)
    names = []
    for c in range(0, len(jobs), 5):
        nm = "%s_call%d.json" % (a.prefix, c // 5 + 1)
        write_json(os.path.join(fin, nm), jobs[c:c + 5], separators=(",", ":"))
        names.append(nm)
    write_json(os.path.join(a.job, "finish", "%s_index.json" % a.prefix), index, indent=0)
    print("%d sheets (%d shots x %d frames; white grid = 100 px, yellow = 500 px of the 720x1280 frame) in %s" % (len(jobs), len(shots), len(fr), ", ".join(names)))
    return 0


def cmd_outputs(a):
    p = os.path.join(a.job, "finish", "outputs.json")
    d = read_json(p, default={})
    for x in a.pairs:
        if "=" not in x:
            raise OverlayError("expected name=url, got %r" % x)
        k, v = x.split("=", 1)
        d[k.replace(".mp4", "")] = v
    write_json(p, d, indent=1)
    print("outputs known: " + ", ".join(sorted(d)))
    return 0


def cmd_join(a):
    plan = read_json(os.path.join(a.job, "finish", "overlay_plan.json"))
    outs = read_json(os.path.join(a.job, "finish", "outputs.json"))
    names = [p["name"] for p in plan["parts"]]
    miss = [n for n in names if n.replace(".mp4", "") not in outs]
    if miss:
        raise OverlayError("no link recorded for %s (use `outputs`)" % ", ".join(miss))
    inputs = [{"name": n, "url": outs[n.replace(".mp4", "")]} for n in names] + [{"name": "final.mp4", "url": plan["video"]}]
    lst = "ffconcat version 1.0\n" + "".join("file '%s'\n" % n for n in names)
    argv = ["-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-i", "final.mp4", "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", "-movflags", "+faststart", a.out]
    j = ffjob("overlay pass join: %d overlay parts (video, stream copy) + the original audio (stream copy)" % len(names), inputs, argv,
              [{"name": a.out, "mime_type": "video/mp4"}], 600, [{"name": "list.txt", "content": lst}])
    p = os.path.join(a.job, "finish", "jobs", "ov_join.json")
    write_json(p, [j], separators=(",", ":"))
    print("wrote %s: %d inputs, output %s" % (p, len(inputs), a.out))
    return 0


def cmd_record(a):
    plan = read_json(os.path.join(a.job, "finish", "overlay_plan.json"))
    items = plan["items"]
    d = {"final": a.url, "duration": plan["duration"], "source": plan["video"], "audio": "original stream copy of source",
         "bubbles": sum(1 for x in items if x["kind"] in ("speech", "phone")), "captions": sum(1 for x in items if x["kind"] == "caption"),
         "halftone_wipes": sum(1 for c in plan["cuts"] if c["kind"] == "inscene"), "scene_changes": sum(1 for c in plan["cuts"] if c["kind"] == "scene"),
         "flaws": a.flaw or []}
    write_json(os.path.join(a.job, "cut_finish.json"), d, indent=1)
    print("wrote cut_finish.json")
    return 0


def find_ffmpeg(explicit=None):
    for c in (explicit, os.environ.get("FFMPEG"), shutil.which("ffmpeg")):
        if c and (os.path.isfile(c) or shutil.which(c)):
            return c
    try:
        import imageio_ffmpeg  # type: ignore
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise OverlayError("no local ffmpeg: pass --ffmpeg PATH, set FFMPEG, or pip install imageio-ffmpeg")


def cmd_measure(a):
    starts, _ = load_starts(a.starts or os.path.join(a.job, "jobs", "starts.json"))
    cut = read_json(a.cut or os.path.join(a.job, "cut_final.json"), default={})
    src = a.file or cut.get("final")
    ff = find_ffmpeg(a.ffmpeg)
    scores = os.path.join(a.job, "finish", "scene_scores.txt")
    os.makedirs(os.path.dirname(scores), exist_ok=True)
    vf = "scale=180:320,select='gte(scene,0.0)',metadata=print:key=lavfi.scene_score:file=scene_scores.txt"
    r = subprocess.run([ff, "-hide_banner", "-nostats", "-i", src, "-vf", vf, "-an", "-f", "null", "-"], cwd=os.path.dirname(scores), capture_output=True, text=True)
    if r.returncode != 0:
        raise OverlayError("ffmpeg failed: " + r.stderr[-300:])
    t, s = [], []
    for ln in open(scores, encoding="utf-8"):
        m = re.search(r"pts_time:([\d.]+)", ln)
        if m:
            t.append(float(m.group(1)))
        m = re.search(r"scene_score=([\d.]+)", ln)
        if m:
            s.append(float(m.group(1)))
    meas, worst = {}, 0.0
    for n in sorted(starts):
        if n == min(starts):
            continue
        e = starts[n]
        cand = [(s[i], t[i]) for i in range(min(len(s), len(t))) if abs(t[i] - e) <= a.window]
        if not cand:
            continue
        sc, tm = max(cand)
        if sc < a.min_score:
            print("note: shot %d cut has a weak scene score (%.2f); keeping the planned time" % (n, sc))
            continue
        meas[str(n)] = round(tm, 4)
        worst = max(worst, abs(tm - e))
    write_json(os.path.join(a.job, "finish", "cuts_measured.json"), meas, indent=0)
    print("measured %d cuts; largest drift from starts.json %.3f s -> finish/cuts_measured.json (plan uses it)" % (len(meas), worst))
    return 0


def cmd_run_local(a):
    ff = find_ffmpeg(a.ffmpeg)
    jobs = read_json(a.jobfile)
    if isinstance(jobs, dict):
        jobs = [jobs]
    wd = os.path.abspath(a.workdir)
    cache = os.path.join(wd, "_cache")
    os.makedirs(cache, exist_ok=True)
    produced = {}
    for ji, j in enumerate(jobs):
        jd = os.path.join(wd, "job%d" % (ji + 1))
        if os.path.isdir(jd):
            shutil.rmtree(jd)
        os.makedirs(jd)
        for inp in j["inputs"]:
            u = inp["url"]
            if os.path.isfile(u):
                src = u
            else:
                key = hashlib.sha1(u.encode()).hexdigest()[:16] + os.path.splitext(u)[1]
                src = os.path.join(cache, key)
                if not os.path.isfile(src):
                    print("fetch", u)
                    req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0 (overlay_pass run-local)"})
                    with urllib.request.urlopen(req) as resp, open(src + ".part", "wb") as out:
                        shutil.copyfileobj(resp, out)
                    os.replace(src + ".part", src)
            dst = os.path.join(jd, inp["name"])
            try:
                os.link(src, dst)           # no copy of a large input
            except OSError:
                shutil.copyfile(src, dst)
        for sc in j.get("sidecars") or []:
            write_text(os.path.join(jd, sc["name"]), sc["content"])
        print("job %d: %s" % (ji + 1, j.get("reason", "")))
        r = subprocess.run([ff, "-hide_banner", "-nostats"] + j["argv"], cwd=jd, capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stderr[-1500:])
            raise OverlayError("ffmpeg failed in job %d" % (ji + 1))
        for o in j["outputs"]:
            dst = os.path.join(wd, o["name"])
            shutil.move(os.path.join(jd, o["name"]), dst)
            produced[o["name"]] = dst
            print("  ->", dst)
        shutil.rmtree(jd, ignore_errors=True)
    return 0


# ------------------------------------------------------------------ cli
def build_parser():
    ap = argparse.ArgumentParser(description="Finish pass: bubbles, captions and transitions as overlays on an existing final cut.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("job")
        p.add_argument("--cut", help="cut json with {final, duration} (default JOB/cut_final.json)")
        p.add_argument("--video", help="final picture link (instead of --cut)")
        p.add_argument("--duration", type=float)
        p.add_argument("--starts", help="shot starts (default JOB/jobs/starts.json)")
        p.add_argument("--faces", help="face boxes (default JOB/face_boxes.json)")
        p.add_argument("--speakers", help="speaker names/colours (default JOB/speakers.json)")
        p.add_argument("--scenes", help="scene overrides {break_before:[shots], same_scene:[shots]} (default JOB/scenes.json)")
        p.add_argument("--scene-mode", default="auto", choices=["auto", "place", "scene_ids"])
        p.add_argument("--size", help="WxH of the final picture (default 720x1280)")
        p.add_argument("--fps", type=int, default=24)
        p.add_argument("--font", default="DejaVu Sans")
        p.add_argument("--first-offset", type=float, default=0.3, help="first line starts this long after its shot start")
        p.add_argument("--gap", type=float, default=0.35, help="gap after every line")
        p.add_argument("--tail-s", type=float, default=0.35, help="bubble stays this long after its line ends")
        p.add_argument("--max-chars", type=int, default=70, help="split a speech line into timed bubbles above this many characters")
        p.add_argument("--caption-chars", type=int, default=100)
        p.add_argument("--missing-faces", default="fail", choices=["fail", "top"])
        p.add_argument("--allow-overlap", action="store_true")
        p.add_argument("--skip-missing", action="store_true", help="skip lines without a measured length")
        p.add_argument("--no-measured", action="store_true", help="ignore finish/cuts_measured.json")
        p.add_argument("--seed", type=int, default=7)
        p.add_argument("--ht-dur", type=float, default=0.7)
        p.add_argument("--zoom", type=float, default=0.14, help="zoom-in amount at the scene change (0.14 = 14 %%)")
        p.add_argument("--zoom-s", type=float, default=0.5, help="seconds of zoom/fade before and after a scene change")
        p.add_argument("--part-seconds", type=float, default=55.0)
        p.add_argument("--crf", type=int, default=21)
        p.add_argument("--preset", default="veryfast")
        p.add_argument("--no-bubbles", dest="bubbles", action="store_false")
        p.add_argument("--no-transitions", dest="transitions", action="store_false")
        p.add_argument("--ht-clips", help="json {ht_LR: url, ...} of the 8 halftone clips (e.g. a series-wide file)")

    p = sub.add_parser("plan")
    common(p)
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("window")
    common(p)
    p.add_argument("start")
    p.add_argument("end")
    p.set_defaults(fn=cmd_window)
    p = sub.add_parser("ht-jobs")
    p.add_argument("job")
    p.add_argument("--size")
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--dur", type=float, default=0.7)
    p.add_argument("--hold", type=float, default=0.2)
    p.add_argument("--pitch", type=int, default=44)
    p.set_defaults(fn=cmd_ht_jobs)
    p = sub.add_parser("sheet")
    p.add_argument("job")
    p.add_argument("--cut")
    p.add_argument("--video")
    p.add_argument("--duration", type=float)
    p.add_argument("--starts")
    p.add_argument("--per-sheet", type=int, default=3)
    p.add_argument("--shots", help="only these shots, e.g. 12,14,15 (to add a sample to a shot where people move)")
    p.add_argument("--prefix", default="sheet", help="file name prefix of the sheet images")
    p.add_argument("--fracs", default="0.2,0.75")
    p.add_argument("--scale", type=float, default=0.4)
    p.set_defaults(fn=cmd_sheet)
    p = sub.add_parser("outputs")
    p.add_argument("job")
    p.add_argument("pairs", nargs="+")
    p.set_defaults(fn=cmd_outputs)
    p = sub.add_parser("join")
    p.add_argument("job")
    p.add_argument("--out", default="cut_finish.mp4")
    p.set_defaults(fn=cmd_join)
    p = sub.add_parser("record")
    p.add_argument("job")
    p.add_argument("url")
    p.add_argument("--flaw", action="append")
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser("measure")
    p.add_argument("job")
    p.add_argument("--cut")
    p.add_argument("--file", help="local path or link of the final (default: cut_final.json final)")
    p.add_argument("--starts")
    p.add_argument("--ffmpeg")
    p.add_argument("--window", type=float, default=1.2)
    p.add_argument("--min-score", type=float, default=0.12)
    p.set_defaults(fn=cmd_measure)
    p = sub.add_parser("run-local")
    p.add_argument("jobfile")
    p.add_argument("--workdir", default="finish_local")
    p.add_argument("--ffmpeg")
    p.set_defaults(fn=cmd_run_local)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except OverlayError as exc:
        print("FAIL: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
