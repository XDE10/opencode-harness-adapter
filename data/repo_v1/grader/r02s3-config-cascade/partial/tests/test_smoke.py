from r02s3pkg import ConfigCascade, ConfigSchema, FieldSpec


def test_basic_layer_override():
    cascade = ConfigCascade()
    cascade.add_layer(
        """
        [server]
        host = "127.0.0.1"
        port = 8000
        """
    )
    cascade.add_layer(
        """
        [server]
        port = 9000
        """
    )
    result = cascade.resolve()
    assert result["server"]["host"] == "127.0.0.1"
    assert result["server"]["port"] == 9000


def test_basic_schema_validation():
    schema = ConfigSchema()
    schema.add_field("server", "host", FieldSpec(str, required=True))
    schema.add_field("server", "port", FieldSpec(int, required=True))

    cascade = ConfigCascade(schema=schema)
    cascade.add_layer(
        """
        [server]
        host = "localhost"
        port = 8080
        """
    )
    resolved = cascade.resolve()
    assert resolved["server"] == {"host": "localhost", "port": 8080}
