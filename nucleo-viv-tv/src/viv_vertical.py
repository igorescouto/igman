#!/usr/bin/env python3
"""
Núcleo Viv · TV vertical (9:16, 2160x3840, 30 fps, sem som, loop perfeito).

4 variações:
  M1_LINHA_DA_JORNADA   100% motion · linha desce a tela passando pelas 3 fases
  M2_TRES_FASES         100% motion · cartões tipográficos (1, 2, ∞) que sobem
  T1_A_JORNADA          takes do espaço em câmera lenta + capítulos das fases
  T2_O_ESPACO           quase só takes em câmera lenta, legenda discreta, logo no fim

Gera em resolve_vertical/:
  grafica/*.mp4        M1 e M2 finais; T1/T2 BASE (fundo+logos) e PREVIEW (com slots sinalizados)
  textos/*.png         cada bloco de texto de T1/T2 como PNG com alfa (clipes soltos no Resolve)
  timelines.json       mapa das timelines que o script do Resolve monta

Uso:  python3 src/viv_vertical.py [--only M1 T1 ...] [--scale 0.5] [--frames 0 100 ...]
"""
import argparse, json, math, os, subprocess
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import viv_render as R
from viv_render import (GREEN, GREEN_DEEP, CREAM, OFFWHITE, F_TITLE, F_BODY, F_LIGHT, F_LABEL, F_MONO,
                        ramp, window, ease_out, ease_io, clamp, with_opacity, text_img, logo_asset,
                        symbol_pieces, paste, bg_at, build_bg, px)

ROOT = R.ROOT
OUT = os.environ.get("VIV_OUT") or os.path.join(ROOT, "resolve_vertical")
FPS = 30
W = H = 0
CREAM_BG = (233, 229, 220)      # cartão claro do M2 (creme da marca clareado)
FADE, XF = 0.3, 0.5


def set_scale(sc):
    global W, H
    R.SC = sc
    R.W, R.H = int(2160 * sc), int(3840 * sc)
    W, H = R.W, R.H


# ---------------------------------------------------------------- texto
def block(lines, fpath, size, color=OFFWHITE, align="l", leading=1.17, tracking=0.0, shadow=False):
    """Bloco de 1+ linhas num RGBA só."""
    imgs = [text_img(l, fpath, size, color, tracking, shadow) for l in lines.split("\n")]
    pad = imgs[0].info["pad"]
    lh = px(size * leading)
    w = max(i.width for i in imgs)
    out = Image.new("RGBA", (w, lh * (len(imgs) - 1) + imgs[0].height), (0, 0, 0, 0))
    for k, im in enumerate(imgs):
        x = 0 if align == "l" else (w - im.width) // 2
        out.alpha_composite(im, (x, k * lh))
    out.info["pad"] = pad
    return out


def put(frame, img, x, y, op=1.0, align="l"):
    """x = borda esquerda (l) ou centro (c); y = topo visual do bloco."""
    if op <= 0.003:
        return
    im = with_opacity(img, op)
    pad = img.info.get("pad", 0)
    xx = int(x - pad) if align == "l" else int(x - im.width / 2)
    yy = int(y - pad)
    frame.alpha_composite(im, (max(xx, 0), max(yy, 0)), (max(0, -xx), max(0, -yy)))


