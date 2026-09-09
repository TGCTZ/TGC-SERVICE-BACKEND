# GEPG Integration - Reconciliation

## Overview

Reconciliation is the process of requesting and matching payment records between the TGC Mifumo system and GEPG. This ensures that all payments are properly recorded and accounted for in both systems.

---

## Architecture

### Flow Diagram

```
Step 1: TGC System → GEPG: sucSpPmtReq (Reconciliation Request)
Step 2: GEPG → TGC System: sucSpPmtReqAck (Request Acknowledgment)
Step 3: GEPG → TGC System: sucSpPmtRes (Reconciliation Response with payment list)
Step 4: TGC System → GEPG: sucSpPmtResAck (Response Acknowledgment)
```

### Process Flow

```
Manual/Scheduled Trigger → create_reconciliation_request()
                                    ↓
                          Generate XML Request
                                    ↓
                          Sign & Send to GEPG
                                    ↓
                          Create Reconciliation Record
                                    ↓
                    Wait for GEPG Response (Async)
                                    ↓
                    Receive sucSpPmtRes via Callback
                                    ↓
                    Parse Payment Transactions
                                    ↓
                    Create ReconciliationTransaction Records
                                    ↓
                    Match with Existing Payments
                                    ↓
                    Send Acknowledgment to GEPG
```

---

## Configuration

### Environment Variables

```bash
# Reconciliation Endpoint
GEPG_RECONCILIATION_URL=http://154.118.230.202:80/api/reconciliation/20/request

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

### Service Functions

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py`

#### 1. Create Reconciliation Request

**Function**: `create_reconciliation_request(trx_date=None)`

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:1171-1254`

**Purpose**: Creates and sends a reconciliation request to GEPG

**Parameters**:
- `trx_date`: Date to reconcile (defaults to today if None)

**Returns**: Dictionary with:
- `success`: Boolean indicating success
- `reconciliation_id`: Unique reconciliation request ID
- `message`: Status message

**Code Example**:

```python
from billing_system_app.services import create_reconciliation_request
from datetime import date, timedelta

# Reconcile yesterday's transactions
yesterday = date.today() - timedelta(days=1)
result = create_reconciliation_request(trx_date=yesterday)

if result["success"]:
    print(f"Reconciliation request sent: {result['reconciliation_id']}")
else:
    print(f"Error: {result['message']}")
```

#### 2. Process Reconciliation Response

**Function**: `process_reconciliation_response(xml_content, reconciliation)`

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:1366-1427`

**Purpose**: Processes the reconciliation response from GEPG containing payment list

**Parameters**:
- `xml_content`: XML response from GEPG
- `reconciliation`: Reconciliation object

**Code Example**:

```python
from billing_system_app.services import process_reconciliation_response
from billing_system_app.models import Reconciliation

# Get reconciliation record
reconciliation = Reconciliation.objects.get(recon_id="some-uuid")

# Process response (typically called from callback endpoint)
process_reconciliation_response(xml_content, reconciliation)
```

#### 3. Continuous Reconciliation Service

**Function**: `continuous_reconciliation_service()`

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:1566-1605`

**Purpose**: Automated reconciliation service that can be scheduled

**Code Example**:

```python
from billing_system_app.services import continuous_reconciliation_service

# Run reconciliation
result = continuous_reconciliation_service()

if result["success"]:
    print("Reconciliation initiated successfully")
else:
    print(f"Reconciliation failed: {result['message']}")
