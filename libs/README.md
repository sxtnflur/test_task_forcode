# Local libraries

Local implementations of the internal GitLab libraries the service depends on
(`utils`, `gate_lib`, `cds_client`, `sbank_client`). They keep the original import paths,
so the gate code does not know whether it runs on these or on the real packages.
To switch back to the real ones, replace the `path` dependencies in the root
`pyproject.toml` with the `git` ones and run `poetry lock`.

| Package        | Contents                                                                                          |
|----------------|---------------------------------------------------------------------------------------------------|
| `gate_lib`     | Gate protocol v2: statuses, request/response models, endpoint builders, validation error handler |
| `utils`        | structlog setup, PAN/CVC masking, logging httpx client, TraceID and logging ASGI middleware       |
| `cds_client`   | `CardData` model and Card Data Storage client                                                     |
| `sbank_client` | Processing (Sbank) API client: invoices, withdrawals, terminals                                   |

## Protocol decisions

- **Invalid request** → HTTP 422 with `code=validation_error` and the list of invalid fields.
  There is no `status` in the body: an invalid request is not a failed operation.
  Input values are not echoed back, so card data cannot leak through errors.
- **The gate raised an exception or returned an invalid response** → the endpoint logs it
  and still answers with a protocol response, `code=internal_error`:
  - `sale`, `p2p_selector_sale` → `failed`: the payer has not been sent anywhere, no money moved;
  - `status`, `refund`, `refund_status`, `withdrawal`, `withdrawal_status`, `sale_confirm` →
    `pending`: money may have moved, the outcome is resolved by a later status check.
- **Card data** for `sale`/`withdrawal` is fetched from CDS by `card_token`
  (`CDS_URL`/`CDS_AUTH_TOKEN` env vars). `sale` without a token goes to `sale_without_card`.

## Tests

```bash
pytest libs
```
