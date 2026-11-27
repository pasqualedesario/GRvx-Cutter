# MenuTitle: GV-Soft Landing
# -*- coding: utf-8 -*-
__doc__ = """
Soft-lands a cubic into a straight segment with automatic minimal edit.
Select the junction on-curve (curve↔line) → preview → Apply.
May slide the junction along the straight when that preserves the curve better.
"""

import math
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
	sys.path.insert(0, _HERE)

import gv_common as gvc

try:
	from GlyphsApp import (
		Glyphs,
		OFFCURVE,
		Message,
		DRAWFOREGROUND,
		UPDATEINTERFACE,
	)
except Exception:
	from GlyphsApp import *  # noqa: F401,F403
	DRAWFOREGROUND = globals().get("DRAWFOREGROUND", "DrawForeground")
	UPDATEINTERFACE = globals().get("UPDATEINTERFACE", "GSUpdateInterface")

try:
	from GlyphsApp import NodeSmoothColor as _NodeSmoothColor
	gvc.NodeSmoothColor = _NodeSmoothColor
except Exception:
	pass
gvc.Glyphs = Glyphs

try:
	from vanilla import FloatingWindow, Button, TextBox, CheckBox
	HAS_VANILLA = True
except Exception:
	HAS_VANILLA = False

try:
	from AppKit import NSBezierPath
except Exception:
	NSBezierPath = None

SCRIPT_TITLE = "GV-Soft Landing"
__version__ = "0.2.1"

# Auto soft-land: prefer junction slide + tiny handle edit over heavy flatten.
MAX_P1_BLEND = 0.28
LEN_BOOST = 0.35
MAX_HANDLE_FRAC = 0.85
KAPPA_OK = 2.5e-4  # end-curvature target (font units^-1 scale)
W_KAPPA = 1.0
W_DEV = 0.045
W_SLIDE = 0.012
W_SOFT = 0.55
SLIDE_STEPS = 17
SOFT_CANDIDATES = (0.0, 0.08, 0.16, 0.28)

UI_STATUS_H = 36

V = gvc.V
add = gvc.add
sub = gvc.sub
mul = gvc.mul
lerp = gvc.lerp
dot = gvc.dot
length = gvc.length
unit = gvc.unit
xy = gvc.xy
project = gvc.project
clamp = gvc.clamp
node_index = gvc.node_index
walk_indices = gvc.walk_indices


def oncurve_neighbor(nodes, idx, step):
	return gvc.oncurve_neighbor(nodes, idx, step, OFFCURVE)


# ── path helpers ───────────────────────────────────────────────────────────

def segment_kind(path, i_on, j_on):
	"""LINE | CURVE | None between two on-curve indices (forward i→j)."""
	n = len(path.nodes)
	between = walk_indices(i_on, j_on, n)
	offs = [k for k in between if path.nodes[k].type == OFFCURVE]
	ons = [k for k in between if path.nodes[k].type != OFFCURVE]
	if ons:
		return None, None, None
	if len(offs) == 0:
		return "LINE", between, offs
	if len(offs) == 2:
		return "CURVE", between, offs
	return None, between, offs


def path_for_node(layer, node):
	for p in layer.paths:
		if node_index(p, node) is not None:
			return p
	return None


def _is_oncurve(obj):
	try:
		return obj.type != OFFCURVE and hasattr(obj, "x")
	except Exception:
		return False


def cubic_point(P0, P1, P2, P3, t):
	u = 1.0 - t
	return (
		u * u * u * P0[0] + 3 * u * u * t * P1[0] + 3 * u * t * t * P2[0] + t * t * t * P3[0],
		u * u * u * P0[1] + 3 * u * u * t * P1[1] + 3 * u * t * t * P2[1] + t * t * t * P3[1],
	)


def end_curvature(P1, P2, P3):
	"""Unsigned curvature proxy at cubic end (t=1). Zero iff P1,P2,P3 collinear."""
	d = sub(P3, P2)
	L = length(d)
	if L < 1e-9:
		return 1e9
	cross = d[0] * (P1[1] - P2[1]) - d[1] * (P1[0] - P2[0])
	return abs(cross) / (L * L * L)