# ---------------------------------------------------------------- logo
def lockup(frame, A, t, t_in, t_out, sig=False, assemble=False):
    out = 1 - ramp(t, t_out - 0.45, t_out)
    sw, sh = A["sym_w"], A["sym_l"].height
    fcy, fsc = H * 0.395, 0.66

    def pieces(sc):
        l = A["sym_l"].resize((max(1, int(A["sym_l"].width * sc)), max(1, int(sh * sc))), Image.BILINEAR)
        r = A["sym_r"].resize((max(1, int(A["sym_r"].width * sc)), max(1, int(A["sym_r"].height * sc))), Image.BILINEAR)
        return l, r

    if assemble:   # símbolo monta no centro (peças vêm dos lados), sobe, depois entram os textos
        k = ease_out((t - t_in) / 1.2)
        op = clamp((t - t_in) / 0.6) * out
        up = ease_io((t - (t_in + 1.35)) / 0.8)
        cy = H / 2 + (fcy - H / 2) * up
        sc = 1 + (fsc - 1) * up
        off = px(280) * (1 - k)
        t_txt = t_in + 2.0
    else:
        op = ramp(t, t_in, t_in + 0.5) * out
        cy = fcy + px(30) * (1 - ease_out((t - t_in) / 0.6))
        sc, off = fsc, 0
        t_txt = t_in + 0.25
    if op > 0.003:
        l, r = pieces(sc)
        x0, top = W / 2 - sw * sc / 2, cy - sh * sc / 2
        frame.alpha_composite(with_opacity(l, op), (int(x0 - off), int(top)))
        frame.alpha_composite(with_opacity(r, op), (int(x0 + A["sym_rx"] * sc + off), int(top + sh * sc - r.height)))
    o1 = ramp(t, t_txt, t_txt + 0.5) * out
    r1 = px(24) * (1 - ease_out((t - t_txt) / 0.6))
    paste(frame, A["wordmark"], W / 2, H * 0.545 + r1, o1)
    o2 = ramp(t, t_txt + 0.3, t_txt + 0.8) * out
    r2 = px(24) * (1 - ease_out((t - t_txt - 0.3) / 0.6))
    paste(frame, A["sub"], W / 2, H * 0.592 + (0 if sig else r2), o2)
    if sig:
        paste(frame, A["sig"], W / 2, H * 0.668 + r2, o2)


def common_assets():
    A = {}
    A["sym_l"], _, A["sym_r"], A["sym_rx"], A["sym_w"] = symbol_pieces(OFFWHITE, 760)
    A["wordmark"] = logo_asset("09.png", OFFWHITE, 170)
    A["sub"] = text_img("NÚCLEO DE MEDICINA INTEGRATIVA", F_LABEL, 54, CREAM, tracking=0.3)
    A["sig"] = text_img("Bem-estar em cada detalhe", F_LIGHT, 132, OFFWHITE)
    A["sym_small"] = logo_asset("03.png", OFFWHITE, 380)
    return A


# ================================================================ conteúdo
FASES = [
    dict(label="FASE 1", titulo="Emagrecimento\ncom método",
         frase="Músculo preservado\ndesde o início.",
         defin="Composição, circunferência\ne força avaliadas.", num="1"),
    dict(label="FASE 2", titulo="Estrutura e\ncontorno corporal",
         frase="Primeiro gordura, depois\nmúsculo, depois pele.",
         defin="Avaliação dedicada:\ngordura, músculo, pele.", num="2"),
    dict(label="FASE PERENE", titulo="Manutenção",
         frase="Manter também\né tratamento.",
         defin="Manter o resultado\ntambém é tratamento.", num="∞"),
]

T1_SLOTS = [("1A", "plano aberto do espaço"), ("1B", "detalhe: equipamento / mãos"),
            ("2A", "sala de avaliação"), ("2B", "consultório"),
            ("PA", "recepção / acolhimento"), ("PB", "detalhe calmo do ambiente")]
T2_SLOTS = [("RECEPÇÃO", "Acolhimento\ndesde a chegada"),
            ("SALA DE ESPERA", "Um espaço pensado\npara desacelerar"),
            ("SALA DE AVALIAÇÃO", "Avaliação de\ncomposição corporal"),
            ("CONSULTÓRIO", "Consulta\nindividualizada"),
            ("SALA DE PROCEDIMENTOS", "Estrutura e\ncontorno corporal"),
            ("NÚCLEO VIV", "Cuidado em\ncada detalhe")]


class V:
    def __init__(self, key, name, dur):
        self.key, self.name, self.dur = key, name, dur
        self.slots, self.A = [], {}

    @property
    def n(self):
        return int(round(self.dur * FPS))

    def slot_alpha(self, t):
        best = (None, 0.0)
        for s in self.slots:
            a = min(ramp(t, s["a"] - XF / 2, s["a"] + XF / 2), 1 - ramp(t, s["b"] - XF / 2, s["b"] + XF / 2))
            if a > 0 and (best[0] is None or s["a"] > best[0]["a"]):
                best = (s, a if best[0] is None else 1.0)
        return best


