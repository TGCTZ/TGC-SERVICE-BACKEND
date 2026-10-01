# GePG Integration - Bill Submission

## Overview

Bill submission is how a bill gets a **control number**: the system builds a
`billSubReq` XML document, optionally signs it, and posts it to GePG. The
customer then pays that number at any bank or mobile wallet.

One bill covers one **order** — the customer's whole visit — with a line item
per stone.

> The XML contract below is accurate and is the reason this document exists.
> The surrounding narrative was written against the system this one replaces, so
> function names, model shapes and file paths in the code listings are
> provenance rather than a map. Where behaviour differs, a note says so.

---

## Architecture

```
Bill request → generate_bill_for_order() → build_bill_xml() → sign (optional) → GePG
                                                                                  ↓
   Bill record ← control number ← _parse_bill_response() ← billSubRes ← GePG response
```

If GePG acknowledges without a number, it arrives later on the
`/gepg/bill/response/` callback instead.

---

## Configuration

### Environment Variables

```bash
# Bill Submission Endpoint
GEPG_BILL_CREATE_URL=https://<gepg-host>/api/bill/20/submission

# Service Provider Configuration
GEPG_SP_GRP_CODE=<SP_CODE>
GEPG_SYS_CODE=<SYS_CODE>
GEPG_SP_CODE=<SP_CODE>
GEPG_SUB_SP_CODE=1001
GEPG_COLL_CENT_CODE=<COLL_CENT_CODE>
GEPG_GFS_CODE=<GFS_CODE>

# Security
GEPG_USE_DIGITAL_SIGNATURE=False   # default; signing is opt-in
GEPG_CERTIFICATE_PASSWORD=<set-in-.env>
```

---

## Implementation

### The entry point

There is **one** way a bill is created:

```python
from apps.billing.services.bill import generate_bill_for_order

bill = generate_bill_for_order(order, service_provider=None, user=request.user)
```

Reached over HTTP as `POST /api/v1/bills/generate/` with `{"order": <id>}`,
guarded by `billing.generate_bill`.

To see what a bill *would* say before raising it:
`GET /api/v1/bills/preview/?order=<id>`. This exists because the fee lives on
the stone's **category**, so a caller holding only the stone types cannot work
out the total itself.

### What it does

1. Prices each stone from `stone.stone_type.category.price`, and **freezes** the
   charge onto the line item — a later price change never alters a raised bill.
2. Allocates `bill_number` as `BILL-YYYY-NNNN`, scanning soft-deleted rows so a
   number is never reissued.
3. Builds `billSubReq` and posts it.
4. Stores the control number if one came back.

Refusals are `ServiceError`: an order with no stones, an order already billed.
Network failure is **not** an exception — the gateway call logs and returns a
result dict with a `CONNECTION_ERROR` status, and the bill is left without a
control number.

> **Differences from the listings further down this document**
>
> | The listings say | Actually |
> | --- | --- |
> | Two entry points, one per service | One: `generate_bill_for_order()` |
> | A "production shop" service exists | It does not; this system only identifies stones |
> | Bill id is `BILL-S-NO-{order}-{item}` | `BILL-YYYY-NNNN`, one per order |
> | Customer id derived from the item id | Derived from the customer's id |
> | SMS is sent on success | No SMS exists anywhere |
> | Store `control_number='PENDING'` | Never stored; the column stays empty |
> | A duplicate returns the existing bill | It raises `ServiceError` |
> | Network errors raise `ValueError` | They are returned, not raised |

---

## XML Payload Structure

