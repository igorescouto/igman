#!/usr/bin/env python3
"""
Núcleo Viv · vídeos de TV (sem som, loop) — renderizador gráfico.

Gera, para cada variação:
  preview  : vídeo completo; onde entra take real aparece um slot sinalizado
  base     : só a camada gráfica (fundo, logo, aberturas/fechamentos), slots vazios
  overlay  : sequência PNG com alfa, só textos/escurecimento que vão POR CIMA dos takes
  roteiro  : JSON com os slots (tempo, o que filmar/usar, campo para o arquivo bruto)

Uso:
  python3 src/viv_render.py --var v1 v2 v3 --mode preview base overlay [--scale 0.5] [--frames 0 100 400]
"""
import argparse, json, math, os, subprocess, sys
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IDV = os.path.join(ROOT, "idv")
OUT = os.path.join(ROOT, "saida")
FPS = 30

# ---------- paleta (extraída dos PNGs da IDV) ----------
GREEN = (19, 53, 43)        # #13352B verde institucional
GREEN_DEEP = (10, 30, 24)   # sombra do verde, para escurecer sob texto
CREAM = (206, 201, 191)     # #CEC9BF creme do pattern
OFFWHITE = (242, 239, 233)  # #F2EFE9 texto principal (contraste ~11:1 sobre o verde)

FONT_DIR = "/usr/share/fonts/opentype/inter"
F_TITLE = os.path.join(FONT_DIR, "InterDisplay-Medium.otf")
F_BODY = os.path.join(FONT_DIR, "InterDisplay-Regular.otf")
F_LIGHT = os.path.join(FONT_DIR, "InterDisplay-Light.otf")
F_LABEL = os.path.join(FONT_DIR, "Inter-SemiBold.otf")
F_MONO = "/usr/share/fonts/truetype/jetbrains-mono/JetBrainsMono-Regular.ttf"

# ---------- utilidades ----------
SC = 1.0          # escala global (1.0 = 3840x2160)
W, H = 3840, 2160


def px(v):
    return int(round(v * SC))


def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def ease_out(x):
    x = clamp(x)
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = clamp(x)
    return 3 * x * x - 2 * x * x * x if x < 1 else 1.0


def ramp(t, a, b):
    """0 antes de a, 1 depois de b, suave entre os dois."""
    if b <= a:
        return 1.0 if t >= a else 0.0
    return ease_io((t - a) / (b - a))


def window(t, t_in, t_out, fade):
    """Opacidade de um bloco: entra em [t_in, t_in+fade], sai em [t_out-fade, t_out]."""
    return min(ramp(t, t_in, t_in + fade), 1 - ramp(t, t_out - fade, t_out))


def with_opacity(img, op):
    if op >= 0.999:
        return img
    r, g, b, a = img.split()
    a = a.point(lambda v: int(v * op))
    return Image.merge("RGBA", (r, g, b, a))


def font(path, size):
    return ImageFont.truetype(path, px(size))