def placeholder(s):
    im = Image.new("RGB", (W, H), (34, 44, 41))
    d = ImageDraw.Draw(im)
    for k in range(-H, W, px(90)):
        d.line([(k, 0), (k + H, H)], fill=(38, 49, 46), width=px(30))
    f1, f2 = ImageFont.truetype(F_MONO, px(64)), ImageFont.truetype(F_MONO, px(92))
    y = H * 0.16
    d.text((px(170), y), "TAKE DO ESPAÇO · CÂMERA LENTA", font=f1, fill=(170, 182, 176))
    d.text((px(170), y + px(110)), f"SLOT {s['id']} · {s['b'] - s['a']:.1f} s", font=f2, fill=(205, 214, 209))
    d.text((px(170), y + px(250)), s["sug"], font=f1, fill=(150, 162, 156))
    return im


def scrim_img(strength, start):
    yy = np.mgrid[0:H, 0:W][0].astype(np.float32) / H
    a = np.clip((yy - start) / (1 - start), 0, 1) ** 1.25 * strength
    a = np.maximum(a, 0.10)
    img = Image.new("RGBA", (W, H), GREEN_DEEP + (0,))
    img.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    return img


# ---------------------------------------------------------------- M1 · linha da jornada
def make_m1():
    v = V("M1", "LINHA_DA_JORNADA", 29.5)
    v.tn = [5.3, 11.9, 18.5]
    v.ny = [0.20, 0.46, 0.72]
    v.scenes = [(0, 4.4, "Abertura"), (4.4, 11.0, "Fase 1"), (11.0, 17.6, "Fase 2"), (17.6, 24.9, "Fase Perene"), (24.9, 29.5, "Assinatura")]
    return v


def m1_assets(v):
    A = v.A
    A["intro_lab"] = text_img("NÚCLEO VIV", F_LABEL, 64, CREAM, tracking=0.35)
    A["intro"] = block("A jornada\ndo paciente", F_BODY, 190, OFFWHITE, "c")
    A["ph"] = [(text_img(f["label"], F_LABEL, 66, CREAM, tracking=0.3),
                block(f["titulo"], F_TITLE, 156, OFFWHITE),
                block(f["defin"], F_BODY, 100, CREAM)) for f in FASES]


def m1_path(u):
    return W * (0.15 + 0.028 * math.sin(u * math.pi * 3.0 + 0.4)), H * (-0.02 + 1.04 * u)


def m1_render(v, t, frame, mode):
    A = v.A
    d = ImageDraw.Draw(frame, "RGBA")
    o = window(t, 0.35, 4.3, 0.45)
    if o > 0:
        r = px(30) * (1 - ease_out((t - 0.35) / 0.8))
        paste(frame, A["sym_small"], W / 2, H * 0.36 + r, o)
        paste(frame, A["intro_lab"], W / 2, H * 0.455 + r, o)
        put(frame, A["intro"], W / 2, H * 0.482 + r, o, "c")
    nu = [(y + 0.02) / 1.04 for y in v.ny]
    seg = [(4.4, 5.3, 0, nu[0]), (11.0, 11.9, nu[0], nu[1]), (17.6, 18.5, nu[1], nu[2]), (24.1, 24.8, nu[2], 1.0)]
    u = 0.0
    for a, b, u0, u1 in seg:
        if t >= a:
            u = u0 + (u1 - u0) * ease_io((t - a) / (b - a))
    fa = 1 - ramp(t, 24.8, 25.3)
    if u > 0 and fa > 0:
        n = max(2, int(500 * u))
        pts = [m1_path(u * k / (n - 1)) for k in range(n)]
        d.line(pts, fill=CREAM + (int(235 * fa),), width=px(9), joint="curve")
        hx, hy = pts[-1]
        rr = px(15)
        d.ellipse([hx - rr, hy - rr, hx + rr, hy + rr], fill=OFFWHITE + (int(255 * fa),))
    for i in range(3):
        tn = v.tn[i]
        if t < tn or fa <= 0:
            continue
        nx, ny = m1_path(nu[i])
        k = ease_out((t - tn) / 0.45)
        act = window(t, tn, tn + 5.5, 0.3)
        if t - tn < 1.2:
            rr = px(34 + 100 * ease_out((t - tn) / 1.2))
            d.ellipse([nx - rr, ny - rr, nx + rr, ny + rr], outline=CREAM + (int(200 * (1 - clamp((t - tn) / 1.2)) * fa),), width=px(4))
        rr = px(34) * k
        d.ellipse([nx - rr, ny - rr, nx + rr, ny + rr], fill=GREEN + (255,), outline=OFFWHITE + (int(255 * fa),), width=px(8))
        ri = px(15) * k
        d.ellipse([nx - ri, ny - ri, nx + ri, ny + ri], fill=(OFFWHITE if act > 0.5 else CREAM) + (int(255 * fa),))
        li, ti, di = A["ph"][i]
        x = W * 0.27
        put(frame, li, x, ny - px(26), ramp(t, tn + 0.1, tn + 0.5) * fa * (0.7 + 0.3 * act))
        o1 = window(t, tn + 0.2, tn + 5.6, FADE)
        put(frame, ti, x + px(40) * (1 - ease_out((t - tn - 0.2) / 0.7)), ny + px(90), o1)
        o2 = window(t, tn + 0.9, tn + 5.6, FADE)
        put(frame, di, x + px(40) * (1 - ease_out((t - tn - 0.9) / 0.7)), ny + px(90) + ti.height - 2 * ti.info["pad"] + px(64), o2)
    lockup(frame, A, t, 25.1, 29.3, sig=True)


