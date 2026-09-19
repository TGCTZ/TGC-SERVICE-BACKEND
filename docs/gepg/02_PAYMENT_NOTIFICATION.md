# GEPG Integration - Payment Notification

## Overview

Payment notification is the process where GEPG sends payment confirmation to the TGC Mifumo system after a customer makes a payment. This is an **inbound API** where GEPG calls our system.

---

## Architecture

### Flow Diagram

```
Customer Payment → GEPG → Payment Notification (XML) → TGC API Endpoint
                                                              ↓
                                                    Parse & Validate XML
                                                              ↓
                                                    Find Associated Bill
                                                              ↓
                                                    Create Payment Record
                                                              ↓
                                                    Update Bill Status
                                                              ↓
                                                    Return Acknowledgment (XML)
```

---

## Configuration

### API Endpoint

**URL**: `POST /gepg/payments/notification/`

**Authentication**: CSRF Exempt (external system)

**Content-Type**: `application/xml`

**Response**: XML acknowledgment

### URL Configuration

```python
from django.urls import path
from .views.payment_api import receive_payment_notification

urlpatterns = [
    path(
        "api/payments/notification/",
        receive_payment_notification,
        name="payment_notification",
    ),
]
```

---

## Implementation

### View Handler

```python
@csrf_exempt
@require_http_methods(["POST"])
def receive_payment_notification(request):
    """
    Receive payment notification from GePG and return acknowledgment

    Endpoint: /api/payments/notification/
    Method: POST
    Content-Type: application/xml

    Returns:
    - XML acknowledgment response
    - Status 200 on EVERY path, including failure
    """
    try:
        # Get raw XML content
        xml_content = request.body.decode("utf-8")

        # Process notification and get acknowledgment
        ack_xml = process_payment_notification(xml_content)

        # Return XML response
        return HttpResponse(content=ack_xml, content_type="application/xml", status=200)

    except Exception as e:
        # Return error response
        error_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <pmtSpNtfReqAck>
        <AckId>ERROR</AckId>
        <ReqId>ERROR</ReqId>
        <AckStsCode>7102</AckStsCode>
    </pmtSpNtfReqAck>
    <signature>SignatureGoesHere</signature>
</Gepg>"""
        return HttpResponse(content=error_xml, content_type="application/xml", status=200)
```

> **The status code is the important part of this endpoint.**
>
> It answers **HTTP 200 on every path**, including a parse failure, where the
> acknowledgement carries code **`7102`**. A 4xx would make GePG treat the
> delivery as failed and send it again — and a payload we could not parse the
> first time will not parse the second. The failure is reported *inside* the
> acknowledgement, which is where GePG looks.
>
> Code `7243` appears in the code table further down but is never sent.

### Service Function