```

---

## XML Payload Structure

### Step 1: Request XML (sucSpPmtReq)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <sucSpPmtReq>
        <ReqId>a1b2c3d4-e5f6-7890-abcd-ef1234567890</ReqId>
        <SpGrpCode>SP99631</SpGrpCode>
        <SysCode>LTGC002</SysCode>
        <TrxDt>2025-01-12</TrxDt>
        <Rsv1></Rsv1>
        <Rsv2></Rsv2>
        <Rsv3></Rsv3>
    </sucSpPmtReq>
    <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

### Step 2: Acknowledgment XML (sucSpPmtReqAck)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <sucSpPmtReqAck>
        <AckId>ACK20250113061500</AckId>
        <ReqId>a1b2c3d4-e5f6-7890-abcd-ef1234567890</ReqId>
        <AckStsCode>7101</AckStsCode>
        <AckStsDesc>Successfully</AckStsDesc>
    </sucSpPmtReqAck>
    <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

### Step 3: Response XML (sucSpPmtRes)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <sucSpPmtRes>
        <BatchHdr>
            <ResId>RES20250113061501</ResId>
            <ReqId>a1b2c3d4-e5f6-7890-abcd-ef1234567890</ReqId>
            <PayStsCode>7101</PayStsCode>
            <PayStsDesc>Successful</PayStsDesc>
        </BatchHdr>
        <PmtDtls>
            <PmtTrxDtl>
                <CustCntrNum>255712345678</CustCntrNum>
                <GrpBillId>BILL-S-NO-001-47</GrpBillId>
                <SpCode>SP99631</SpCode>
                <BillId>BILL-S-NO-001-47</BillId>
                <BillCtrNum>9944000001234</BillCtrNum>
                <PspCode>PSP001</PspCode>
                <PspName>M-Pesa</PspName>
                <TrxId>TRX20250112150000</TrxId>
                <PayRefId>REF20250112150000</PayRefId>
                <BillAmt>50000.00</BillAmt>
                <PaidAmt>50000.00</PaidAmt>
                <BillPayOpt>3</BillPayOpt>
                <Ccy>TZS</Ccy>
                <CollAccNum>ACC001</CollAccNum>
                <TrxDtTm>2025-01-12T15:00:00</TrxDtTm>
                <UsdPayChnl>USSD</UsdPayChnl>
                <PyrCellNum>255712345678</PyrCellNum>
                <PyrName>John Doe</PyrName>
                <PyrEmail>john@example.com</PyrEmail>
            </PmtTrxDtl>
            <!-- More payment transactions... -->
        </PmtDtls>
    </sucSpPmtRes>
    <signature>BASE64_ENCODED_SIGNATURE</signature>
</Gepg>
```

### Step 4: Response Acknowledgment XML (sucSpPmtResAck)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <sucSpPmtResAck>
        <AckId>SP20250113061502</AckId>
        <ResId>RES20250113061501</ResId>
        <AckStsCode>7101</AckStsCode>
    </sucSpPmtResAck>
    <signature>SignatureGoesHere</signature>
</Gepg>
```

---

## Database Models

### Reconciliation Model

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/models.py:118-166`

```python
class Reconciliation(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("acknowledged", "Acknowledged"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    # Request fields
    recon_id = models.CharField(max_length=50, unique=True)
    sp_grp_code = models.CharField(max_length=10)
    sys_code = models.CharField(max_length=10)
    trx_dt = models.DateField()

    # Acknowledgment fields
    ack_id = models.CharField(max_length=100, blank=True, null=True)
    ack_sts_code = models.CharField(max_length=100, blank=True, null=True)
    ack_sts_desc = models.CharField(max_length=500, blank=True, null=True)

    # Response fields
    res_id = models.CharField(max_length=100, blank=True, null=True)
    pay_sts_code = models.CharField(max_length=100, blank=True, null=True)
    pay_sts_desc = models.CharField(max_length=500, blank=True, null=True)

    # Status tracking
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    request_date = models.DateTimeField(auto_now_add=True)
    acknowledgment_date = models.DateTimeField(blank=True, null=True)
    response_date = models.DateTimeField(blank=True, null=True)

    # Raw data storage
    request_xml = models.TextField(blank=True, null=True)
    acknowledgment_xml = models.TextField(blank=True, null=True)
    response_xml = models.TextField(blank=True, null=True)

    # Error tracking
    error_message = models.TextField(blank=True, null=True)
    retry_count = models.IntegerField(default=0)
    last_retry = models.DateTimeField(blank=True, null=True)
```

### ReconciliationTransaction Model

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/models.py:169-213`

```python
class ReconciliationTransaction(models.Model):
    """
    Model to store individual transaction details from reconciliation response
    """

    reconciliation = models.ForeignKey(
        Reconciliation, on_delete=models.CASCADE, related_name="transactions"
    )

    # Transaction details from PmtTrxDtl
    cust_cntr_num = models.CharField(max_length=12)
    grp_bill_id = models.CharField(max_length=100)
    sp_code = models.CharField(max_length=10)
    bill_id = models.CharField(max_length=100)
    bill_ctr_num = models.CharField(max_length=12)
    psp_code = models.CharField(max_length=10)
    psp_name = models.CharField(max_length=200)
    trx_id = models.CharField(max_length=100)
    pay_ref_id = models.CharField(max_length=100)
    bill_amount = models.DecimalField(max_digits=32, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=32, decimal_places=2)
    bill_pay_opt = models.CharField(max_length=10)
    currency = models.CharField(max_length=3)
    coll_acc_num = models.CharField(max_length=50)
    trx_dt_tm = models.DateTimeField()
    usd_pay_chnl = models.CharField(max_length=50)

    # Optional fields
    pyr_cell_num = models.CharField(max_length=15, blank=True, null=True)
    pyr_email = models.CharField(max_length=150, blank=True, null=True)
    pyr_name = models.CharField(max_length=200, blank=True, null=True)

    # Link to our Payment model if exists
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reconciliation_transactions",
    )

    created_at = models.DateTimeField(auto_now_add=True)
