#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for GV-Pill Cut span selection (no Glyphs required)."""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

OFFCURVE = "offcurve"
LINE = "line"
CURVE = "curve"
MAX_SPAN_NODES = 14


class _Node:
	def __init__(self, type_, x=0.0, y=0.0):
		self.type = type_
		self.x = float(x)
		self.y = float(y)


class _Path:
	def __init__(self, nodes):
		self.nodes = list(nodes)


def walk(i, j, n):
	out, k = [], (i + 1) % n
	while k != j and len(out) <= n:
		out.append(k)
		k = (k + 1) % n
	return out


def length(a):
	return math.hypot(a[0], a[1])


def V(a, b):
	return (b[0] - a[0], b[1] - a[1])


def xy(n):
	return (float(n.x), float(n.y))


def unit(a):
	L = length(a)
	return (1.0, 0.0) if L < 1e-12 else (a[0] / L, a[1] / L)


def dot(a, b):
	return a[0] * b[0] + a[1] * b[1]


def sub(a, b):
	return (a[0] - b[0], a[1] - b[1])


def choose_span_old(path, i, j):
	"""Pre-0.1.1 ranking: preferred any short span that contained offcurves."""
	n = len(path.nodes)
	fwd, bwd = walk(i, j, n), walk(j, i, n)

	def rank(span):
		n_off = sum(1 for k in span if path.nodes[k].type == OFFCURVE)
		short_notch = 0 if (n_off > 0 and len(span) <= MAX_SPAN_NODES) else 1
		return (short_notch, len(span))

	return (i, j, fwd) if rank(fwd) <= rank(bwd) else (j, i, bwd)


def choose_span_new(path, i, j, prefer_dir=None, origin=None):
	n = len(path.nodes)
	candidates = ((i, j, walk(i, j, n)), (j, i, walk(j, i, n)))

	def oncurve_count(span):
		return sum(1 for k in span if path.nodes[k].type != OFFCURVE)

	def geom_len(start, end, span):
		idxs = [start] + list(span) + [end]
		total = 0.0
		for a, b in zip(idxs, idxs[1:]):
			total += length(V(xy(path.nodes[a]), xy(path.nodes[b])))
		return total

	def midpoint(start, end, span):
		pts = [xy(path.nodes[start]), xy(path.nodes[end])]
		for k in span:
			if path.nodes[k].type != OFFCURVE:
				pts.append(xy(path.nodes[k]))
		m = float(len(pts))
		return (sum(p[0] for p in pts) / m, sum(p[1] for p in pts) / m)

	def rank(start, end, span):
		bias = 0.0
		if prefer_dir is not None and origin is not None:
			mid = midpoint(start, end, span)
			bias = -dot(sub(mid, origin), unit(prefer_dir))
		return (oncurve_count(span), geom_len(start, end, span), bias, len(span))

	return min(candidates, key=lambda c: rank(*c))


class ChooseSpanTests(unittest.TestCase):
	def test_offcurve_bias_no_longer_picks_long_stem_edge(self):
		# Short tip: two line nodes. Long way: many offcurves along the stem.
		nodes = [
			_Node(LINE, 0, 500),  # 0 A left
			_Node(LINE, 0, 900),
			_Node(LINE, 100, 900),
			_Node(LINE, 100, 500),  # 3 B right
			_Node(OFFCURVE, 100, 400),
			_Node(OFFCURVE, 100, 300),
			_Node(CURVE, 100, 200),
			_Node(OFFCURVE, 100, 100),
			_Node(OFFCURVE, 50, 50),
			_Node(CURVE, 0, 100),
			_Node(OFFCURVE, 0, 200),
			_Node(OFFCURVE, 0, 300),
			_Node(CURVE, 0, 400),
		]
		path = _Path(nodes)
		old = choose_span_old(path, 0, 3)
		new = choose_span_new(path, 0, 3)
		self.assertEqual(old[2], list(range(4, 13)), "old bug picks long offcurve span")
		self.assertEqual(new[0], 0)
		self.assertEqual(new[1], 3)
		self.assertEqual(new[2], [1, 2])

	def test_equal_tips_prefer_into_direction(self):
		nodes = [
			_Node(LINE, 0, 500),  # 0 L
			_Node(LINE, 0, 0),
			_Node(LINE, 100, 0),
			_Node(LINE, 100, 500),  # 3 R
			_Node(LINE, 100, 1000),
			_Node(LINE, 0, 1000),
		]
		path = _Path(nodes)
		# Into stem toward bottom tip (negative y from center).
		start, end, span = choose_span_new(
			path, 0, 3, prefer_dir=(0.0, -1.0), origin=(50.0, 500.0)
		)
		self.assertEqual(sorted([start, end]), [0, 3])
		self.assertEqual(span, [1, 2])


if __name__ == "__main__":
	# Keep this file self-contained; repo root on path unused on purpose.
	sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
	unittest.main()
