# GEPG Integration - SMS Notifications

## Overview

SMS integration provides automated customer notifications for bill creation and payment confirmations. The system uses **Beem Africa SMS API** to send SMS messages to customers.

---

## Architecture

### Flow Diagram

```
Bill Created → Control Number Received → send_payment_sms() → Beem Africa API → Customer Phone
                                                                      ↓
                                                              SMS Delivery Status
                                                                      ↓
                                                              Log to Debug File
```

---

## Configuration

### Environment Variables

```bash
# Beem Africa SMS API Configuration
BEEM_AFRICA_API_KEY=<set-in-.env>
BEEM_AFRICA_SECRET_KEY=<set-in-.env>
```

### API Endpoint

**URL**: `https://apisms.beem.africa/v1/send`

**Method**: POST

**Authentication**: Basic Auth (Base64 encoded API Key:Secret Key)

**Content-Type**: application/json

---

## Implementation

### Service Functions

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py`

#### 1. Send Payment SMS

**Function**: `send_payment_sms(phone_number, amount, control_number)`

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:66-154`

**Purpose**: Sends SMS notification with payment instructions

**Parameters**:
- `phone_number`: Customer phone number (international format)
- `amount`: Payment amount (Decimal)
- `control_number`: GEPG control number for payment

**Returns**: Boolean (True if SMS sent successfully, False otherwise)

**Code Example**:

```python
from billing_system_app.services import send_payment_sms
from decimal import Decimal

# Send SMS
success = send_payment_sms(
    phone_number="255712345678",
    amount=Decimal("50000.00"),
    control_number="9944000001234",
)

if success:
    print("SMS sent successfully")
else:
    print("Failed to send SMS")
```

#### 2. Send SMS for Bill

**Function**: `send_payment_sms_for_bill(bill)`

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:157-184`

**Purpose**: Sends SMS for an existing bill with control number

**Parameters**:
- `bill`: Bill object

**Returns**: Boolean (True if SMS sent successfully, False otherwise)

**Code Example**:

```python
from billing_system_app.services import send_payment_sms_for_bill
from billing_system_app.models import Bill

# Get bill
bill = Bill.objects.get(bill_id="BILL-S-NO-001-47")

# Send SMS
success = send_payment_sms_for_bill(bill)

if success:
    print(f"SMS sent to {bill.customer_phone}")
else:
    print("Failed to send SMS")
```

---

## Complete Implementation

### SMS Sending Function

```python
def send_payment_sms(phone_number: str, amount: Decimal, control_number: str) -> bool:
    """
    Send SMS notification to user with payment instructions using Beem Africa API.

    Args:
        phone_number: The phone number to send SMS to (should be in international format)
        amount: The amount to be paid
        control_number: The GePG control number for payment

    Returns:
        bool: True if SMS was sent successfully, False otherwise
    """
    try:
        # SMS API Configuration
        api_key = getattr(settings, "BEEM_AFRICA_API_KEY", "<set-in-.env>")
        secret_key = getattr(settings, "BEEM_AFRICA_SECRET_KEY", "<set-in-.env>")

        # Normalize phone number to ensure it's in correct format
        normalized_phone = _normalize_msisdn_tz(phone_number)
        if not normalized_phone:
            print(f"Invalid phone number for SMS: {phone_number}")
            return False

        # Format amount with commas
        formatted_amount = f"{amount:,.0f}"

        # Create message
        message = f"Pay TZS {formatted_amount} to the control number {control_number}"

        # Prepare API request
        url = "https://apisms.beem.africa/v1/send"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {base64.b64encode(f'{api_key}:{secret_key}'.encode()).decode()}",
        }

        payload = {
            "source_addr": "TGC-INFO",
            "schedule_time": "",
            "encoding": 0,
            "message": message,
            "recipients": [{"recipient_id": 1, "dest_addr": normalized_phone}],
        }

        # Send SMS
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        # Log SMS attempt to file
        try:
            with open("/tmp/sms_debug.xml", "a") as sms_file:
                sms_file.write(f"=== SMS Attempt at {now()} ===\n")
                sms_file.write(f"Phone: {normalized_phone}\n")
                sms_file.write(f"Message: {message}\n")
                sms_file.write(f"Status Code: {response.status_code}\n")
                sms_file.write(f"Response: {response.text}\n")
                if response.status_code == 200:
                    sms_file.write("✅ SUCCESS\n")
                else:
                    sms_file.write("❌ FAILED\n")
                sms_file.write("\n")
        except Exception as log_error:
            pass

        if response.status_code == 200:
            print(f"✅ SMS sent successfully to {normalized_phone}: {message}")
            return True
        else:
            print(
                f"❌ Failed to send SMS to {normalized_phone}. Status: {response.status_code}, Response: {response.text}"
            )
            return False

    except Exception as e:
        # Log error to file
        try:
            with open("/tmp/sms_debug.xml", "a") as sms_file:
                sms_file.write(f"=== SMS Error at {now()} ===\n")
                sms_file.write(f"Phone: {phone_number}\n")
                sms_file.write(f"Error: {str(e)}\n")
                sms_file.write("❌ ERROR\n\n")
        except Exception as log_error:
            pass

        print(f"❌ Error sending SMS to {phone_number}: {str(e)}")
        return False