# ---------------------------------------------------------------- M2 · três fases (cartões)
def make_m2():
    v = V("M2", "TRES_FASES", 27.4)
    v.ct = [4.5, 10.5, 16.5]
    v.scenes = [(0, 4.5, "Abertura"), (4.5, 10.5, "Fase 1"), (10.5, 16.5, "Fase 2"), (16.5, 22.5, "Fase Perene"), (22.5, 27.4, "Assinatura")]
    return v


def m2_assets(v):
    A = v.A
    A["open"] = block("Não é uma clínica.\nÉ um processo.", F_BODY, 176, OFFWHITE, "c")
    A["cards"] = []
    for i, f in enumerate(FASES):
        fg, sub = (GREEN, GREEN) if i == 1 else (OFFWHITE, CREAM)
        A["cards"].append(dict(
            num=with_opacity(text_img(f["num"], F_LIGHT, 1500, fg), 0.13),
            label=text_img(f["label"], F_LABEL, 72, sub, tracking=0.32),
            titulo=block(f["titulo"], F_TITLE, 196, fg, "c"),
            frase=block(f["frase"], F_BODY, 120, sub, "c")))
    p = Image.open(os.path.join(R.IDV, "pattern", "03.png")).convert("RGBA")
    tw = px(2900)
    p = p.resize((tw, int(p.height * tw / p.width)), Image.LANCZOS)
    cb = Image.new("RGBA", (W, H), CREAM_BG + (255,))
    pat = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for yy in range(0, H, p.height):
        pat.alpha_composite(p, (0, yy))
    cb.alpha_composite(with_opacity(pat, 0.05))
    A["cream"] = cb


def m2_card(v, i, t, base):
    """Cartão i inteiro (fundo + conteúdo) no tempo t."""
    A, c = v.A, v.A["cards"][i]
    t0 = v.ct[i]
    layer = (A["cream"].copy() if i == 1 else base.copy())
    out = 1.0 if i < 2 else 1 - ramp(t, 22.1, 22.5)
    paste(layer, c["num"], W / 2, H * 0.30, ramp(t, t0 + 0.3, t0 + 1.0) * out)
    o1 = ramp(t, t0 + 0.55, t0 + 0.85) * out
    r1 = px(40) * (1 - ease_out((t - t0 - 0.55) / 0.7))
    paste(layer, c["label"], W / 2, H * 0.475 + r1, o1)
    put(layer, c["titulo"], W / 2, H * 0.505 + r1, o1, "c")
    o2 = ramp(t, t0 + 1.4, t0 + 1.7) * out
    r2 = px(30) * (1 - ease_out((t - t0 - 1.4) / 0.7))
    put(layer, c["frase"], W / 2, H * 0.505 + c["titulo"].height - 2 * c["titulo"].info["pad"] + px(90) + r2, o2, "c")
    d = ImageDraw.Draw(layer, "RGBA")                # progresso: 3 traços, o atual cheio
    fg = GREEN if i == 1 else OFFWHITE
    sw, gap = px(150), px(36)
    x0 = W / 2 - (3 * sw + 2 * gap) / 2
    for k in range(3):
        a = int((255 if k == i else 90) * o1)
        d.rounded_rectangle([x0 + k * (sw + gap), H * 0.9, x0 + k * (sw + gap) + sw, H * 0.9 + px(10)], px(5), fill=fg + (a,))
    return layer


