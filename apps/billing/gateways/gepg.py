"""GePG gateway: build/submit bill XML and parse payment notifications.

Isolates the GePG wire format (XML, HTTP, status codes) from the service layer.
"""

import logging
import re
import secrets
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

import requests
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError
from defusedxml.ElementTree import fromstring as parse_xml

from django.conf import settings
from django.utils import timezone

from .signing import sign_if_enabled

logger = logging.getLogger(__name__)

ACK_SUCCESS = {"7101", "7241"}


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def format_amount(value) -> str:
    """Format a money value to a 2-decimal string."""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"


def escape_xml(text) -> str:
    """Escape XML special characters in a value."""
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def normalize_msisdn(phone) -> str:
    """Normalize a phone number to Tanzania MSISDN format (255XXXXXXXXX)."""
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("255"):
        normalized = digits
    elif digits.startswith("0") and len(digits) >= 10:
        normalized = f"255{digits[1:]}"
    elif len(digits) == 9:
        normalized = f"255{digits}"
    else:
        normalized = digits
    return normalized[:12]


def generate_req_id() -> str:
    """Unique request id: SP group code + timestamp."""
    return f"{settings.GEPG_SP_GRP_CODE}{timezone.now():%Y%m%d%H%M%S}"


def parse_datetime(value: str) -> datetime:
    """Parse a GePG datetime (tolerating '.'/':' fractional seconds) as aware."""
    if not value:
        raise ValueError("Missing datetime value")
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        normalised = re.sub(r":(\d{1,6})$", r".\1", value)
        dt = datetime.strptime(normalised, "%Y-%m-%dT%H:%M:%S.%f")
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


# ------------------------------------------------------------
# Outbound: bill submission
# ------------------------------------------------------------
def build_bill_xml(bill, customer, username: str = "System") -> str:
    """Build the (unsigned) billSubReq XML for a bill and its customer."""
    amount = format_amount(bill.total_amount)
    gen_at = bill.issued_at or timezone.now()
    expiry = bill.expiry_at or gen_at
    phone = normalize_msisdn(customer.phone)
    cust_id = re.sub(r"\D", "", str(customer.id)).zfill(8)[:20]

    items_xml = ""
    for item in bill.items.all():
        items_xml += f"""
          <BillItem>
            <RefBillId>{bill.bill_number}</RefBillId>
            <SubSpCode>{settings.GEPG_SUB_SP_CODE}</SubSpCode>
            <GfsCode>{settings.GEPG_GFS_CODE}</GfsCode>
            <BillItemRef>{escape_xml(item.item_ref or f"ITEM-{item.id}")}</BillItemRef>
            <UseItemRefOnPay>N</UseItemRefOnPay>
            <BillItemAmt>{format_amount(item.amount)}</BillItemAmt>
            <BillItemEqvAmt>{format_amount(item.amount)}</BillItemEqvAmt>
            <CollSp>{settings.GEPG_SP_GRP_CODE}</CollSp>
          </BillItem>"""

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <billSubReq>
    <BillHdr>
      <ReqId>{generate_req_id()}</ReqId>
      <SpGrpCode>{settings.GEPG_SP_GRP_CODE}</SpGrpCode>
      <SysCode>{settings.GEPG_SYS_CODE}</SysCode>
      <BillTyp>{bill.bill_type}</BillTyp>
      <PayTyp>{bill.pay_type}</PayTyp>
      <GrpBillId>{bill.bill_number}</GrpBillId>
    </BillHdr>
    <BillDtls>
      <BillDtl>
        <BillId>{bill.bill_number}</BillId>
        <SpCode>{settings.GEPG_SP_CODE}</SpCode>
        <CollCentCode>{settings.GEPG_COLL_CENT_CODE}</CollCentCode>
        <BillDesc>{escape_xml(f"TGC bill {bill.bill_number}")}</BillDesc>
        <CustTin>000000000</CustTin>
        <CustId>{cust_id}</CustId>
        <CustIdTyp>5</CustIdTyp>
        <CustAccnt>TGCACCNT</CustAccnt>
        <CustName>{escape_xml(customer.full_name)}</CustName>
        <CustCellNum>{phone}</CustCellNum>
        <CustEmail>{escape_xml(customer.email)}</CustEmail>
        <BillGenDt>{gen_at:%Y-%m-%dT%H:%M:%S}</BillGenDt>
        <BillExprDt>{expiry:%Y-%m-%dT%H:%M:%S}</BillExprDt>
        <BillGenBy>{escape_xml(username)}</BillGenBy>
        <BillApprBy>{escape_xml(username)}</BillApprBy>
        <BillAmt>{amount}</BillAmt>
        <BillEqvAmt>{amount}</BillEqvAmt>
        <MinPayAmt>{amount}</MinPayAmt>
        <Ccy>{bill.currency}</Ccy>
        <ExchRate>1.00</ExchRate>
        <BillPayOpt>3</BillPayOpt>
        <PayPlan>1</PayPlan>
        <PayLimTyp>1</PayLimTyp>
        <PayLimAmt>0.00</PayLimAmt>
        <CollPsp></CollPsp>
        <BillItems>{items_xml}
        </BillItems>
      </BillDtl>
    </BillDtls>
  </billSubReq>
  <signature>SignatureGoesHere</signature>
