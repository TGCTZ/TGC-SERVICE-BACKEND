# GEPG Integration - Bill Submission

## Overview

Bill submission is the process of creating and submitting bills to the GEPG (Government Electronic Payment Gateway) system. The TGC Mifumo system supports bill creation for two main services:

1. **Identification Services** - Bills for gemstone identification
2. **Production Shop Orders** - Bills for production shop services

---

## Architecture

### Flow Diagram

```
User Request → Django View → Service Function → XML Generation → Digital Signature → GEPG API
                                                                                        ↓
Database ← Bill Record ← Response Parser ← XML Response ← GEPG API Response ← GEPG API
    ↓
SMS Service → Customer Notification
```

---

## Configuration

### Environment Variables

```bash
# Bill Submission Endpoint
GEPG_BILL_CREATE_URL=http://154.118.230.202:80/api/bill/20/submission

# Service Provider Configuration
GEPG_SP_GRP_CODE=SP99631
GEPG_SYS_CODE=LTGC002
GEPG_SP_CODE=SP99631
GEPG_SUB_SP_CODE=1001
GEPG_COLL_CENT_CODE=CC1014000199631
GEPG_GFS_CODE=142201660128

# Security
GEPG_USE_DIGITAL_SIGNATURE=True
GEPG_CERTIFICATE_PASSWORD=<set-in-.env>
```

---

## Implementation

### Service Functions

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py`

#### 1. Identification Services Bill Creation

**Function**: `create_external_bill_for_identification(item, request=None)`

**Purpose**: Creates a bill for gemstone identification services

**Parameters**:
- `item`: ItemTB object containing identification details
- `request`: Optional Django request object for user context

**Returns**: Dictionary with:
- `bill_id`: Unique bill identifier
- `control_number`: GEPG control number for payment
- `status_code`: GEPG response status code
- `status_desc`: Status description
- `raw_response`: Raw XML response from GEPG

**Code Example**:

```python
from billing_system_app.services import create_external_bill_for_identification
from gemmology_app.models import ItemTB

# Get the identification item
item = ItemTB.objects.get(id=96)

# Create bill
result = create_external_bill_for_identification(item, request)

# Check result
if result["status_code"] in ["7101", "7241"]:
    print(f"Bill created: {result['bill_id']}")
    print(f"Control Number: {result['control_number']}")
else:
    print(f"Error: {result['status_desc']}")
```

**Key Features**:
- Automatic bill ID generation: `BILL-S-NO-{order_no}-{item_id}`
- Customer ID derived from item ID (zero-padded to 8 digits)
- Phone number normalization to Tanzania format (255...)
- XML special character escaping
- Digital signature application
- Automatic SMS notification on success

#### 2. Production Shop Bill Creation

**Function**: `create_external_bill_for_production_shop(order, description, total_amount, request=None)`

**Purpose**: Creates a bill for production shop orders

**Parameters**:
- `order`: Order object containing order details
- `description`: Bill description
- `total_amount`: Total bill amount
- `request`: Optional Django request object

**Returns**: Same dictionary structure as identification bills

**Code Example**:

```python
from billing_system_app.services import create_external_bill_for_production_shop
from production_shop_app.models import Order

# Get the order
order = Order.objects.get(order_no="ORD-2025-001")

# Create bill
result = create_external_bill_for_production_shop(
    order=order,
    description="Production Shop Services",
    total_amount=150000.00,
    request=request,
)
```

---

## XML Payload Structure

### Request XML (billSubReq)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
  <billSubReq>
    <BillHdr>
      <ReqId>SP9963120250113061430</ReqId>
      <SpGrpCode>SP99631</SpGrpCode>
      <SysCode>LTGC002</SysCode>
      <BillTyp>1</BillTyp>
      <PayTyp>2</PayTyp>
      <GrpBillId>BILL-S-NO-001-47</GrpBillId>
    </BillHdr>
    
    <BillDtls>
      <BillDtl>
        <BillId>BILL-S-NO-001-47</BillId>
        <SpCode>SP99631</SpCode>
        <CollCentCode>CC1014000199631</CollCentCode>
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
            <GfsCode>142201660128</GfsCode>
            <BillItemRef>B1IT-96</BillItemRef>
            <UseItemRefOnPay>N</UseItemRefOnPay>
            <BillItemAmt>50000.00</BillItemAmt>
            <BillItemEqvAmt>50000.00</BillItemEqvAmt>
            <CollSp>SP99631</CollSp>
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
    <ReqId>SP9963120250113061430</ReqId>
    <AckStsCode>7101</AckStsCode>
    <AckStsDesc>Successfully</AckStsDesc>
  </billSubReqAck>
  
  <billSubRes>
    <BillHdr>
      <ResId>RES20250113061431</ResId>
      <ReqId>SP9963120250113061430</ReqId>
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
    <ReqId>SP9963120250113061430</ReqId>
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
4. Send SMS notification to customer
5. Return success response

### Asynchronous Flow

1. Send bill submission request
2. Receive acknowledgment (7101) without control number
3. Create Bill record with `control_number="PENDING"`
4. Wait for callback with `billSubRes`
5. Update Bill record with actual control number
6. Send SMS notification to customer

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

### Bill Model

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/models.py:17-44`

```python
class Bill(models.Model):
    bill_id = models.CharField(max_length=50, unique=True)
    service_provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE)
    control_number = models.CharField(max_length=20, blank=True, null=True)
    bill_type = models.IntegerField(choices=BILL_TYPE_CHOICES, default=1)
    pay_type = models.IntegerField(choices=PAY_TYPE_CHOICES, default=1)
    customer_name = models.CharField(max_length=255)
    customer_id = models.CharField(max_length=50)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)
    customer_email = models.EmailField(blank=True, null=True)
    bill_description = models.TextField()
    bill_generated_date = models.DateTimeField()
    bill_expiry_date = models.DateTimeField()
    bill_amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=5, default="TZS")
    status_code = models.CharField(max_length=10, blank=True, null=True)
    status_desc = models.CharField(max_length=255, blank=True, null=True)
```

### BillItem Model

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/models.py:47-58`

```python
class BillItem(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="items")
    sub_sp_code = models.CharField(max_length=20)
    gfs_code = models.CharField(max_length=20)
    item_ref = models.CharField(max_length=50)
    use_item_ref_on_pay = models.BooleanField(default=False)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    eqv_amount = models.DecimalField(max_digits=15, decimal_places=2)
    coll_sp = models.CharField(max_length=20)
```

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

All bill submission requests are digitally signed using PKCS#12 certificates with SHA256withRSA algorithm.

**Implementation**: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/crypto_utils.py`

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

- **Private Key**: `tgc_mifumo/certificates/tgpmis_privatekey.pfx`
- **Public Certificate**: `tgc_mifumo/certificates/gepgpubliccertificate_DEC2024_DEC2026.pfx`
- **Password**: Stored in `GEPG_CERTIFICATE_PASSWORD` environment variable

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
4. Check GEPG response in debug file: `/tmp/gepg_request_debug.xml`
5. Verify SMS notification sent

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
1. Check callback URL is accessible: `https://api.tgpmis.tgc.ac.tz/billing/api/bill/response/`
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
4. **Send SMS notifications** after successful bill creation
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
