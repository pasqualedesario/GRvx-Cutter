# MenuTitle: GRvx Cutter
# -*- coding: utf-8 -*-
__doc__ = """
Cuts a geometric semicircle into a stem (including diagonals).
Select two on-curve nodes → goniometer preview → cut inside or outside the stem.
"""

import math
import traceback
import webbrowser

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
	from GlyphsApp import NodeSmoothColor
except Exception:
	NodeSmoothColor = None

try:
	from vanilla import FloatingWindow, RadioGroup, Button, TextBox, CheckBox
	HAS_VANILLA = True
except Exception:
	HAS_VANILLA = False

try:
	from AppKit import (
		NSFont,
		NSPoint,
		NSColor,
		NSBezierPath,
		NSMakeRect,
		NSFontAttributeName,
		NSForegroundColorAttributeName,
		NSUnderlineStyleAttributeName,
		NSUnderlineStyleSingle,
		NSWorkspace,
		NSURL,
	)
	from Foundation import NSString, NSMutableAttributedString, NSAttributedString
except Exception:
	NSFont = NSPoint = NSColor = NSBezierPath = None
	NSMakeRect = NSFontAttributeName = NSForegroundColorAttributeName = None
	NSUnderlineStyleAttributeName = NSUnderlineStyleSingle = None
	NSWorkspace = NSURL = None
	NSString = NSMutableAttributedString = NSAttributedString = None

KAPPA = 4.0 * math.tan(math.pi / 8.0) / 3.0
MAX_SPAN_NODES = 14
SCRIPT_TITLE = "GRvx Cutter"
__version__ = "0.1.0"

# UI layout (SECTION == window margin)
UI_MARGIN = 18
UI_SECTION = UI_MARGIN
UI_INNER = 2
UI_BTN_GAP = 20
UI_WIDTH = 340
UI_FONT_SIZE = 13.0
CREDIT_FONT_SIZE = 10.0
UI_TITLE_H = 20
UI_ABOUT_H = 52
UI_INSTR_BODY_H = 52
UI_VERSO_H = 20
UI_RADIO_H = 48
UI_CHECK_H = 24
UI_BTN_H = 28
UI_CREDIT_H = 20
UI_LANG_W = 96
NS_BEZEL_RECESSED = 13
NS_CONTROL_SIZE_SMALL = 1


# ── math ───────────────────────────────────────────────────────────────────

def V(a, b):
	return (b[0] - a[0], b[1] - a[1])


def add(a, b):
	return (a[0] + b[0], a[1] + b[1])


def sub(a, b):
	return (a[0] - b[0], a[1] - b[1])


def mul(a, s):
	return (a[0] * s, a[1] * s)


def dot(a, b):
	return a[0] * b[0] + a[1] * b[1]


def length(a):
	return math.hypot(a[0], a[1])


def unit(a):
	L = length(a)
	return (1.0, 0.0) if L < 1e-12 else (a[0] / L, a[1] / L)


def rot90(a, sign=1.0):
	return (-a[1] * sign, a[0] * sign)


def xy(n):
	return (float(n.x), float(n.y))


def project(P, origin, direction):
	d = unit(direction)
	return add(origin, mul(d, dot(sub(P, origin), d)))


# ── path helpers ───────────────────────────────────────────────────────────

def node_index(path, node):
	for i, n in enumerate(path.nodes):
		if n is node:
			return i
	for i, n in enumerate(path.nodes):
		if n.type == node.type and abs(n.x - node.x) < 1e-6 and abs(n.y - node.y) < 1e-6:
			return i
	return None


def walk(i, j, n):
	out, k = [], (i + 1) % n
	while k != j and len(out) <= n:
		out.append(k)
		k = (k + 1) % n
	return out


def oncurve_neighbor(nodes, idx, step):
	n = len(nodes)
	k = (idx + step) % n
	for _ in range(n):
		if nodes[k].type != OFFCURVE:
			return k
		k = (k + step) % n
	return None