def m2_render(v, t, frame, mode):
    A = v.A
    base = frame.copy()
    o = window(t, 0.4, 4.3, 0.45)
    if o > 0:
        r = px(30) * (1 - ease_out((t - 0.4) / 0.8))
        paste(frame, A["sym_small"], W / 2, H * 0.36 + r, o)
        put(frame, A["open"], W / 2, H * 0.47 + r, o, "c")
    for i in range(3):
        t0 = v.ct[i]
        if t < t0 or (i < 2 and t > v.ct[i + 1] + 0.7):
            continue
        k = ease_io((t - t0) / 0.65)
        off = int(H * (1 - k))
        card = m2_card(v, i, t, base)
        if off <= 0:
            frame.paste(card, (0, 0))
        else:
            frame.paste(card.crop((0, 0, W, H - off)), (0, off))
            ImageDraw.Draw(frame, "RGBA").line([(0, off), (W, off)], fill=CREAM + (255,), width=px(6))
    lockup(frame, A, t, 22.6, 27.2, sig=True)


# ---------------------------------------------------------------- T1 · a jornada (takes + capítulos)
def make_t1():
    v = V("T1", "A_JORNADA", 29.8)
    c0, cl = 5.8, 6.4
    v.ch = [(c0 + i * cl, c0 + (i + 1) * cl) for i in range(3)]
    for i in range(3):
        for j in range(2):
            sid, sug = T1_SLOTS[i * 2 + j]
            a = c0 + i * cl + j * cl / 2
            v.slots.append(dict(id=sid, a=round(a, 3), b=round(a + cl / 2, 3), sug=sug))
    v.scenes = [(0, 5.8, "Logo animada")] + [(a, b, FASES[i]["label"].title()) for i, (a, b) in enumerate(v.ch)] + [(25.0, 29.8, "Assinatura")]
    return v


def t1_assets(v):
    A = v.A
    A["ch"] = [(text_img(f["label"], F_LABEL, 76, CREAM, tracking=0.3, shadow=True),
                block(f["titulo"], F_TITLE, 190, OFFWHITE, shadow=True),
                block(f["frase"], F_BODY, 118, OFFWHITE, shadow=True)) for f in FASES]
    A["scrim"] = scrim_img(0.9, 0.42)


def t1_chapter(frame, v, i, o1=1.0, o2=1.0, r1=0, r2=0, parts=("titulo", "frase")):
    li, ti, pi = v.A["ch"][i]
    x = W * 0.08
    if "titulo" in parts:
        d = ImageDraw.Draw(frame, "RGBA")
        for k in range(3):
            cx, cy, rr = x + px(18) + k * px(72), H * 0.672 + r1, px(17)
            if k == i:
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=OFFWHITE + (int(255 * o1),))
            else:
                d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=CREAM + (int(170 * o1),), width=px(4))
        put(frame, li, x, H * 0.695 + r1, o1)
        put(frame, ti, x, H * 0.727 + r1, o1)
    if "frase" in parts:
        put(frame, pi, x, H * 0.727 + ti.height - 2 * ti.info["pad"] + px(70) + r2, o2)


def t1_render(v, t, frame, mode):
    A = v.A
    if mode in ("preview", "base"):
        lockup(frame, A, t, 0.3, 5.75, assemble=True)
        lockup(frame, A, t, 25.2, 29.55, sig=True)
    if mode == "preview":
        a0, b0 = v.ch[0][0], v.ch[-1][1]
        sop = min(ramp(t, a0 - XF / 2, a0 + XF / 2), 1 - ramp(t, b0 - XF / 2, b0 + XF / 2))
        if sop > 0:
            frame.alpha_composite(with_opacity(A["scrim"], sop))
        for i, (a, b) in enumerate(v.ch):
            if a <= t <= b:
                t1_chapter(frame, v, i, window(t, a + 0.25, b - 0.25, FADE), window(t, a + 1.3, b - 0.25, FADE),
                           px(36) * (1 - ease_out((t - a - 0.25) / 0.7)), px(30) * (1 - ease_out((t - a - 1.3) / 0.7)))