def start_curvature(P0, P1, P2):
	"""Unsigned curvature proxy at cubic start (t=0)."""
	d = sub(P1, P0)
	L = length(d)
	if L < 1e-9:
		return 1e9
	cross = d[0] * (P2[1] - P1[1]) - d[1] * (P2[0] - P1[0])
	return abs(cross) / (L * L * L)


def sample_cubic(P0, P1, P2, P3, n=12):
	return [cubic_point(P0, P1, P2, P3, i / float(n)) for i in range(n + 1)]


def rms_dev(samples_a, samples_b):
	if not samples_a or len(samples_a) != len(samples_b):
		return 1e9
	acc = 0.0
	for a, b in zip(samples_a, samples_b):
		acc += (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2
	return math.sqrt(acc / float(len(samples_a)))


def _handles_cubic_then_line(P0, P1, P2, J, L, soft):
	"""G1 end handle on the line + mild P1 pull. J/L define the straight."""
	s = clamp(float(soft), 0.0, 1.0)
	line_axis = unit(V(J, L))
	into_curve = mul(line_axis, -1.0)
	chord = length(V(P0, J))
	max_len = max(chord * MAX_HANDLE_FRAC, 1.0)
	len_g1 = length(V(J, P2))
	if len_g1 < 1e-9:
		len_g1 = min(chord * 0.35, max_len)
	# Scale end-handle with chord if junction slid.
	len_g1 = min(max(len_g1, 1.0), max_len)
	len_hi = min(len_g1 * (1.0 + LEN_BOOST), max_len)
	len2 = len_g1 + (len_hi - len_g1) * s
	prop_P2 = add(J, mul(into_curve, len2))

	P1_on_line = project(P1, J, line_axis)
	if dot(V(J, P1_on_line), line_axis) > 0:
		P1_on_line = J
	# Keep P1 roughly at same along-curve depth when J moves: blend from current P1.
	prop_P1 = lerp(P1, P1_on_line, s * MAX_P1_BLEND)
	if length(V(P0, prop_P1)) < 1e-6:
		prop_P1 = P1
	return prop_P1, prop_P2, line_axis, s


def _handles_line_then_cubic(J, P1, P2, far, L, soft):
	s = clamp(float(soft), 0.0, 1.0)
	line_axis = unit(V(J, L))
	into_curve = mul(line_axis, -1.0)
	if length(V(J, P1)) > 1e-9 and dot(V(J, P1), into_curve) < 0:
		into_curve = mul(into_curve, -1.0)
	chord = length(V(J, far))
	max_len = max(chord * MAX_HANDLE_FRAC, 1.0)
	len_g1 = length(V(J, P1))
	if len_g1 < 1e-9:
		len_g1 = min(chord * 0.35, max_len)
	len_g1 = min(max(len_g1, 1.0), max_len)
	len_hi = min(len_g1 * (1.0 + LEN_BOOST), max_len)
	len1 = len_g1 + (len_hi - len_g1) * s
	prop_P1 = add(J, mul(into_curve, len1))
	P2_on_line = project(P2, J, line_axis)
	prop_P2 = lerp(P2, P2_on_line, s * MAX_P1_BLEND)
	if length(V(far, prop_P2)) < 1e-6:
		prop_P2 = P2
	return prop_P1, prop_P2, line_axis, s


def _slide_range(J, L, chord):
	"""Signed slide along line_axis=unit(J→L): + toward L, − toward curve."""
	line_len = length(V(J, L))
	# Keep a usable straight and a usable cubic span.
	max_toward_L = max(0.0, min(line_len * 0.45, chord * 0.35))
	max_toward_curve = max(0.0, min(chord * 0.40, line_len * 0.85))
	return -max_toward_curve, max_toward_L


def _auto_result(prop_P1, prop_P2, prop_J, axis, soft, slide, kappa, dev):
	return {
		"prop_P1": prop_P1,
		"prop_P2": prop_P2,
		"prop_J": prop_J,
		"line_axis": axis,
		"soft": soft,
		"slide": slide,
		"kappa": kappa,
		"dev": dev,
	}


def _auto_cubic_then_line(P0, P1, P2, J, L):
	"""Minimal soft + optional junction slide along the straight."""
	orig_samples = sample_cubic(P0, P1, P2, J)
	chord0 = max(length(V(P0, J)), 1.0)
	line_axis = unit(V(J, L))
	t_lo, t_hi = _slide_range(J, L, chord0)
	best = None

	for i in range(SLIDE_STEPS):
		slide = 0.0 if SLIDE_STEPS == 1 else t_lo + (t_hi - t_lo) * (i / float(SLIDE_STEPS - 1))
		J2 = add(J, mul(line_axis, slide))
		# Don't collapse the straight.
		if length(V(J2, L)) < 8.0:
			continue
		for soft in SOFT_CANDIDATES:
			prop_P1, prop_P2, axis, s = _handles_cubic_then_line(P0, P1, P2, J2, L, soft)
			kappa = end_curvature(prop_P1, prop_P2, J2)
			dev = rms_dev(orig_samples, sample_cubic(P0, prop_P1, prop_P2, J2))
			cost = (
				W_KAPPA * kappa
				+ W_DEV * dev
				+ W_SLIDE * abs(slide) / chord0
				+ W_SOFT * s
			)
			# Prefer solutions that already meet κ target; among them minimize cost.
			rank = (0 if kappa <= KAPPA_OK else 1, cost, abs(slide), s)
			cand = _auto_result(prop_P1, prop_P2, J2, axis, s, slide, kappa, dev)
			if best is None or rank < best[0]:
				best = (rank, cand)

	return best[1] if best else None


def _auto_line_then_cubic(J, P1, P2, far, L):
	orig_samples = sample_cubic(J, P1, P2, far)
	chord0 = max(length(V(J, far)), 1.0)
	line_axis = unit(V(J, L))
	t_lo, t_hi = _slide_range(J, L, chord0)
	best = None
	for i in range(SLIDE_STEPS):
		slide = 0.0 if SLIDE_STEPS == 1 else t_lo + (t_hi - t_lo) * (i / float(SLIDE_STEPS - 1))
		J2 = add(J, mul(line_axis, slide))
		if length(V(J2, L)) < 8.0:
			continue
		for soft in SOFT_CANDIDATES:
			prop_P1, prop_P2, axis, s = _handles_line_then_cubic(J2, P1, P2, far, L, soft)
			kappa = start_curvature(J2, prop_P1, prop_P2)
			dev = rms_dev(orig_samples, sample_cubic(J2, prop_P1, prop_P2, far))
			cost = W_KAPPA * kappa + W_DEV * dev + W_SLIDE * abs(slide) / chord0 + W_SOFT * s
			rank = (0 if kappa <= KAPPA_OK else 1, cost, abs(slide), s)
			cand = _auto_result(prop_P1, prop_P2, J2, axis, s, slide, kappa, dev)
			if best is None or rank < best[0]:
				best = (rank, cand)
	return best[1] if best else None


def _proposal(path, mode, j_idx, indices, points, auto):
	geo = {
		"path": path,
		"mode": mode,
		"j_idx": j_idx,
	}
	geo.update(indices)
	geo.update(points)
	geo.update(auto)
	return geo


def _junction_from_indices(path, j_idx):
	"""Build auto soft-land proposal for on-curve junction index, or (None, status)."""
	nodes = path.nodes
	prev_i = oncurve_neighbor(nodes, j_idx, -1)
	next_i = oncurve_neighbor(nodes, j_idx, +1)
	if prev_i is None or next_i is None:
		return None, "err_junction"

	kind_prev, _b0, offs_prev = segment_kind(path, prev_i, j_idx)
	kind_next, _b1, offs_next = segment_kind(path, j_idx, next_i)

	cubic_then_line = kind_prev == "CURVE" and kind_next == "LINE"
	line_then_cubic = kind_prev == "LINE" and kind_next == "CURVE"
	if not cubic_then_line and not line_then_cubic:
		return None, "err_junction"

	if cubic_then_line:
		P0_i, P1_i, P2_i = prev_i, offs_prev[0], offs_prev[1]
		L_i = next_i
		P0, P1, P2 = xy(nodes[P0_i]), xy(nodes[P1_i]), xy(nodes[P2_i])
		J, L = xy(nodes[j_idx]), xy(nodes[L_i])
		auto = _auto_cubic_then_line(P0, P1, P2, J, L)
		if auto is None:
			return None, "err_junction"
		return _proposal(
			path,
			"cubic_then_line",
			j_idx,
			{"P0_i": P0_i, "P1_i": P1_i, "P2_i": P2_i, "L_i": L_i},
			{"P0": P0, "P1": P1, "P2": P2, "J": J, "L": L},
			auto,
		), "ok"

	P0_i = j_idx
	P1_i, P2_i = offs_next[0], offs_next[1]
	far_i = next_i
	L_i = prev_i
	J = xy(nodes[j_idx])
	P1, P2 = xy(nodes[P1_i]), xy(nodes[P2_i])
	far, L = xy(nodes[far_i]), xy(nodes[L_i])
	auto = _auto_line_then_cubic(J, P1, P2, far, L)
	if auto is None:
		return None, "err_junction"
	return _proposal(
		path,
		"line_then_cubic",
		j_idx,
		{"P0_i": P0_i, "P1_i": P1_i, "P2_i": P2_i, "far_i": far_i, "L_i": L_i},
		{"P0": J, "P1": P1, "P2": P2, "J": J, "L": L, "far": far},
		auto,
	), "ok"


def _status_for_geo(geo, lang):
	slide = abs(geo.get("slide", 0.0))
	if slide >= 0.75:
		return t(lang, "status_slide") % slide
	return t(lang, "status_ok")


def resolve_junction(layer, lang="it"):
	"""From selection → proposal dict or (None, error message)."""
	sel = [o for o in layer.selection if _is_oncurve(o)]
	if len(sel) == 0:
		return None, t(lang, "need_one")
	if len(sel) > 2:
		return None, t(lang, "need_one")

	if len(sel) == 1:
		node = sel[0]
		path = path_for_node(layer, node)
		if path is None:
			return None, t(lang, "err_path")
		j_idx = node_index(path, node)
		geo, code = _junction_from_indices(path, j_idx)
		if geo is None:
			return None, t(lang, code)
		return geo, _status_for_geo(geo, lang)

	na, nb = sel[0], sel[1]
	path = path_for_node(layer, na)
	if path is None or node_index(path, nb) is None:
		return None, t(lang, "same_path")
	candidates = []
	for node in (na, nb):
		j_idx = node_index(path, node)
		geo, code = _junction_from_indices(path, j_idx)
		if geo is not None:
			candidates.append(geo)
	if not candidates:
		return None, t(lang, "err_junction")
	geo = next((g for g in candidates if g["mode"] == "cubic_then_line"), candidates[0])
	return geo, _status_for_geo(geo, lang)


def apply_soft_landing(geo):
	"""Mutate path nodes from proposal (handles + optional junction slide)."""
	path = geo["path"]
	nodes = path.nodes
	j = nodes[geo["j_idx"]]
	j.smooth = True
	prop_J = geo.get("prop_J", geo["J"])
	j.x, j.y = prop_J
	p1 = nodes[geo["P1_i"]]
	p2 = nodes[geo["P2_i"]]
	p1.x, p1.y = geo["prop_P1"]
	p2.x, p2.y = geo["prop_P2"]
	return True


def run_soft_landing(lang="it"):
	font = Glyphs.font
	if not font:
		Message(t(lang, "no_font"), SCRIPT_TITLE)
		return False
	layers = font.selectedLayers
	if not layers:
		Message(t(lang, "no_glyph"), SCRIPT_TITLE)
		return False
	layer = layers[0]
	geo, msg = resolve_junction(layer, lang=lang)
	if geo is None:
		Message(msg, SCRIPT_TITLE)
		return False

	glyph = getattr(layer, "parent", None)
	font.disableUpdateInterface()
	try:
		if glyph is not None:
			try:
				glyph.beginUndo()
			except Exception:
				pass
		apply_soft_landing(geo)
		if glyph is not None:
			try:
				glyph.endUndo()
			except Exception:
				pass
	finally:
		font.enableUpdateInterface()

	Glyphs.showNotification(SCRIPT_TITLE, msg)
	Glyphs.redraw()
	return True


# ── drawing ────────────────────────────────────────────────────────────────

def draw_soft_preview(layer, info, lang="it"):
	try:
		if NSBezierPath is None:
			return
		geo, status = resolve_junction(layer, lang=lang)
		scale = gvc.scale_from_info(info)
		green = gvc.glyphs_green(1.0)
		dim = gvc.glyphs_green(0.35)
		if green is None:
			return
		if geo is None:
			sel = [o for o in layer.selection if _is_oncurve(o)]
			if sel:
				gvc.draw_label(
					status,
					(sel[0].x + 8.0 / scale, sel[0].y + 8.0 / scale),
					scale,
					green,
				)
			return

		J0, L = geo["J"], geo["L"]
		prop_J = geo.get("prop_J", J0)
		prop_P1, prop_P2 = geo["prop_P1"], geo["prop_P2"]

		gvc.stroke_line(prop_J, L, scale, dim, width_px=2.0, dashed=False)
		if abs(geo.get("slide", 0.0)) >= 0.5:
			gvc.stroke_line(J0, prop_J, scale, dim, width_px=1.0, dashed=True)
			gvc.mark_point(J0, scale, dim, radius_px=2.5)

		if geo["mode"] == "cubic_then_line":
			gvc.stroke_line(geo["P0"], prop_P1, scale, green, width_px=1.2)
			gvc.stroke_line(prop_P1, prop_P2, scale, green, width_px=0.8, dashed=True)
			gvc.stroke_line(prop_P2, prop_J, scale, green, width_px=1.2)
		else:
			gvc.stroke_line(prop_J, prop_P1, scale, green, width_px=1.2)
			gvc.stroke_line(prop_P1, prop_P2, scale, green, width_px=0.8, dashed=True)
			gvc.stroke_line(prop_P2, geo["far"], scale, green, width_px=1.2)

		gvc.mark_point(prop_J, scale, green, radius_px=4.0)
		gvc.mark_point(prop_P1, scale, green, radius_px=3.0)
		gvc.mark_point(prop_P2, scale, green, radius_px=3.0)
		gvc.draw_label(
			status,
			(prop_J[0] + 10.0 / scale, prop_J[1] + 10.0 / scale),
			scale,
			green,
		)
	except Exception:
		traceback.print_exc()


# ── i18n ───────────────────────────────────────────────────────────────────

UI = {
	"it": {
		"about_title": "Cos’è GV-Soft Landing",
		"about_body": (
			"Calcola in automatico l’intervento minimo per far atterrare "
			"una cubica su un tratto dritto (G1), spostando il giunto lungo "
			"il dritto solo se serve a conservare meglio la curva."
		),
		"instructions": "Istruzioni",
		"body": (
			"Seleziona il nodo on-curve di giunzione curva↔linea "
			"(oppure i due estremi del segmento cubico), poi Applica."
		),
		"preview": "Anteprima",
		"apply": "Applica",
		"cancel": "Annulla",
		"credit_prefix": "Sviluppo: ",
		"credit_name": "Pasquale de Sario",
		"site": "https://pasqualedesario.eu/#it",
		"lang_button": "English",
		"no_font": "Nessun font aperto.",
		"no_glyph": "Seleziona un glifo in Edit View.",
		"need_one": (
			"Seleziona il nodo on-curve di giunzione\n"
			"tra una curva cubica e un tratto dritto."
		),
		"same_path": "I nodi devono appartenere allo stesso path.",
		"err_path": "Nodo non trovato nel path.",
		"err_junction": (
			"Giunzione curva↔linea non trovata.\n"
			"Seleziona il nodo dove una cubica incontra un tratto dritto."
		),
		"status_ok": "Soft Landing · auto",
		"status_slide": "Soft Landing · giunto Δ %.0f",
		"status_idle": "Seleziona il giunto curva↔linea",
	},
	"en": {
		"about_title": "What is GV-Soft Landing",
		"about_body": (
			"Automatically finds the smallest edit to soft-land a cubic "
			"onto a straight (G1), sliding the junction along the line "
			"only when that better preserves the curve."
		),
		"instructions": "Instructions",
		"body": (
			"Select the on-curve junction between a cubic and a line "
			"(or both ends of the cubic segment), then Apply."
		),
		"preview": "Preview",
		"apply": "Apply",
		"cancel": "Cancel",
		"credit_prefix": "Development: ",
		"credit_name": "Pasquale de Sario",
		"site": "https://pasqualedesario.eu/#en",
		"lang_button": "Italiano",
		"no_font": "No font open.",
		"no_glyph": "Select a glyph in Edit View.",
		"need_one": (
			"Select the on-curve junction node\n"
			"between a cubic curve and a straight segment."
		),
		"same_path": "Both nodes must belong to the same path.",
		"err_path": "Node not found on a path.",
		"err_junction": (
			"No curve↔line junction found.\n"
			"Select the node where a cubic meets a straight segment."
		),
		"status_ok": "Soft Landing · auto",
		"status_slide": "Soft Landing · junction Δ %.0f",
		"status_idle": "Select a curve↔line junction",
	},
}


def t(lang, key):
	return gvc.t(UI, lang, key)


# ── dialog ─────────────────────────────────────────────────────────────────

class GVSoftLandingDialog(object):
	def __init__(self):
		m, s, inn, W = gvc.UI_MARGIN, gvc.UI_SECTION, gvc.UI_INNER, gvc.UI_WIDTH
		H = (
			m
			+ gvc.UI_TITLE_H + inn + gvc.UI_ABOUT_H + s
			+ gvc.UI_TITLE_H + inn + gvc.UI_INSTR_BODY_H + s
			+ gvc.UI_CHECK_H + s
			+ UI_STATUS_H + s
			+ gvc.UI_BTN_H + s
			+ gvc.UI_CREDIT_H
			+ m
		)

		self.lang = "it"
		self.show_preview = True
		self.w = FloatingWindow((W, H), SCRIPT_TITLE)
		gvc.tint_panel_white(self.w)
		gvc.set_window_title(self.w, SCRIPT_TITLE)
		y = m

		self.w.aboutTitle = TextBox((m, y, -m, gvc.UI_TITLE_H), "")
		gvc.style_heading(self.w.aboutTitle)
		y += gvc.UI_TITLE_H + inn
		self.w.aboutBody = TextBox((m, y, -m, gvc.UI_ABOUT_H), "")
		gvc.style_body(self.w.aboutBody)
		y += gvc.UI_ABOUT_H + s

		self.w.instrTitle = TextBox((m, y, -m, gvc.UI_TITLE_H), "")
		gvc.style_heading(self.w.instrTitle)
		y += gvc.UI_TITLE_H + inn
		self.w.instrBody = TextBox((m, y, -m, gvc.UI_INSTR_BODY_H), "")
		gvc.style_body(self.w.instrBody)
		y += gvc.UI_INSTR_BODY_H + s

		self.w.preview = CheckBox(
			(m, y, -m, gvc.UI_CHECK_H),
			t("it", "preview"),
			value=True,
			callback=self.toggle_preview_,
		)
		gvc.style_checkbox(self.w.preview)
		y += gvc.UI_CHECK_H + s

		self.w.status = TextBox((m, y, -m, UI_STATUS_H), "")
		gvc.style_body(self.w.status)
		y += UI_STATUS_H + s

		bw = (W - m * 2 - gvc.UI_BTN_GAP) / 2.0
		self.w.run = Button((m, y, bw, gvc.UI_BTN_H), "", callback=self.apply_)
		self.w.cancel = Button((m + bw + gvc.UI_BTN_GAP, y, bw, gvc.UI_BTN_H), "", callback=self.cancel_)
		gvc.style_action_button(self.w.run, default=True, green_fill=True)
		gvc.style_action_button(self.w.cancel)
		y += gvc.UI_BTN_H + s

		self.w.credit = Button(
			(m, y, W - m * 2 - gvc.UI_LANG_W - 8, gvc.UI_CREDIT_H),
			"",
			callback=self.open_credit_,
		)
		self.w.lang = Button(
			(W - m - gvc.UI_LANG_W, y, gvc.UI_LANG_W, gvc.UI_CREDIT_H),
			"",
			callback=self.toggle_lang_,
		)
		gvc.style_lang_chip(self.w.lang)

		self.apply_language()
		self.refresh_status_()
		self.w.bind("close", self._on_close)
		Glyphs.addCallback(self._draw, DRAWFOREGROUND)
		Glyphs.addCallback(self._ui_update, UPDATEINTERFACE)
		Glyphs.redraw()
		self.w.open()
		gvc.set_window_title(self.w, SCRIPT_TITLE)

	def apply_language(self):
		L = self.lang
		self.w.aboutTitle.set(t(L, "about_title"))
		gvc.style_heading(self.w.aboutTitle)
		self.w.aboutBody.set(t(L, "about_body"))
		gvc.style_body(self.w.aboutBody)
		self.w.instrTitle.set(t(L, "instructions"))
		gvc.style_heading(self.w.instrTitle)
		self.w.instrBody.set(t(L, "body"))
		gvc.style_body(self.w.instrBody)
		try:
			self.w.preview.setTitle(t(L, "preview"))
		except Exception:
			try:
				self.w.preview.getNSButton().setTitle_(t(L, "preview"))
			except Exception:
				pass
		gvc.style_checkbox(self.w.preview)
		self.w.run.setTitle(t(L, "apply"))
		self.w.cancel.setTitle(t(L, "cancel"))
		gvc.style_action_button(self.w.run, default=True, green_fill=True)
		gvc.style_action_button(self.w.cancel)
		gvc.style_credit_line(
			self.w.credit,
			t(L, "credit_prefix"),
			t(L, "credit_name"),
		)
		gvc.style_lang_chip(self.w.lang, t(L, "lang_button"))
		gvc.tint_panel_white(self.w)
		gvc.set_window_title(self.w, SCRIPT_TITLE)
		self.refresh_status_()

	def refresh_status_(self):
		font = Glyphs.font
		msg = t(self.lang, "status_idle")
		if font and font.selectedLayers:
			_geo, msg = resolve_junction(font.selectedLayers[0], lang=self.lang)
		try:
			self.w.status.set(msg)
			gvc.style_body(self.w.status)
		except Exception:
			pass

	def open_credit_(self, sender):
		gvc.open_site(t(self.lang, "site"))

	def toggle_lang_(self, sender):
		self.lang = "en" if self.lang == "it" else "it"
		self.apply_language()

	def toggle_preview_(self, sender):
		self.show_preview = bool(sender.get())
		try:
			Glyphs.redraw()
		except Exception:
			pass

	def _draw(self, layer, info):
		if self.show_preview:
			draw_soft_preview(layer, info, lang=self.lang)

	def _ui_update(self, sender):
		self.refresh_status_()
		if not self.show_preview:
			return
		try:
			Glyphs.redraw()
		except Exception:
			pass

	def apply_(self, sender):
		run_soft_landing(lang=self.lang)
		self.refresh_status_()

	def cancel_(self, sender):
		self.w.close()

	def _remove_callbacks(self):
		gvc.remove_glyphs_callbacks((
			(self._draw, DRAWFOREGROUND),
			(self._ui_update, UPDATEINTERFACE),
		))

	def _on_close(self, sender):
		self._remove_callbacks()
		try:
			Glyphs.redraw()
		except Exception:
			pass


if __name__ == "__main__":
	if HAS_VANILLA:
		GVSoftLandingDialog()
	else:
		run_soft_landing()
