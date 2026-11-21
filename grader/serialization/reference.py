import json


def encode_record(record: dict) -> str:
    return json.dumps(record, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)