```

---

## Message Format

### Payment Instruction Message

```
Pay TZS 50,000 to the control number 9944000001234
```

**Components**:
- **Currency**: TZS (Tanzanian Shillings)
- **Amount**: Formatted with commas (e.g., 50,000)
- **Control Number**: GEPG control number for payment

---

## Phone Number Normalization

### Normalization Function

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:29-41`

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

### Examples

| Input | Output |
|-------|--------|
| `0712345678` | `255712345678` |
| `712345678` | `255712345678` |
| `255712345678` | `255712345678` |
| `+255712345678` | `255712345678` |

---

## API Request Structure

### Request Payload

```json
{
    "source_addr": "TGC-INFO",
    "schedule_time": "",
    "encoding": 0,
    "message": "Pay TZS 50,000 to the control number 9944000001234",
    "recipients": [
        {
            "recipient_id": 1,
            "dest_addr": "255712345678"
        }
    ]
}
```

### Request Headers

```json
{
    "Content-Type": "application/json",
    "Authorization": "Basic BASE64_ENCODED_CREDENTIALS"
}
```

**Authorization**: Base64 encoded `api_key:secret_key`

---

## Response Handling

### Success Response

**Status Code**: 200

**Response Body**:
```json
{
    "successful": true,
    "request_id": "12345678",
    "code": 100,
    "message": "Message sent successfully"
}
```

### Error Response

**Status Code**: 400, 401, 500, etc.

**Response Body**:
```json
{
    "successful": false,
    "code": 401,
    "message": "Invalid credentials"
}
```

---

## Integration Points

### 1. Bill Creation (Identification Services)

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:792-797`

```python
# Send SMS notification to customer with payment instructions
sms_sent = send_payment_sms(customer_phone, billing_bill.bill_amount, control_number)
if sms_sent:
    print(f"📱 SMS notification sent to {customer_phone} for bill {gepg_bill_id}")
else:
    print(
        f"⚠️ Failed to send SMS notification to {customer_phone} for bill {gepg_bill_id}"
    )
```

### 2. Bill Creation (Production Shop)

Location: `@/home/tgc_mifumo/tgc_mifumo/billing_system_app/services.py:1094-1099`

```python
# Send SMS notification to customer with payment instructions
sms_sent = send_payment_sms(customer_phone, billing_bill.bill_amount, control_number)
if sms_sent:
    print(
        f"📱 SMS notification sent to {customer_phone} for production bill {gepg_bill_id}"
    )
else:
    print(
        f"⚠️ Failed to send SMS notification to {customer_phone} for production bill {gepg_bill_id}"
    )
```

### 3. Asynchronous Bill Response

When control number is received via callback, SMS can be sent:

```python
# After updating bill with control number
if bill.control_number and bill.control_number != "PENDING":
    send_payment_sms_for_bill(bill)
```

---

## Logging

### Debug Log File

**Location**: `/tmp/sms_debug.xml`

**Format**:
```
=== SMS Attempt at 2025-01-13 06:15:00 ===
Phone: 255712345678
Message: Pay TZS 50,000 to the control number 9944000001234
Status Code: 200
Response: {"successful":true,"request_id":"12345678"}
✅ SUCCESS

