#!/usr/bin/env python3
"""
Monta o vídeo final de V1 / V2 juntando:
  camada BASE (gráfica)  +  takes reais nos slots do roteiro  +  OVERLAY (textos com alfa)
Só usa ffmpeg (não precisa do Resolve). Nunca altera os brutos: só lê.

Uso:
  python3 src/montar_com_brutos.py --var v1 --brutos "/Volumes/Extreme SSD/.../BRUTOS" [--auto]

  --auto  preenche slots sem "arquivo" no roteiro com os clipes da pasta, em ordem alfabética
          (rascunho rápido; o ideal é escolher cada take no roteiro/*.json).
Saídas em saida/:  NucleoViv_TV_V1_A_JORNADA_FINAL_3840x2160_30p_loop.mp4 (+ versão 1920x1080)
"""
import argparse, glob, json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_EXT = (".mov", ".mp4", ".mxf", ".m4v", ".avi", ".mts", ".braw", ".r3d")


def probe_dur(p):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                         capture_output=True, text=True).stdout.strip()
    try:
        return float(out)
    except ValueError:
        return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--var", required=True, choices=["v1", "v2"])
    ap.add_argument("--brutos", required=True)
    ap.add_argument("--saida", default=os.path.join(ROOT, "saida"))
    ap.add_argument("--destino", default=None, help="pasta do vídeo final (padrão: a mesma de --saida)")
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--crf", default="17")
    a = ap.parse_args()

    rot_path = glob.glob(os.path.join(ROOT, "roteiro", f"{a.var}_*.json"))[0]
    rot = json.load(open(rot_path))
    tag = f"{a.var.upper()}_{rot['nome']}"
    base = glob.glob(os.path.join(a.saida, f"NucleoViv_TV_{tag}_BASE_grafica_*.mp4"))
    ovl = glob.glob(os.path.join(a.saida, f"{tag}_OVERLAY_*"))
    if not base or not ovl:
        sys.exit("Faltam a BASE e/ou o OVERLAY em saida/. Rode antes: python3 src/viv_render.py --var %s --mode base overlay" % a.var)
    base, ovl = sorted(base)[-1], sorted(ovl)[-1]
    W, H = [int(x) for x in base.rsplit("_", 3)[-3].split("x")] if "x" in base.rsplit("_", 3)[-3] else (3840, 2160)
    fps, XF, dur = rot["fps"], rot["dissolve_s"], rot["duracao_s"]

    clips = sorted(f for f in os.listdir(a.brutos) if f.lower().endswith(VIDEO_EXT) and not f.startswith("."))
    auto_i = 0
    slots = rot["slots"]
    log = []
    for s in slots:
        if not s.get("arquivo"):
            if not a.auto:
                sys.exit(f"Slot {s['id']} ({s['descricao']}) sem arquivo no {rot_path}. Preencha ou use --auto.")
            if auto_i >= len(clips):
                sys.exit("Brutos insuficientes para --auto.")
            s["arquivo"] = clips[auto_i]
            auto_i += 1
            d = probe_dur(os.path.join(a.brutos, s["arquivo"]))
            need = (s["end"] - s["start"] + XF) * s.get("velocidade", 1.0)
            s["entrada_s"] = max(0.0, (d - need) / 2)       # meio do clipe: costuma ser o trecho mais estável
            log.append(f"AUTO slot {s['id']}: {s['arquivo']} a partir de {s['entrada_s']:.2f}s")

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", base]
    fc = []
    for k, s in enumerate(slots):
        sp = float(s.get("velocidade", 1.0))
        D = s["end"] - s["start"] + XF
        cmd += ["-ss", f"{s['entrada_s']:.3f}", "-t", f"{D * sp + 0.5:.3f}", "-i", os.path.join(a.brutos, s["arquivo"])]
        nxt = slots[k + 1] if k + 1 < len(slots) else None
        adjacent = nxt is not None and abs(nxt["start"] - s["end"]) < 1e-3
        chain = (f"[{k + 1}:v]setpts=(PTS-STARTPTS)/{sp},fps={fps},"
                 f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
                 f"tpad=stop_mode=clone:stop_duration=5,trim=duration={D:.3f},format=yuva420p,"
                 f"fade=t=in:st=0:d={XF}:alpha=1")
        if not adjacent:
            chain += f",fade=t=out:st={D - XF:.3f}:d={XF}:alpha=1"
        chain += f",setpts=PTS+{s['start'] - XF / 2:.3f}/TB[t{k}]"
        fc.append(chain)
    seq = sorted(glob.glob(os.path.join(ovl, "*.png")))
    pattern = seq[0][:-8] + "%04d.png"
    cmd += ["-framerate", str(fps), "-i", pattern]
    last = "0:v"
    for k in range(len(slots)):
        fc.append(f"[{last}][t{k}]overlay=eof_action=pass:repeatlast=0[m{k}]")
        last = f"m{k}"
    fc.append(f"[{last}][{len(slots) + 1}:v]overlay=eof_action=pass,format=yuv420p,trim=duration={dur}[out]")
    out4k = os.path.join(a.destino or a.saida, f"NucleoViv_TV_{tag}_FINAL_{W}x{H}_30p_loop.mp4")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[out]", "-an", "-c:v", "libx264", "-preset", "medium",
            "-crf", a.crf, "-profile:v", "high", "-level", "5.1", "-g", "30", "-movflags", "+faststart", out4k]
    subprocess.run(cmd, check=True)
    out1080 = out4k.replace(f"{W}x{H}", "1920x1080")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out4k, "-vf", "scale=1920:1080:flags=lanczos",
                    "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-level", "4.1",
                    "-g", "30", "-movflags", "+faststart", out1080], check=True)
    for l in log:
        print(l)
    print(out4k)
    print(out1080)


if __name__ == "__main__":
    main()
