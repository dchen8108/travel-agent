from __future__ import annotations

import argparse


def positive_int_argument(flag_name: str):
    def _parse(value: str) -> int:
        parsed = int(value)
        if parsed < 1:
            raise argparse.ArgumentTypeError(f"{flag_name} must be >= 1")
        return parsed

    return _parse


def non_negative_int_argument(flag_name: str):
    def _parse(value: str) -> int:
        parsed = int(value)
        if parsed < 0:
            raise argparse.ArgumentTypeError(f"{flag_name} must be >= 0")
        return parsed

    return _parse


def non_negative_float_argument(flag_name: str):
    def _parse(value: str) -> float:
        parsed = float(value)
        if parsed < 0:
            raise argparse.ArgumentTypeError(f"{flag_name} must be >= 0")
        return parsed

    return _parse
