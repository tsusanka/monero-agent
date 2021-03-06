# Automatically generated by pb2py
# fmt: off
from .. import protobuf as p
if __debug__:
    try:
        from typing import List
    except ImportError:
        List = None  # type: ignore
from .TezosDelegationType import TezosDelegationType
from .TezosOperationCommon import TezosOperationCommon
from .TezosOriginationType import TezosOriginationType
from .TezosTransactionType import TezosTransactionType


class TezosSignTx(p.MessageType):
    MESSAGE_WIRE_TYPE = 152
    FIELDS = {
        1: ('address_n', p.UVarintType, p.FLAG_REPEATED),
        2: ('operation', TezosOperationCommon, 0),
        3: ('transaction', TezosTransactionType, 0),
        4: ('origination', TezosOriginationType, 0),
        5: ('delegation', TezosDelegationType, 0),
    }

    def __init__(
        self,
        address_n: List[int] = None,
        operation: TezosOperationCommon = None,
        transaction: TezosTransactionType = None,
        origination: TezosOriginationType = None,
        delegation: TezosDelegationType = None,
    ) -> None:
        self.address_n = address_n if address_n is not None else []
        self.operation = operation
        self.transaction = transaction
        self.origination = origination
        self.delegation = delegation