```

---

## Key Features

### 1. Automatic Request ID Generation

Uses UUID for unique reconciliation request IDs:

```python
import uuid

req_id = str(uuid.uuid4())
```

### 2. Transaction Date Handling

Defaults to today's date if not specified:

```python
if trx_date is None:
    trx_date = date.today()
```

### 3. Payment Matching

Links reconciliation transactions to existing payment records:

```python
payment = None
try:
    payment = Payment.objects.filter(trx_id=trx_id).first()
except:
    pass

transaction = ReconciliationTransaction.objects.create(
    # ... other fields ...
    payment=payment
)
```

### 4. Status Tracking

Tracks reconciliation status through multiple stages:
- **pending**: Request sent, waiting for acknowledgment
- **acknowledged**: Acknowledgment received, waiting for response
- **completed**: Response received and processed
- **failed**: Error occurred at any stage

### 5. Debug Logging

All reconciliation requests and responses are logged to `/tmp/gepg_reconciliation_debug.xml`

---

## Status Codes

### Success Codes
- **7101**: Successfully processed

### Error Codes
- **7102**: Processing failed
- **7201**: Invalid request format
- **7202**: Invalid transaction date
- **7203**: No transactions found for date

---

## Implementation Details

### Complete Request Function

```python
def create_reconciliation_request(trx_date=None):
    """
    Create and send reconciliation request to GePG
    """
    try:
        import logging
        import uuid
        from datetime import date, timedelta
        from .models import Reconciliation

        logger = logging.getLogger(__name__)

        # Use settings from .env
        sp_grp_code = settings.GEPG_SP_GRP_CODE
        sys_code = settings.GEPG_SYS_CODE

        # Generate unique request ID
        req_id = str(uuid.uuid4())

        # Use provided date or default to today
        if trx_date is None:
            trx_date = date.today()

        # Create reconciliation request XML
        xml_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
<Gepg>
    <sucSpPmtReq>
        <ReqId>{req_id}</ReqId>
        <SpGrpCode>{sp_grp_code}</SpGrpCode>
        <SysCode>{sys_code}</SysCode>
        <TrxDt>{trx_date.strftime("%Y-%m-%d")}</TrxDt>
        <Rsv1></Rsv1>
        <Rsv2></Rsv2>
        <Rsv3></Rsv3>
    </sucSpPmtReq>
    <signature>SignatureGoesHere</signature>
