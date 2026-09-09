# GEPG Integration - Bill Cancellation

## Overview

Bill cancellation allows the system to cancel previously submitted bills in GEPG. This is useful when:
- Customer requests cancellation
- Order is cancelled
- Bill was created in error
- Service cannot be provided

---

## Architecture

### Flow Diagram

```
User Request → Django View → cancel_bill() → XML Generation → Digital Signature → GEPG API
                                                                                      ↓
Database ← Bill Status Update ← Response Parser ← XML Response ← GEPG API Response ← GEPG API
    ↓
Order Status Reset (if applicable)
```

---

## Configuration

### Environment Variables

```bash
# Bill Cancellation Endpoint
GEPG_BILL_CANCEL_URL=http://154.118.230.202:80/api/bill/20/cancellation

# Service Provider Configuration
GEPG_SP_GRP_CODE=SP99631
GEPG_SYS_CODE=LTGC002
GEPG_SP_CODE=SP99631

# Security
GEPG_USE_DIGITAL_SIGNATURE=True
GEPG_CERTIFICATE_PASSWORD=<set-in-.env>
```

---

## Implementation

### Service Function

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:351-491`

**Function**: `cancel_bill(bill, reason, request=None)`

**Purpose**: Sends a bill cancellation request to GEPG

**Parameters**:
- `bill`: Bill object to cancel
- `reason`: Cancellation reason (string)
- `request`: Optional Django request object for user context

**Returns**: Dictionary with:
- `status_code`: GEPG response status code
- `status_desc`: Status description
- `raw_response`: Raw XML response from GEPG

**Code Example**:

```python
from billing_system_app.services import cancel_bill
from billing_system_app.models import Bill

# Get the bill to cancel
bill = Bill.objects.get(bill_id="BILL-S-NO-001-47")

# Cancel the bill
result = cancel_bill(bill=bill, reason="Customer requested cancellation", request=request)

# Check result
if result["status_code"] == "7283":
    print(f"Bill cancelled successfully")
    print(f"Status: {result['status_desc']}")
else:
    print(f"Cancellation failed: {result['status_desc']}")
```

---

## XML Payload Structure

### Request XML (billCanclReq)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
 <billCanclReq>
 <ReqId>SP9963120250113061430</ReqId>
            <SpGrpCode>SP99631</SpGrpCode>
            <SysCode>LTGC002</SysCode>
            <BillTyp>1</BillTyp>
            <GrpBillId>BILL-S-NO-001-47</GrpBillId>
 <CanclGenBy>admin</CanclGenBy>
 <CanclApprBy>admin</CanclApprBy>
 <CanclReasn>Customer requested cancellation</CanclReasn>
 </billCanclReq>
 <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

### Response XML (billCanclReqAck + billCanclRes)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <billCanclReqAck>
    <AckId>ACK20250113061431</AckId>
    <ReqId>SP9963120250113061430</ReqId>
    <AckStsCode>7101</AckStsCode>
    <AckStsDesc>Successfully</AckStsDesc>
  </billCanclReqAck>
  
  <billCanclRes>
    <ReqId>SP9963120250113061430</ReqId>
    <GrpBillId>BILL-S-NO-001-47</GrpBillId>
    <CanclStsCode>7283</CanclStsCode>
    <CanclStsDesc>Bill Cancelled Successfully</CanclStsDesc>
  </billCanclRes>
  <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

---

## Implementation Details

### Complete Function Code

```python
def cancel_bill(bill: Bill, reason: str, request=None) -> dict:
    """
    Sends a bill cancellation request to the external mock GePG system.
    Returns a dict with keys: status_code, status_desc, raw_response
    """
    import logging

    logger = logging.getLogger(__name__)

    # Use settings from .env instead of database
    sp_grp_code = settings.GEPG_SP_GRP_CODE
    sys_code = settings.GEPG_SYS_CODE

    # Escape XML special characters in user-provided data
    escaped_reason = _escape_xml(reason)
    escaped_gen_by = _escape_xml(bill.bill_generated_by)
    escaped_appr_by = _escape_xml(bill.bill_approved_by)

    # Generate XML with proper indentation and line breaks
    xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
 <billCanclReq>
 <ReqId>{_generate_req_id(sp_grp_code)}</ReqId>
            <SpGrpCode>{sp_grp_code}</SpGrpCode>
            <SysCode>{sys_code}</SysCode>
            <BillTyp>{bill.bill_type}</BillTyp>
            <GrpBillId>{bill.bill_id}</GrpBillId>
 <CanclGenBy>{escaped_gen_by}</CanclGenBy>
 <CanclApprBy>{escaped_appr_by}</CanclApprBy>
 <CanclReasn>{escaped_reason}</CanclReasn>
 </billCanclReq>
 <signature>SignatureGoesHere</signature>
