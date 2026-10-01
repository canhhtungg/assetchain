# AssetChain backend authentication

The browser authenticates through `POST /api/auth/login`; it no longer receives
ChainLaunch credentials. Configure the backend with:

- `FABRIC_USERNAME` and `FABRIC_PASSWORD`: ChainLaunch service credentials.
- `APP_SECRET`: a random application secret used to sign login sessions.
- `AUTH_TOKEN_MAX_AGE`: session lifetime in seconds (defaults to 8 hours).
- `AUTH_CREDENTIALS_FILE`: optional JSON file containing password hashes for
  users that already existed before password credentials were added to the
  chaincode.

Copy `.env.example` to an untracked `.env`, then fill it locally. Do not commit
these values. Generate an application secret with
`./venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(48))'` and
place it in the runtime environment or `.env`.

## Existing users

After upgrading the chaincode, existing seeded users do not have a password.
Create an untracked fallback credential file without putting plaintext
passwords on the command line:

```bash
./venv/bin/python manage_credentials.py admin ./credentials.local.json
```

Set `AUTH_CREDENTIALS_FILE` to that file's absolute path. The utility prompts
twice and stores only a Werkzeug password hash with mode `0600`.

## New users

An authenticated Admin creates a user from the UI with ID, username, password,
full name, and role. The backend hashes the password before invoking
`CreateUser`; the chaincode stores the hash in the `userCredentials` private-data collection
so `GetAllUsers` and `GetUser` never expose it.

Redeploy/upgrade the chaincode before using the updated backend because
`CreateUser` now accepts the password hash argument and login uses
`GetPasswordHash` plus `GetUserByUsername`.

> **PDC rollout gate:** `USER_CREDENTIAL_PDC_ENABLED` must remain `false` until the committed Fabric definition actually contains `collections_config.json`. The current ChainLaunch definition API commits `Collections: nil`; enabling the flag earlier would break credential reads. Identity migration can be deployed independently, then PDC can be enabled in a later lifecycle upgrade that proves collection bytes on-chain.

## Per-user Fabric signing identities

`FABRIC_KEY_ID` is now a **query-only service identity**. For every mutation,
the backend reads `IDENTITY_REGISTRY_DB` and selects the active ChainLaunch
`key_id` belonging to the authenticated `userID`. Missing/inactive bindings,
missing actor arguments, and actor/session mismatches fail closed. The SQLite
registry contains only key IDs, organization/MSP metadata, and SHA-256
certificate fingerprints; it is forced to mode `0600` and never stores or
exports a private key.

The chaincode stores a matching public binding under
`IDENTITY_BINDING_<userID>`. Every business mutation verifies that its
`actorID` resolves to the invoker's MSPID and X.509 certificate fingerprint.
Supplying another user's actorID or signing with the service key is therefore
rejected even if an API authorization bug were introduced.

### One-time migration for the first Admin

This is deliberately a two-step operation because the certificate fingerprint
does not exist until ChainLaunch creates the key:

1. Upgrade the chaincode code on a staging copy and run the read-only
   compatibility queries first. Do not enable user mutations yet.
2. While signed in as the existing Admin, call
   `POST /api/admin/fabric-identities/<adminID>/bootstrap` with
   `organizationID`, `name`, and optional `mspID`, `description`, `dnsNames`,
   `ipAddresses`. The backend reads the organization from ChainLaunch and derives
   its MSP ID; if `mspID` is supplied it must match. It then calls exactly
   `POST /organizations/{id}/keys` with `role=client`, stores a **pending** local
   binding, and returns only public metadata.
3. Put the returned lowercase fingerprint plus Admin ID and MSP ID into the
   external-chaincode runtime variables `IDENTITY_BOOTSTRAP_USER_ID`,
   `IDENTITY_BOOTSTRAP_MSP_ID`, and
   `IDENTITY_BOOTSTRAP_CERT_FINGERPRINT`, identically on every peer.
4. After the upgraded definition is committed and running, call
   `POST /api/admin/fabric-identities/<adminID>/bootstrap/complete`. It signs
   `BootstrapAdminIdentity` with the pending Admin key. The chaincode accepts it
   once, only for an existing ledger user with role Admin and an exact allowlist
   match, then writes an immutable bootstrap-complete marker.
5. Remove the three bootstrap environment values from the next chaincode
   runtime configuration. The ledger marker remains a second barrier.
6. Provision each remaining user through
   `POST /api/admin/fabric-identities/<userID>`. The already-bound Admin signs
   `RegisterUserIdentity`; only after that ledger transaction succeeds does the
   local binding become active.

### New-user provisioning requests

Creating a user through `POST /api/users` also writes one de-duplicated pending
request to the local identity registry. The Admin **Yêu cầu** page loads these
requests from `GET /api/fabric-identity-requests`. Approving a request calls
`POST /api/fabric-identity-requests/<requestID>/approve`; the backend creates a
ChainLaunch client key in `FABRIC_IDENTITY_ORGANIZATION_ID`, registers its
certificate fingerprint on the ledger with the Admin identity, and marks the
request approved only after the binding is active. Rejecting it creates no key.

Approval is atomically claimed so concurrent Admin actions cannot create two
keys. A failed request with a pending/failed local binding retries through the
reconciliation path. If ChainLaunch returned a key ID without enough
certificate data to create a binding, retries fail closed and require operator
reconciliation instead of creating another key. Until approval succeeds,
`ENFORCE_FABRIC_IDENTITY_LOGIN=1` prevents that user from signing in.

Deleting a user first submits `DeleteUser`, which removes the current user,
credential and identity binding from Fabric world state in one transaction. Only
after that transaction commits does the backend delete the user's dedicated
ChainLaunch key through `DELETE /keys/<keyID>` and mark the local audit binding
`revoked`. Historical ledger blocks remain immutable. If ChainLaunch cleanup
fails, the removed on-ledger binding already prevents the orphan key from
signing business mutations, and the API reports that key cleanup is pending.

Do not use the normal provisioning endpoint to replace an identity. It rejects
an existing local binding. Rotation requires an explicit operator workflow
using `RotateUserIdentity`, reconciliation of both stores, and revocation or
retirement of the old ChainLaunch key only after the new binding is proven.
There is no migration bypass or service-key fallback for mutations.

### Provisioning response failures

If ChainLaunch creates a key but omits the certificate, the backend reports the
key ID and leaves it unbound. If the certificate was available but ledger
registration failed, the local row stays `failed`; after fixing the cause call
`POST /api/admin/fabric-identities/<userID>/complete`. That endpoint first
queries `GetUserIdentity` to reconcile a lost success response, then submits
`RegisterUserIdentity` only when still needed. The backend intentionally does
**not** delete a key or activate a guessed fingerprint. API responses and audit
events never include private-key material, even if an upstream response does.