def text_img(text, fpath, size, color=OFFWHITE, tracking=0.0, shadow=False):
    """Texto em RGBA justo. tracking em fração do corpo. shadow = sombra suave para cima de take."""
    f = font(fpath, size)
    tr = tracking * px(size)
    widths = [f.getlength(c) for c in text]
    tw = int(sum(widths) + tr * max(0, len(text) - 1)) + 2
    asc, desc = f.getmetrics()
    pad = px(40) if shadow else px(4)
    img = Image.new("RGBA", (tw + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = pad
    for c, w_ in zip(text, widths):
        d.text((x, pad), c, font=f, fill=color + (255,))
        x += w_ + tr
    if shadow:
        a = img.getchannel("A").filter(ImageFilter.GaussianBlur(px(14)))
        a = a.point(lambda v: int(v * 0.55))
        sh = Image.new("RGBA", img.size, GREEN_DEEP + (0,))
        sh.putalpha(a)
        sh.alpha_composite(img)
        img = sh
    img.info["pad"] = pad
    return img


def logo_asset(name, color, height):
    """Carrega PNG da IDV, recorta e recolore (mantém só o alfa)."""
    im = Image.open(os.path.join(IDV, "logo", name)).convert("RGBA")
    im = im.crop(im.getchannel("A").getbbox())
    sc = px(height) / im.height
    im = im.resize((max(1, int(im.width * sc)), px(height)), Image.LANCZOS)
    out = Image.new("RGBA", im.size, color + (0,))
    out.putalpha(im.getchannel("A"))
    return out


def symbol_pieces(color, height):
    """Símbolo (logo 03) dividido nas duas peças: asa esquerda e crescente direita.
    Retorna (esq, x_esq, dir, x_dir, largura_total) com posições relativas ao bbox do símbolo."""
    im = Image.open(os.path.join(IDV, "logo", "03.png")).convert("RGBA")
    bb = im.getchannel("A").getbbox()
    im = im.crop(bb)
    split = 1340 - bb[0]                     # coluna vazia entre as peças (medida)
    sc = px(height) / im.height
    full_w = int(im.width * sc)

    def piece(box):
        p = im.crop(box)
        p = p.resize((max(1, int(p.width * sc)), max(1, int(p.height * sc))), Image.LANCZOS)
        o = Image.new("RGBA", p.size, color + (0,))
        o.putalpha(p.getchannel("A"))
        return o

    left = piece((0, 0, split, im.height))
    right = piece((split, 0, im.width, im.height))
    return left, 0, right, int(split * sc), full_w


def paste(frame, img, cx, cy, op=1.0, anchor="c"):
    """Compõe img com opacidade; anchor 'c' centro, 'l' esquerda-meio (cx = borda esquerda)."""
    if op <= 0.003 or img is None:
        return
    im = with_opacity(img, op)
    pad = img.info.get("pad", 0)
    if anchor == "c":
        x = int(cx - im.width / 2)
    else:
        x = int(cx - pad)
    y = int(cy - im.height / 2)
    frame.alpha_composite(im, (max(x, 0), max(y, 0)),
                          (max(0, -x), max(0, -y)))


# ---------- fundo com pattern (loop perfeito: deriva senoidal com período = duração) ----------
_BG = None


def build_bg():
    global _BG
    p = Image.open(os.path.join(IDV, "pattern", "02.png")).convert("RGBA")  # pattern creme, fundo transparente
    tile_w = px(2900)
    p = p.resize((tile_w, int(p.height * tile_w / p.width)), Image.LANCZOS)
    margin = px(240)
    cw, ch = W + 2 * margin, H + 2 * margin
    big = Image.new("RGBA", (cw, ch), GREEN + (255,))
    pat = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for yy in range(0, ch, p.height):
        for xx in range(0, cw, p.width):
            pat.alpha_composite(p, (xx, yy))
    big.alpha_composite(with_opacity(pat, 0.075))
    # vinheta muito leve para dar profundidade (não interfere no contraste do centro)
    yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32)
    d = np.sqrt(((xx - cw / 2) / (cw / 2)) ** 2 + ((yy - ch / 2) / (ch / 2)) ** 2)
    v = np.clip((d - 0.55) / 0.9, 0, 1) * 0.32
    arr = np.array(big).astype(np.float32)
    arr[..., :3] = arr[..., :3] * (1 - v[..., None]) + np.array(GREEN_DEEP, np.float32) * v[..., None]
    _BG = (Image.fromarray(arr.astype(np.uint8)).convert("RGB"), margin)


def bg_at(t, dur):
    big, m = _BG
    ph = 2 * math.pi * t / dur
    ox = m + int(m * 0.8 * math.sin(ph))
    oy = m + int(m * 0.5 * math.sin(2 * ph))
    return big.crop((ox, oy, ox + W, oy + H))


# ---------- escurecimento sob texto (para cima de take) ----------
_SCRIM = {}


def scrim(kind):
    if kind in _SCRIM:
        return _SCRIM[kind]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    if kind == "chapter":     # base inferior-esquerda, mais forte
        a = np.clip((yy / H - 0.35) / 0.65, 0, 1) ** 1.3 * 0.86
        a = np.maximum(a, 0.18)
        a *= np.clip(1.25 - xx / W * 0.55, 0, 1)
    else:                      # legenda discreta no canto inferior
        a = np.clip((yy / H - 0.6) / 0.4, 0, 1) ** 1.6 * 0.72
        a *= np.clip(1.2 - xx / W * 0.7, 0, 1)
    img = Image.new("RGBA", (W, H), GREEN_DEEP + (0,))
    img.putalpha(Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8)))
    _SCRIM[kind] = img
    return img