</Gepg>"""


def submit_bill(bill, customer, username: str = "System") -> dict:
    """Sign and POST a bill to GePG; return the parsed outcome.

    Result keys: success, control_number, status_code, status_desc, is_sync,
    raw_response.
    """
    if getattr(settings, "GEPG_SIMULATE", False):
        # Development: skip the network and return an instant control number.
        control_number = f"99{secrets.randbelow(10**10):010d}"
        return _result(True, control_number, "7101", "Simulated (dev)", True, None)

    xml_payload = sign_if_enabled(build_bill_xml(bill, customer, username))
    try:
        response = requests.post(
            settings.GEPG_BILL_CREATE_URL,
            data=xml_payload.encode("utf-8"),
            headers={
                "Content-Type": "application/xml",
                "Gepg-Com": "default.sp.in",
                "Gepg-Code": settings.GEPG_SP_CODE,
            },
            timeout=30,
        )
        response.raise_for_status()
        raw = response.text
    except requests.exceptions.RequestException as exc:
        logger.error("GePG bill submission failed: %s", exc)
        return _result(False, None, "CONNECTION_ERROR", str(exc), False, None)

    return _parse_bill_response(raw)


def _parse_bill_response(raw: str) -> dict:
    """Parse a billSubRes (sync control number) or billSubReqAck (async) response."""
    try:
        root = parse_xml(raw)
    except (ParseError, DefusedXmlException) as exc:
        logger.error("GePG response parse error: %s", exc)
        return _result(False, None, "XML_PARSE_ERROR", str(exc), False, raw)

    bill_dtl = root.find("billSubRes//BillDtl")
    if bill_dtl is not None:
        control_number = bill_dtl.findtext("BillCntrNum")
        return _result(
            bool(control_number),
            control_number,
            bill_dtl.findtext("BillStsCode", ""),
            bill_dtl.findtext("BillStsDesc", ""),
            True,
            raw,
        )

    ack = root.find("billSubReqAck")
    if ack is not None:
        code = ack.findtext("AckStsCode", "")
        desc = ack.findtext("AckStsDesc", "")
        if code in ACK_SUCCESS:
            # Acknowledged; control number will arrive via callback.
            return _result(
                True, "PENDING", code, desc or "Awaiting control number", False, raw
            )
        return _result(False, None, code, desc or "Rejected by GePG", False, raw)

    return _result(
        False, None, "UNKNOWN_RESPONSE", "Unrecognised GePG response", False, raw
    )


def _result(success, control_number, status_code, status_desc, is_sync, raw) -> dict:
    return {
        "success": success,
        "control_number": control_number,
        "status_code": status_code,
        "status_desc": status_desc,
        "is_sync": is_sync,
        "raw_response": raw,
    }


# ------------------------------------------------------------
# Inbound: payment notification
# ------------------------------------------------------------
def parse_payment_notification(xml_content: str) -> tuple[dict, list[dict]]:
    """Parse a pmtSpNtfReq into (header, [transactions]). Raises ValueError if invalid."""
    root = parse_xml(xml_content)
    pmt_hdr = root.find(".//PmtHdr")
    details = root.findall(".//PmtTrxDtl")
    if pmt_hdr is None or not details:
        raise ValueError("Missing payment header or details")

    header = {
        "req_id": pmt_hdr.findtext("ReqId", ""),
        "grp_bill_id": pmt_hdr.findtext("GrpBillId", ""),
        "sp_grp_code": pmt_hdr.findtext("SpGrpCode", ""),
        "cust_cntr_num": pmt_hdr.findtext("CustCntrNum", ""),
        "entry_count": int(pmt_hdr.findtext("EntryCnt", "1")),
    }
    transactions = [
        {
            "sp_code": d.findtext("SpCode", ""),
            "gepg_bill_id": d.findtext("BillId", ""),
            "bill_ctr_num": d.findtext("BillCtrNum", ""),
            "psp_code": d.findtext("PspCode", ""),
            "psp_name": d.findtext("PspName", ""),
            "trx_id": d.findtext("TrxId", ""),
            "pay_ref_id": d.findtext("PayRefId", ""),
            "bill_amount": Decimal(d.findtext("BillAmt", "0")),
            "paid_amount": Decimal(d.findtext("PaidAmt", "0")),
            "bill_pay_opt": d.findtext("BillPayOpt", ""),
            "currency": d.findtext("Ccy", ""),
            "coll_acc_num": d.findtext("CollAccNum", ""),
            "trx_dt_tm": parse_datetime(d.findtext("TrxDtTm", "")),
            "usd_pay_chnl": d.findtext("UsdPayChnl", ""),
            "pyr_cell_num": d.findtext("PyrCellNum", ""),
            "pyr_email": d.findtext("PyrEmail", ""),
            "pyr_name": d.findtext("PyrName", ""),
        }
        for d in details
    ]
    return header, transactions


def build_payment_ack(req_id: str, status_code: str = "7101") -> str:
    """Build a signed pmtSpNtfReqAck response for GePG."""
    ack = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <pmtSpNtfReqAck>
        <AckId>SP{timezone.now():%Y%m%d%H%M%S}</AckId>
        <ReqId>{req_id}</ReqId>
        <AckStsCode>{status_code}</AckStsCode>
    </pmtSpNtfReqAck>
    <signature>SignatureGoesHere</signature>
</Gepg>"""
    return sign_if_enabled(ack)


