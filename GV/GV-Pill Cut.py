# MenuTitle: GV-Pill Cut
# -*- coding: utf-8 -*-
__doc__ = """
Cuts a geometric semicircle into a stem (including diagonals).
Select two on-curve nodes → goniometer preview → cut inside or outside the stem.
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
		GSNode,
		CURVE,
		LINE,
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
	from vanilla import FloatingWindow, RadioGroup, Button, TextBox, CheckBox
	HAS_VANILLA = True
except Exception:
	HAS_VANILLA = False

try:
	from AppKit import NSPoint, NSBezierPath, NSMakeRect, NSFontAttributeName
	from Foundation import NSString
except Exception:
	NSPoint = NSBezierPath = NSMakeRect = NSFontAttributeName = None
	NSString = None

KAPPA = 4.0 * math.tan(math.pi / 8.0) / 3.0
MAX_SPAN_NODES = 14
SCRIPT_TITLE = "GV-Pill Cut"
__version__ = "0.1.3"

UI_VERSO_H = 20
UI_RADIO_H = 48

V = gvc.V
add = gvc.add
sub = gvc.sub
mul = gvc.mul
dot = gvc.dot
length = gvc.length
unit = gvc.unit
rot90 = gvc.rot90
xy = gvc.xy
project = gvc.project
node_index = gvc.node_index
walk = gvc.walk_indices


def oncurve_neighbor(nodes, idx, step):
	return gvc.oncurve_neighbor(nodes, idx, step, OFFCURVE)


# ── path helpers ───────────────────────────────────────────────────────────

def edge_dir(path, idx, forward=True):
	a = xy(path.nodes[idx])
	j = oncurve_neighbor(path.nodes, idx, 1 if forward else -1)
	if j is None:
		return (1.0, 0.0)
	b = xy(path.nodes[j])
	return unit(V(a, b) if forward else V(b, a))


def span_oncurve_count(path, span):
	return sum(1 for k in span if path.nodes[k].type != OFFCURVE)


def span_geometry_length(path, start_i, end_i, span):
	"""Polyline length start → span → end (node centers)."""
	idxs = [start_i] + list(span) + [end_i]
	total = 0.0
	for a, b in zip(idxs, idxs[1:]):
		total += length(V(xy(path.nodes[a]), xy(path.nodes[b])))
	return total


def span_midpoint(path, start_i, end_i, span):
	pts = [xy(path.nodes[start_i]), xy(path.nodes[end_i])]
	for k in span:
		if path.nodes[k].type != OFFCURVE:
			pts.append(xy(path.nodes[k]))
	n = float(len(pts)) or 1.0
	return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def choose_span(path, i, j, prefer_dir=None, origin=None):
	"""Pick the outline span to replace with the semicircle.

	Ranks by fewer on-curve nodes, then shorter geometry. Optional
	prefer_dir/origin break ties toward the cut side of the stem.
	"""
	n = len(path.nodes)
	candidates = ((i, j, walk(i, j, n)), (j, i, walk(j, i, n)))

	def rank(start, end, span):
		bias = 0.0
		if prefer_dir is not None and origin is not None:
			mid = span_midpoint(path, start, end, span)
			bias = -dot(sub(mid, origin), unit(prefer_dir))
		return (
			span_oncurve_count(path, span),
			span_geometry_length(path, start, end, span),
			bias,
			len(span),
		)

	return min(candidates, key=lambda c: rank(*c))


def path_for_nodes(layer, node_a, node_b):
	"""Return the path that contains both nodes, or None."""
	return next(
		(
			p
			for p in layer.paths
			if node_index(p, node_a) is not None and node_index(p, node_b) is not None
		),
		None,
	)


def point_in_path(path, pt):
	try:
		bp = path.bezierPath
		p = NSPoint(pt[0], pt[1]) if NSPoint else (pt[0], pt[1])
		return bool(bp.containsPoint_(p))
	except Exception:
		return False


def path_centroid(path):
	pts = [xy(n) for n in path.nodes if n.type != OFFCURVE]
	if not pts:
		return (0.0, 0.0)
	n = float(len(pts))
	return (sum(p[0] for p in pts) / n, sum(p[1] for p in pts) / n)


def stem_frame(path, i, j):
	pi, pj = xy(path.nodes[i]), xy(path.nodes[j])
	best = None
	for a in (edge_dir(path, i, True), edge_dir(path, i, False)):
		for b in (edge_dir(path, j, True), edge_dir(path, j, False)):
			if abs(dot(a, b)) < 0.85:
				continue
			s = unit(add(a, b) if dot(a, b) > 0 else sub(a, b))
			w = V(pi, pj)
			along = abs(dot(w, s))
			perp = length(sub(w, mul(s, dot(w, s))))
			if perp < 1.0 or along > perp * 2.5:
				continue
			if best is None or perp > best[0]:
				best = (perp, s)
	return (best[1], best[0]) if best else None


def diameter_on_stem(A, B, s, width):
	s = unit(s)
	along = dot(V(A, B), s)
	A2 = add(A, mul(s, along / 2.0))
	B2 = add(B, mul(s, -along / 2.0))
	p = rot90(s, +1)
	if dot(p, V(A2, B2)) < 0:
		p = rot90(s, -1)
	mid = mul(add(A2, B2), 0.5)
	half = width / 2.0
	A2, B2 = add(mid, mul(p, -half)), add(mid, mul(p, +half))
	A2, B2 = project(A2, A, s), project(B2, B, s)
	along = dot(V(A2, B2), s)
	A2 = add(A2, mul(s, along / 2.0))
	B2 = add(B2, mul(s, -along / 2.0))
	return A2, B2, mul(add(A2, B2), 0.5)


def into_stem(path, center, s, width):
	s = unit(s)
	d = max(width * 0.4, 4.0)
	pos, neg = add(center, mul(s, d)), add(center, mul(s, -d))
	ip, inn = point_in_path(path, pos), point_in_path(path, neg)
	if ip and not inn:
		return s
	if inn and not ip:
		return mul(s, -1.0)
	return s if dot(sub(path_centroid(path), center), s) >= 0 else mul(s, -1.0)


# ── goniometer ─────────────────────────────────────────────────────────────

def _is_oncurve(obj):
	try:
		return obj.type != OFFCURVE and hasattr(obj, "x")
	except Exception:
		return False


def selection_geometry(layer, for_preview=False):
	"""From 2 selected on-curve nodes: circle with diameter ⊥ stem.
	Returns (geo_dict | None, status_string).
	"""
	sel = [o for o in layer.selection if _is_oncurve(o)]
	if len(sel) != 2:
		return None, "Seleziona 2 nodi on-curve nel canvas del glifo"
	na, nb = sel[0], sel[1]
	path = path_for_nodes(layer, na, nb)
	if path is None:
		return None, "I due nodi devono stare sullo stesso path"
	i, j = node_index(path, na), node_index(path, nb)
	start_i, end_i, between = choose_span(path, i, j)
	A, B = xy(path.nodes[start_i]), xy(path.nodes[end_i])

	stem = stem_frame(path, start_i, end_i)
	aligned = False
	if stem is not None and (for_preview or len(between) <= MAX_SPAN_NODES):
		s, width = stem
		A2, B2, C = diameter_on_stem(A, B, s, width)
		aligned = True
	else:
		s = rot90(unit(V(A, B)), +1)
		width = length(V(A, B))
		A2, B2, C = A, B, mul(add(A, B), 0.5)
		if not for_preview and len(between) > MAX_SPAN_NODES:
			return None, "Tratto troppo lungo — avvicina i 2 nodi del diametro"
		if not for_preview and stem is None:
			return None, "Asta non riconosciuta"

	r = length(V(A2, B2)) / 2.0
	if r < 0.5:
		return None, "Distanza troppo piccola"

	across = unit(V(A2, B2))
	along = unit(s)
	left, right = A2, B2
	if left[0] > right[0] or (abs(left[0] - right[0]) < 1e-6 and left[1] < right[1]):
		left, right = right, left
		across = mul(across, -1.0)
	sup = add(C, mul(along, r))
	inf = add(C, mul(along, -r))
	if sup[1] < inf[1]:
		sup, inf = inf, sup
		along = mul(along, -1.0)

	into = into_stem(path, C, s, width) if aligned else along
	status = "Goniometro attivo · r=%.0f Ø=%.0f" % (r, 2 * r)
	if aligned:
		status += " · diametro ⊥ asta"
	else:
		status += " · (asta non rilevata, diametro grezzo)"
	return {
		"center": C,
		"radius": r,
		"diameter": 2.0 * r,
		"stem": s,
		"across": across,
		"along": along,
		"left": left,
		"right": right,
		"sup": sup,
		"inf": inf,
		"into": into,
		"width": width,
		"aligned": aligned,
		"angle_deg": math.degrees(math.atan2(across[1], across[0])),
	}, status


def _normalize_inclination(angle_deg):
	a = float(angle_deg) % 180.0
	if a > 90.0:
		a -= 180.0
	if a <= -90.0:
		a += 180.0
	return a


def _fmt_dec(value, decimals=1):
	return (("%%.%df" % decimals) % float(value)).replace(".", ",")


def _draw_readout_block(C, r, scale, color, radius, diameter, angle_deg):
	if color is None:
		return
	incl = abs(_normalize_inclination(angle_deg))
	line = "r: %s  Ø: %s  %s°" % (
		_fmt_dec(radius, 1),
		_fmt_dec(diameter, 1),
		_fmt_dec(incl, 1),
	)
	anchor = (C[0], C[1] - r - 16.0 / max(scale, 0.01))
	if NSString is not None and gvc.NSFont is not None:
		size = max(10.0, 11.0 / max(scale, 0.01))
		attrs = {NSFontAttributeName: gvc.NSFont.systemFontOfSize_(size)}
		tw = float(NSString.stringWithString_(line).sizeWithAttributes_(attrs).width)
		anchor = (C[0] - tw * 0.5, anchor[1])
	gvc.draw_label(line, anchor, scale, color)


def draw_goniometer(layer, info):
	try:
		if NSBezierPath is None:
			return
		geo, _status = selection_geometry(layer, for_preview=True)
		if geo is None:
			return
		scale = gvc.scale_from_info(info)
		fill = gvc.glyphs_green(0.25)
		green = gvc.glyphs_green(1.0)
		if fill is None or green is None:
			return

		C, r = geo["center"], geo["radius"]
		L, R, Sup, Inf = geo["left"], geo["right"], geo["sup"], geo["inf"]
		lw = max(0.3, 0.425 / max(scale, 0.01))
		dash = [3.0 / max(scale, 0.01), 2.5 / max(scale, 0.01)]

		circle = NSBezierPath.bezierPathWithOvalInRect_(
			NSMakeRect(C[0] - r, C[1] - r, r * 2.0, r * 2.0)
		)
		fill.set()
		circle.fill()

		green.set()

		def dotted(a, b):
			path = NSBezierPath.bezierPath()
			path.moveToPoint_(tuple(a))
			path.lineToPoint_(tuple(b))
			path.setLineWidth_(lw)
			try:
				path.setLineDash_count_phase_(dash, 2, 0.0)
			except Exception:
				pass
			path.stroke()

		dotted(L, R)
		dotted(Sup, Inf)

		# Radius on the angle bisector of ⊥ diameter and stem-parallel axis
		rad_dir = unit(add(unit(sub(R, C)), unit(sub(Sup, C))))
		rad_end = add(C, mul(rad_dir, r))
		rad = NSBezierPath.bezierPath()
		rad.moveToPoint_(tuple(C))
		rad.lineToPoint_(tuple(rad_end))
		rad.setLineWidth_(lw)
		rad.stroke()

		for pt in (L, R, Sup, Inf):
			gvc.mark_point(pt, scale, green, 3.0)
		gvc.mark_point(C, scale, green, 2.2)
		_draw_readout_block(C, r, scale, green, r, geo["diameter"], geo["angle_deg"])
	except Exception:
		traceback.print_exc()


# ── cut ────────────────────────────────────────────────────────────────────

def make_node(type_, pt, smooth=False):
	nd = GSNode()
	nd.type = type_
	nd.smooth = bool(smooth)
	nd.x, nd.y = float(pt[0]), float(pt[1])
	return nd


def semicircle(A, B, side):
	"""Geometric semicircle A → M → B as two κ quarters.
	side >= 0 → CCW from A; else CW. Returns [A,o1,o2,M,o3,o4,B] or None.
	"""
	A = (float(A[0]), float(A[1]))
	B = (float(B[0]), float(B[1]))
	C = ((A[0] + B[0]) * 0.5, (A[1] + B[1]) * 0.5)
	r = length(V(A, B)) / 2.0
	if r < 0.5:
		return None

	ta = math.atan2(A[1] - C[1], A[0] - C[0])
	sweep = math.pi if side >= 0 else -math.pi
	end = (C[0] + r * math.cos(ta + sweep), C[1] + r * math.sin(ta + sweep))
	if length(sub(end, B)) > max(1.0, r * 0.05):
		sweep = -sweep

	tm = ta + sweep / 2.0
	M = (C[0] + r * math.cos(tm), C[1] + r * math.sin(tm))

	def quarter(t0, t1):
		sg = 1.0 if (t1 - t0) > 0 else -1.0
		h = r * KAPPA
		t0u = (-math.sin(t0) * sg, math.cos(t0) * sg)
		t1u = (-math.sin(t1) * sg, math.cos(t1) * sg)
		p0 = (C[0] + r * math.cos(t0), C[1] + r * math.sin(t0))
		p3 = (C[0] + r * math.cos(t1), C[1] + r * math.sin(t1))
		return add(p0, mul(t0u, h)), sub(p3, mul(t1u, h))

	c1, c2 = quarter(ta, tm)
	c3, c4 = quarter(tm, ta + sweep)
	return [A, c1, c2, M, c3, c4, B]


def rebuild_path(old_nodes, start_i, end_i, between, pts):
	"""Replace span start→end with semicircle pts. A/B are corners; apex M is smooth."""
	n = len(old_nodes)
	remove = set(between)
	st = make_node(LINE, pts[0], False)
	src_start = old_nodes[start_i]
	if src_start.type != OFFCURVE:
		st.type = src_start.type
	st.smooth = False
	out = [
		st,
		make_node(OFFCURVE, pts[1]),
		make_node(OFFCURVE, pts[2]),
		make_node(CURVE, pts[3], True),
		make_node(OFFCURVE, pts[4]),
		make_node(OFFCURVE, pts[5]),
		make_node(CURVE, pts[6], False),
	]
	k, guard = (end_i + 1) % n, 0
	while k != start_i and guard <= n:
		guard += 1
		if k not in remove:
			src = old_nodes[k]
			out.append(make_node(src.type, xy(src), bool(src.smooth)))
		k = (k + 1) % n
	return out


def chord_is_across_stem(A, B, s):
	"""True if A–B is mostly perpendicular to the stem axis (opposite edges)."""
	chord = V(A, B)
	along = abs(dot(chord, s))
	perp = length(sub(chord, mul(s, dot(chord, s))))
	return perp >= 1.0 and along <= perp * 1.25


def diameter_is_valid(A, B, A2, B2, s, width):
	"""True if aligned diameter still matches stem width and stays ⊥ to the stem."""
	if length(V(A, A2)) > width * 3 or length(V(B, B2)) > width * 3:
		return False
	if abs(length(V(A2, B2)) - width) > max(2.0, width * 0.15):
		return False
	if abs(dot(unit(V(A2, B2)), s)) > 0.35:
		return False
	return True


def semicircle_into(A2, B2, center, into):
	"""Semicircle A2→B2 whose apex points along `into`. None on failure."""
	pts = semicircle(A2, B2, +1)
	if pts is None:
		return None
	if dot(sub(pts[3], center), into) < 0:
		pts = semicircle(A2, B2, -1)
	return pts


# ── i18n ───────────────────────────────────────────────────────────────────

UI = {
	"it": {
		"about_title": "Cos’è GV-Pill Cut",
		"about_body": (
			"Inserisce una semicirconferenza su un’asta (retta o diagonale) "
			"con diametro perpendicolare all’asse dell’asta."
		),
		"instructions": "Istruzioni",
		"body": (
			"Apri un glifo e seleziona due nodi on-curve sui lati opposti "
			"dell’asta. Il goniometro mostra l’anteprima della circonferenza."
		),
		"verso": "Verso del taglio",
		"verso_in": "All’interno dell’asta",
		"verso_out": "All’esterno dell’asta",
		"goniometer": "Goniometro",
		"apply": "Applica",
		"cancel": "Annulla",
		"credit_prefix": "Sviluppo: ",
		"credit_name": "Pasquale de Sario",
		"site": "https://pasqualedesario.eu/#it",
		"lang_button": "English",
		"no_font": "Nessun font aperto.",
		"no_glyph": "Seleziona un glifo in Edit View.",
		"need_two": (
			"Seleziona esattamente due nodi on-curve\n"
			"sui lati opposti dell’asta (estremi del diametro)."
		),
		"same_path": "I due nodi devono appartenere allo stesso path.",
		"notify": "Taglio · %s",
		"verso_key_in": "all’interno",
		"verso_key_out": "all’esterno",
		"err_long": (
			"Il tratto tra i due nodi è troppo lungo (%d nodi).\n"
			"Seleziona i due estremi del diametro del taglio."
		),
		"err_stem": "Asta non riconosciuta.\nSeleziona due nodi sui lati opposti dell’asta.",
		"err_width": "Spessore asta non valido (%.1f).",
		"err_align": "Allineamento del diametro non riuscito — ripeti la selezione.",
		"err_radius": "Raggio troppo piccolo.",
		"err_rebuild": "Ricostruzione del path non riuscita.",
	},
	"en": {
		"about_title": "What is GV-Pill Cut",
		"about_body": (
			"Inserts a semicircle on a stem (straight or diagonal) "
			"with the diameter perpendicular to the stem axis."
		),
		"instructions": "Instructions",
		"body": (
			"Open a glyph and select two on-curve nodes on opposite sides "
			"of the stem. The goniometer shows a preview of the circle."
		),
		"verso": "Cut direction",
		"verso_in": "Inside the stem",
		"verso_out": "Outside the stem",
		"goniometer": "Goniometer",
		"apply": "Apply",
		"cancel": "Cancel",
		"credit_prefix": "Development: ",
		"credit_name": "Pasquale de Sario",
		"site": "https://pasqualedesario.eu/#en",
		"lang_button": "Italiano",
		"no_font": "No font open.",
		"no_glyph": "Select a glyph in Edit View.",
		"need_two": (
			"Select exactly two on-curve nodes\n"
			"on opposite sides of the stem (diameter ends)."
		),
		"same_path": "Both nodes must belong to the same path.",
		"notify": "Cut · %s",
		"verso_key_in": "inside",
		"verso_key_out": "outside",
		"err_long": (
			"The span between the nodes is too long (%d nodes).\n"
			"Select the two ends of the cut diameter."
		),
		"err_stem": "Stem not recognized.\nSelect two nodes on opposite sides of the stem.",
		"err_width": "Invalid stem width (%.1f).",
		"err_align": "Diameter alignment failed — try selecting again.",
		"err_radius": "Radius too small.",
		"err_rebuild": "Path rebuild failed.",
	},
}


def t(lang, key):
	return gvc.t(UI, lang, key)


def apply_cut(path, node_a, node_b, verso="dentro", lang="it"):
	i, j = node_index(path, node_a), node_index(path, node_b)
	if i is None or j is None or i == j:
		return False, t(lang, "same_path")

	# Provisional span → stem → into, then re-rank span toward the cut side.
	start_i, end_i, between = choose_span(path, i, j)
	if len(between) > MAX_SPAN_NODES:
		return False, t(lang, "err_long") % len(between)
	old = list(path.nodes)
	stem = stem_frame(path, start_i, end_i)
	if stem is None:
		return False, t(lang, "err_stem")
	s, width = stem
	if width < 1.0 or width > 2000:
		return False, t(lang, "err_width") % width

	A, B = xy(old[start_i]), xy(old[end_i])
	_A2, _B2, center = diameter_on_stem(A, B, s, width)
	into = into_stem(path, center, s, width)
	if verso == "fuori":
		into = mul(into, -1.0)

	start_i, end_i, between = choose_span(
		path, i, j, prefer_dir=into, origin=center
	)
	if len(between) > MAX_SPAN_NODES:
		return False, t(lang, "err_long") % len(between)

	A, B = xy(old[start_i]), xy(old[end_i])
	if not chord_is_across_stem(A, B, s):
		return False, t(lang, "err_stem")

	A2, B2, center = diameter_on_stem(A, B, s, width)
	if not diameter_is_valid(A, B, A2, B2, s, width):
		return False, t(lang, "err_align")

	pts = semicircle_into(A2, B2, center, into)
	if pts is None:
		return False, t(lang, "err_radius")

	new_nodes = rebuild_path(old, start_i, end_i, between, pts)
	if len(new_nodes) < 3:
		return False, t(lang, "err_rebuild")
	path.nodes = new_nodes
	try:
		path.closed = True
	except Exception:
		pass
	return True, "ok"


def run_cutter(verso="dentro", lang="it"):
	font = Glyphs.font
	if not font:
		Message(t(lang, "no_font"), SCRIPT_TITLE)
		return
	layers = font.selectedLayers
	if not layers:
		Message(t(lang, "no_glyph"), SCRIPT_TITLE)
		return
	layer = layers[0]
	sel = [o for o in layer.selection if isinstance(o, GSNode) and o.type != OFFCURVE]
	if len(sel) != 2:
		Message(t(lang, "need_two"), SCRIPT_TITLE)
		return
	na, nb = sel[0], sel[1]
	path = path_for_nodes(layer, na, nb)
	if path is None:
		Message(t(lang, "same_path"), SCRIPT_TITLE)
		return

	glyph = getattr(layer, "parent", None)
	font.disableUpdateInterface()
	ok, msg = False, ""
	try:
		if glyph is not None:
			try:
				glyph.beginUndo()
			except Exception:
				pass
		ok, msg = apply_cut(path, na, nb, verso=verso, lang=lang)
		layer.selection = []
		if glyph is not None:
			try:
				glyph.endUndo()
			except Exception:
				pass
	finally:
		font.enableUpdateInterface()
	if ok:
		label = t(lang, "verso_key_in") if verso == "dentro" else t(lang, "verso_key_out")
		Glyphs.showNotification(SCRIPT_TITLE, t(lang, "notify") % label)
		Glyphs.redraw()
	else:
		Message(msg, SCRIPT_TITLE)


# ── dialog ─────────────────────────────────────────────────────────────────

class GVPillCutDialog(object):
	def __init__(self):
		m, s, inn, W = gvc.UI_MARGIN, gvc.UI_SECTION, gvc.UI_INNER, gvc.UI_WIDTH
		H = (
			m
			+ gvc.UI_TITLE_H + inn + gvc.UI_ABOUT_H + s
			+ gvc.UI_TITLE_H + inn + gvc.UI_INSTR_BODY_H + s
			+ UI_VERSO_H + inn + UI_RADIO_H + s
			+ gvc.UI_CHECK_H + s
			+ gvc.UI_BTN_H + s
			+ gvc.UI_CREDIT_H
			+ m
		)

		self.lang = "it"
		self.show_goniometer = True
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

		self.w.versoLabel = TextBox((m, y, -m, UI_VERSO_H), "")
		gvc.style_heading(self.w.versoLabel)
		y += UI_VERSO_H + inn
		self.w.verso = RadioGroup(
			(m, y, -m, UI_RADIO_H),
			[t("it", "verso_in"), t("it", "verso_out")],
		)
		self.w.verso.set(0)
		gvc.style_radio(self.w.verso)
		y += UI_RADIO_H + s

		self.w.goniometer = CheckBox(
			(m, y, -m, gvc.UI_CHECK_H),
			t("it", "goniometer"),
			value=True,
			callback=self.toggle_goniometer_,
		)
		gvc.style_checkbox(self.w.goniometer)
		y += gvc.UI_CHECK_H + s

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
		self.w.versoLabel.set(t(L, "verso"))
		gvc.style_heading(self.w.versoLabel)
		try:
			matrix = self.w.verso.getNSMatrix()
			matrix.cellAtRow_column_(0, 0).setTitle_(t(L, "verso_in"))
			matrix.cellAtRow_column_(1, 0).setTitle_(t(L, "verso_out"))
		except Exception:
			pass
		gvc.style_radio(self.w.verso)
		try:
			self.w.goniometer.setTitle(t(L, "goniometer"))
		except Exception:
			try:
				self.w.goniometer.getNSButton().setTitle_(t(L, "goniometer"))
			except Exception:
				pass
		gvc.style_checkbox(self.w.goniometer)
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

	def open_credit_(self, sender):
		gvc.open_site(t(self.lang, "site"))

	def toggle_lang_(self, sender):
		self.lang = "en" if self.lang == "it" else "it"
		self.apply_language()

	def toggle_goniometer_(self, sender):
		self.show_goniometer = bool(sender.get())
		try:
			Glyphs.redraw()
		except Exception:
			pass

	def _draw(self, layer, info):
		if self.show_goniometer:
			draw_goniometer(layer, info)

	def _ui_update(self, sender):
		if not self.show_goniometer:
			return
		try:
			Glyphs.redraw()
		except Exception:
			pass

	def apply_(self, sender):
		run_cutter("dentro" if self.w.verso.get() == 0 else "fuori", lang=self.lang)

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
		GVPillCutDialog()
	else:
		run_cutter("dentro")