# ---------- placeholder de take (só no preview) ----------
def placeholder(slot):
    im = Image.new("RGB", (W, H), (34, 44, 41))
    d = ImageDraw.Draw(im)
    # listras diagonais discretas = "não é arte final"
    for k in range(-H, W, px(90)):
        d.line([(k, 0), (k + H, H)], fill=(38, 49, 46), width=px(30))
    m = px(150)
    dash = px(40)
    col = (120, 135, 128)
    for x in range(m, W - m, dash * 2):
        d.line([(x, m), (min(x + dash, W - m), m)], fill=col, width=px(5))
        d.line([(x, H - m), (min(x + dash, W - m), H - m)], fill=col, width=px(5))
    for y in range(m, H - m, dash * 2):
        d.line([(m, y), (m, min(y + dash, H - m))], fill=col, width=px(5))
        d.line([(W - m, y), (W - m, min(y + dash, H - m))], fill=col, width=px(5))
    f1 = ImageFont.truetype(F_MONO, px(60))
    f2 = ImageFont.truetype(F_MONO, px(84))
    f3 = ImageFont.truetype(F_MONO, px(52))
    d.text((m + px(70), m + px(60)), f"TAKE REAL · SLOT {slot['id']} · {slot['end'] - slot['start']:.1f}s",
           font=f1, fill=(170, 182, 176))
    d.text((m + px(70), m + px(170)), slot["descricao"], font=f2, fill=(205, 214, 209))
    d.text((m + px(70), m + px(300)), slot.get("sugestao", ""), font=f3, fill=(150, 162, 156))
    return im


# =====================================================================
#  DEFINIÇÃO DAS VARIAÇÕES
# =====================================================================
FADE = 0.3          # entrada/saída de texto
XF = 0.5            # dissolve entre takes / entre gráfico e take


class Var:
    def __init__(self, key, name, dur):
        self.key, self.name, self.dur = key, name, dur
        self.slots = []
        self.assets = {}

    def slot_alpha(self, t):
        """(slot ativo, alfa do take) com dissolve XF centrado nas bordas."""
        best = (None, 0.0)
        for s in self.slots:
            a = min(ramp(t, s["start"] - XF / 2, s["start"] + XF / 2),
                    1 - ramp(t, s["end"] - XF / 2, s["end"] + XF / 2))
            # entre dois slots colados, o segundo assume (cross dissolve)
            if a > 0 and (best[0] is None or s["start"] > best[0]["start"]):
                best = (s, a if best[0] is None else 1.0)
        return best


