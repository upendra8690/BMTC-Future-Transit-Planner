"""Builds GTFS-Realtime feeds (protobuf bytes) for tests. Test use only: the app never makes up vehicles.

The encoding follows the GTFS-Realtime 2.0 specification, so the decoder in app/services/realtime.py is tested
against bytes laid out exactly as an operator's feed would be.
"""

from __future__ import annotations

import struct


def _varint(value: int) -> bytes:
    value &= (1 << 64) - 1
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _key(number: int, wire: int) -> bytes:
    return _varint(number << 3 | wire)


def _len(number: int, payload: bytes) -> bytes:
    return _key(number, 2) + _varint(len(payload)) + payload


def _uint(number: int, value: int) -> bytes:
    return _key(number, 0) + _varint(value)


def _f32(number: int, value: float) -> bytes:
    return _key(number, 5) + struct.pack("<f", value)


def _str(number: int, text: str) -> bytes:
    return _len(number, text.encode("utf-8"))


def _trip(trip_id: str, route_id: str, start_date: str, canceled: bool = False) -> bytes:
    out = b""
    if trip_id:
        out += _str(1, trip_id)
    if start_date:
        out += _str(3, start_date)
    if canceled:
        out += _uint(4, 3)
    if route_id:
        out += _str(5, route_id)
    return out


def vehicle(entity_id: str, *, vehicle_id: str, label: str, lat: float, lon: float, timestamp: int,
            trip_id: str = "", route_id: str = "", start_date: str = "", stop_sequence: int | None = None,
            stop_id: str = "", status: int | None = None, bearing: float | None = None,
            speed: float | None = None) -> bytes:
    position = _f32(1, lat) + _f32(2, lon)
    if bearing is not None:
        position += _f32(3, bearing)
    if speed is not None:
        position += _f32(5, speed)
    body = _len(1, _trip(trip_id, route_id, start_date)) + _len(2, position)
    if stop_sequence is not None:
        body += _uint(3, stop_sequence)
    if status is not None:
        body += _uint(4, status)
    body += _uint(5, timestamp)
    if stop_id:
        body += _str(7, stop_id)
    body += _len(8, _str(1, vehicle_id) + _str(2, label))
    return _str(1, entity_id) + _len(4, body)


def trip_update(entity_id: str, *, trip_id: str, route_id: str = "", start_date: str = "", vehicle_id: str = "",
                vehicle_label: str = "", timestamp: int | None = None, delay: int | None = None,
                stops: list[tuple] = (), canceled: bool = False) -> bytes:
    """stops: (sequence, stop_id, arrival_time or None, arrival_delay or None, skipped)."""
    body = _len(1, _trip(trip_id, route_id, start_date, canceled))
    for sequence, stop_id, arrival_time, arrival_delay, skipped in stops:
        event = b""
        if arrival_delay is not None:
            event += _uint(1, arrival_delay)
        if arrival_time is not None:
            event += _uint(2, arrival_time)
        update = _uint(1, sequence)
        if event:
            update += _len(2, event)
        if stop_id:
            update += _str(4, stop_id)
        if skipped:
            update += _uint(5, 1)
        body += _len(2, update)
    if vehicle_id or vehicle_label:
        body += _len(3, _str(1, vehicle_id) + _str(2, vehicle_label))
    if timestamp is not None:
        body += _uint(4, timestamp)
    if delay is not None:
        body += _uint(5, delay)
    return _str(1, entity_id) + _len(3, body)


def feed(timestamp: int, entities: list[bytes]) -> bytes:
    header = _str(1, "2.0") + _uint(2, 0) + _uint(3, timestamp)
    return _len(1, header) + b"".join(_len(2, entity) for entity in entities)
