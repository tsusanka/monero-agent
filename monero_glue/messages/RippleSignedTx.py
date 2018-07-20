# Automatically generated by pb2py
# fmt: off
from .. import protobuf as p


class RippleSignedTx(p.MessageType):
    MESSAGE_WIRE_TYPE = 403
    FIELDS = {
        1: ('signature', p.BytesType, 0),
        2: ('serialized_tx', p.BytesType, 0),
    }

    def __init__(
        self,
        signature: bytes = None,
        serialized_tx: bytes = None,
    ) -> None:
        self.signature = signature
        self.serialized_tx = serialized_tx