# ---------------- V1 · A JORNADA ----------------
def make_v1():
    v = Var("v1", "A_JORNADA", 29.8)
    chapters = [
        ("FASE 1", "Emagrecimento com método", "Músculo preservado desde o início."),
        ("FASE 2", "Estrutura e contorno corporal", "Primeiro gordura, depois músculo, depois pele."),
        ("FASE PERENE", "Manutenção", "Manter também é tratamento."),
    ]
    takes = [
        ("1A", "Avaliação de composição corporal", "bioimpedância / paciente na balança de composição; plano médio, câmera parada"),
        ("1B", "Medida de circunferência ou força", "fita métrica na cintura ou dinamômetro na mão; detalhe, foco nas mãos"),
        ("2A", "Avaliação dedicada de contorno", "médico avaliando / marcação corporal discreta; plano fechado"),
        ("2B", "Consultório: conversa sobre o plano", "médico e paciente à mesa, de costas ou perfil; luz suave"),
        ("PA", "Acompanhamento / retorno", "recepção acolhendo paciente ou agenda de retorno; plano aberto"),
        ("PB", "Ambiente da clínica em calma", "detalhe do ambiente: planta, luz, sala de espera vazia; movimento lento"),
    ]
    c0, cl = 5.8, 6.4
    for i, (lab, title, phrase) in enumerate(chapters):
        c = c0 + i * cl
        for j in range(2):
            tk = takes[i * 2 + j]
            v.slots.append({"id": tk[0], "start": round(c + j * cl / 2, 3), "end": round(c + (j + 1) * cl / 2, 3),
                            "descricao": tk[1], "sugestao": tk[2], "arquivo": "", "entrada_s": 0.0, "velocidade": 1.0})
    v.chapters = [(lab, title, phrase, c0 + i * cl, c0 + (i + 1) * cl) for i, (lab, title, phrase) in enumerate(chapters)]
    return v


# ---------------- V2 · BASTIDOR SILENCIOSO ----------------
def make_v2():
    v = Var("v2", "BASTIDOR_SILENCIOSO", 30.0)
    caps = [
        ("RECEPÇÃO", "Acolhimento desde a chegada", "paciente chegando / recepcionista; plano aberto, câmera parada ou travelling lento"),
        ("SALA DE AVALIAÇÃO", "Avaliação de composição corporal", "bioimpedância; plano médio, contemplativo"),
        ("SALA DE AVALIAÇÃO", "Medida de circunferência", "fita métrica; detalhe nas mãos"),
        ("SALA DE AVALIAÇÃO", "Teste de força muscular", "dinamômetro de preensão; detalhe"),
        ("CONSULTÓRIO", "Consulta individualizada", "médico e paciente conversando; perfil, sem rosto em close"),
        ("SALA DE ESPERA", "Cuidado em cada detalhe", "detalhe do ambiente: luz, plantas, poltrona; movimento muito lento"),
    ]
    s0, sl = 0.4, 4.2
    for i, (amb, act, sug) in enumerate(caps):
        v.slots.append({"id": f"B{i + 1}", "start": round(s0 + i * sl, 3), "end": round(s0 + (i + 1) * sl, 3),
                        "descricao": act, "ambiente": amb, "sugestao": sug, "arquivo": "", "entrada_s": 0.0, "velocidade": 1.0})
    return v


# ---------------- V3 · MOTION PURO ----------------
def make_v3():
    v = Var("v3", "MOTION_PURO", 29.5)
    v.phases = [
        ("FASE 1", "Emagrecimento com método", "Composição, circunferência e força avaliadas.", 0.20),
        ("FASE 2", "Estrutura e contorno corporal", "Gordura, músculo e pele, nessa ordem.", 0.50),
        ("FASE PERENE", "Manutenção", "Manter o resultado também é tratamento.", 0.80),
    ]
    return v


VARS = {"v1": make_v1, "v2": make_v2, "v3": make_v3}


