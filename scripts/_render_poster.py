"""Render the poster's first slide to PNG via PowerPoint COM (Windows only)."""
import os
import sys
import time
import win32com.client
from win32com.client import constants as c

POSTER = r"C:\Users\wangy\Desktop\meam623_poster.pptx"
OUTDIR = r"C:\Users\wangy\Desktop\poster_render"
os.makedirs(OUTDIR, exist_ok=True)
for f in os.listdir(OUTDIR):
    if f.lower().endswith((".png", ".jpg")):
        os.remove(os.path.join(OUTDIR, f))

ppt = win32com.client.gencache.EnsureDispatch("PowerPoint.Application")
# Some PPT installs require Visible to be at least true to export
try:
    ppt.Visible = 1
except Exception:
    pass

pres = ppt.Presentations.Open(POSTER, WithWindow=False)
try:
    # Export full slide as PNG at a moderate resolution
    # Slide width is 33.1 in × 96 dpi -> ~3178 px. Use 1600 to keep small.
    pres.Slides(1).Export(os.path.join(OUTDIR, "slide-1.png"), "PNG", 1600, 2262)
    print("[render] -> slide-1.png")
finally:
    pres.Close()
    ppt.Quit()
