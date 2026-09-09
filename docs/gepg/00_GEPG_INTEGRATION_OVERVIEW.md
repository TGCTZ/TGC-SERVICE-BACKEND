# GEPG Integration - Overview & Index

> Ported from the previous system. Real credentials have been redacted to
> `<set-in-.env>`; set the actual values in `.env` (see `.env.example`). Some
> file paths in these docs refer to the previous codebase — in TGC-SYSTEM the
> GePG code lives in `apps/billing/` (gateway in `apps/billing/gateways/`).

## Table of Contents

This documentation suite provides comprehensive information about the TGC Mifumo GEPG (Government Electronic Payment Gateway) integration.

### Documentation Files

1. **[Bill Submission](01_BILL_SUBMISSION.md)** - Creating and submitting bills to GEPG
2. **[Payment Notification](02_PAYMENT_NOTIFICATION.md)** - Receiving and processing payment notifications from GEPG
3. **[Bill Cancellation](03_BILL_CANCELLATION.md)** - Cancelling bills in GEPG
4. **[Reconciliation](04_RECONCILIATION.md)** - Reconciling payments with GEPG
5. **[SMS Integration](05_SMS_INTEGRATION.md)** - SMS notifications via Beem Africa

---

## System Architecture

```
TGC Mifumo System ←→ GEPG (Government Payment Gateway)
     ↓                    ↓
Identification Services  Production Shop Orders
     ↓                    ↓
   Billing System ←→ Payment Processing
                         ↓
                   SMS Notifications
```

---

## Configuration Overview

### Environment Variables

The GEPG integration is configured via environment variables in `.env`:

#### GEPG API Endpoints
- `GEPG_BILL_CREATE_URL`: http://154.118.230.202:80/api/bill/20/submission
- `GEPG_BILL_UPDATE_URL`: http://154.118.230.202:80/api/bill/20/change-submission
- `GEPG_BILL_CANCEL_URL`: http://154.118.230.202:80/api/bill/20/cancellation
- `GEPG_RECONCILIATION_URL`: http://154.118.230.202:80/api/reconciliation/20/request

#### GEPG Service Provider Configuration
- `GEPG_SP_GRP_CODE`: SP99631
- `GEPG_SYS_CODE`: LTGC002
- `GEPG_SP_CODE`: SP99631
- `GEPG_SUB_SP_CODE`: 1001
- `GEPG_COLL_CENT_CODE`: CC1014000199631
- `GEPG_GFS_CODE`: 142201660128

#### Security Settings
- `GEPG_USE_DIGITAL_SIGNATURE`: True
- `GEPG_CERTIFICATE_PASSWORD`: <set-in-.env>

#### SMS Configuration (Beem Africa)
- `BEEM_AFRICA_API_KEY`: <set-in-.env>
- `BEEM_AFRICA_SECRET_KEY`: [Base64 encoded]

---

## Core Components

### 1. Models (`billing_app/models.py`)
- **Bill**: Main billing entity with GEPG integration
- **BillItem**: Individual line items for bills
- **Payment**: Payment records from GEPG
- **ReconciliationRequest**: Reconciliation tracking

### 2. Services (`billing_app/services/`)
- **gepg_service.py**: Core GEPG API integration
- **crypto_utils.py**: Digital signature and encryption
- **sms_service.py**: SMS notification handling

### 3. API Views (`billing_app/views.py`)
- Payment notification endpoint
- Bill management endpoints
- Reconciliation endpoints

### 4. URL Configuration (`billing_app/urls.py`)
- API routing for GEPG callbacks
- Internal API endpoints

---

## Integration Flow

### Outbound (TGC → GEPG)
1. **Bill Creation**: System generates bill → Signs XML → Sends to GEPG
2. **Bill Update**: Modify existing bill → Signs XML → Sends to GEPG
3. **Bill Cancellation**: Cancel bill → Signs XML → Sends to GEPG
4. **Reconciliation Request**: Request payment data → Signs XML → Sends to GEPG