=== SMS Error at 2025-01-13 06:16:00 ===
Phone: 0712345678
Error: Connection timeout
❌ ERROR
```

### Console Output

**Success**:
```
✅ SMS sent successfully to 255712345678: Pay TZS 50,000 to the control number 9944000001234
```

**Failure**:
```
❌ Failed to send SMS to 255712345678. Status: 401, Response: {"error":"Invalid credentials"}
```

---

## Error Handling

### Invalid Phone Number

```python
normalized_phone = _normalize_msisdn_tz(phone_number)
if not normalized_phone:
    print(f"Invalid phone number for SMS: {phone_number}")
    return False
```

### Network Errors

```python
try:
    response = requests.post(url, json=payload, headers=headers, timeout=30)
except Exception as e:
    print(f"❌ Error sending SMS to {phone_number}: {str(e)}")
    return False
```

### API Errors

```python
if response.status_code == 200:
    return True
else:
    print(
        f"❌ Failed to send SMS. Status: {response.status_code}, Response: {response.text}"
    )
    return False
```

### Logging Errors

```python
try:
    with open("/tmp/sms_debug.xml", "a") as sms_file:
        # Log SMS attempt
        pass
except Exception as log_error:
    # Don't let logging failure break SMS sending
    pass
```

---

## Testing

### Manual Testing

```python
from billing_system_app.services import send_payment_sms
from decimal import Decimal

# Test SMS sending
success = send_payment_sms(
    phone_number="255712345678",
    amount=Decimal("50000.00"),
    control_number="9944000001234",
)

print(f"SMS sent: {success}")
```

### Test with Different Phone Formats

```python
test_numbers = [
    "0712345678",
    "712345678",
    "255712345678",
    "+255712345678",
]

for number in test_numbers:
    success = send_payment_sms(number, Decimal("1000.00"), "TEST123")
    print(f"{number} -> {success}")
```

### Check Debug Log

```bash
tail -f /tmp/sms_debug.xml
```

---

## Common Use Cases

### 1. Send SMS After Bill Creation

```python
from billing_system_app.services import (
    create_external_bill_for_identification,
    send_payment_sms,
)
from gemmology_app.models import ItemTB

# Create bill
item = ItemTB.objects.get(id=96)
result = create_external_bill_for_identification(item)

# SMS is automatically sent if control number is available
# Manual send if needed:
if result["control_number"] != "PENDING":
    send_payment_sms(
        phone_number=item.order_no.phone_number,
        amount=result["bill_amount"],
        control_number=result["control_number"],
    )
```

### 2. Resend SMS for Existing Bill

```python
from billing_system_app.services import send_payment_sms_for_bill
from billing_system_app.models import Bill

# Get bill
bill = Bill.objects.get(bill_id="BILL-S-NO-001-47")

# Resend SMS
if bill.control_number and bill.control_number != "PENDING":
    success = send_payment_sms_for_bill(bill)
    if success:
        print("SMS resent successfully")
```

### 3. Bulk SMS for Unpaid Bills

```python
from billing_system_app.services import send_payment_sms_for_bill
from billing_system_app.models import Bill

# Find unpaid bills with control numbers
unpaid_bills = Bill.objects.filter(
    status_code__in=["7101", "7241"], control_number__isnull=False
).exclude(control_number="PENDING")

# Send reminder SMS
for bill in unpaid_bills:
    success = send_payment_sms_for_bill(bill)
    if success:
        print(f"Reminder sent for {bill.bill_id}")
```

### 4. Custom SMS Message

```python
from billing_system_app.services import _normalize_msisdn_tz
import requests
import base64
from django.conf import settings


def send_custom_sms(phone_number, message):
    """Send custom SMS message"""
    api_key = settings.BEEM_AFRICA_API_KEY
    secret_key = settings.BEEM_AFRICA_SECRET_KEY

    normalized_phone = _normalize_msisdn_tz(phone_number)

    url = "https://apisms.beem.africa/v1/send"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {base64.b64encode(f'{api_key}:{secret_key}'.encode()).decode()}",
    }

    payload = {
        "source_addr": "TGC-INFO",
        "message": message,
        "recipients": [{"recipient_id": 1, "dest_addr": normalized_phone}],
    }

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    return response.status_code == 200


