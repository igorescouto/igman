# -*- coding: utf-8 -*-
"""
Núcleo Viv · TV vertical — cria o projeto no DaVinci Resolve com as 4 timelines montadas.

COMO RODAR (uma vez):
  1. Abra o DaVinci Resolve (qualquer projeto aberto serve).
  2. Menu Workspace > Console > aba "Py3".
  3. Cole as DUAS linhas abaixo (troque só o caminho da primeira) e dê Enter:
        PASTA_PROJETO = r"C:\\CAMINHO\\nucleo-viv-tv\\resolve_vertical"
        exec(open(PASTA_PROJETO + "/criar_projeto_resolve.py", encoding="utf-8").read())
  4. Vai abrir uma janela pedindo a pasta dos TAKES (os IGOR20261107_*.MP4 no Extreme SSD).

O QUE ELE CRIA
  Projeto "NucleoViv_TV_Vertical" · 2160x3840 · 30 fps, com os bins GRAFICA, TEXTOS, TAKES e 4 timelines:
    M1_LINHA_DA_JORNADA, M2_TRES_FASES   100% motion, já cortadas por cena
    T1_A_JORNADA, T2_O_ESPACO            V1 base (fundo+logos) · V2 takes em câmera lenta ·
                                         V3 escurecimento · V4/V5 cada texto como clipe solto
  Marcadores em cada cena com o que lapidar. Fila de render pronta (MP4 H.264, sem áudio).

Os takes são só REFERENCIADOS (import do Resolve): nada é movido, alterado ou apagado.
Para escolher takes específicos antes de rodar, edite ESCOLHA_DE_TAKES logo abaixo.
"""
import json, os, sys

# Opcional: nome do arquivo por slot. Slot sem nome = escolha automática espalhada pela gravação.
# Slots: T1 -> 1A 1B 2A 2B PA PB   |   T2 -> E1 E2 E3 E4 E5 E6
ESCOLHA_DE_TAKES = {
    # "1A": "IGOR20261107_0891.MP4",
}
PASTA_TAKES = ""     # deixe vazio para escolher na janela; ou escreva o caminho aqui
VIDEO_EXT = (".mp4", ".mov", ".mxf", ".m4v", ".braw")
FPS = 30


def _aqui():
    for cand in (globals().get("__file__"), globals().get("PASTA_PROJETO")):
        if cand and os.path.exists(cand):
            return os.path.dirname(os.path.abspath(cand)) if os.path.isfile(cand) else cand
    # rodando por exec(open(...)) no console: procura o timelines.json nos argumentos do exec
    import inspect
    for fr in inspect.stack():
        for v in fr.frame.f_locals.values():
            if isinstance(v, str) and v.endswith("criar_projeto_resolve.py") and os.path.exists(v):
                return os.path.dirname(os.path.abspath(v))
    return os.getcwd()


def _resolve():
    r = globals().get("resolve")
    if r:
        return r
    try:
        import DaVinciResolveScript as dvr
    except ImportError:
        for p in (r"C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules",
                  "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules",
                  "/opt/resolve/Developer/Scripting/Modules"):
            sys.path.append(p)
        import DaVinciResolveScript as dvr
    return dvr.scriptapp("Resolve")


def _log(*a):
    print("[Viv]", *a)


