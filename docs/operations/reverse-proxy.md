# TLS reverse proxy

The API speaks plain HTTP. Always terminate TLS in a reverse proxy before the server is reachable
beyond localhost.

## Caddy

```
skills.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

## nginx

```nginx
server {
    listen 443 ssl;
    server_name skills.example.com;
    # ssl_certificate / ssl_certificate_key ...
    client_max_body_size 50m;          # OWL_SERVER_MAX_BODY_MB plus overhead

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Trust forwarded headers only from proxies you control: set `FORWARDED_ALLOW_IPS` (or
`--forwarded-allow-ips`) to the proxy address, otherwise the audit log records the proxy instead of the
client.

## Authenticating proxy (Kerberos, SAML, oauth2-proxy)

A proxy can also authenticate users and pass the identity on. OWL then trusts the user headers
**only** when the request carries the shared secret header (`X-OWL-Proxy-Secret`, at least 24
characters, configured with `OWL_SERVER_PROXY_SECRET`). Make sure clients cannot reach the API
directly, and that the proxy strips these headers from incoming requests. See {doc}`/guide/identity`.
