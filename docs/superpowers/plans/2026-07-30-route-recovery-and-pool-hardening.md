# Route recovery and pool hardening implementation plan

## Goal

Allow administrators to manually recover automatically unhealthy model routes, keep at least one usable supplier route available for every model, and eliminate confirmed avoidable database connection retention during provider model discovery.

## Tasks

1. Add route-health integration tests for the multi-route last-resort policy and concurrent failures. Preserve the existing single-route guarantee.
2. Implement deterministic model-route locking and reset all eligible routes when opening the final usable route would leave the model unavailable.
3. Add an authenticated `POST /admin/model-routes/{route_id}/recover` endpoint with integration coverage.
4. Add the recovery action to the models admin UI with API, state-race, success, and error tests.
5. Add pool-size-one model-discovery regression tests, then release the ORM connection before waiting on upstream discovery I/O by using an immutable discovery snapshot.
6. Add a request-cancellation pool regression around the HTTP middleware. Replace decorator middleware with pure ASGI middleware only if the regression reproduces a retained connection.
7. Run backend and frontend checks in CI order, then report confirmed causes separately from lower-probability thread/HTTP pool risks.