### Request XML (billSubReq)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <billSubReq>
    <BillHdr>
      <ReqId><SP_CODE>20250113061430</ReqId>
      <SpGrpCode><SP_CODE></SpGrpCode>
      <SysCode><SYS_CODE></SysCode>
      <BillTyp>1</BillTyp>
      <PayTyp>1</PayTyp>
      <GrpBillId>BILL-S-NO-001-47</GrpBillId>
    </BillHdr>
    
    <BillDtls>
      <BillDtl>
        <BillId>BILL-S-NO-001-47</BillId>
        <SpCode><SP_CODE></SpCode>
        <CollCentCode><COLL_CENT_CODE></CollCentCode>
        <BillDesc>Identification - Ruby</BillDesc>
        <CustTin>000000000</CustTin>
        <CustId>00000096</CustId>
        <CustIdTyp>5</CustIdTyp>
        <CustAccnt>TGCACCNT</CustAccnt>
        <CustName>John Doe</CustName>
        <CustCellNum>255712345678</CustCellNum>
        <CustEmail>john@example.com</CustEmail>
        <BillGenDt>2025-01-13T06:14:30</BillGenDt>
        <BillExprDt>2026-01-13T06:14:30</BillExprDt>
        <BillGenBy>admin</BillGenBy>
        <BillApprBy>admin</BillApprBy>
        <BillAmt>50000.00</BillAmt>
        <BillEqvAmt>50000.00</BillEqvAmt>
        <MinPayAmt>50000.00</MinPayAmt>
        <Ccy>TZS</Ccy>
        <ExchRate>1.00</ExchRate>
        <BillPayOpt>3</BillPayOpt>
        <PayPlan>1</PayPlan>
        <PayLimTyp>1</PayLimTyp>
        <PayLimAmt>0.00</PayLimAmt>
        <CollPsp></CollPsp>
        
        <BillItems>
          <BillItem>
            <RefBillId>BILL-S-NO-001-47</RefBillId>
            <SubSpCode>1001</SubSpCode>
            <GfsCode><GFS_CODE></GfsCode>
            <BillItemRef>B1IT-96</BillItemRef>
            <UseItemRefOnPay>N</UseItemRefOnPay>
            <BillItemAmt>50000.00</BillItemAmt>
            <BillItemEqvAmt>50000.00</BillItemEqvAmt>
            <CollSp><SP_CODE></CollSp>
          </BillItem>
        </BillItems>
      </BillDtl>
    </BillDtls>
  </billSubReq>
  <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

### Response XML (billSubReqAck + billSubRes)

#### Synchronous Response (Immediate Control Number)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <billSubReqAck>
    <AckId>ACK20250113061431</AckId>
    <ReqId><SP_CODE>20250113061430</ReqId>
    <AckStsCode>7101</AckStsCode>
    <AckStsDesc>Successfully</AckStsDesc>
  </billSubReqAck>
  
  <billSubRes>
    <BillHdr>
      <ResId>RES20250113061431</ResId>
      <ReqId><SP_CODE>20250113061430</ReqId>
    </BillHdr>
    <BillDtls>
      <BillDtl>
        <BillId>BILL-S-NO-001-47</BillId>
        <BillCntrNum>9944000001234</BillCntrNum>
        <BillStsCode>7101</BillStsCode>
        <BillStsDesc>Bill Created Successfully</BillStsDesc>
      </BillDtl>
    </BillDtls>
  </billSubRes>
  <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

#### Asynchronous Response (Acknowledgment Only)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <billSubReqAck>
    <AckId>ACK20250113061431</AckId>
    <ReqId><SP_CODE>20250113061430</ReqId>
    <AckStsCode>7101</AckStsCode>
    <AckStsDesc>Successfully</AckStsDesc>
  </billSubReqAck>
  <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

**Note**: In asynchronous mode, the `billSubRes` is sent later to the callback URL.

---

## Response Handling

### Synchronous Flow

1. Send bill submission request
2. Receive immediate response with control number
3. Create Bill record in database
4. Notify the customer *(not implemented — see document 05)*
5. Return success response

### Asynchronous Flow

1. Send bill submission request
2. Receive acknowledgment (7101) without control number
3. Create Bill record with `control_number="PENDING"`
4. Wait for callback with `billSubRes`
5. Update Bill record with actual control number
6. Notify the customer *(not implemented — see document 05)*