# =====================================================================
#  ASSETS (pré-render uma vez, compartilhados com os workers via fork)
# =====================================================================
def build_assets(v):
    A = v.assets
    A["sym_l"], A["sym_lx"], A["sym_r"], A["sym_rx"], A["sym_w"] = symbol_pieces(OFFWHITE, 620)
    A["wordmark"] = logo_asset("09.png", OFFWHITE, 150)               # "V Í V"
    A["sub"] = text_img("NÚCLEO DE MEDICINA INTEGRATIVA", F_LABEL, 50, CREAM, tracking=0.32)
    A["sig"] = text_img("Bem-estar em cada detalhe", F_LIGHT, 118, OFFWHITE)
    A["sym_small"] = logo_asset("03.png", OFFWHITE, 300)
    if v.key == "v1":
        A["ch"] = []
        for lab, title, phrase, a, b in v.chapters:
            A["ch"].append((text_img(lab, F_LABEL, 78, CREAM, tracking=0.3, shadow=True),
                            text_img(title, F_TITLE, 190, OFFWHITE, shadow=True),
                            text_img(phrase, F_BODY, 118, OFFWHITE, shadow=True)))
    if v.key == "v2":
        A["cap"] = [(text_img(s["ambiente"], F_LABEL, 62, CREAM, tracking=0.3, shadow=True),
                     text_img(s["descricao"], F_BODY, 112, OFFWHITE, shadow=True)) for s in v.slots]
    if v.key == "v3":
        A["intro"] = text_img("A jornada do paciente", F_BODY, 150, OFFWHITE)
        A["intro_lab"] = text_img("NÚCLEO VIV", F_LABEL, 62, CREAM, tracking=0.35)
        A["ph"] = [(text_img(l, F_LABEL, 66, CREAM, tracking=0.3),
                    text_img(n, F_TITLE, 176, OFFWHITE),
                    text_img(d, F_BODY, 112, CREAM)) for l, n, d, _ in v.phases]
    A["ph_imgs"] = {s["id"]: placeholder(s) for s in v.slots}
    A["mark_line"] = None


# =====================================================================
#  CENAS
# =====================================================================
def lockup(frame, A, t, t_in, t_out, second="sub", assemble=False):
    """Símbolo + VIV + (subtítulo | assinatura). assemble=True: símbolo monta no centro e sobe."""
    out = 1 - ramp(t, t_out - 0.45, t_out)
    sw, sh = A["sym_w"], A["sym_l"].height
    final_cy = H * 0.355
    final_sc = 0.62
    if assemble:
        # 1) peças entram de lados opostos e encaixam no centro
        k = ease_out((t - t_in) / 1.2)
        op = clamp((t - t_in) / 0.6) * out
        # 2) símbolo sobe e reduz
        up = ease_io((t - (t_in + 1.35)) / 0.8)
        cy = H / 2 + (final_cy - H / 2) * up
        sc = 1 + (final_sc - 1) * up
        off = px(260) * (1 - k)
        tw = sw * sc
        l = A["sym_l"] if sc == 1 else A["sym_l"].resize((max(1, int(A["sym_l"].width * sc)), max(1, int(sh * sc))), Image.BILINEAR)
        r = A["sym_r"] if sc == 1 else A["sym_r"].resize((max(1, int(A["sym_r"].width * sc)), max(1, int(A["sym_r"].height * sc))), Image.BILINEAR)
        x0 = W / 2 - tw / 2
        top = cy - sh * sc / 2
        if op > 0:
            frame.alpha_composite(with_opacity(l, op), (int(x0 - off), int(top)))
            frame.alpha_composite(with_opacity(r, op), (int(x0 + A["sym_rx"] * sc + off), int(top + (sh * sc - r.height))))
        t_txt = t_in + 2.0
    else:
        op = ramp(t, t_in, t_in + 0.5) * out
        l = A["sym_l"].resize((int(A["sym_l"].width * final_sc), int(sh * final_sc)), Image.BILINEAR)
        r = A["sym_r"].resize((int(A["sym_r"].width * final_sc), int(A["sym_r"].height * final_sc)), Image.BILINEAR)
        tw = sw * final_sc
        x0 = W / 2 - tw / 2
        rise = px(30) * (1 - ease_out((t - t_in) / 0.6))
        top = final_cy - sh * final_sc / 2 + rise
        if op > 0:
            frame.alpha_composite(with_opacity(l, op), (int(x0), int(top)))
            frame.alpha_composite(with_opacity(r, op), (int(x0 + A["sym_rx"] * final_sc), int(top + sh * final_sc - r.height)))
        t_txt = t_in + 0.25
    wm_op = ramp(t, t_txt, t_txt + 0.5) * out
    rise = px(24) * (1 - ease_out((t - t_txt) / 0.6))
    paste(frame, A["wordmark"], W / 2, H * 0.60 + rise, wm_op)
    s_op = ramp(t, t_txt + 0.3, t_txt + 0.8) * out
    rise2 = px(24) * (1 - ease_out((t - t_txt - 0.3) / 0.6))
    if second == "sub":
        paste(frame, A["sub"], W / 2, H * 0.705 + rise2, s_op)
    else:
        paste(frame, A["sub"], W / 2, H * 0.685, s_op * 0.9)
        paste(frame, A["sig"], W / 2, H * 0.80 + rise2, s_op)


