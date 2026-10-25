"""Token accounting.

Agents are stubs in the early phases, so no model reports real usage. We estimate the
size of what an agent would be sent as ceil(len(json)/4). Every trace record labels the
number as an estimate. Once agents call real models, record the response's
`usage_metadata` instead and set token_source accordingly.
"""
import json
import math

TOKEN_SOURCE = "estimate"


def estimate_tokens(obj) -> int:
    return math.ceil(len(json.dumps(obj, sort_keys=True, default=str)) / 4)