# ------------------------------------------------------------
# Inbound: async control-number callback (billSubRes)
# ------------------------------------------------------------
def parse_bill_response(xml_content: str) -> dict:
    """Parse an async billSubRes callback into its control-number fields."""
    root = parse_xml(xml_content)
    hdr = root.find("billSubRes/BillHdr")
    dtl = root.find("billSubRes//BillDtl")
    if dtl is None:
        raise ValueError("Missing BillDtl in billSubRes")
    return {
        "req_id": hdr.findtext("ReqId", "") if hdr is not None else "",
        "res_id": hdr.findtext("ResId", "") if hdr is not None else "",
        "bill_id": dtl.findtext("BillId", ""),
        "control_number": dtl.findtext("BillCntrNum", ""),
        "status_code": dtl.findtext("BillStsCode", ""),
        "status_desc": dtl.findtext("BillStsDesc", ""),
    }


def build_bill_response_ack(res_id: str, status_code: str = "7101") -> str:
    """Build a signed billSubResAck response for GePG."""
    ack = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <billSubResAck>
        <ResId>{res_id}</ResId>
        <AckStsCode>{status_code}</AckStsCode>
    </billSubResAck>
    <signature>SignatureGoesHere</signature>
</Gepg>"""
    return sign_if_enabled(ack)