def render_v1(v, t, mode, frame):
    A = v.assets
    g = mode in ("preview", "base")
    if g:
        lockup(frame, A, t, 0.3, 5.75, "sub", assemble=True)
        lockup(frame, A, t, 25.2, 29.55, "sig")
    if mode in ("preview", "overlay"):
        a0, b0 = v.chapters[0][3], v.chapters[-1][4]
        sop = min(ramp(t, a0 - XF / 2, a0 + XF / 2), 1 - ramp(t, b0 - XF / 2, b0 + XF / 2))
        if sop > 0:
            frame.alpha_composite(with_opacity(scrim("chapter"), sop))
        for i, (lab, title, phrase, a, b) in enumerate(v.chapters):
            if not (a <= t <= b):
                continue
            li, ti, pi = A["ch"][i]
            x = W * 0.085
            o1 = window(t, a + 0.25, b - 0.25, FADE)
            r1 = px(36) * (1 - ease_out((t - a - 0.25) / 0.7))
            paste(frame, li, x, H * 0.585 + r1, o1, "l")
            paste(frame, ti, x, H * 0.675 + r1, o1, "l")
            o2 = window(t, a + 1.3, b - 0.25, FADE)
            r2 = px(30) * (1 - ease_out((t - a - 1.3) / 0.7))
            paste(frame, pi, x, H * 0.80 + r2, o2, "l")
            # marcador de progresso da jornada (3 pontos, o atual preenchido)
            for k in range(3):
                cx = x + px(18) + k * px(70)
                cy = H * 0.515 + r1
                d = ImageDraw.Draw(frame)
                rr = px(16)
                col = OFFWHITE + (int(255 * o1),) if k == i else CREAM + (int(150 * o1),)
                if k == i:
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=col)
                else:
                    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=col, width=px(4))


def render_v2(v, t, mode, frame):
    A = v.assets
    if mode in ("preview", "base"):
        lockup(frame, A, t, 25.8, 29.75, "sig")
    if mode in ("preview", "overlay"):
        first, last = v.slots[0], v.slots[-1]
        sop = min(ramp(t, first["start"] - XF / 2, first["start"] + XF / 2),
                  1 - ramp(t, last["end"] - XF / 2, last["end"] + XF / 2))
        if sop > 0:
            frame.alpha_composite(with_opacity(scrim("caption"), sop))
        for i, s in enumerate(v.slots):
            a, b = s["start"], s["end"]
            if not (a <= t <= b):
                continue
            amb, act = A["cap"][i]
            o = window(t, a + 0.45, b - 0.25, 0.25)
            x = W * 0.07
            d = ImageDraw.Draw(frame)
            # filete vertical à esquerda, assinatura visual discreta
            lh = px(150)
            ly = H * 0.835
            d.line([(x, ly - lh / 2), (x, ly + lh / 2)], fill=CREAM + (int(220 * o),), width=px(5))
            paste(frame, amb, x + px(44), H * 0.805, o, "l")
            paste(frame, act, x + px(44), H * 0.862, o, "l")


def v3_path(u):
    """Linha da jornada: atravessa a tela com onda suave. u em [0,1] -> (x,y)."""
    x = -0.03 + 1.06 * u
    y = 0.40 + 0.045 * math.sin(u * math.pi * 2.0 + 0.6)
    return x * W, y * H


