# -*- coding: utf-8 -*-
"""Shared helpers for GV Glyphs scripts (no MenuTitle — not a menu item)."""

from __future__ import annotations

import math
import webbrowser

try:
	from GlyphsApp import Glyphs, NodeSmoothColor
except Exception:
	Glyphs = None
	NodeSmoothColor = None

try:
	from AppKit import (
		NSFont,
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
	NSFont = NSColor = NSBezierPath = None
	NSMakeRect = NSFontAttributeName = NSForegroundColorAttributeName = None
	NSUnderlineStyleAttributeName = NSUnderlineStyleSingle = None
	NSWorkspace = NSURL = None
	NSString = NSMutableAttributedString = NSAttributedString = None

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


def lerp(a, b, t):
	return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


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


def clamp(v, lo, hi):
	return max(lo, min(hi, v))


# ── path helpers ───────────────────────────────────────────────────────────

def node_index(path, node):
	for i, n in enumerate(path.nodes):
		if n is node:
			return i
	for i, n in enumerate(path.nodes):
		if n.type == node.type and abs(n.x - node.x) < 1e-6 and abs(n.y - node.y) < 1e-6:
			return i
	return None


def oncurve_neighbor(nodes, idx, step, offcurve):
	"""Next on-curve index walking `step` (+1/-1), skipping `offcurve` nodes."""
	n = len(nodes)
	k = (idx + step) % n
	for _ in range(n):
		if nodes[k].type != offcurve:
			return k
		k = (k + step) % n
	return None


def walk_indices(i, j, n):
	out, k = [], (i + 1) % n
	while k != j and len(out) <= n:
		out.append(k)
		k = (k + 1) % n
	return out


# ── i18n / links ───────────────────────────────────────────────────────────

def t(ui, lang, key):
	return ui.get(lang, ui["it"]).get(key, ui["it"].get(key, key))


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


# ── drawing helpers ────────────────────────────────────────────────────────

def color_rgba(r, g, b, a):
	if NSColor is None:
		return None
	try:
		return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, a)
	except Exception:
		return None


def glyphs_green(alpha=1.0):
	color = NodeSmoothColor
	if color is None and Glyphs is not None:
		try:
			color = Glyphs.colorObjectToNSColor("GREEN")
		except Exception:
			color = None
	if color is None:
		color = color_rgba(0.2, 0.75, 0.25, 1.0)
	if color is None:
		return None
	try:
		return color.colorWithAlphaComponent_(float(alpha))
	except Exception:
		return color


def scale_from_info(info):
	if isinstance(info, dict):
		for key in ("Scale", "scale", "ScaleFactor"):
			if key in info:
				try:
					return float(info[key])
				except Exception:
					pass
	return 1.0


def mark_point(pt, scale, color, radius_px=3.5):
	if NSBezierPath is None or NSMakeRect is None or color is None:
		return
	rr = radius_px / max(scale, 0.01)
	color.set()
	NSBezierPath.bezierPathWithOvalInRect_(
		NSMakeRect(pt[0] - rr, pt[1] - rr, rr * 2, rr * 2)
	).fill()


def draw_label(text, pt, scale, color, offset=(0.0, 0.0), bold=False):
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


def stroke_line(a, b, scale, color, width_px=1.0, dashed=False):
	if NSBezierPath is None or color is None:
		return
	path = NSBezierPath.bezierPath()
	path.moveToPoint_(tuple(a))
	path.lineToPoint_(tuple(b))
	path.setLineWidth_(max(0.25, width_px / max(scale, 0.01)))
	if dashed:
		dash = [3.0 / max(scale, 0.01), 2.5 / max(scale, 0.01)]
		try:
			path.setLineDash_count_phase_(dash, 2, 0.0)
		except Exception:
			pass
	color.set()
	path.stroke()


# ── UI helpers ─────────────────────────────────────────────────────────────

def ui_font(bold=False):
	if not NSFont:
		return None
	if bold:
		return NSFont.boldSystemFontOfSize_(UI_FONT_SIZE)
	return NSFont.systemFontOfSize_(UI_FONT_SIZE)


def credit_font():
	return NSFont.systemFontOfSize_(CREDIT_FONT_SIZE) if NSFont else None


def text_black():
	if NSColor is None:
		return None
	try:
		return NSColor.blackColor()
	except Exception:
		return None


def measure_text(text, font):
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


def set_window_title(window, title):
	try:
		window.getNSWindow().setTitle_(title)
	except Exception:
		pass


def style_heading(box):
	try:
		field = box.getNSTextField()
		font = ui_font(bold=True)
		if font:
			field.setFont_(font)
		black = text_black()
		if black is not None:
			field.setTextColor_(black)
		field.setDrawsBackground_(False)
	except Exception:
		pass


def style_body(box):
	try:
		field = box.getNSTextField()
		font = ui_font(bold=False)
		if font:
			field.setFont_(font)
		black = text_black()
		if black is not None:
			field.setTextColor_(black)
		field.setSelectable_(False)
		field.setDrawsBackground_(False)
	except Exception:
		pass


def style_radio(radio):
	try:
		matrix = radio.getNSMatrix()
		font = ui_font(bold=False)
		black = text_black()
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
		font = ui_font(bold=False)
		black = text_black()
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


def style_credit_line(button, prefix, name):
	"""Plain prefix + green underlined name (opens site via button callback)."""
	full = prefix + name
	font = credit_font()
	base = text_black()
	link_color = glyphs_green(1.0) or base
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
			button.setPosSize((x, y, max(measure_text(full, font) + 12.0, 80.0), h))
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
		font = credit_font()
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
		font = ui_font(bold=False)
		black = text_black()
		title = ns.title() or ""
		if green_fill:
			soft = glyphs_green(0.25)
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


def remove_glyphs_callbacks(callbacks):
	"""callbacks: iterable of (fn, hook)."""
	if Glyphs is None:
		return
	for fn, hook in callbacks:
		try:
			Glyphs.removeCallback(fn, hook)
		except Exception:
			try:
				Glyphs.removeCallback(fn)
			except Exception:
				pass