# ---------------------------------------------------------------- T2 · o espaço (bastidor silencioso)
def make_t2():
    v = V("T2", "O_ESPACO", 30.0)
    for i, (amb, act) in enumerate(T2_SLOTS):
        a = 0.4 + i * 4.2
        v.slots.append(dict(id=f"E{i + 1}", a=round(a, 3), b=round(a + 4.2, 3), sug=amb.lower(), amb=amb, act=act))
    v.scenes = [(s["a"] if i else 0, s["b"], s["amb"].title()) for i, s in enumerate(v.slots)] + [(25.6, 30.0, "Assinatura")]
    return v


def t2_assets(v):
    A = v.A
    A["cap"] = [(text_img(s["amb"], F_LABEL, 62, CREAM, tracking=0.3, shadow=True),
                 block(s["act"], F_BODY, 124, OFFWHITE, shadow=True)) for s in v.slots]
    A["scrim"] = scrim_img(0.78, 0.6)


def t2_caption(frame, v, i, o=1.0):
    amb, act = v.A["cap"][i]
    x = W * 0.08
    h = act.height - 2 * act.info["pad"]
    top = H * 0.9 - h
    ImageDraw.Draw(frame, "RGBA").line([(x, top - px(100)), (x, H * 0.9)], fill=CREAM + (int(225 * o),), width=px(6))
    put(frame, amb, x + px(50), top - px(100), o)
    put(frame, act, x + px(50), top, o)


def t2_render(v, t, frame, mode):
    A = v.A
    if mode in ("preview", "base"):
        lockup(frame, A, t, 25.8, 29.75, sig=True)
    if mode == "preview":
        sop = min(ramp(t, v.slots[0]["a"] - XF / 2, v.slots[0]["a"] + XF / 2), 1 - ramp(t, v.slots[-1]["b"] - XF / 2, v.slots[-1]["b"] + XF / 2))
        if sop > 0:
            frame.alpha_composite(with_opacity(A["scrim"], sop))
        for i, s in enumerate(v.slots):
            if s["a"] <= t <= s["b"]:
                t2_caption(frame, v, i, window(t, s["a"] + 0.45, s["b"] - 0.25, 0.25))


MAKE = {"M1": (make_m1, m1_assets, m1_render), "M2": (make_m2, m2_assets, m2_render),
        "T1": (make_t1, t1_assets, t1_render), "T2": (make_t2, t2_assets, t2_render)}

# ================================================================ render
G = {}


def render_frame(i):
    v, mode, fn = G["v"], G["mode"], G["fn"]
    t = i / FPS
    bg = bg_at(t, v.dur)
    if mode == "preview":
        s, a = v.slot_alpha(t)
        if s is not None and a > 0:
            ph = v.A["ph_imgs"][s["id"]]
            bg = Image.blend(bg, ph, a) if a < 1 else ph.copy()
    frame = bg.convert("RGBA")
    fn(v, t, frame, mode)
    return frame.convert("RGB").tobytes()


def encode(v, mode, path, frames=None):
    G["mode"] = mode
    if frames:
        for i in frames:
            Image.frombytes("RGB", (W, H), render_frame(i)).save(path.replace(".mp4", f"_f{i:04d}.png"))
        return
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
           "-profile:v", "high", "-level", "5.1", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-colorspace", "bt709", "-g", "30", "-movflags", "+faststart", path]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for k in range(0, v.n, 16):
            for b in pool.map(render_frame, range(k, min(v.n, k + 16))):
                ff.stdin.write(b)
    ff.stdin.close()
    ff.wait()
    print(path, flush=True)


def fr(sec):
    return int(round(sec * FPS))


