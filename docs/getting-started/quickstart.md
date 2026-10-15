# Quickstart

This takes about five minutes and ends with a skill pushed to your own server.

1. Start the stack ({doc}`installation`). A fresh server is **open**: no login is needed and the
   server logs a warning saying so.
2. Open the dashboard at <http://127.0.0.1:8080> (or use the API directly on port 8765).
3. Point the OWL CLI at the server and push:

   ```console
   $ owl remote add company http://127.0.0.1:8765
   $ owl push --all -r company
   $ owl search security -r company
   $ owl install secure-review -r company
   ```

4. When more people should use it, open **Settings → Secure this server** in the dashboard. That
   creates the first administrator; from then on every request needs a login or token.
   Tokens are created under **Tokens**:

   ```console
   $ export OWL_TOKEN=owl_…
   $ owl remote add company https://skills.example.com --token-env OWL_TOKEN
   ```

5. Optionally connect an identity provider ({doc}`/guide/identity`).

```{warning}
An open server gives every client that can reach it administrator rights. Keep it on `127.0.0.1` or a
trusted network until it is secured, and put TLS in front of it before exposing it ({doc}`/operations/reverse-proxy`).
```