```python
def process_payment_notification(xml_content: str) -> str:
    """
    Process payment notification XML from GePG and store payment record.
    Returns acknowledgment XML.
    """
    try:
        # Parse the XML
        root = ET.fromstring(xml_content)
        pmt_hdr = root.find(".//PmtHdr")
        payment_details = root.findall(".//PmtTrxDtl")

        if not pmt_hdr or not payment_details:
            raise ValueError("Missing payment header or details")

        req_id = pmt_hdr.findtext("ReqId", "")

        for pmt_dtl in payment_details:
            # Extract payment details
            bill_id = pmt_dtl.findtext("BillId", "")
            trx_id = pmt_dtl.findtext("TrxId", "")
            pay_ref_id = pmt_dtl.findtext("PayRefId", "")
            paid_amount = Decimal(pmt_dtl.findtext("PaidAmt", "0"))

            if not bill_id:
                raise ValueError("BillId missing in payment detail")

            # Find the associated bill
            try:
                bill = Bill.objects.get(bill_id=bill_id)
            except Bill.DoesNotExist:
                raise ValueError(f"Bill {bill_id} not found")

            # Create or update payment record
            defaults = {
                "bill": bill,
                "bill_id": bill_id,
                "pay_ref_id": pay_ref_id,
                "paid_amount": paid_amount,
                "bill_amount": bill.bill_amount,
                "currency": bill.currency,
                "psp_name": pmt_dtl.findtext("PspName", ""),
                "psp_code": pmt_dtl.findtext("PspCode", ""),
                "coll_acc_num": pmt_dtl.findtext("CollAccNum", ""),
                "usd_pay_chnl": pmt_dtl.findtext("UsdPayChnl", ""),
                "pyr_cell_num": pmt_dtl.findtext("PyrCellNum", ""),
                "pyr_name": pmt_dtl.findtext("PyrName", ""),
                "pyr_email": pmt_dtl.findtext("PyrEmail", ""),
                "trx_dt_tm": _parse_gepg_datetime(pmt_dtl.findtext("TrxDtTm", "")),
                "is_processed": True,
                "raw_request": xml_content,
                # Add missing fields from PmtHdr
                "req_id": req_id,
                "grp_bill_id": pmt_hdr.findtext("GrpBillId", ""),
                "sp_grp_code": pmt_hdr.findtext("SpGrpCode", ""),
                "cust_cntr_num": pmt_hdr.findtext("CustCntrNum", ""),
                "entry_count": int(pmt_hdr.findtext("EntryCnt", "1")),
                # Add missing fields from PmtTrxDtl
                "sp_code": pmt_dtl.findtext("SpCode", ""),
                "bill_ctr_num": pmt_dtl.findtext("BillCtrNum", ""),
                "bill_pay_opt": pmt_dtl.findtext("BillPayOpt", ""),
            }

            payment, created = Payment.objects.get_or_create(
                trx_id=trx_id, defaults=defaults
            )

            if not created:
                # Update the existing record with the latest data
                for field, value in defaults.items():
                    setattr(payment, field, value)
                payment.save()

            if created:
                # Update bill status to paid
                bill.status_code = "102"  # Paid
                bill.status_desc = "Payment Received"
                bill.save(update_fields=["status_code", "status_desc"])

        # Generate acknowledgment XML
        ack_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <pmtSpNtfReqAck>
        <AckId>SP{datetime.now().strftime("%Y%m%d%H%M%S")}</AckId>
        <ReqId>{req_id}</ReqId>
        <AckStsCode>7101</AckStsCode>
    </pmtSpNtfReqAck>
    <signature>SignatureGoesHere</signature>
</Gepg>""".strip()

        # Sign if digital signatures enabled
        ack_xml = _sign_xml_if_enabled(ack_xml)

        return ack_xml

    except Exception as e:
        # Return error acknowledgment
        error_ack = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <pmtSpNtfReqAck>
        <AckId>SP{datetime.now().strftime("%Y%m%d%H%M%S")}</AckId>
        <ReqId>ERROR</ReqId>
        <AckStsCode>7102</AckStsCode>
    </pmtSpNtfReqAck>
    <signature>SignatureGoesHere</signature>
</Gepg>""".strip()

        error_ack = _sign_xml_if_enabled(error_ack)

        return error_ack
```

---

## XML Payload Structure

### Request XML (pmtSpNtfReq)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <pmtSpNtfReq>
    <PmtHdr>
      <ReqId>576HT657</ReqId>
      <GrpBillId>BILL-S-NO-001-47</GrpBillId>
      <SpGrpCode><SP_CODE></SpGrpCode>
      <CustCntrNum>255712345678</CustCntrNum>
      <EntryCnt>1</EntryCnt>
    </PmtHdr>
    <PmtDtls>
      <PmtTrxDtl>
        <SpCode><SP_CODE></SpCode>
        <BillId>BILL-S-NO-001-47</BillId>
        <BillCtrNum>9944000001234</BillCtrNum>
        <PspCode>PSP001</PspCode>
        <PspName>M-Pesa</PspName>
        <TrxId>TRX20250113061500</TrxId>
        <PayRefId>REF20250113061500</PayRefId>
        <BillAmt>50000.00</BillAmt>
        <PaidAmt>50000.00</PaidAmt>
        <BillPayOpt>3</BillPayOpt>
        <Ccy>TZS</Ccy>
        <CollAccNum>ACC001</CollAccNum>
        <TrxDtTm>2025-01-13T06:15:00</TrxDtTm>
        <UsdPayChnl>USSD</UsdPayChnl>
        <PyrCellNum>255712345678</PyrCellNum>
        <PyrName>John Doe</PyrName>
        <PyrEmail>john@example.com</PyrEmail>
      </PmtTrxDtl>
    </PmtDtls>
  </pmtSpNtfReq>
  <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