def edge_dir(path, idx, forward=True):
	a = xy(path.nodes[idx])
	j = oncurve_neighbor(path.nodes, idx, 1 if forward else -1)
	b = xy(path.nodes[j])
	return unit(V(a, b) if forward else V(b, a))


def choose_span(path, i, j):
	n = len(path.nodes)
	fwd, bwd = walk(i, j, n), walk(j, i, n)

	def rank(span):
		n_off = sum(1 for k in span if path.nodes[k].type == OFFCURVE)
		short_notch = 0 if (n_off > 0 and len(span) <= MAX_SPAN_NODES) else 1
		return (short_notch, len(span))

	return (i, j, fwd) if rank(fwd) <= rank(bwd) else (j, i, bwd)


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
	path = next(
		(p for p in layer.paths if node_index(p, na) is not None and node_index(p, nb) is not None),
		None,
	)
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


def _color_rgba(r, g, b, a):
	if NSColor is None:
		return None
	try:
		return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)
	except Exception:
		return None


def _glyphs_green(alpha=1.0):
	color = NodeSmoothColor
	if color is None:
		try:
			color = Glyphs.colorObjectToNSColor("GREEN")
		except Exception:
			color = None
	if color is None:
		color = _color_rgba(0.2, 0.75, 0.25, 1.0)
	if color is None:
		return None
	try:
		return color.colorWithAlphaComponent_(float(alpha))
	except Exception:
		return color


def _draw_label(text, pt, scale, color, offset=(0.0, 0.0), bold=False):
	if NSString is None or NSFont is None or color is None:
		return
	size = max(10.0, 11.0 / max(scale, 0.01))
	font = NSFont.boldSystemFontOfSize_(size) if bold else NSFont.systemFontOfSize_(size)
	attrs = {
		NSFontAttributeName: font,
		NSForegroundColorAttributeName: color,
	}
	NSString.stringWithString_(text).drawAtPoint_withAttributes_(
		(pt[0] + offset[0] / scale, pt[1] + offset[1] / scale),
		attrs,
	)


def _mark(pt, scale, color, radius_px=3.5):
	if NSBezierPath is None or NSMakeRect is None or color is None:
		return
	rr = radius_px / max(scale, 0.01)
	color.set()
	NSBezierPath.bezierPathWithOvalInRect_(
		NSMakeRect(pt[0] - rr, pt[1] - rr, rr * 2, rr * 2)
	).fill()


def _scale_from_info(info):
	if isinstance(info, dict):
		for key in ("Scale", "scale", "ScaleFactor"):
			if key in info:
				try:
					return float(info[key])
				except Exception:
					pass
	return 1.0


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
	if NSString is not None and NSFont is not None:
		size = max(10.0, 11.0 / max(scale, 0.01))
		attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(size)}
		tw = float(NSString.stringWithString_(line).sizeWithAttributes_(attrs).width)
		anchor = (C[0] - tw * 0.5, anchor[1])
	_draw_label(line, anchor, scale, color)


def draw_goniometer(layer, info):
	try:
		if NSBezierPath is None:
			return
		geo, _status = selection_geometry(layer, for_preview=True)
		if geo is None:
			return
		scale = _scale_from_info(info)
		fill = _glyphs_green(0.25)
		green = _glyphs_green(1.0)
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
			_mark(pt, scale, green, 3.0)
		_mark(C, scale, green, 2.2)
		_draw_readout_block(C, r, scale, green, r, geo["diameter"], geo["angle_deg"])
	except Exception:
		print(traceback.format_exc())


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
	"""Replace span with semicircle. A/B stay corners; only apex M is smooth."""
	n = len(old_nodes)
	remove = set(between)
	st = make_node(LINE, pts[0], False)
	if old_nodes[start_i].type == LINE:
		st.type = LINE
	elif old_nodes[start_i].type != OFFCURVE:
		st.type = old_nodes[start_i].type
	st.smooth = False
	arc = [
		make_node(OFFCURVE, pts[1]),
		make_node(OFFCURVE, pts[2]),
		make_node(CURVE, pts[3], True),
		make_node(OFFCURVE, pts[4]),
		make_node(OFFCURVE, pts[5]),
		make_node(CURVE, pts[6], False),
	]
	out = [st] + arc
	k, guard = (end_i + 1) % n, 0
	while k != start_i and guard <= n:
		guard += 1
		if k not in remove:
			src = old_nodes[k]
			out.append(make_node(src.type, xy(src), src.smooth))
		k = (k + 1) % n
	return out


