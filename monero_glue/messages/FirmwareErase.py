# Automatically generated by pb2py
# fmt: off
from .. import protobuf as p


class FirmwareErase(p.MessageType):
    MESSAGE_WIRE_TYPE = 6
    FIELDS = {
        1: ('length', p.UVarintType, 0),
    }

    def __init__(
        self,
        length: int = None,
    ) -> None:
        self.length = length