</Gepg>""".strip()

    # Sign the XML payload if digital signatures are enabled
    xml_payload = _sign_xml_if_enabled(xml_payload)

    # Debug: log and persist the request XML
    logger.info("=== Sending Bill Cancellation Request ===")
    logger.info(f"Bill ID: {bill.bill_id} | Reason: {reason}")
    logger.info(f"XML Payload:\n{xml_payload}\n")

    try:
        with open("/tmp/gepg_request_debug.xml", "a") as debug_file:
            debug_file.write(f"=== Cancellation Request sent at {now()} ===\n")
            debug_file.write(f"Bill ID: {bill.bill_id}\n")
            debug_file.write(f"Reason: {reason}\n")
            debug_file.write(f"{xml_payload}\n\n")
    except Exception:
        pass

    # Send the request to external mock GePG
    url = settings.GEPG_BILL_CANCEL_URL
    sp_code = settings.GEPG_SP_CODE
    try:
        resp = requests.post(
            url,
            data=xml_payload.encode("utf-8"),
            headers={
                "Content-Type": "application/xml",
                "Gepg-Com": "changebill.sp.in",
                "Gepg-Code": sp_code,
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw_response = resp.text

        # Debug: log full response
        logger.info("=== Bill Cancellation HTTP Response ===")
        logger.info(raw_response)

        try:
            with open("/tmp/gepg_request_debug.xml", "a") as debug_file:
                debug_file.write(f"=== Cancellation Response received at {now()} ===\n")
                debug_file.write(f"Bill ID: {bill.bill_id}\n")
                debug_file.write(raw_response)
                debug_file.write("\n\n")
        except Exception:
            pass
    except requests.exceptions.RequestException:
        raise

    # Parse XML response
    root = ET.fromstring(raw_response)
    ns = {}

    # Log acknowledgment (Step 2)
    bill_cancl_req_ack = root.find("billCanclReqAck", ns)
    if bill_cancl_req_ack is not None:
        ack_sts_code = bill_cancl_req_ack.findtext("AckStsCode")
        ack_sts_desc = bill_cancl_req_ack.findtext("AckStsDesc")
        ack_req_id = bill_cancl_req_ack.findtext("ReqId")

        logger.info("=== Received Bill Cancellation Acknowledgment ===")
        logger.info(f"Ack Status: {ack_sts_code} - {ack_sts_desc}")
        logger.info(f"ReqId: {ack_req_id}")

    bill_cancl_res = root.find("billCanclRes", ns)
    status_code = (
        bill_cancl_res.findtext("CanclStsCode") if bill_cancl_res is not None else None
    )
    status_desc = (
        bill_cancl_res.findtext("CanclStsDesc") if bill_cancl_res is not None else None
    )

    # Update bill status
    if status_code == "7283":  # Success code
        bill.status_code = status_code
        bill.status_desc = status_desc
        bill.save()

        # Get the identification item and reset its order status
        try:
            from gemmology_app.models import ItemTB, Status

            if bill.customer_id and bill.customer_id.isdigit():
                item = ItemTB.objects.filter(id=int(bill.customer_id)).first()
                if item and item.order_no:
                    # Reset order status to 100 (new)
                    item.order_no.status = Status.objects.get(code="100")
                    item.order_no.save()
        except Exception:
            # Don't let status update failure prevent bill cancellation
            pass

    return {
        "status_code": status_code,
        "status_desc": status_desc,
        "raw_response": raw_response,
    }
```

---

## Key Features

### 1. XML Escaping

User-provided data (reason, generated_by, approved_by) is escaped to prevent XML injection:

```python
escaped_reason = _escape_xml(reason)
escaped_gen_by = _escape_xml(bill.bill_generated_by)
escaped_appr_by = _escape_xml(bill.bill_approved_by)
```

### 2. Digital Signature

XML payload is signed before sending:

```python
xml_payload = _sign_xml_if_enabled(xml_payload)
```

### 3. Debug Logging

All requests and responses are logged to `/tmp/gepg_request_debug.xml`:

```python
with open("/tmp/gepg_request_debug.xml", "a") as debug_file:
    debug_file.write(f"=== Cancellation Request sent at {now()} ===\n")
    debug_file.write(f"Bill ID: {bill.bill_id}\n")
    debug_file.write(f"Reason: {reason}\n")
    debug_file.write(f"{xml_payload}\n\n")
```

### 4. Order Status Reset

When a bill is cancelled, the associated order status is reset to "new" (code 100):

```python
if status_code == "7283":  # Success code
    # Update bill status
    bill.status_code = status_code
    bill.status_desc = status_desc
    bill.save()

    # Reset order status
    try:
        from gemmology_app.models import ItemTB, Status

        if bill.customer_id and bill.customer_id.isdigit():
            item = ItemTB.objects.filter(id=int(bill.customer_id)).first()
            if item and item.order_no:
                item.order_no.status = Status.objects.get(code="100")
                item.order_no.save()
    except Exception:
        pass
```

---

## Status Codes

### Success Codes
- **7283**: Bill cancelled successfully

### Acknowledgment Codes
- **7101**: Request acknowledged successfully
- **7102**: Request acknowledgment failed

### Error Codes
- **7284**: Bill not found
- **7285**: Bill already cancelled
- **7286**: Bill already paid (cannot cancel)
- **7287**: Invalid bill status for cancellation

---

## HTTP Headers

### Request Headers

```python
headers = {
    "Content-Type": "application/xml",
    "Gepg-Com": "changebill.sp.in",
    "Gepg-Code": sp_code,  # e.g., "SP99631"
}
```

**Note**: The `Gepg-Com` header value is `"changebill.sp.in"` for cancellation requests.

---

## Response Handling

### Two-Step Response

1. **Acknowledgment (billCanclReqAck)**: Confirms request received
2. **Result (billCanclRes)**: Contains actual cancellation status

### Parsing Logic

```python
# Parse acknowledgment
bill_cancl_req_ack = root.find("billCanclReqAck", ns)
if bill_cancl_req_ack is not None:
    ack_sts_code = bill_cancl_req_ack.findtext("AckStsCode")
    ack_sts_desc = bill_cancl_req_ack.findtext("AckStsDesc")

# Parse result
bill_cancl_res = root.find("billCanclRes", ns)
status_code = bill_cancl_res.findtext("CanclStsCode")
status_desc = bill_cancl_res.findtext("CanclStsDesc")
```

---

## Error Handling

### Network Errors

```python
try:
    resp = requests.post(
        url, data=xml_payload.encode("utf-8"), headers=headers, timeout=30
    )
    resp.raise_for_status()
except requests.exceptions.RequestException:
    raise
```

### XML Parsing Errors

```python
try:
    root = ET.fromstring(raw_response)
except Exception as e:
    raise ValueError(f"Invalid XML response: {str(e)}")
```

### Bill Not Found

If GEPG returns status code 7284, the bill was not found in GEPG system.

### Bill Already Paid

If GEPG returns status code 7286, the bill has already been paid and cannot be cancelled.

---

## Testing

### Manual Testing

```python
from billing_system_app.services import cancel_bill
from billing_system_app.models import Bill

# Get a bill
bill = Bill.objects.get(bill_id="BILL-S-NO-001-47")

# Cancel it
result = cancel_bill(bill=bill, reason="Test cancellation", request=None)

# Check result
print(f"Status Code: {result['status_code']}")
print(f"Status Desc: {result['status_desc']}")
print(f"Raw Response: {result['raw_response']}")
```

### Verify Database Update

```python
# Refresh bill from database
bill.refresh_from_db()

# Check status
print(f"Bill Status: {bill.status_code} - {bill.status_desc}")

# Check order status (if identification bill)
if bill.customer_id and bill.customer_id.isdigit():
    from gemmology_app.models import ItemTB

    item = ItemTB.objects.filter(id=int(bill.customer_id)).first()
    if item and item.order_no:
        print(f"Order Status: {item.order_no.status.code}")
```

---

## Common Use Cases

### 1. Customer Cancellation Request

```python
def handle_customer_cancellation(bill_id, reason):
    bill = Bill.objects.get(bill_id=bill_id)

    # Check if bill is paid
    if bill.status_code == "102":
        return {"error": "Cannot cancel paid bill"}

    # Cancel the bill
    result = cancel_bill(bill, reason)

    if result["status_code"] == "7283":
        return {"success": True, "message": "Bill cancelled successfully"}
    else:
        return {"error": result["status_desc"]}
```

### 2. Order Cancellation

```python
def cancel_order_bill(order):
    # Find bill for this order
    bill = Bill.objects.filter(
        customer_id=str(order.id),
        status_code__in=["7101", "7241"],  # Not paid or cancelled
    ).first()

    if bill:
        result = cancel_bill(bill=bill, reason=f"Order {order.order_no} cancelled")
        return result
    else:
        return {"error": "No active bill found for this order"}
```

### 3. Bulk Cancellation

```python
def cancel_expired_bills():
    from django.utils import timezone

    # Find expired unpaid bills
    expired_bills = Bill.objects.filter(
        bill_expiry_date__lt=timezone.now(), status_code__in=["7101", "7241"]
    )

    results = []
    for bill in expired_bills:
        result = cancel_bill(bill=bill, reason="Bill expired")
        results.append({"bill_id": bill.bill_id, "status": result["status_code"]})

    return results
```

---

## Troubleshooting

### Issue: Cancellation request timeout

**Cause**: GEPG API not responding

**Solution**:
1. Check GEPG API URL is correct
2. Verify network connectivity
3. Check firewall settings
4. Increase timeout value if needed

### Issue: Bill status not updated

**Cause**: Status code is not '7283'

**Solution**:
1. Check GEPG response status code
2. Verify bill exists in GEPG
3. Check if bill is already paid or cancelled
4. Review debug logs in `/tmp/gepg_request_debug.xml`

### Issue: Order status not reset

**Cause**: Exception in order status update logic

**Solution**:
1. Verify customer_id is numeric
2. Check ItemTB record exists
3. Verify Status object with code '100' exists
4. Check exception logs

### Issue: XML special characters causing errors

**Cause**: Unescaped special characters in reason or user names

**Solution**: System automatically escapes XML characters using `_escape_xml()` function

---

## Best Practices

1. **Always provide clear cancellation reasons** - Helps with audit trail
2. **Check bill status before cancelling** - Don't try to cancel paid bills
3. **Log all cancellation requests** - For debugging and compliance
4. **Handle errors gracefully** - Return meaningful error messages
5. **Update related records** - Reset order status when cancelling identification bills
6. **Test in staging first** - Verify cancellation works before production use
7. **Monitor cancellation rates** - High cancellation rates may indicate issues
8. **Preserve audit trail** - Keep raw XML responses for compliance

---

## Security Considerations

### 1. Authorization

Ensure only authorized users can cancel bills:

```python
from django.contrib.auth.decorators import permission_required


@permission_required("billing_system_app.can_cancel_bill")
def cancel_bill_view(request, bill_id):
    bill = Bill.objects.get(bill_id=bill_id)
    result = cancel_bill(bill, request.POST.get("reason"), request)
    # ...
```

### 2. Audit Logging

Log who cancelled the bill and when:

```python
import logging

logger = logging.getLogger("billing.audit")

logger.info(f"Bill {bill.bill_id} cancelled by {request.user.username}")
logger.info(f"Reason: {reason}")
logger.info(f"Status: {result['status_code']}")
```

### 3. Validation

Validate cancellation reason:

```python
def validate_cancellation_reason(reason):
    if not reason or len(reason.strip()) < 10:
        raise ValueError("Cancellation reason must be at least 10 characters")
    if len(reason) > 500:
        raise ValueError("Cancellation reason too long")
    return reason.strip()
```

---

## Related Documentation

- [Bill Submission](01_BILL_SUBMISSION.md)
- [Payment Notification](02_PAYMENT_NOTIFICATION.md)
- [Database Models](../../apps/billing/models/bill.py)

---

**Last Updated**: January 2026  
**Version**: 1.0