def build(key, frames=None):
    mk, assets, fn = MAKE[key]
    v = mk()
    build_bg()
    v.A.update(common_assets())
    assets(v)
    v.A["ph_imgs"] = {s["id"]: placeholder(s) for s in v.slots}
    G["v"], G["fn"] = v, fn
    gdir, tdir = os.path.join(OUT, "grafica"), os.path.join(OUT, "textos")
    os.makedirs(gdir, exist_ok=True)
    os.makedirs(tdir, exist_ok=True)
    tag = f"{v.key}_{v.name}"
    tl = dict(nome=tag, frames=v.n, render=f"NucleoViv_TV_{tag}_2160x3840_30p_loop",
              cenas=[dict(nome=n, ini=fr(a), fim=fr(b)) for a, b, n in v.scenes], trilhas={}, slots=[])
    if not v.slots:
        f = f"grafica/NucleoViv_TV_{tag}_2160x3840_30p_loop.mp4"
        encode(v, "final", os.path.join(OUT, f), frames)
        tl["trilhas"]["1"] = [dict(arquivo=f, rec=c["ini"], src=c["ini"], dur=c["fim"] - c["ini"], nome=c["nome"]) for c in tl["cenas"]]
        return tl
    fb, fp = f"grafica/{tag}_BASE_fundo_e_logos.mp4", f"grafica/{tag}_PREVIEW_com_slots.mp4"
    encode(v, "preview", os.path.join(OUT, fp), frames)
    if frames:
        return tl
    encode(v, "base", os.path.join(OUT, fb))
    tl["preview"] = fp
    tl["trilhas"]["1"] = [dict(arquivo=fb, rec=0, src=0, dur=v.n, nome="Base: fundo e logos")]
    tl["slots"] = [dict(id=s["id"], rec=fr(s["a"]), dur=fr(s["b"]) - fr(s["a"]), sugestao=s["sug"]) for s in v.slots]

    def still(name, draw):
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw(im)
        p = f"textos/{tag}_{name}.png"
        im.save(os.path.join(OUT, p))
        return p

    v.A["scrim"].save(os.path.join(OUT, f"textos/{tag}_escurecimento.png"))
    a0, b0 = v.slots[0]["a"], v.slots[-1]["b"]
    tl["trilhas"]["3"] = [dict(arquivo=f"textos/{tag}_escurecimento.png", rec=fr(a0), src=0, dur=fr(b0) - fr(a0), nome="Escurecimento sob o texto")]
    t4, t5 = [], []
    if key == "T1":
        for i, (a, b) in enumerate(v.ch):
            p1 = still(f"fase{i + 1}_titulo", lambda im, i=i: t1_chapter(im, v, i, parts=("titulo",)))
            p2 = still(f"fase{i + 1}_frase", lambda im, i=i: t1_chapter(im, v, i, parts=("frase",)))
            t4.append(dict(arquivo=p1, rec=fr(a + 0.25), src=0, dur=fr(b - 0.25) - fr(a + 0.25), nome=FASES[i]["label"] + " título"))
            t5.append(dict(arquivo=p2, rec=fr(a + 1.3), src=0, dur=fr(b - 0.25) - fr(a + 1.3), nome=FASES[i]["label"] + " frase"))
    else:
        for i, s in enumerate(v.slots):
            p1 = still(f"legenda{i + 1}", lambda im, i=i: t2_caption(im, v, i))
            t4.append(dict(arquivo=p1, rec=fr(s["a"] + 0.45), src=0, dur=fr(s["b"] - 0.25) - fr(s["a"] + 0.45), nome="Legenda " + s["amb"].title()))
    tl["trilhas"]["4"] = t4
    if t5:
        tl["trilhas"]["5"] = t5
    return tl


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=["M1", "M2", "T1", "T2"])
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--frames", nargs="*", type=int)
    a = ap.parse_args()
    set_scale(a.scale)
    os.makedirs(OUT, exist_ok=True)
    spec_p = os.path.join(OUT, "timelines.json")
    spec = json.load(open(spec_p)) if os.path.exists(spec_p) else dict(projeto="NucleoViv_TV_Vertical", largura=2160, altura=3840, fps=FPS, timelines={})
    for k in a.only:
        tl = build(k, a.frames)
        if not a.frames and a.scale == 1.0:
            spec["timelines"][k] = tl
            json.dump(spec, open(spec_p, "w"), ensure_ascii=False, indent=1)
