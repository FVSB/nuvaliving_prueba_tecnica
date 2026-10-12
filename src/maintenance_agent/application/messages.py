"""Application message contracts independent from terminal I/O."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkOrderMessage:
    """The common immutable protocol payload addressed to a work order and role."""

    work_order_id: str
    role: str
    body: str


@dataclass(frozen=True, slots=True)
class InboundMessage(WorkOrderMessage):
    """A validated participant message received from standard input."""


@dataclass(frozen=True, slots=True)
class OutboundMessage(WorkOrderMessage):
    """A message ready to be framed by the CLI transport."""


@dataclass(frozen=True, slots=True)
class TerminalFrame:
    """Exactly two terminal protocol lines for one completed work order."""

    work_order_id: str
    result: str
    detail: str
