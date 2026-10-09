"""GePG cancellation and reconciliation workflows, kept auditable locally."""

import uuid
from datetime import date
from decimal import Decimal

import requests
from defusedxml.ElementTree import fromstring

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError

from ..gateways.gepg import escape_xml, generate_req_id, sign_if_enabled
from ..models import (
    Bill,
    BillCancellation,
    Reconciliation,
    ReconciliationTransaction,
)


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
        response = requests.post(
            settings.GEPG_BILL_CANCEL_URL,
            data=xml.encode(),
            headers={
                "Content-Type": "application/xml",
                "Gepg-Com": "changebill.sp.in",
                "Gepg-Code": settings.GEPG_SP_CODE,
            },
            timeout=30,
        )
        response.raise_for_status()
        root = fromstring(response.text)
        result = root.find(".//billCanclRes")
        if result is not None:
            record.status_code = result.findtext("CanclStsCode", "")
            record.status_desc = result.findtext("CanclStsDesc", "")
            if record.status_code == "7283":
                bill.status = "cancelled"
                bill.status_code, bill.status_desc = (
                    record.status_code,
                    record.status_desc,
                )
                bill.save(
                    update_fields=["status", "status_code", "status_desc", "updated_at"]
                )
        record.response_xml = response.text
        record.save()
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
        response = requests.post(
            settings.GEPG_RECONCILIATION_URL,
            data=xml.encode(),
            headers={
                "Content-Type": "application/xml",
                "Gepg-Com": "default.sp.in",
                "Gepg-Code": settings.GEPG_SP_CODE,
            },
            timeout=30,
        )
        response.raise_for_status()
        root = fromstring(response.text)
        ack = root.find(".//sucSpPmtReqAck")
        if ack is not None:
            recon.ack_id = ack.findtext("AckId", "")
            recon.ack_status_code = ack.findtext("AckStsCode", "")
            recon.ack_status_desc = ack.findtext("AckStsDesc", "")
            recon.status = "acknowledged" if recon.ack_status_code == "7101" else "failed"
            recon.acknowledgement_xml = response.text
            recon.save()
        return recon
    except Exception as exc:
        recon.status, recon.error_message = "failed", str(exc)
        recon.save()
        raise ServiceError(f"GePG reconciliation failed: {exc}") from exc


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
<CanclStsCode>7284</CanclStsCode>
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
            trx_id = detail.findtext("TrxId", "")
            ReconciliationTransaction.objects.update_or_create(
                reconciliation=recon,
                trx_id=trx_id,
                defaults={
                    "cust_cntr_num": detail.findtext("CustCntrNum", ""),
                    "grp_bill_id": detail.findtext("GrpBillId", ""),
                    "sp_code": detail.findtext("SpCode", ""),
                    "bill_id": detail.findtext("BillId", ""),
                    "bill_ctr_num": detail.findtext("BillCtrNum", ""),
                    "psp_code": detail.findtext("PspCode", ""),
                    "psp_name": detail.findtext("PspName", ""),
                    "pay_ref_id": detail.findtext("PayRefId", ""),
                    "bill_amount": Decimal(detail.findtext("BillAmt", "0") or "0"),
                    "paid_amount": Decimal(detail.findtext("PaidAmt", "0") or "0"),
                    "bill_pay_opt": detail.findtext("BillPayOpt", ""),
                    "currency": detail.findtext("Ccy", ""),
                    "coll_acc_num": detail.findtext("CollAccNum", ""),
                    "trx_dt_tm": detail.findtext("TrxDtTm", ""),
                    "usd_pay_chnl": detail.findtext("UsdPayChnl", ""),
                    "trd_pty_trx_id": detail.findtext("TrdPtyTrxId", ""),
                    "qt_ref_id": detail.findtext("QtRefId", ""),
                    "pyr_cell_num": detail.findtext("PyrCellNum", ""),
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
        ack_id = f"SP{timezone.now():%Y%m%d%H%M%S}"
        ack = sign_if_enabled(
            f"<Gepg><sucSpPmtResAck><AckId>{ack_id}</AckId><ResId>{escape_xml(res_id)}</ResId><AckStsCode>7101</AckStsCode></sucSpPmtResAck><signature>SignatureGoesHere</signature></Gepg>"
        )
        recon.response_ack_xml = ack
        recon.save(update_fields=["response_ack_xml", "updated_at"])
        return ack
    except Exception:
        return sign_if_enabled(
            "<Gepg><sucSpPmtResAck><AckId>ERROR</AckId><ResId>UNKNOWN</ResId><AckStsCode>7102</AckStsCode></sucSpPmtResAck><signature>SignatureGoesHere</signature></Gepg>"
        )
