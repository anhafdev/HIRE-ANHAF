from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from ..exceptions import ProviderResponseInvalid


class Loose(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class EsploraStatus(Loose):
    confirmed: bool = False
    block_height: int | None = None
    block_time: int | None = None


class EsploraOutput(Loose):
    scriptpubkey_address: str | None = None
    value: int = 0


class EsploraInput(Loose):
    sequence: int | None = None


class EsploraTransaction(Loose):
    txid: str
    status: EsploraStatus = EsploraStatus()
    vin: list[EsploraInput] = []
    vout: list[EsploraOutput] = []


class BlockchainInfoOutput(Loose):
    addr: str | None = None
    value: int = 0


class BlockchainInfoInputPrev(Loose):
    sequence: int | None = None


class BlockchainInfoInput(Loose):
    sequence: int | None = None


class BlockchainInfoTransaction(Loose):
    hash: str
    block_height: int | None = None
    time: int | None = None
    inputs: list[BlockchainInfoInput] = []
    out: list[BlockchainInfoOutput] = []


class TronLogEntry(Loose):
    address: str | None = None
    topics: list[str] = []
    data: str | None = None


class TronReceipt(Loose):
    result: str | None = None


class TronTransactionInfo(Loose):
    id: str | None = None
    blockNumber: int | None = None
    blockTimeStamp: int | None = None
    receipt: TronReceipt = TronReceipt()
    log: list[TronLogEntry] = []


class TronRawData(Loose):
    timestamp: int | None = None


class TronReturn(Loose):
    contractRet: str | None = None


class TronContractValue(Loose):
    data: str | None = None
    contract_address: str | None = None


class TronContractParameter(Loose):
    value: TronContractValue = TronContractValue()


class TronContractCall(Loose):
    parameter: TronContractParameter = TronContractParameter()


class TronRawDataFull(Loose):
    timestamp: int | None = None
    contract: list[TronContractCall] = []


class TronTransaction(Loose):
    txID: str | None = None
    ret: list[TronReturn] = []
    raw_data: TronRawDataFull = TronRawDataFull()


class TronscanTransfer(Loose):
    to_address: str | None = None
    contract_address: str | None = None
    decimals: int = 6
    amount_str: str | None = None
    quant: str | None = None


class TronscanTransaction(Loose):
    hash: str | None = None
    block: int | None = None
    timestamp: int | None = None
    confirmed: bool = False
    contractRet: str | None = None
    trc20TransferInfo: list[TronscanTransfer] = []
    tokenTransferInfo: TronscanTransfer | None = None


class EvmTransaction(Loose):
    hash: str
    blockNumber: str | None = None
    to: str | None = None
    input: str | None = None
    value: str | None = None


class EvmBlock(Loose):
    timestamp: str | None = None


class EvmTraceAction(Loose):
    callType: str | None = None
    to: str | None = None
    value: str | None = None


class EvmTraceEntry(Loose):
    type: str | None = None
    action: EvmTraceAction = EvmTraceAction()


class EvmLogEntry(Loose):
    address: str | None = None
    topics: list[str] = []
    data: str | None = None


class EvmReceipt(Loose):
    transactionHash: str | None = None
    status: str | None = None
    blockNumber: str | None = None
    logs: list[EvmLogEntry] = []


def parse_or_fail(model: type[BaseModel], payload: Any, provider: str) -> Any:
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ProviderResponseInvalid(provider, error.errors()[0].get("msg", "schema mismatch"))
    except Exception as error:
        raise ProviderResponseInvalid(provider, str(error))