### Response XML (pmtSpNtfReqAck)

#### Success Response

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <pmtSpNtfReqAck>
        <AckId>SP20250113061501</AckId>
        <ReqId>576HT657</ReqId>
        <AckStsCode>7101</AckStsCode>
    </pmtSpNtfReqAck>
    <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

#### Error Response

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <pmtSpNtfReqAck>
        <AckId>SP20250113061501</AckId>
        <ReqId>ERROR</ReqId>
        <AckStsCode>7102</AckStsCode>
    </pmtSpNtfReqAck>
    <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

---

## Database Models

The real shape is in
[`apps/billing/models/bill.py`](../../apps/billing/models/bill.py). One
`Payment` row per GePG transaction.

| Column | Source | Notes |
| --- | --- | --- |
| `bill` | — | Foreign key. **Not** `local_bill` |
| `gepg_bill_id` | `BillId` | The bill id as GePG knows it |
| `trx_id` | `TrxId` | The idempotency key |
| `req_id`, `grp_bill_id`, `sp_grp_code`, `cust_cntr_num` | `PmtHdr` | |
| `entry_count` | `EntryCnt` | `PositiveIntegerField` |
| `bill_amount`, `paid_amount` | `BillAmt`, `PaidAmt` | `max_digits=15` |
| `trx_dt_tm` | `TrxDtTm` | When the customer paid |
| `pyr_name`, `pyr_cell_num`, `pyr_email` | `PyrName`, `PyrCellNum`, `PyrEmail` | Who paid |
| `psp_code`, `psp_name`, `usd_pay_chnl` | | Which channel took the money |

Two details differ from a naive reading:

- **`trx_id` is not `unique=True`.** It carries a *partial* unique constraint
  that excludes blanks and soft-deleted rows — the same rule every natural key
  in this project follows, because a plain `unique=True` on a soft-deletable
  model produces "cannot create, says it already exists, but I deleted it".
- **Text columns default to `""`, not `NULL`.** One empty representation rather
  than two.

---

## Processing Logic

### Step-by-Step Flow

1. **Receive XML**: GEPG posts XML to `/gepg/payments/notification/`, parsed
   with `defusedxml` rather than the standard library — the endpoint is public,
   and `xml.etree.ElementTree` is documented as unsafe against hostile input
2. **Parse XML**: Extract payment header and transaction details
3. **Validate Data**: Check for required fields (BillId, TrxId, etc.)
4. **Find Bill**: Look it up by `bill_number`, falling back to `control_number`
   — GePG may echo back either
5. **Check Duplicate**: Use TrxId to prevent duplicate payment processing
6. **Create/Update Payment**: Store payment record with all details
7. **Recompute the bill's status**: sum every payment against
   `bill.total_amount` — `paid` if covered in full, `partially_paid` if not.
   There is no magic `102`; `status_code` holds the raw gateway string from
   *submission* and is not touched here
8. **Transition the stones**: on full settlement every stone on the order moves
   to `paid`, which is what unblocks findings
8. **Generate Acknowledgment**: Create XML acknowledgment
9. **Sign Response**: Apply digital signature if enabled
10. **Return Response**: Send acknowledgment back to GEPG

### Partial payments

A bill is not only paid or unpaid. Settlement compares the **sum of every
payment** against `bill.total_amount`:

| Covered | Bill status | Stones |
| --- | --- | --- |
| In full | `paid` | All transition to `paid` |
| In part | `partially_paid` | Unchanged |

A bill that is 90% paid is still a bill nobody can act on, which is why the
stones do not move until the balance lands.

### Duplicate Payment Handling

