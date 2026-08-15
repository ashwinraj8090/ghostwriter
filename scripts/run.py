#!/usr/bin/env python3
"""Entrypoint: python scripts/run.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ghostwriter.agent import run

if __name__ == "__main__":
    run()