### Inbound (GEPG → TGC)
1. **Payment Notification**: GEPG sends payment → System verifies → Updates bill → Sends SMS
2. **Reconciliation Response**: GEPG sends payment list → System processes → Updates records

---

## Security Features

### Digital Signatures
- All outbound requests are digitally signed using PKCS#12 certificates
- Signatures ensure message integrity and authenticity
- Certificate password protected

### XML Encryption
- Sensitive data encrypted in XML payloads
- AES encryption for data protection

### Authentication
- CSRF exemption for GEPG callbacks (external system)
- Internal endpoints protected by Django authentication

---

## Key Features

### ✅ Bill Management
- Create bills for identification services
- Create bills for production shop orders
- Update bill amounts and details
- Cancel bills when needed
- Automatic control number generation

### ✅ Payment Processing
- Real-time payment notifications from GEPG
- Automatic bill status updates
- Payment verification and validation
- Duplicate payment prevention

### ✅ Reconciliation
- Manual reconciliation requests
- Automatic payment matching
- Discrepancy detection
- Audit trail maintenance

### ✅ SMS Notifications
- Payment confirmation SMS
- Bill generation notifications
- Custom message templates
- Beem Africa integration

---

## Database Schema

### Bill Table
- `bill_id`: Unique identifier (e.g., BILL-S-NO-001-47)
- `control_number`: GEPG control number
- `amount`: Bill amount
- `status`: PENDING, PAID, CANCELLED, EXPIRED
- `bill_type`: IDENTIFICATION, PRODUCTION_SHOP
- `is_gepg_submitted`: Boolean flag
- `gepg_submission_date`: Timestamp

### Payment Table
- `payment_id`: Unique identifier
- `bill`: Foreign key to Bill
- `transaction_id`: GEPG transaction ID
- `amount`: Payment amount
- `payment_date`: Payment timestamp
- `payer_phone`: Customer phone number
- `payer_name`: Customer name

---

## Error Handling

### Common Scenarios
1. **Network Failures**: Retry mechanism with exponential backoff
2. **Invalid Signatures**: Logging and notification
3. **Duplicate Payments**: Detection and prevention
4. **Bill Not Found**: Graceful error responses
5. **GEPG API Errors**: Detailed error logging

---

## Monitoring & Logging

### Log Locations
- Application logs: Django logging framework
- GEPG request/response logs: Detailed XML logging
- Payment notifications: Timestamped records
- Error logs: Exception tracking

### Key Metrics
- Bill submission success rate
- Payment notification processing time
- Reconciliation accuracy
- SMS delivery rate

---

## Testing

### Test Scenarios
1. Bill creation and submission
2. Payment notification processing
3. Bill cancellation
4. Reconciliation requests
5. SMS delivery
6. Error handling

### Test Data
- Use test GEPG environment
- Test control numbers
- Mock payment notifications
- Sample XML payloads

---

## Deployment Considerations

### Prerequisites
- PostgreSQL database
- PKCS#12 certificate file
- GEPG API access credentials
- Beem Africa SMS credentials
- Python 3.x with Django

### Configuration Steps
1. Set up environment variables
2. Install certificate
3. Configure database
4. Run migrations
5. Test GEPG connectivity
6. Verify SMS integration

---

## Support & Maintenance

### Regular Tasks
- Monitor payment notifications
- Review reconciliation reports
- Update certificates before expiry
- Check SMS delivery status
- Review error logs

### Troubleshooting
- Check GEPG API connectivity
- Verify certificate validity
- Review XML signatures
- Check database connections
- Validate environment variables

---

## Next Steps

For detailed information about each feature, please refer to the specific documentation files listed at the top of this document.

---

**Last Updated**: January 2026  
**Version**: 1.0  
**Maintained By**: TGC Mifumo Development Team