```python
payment, created = Payment.objects.get_or_create(trx_id=trx_id, defaults=defaults)

if not created:
    # Update the existing record with the latest data
    for field, value in defaults.items():
        setattr(payment, field, value)
    payment.save()

if created:
    # Only update bill status for new payments
    bill.status_code = "102"  # Paid
    bill.status_desc = "Payment Received"
    bill.save(update_fields=["status_code", "status_desc"])
```

**Key Point**: Bill status is only updated when a **new** payment is created, preventing duplicate status updates.

---

## Helper Functions

### DateTime Parsing

```python
def _parse_gepg_datetime(value: str) -> datetime:
    """
    Parse GePG datetime strings which may optionally include fractional seconds
    using either dot or colon as the separator.
    
    Examples:
    - 2025-11-10T12:00:26
    - 2025-11-10T12:00:26.920
    - 2025-11-10T12:00:26:920
    """
    if not value:
        raise ValueError("Missing datetime value")

    # Fast path for the common format without sub-second precision
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        pass

    # Normalise the separator between seconds and fractional seconds to a dot
    normalised = re.sub(r":(\d{1,6})$", r".\1", value)

    # Try with fractional seconds
    try:
        return datetime.strptime(normalised, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError as exc:
        raise ValueError(f"Unrecognised GePG datetime format: {value}") from exc
```

---

## Status Codes

### Acknowledgment Status Codes

- **7101**: Successfully processed
- **7102**: Processing failed
- **7243**: Invalid request format *(defined by GePG; this system never sends it — it answers 7102)*

### Bill Status Codes (Updated After Payment)

- **102**: Payment Received (Paid)

---

## Error Handling

### Missing Bill

```python
try:
    bill = Bill.objects.get(bill_id=bill_id)
except Bill.DoesNotExist:
    raise ValueError(f"Bill {bill_id} not found")
```

**Response**: Returns error acknowledgment with status code 7102

### Invalid XML

```python
try:
    root = ET.fromstring(xml_content)
except Exception as e:
    # Return error acknowledgment
    return error_ack_xml
```

**Response**: Returns error acknowledgment with status code 7102

### Missing Required Fields

```python
if not pmt_hdr or not payment_details:
    raise ValueError("Missing payment header or details")

if not bill_id:
    raise ValueError("BillId missing in payment detail")
```

**Response**: Returns error acknowledgment with status code 7102

---

## Security

### CSRF Exemption

Payment notification endpoint is exempt from CSRF protection because it's called by an external system (GEPG).

```python
@csrf_exempt
@require_http_methods(["POST"])
def receive_payment_notification(request):
    # ...
```

### Digital Signature Verification

**Note**: Current implementation signs the acknowledgment but does not verify incoming signatures from GEPG. This should be implemented for production use.

**Recommended Implementation**:

```python
def verify_gepg_signature(xml_content: str, signature: str) -> bool:
    """Verify GEPG signature on incoming payment notification"""
    # Extract signature from XML
    # Load GEPG public certificate
    # Verify signature using public key
    # Return True if valid, False otherwise
    pass
```

---

## Testing

### Manual Testing with cURL

```bash
curl -X POST http://localhost:8000/gepg/payments/notification/ \
  -H "Content-Type: application/xml" \
  -d '<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <pmtSpNtfReq>
    <PmtHdr>
      <ReqId>TEST001</ReqId>
      <GrpBillId>BILL-S-NO-001-47</GrpBillId>
      <SpGrpCode><SP_CODE></SpGrpCode>
      <CustCntrNum>255712345678</CustCntrNum>
      <EntryCnt>1</EntryCnt>
    </PmtHdr>
    <PmtDtls>
      <PmtTrxDtl>
        <SpCode><SP_CODE></SpCode>
        <BillId>BILL-S-NO-001-47</BillId>
        <BillCtrNum>9944000001234</BillCtrNum>
        <PspCode>PSP001</PspCode>
        <PspName>M-Pesa</PspName>
        <TrxId>TRX-TEST-001</TrxId>
        <PayRefId>REF-TEST-001</PayRefId>
        <BillAmt>50000.00</BillAmt>
        <PaidAmt>50000.00</PaidAmt>
        <BillPayOpt>3</BillPayOpt>
        <Ccy>TZS</Ccy>
        <CollAccNum>ACC001</CollAccNum>
        <TrxDtTm>2025-01-13T06:15:00</TrxDtTm>
        <UsdPayChnl>USSD</UsdPayChnl>
        <PyrCellNum>255712345678</PyrCellNum>
        <PyrName>John Doe</PyrName>
        <PyrEmail>john@example.com</PyrEmail>
      </PmtTrxDtl>
    </PmtDtls>
  </pmtSpNtfReq>
  <signature>TestSignature</signature>
</Gepg>'
```