# ── i18n ───────────────────────────────────────────────────────────────────

UI = {
	"it": {
		"about_title": "Cos’è GRvx Cutter",
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
		"credit_prefix": "Development: ",
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
		"err_same_path": "I due nodi devono appartenere allo stesso path.",
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
		"about_title": "What is GRvx Cutter",
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
		"err_same_path": "Both nodes must belong to the same path.",
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
	return UI.get(lang, UI["it"]).get(key, UI["it"].get(key, key))


def open_site(url):
	try:
		if NSWorkspace is not None and NSURL is not None:
			NSWorkspace.sharedWorkspace().openURL_(NSURL.URLWithString_(url))
			return
	except Exception:
		pass
	try:
		webbrowser.open(url)
	except Exception:
		pass


def apply_cut(path, node_a, node_b, verso="dentro", lang="it"):
	i, j = node_index(path, node_a), node_index(path, node_b)
	if i is None or j is None or i == j:
		return False, t(lang, "err_same_path")
	start_i, end_i, between = choose_span(path, i, j)
	if len(between) > MAX_SPAN_NODES:
		return False, t(lang, "err_long") % len(between)
	old = list(path.nodes)
	A, B = xy(old[start_i]), xy(old[end_i])
	stem = stem_frame(path, start_i, end_i)
	if stem is None:
		return False, t(lang, "err_stem")
	s, width = stem
	if width < 1.0 or width > 2000:
		return False, t(lang, "err_width") % width
	A2, B2, center = diameter_on_stem(A, B, s, width)
	if length(V(A, A2)) > width * 3 or length(V(B, B2)) > width * 3:
		return False, t(lang, "err_align")
	into = into_stem(path, center, s, width)
	if verso == "fuori":
		into = mul(into, -1.0)
	pts = semicircle(A2, B2, +1)
	if pts is None:
		return False, t(lang, "err_radius")
	if dot(sub(pts[3], center), into) < 0:
		pts = semicircle(A2, B2, -1)
		if pts is None:
			return False, t(lang, "err_radius")
	new_nodes = rebuild_path(old, start_i, end_i, between, pts)
	if len(new_nodes) < 3:
		return False, t(lang, "err_rebuild")
	path.nodes = new_nodes
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
	path = next(
		(p for p in layer.paths if node_index(p, na) is not None and node_index(p, nb) is not None),
		None,
	)
	if path is None:
		Message(t(lang, "same_path"), SCRIPT_TITLE)
		return
	font.disableUpdateInterface()
	ok, msg = False, ""
	try:
		ok, msg = apply_cut(path, na, nb, verso=verso, lang=lang)
		layer.selection = []
	finally:
		font.enableUpdateInterface()
	if ok:
		label = t(lang, "verso_key_in") if verso == "dentro" else t(lang, "verso_key_out")
		Glyphs.showNotification(SCRIPT_TITLE, t(lang, "notify") % label)
		Glyphs.redraw()
	else:
		Message(msg, SCRIPT_TITLE)


# ── UI helpers ─────────────────────────────────────────────────────────────

def _ui_font(bold=False):
	if not NSFont:
		return None
	if bold:
		return NSFont.boldSystemFontOfSize_(UI_FONT_SIZE)
	return NSFont.systemFontOfSize_(UI_FONT_SIZE)


def _credit_font():
	return NSFont.systemFontOfSize_(CREDIT_FONT_SIZE) if NSFont else None


def _text_black():
	if NSColor is None:
		return None
	try:
		return NSColor.blackColor()
	except Exception:
		return None


def _measure_text(text, font):
	if NSString is None or font is None:
		return float(len(text) * 6)
	attrs = {NSFontAttributeName: font}
	return float(NSString.stringWithString_(text).sizeWithAttributes_(attrs).width)


def tint_panel_white(window):
	if NSColor is None:
		return
	try:
		white = NSColor.whiteColor()
	except Exception:
		return
	try:
		view = window.getNSView()
		view.setWantsLayer_(True)
		view.layer().setBackgroundColor_(white.CGColor())
	except Exception:
		pass
	try:
		nsw = window.getNSWindow()
		nsw.setBackgroundColor_(white)
		nsw.setOpaque_(True)
	except Exception:
		pass


def style_window_title_bold(window, title=SCRIPT_TITLE):
	# Only set the title string. Do not walk the private titlebar views or
	# force boldSystemFont — that can clip glyphs (e.g. a cut through the "r").
	try:
		window.getNSWindow().setTitle_(title)
	except Exception:
		pass


def style_heading(box):
	try:
		field = box.getNSTextField()
		font = _ui_font(bold=True)
		if font:
			field.setFont_(font)
		black = _text_black()
		if black is not None:
			field.setTextColor_(black)
		field.setDrawsBackground_(False)
	except Exception:
		pass


def style_body(box):
	try:
		field = box.getNSTextField()
		font = _ui_font(bold=False)
		if font:
			field.setFont_(font)
		black = _text_black()
		if black is not None:
			field.setTextColor_(black)
		field.setSelectable_(False)
		field.setDrawsBackground_(False)
	except Exception:
		pass


def style_radio(radio):
	try:
		matrix = radio.getNSMatrix()
		font = _ui_font(bold=False)
		black = _text_black()
		if font:
			matrix.setFont_(font)
		for row in range(matrix.numberOfRows()):
			for col in range(matrix.numberOfColumns()):
				cell = matrix.cellAtRow_column_(row, col)
				if cell is None:
					continue
				if font:
					cell.setFont_(font)
				if black is not None:
					try:
						cell.setTextColor_(black)
					except Exception:
						pass
	except Exception:
		pass


def style_checkbox(checkbox):
	try:
		ns = checkbox.getNSButton()
		font = _ui_font(bold=False)
		black = _text_black()
		title = ns.title() or ""
		attrs = {}
		if font is not None:
			attrs[NSFontAttributeName] = font
			ns.setFont_(font)
		if black is not None and NSForegroundColorAttributeName:
			attrs[NSForegroundColorAttributeName] = black
		if attrs and NSAttributedString is not None:
			ns.setAttributedTitle_(
				NSAttributedString.alloc().initWithString_attributes_(title, attrs)
			)
	except Exception:
		pass


def style_credit_line(button, prefix, name, url=None):
	full = prefix + name
	font = _credit_font()
	base = _text_black()
	link_color = _glyphs_green(1.0) or base
	try:
		ns = button.getNSButton()
		ns.setBordered_(False)
		ns.setButtonType_(0)
		try:
			ns.setAlignment_(0)
		except Exception:
			pass
		if NSMutableAttributedString is None:
			ns.setTitle_(full)
			if font:
				ns.setFont_(font)
			return
		attr = NSMutableAttributedString.alloc().initWithString_(full)
		base_attrs = {}
		if font is not None:
			base_attrs[NSFontAttributeName] = font
		if base is not None and NSForegroundColorAttributeName:
			base_attrs[NSForegroundColorAttributeName] = base
		if base_attrs:
			attr.addAttributes_range_(base_attrs, (0, len(full)))
		link_attrs = {}
		if font is not None:
			link_attrs[NSFontAttributeName] = font
		if link_color is not None and NSForegroundColorAttributeName:
			link_attrs[NSForegroundColorAttributeName] = link_color
		if NSUnderlineStyleAttributeName is not None and NSUnderlineStyleSingle is not None:
			link_attrs[NSUnderlineStyleAttributeName] = NSUnderlineStyleSingle
		if link_attrs and name:
			attr.addAttributes_range_(link_attrs, (len(prefix), len(name)))
		ns.setAttributedTitle_(attr)
		try:
			x, y, _ow, h = button.getPosSize()
			button.setPosSize((x, y, max(_measure_text(full, font) + 12.0, 80.0), h))
		except Exception:
			pass
	except Exception:
		pass


def style_lang_chip(button, title=None):
	try:
		ns = button.getNSButton()
		ns.setTitle_(title if title is not None else (ns.title() or ""))
		ns.setBezelStyle_(NS_BEZEL_RECESSED)
		try:
			ns.setControlSize_(NS_CONTROL_SIZE_SMALL)
		except Exception:
			pass
		font = _credit_font()
		if font:
			ns.setFont_(font)
		try:
			ns.setWantsLayer_(True)
			layer = ns.layer()
			if layer is not None:
				layer.setCornerRadius_(8.0)
				layer.setMasksToBounds_(True)
		except Exception:
			pass
	except Exception:
		pass


def style_action_button(button, default=False, green_fill=False):
	try:
		ns = button.getNSButton()
		if default:
			ns.setKeyEquivalent_("\r")
		font = _ui_font(bold=False)
		black = _text_black()
		title = ns.title() or ""
		if green_fill:
			soft = _glyphs_green(0.25)
			if soft is not None:
				try:
					ns.setBezelColor_(soft)
				except Exception:
					pass
		else:
			try:
				ns.setBezelColor_(None)
			except Exception:
				pass
			try:
				ns.setContentTintColor_(None)
			except Exception:
				pass
		attrs = {}
		if font is not None:
			attrs[NSFontAttributeName] = font
			ns.setFont_(font)
		if black is not None and NSForegroundColorAttributeName:
			attrs[NSForegroundColorAttributeName] = black
		if attrs and title and NSAttributedString is not None:
			ns.setAttributedTitle_(
				NSAttributedString.alloc().initWithString_attributes_(title, attrs)
			)
	except Exception:
		pass


# ── dialog ─────────────────────────────────────────────────────────────────

class GRvxCutterDialog(object):
	def __init__(self):
		m, s, inn, W = UI_MARGIN, UI_SECTION, UI_INNER, UI_WIDTH
		H = (
			m
			+ UI_TITLE_H + inn + UI_ABOUT_H + s
			+ UI_TITLE_H + inn + UI_INSTR_BODY_H + s
			+ UI_VERSO_H + inn + UI_RADIO_H + s
			+ UI_CHECK_H + s
			+ UI_BTN_H + s
			+ UI_CREDIT_H
			+ m
		)

		self.lang = "it"
		self.show_goniometer = True
		self.w = FloatingWindow((W, H), SCRIPT_TITLE)
		tint_panel_white(self.w)
		style_window_title_bold(self.w)
		y = m

		self.w.aboutTitle = TextBox((m, y, -m, UI_TITLE_H), "")
		style_heading(self.w.aboutTitle)
		y += UI_TITLE_H + inn
		self.w.aboutBody = TextBox((m, y, -m, UI_ABOUT_H), "")
		style_body(self.w.aboutBody)
		y += UI_ABOUT_H + s

		self.w.instrTitle = TextBox((m, y, -m, UI_TITLE_H), "")
		style_heading(self.w.instrTitle)
		y += UI_TITLE_H + inn
		self.w.instrBody = TextBox((m, y, -m, UI_INSTR_BODY_H), "")
		style_body(self.w.instrBody)
		y += UI_INSTR_BODY_H + s

		self.w.versoLabel = TextBox((m, y, -m, UI_VERSO_H), "")
		style_heading(self.w.versoLabel)
		y += UI_VERSO_H + inn
		self.w.verso = RadioGroup(
			(m, y, -m, UI_RADIO_H),
			[t("it", "verso_in"), t("it", "verso_out")],
		)
		self.w.verso.set(0)
		style_radio(self.w.verso)
		y += UI_RADIO_H + s

		self.w.goniometer = CheckBox(
			(m, y, -m, UI_CHECK_H),
			t("it", "goniometer"),
			value=True,
			callback=self.toggle_goniometer_,
		)
		style_checkbox(self.w.goniometer)
		y += UI_CHECK_H + s

		bw = (W - m * 2 - UI_BTN_GAP) / 2.0
		self.w.run = Button((m, y, bw, UI_BTN_H), "", callback=self.apply_)
		self.w.cancel = Button((m + bw + UI_BTN_GAP, y, bw, UI_BTN_H), "", callback=self.cancel_)
		style_action_button(self.w.run, default=True, green_fill=True)
		style_action_button(self.w.cancel)
		y += UI_BTN_H + s

		self.w.credit = Button(
			(m, y, W - m * 2 - UI_LANG_W - 8, UI_CREDIT_H),
			"",
			callback=self.open_credit_,
		)
		self.w.lang = Button(
			(W - m - UI_LANG_W, y, UI_LANG_W, UI_CREDIT_H),
			"",
			callback=self.toggle_lang_,
		)
		style_lang_chip(self.w.lang)

		self.apply_language()
		self.w.bind("close", self._on_close)
		Glyphs.addCallback(self._draw, DRAWFOREGROUND)
		Glyphs.addCallback(self._ui_update, UPDATEINTERFACE)
		Glyphs.redraw()
		self.w.open()
		style_window_title_bold(self.w)

	def apply_language(self):
		L = self.lang
		self.w.aboutTitle.set(t(L, "about_title"))
		style_heading(self.w.aboutTitle)
		self.w.aboutBody.set(t(L, "about_body"))
		style_body(self.w.aboutBody)
		self.w.instrTitle.set(t(L, "instructions"))
		style_heading(self.w.instrTitle)
		self.w.instrBody.set(t(L, "body"))
		style_body(self.w.instrBody)
		self.w.versoLabel.set(t(L, "verso"))
		style_heading(self.w.versoLabel)
		try:
			matrix = self.w.verso.getNSMatrix()
			matrix.cellAtRow_column_(0, 0).setTitle_(t(L, "verso_in"))
			matrix.cellAtRow_column_(1, 0).setTitle_(t(L, "verso_out"))
		except Exception:
			pass
		style_radio(self.w.verso)
		try:
			self.w.goniometer.setTitle(t(L, "goniometer"))
		except Exception:
			try:
				self.w.goniometer.getNSButton().setTitle_(t(L, "goniometer"))
			except Exception:
				pass
		style_checkbox(self.w.goniometer)
		self.w.run.setTitle(t(L, "apply"))
		self.w.cancel.setTitle(t(L, "cancel"))
		style_action_button(self.w.run, default=True, green_fill=True)
		style_action_button(self.w.cancel)
		style_credit_line(
			self.w.credit,
			t(L, "credit_prefix"),
			t(L, "credit_name"),
			t(L, "site"),
		)
		style_lang_chip(self.w.lang, t(L, "lang_button"))
		tint_panel_white(self.w)
		style_window_title_bold(self.w)

	def open_credit_(self, sender):
		open_site(t(self.lang, "site"))

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
		for fn, hook in (
			(self._draw, DRAWFOREGROUND),
			(self._ui_update, UPDATEINTERFACE),
		):
			try:
				Glyphs.removeCallback(fn, hook)
			except Exception:
				try:
					Glyphs.removeCallback(fn)
				except Exception:
					pass

	def _on_close(self, sender):
		self._remove_callbacks()
		try:
			Glyphs.redraw()
		except Exception:
			pass


if __name__ == "__main__":
	if HAS_VANILLA:
		GRvxCutterDialog()
	else:
		run_cutter("dentro")
