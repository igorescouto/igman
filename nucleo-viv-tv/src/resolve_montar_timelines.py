#!/usr/bin/env python3
"""
DaVinci Resolve (Studio ou free, 18+) — cria o projeto e as 3 timelines dos vídeos de TV do Núcleo Viv.

O que faz:
  * cria/abre o projeto "NucleoViv_TV_Loop" em 3840x2160, 30 fps
  * importa a BASE gráfica, o OVERLAY (sequência PNG com alfa) e os brutos indicados no roteiro
    (importar no Resolve só referencia os arquivos: nada é alterado, movido ou apagado nos brutos)
  * monta cada timeline:  V1 = base gráfica | V2 = takes nos slots | V3 = textos (overlay)
  * configura e enfileira o render: MP4 H.264, 3840x2160, 30p, SEM áudio

Como rodar:
  1) preencha config_caminhos.json (ao lado deste arquivo) e os campos "arquivo" de roteiro/*.json
  2) no Resolve: Workspace > Console > Py3 e execute:  exec(open(r"CAMINHO/src/resolve_montar_timelines.py").read())
     ou, fora do Resolve, com as variáveis de scripting configuradas:  python3 src/resolve_montar_timelines.py

Limites da API do Resolve (fazer à mão depois de rodar, 2 min):
  * dissolves entre takes: selecione os cortes da trilha V2 e Ctrl/Cmd+T (0,5 s, centralizado)
  * correção de cor dos brutos (se gravados em LOG) — não é possível via script
"""
import glob, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
ROOT = os.path.dirname(HERE)
CFG = json.load(open(os.path.join(HERE, "config_caminhos.json")))
BRUTOS = CFG["brutos"]
SAIDA = CFG.get("saida", "")
if not SAIDA or SAIDA.startswith("COLE"):
    SAIDA = os.path.join(ROOT, "saida")
if BRUTOS.startswith("COLE"):
    sys.exit("Preencha o caminho dos brutos em src/config_caminhos.json")
FPS = 30


def get_resolve():
    try:
        return resolve  # noqa: F821  (definido quando roda pelo console do Resolve)
    except NameError:
        pass
    try:
        import DaVinciResolveScript as dvr
    except ImportError:
        for p in [r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
                  "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
                  "/opt/resolve/Developer/Scripting/Modules"]:
            sys.path.append(p)
        import DaVinciResolveScript as dvr
    return dvr.scriptapp("Resolve")


def main():
    r = get_resolve()
    pm = r.GetProjectManager()
    proj = pm.LoadProject("NucleoViv_TV_Loop") or pm.CreateProject("NucleoViv_TV_Loop")
    for k, v in {"timelineResolutionWidth": "3840", "timelineResolutionHeight": "2160",
                 "timelineFrameRate": "30", "timelinePlaybackFrameRate": "30"}.items():
        proj.SetSetting(k, v)
    mp = proj.GetMediaPool()
    root = mp.GetRootFolder()

    for var in ("v1", "v2", "v3"):
        mp.SetCurrentFolder(root)
        folder = mp.AddSubFolder(root, var.upper())
        mp.SetCurrentFolder(folder)
        if var == "v3":
            f = sorted(glob.glob(os.path.join(SAIDA, "NucleoViv_TV_V3_*FINAL_3840x2160*.mp4")))
            item = mp.ImportMedia(f)[0]
            tl = mp.CreateEmptyTimeline("V3_MOTION_PURO")
            mp.AppendToTimeline([{"mediaPoolItem": item, "trackIndex": 1}])
            queue_render(proj, tl, "NucleoViv_TV_V3_MOTION_PURO_FINAL_3840x2160_30p_loop")
            continue

        rot = json.load(open(glob.glob(os.path.join(ROOT, "roteiro", f"{var}_*.json"))[0]))
        tag = f"{var.upper()}_{rot['nome']}"
        base = mp.ImportMedia(sorted(glob.glob(os.path.join(SAIDA, f"NucleoViv_TV_{tag}_BASE_grafica_3840x2160*.mp4"))))[0]
        seq_dir = sorted(glob.glob(os.path.join(SAIDA, f"{tag}_OVERLAY_3840x2160")))[0]
        n = len(glob.glob(os.path.join(seq_dir, "*.png")))
        ovl = mp.ImportMedia([{"FilePath": os.path.join(seq_dir, f"{tag}_OVERLAY_%04d.png"),
                               "StartIndex": 0, "EndIndex": n - 1}])[0]

        tl = mp.CreateEmptyTimeline(tag)
        proj.SetCurrentTimeline(tl)
        tl.AddTrack("video")
        tl.AddTrack("video")
        t0 = tl.GetStartFrame()
        total = int(round(rot["duracao_s"] * FPS))
        mp.AppendToTimeline([{"mediaPoolItem": base, "startFrame": 0, "endFrame": total - 1,
                              "trackIndex": 1, "recordFrame": t0}])
        faltando = []
        for s in rot["slots"]:
            if not s.get("arquivo"):
                faltando.append(s["id"])
                continue
            item = mp.ImportMedia([os.path.join(BRUTOS, s["arquivo"])])
            if not item:
                faltando.append(s["id"] + " (arquivo não encontrado)")
                continue
            item = item[0]
            src_fps = float(item.GetClipProperty("FPS") or FPS)
            sp = float(s.get("velocidade", 1.0))
            if sp < 1.0 and src_fps >= FPS / sp - 0.5:
                # câmera lenta conformada: ex. bruto 60p tocando a 30p = 50%
                item.SetClipProperty("FPS", str(FPS))
                src_fps = FPS
            a = int(round(s["entrada_s"] * src_fps))
            dur = int(round((s["end"] - s["start"]) * FPS * (src_fps / FPS if sp >= 1.0 else 1)))
            mp.AppendToTimeline([{"mediaPoolItem": item, "startFrame": a, "endFrame": a + dur - 1,
                                  "trackIndex": 2, "recordFrame": t0 + int(round(s["start"] * FPS))}])
        mp.AppendToTimeline([{"mediaPoolItem": ovl, "startFrame": 0, "endFrame": n - 1,
                              "trackIndex": 3, "recordFrame": t0}])
        if faltando:
            print(f"[{tag}] slots sem take: {', '.join(faltando)} — a base mostra só o fundo nesses trechos.")
        queue_render(proj, tl, f"NucleoViv_TV_{tag}_FINAL_3840x2160_30p_loop")

    if CFG.get("renderizar_agora"):
        proj.StartRendering()
    print("Pronto. Confira os dissolves na trilha V2 e renderize pela página Deliver.")


def queue_render(proj, tl, name):
    proj.SetCurrentTimeline(tl)
    proj.SetCurrentRenderFormatAndCodec("mp4", "H264")
    proj.SetRenderSettings({"SelectAllFrames": True, "TargetDir": SAIDA, "CustomName": name,
                            "ExportVideo": True, "ExportAudio": False,
                            "FormatWidth": 3840, "FormatHeight": 2160, "FrameRate": 30})
    proj.AddRenderJob()


main()
