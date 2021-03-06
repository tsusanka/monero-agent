# Automatically generated by pb2py
# fmt: off
from .. import protobuf as p
from .MoneroAccountPublicAddress import MoneroAccountPublicAddress


class MoneroTransactionDestinationEntry(p.MessageType):
    FIELDS = {
        1: ('amount', p.UVarintType, 0),
        2: ('addr', MoneroAccountPublicAddress, 0),
        3: ('is_subaddress', p.BoolType, 0),
    }

    def __init__(
        self,
        amount: int = None,
        addr: MoneroAccountPublicAddress = None,
        is_subaddress: bool = None,
    ) -> None:
        self.amount = amount
        self.addr = addr
        self.is_subaddress = is_subaddress
