"""ICEBERGSIM v2 REST server (ARCHITECTURE §3.12): a thin UI/API layer.

Routes parse requests, call icebergsim domain services, and serialize results. No
statistical formulas live here. The server binds to localhost only by default (SPEC §20).
"""