def main():
    r = _resolve()
    here = _aqui()
    spec_path = os.path.join(here, "timelines.json")
    if not os.path.exists(spec_path):
        _log("Não achei timelines.json em", here, "— defina PASTA_PROJETO = r'...\\resolve_vertical' antes do exec.")
        return
    spec = json.load(open(spec_path, encoding="utf-8"))

    # ---------- pasta dos takes
    takes_dir = PASTA_TAKES
    if not takes_dir or not os.path.isdir(takes_dir):
        try:
            takes_dir = r.Fusion().RequestDir("") or ""
        except Exception:
            takes_dir = ""
    takes = []
    if takes_dir and os.path.isdir(takes_dir):
        for d, _, fs in os.walk(takes_dir):
            takes += [os.path.join(d, f) for f in fs if f.lower().endswith(VIDEO_EXT) and not f.startswith(".")]
        takes.sort()
    _log(len(takes), "takes encontrados em", takes_dir or "(nenhuma pasta escolhida)")

    # ---------- projeto
    pm = r.GetProjectManager()
    name, k = spec["projeto"], 1
    proj = pm.CreateProject(name)
    while proj is None and k < 20:
        k += 1
        proj = pm.CreateProject("%s_%d" % (name, k))
    if proj is None:
        _log("Não consegui criar o projeto.")
        return
    for key, val in (("timelineFrameRate", str(FPS)), ("timelinePlaybackFrameRate", str(FPS)),
                     ("timelineResolutionWidth", str(spec["largura"])), ("timelineResolutionHeight", str(spec["altura"])),
                     ("timelineOutputResolutionWidth", str(spec["largura"])), ("timelineOutputResolutionHeight", str(spec["altura"])),
                     ("timelineInputResMismatchBehavior", "scaleToCrop")):   # take horizontal preenche o quadro vertical
        if not proj.SetSetting(key, val):
            _log("aviso: não apliquei", key)
    mp = proj.GetMediaPool()
    root = mp.GetRootFolder()
    bins = {n: mp.AddSubFolder(root, n) for n in ("GRAFICA", "TEXTOS", "TAKES", "REFERENCIA")}

    cache = {}

    def media(rel, bin_name):
        if rel not in cache:
            mp.SetCurrentFolder(bins[bin_name])
            got = mp.ImportMedia([os.path.join(here, rel.replace("/", os.sep))])
            cache[rel] = got[0] if got else None
            if not got:
                _log("FALTOU importar:", rel)
        return cache[rel]

    # ---------- takes: importa todos para o bin (facilita trocar depois) e conforma câmera lenta
    take_items = {}
    if takes:
        mp.SetCurrentFolder(bins["TAKES"])
        for it in (mp.ImportMedia(takes) or []):
            take_items[it.GetName()] = it
    nomes = sorted(take_items)

    def conformar(it):
        """60p/120p tocando a 30 fps = câmera lenta real (sem frames inventados)."""
        try:
            fps = float(it.GetClipProperty("FPS"))
        except Exception:
            fps = FPS
        if fps > FPS + 1:
            it.SetClipProperty("FPS", str(FPS))
            return "%.0f→30 fps (%.0f%%)" % (fps, 100.0 * FPS / fps)
        return "%.0f fps: sem câmera lenta automática (use Retime 50%% + Optical Flow)" % fps

    def frames_de(it):
        try:
            return int(it.GetClipProperty("Frames"))
        except Exception:
            return 0

    usados = []

    def escolher(slot_id, ordem, total):
        if ESCOLHA_DE_TAKES.get(slot_id) in take_items:
            return take_items[ESCOLHA_DE_TAKES[slot_id]]
        if not nomes:
            return None
        # espalha as escolhas ao longo da gravação e evita repetir
        idx = int((ordem + 0.5) * len(nomes) / total) % len(nomes)
        for _ in range(len(nomes)):
            if nomes[idx] not in usados:
                break
            idx = (idx + 1) % len(nomes)
        usados.append(nomes[idx])
        return take_items[nomes[idx]]

    todos_slots = [(k_, s) for k_ in ("T1", "T2") for s in spec["timelines"].get(k_, {}).get("slots", [])]
    plano = {}
    for n_, (k_, s) in enumerate(todos_slots):
        plano[(k_, s["id"])] = escolher(s["id"], n_, len(todos_slots))

    # ---------- timelines
    for key in ("M1", "M2", "T1", "T2"):
        tl_spec = spec["timelines"].get(key)
        if not tl_spec:
            continue
        mp.SetCurrentFolder(root)
        tl = mp.CreateEmptyTimeline(tl_spec["nome"])
        if not tl:
            _log("Não criei a timeline", tl_spec["nome"])
            continue
        proj.SetCurrentTimeline(tl)
        t0 = tl.GetStartFrame()
        ntracks = max(int(x) for x in tl_spec["trilhas"]) if tl_spec["trilhas"] else 1
        if tl_spec.get("slots"):
            ntracks = max(ntracks, 2)
        while tl.GetTrackCount("video") < ntracks:
            tl.AddTrack("video")
        nomes_trilha = {1: "BASE / MOTION", 2: "TAKES camera lenta", 3: "ESCURECIMENTO", 4: "TEXTOS", 5: "TEXTOS 2"}
        for i in range(1, ntracks + 1):
            try:
                tl.SetTrackName("video", i, nomes_trilha.get(i, "V%d" % i))
            except Exception:
                pass

        def append(item, track, rec, src, dur):
            if item is None:
                return
            ok = mp.AppendToTimeline([{"mediaPoolItem": item, "startFrame": int(src), "endFrame": int(src + dur - 1),
                                       "trackIndex": int(track), "recordFrame": int(t0 + rec), "mediaType": 1}])
            if not ok:
                _log("  não consegui colocar", item.GetName(), "na V%d em %d" % (track, rec))

        for c in tl_spec["trilhas"].get("1", []):
            append(media(c["arquivo"], "GRAFICA"), 1, c["rec"], c["src"], c["dur"])
        for s in tl_spec.get("slots", []):
            it = plano.get((key, s["id"]))
            if it is None:
                _log("  %s slot %s sem take (a base aparece no lugar)" % (key, s["id"]))
                continue
            info = conformar(it)
            total = frames_de(it)
            ini = max(0, (total - s["dur"]) // 2)          # miolo do take: costuma ser o trecho mais estável
            append(it, 2, s["rec"], ini, s["dur"])
            _log("  %s slot %s <- %s | %s" % (key, s["id"], it.GetName(), info))
        for tr in ("3", "4", "5"):
            for c in tl_spec["trilhas"].get(tr, []):
                append(media(c["arquivo"], "TEXTOS"), int(tr), c["rec"], c["src"], c["dur"])
        if tl_spec.get("preview"):
            media(tl_spec["preview"], "REFERENCIA")

        for c in tl_spec["cenas"]:
            nota = "Lapidar: ritmo, entrada/saída do texto (fade 0,3 s), cor."
            if tl_spec.get("slots"):
                nota = "Trocar/ajustar o take da V2, dissolve 0,5 s entre takes (Ctrl/Cmd+T), fade nos textos, cor."
            try:
                tl.AddMarker(int(c["ini"]), "Cream", c["nome"], nota, 1)
            except Exception:
                pass

        try:
            proj.SetCurrentRenderFormatAndCodec("mp4", "H264")
            proj.SetRenderSettings({"SelectAllFrames": True, "CustomName": tl_spec["render"],
                                    "TargetDir": os.path.join(here, "render"),
                                    "ExportVideo": True, "ExportAudio": False,
                                    "FormatWidth": spec["largura"], "FormatHeight": spec["altura"], "FrameRate": float(FPS)})
            os.makedirs(os.path.join(here, "render"), exist_ok=True)
            proj.AddRenderJob()
        except Exception as e:
            _log("  render não enfileirado:", e)
        _log("timeline pronta:", tl_spec["nome"])

    pm.SaveProject()
    try:
        r.OpenPage("edit")
    except Exception:
        pass
    _log("Projeto '%s' criado. Loop: o primeiro e o último frame de cada timeline são o mesmo fundo vazio — não corte as pontas." % proj.GetName())


main()