def render_v3(v, t, mode, frame):
    A = v.assets
    d = ImageDraw.Draw(frame)
    # intro: símbolo + "A jornada do paciente"
    o = window(t, 0.35, 4.4, 0.45)
    if o > 0:
        r = px(30) * (1 - ease_out((t - 0.35) / 0.8))
        paste(frame, A["sym_small"], W / 2, H * 0.36 + r, o)
        paste(frame, A["intro_lab"], W / 2, H * 0.56 + r, o)
        paste(frame, A["intro"], W / 2, H * 0.645 + r, o)
    # linha: progressão por trechos (para em cada fase)
    us = [p[3] for p in v.phases]
    def u_of(x_target):  # inverte x(u)
        return (x_target + 0.03) / 1.06
    nodes_u = [u_of(x) for x in us]
    seg = [(4.5, 5.5, 0.0, nodes_u[0]), (10.9, 11.9, nodes_u[0], nodes_u[1]),
           (17.4, 18.4, nodes_u[1], nodes_u[2]), (23.9, 24.6, nodes_u[2], 1.0)]
    u = 0.0
    for a, b, u0, u1 in seg:
        if t >= a:
            u = u0 + (u1 - u0) * ease_io((t - a) / (b - a))
    fade_all = 1 - ramp(t, 24.6, 25.1)
    if u > 0 and fade_all > 0:
        n = max(2, int(400 * u))
        pts = [v3_path(u * k / (n - 1)) for k in range(n)]
        d.line(pts, fill=CREAM + (int(235 * fade_all),), width=px(9), joint="curve")
        # ponta luminosa
        hx, hy = pts[-1]
        if t < 24.7:
            rr = px(14)
            d.ellipse([hx - rr, hy - rr, hx + rr, hy + rr], fill=OFFWHITE + (int(255 * fade_all),))
    # nós e textos
    t_nodes = [5.5, 11.9, 18.4]
    for i, (lab, name, deff, xn) in enumerate(v.phases):
        tn = t_nodes[i]
        if t < tn or fade_all <= 0:
            continue
        nx, ny = v3_path(nodes_u[i])
        k = ease_out((t - tn) / 0.45)
        active = window(t, tn, tn + 5.4, 0.3)
        # anel expandindo no momento da chegada
        if t - tn < 1.2:
            rr = px(30 + 90 * ease_out((t - tn) / 1.2))
            ao = int(200 * (1 - clamp((t - tn) / 1.2)) * fade_all)
            d.ellipse([nx - rr, ny - rr, nx + rr, ny + rr], outline=CREAM + (ao,), width=px(4))
        rr = px(30) * k
        d.ellipse([nx - rr, ny - rr, nx + rr, ny + rr], fill=GREEN + (255,),
                  outline=OFFWHITE + (int(255 * fade_all),), width=px(7))
        ri = px(13) * k
        d.ellipse([nx - ri, ny - ri, nx + ri, ny + ri], fill=(OFFWHITE if active > 0.5 else CREAM) + (int(255 * fade_all),))
        li, ni, di = A["ph"][i]
        # rótulo da fase fica acima do nó depois de revelado
        paste(frame, li, nx, ny - px(110), ramp(t, tn + 0.1, tn + 0.5) * fade_all * (0.75 + 0.25 * active))
        # bloco grande centralizado (uma fase por vez)
        o1 = window(t, tn + 0.2, tn + 5.5, FADE)
        r1 = px(36) * (1 - ease_out((t - tn - 0.2) / 0.7))
        paste(frame, ni, W / 2, H * 0.635 + r1, o1)
        o2 = window(t, tn + 0.9, tn + 5.5, FADE)
        r2 = px(30) * (1 - ease_out((t - tn - 0.9) / 0.7))
        paste(frame, di, W / 2, H * 0.745 + r2, o2)
    # fechamento
    lockup(frame, A, t, 25.0, 29.3, "sig")


RENDER = {"v1": render_v1, "v2": render_v2, "v3": render_v3}

