#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for GV-Pill Cut span selection (no Glyphs required)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "GV" / "GV-Pill Cut.py"


def _load_module():
	sys.modules.setdefault("GlyphsApp", type(sys)("GlyphsApp"))
	ga = sys.modules["GlyphsApp"]
	for name, val in {
		"Glyphs": None,
		"GSNode": object,
		"CURVE": "curve",
		"LINE": "line",
		"OFFCURVE": "offcurve",
		"Message": lambda *a, **k: None,
		"DRAWFOREGROUND": "DrawForeground",
		"UPDATEINTERFACE": "GSUpdateInterface",
		"NodeSmoothColor": None,
	}.items():
		setattr(ga, name, val)

	sys.modules.setdefault("vanilla", type(sys)("vanilla"))
	sys.modules.setdefault("AppKit", type(sys)("AppKit"))
	sys.modules.setdefault("Foundation", type(sys)("Foundation"))

	# Ensure sibling gv_common is importable when the script loads.
	gv_dir = str(SCRIPT.parent)
	if gv_dir not in sys.path:
		sys.path.insert(0, gv_dir)

	spec = importlib.util.spec_from_file_location("gv_pill_cut", SCRIPT)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


class _Node:
	def __init__(self, type_, x=0.0, y=0.0):
		self.type = type_
		self.x = float(x)
		self.y = float(y)


class _Path:
	def __init__(self, nodes):
		self.nodes = list(nodes)


class ChooseSpanTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.m = _load_module()
		cls.OFF = cls.m.OFFCURVE
		cls.LINE = cls.m.LINE
		cls.CURVE = cls.m.CURVE

	def test_offcurve_bias_no_longer_picks_long_stem_edge(self):
		# Short tip: two line nodes. Long way: many offcurves along the stem.
		nodes = [
			_Node(self.LINE, 0, 500),  # 0 A left
			_Node(self.LINE, 0, 900),
			_Node(self.LINE, 100, 900),
			_Node(self.LINE, 100, 500),  # 3 B right
			_Node(self.OFF, 100, 400),
			_Node(self.OFF, 100, 300),
			_Node(self.CURVE, 100, 200),
			_Node(self.OFF, 100, 100),
			_Node(self.OFF, 50, 50),
			_Node(self.CURVE, 0, 100),
			_Node(self.OFF, 0, 200),
			_Node(self.OFF, 0, 300),
			_Node(self.CURVE, 0, 400),
		]
		path = _Path(nodes)
		start, end, span = self.m.choose_span(path, 0, 3)
		self.assertEqual(start, 0)
		self.assertEqual(end, 3)
		self.assertEqual(span, [1, 2])

	def test_equal_tips_prefer_into_direction(self):
		nodes = [
			_Node(self.LINE, 0, 500),  # 0 L
			_Node(self.LINE, 0, 0),
			_Node(self.LINE, 100, 0),
			_Node(self.LINE, 100, 500),  # 3 R
			_Node(self.LINE, 100, 1000),
			_Node(self.LINE, 0, 1000),
		]
		path = _Path(nodes)
		# Into stem toward bottom tip (negative y from center).
		start, end, span = self.m.choose_span(
			path, 0, 3, prefer_dir=(0.0, -1.0), origin=(50.0, 500.0)
		)
		self.assertEqual(sorted([start, end]), [0, 3])
		self.assertEqual(span, [1, 2])


if __name__ == "__main__":
	unittest.main()
