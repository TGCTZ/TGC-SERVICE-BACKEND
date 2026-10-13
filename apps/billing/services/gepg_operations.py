"""GePG cancellation and reconciliation workflows, kept auditable locally."""

import logging
import uuid
from datetime import date

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

from django.conf import settings
from django.db import transaction

from apps.core.exceptions import ServiceError

from ..gateways.gepg import (
    build_reconciliation_ack,
    escape_xml,
    generate_req_id,
    parse_payment_detail,
    sign_if_enabled,
)
from ..gepg_transport import finish_gepg_request, send_gepg_request
from ..models import (
    Bill,
    BillCancellation,
    GePGRequest,
    Reconciliation,
    ReconciliationTransaction,
)
from .payment import _apply_payment

logger = logging.getLogger(__name__)


def cancel_bill(bill: Bill, *, reason: str, user) -> BillCancellation:
    """Send the legacy cancellation XML and retain both request and response."""
    if bill.status in {"paid", "cancelled"}:
        raise ServiceError("Paid or cancelled bills cannot be cancelled.")
    req_id = generate_req_id()
    username = user.get_username()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg><billCanclReq><ReqId>{req_id}</ReqId><SpGrpCode>{settings.GEPG_SP_GRP_CODE}</SpGrpCode><SysCode>{settings.GEPG_SYS_CODE}</SysCode><BillTyp>{bill.bill_type}</BillTyp><GrpBillId>{escape_xml(bill.bill_number)}</GrpBillId><CanclGenBy>{escape_xml(username)}</CanclGenBy><CanclApprBy>{escape_xml(username)}</CanclApprBy><CanclReasn>{escape_xml(reason)}</CanclReasn></billCanclReq><signature>SignatureGoesHere</signature></Gepg>"""
    xml = sign_if_enabled(xml)
    record = BillCancellation.objects.create(
        bill=bill, req_id=req_id, reason=reason, request_xml=xml
    )
    try:
        outbound, response_xml = send_gepg_request(
            GePGRequest.Operation.CANCELLATION,
            settings.GEPG_BILL_CANCEL_URL,
            xml,
            cancellation=record,
        )
        if response_xml is None:
            raise ServiceError(
                outbound.last_error or "GePG cancellation could not be sent."
            )
        _apply_cancellation_response(outbound, response_xml)
        return record
    except Exception as exc:
        record.status_code, record.status_desc = "CONNECTION_ERROR", str(exc)[:255]
        record.save()
        raise ServiceError(f"GePG cancellation failed: {exc}") from exc


def request_reconciliation(trx_date: date, *, user=None) -> Reconciliation:
    """Create a reconciliation record then send the legacy sucSpPmtReq."""
    req_id = str(uuid.uuid4())
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg><sucSpPmtReq><ReqId>{req_id}</ReqId><SpGrpCode>{settings.GEPG_SP_GRP_CODE}</SpGrpCode><SysCode>{settings.GEPG_SYS_CODE}</SysCode><TrxDt>{trx_date:%Y-%m-%d}</TrxDt><Rsv1></Rsv1><Rsv2></Rsv2><Rsv3></Rsv3></sucSpPmtReq><signature>SignatureGoesHere</signature></Gepg>"""
    xml = sign_if_enabled(xml)
    recon = Reconciliation.objects.create(
        req_id=req_id, trx_dt=trx_date, request_xml=xml, created_by=user
    )
    try:
        outbound, response_xml = send_gepg_request(
            GePGRequest.Operation.RECONCILIATION,
            settings.GEPG_RECONCILIATION_URL,
            xml,
            reconciliation=recon,
        )
        if response_xml is None:
            raise ServiceError(
                outbound.last_error or "GePG reconciliation could not be sent."
            )
        _apply_reconciliation_ack(outbound, response_xml)
        return recon
    except Exception as exc:
        recon.status, recon.error_message = "failed", str(exc)
        recon.save()
        raise ServiceError(f"GePG reconciliation failed: {exc}") from exc


def _apply_cancellation_response(outbound, response_xml: str) -> None:
    """Apply a synchronous cancellation response to its audit row and bill."""
    record = outbound.cancellation
    root = fromstring(response_xml)
    result = root.find(".//billCanclRes")
    if result is None:
        finish_gepg_request(
            outbound, accepted=False, status_code="7242", response_xml=response_xml
        )
        raise ServiceError("GePG returned no cancellation response.")
    record.status_code = result.findtext("CanclStsCode", "")
    record.status_desc = result.findtext("CanclStsDesc", "")
    if record.status_code == "7283":
        record.bill.status = "cancelled"
        record.bill.status_code = record.status_code
        record.bill.status_desc = record.status_desc
        record.bill.save(
            update_fields=["status", "status_code", "status_desc", "updated_at"]
        )
    record.response_xml = response_xml
    record.save()
    finish_gepg_request(
        outbound,
        accepted=record.status_code in {"7101", "7283"},
        status_code=record.status_code,
        status_desc=record.status_desc,
        response_xml=response_xml,
    )


def _apply_reconciliation_ack(outbound, response_xml: str) -> None:
    """Apply a request acknowledgement to its reconciliation row."""
    recon = outbound.reconciliation
    root = fromstring(response_xml)
    ack = root.find(".//sucSpPmtReqAck")
    if ack is not None:
        recon.ack_id = ack.findtext("AckId", "")
        recon.ack_status_code = ack.findtext("AckStsCode", "")
        recon.ack_status_desc = ack.findtext("AckStsDesc", "")
        recon.status = "acknowledged" if recon.ack_status_code == "7101" else "failed"
        recon.acknowledgement_xml = response_xml
        recon.save()
        finish_gepg_request(
            outbound,
            accepted=recon.ack_status_code == "7101",
            status_code=recon.ack_status_code,
            status_desc=recon.ack_status_desc,
            response_xml=response_xml,
        )
        return
    finish_gepg_request(
        outbound, accepted=False, status_code="7242", response_xml=response_xml
    )
    raise ServiceError("GePG returned no reconciliation acknowledgement.")