**Code Implementation**:

```python
# From services.py lines 678-730
if bill_hdr is None or bill_dtls is None:
    if ack is not None and ack.findtext("AckStsCode") == "7101":
        # ASYNCHRONOUS FLOW
        print("✅ Step 1-2 Complete: Request acknowledged by GePG (7101)")
        print("⏳ Step 3 Pending: Waiting for GePG to send billSubRes to callback URL")
        
        # Create a pending bill record
        billing_bill = Bill.objects.create(
            bill_id=bill_id_str,
            service_provider=sp,
            control_number="PENDING",  # Will be updated in callback
            # ... other fields ...
            status_code="7101",
            status_desc="Acknowledged - Awaiting Control Number",
        )
        
        return {
            "bill_id": bill_id_str,
            "control_number": "PENDING",
            "status_code": "7101",
            "status_desc": "Acknowledged - Awaiting Control Number",
            "raw_response": raw_response,
        }
```

---

## Status Codes

### Success Codes
- **7101**: Successfully processed
- **7241**: Successfully processed with warnings

### Error Codes
- **7102**: Invalid request format
- **7201**: Duplicate bill ID
- **7284**: Invalid response format
- **7301**: Authentication failed
- **7401**: Service provider not found

---

## Database Models

The real shapes are in
[`apps/billing/models/bill.py`](../../apps/billing/models/bill.py). The columns
that matter to submission:

### `Bill`

| Column | Notes |
| --- | --- |
| `bill_number` | `BILL-YYYY-NNNN`, allocated locally |
| `control_number` | Issued by GePG; blank until it arrives |
| `order` | One-to-one. One bill per order |
| `service_provider` | Foreign key |
| `total_amount` | Sum of the line items |
| `status` | `pending` / `partially_paid` / `paid` / `cancelled` / `expired` |
| `bill_type`, `pay_type` | `PositiveSmallIntegerField`, both default `1` |
| `status_code`, `status_desc` | The raw gateway strings from submission |
| `gepg_submitted_at` | When it went out |

### `BillItem`

| Column | Notes |
| --- | --- |
| `bill` | Foreign key |
| `stone` | Which stone this line is for |
| `description`, `unit_price`, `amount` | The frozen charge |
| `weight` | Nullable — recorded, not priced on |
| `gfs_code`, `item_ref` | Carried into the XML |

The fields the legacy model stored per row — `sub_sp_code`, `coll_sp`,
`use_item_ref_on_pay`, `eqv_amount` — are **not columns here**. They are emitted
into the XML from settings, because they are the same for every bill this system
raises and storing a constant per row invites the copies to disagree.

Customer details are likewise not duplicated onto the bill: they are reached
through `bill.order.customer`.

---

## Helper Functions

### Amount Formatting

```python
def _format_amount(value: float | Decimal) -> str:
    """Format amount to 2 decimal places"""
    amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amount:.2f}"
```

### Phone Number Normalization

```python
def _normalize_msisdn_tz(phone: str | None) -> str:
    """Normalize phone number to Tanzania format (255...)"""
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
```

### XML Escaping

```python
def _escape_xml(text: str | None) -> str:
    """Escape XML special characters"""
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
```

---

## Security

### Digital Signatures

Bill submissions **can** be signed with a PKCS#12 key using SHA256withRSA. Two
things to know before relying on it:

- It is **opt-in and off by default** (`GEPG_USE_DIGITAL_SIGNATURE=False`).
- When enabled, it **fails open**: a missing or unreadable key logs an error and
  sends the payload with the `SignatureGoesHere` placeholder still in place,
  rather than refusing to send.

Assume outbound messages are currently unsigned unless you have checked the
setting and the key.

**Implementation**: `apps/billing/gateways/signing.py`

