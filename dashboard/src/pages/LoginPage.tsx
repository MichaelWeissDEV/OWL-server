import { Alert, Button, Center, Divider, Image, Paper, PasswordInput, Stack, Text, TextInput, Title } from "@mantine/core";
import { useForm } from "@mantine/form";
import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { api, API } from "../api/client";
import { useAuth } from "../auth/AuthProvider";

export const SSO_KEY = "owl.sso.provider";

export function LoginPage() {
  const { config, signedIn, login, loading } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const form = useForm({
    initialValues: { username: "", password: "" },
    validate: {
      username: (v) => (v.trim() ? null : "Enter your username"),
      password: (v) => (v ? null : "Enter your password"),
    },
  });
  const next = params.get("next") && params.get("next")!.startsWith("/") ? params.get("next")! : "/";

  useEffect(() => {
    document.title = "Sign in - OWL Server";
  }, []);

  if (loading) return null;
  if (signedIn) return <Navigate to={next} replace />;

  const submit = form.onSubmit(async (values) => {
    setBusy(true);
    setError(null);
    try {
      await login(values.username.trim(), values.password);
      navigate(next, { replace: true });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  });

  const sso = async (id: string) => {
    setError(null);
    try {
      const { authorization_url } = await api<{ authorization_url: string }>(`${API}/auth/sso/${id}/login?json=1`, { quiet401: true });
      window.sessionStorage.setItem(SSO_KEY, id);
      window.location.assign(authorization_url);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const passwordLogin = !!config && (config.local_accounts || !!config.ldap);
  return (
    <Center mih="80vh">
      <Paper withBorder shadow="sm" p="xl" w={400} maw="100%">
        <Stack>
          <Stack align="center" gap={4}>
            <Image src="/owl.png" alt="OWL" h={72} w="auto" />
            <Title order={2}>Sign in</Title>
          </Stack>
          {config?.open && (
            <Alert color="yellow" title="No login required">
              This server is in open mode. <Link to="/">Continue</Link> or secure it in Settings.
            </Alert>
          )}
          {config?.proxy && !config.open && (
            <Alert color="blue">Your organisation may sign you in automatically through its proxy. If you see this page, that did not happen.</Alert>
          )}
          {error && <Alert color="red" role="alert">{error}</Alert>}
          {passwordLogin && (
            <form onSubmit={submit} noValidate>
              <Stack>
                <TextInput label={config?.ldap ? `Username (${config.ldap.label})` : "Username"} autoComplete="username" data-autofocus
                  {...form.getInputProps("username")} />
                <PasswordInput label="Password" autoComplete="current-password" {...form.getInputProps("password")} />
                <Button type="submit" loading={busy}>Sign in</Button>
              </Stack>
            </form>
          )}
          {passwordLogin && (config?.providers.length ?? 0) > 0 && <Divider label="or" labelPosition="center" />}
          {config?.providers.map((p) => (
            <Button key={p.id} variant="default" onClick={() => void sso(p.id)}>{p.label}</Button>
          ))}
          {config && !passwordLogin && config.providers.length === 0 && !config.proxy && !config.open && (
            <Text c="dimmed" size="sm">No sign-in method is configured. Ask the administrator.</Text>
          )}
        </Stack>
      </Paper>
    </Center>
  );
}

export function SsoCallback() {
  const { acceptToken } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = params.get("code");
    const state = params.get("state");
    const provider = window.sessionStorage.getItem(SSO_KEY) ?? (state?.startsWith("o") ? "oauth" : "oidc");
    if (!code || !state) {
      setError(params.get("error_description") ?? params.get("error") ?? "The sign-in did not complete.");
      return;
    }
    api<{ token: string }>(`${API}/auth/sso/${provider}/exchange`, { method: "POST", json: { code, state }, quiet401: true })
      .then(async (r) => {
        window.sessionStorage.removeItem(SSO_KEY);
        await acceptToken(r.token);
        navigate("/", { replace: true });
      })
      .catch((e: Error) => setError(e.message));
    // run once for the one-time code
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <Center mih="60vh">
      {error ? (
        <Stack align="center">
          <Alert color="red" title="Sign-in failed" role="alert">{error}</Alert>
          <Button component={Link} to="/login">Back to sign in</Button>
        </Stack>
      ) : (
        <Text role="status">Signing you in...</Text>
      )}
    </Center>
  );
}
