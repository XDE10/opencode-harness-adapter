import json


def encode_record(record: dict) -> str:
    return json.dumps(record)