```python
def sign_xml_payload(xml_payload: str) -> str:
    """Add digital signature to XML payload"""
    signature = sign_xml_content(xml_payload)
    signed_payload = xml_payload.replace(
        "<signature>SignatureGoesHere</signature>", f"<signature>{signature}</signature>"
    )
    return signed_payload
```

### Certificate Configuration

- **Private key**: `GEPG_PRIVATE_KEY_PATH`, defaulting to
  `certificates/private.pfx`
- **Public certificate**: `GEPG_PUBLIC_CERT_PATH`, defaulting to
  `certificates/public.pfx` — **read by nothing**. Inbound messages are not
  verified; see the gaps list in [the overview](00_GEPG_INTEGRATION_OVERVIEW.md)
- **Password**: `GEPG_CERTIFICATE_PASSWORD`, with no default, because a blank
  passphrase would let an unsigned payload reach the gateway unnoticed

---

## Error Handling

### Network Errors

```python
try:
    resp = requests.post(
        url, data=xml_payload.encode("utf-8"), headers=headers, timeout=30
    )
    resp.raise_for_status()
except requests.exceptions.RequestException as e:
    raise ValueError(f"Failed to connect to GePG API: {str(e)}")
```

### XML Parsing Errors

```python
try:
    root = ET.fromstring(raw_response)
except Exception as e:
    raise ValueError(f"Invalid XML response: {str(e)}")
```

### Duplicate Bills

```python
existing_bill = Bill.objects.filter(bill_id=gepg_bill_id).first()
if existing_bill:
    return {
        "bill_id": existing_bill.bill_id,
        "control_number": existing_bill.control_number,
        "status_code": existing_bill.status_code,
        "status_desc": existing_bill.status_desc,
    }
```

---

## Testing

### Manual Testing

1. Create a test identification item
2. Call bill creation function
3. Verify bill record in database
4. Check the logged request and response — the gateway module logs both through Django's logging framework; nothing is written to a debug file
5. ~~Verify SMS notification sent~~ *(no SMS is sent)*

### Test Data

```python
# Test bill creation
from billing_system_app.services import create_external_bill_for_identification
from gemmology_app.models import ItemTB

item = ItemTB.objects.first()
result = create_external_bill_for_identification(item)

print(f"Bill ID: {result['bill_id']}")
print(f"Control Number: {result['control_number']}")
print(f"Status: {result['status_code']} - {result['status_desc']}")
```

---

## Troubleshooting

### Issue: Control Number is "PENDING"

**Cause**: Asynchronous response flow - waiting for callback

**Solution**: 
1. Check the callback URL is reachable: `https://<your-host>/gepg/bill/response/`
2. Verify GEPG can reach your server
3. Check firewall settings
4. Monitor callback endpoint logs

### Issue: Digital Signature Failed

**Cause**: Certificate issues or password mismatch

**Solution**:
1. Verify certificate files exist
2. Check `GEPG_CERTIFICATE_PASSWORD` is correct
3. Ensure certificate is not expired
4. Check certificate format (must be PKCS#12 .pfx)

### Issue: Invalid Customer ID

**Cause**: Customer ID contains non-numeric characters

**Solution**: System automatically uses item ID zero-padded to 8 digits

---

## Best Practices

1. **Always validate input data** before creating bills
2. **Use try-except blocks** for API calls
3. **Log all requests and responses** for debugging
4. **Notify the customer** after successful bill creation *(not built)*
5. **Handle both synchronous and asynchronous** response flows
6. **Check for duplicate bills** before creating new ones
7. **Set appropriate bill expiry dates** (typically 365 days)
8. **Escape XML special characters** in user input

---

## Related Documentation

- [Payment Notification](02_PAYMENT_NOTIFICATION.md)
- [Bill Cancellation](03_BILL_CANCELLATION.md)
- [SMS Integration](05_SMS_INTEGRATION.md)

---

**Last Updated**: January 2026  
**Version**: 1.0
