"""Shared style spec for all 3 results columns of the MEAM 623 poster.

Goal: every column should look like it was designed by the same person.
Same font sizes, same color palette, same bullet style, same take-away style.

Hierarchy
---------
TITLE     40 pt  navy bold       — column number + title
DONE      28 pt  green           — "✓ Done" badge
BODY      26 pt  dark            — description sentence(s) under title
EQ_MAIN   26 pt  navy bold       — equation / setup line
EQ_SUB    20 pt  mid             — equation subtitle / parameter recap
PLAN_HEAD 26 pt  navy bold       — top headline result of Plan box
BULL_HEAD 24 pt  dark bold       — "✓  Header" or "✗  Header" of each bullet
BULL_BODY 20 pt  body-darker     — short sub-explanation under each bullet
TAKEAWAY  26 pt  navy bold       — final closing claim of the column

Colors
------
NAVY      #011F5B   primary brand colour, used for all headings
GREEN     #2E7D32   used only for the "✓ Done" badge
RED       #C62828   used only for the "✗" failure marker
DARK      #1F1F1F   bold body text (bullet heads, plain body sentences)
BODY      #2E3440   plain body text (slightly softer than DARK)
MID       #4A5263   subtitle / parameter recap (darker than the old #555)
"""

from pptx.dml.color import RGBColor

NAVY  = RGBColor(0x01, 0x1F, 0x5B)
GREEN = RGBColor(0x2E, 0x7D, 0x32)
RED   = RGBColor(0xC6, 0x28, 0x28)
DARK  = RGBColor(0x1F, 0x1F, 0x1F)
BODY  = RGBColor(0x2E, 0x34, 0x40)
MID   = RGBColor(0x4A, 0x52, 0x63)

TITLE     = 40
DONE      = 28
BODY_PT   = 28
EQ_MAIN   = 28
EQ_SUB    = 22
PLAN_HEAD = 28
BULL_HEAD = 26
BULL_BODY = 22
TAKEAWAY  = 30

FONT = "Arial"