# =====================================================================
#  FRAME
# =====================================================================
G = {}


def render_frame(i):
    v, mode = G["v"], G["mode"]
    t = i / FPS
    if mode == "overlay":
        frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    else:
        bg = bg_at(t, v.dur)
        if mode == "preview":
            s, a = v.slot_alpha(t)
            if s is not None and a > 0:
                bg = Image.blend(bg, A_ph(v, s), a) if a < 1 else A_ph(v, s).copy()
        frame = bg.convert("RGBA")
    RENDER[v.key](v, t, mode, frame)
    if mode == "overlay":
        return frame
    return frame.convert("RGB").tobytes()


def A_ph(v, s):
    return v.assets["ph_imgs"][s["id"]]


def init_worker():
    pass


def run(var_key, mode, scale, only_frames=None, out_dir=OUT, crf=17):
    global SC, W, H
    SC = scale
    W, H = int(3840 * SC), int(2160 * SC)
    _SCRIM.clear()
    v = VARS[var_key]()
    build_bg()
    build_assets(v)
    G["v"], G["mode"] = v, mode
    n = int(round(v.dur * FPS))
    tag = f"{v.key.upper()}_{v.name}"
    res = f"{W}x{H}"
    os.makedirs(out_dir, exist_ok=True)
    if only_frames:
        for i in only_frames:
            r = render_frame(i)
            im = r if isinstance(r, Image.Image) else Image.frombytes("RGB", (W, H), r)
            p = os.path.join(out_dir, f"{tag}_{mode}_f{i:04d}.png")
            im.save(p)
            print(p)
        return v
    if mode == "overlay":
        d = os.path.join(out_dir, f"{tag}_OVERLAY_{res}")
        os.makedirs(d, exist_ok=True)
        with Pool(os.cpu_count()) as pool:
            for i, im in enumerate(pool.imap(render_frame, range(n), chunksize=4)):
                bb = im.getbbox()
                im.save(os.path.join(d, f"{tag}_OVERLAY_{i:04d}.png"), optimize=False, compress_level=6)
        print(d)
        return v
    suffix = "PREVIEW_com_slots" if (mode == "preview" and v.slots) else ("BASE_grafica" if mode == "base" else "FINAL")
    path = os.path.join(out_dir, f"NucleoViv_TV_{tag}_{suffix}_{res}_30p_loop.mp4")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", res, "-r", str(FPS),
           "-i", "-", "-an", "-c:v", "libx264", "-preset", "medium", "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "5.1" if W > 1920 else "4.1",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
           "-g", "30", "-movflags", "+faststart", path]
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool(os.cpu_count()) as pool:
        for b in pool.imap(render_frame, range(n), chunksize=4):
            ff.stdin.write(b)
    ff.stdin.close()
    ff.wait()
    print(path)
    return v


def write_roteiro(v):
    p = os.path.join(ROOT, "roteiro", f"{v.key}_{v.name.lower()}.json")
    old = {}
    if os.path.exists(p):  # preserva arquivos já preenchidos pelo editor
        for s in json.load(open(p)).get("slots", []):
            old[s["id"]] = s
    slots = []
    for s in v.slots:
        s = dict(s)
        if s["id"] in old:
            for k in ("arquivo", "entrada_s", "velocidade"):
                s[k] = old[s["id"]].get(k, s[k])
        slots.append(s)
    json.dump({"variacao": v.key, "nome": v.name, "duracao_s": v.dur, "fps": FPS, "dissolve_s": XF,
               "slots": slots}, open(p, "w"), ensure_ascii=False, indent=2)
    print(p)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--var", nargs="+", default=["v1", "v2", "v3"])
    ap.add_argument("--mode", nargs="+", default=["preview"])
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--frames", nargs="*", type=int)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    for k in a.var:
        for m in a.mode:
            if m in ("base", "overlay") and k == "v3":
                continue
            v = run(k, m, a.scale, a.frames, a.out)
        if v.slots and not a.frames:
            write_roteiro(v)
