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
`CreateUser`; the chaincode stores the hash under a separate `AUTH_` key so
`GetAllUsers` and `GetUser` never expose it.

Redeploy/upgrade the chaincode before using the updated backend because
`CreateUser` now accepts the password hash argument and login uses
`GetPasswordHash` plus `GetUserByUsername`.