# Usage
send_custom_sms("255712345678", "Your payment has been received. Thank you!")
```

---

## Troubleshooting

### Issue: SMS not delivered

**Possible Causes**:
1. Invalid phone number
2. Network connectivity issues
3. Invalid API credentials
4. Insufficient SMS credits

**Solutions**:
1. Verify phone number format (should start with 255)
2. Check internet connectivity
3. Verify API key and secret key in `.env`
4. Check Beem Africa account balance
5. Review debug log: `/tmp/sms_debug.xml`

### Issue: Phone number normalization fails

**Cause**: Invalid phone number format

**Solution**:
```python
from billing_system_app.services import _normalize_msisdn_tz

# Test normalization
phone = "0712345678"
normalized = _normalize_msisdn_tz(phone)
print(f"Original: {phone}, Normalized: {normalized}")
```

### Issue: API returns 401 Unauthorized

**Cause**: Invalid API credentials

**Solution**:
1. Verify `BEEM_AFRICA_API_KEY` in `.env`
2. Verify `BEEM_AFRICA_SECRET_KEY` in `.env`
3. Check credentials in Beem Africa dashboard
4. Ensure Base64 encoding is correct

### Issue: SMS sent but not received

**Cause**: Phone number not active or network issues

**Solution**:
1. Verify phone number is active
2. Check network coverage
3. Try sending to different number
4. Check Beem Africa delivery reports

---

## Best Practices

1. **Always normalize phone numbers** - Use `_normalize_msisdn_tz()` before sending
2. **Handle errors gracefully** - Don't let SMS failures break bill creation
3. **Log all SMS attempts** - Keep audit trail in debug file
4. **Validate phone numbers** - Check format before sending
5. **Use clear messages** - Keep SMS concise and informative
6. **Monitor delivery rates** - Track success/failure rates
7. **Set appropriate timeouts** - Use 30-second timeout for API calls
8. **Secure credentials** - Store API keys in environment variables
9. **Test thoroughly** - Test with various phone number formats
10. **Handle rate limits** - Implement retry logic if needed

---

## Security Considerations

### 1. Credential Storage

Store API credentials in environment variables, never in code:

```python
api_key = getattr(settings, "BEEM_AFRICA_API_KEY")
secret_key = getattr(settings, "BEEM_AFRICA_SECRET_KEY")
```

### 2. Phone Number Privacy

Don't log full phone numbers in production logs:

```python
# Mask phone number in logs
masked_phone = phone_number[:3] + "****" + phone_number[-3:]
logger.info(f"SMS sent to {masked_phone}")
```

### 3. Message Content

Avoid including sensitive information in SMS messages:
- ✅ Control numbers (public)
- ✅ Amounts (necessary)
- ❌ Customer IDs
- ❌ Personal information
- ❌ Account details

---

## Monitoring & Analytics

### SMS Delivery Metrics

```python
from billing_system_app.models import Bill
from django.db.models import Count, Q
from datetime import date, timedelta

# Get bills created today
today = date.today()
bills_today = Bill.objects.filter(bill_generated_date__date=today)

# Count bills with control numbers (SMS should be sent)
bills_with_control = bills_today.exclude(
    Q(control_number__isnull=True) | Q(control_number="PENDING")
)

print(f"Bills created today: {bills_today.count()}")
print(f"Bills with control numbers: {bills_with_control.count()}")
print(f"SMS delivery rate: {bills_with_control.count() / bills_today.count() * 100:.2f}%")
```

### Parse Debug Log

```python
import re


def parse_sms_log(log_file="/tmp/sms_debug.xml"):
    """Parse SMS debug log and return statistics"""
    with open(log_file, "r") as f:
        content = f.read()

    success_count = content.count("✅ SUCCESS")
    failed_count = content.count("❌ FAILED")
    error_count = content.count("❌ ERROR")

    return {
        "success": success_count,
        "failed": failed_count,
        "error": error_count,
        "total": success_count + failed_count + error_count,
        "success_rate": success_count / (success_count + failed_count + error_count) * 100
        if (success_count + failed_count + error_count) > 0
        else 0,
    }


# Usage
stats = parse_sms_log()
print(f"SMS Statistics: {stats}")
```

---

## Related Documentation

- [Bill Submission](01_BILL_SUBMISSION.md)
- [Payment Notification](02_PAYMENT_NOTIFICATION.md)
- [Beem Africa API Documentation](https://apidocs.beem.africa/)

---

**Last Updated**: January 2026  
**Version**: 1.0