</Gepg>"""

        # Sign the XML payload if digital signatures are enabled
        xml_payload = _sign_xml_if_enabled(xml_payload)

        # Create reconciliation record in database
        reconciliation = Reconciliation.objects.create(
            recon_id=req_id,
            sp_grp_code=sp_grp_code,
            sys_code=sys_code,
            trx_dt=trx_date,
            request_xml=xml_payload,
            status="pending",
        )

        # Send request to GePG
        response = send_reconciliation_request_to_gepg(xml_payload)

        if response.status_code == 200:
            # Parse acknowledgment
            process_reconciliation_acknowledgment(response.content, reconciliation)
            return {
                "success": True,
                "reconciliation_id": req_id,
                "message": "Reconciliation request sent successfully",
            }
        else:
            reconciliation.status = "failed"
            reconciliation.error_message = f"GePG API Error: {response.status_code}"
            reconciliation.save()
            return {
                "success": False,
                "message": f"Failed to send reconciliation request: {response.status_code}",
            }

    except Exception as e:
        return {"success": False, "message": str(e)}
```

---

## Testing

### Manual Testing

```python
from billing_system_app.services import create_reconciliation_request
from datetime import date, timedelta

# Test reconciliation for yesterday
yesterday = date.today() - timedelta(days=1)
result = create_reconciliation_request(trx_date=yesterday)

print(f"Success: {result['success']}")
print(f"Message: {result['message']}")
if result["success"]:
    print(f"Reconciliation ID: {result['reconciliation_id']}")
```

### Verify Database Records

```python
from billing_system_app.models import Reconciliation, ReconciliationTransaction

# Get reconciliation record
recon = Reconciliation.objects.latest("request_date")
print(f"Status: {recon.status}")
print(f"Transaction Date: {recon.trx_dt}")
print(f"Acknowledgment: {recon.ack_sts_code} - {recon.ack_sts_desc}")

# Get transactions
transactions = ReconciliationTransaction.objects.filter(reconciliation=recon)
print(f"Transactions found: {transactions.count()}")

for txn in transactions:
    print(f"  - {txn.trx_id}: {txn.bill_id} - {txn.paid_amount}")
```

### Check Payment Matching

```python
from billing_system_app.models import ReconciliationTransaction, Payment

# Find transactions with matched payments
matched = ReconciliationTransaction.objects.filter(payment__isnull=False)
print(f"Matched transactions: {matched.count()}")

# Find transactions without matched payments
unmatched = ReconciliationTransaction.objects.filter(payment__isnull=True)
print(f"Unmatched transactions: {unmatched.count()}")

for txn in unmatched:
    print(f"  - {txn.trx_id}: {txn.bill_id}")
```

---

## Common Use Cases

### 1. Daily Reconciliation

```python
from billing_system_app.services import continuous_reconciliation_service

# Run daily reconciliation (typically via cron job)
result = continuous_reconciliation_service()
```

### 2. Manual Reconciliation for Specific Date

```python
from billing_system_app.services import create_reconciliation_request
from datetime import date

# Reconcile specific date
specific_date = date(2025, 1, 10)
result = create_reconciliation_request(trx_date=specific_date)
```

### 3. Reconciliation Report

```python
from billing_system_app.models import Reconciliation, ReconciliationTransaction
from django.db.models import Sum, Count

# Get reconciliation summary
recon = Reconciliation.objects.get(recon_id="some-uuid")

summary = {
    "status": recon.status,
    "transaction_date": recon.trx_dt,
    "total_transactions": recon.transactions.count(),
    "total_amount": recon.transactions.aggregate(Sum("paid_amount"))["paid_amount__sum"],
    "matched_payments": recon.transactions.filter(payment__isnull=False).count(),
    "unmatched_payments": recon.transactions.filter(payment__isnull=True).count(),
}

print(summary)
```

### 4. Retry Failed Reconciliation

```python
from billing_system_app.models import Reconciliation

# Find failed reconciliations
failed = Reconciliation.objects.filter(status="failed")

for recon in failed:
    # Retry reconciliation
    result = create_reconciliation_request(trx_date=recon.trx_dt)
    if result["success"]:
        print(f"Retry successful for {recon.trx_dt}")
    else:
        print(f"Retry failed for {recon.trx_dt}: {result['message']}")
```

---

## Troubleshooting

### Issue: No transactions in reconciliation response

**Cause**: No payments made on the specified date

**Solution**: 
1. Verify the transaction date is correct
2. Check if any payments were made on that date
3. Try reconciling a different date with known payments

### Issue: Reconciliation stuck in "pending" status

**Cause**: Acknowledgment not received from GEPG

**Solution**:
1. Check GEPG API connectivity
2. Verify request was sent successfully
3. Check debug logs in `/tmp/gepg_reconciliation_debug.xml`
4. Retry the reconciliation request

### Issue: Transactions not matching with payments

**Cause**: Transaction IDs don't match between systems

**Solution**:
1. Check if payment records exist: `Payment.objects.filter(trx_id='...')`
2. Verify transaction ID format is consistent
3. Check for typos or formatting differences
4. Review payment notification logs

### Issue: Reconciliation response not received

**Cause**: Callback URL not accessible or not configured

**Solution**:
1. Verify callback URL is accessible from GEPG
2. Check firewall settings
3. Ensure endpoint is properly configured
4. Monitor server logs for incoming requests

---

## Best Practices

1. **Run reconciliation daily** - Automate daily reconciliation for previous day's transactions
2. **Monitor reconciliation status** - Set up alerts for failed reconciliations
3. **Review unmatched transactions** - Investigate transactions that don't match existing payments
4. **Keep audit trail** - Store all XML requests and responses for compliance
5. **Handle errors gracefully** - Implement retry logic for failed reconciliations
6. **Validate transaction dates** - Ensure dates are in correct format and within valid range
7. **Match payments accurately** - Use transaction IDs to link reconciliation data with payment records
8. **Generate reports** - Create regular reconciliation reports for accounting

---

## Scheduling Reconciliation

### Using Django Management Command

Create a management command for scheduled reconciliation:

```python
# billing_system_app/management/commands/reconcile_payments.py
from django.core.management.base import BaseCommand
from billing_system_app.services import continuous_reconciliation_service


class Command(BaseCommand):
    help = "Run daily payment reconciliation with GEPG"

    def handle(self, *args, **options):
        self.stdout.write("Starting reconciliation...")
        result = continuous_reconciliation_service()

        if result["success"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reconciliation completed: {result['reconciliation_id']}"
                )
            )
        else:
            self.stdout.write(
                self.style.ERROR(f"Reconciliation failed: {result['message']}")
            )
```

### Cron Job Setup

```bash
# Run reconciliation daily at 2 AM
0 2 * * * cd /home/tgc_mifumo/tgc_mifumo && python manage.py reconcile_payments
```

---

## Related Documentation

- [Payment Notification](02_PAYMENT_NOTIFICATION.md)
- [Bill Submission](01_BILL_SUBMISSION.md)
- [Database Models](../../apps/billing/models/bill.py)

---

**Last Updated**: January 2026  
**Version**: 1.0
