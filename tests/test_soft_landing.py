#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Geometry tests for GV-Soft Landing (no Glyphs required)."""

from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "GV" / "GV-Soft Landing.py"


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

	spec = importlib.util.spec_from_file_location("grvx_soft_landing", SCRIPT)
	mod = importlib.util.module_from_spec(spec)
	spec.loader.exec_module(mod)
	return mod


class _Node:
	def __init__(self, type_, x, y, smooth=False):
		self.type = type_
		self.x = float(x)
		self.y = float(y)
		self.smooth = smooth


class _Path:
	def __init__(self, nodes):
		self.nodes = list(nodes)


class SoftLandingTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.m = _load_module()

	def _e_bottom_path(self):
		OFF, CURVE, LINE = self.m.OFFCURVE, self.m.CURVE, self.m.LINE
		return _Path(
			[
				_Node(LINE, 67, 470),
				_Node(OFF, 67, 182),
				_Node(OFF, 257, 0),
				_Node(CURVE, 565, 0, smooth=True),
				_Node(LINE, 839, 0),
				_Node(LINE, 839, 100),
			]
		)

	def test_auto_g1_on_line(self):
		path = self._e_bottom_path()
		path.nodes[2].y = 12.0
		geo, code = self.m._junction_from_indices(path, 3)
		self.assertEqual(code, "ok")
		self.assertEqual(geo["mode"], "cubic_then_line")
		self.assertAlmostEqual(geo["prop_P2"][1], geo["prop_J"][1], places=5)

	def test_auto_prefers_small_soft(self):
		path = self._e_bottom_path()
		geo, code = self.m._junction_from_indices(path, 3)
		self.assertEqual(code, "ok")
		self.assertLessEqual(geo["soft"], 0.28)

	def test_auto_can_slide_junction(self):
		# Steep arrival: high end curvature unless J slides / mild soft.
		path = self._e_bottom_path()
		path.nodes[1].x, path.nodes[1].y = 120, 40
		path.nodes[2].x, path.nodes[2].y = 400, 30
		geo, code = self.m._junction_from_indices(path, 3)
		self.assertEqual(code, "ok")
		# Either a slide or a soft adjust should improve landing.
		self.assertTrue(abs(geo["slide"]) > 0.5 or geo["soft"] > 0.0)

	def test_rejects_non_junction(self):
		path = self._e_bottom_path()
		geo, code = self.m._junction_from_indices(path, 4)
		self.assertIsNone(geo)
		self.assertEqual(code, "err_junction")

	def test_end_curvature_zero_when_collinear(self):
		k = self.m.end_curvature((0, 0), (10, 0), (20, 0))
		self.assertAlmostEqual(k, 0.0, places=9)


if __name__ == "__main__":
	unittest.main()