@transaction.atomic
def handle_cancel_response(xml: str) -> str:
    """Persist asynchronous cancellation result and return a GePG XML ack."""
    try:
        root = fromstring(xml)
        response = root.find(".//billCanclRes")
        if response is None:
            raise ValueError("Missing billCanclRes")
        bill_id = response.findtext("GrpBillId", "")
        code = response.findtext("CanclStsCode", "7284")
        bill = Bill.objects.select_for_update().get(bill_number=bill_id)
        bill.status_code, bill.status_desc = code, response.findtext("CanclStsDesc", "")
        if code == "7283":
            bill.status = "cancelled"
        bill.save(update_fields=["status", "status_code", "status_desc", "updated_at"])
        req_id = response.findtext("ReqId", "")
        rec = BillCancellation.objects.filter(bill=bill, req_id=req_id).first()
        if rec is None:
            rec = (
                BillCancellation.objects.filter(bill=bill).order_by("-created_at").first()
            )
        if rec:
            rec.status_code, rec.status_desc, rec.response_xml = (
                code,
                bill.status_desc,
                xml,
            )
            rec.save()
        ack = f"""<Gepg><billCanclRes>
<ReqId>{escape_xml(response.findtext("ReqId", ""))}</ReqId>
<GrpBillId>{escape_xml(bill_id)}</GrpBillId><CanclStsCode>{code}</CanclStsCode>
<CanclStsDesc>{escape_xml(bill.status_desc)}</CanclStsDesc>
</billCanclRes><signature>SignatureGoesHere</signature></Gepg>"""
        return sign_if_enabled(ack)
    except Exception:
        ack = """<Gepg><billCanclRes><ReqId>ERROR</ReqId><GrpBillId>UNKNOWN</GrpBillId>
<CanclStsCode>7242</CanclStsCode>
<CanclStsDesc>Invalid or unknown cancellation</CanclStsDesc>
</billCanclRes><signature>SignatureGoesHere</signature></Gepg>"""
        return sign_if_enabled(ack)


@transaction.atomic
def handle_reconciliation_response(xml: str) -> str:
    """Store response header and transaction rows, then return legacy ack XML."""
    try:
        root = fromstring(xml)
        batch = root.find(".//BatchHdr")
        if batch is None:
            raise ValueError("Missing BatchHdr")
        req_id, res_id = batch.findtext("ReqId", ""), batch.findtext("ResId", "")
        recon = Reconciliation.objects.select_for_update().get(req_id=req_id)
        recon.res_id = res_id
        recon.payment_status_code = batch.findtext("PayStsCode", "")
        recon.payment_status_desc = batch.findtext("PayStsDesc", "")
        recon.response_xml = xml
        recon.status = "completed" if recon.payment_status_code == "7101" else "failed"
        recon.save()
        for detail in root.findall(".//PmtTrxDtl"):
            payment = parse_payment_detail(detail)
            trx_id = payment["trx_id"]
            ReconciliationTransaction.objects.update_or_create(
                reconciliation=recon,
                trx_id=trx_id,
                defaults={
                    "cust_cntr_num": detail.findtext("CustCntrNum", ""),
                    "grp_bill_id": detail.findtext("GrpBillId", ""),
                    "sp_code": detail.findtext("SpCode", ""),
                    "bill_id": detail.findtext("BillId", ""),
                    "bill_ctr_num": payment["bill_ctr_num"],
                    "psp_code": detail.findtext("PspCode", ""),
                    "psp_name": detail.findtext("PspName", ""),
                    "pay_ref_id": detail.findtext("PayRefId", ""),
                    "bill_amount": payment["bill_amount"],
                    "paid_amount": payment["paid_amount"],
                    "bill_pay_opt": payment["bill_pay_opt"],
                    "currency": payment["currency"],
                    "coll_acc_num": payment["coll_acc_num"],
                    "trx_dt_tm": detail.findtext("TrxDtTm", ""),
                    "usd_pay_chnl": payment["usd_pay_chnl"],
                    "trd_pty_trx_id": detail.findtext("TrdPtyTrxId", ""),
                    "qt_ref_id": detail.findtext("QtRefId", ""),
                    "pyr_cell_num": payment["pyr_cell_num"],
                    "pyr_email": detail.findtext("PyrEmail", ""),
                    "pyr_name": detail.findtext("PyrName", ""),
                    "rsv1": detail.findtext("Rsv1", ""),
                    "rsv2": detail.findtext("Rsv2", ""),
                    "rsv3": detail.findtext("Rsv3", ""),
                    "raw_xml": __import__(
                        "xml.etree.ElementTree", fromlist=["tostring"]
                    ).tostring(detail, encoding="unicode"),
                },
            )
            if recon.payment_status_code == "7101":
                _apply_payment(
                    {
                        "req_id": req_id,
                        "grp_bill_id": batch.findtext("GrpBillId", ""),
                        "sp_grp_code": batch.findtext("SpGrpCode", ""),
                        "entry_count": None,
                    },
                    payment,
                    xml,
                )
        ack = build_reconciliation_ack(res_id, "7101")
        recon.response_ack_xml = ack
        recon.save(update_fields=["response_ack_xml", "updated_at"])
        return ack
    except (ValueError, ParseError, DefusedXmlException):
        return build_reconciliation_ack("UNKNOWN", "7242")
    except Exception:
        logger.exception("Could not apply GePG reconciliation response")
        return build_reconciliation_ack("UNKNOWN", "7321")
