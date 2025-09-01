# Billing API Endpoints

This directory contains the billing-related API endpoints that can be accessed using API keys.

## Endpoints

### GET /api/v1/dashboard/billing/subscription

Returns the user's subscription information including:
- User ID
- Email
- Plan type
- Subscription status
- Current period end date
- Account balance
- Account creation date

### GET /api/v1/dashboard/billing/usage

Returns the API key usage statistics including:
- Total token usage (prompt, completion, and total)
- Total cost
- Daily usage for the last 30 days (tokens and cost)
- Usage by model (tokens and cost)

## Authentication

Both endpoints require authentication via API key in the Authorization header:
```
Authorization: Bearer <api_key>
```

## Response Format

All responses are in JSON format.