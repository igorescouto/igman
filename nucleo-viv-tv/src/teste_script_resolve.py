#!/usr/bin/env python3
"""Roda criar_projeto_resolve.py contra um Resolve simulado (confere a lógica, não a API real)."""
import os, sys, tempfile, json

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resolve_vertical")
LOG = []


class Item:
    def __init__(s, path, fps=59.94, frames=900):
        s.path, s.fps, s.frames = path, fps, frames

    def GetName(s): return os.path.basename(s.path)
    def GetClipProperty(s, k): return {"FPS": str(s.fps), "Frames": str(s.frames)}[k]
    def SetClipProperty(s, k, v): s.fps = float(v); return True


class TL:
    def __init__(s, name): s.name, s.tracks, s.markers = name, 1, []
    def GetStartFrame(s): return 108000
    def GetTrackCount(s, k): return s.tracks
    def AddTrack(s, k): s.tracks += 1; return True
    def SetTrackName(s, *a): return True
    def AddMarker(s, *a): s.markers.append(a); return True


class MP:
    def __init__(s): s.cur = None
    def GetRootFolder(s): return "root"
    def AddSubFolder(s, r, n): return n
    def SetCurrentFolder(s, f): s.cur = f; return True
    def ImportMedia(s, paths):
        for p in paths:
            assert os.path.exists(p), "arquivo inexistente: " + p
        return [Item(p) for p in paths]
    def CreateEmptyTimeline(s, n): s.tl = TL(n); LOG.append(("TL", n)); return s.tl
    def AppendToTimeline(s, clips):
        for c in clips:
            assert c["endFrame"] >= c["startFrame"] >= 0
            LOG.append((s.tl.name, c["trackIndex"], c["recordFrame"] - 108000, c["endFrame"] - c["startFrame"] + 1, c["mediaPoolItem"].GetName()))
        return True


class Proj:
    def __init__(s): s.mp = MP(); s.jobs = 0
    def GetName(s): return "NucleoViv_TV_Vertical"
    def SetSetting(s, k, v): return True
    def GetMediaPool(s): return s.mp
    def SetCurrentTimeline(s, t): return True
    def SetCurrentRenderFormatAndCodec(s, *a): return True
    def SetRenderSettings(s, d): assert d["ExportAudio"] is False; return True
    def AddRenderJob(s): s.jobs += 1; return "job"


class PM:
    def CreateProject(s, n): s.p = Proj(); return s.p
    def SaveProject(s): return True


class Res:
    def __init__(s, d): s.pm, s.d = PM(), d
    def GetProjectManager(s): return s.pm
    def Fusion(s): return type("F", (), {"RequestDir": lambda self, x: s.d})()
    def OpenPage(s, p): return True


with tempfile.TemporaryDirectory() as d:
    for i in range(40):
        open(os.path.join(d, "IGOR20261107_%04d.MP4" % (865 + i)), "w").close()
    res = Res(d)
    src = open(os.path.join(HERE, "criar_projeto_resolve.py"), encoding="utf-8").read()
    exec(src, {"resolve": res, "PASTA_PROJETO": HERE, "__name__": "x"})
    spec = json.load(open(os.path.join(HERE, "timelines.json")))
    for k, t in spec["timelines"].items():
        clips = [l for l in LOG if l[0] == t["nome"]]
        v1 = sorted((c[2], c[3]) for c in clips if c[1] == 1)
        pos = 0
        for rec, dur in v1:                      # V1 precisa cobrir a timeline inteira, sem buraco
            assert rec == pos, (t["nome"], rec, pos)
            pos += dur
        assert pos == t["frames"], (t["nome"], pos, t["frames"])
        takes = [c for c in clips if c[1] == 2]
        assert len(takes) == len(t.get("slots", [])), t["nome"]
        assert all(c[2] + c[3] <= t["frames"] for c in clips)
        print("OK", t["nome"], "| clipes:", len(clips), "| takes:", [c[4][-8:-4] for c in takes])
    assert len(set(c[4] for c in LOG if len(c) == 5 and c[1] == 2)) == 12, "takes repetidos"
    print("OK render jobs:", res.pm.p.jobs)