### Python Testing

```python
from billing_system_app.services import process_payment_notification

xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <pmtSpNtfReq>
    <!-- ... XML content ... -->
  </pmtSpNtfReq>
  <signature>TestSignature</signature>
</Gepg>"""

ack_xml = process_payment_notification(xml_content)
print(ack_xml)
```

### Verify Payment Record

```python
from billing_system_app.models import Payment, Bill

# Check payment was created
payment = Payment.objects.get(trx_id="TRX-TEST-001")
print(f"Payment Amount: {payment.paid_amount}")
print(f"Payment Status: {payment.is_processed}")

# Check bill was updated
bill = Bill.objects.get(bill_id="BILL-S-NO-001-47")
print(f"Bill Status: {bill.status_code} - {bill.status_desc}")
```

---

## Monitoring & Logging

### Log Payment Notifications

```python
import logging

logger = logging.getLogger(__name__)

logger.info(f"Received payment notification for Bill {bill_id}")
logger.info(f"Transaction ID: {trx_id}, Amount: {paid_amount}")
```

### Database Queries

```python
# Get all payments for a bill
payments = Payment.objects.filter(bill__bill_number="BILL-2627-0001")

# Get payments by date
from django.utils import timezone
from datetime import timedelta

today = timezone.now().date()
payments_today = Payment.objects.filter(trx_dt_tm__date=today)

# Get unprocessed payments
unprocessed = Payment.objects.filter(is_processed=False)
```

---

## Troubleshooting

### Issue: Payment notification not received

**Possible Causes**:
1. Firewall blocking GEPG IP
2. Incorrect callback URL configuration
3. Server not accessible from internet

**Solutions**:
1. Check firewall rules
2. Verify URL in GEPG configuration
3. Test endpoint accessibility from external network
4. Check server logs for incoming requests

### Issue: Bill not found error

**Cause**: Bill ID in payment notification doesn't match any bill in database

**Solution**:
1. Verify bill was created successfully
2. Check bill ID format matches
3. Query database: `Bill.objects.filter(bill_id='BILL-S-NO-001-47')`

### Issue: Duplicate payment processing

**Cause**: Same transaction ID sent multiple times

**Solution**: System automatically handles duplicates using `get_or_create` with `trx_id` as unique key

### Issue: DateTime parsing error

**Cause**: GEPG sends datetime in unexpected format

**Solution**: `_parse_gepg_datetime` function handles multiple formats. Check logs for actual format received.

---

## Best Practices

1. **Always return acknowledgment** - Even on errors, return proper XML acknowledgment
2. **Log all notifications** - Store raw XML for debugging and audit trail
3. **Handle duplicates gracefully** - Use unique transaction ID to prevent duplicate processing
4. **Validate all fields** - Check for required fields before processing
5. **Update bill status atomically** - Use database transactions for consistency
6. **Monitor endpoint health** - Set up alerts for failed notifications
7. **Test with various scenarios** - Test with partial payments, overpayments, etc.
8. **Implement signature verification** - Verify GEPG signatures in production

---

## Related Documentation

- [Bill Submission](01_BILL_SUBMISSION.md)
- [Reconciliation](04_RECONCILIATION.md)
- [Database Models](../../apps/billing/models/bill.py)

---

**Last Updated**: January 2026  
**Version**: 1.0
