import {
  ActionIcon, Alert, AppShell, Burger, Button, Group, Image, Menu, NavLink, Select, Text, Tooltip,
  useComputedColorScheme, useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconActivity, IconBooks, IconChartBar, IconStack2, IconKey, IconLogin, IconLogout, IconMoon, IconSettings,
  IconShieldLock, IconSun, IconUser, IconUsers, IconHistory, IconAlertTriangle,
} from "@tabler/icons-react";
import { Link, NavLink as RouterLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useRegistries } from "../api/hooks";
import { useAuth } from "../auth/AuthProvider";
import { useCurrentRegistry } from "../registry";

function ThemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("light", { getInitialValueInEffect: true });
  const dark = computed === "dark";
  return (
    <Tooltip label={dark ? "Switch to light mode" : "Switch to dark mode"}>
      <ActionIcon variant="default" size="lg" aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
        onClick={() => setColorScheme(dark ? "light" : "dark")}>
        {dark ? <IconSun size={18} aria-hidden /> : <IconMoon size={18} aria-hidden />}
      </ActionIcon>
    </Tooltip>
  );
}

function Item({ to, label, icon }: { to: string; label: string; icon: React.ReactNode }) {
  const location = useLocation();
  const active = location.pathname === to || location.pathname.startsWith(`${to}/`);
  return <NavLink component={RouterLink} to={to} label={label} leftSection={icon} active={active} />;
}

export function Layout() {
  const [opened, { toggle, close }] = useDisclosure();
  const { me, config, isAdmin, signedIn, logout } = useAuth();
  const navigate = useNavigate();
  const registries = useRegistries();
  const { slug } = useCurrentRegistry();
  const base = slug ? `/r/${slug}` : null;

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 250, breakpoint: "sm", collapsed: { mobile: !opened } }} padding="md">
      <a href="#main" className="skip-link">Skip to content</a>
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Group wrap="nowrap">
            <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label="Toggle navigation" />
            <Link to="/" style={{ textDecoration: "none", color: "inherit" }} aria-label="OWL Server home">
              <Group gap="xs" wrap="nowrap">
                <Image src="/owl.png" alt="" h={38} w="auto" />
                <Text fw={700} size="lg" visibleFrom="xs">OWL Server</Text>
              </Group>
            </Link>
          </Group>
          <Group gap="xs" wrap="nowrap">
            {(registries.data?.length ?? 0) > 1 && slug && (
              <Select
                aria-label="Registry"
                w={170}
                size="sm"
                allowDeselect={false}
                data={registries.data!.map((r) => ({ value: r.slug, label: r.name || r.slug }))}
                value={slug}
                onChange={(v) => v && navigate(`/r/${v}/skills`)}
              />
            )}
            <ThemeToggle />
            {signedIn ? (
              <Menu position="bottom-end" withinPortal>
                <Menu.Target>
                  <Button variant="default" leftSection={<IconUser size={16} aria-hidden />} aria-label="Account menu">
                    {me?.username}
                  </Button>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Item component={Link} to="/profile" leftSection={<IconUser size={14} />}>Profile & tokens</Menu.Item>
                  <Menu.Divider />
                  <Menu.Item leftSection={<IconLogout size={14} />} onClick={() => void logout().then(() => navigate("/login"))}>Sign out</Menu.Item>
                </Menu.Dropdown>
              </Menu>
            ) : (
              !config?.open && (
                <Button component={Link} to="/login" leftSection={<IconLogin size={16} aria-hidden />}>Sign in</Button>
              )
            )}
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="sm" aria-label="Main navigation" onClick={close}>
        <Item to="/" label="Overview" icon={<IconChartBar size={18} aria-hidden />} />
        {base && (
          <>
            <Item to={`${base}/skills`} label="Skills" icon={<IconBooks size={18} aria-hidden />} />
            <Item to={`${base}/collections`} label="Collections" icon={<IconStack2 size={18} aria-hidden />} />
            <Item to={`${base}/activity`} label="Activity" icon={<IconActivity size={18} aria-hidden />} />
          </>
        )}
        <Item to="/registries" label="Registries" icon={<IconShieldLock size={18} aria-hidden />} />
        {isAdmin && (
          <>
            <Text size="xs" c="dimmed" tt="uppercase" fw={700} mt="md" mb={4} px="sm">Administration</Text>
            <Item to="/admin/users" label="Users" icon={<IconUsers size={18} aria-hidden />} />
            <Item to="/admin/tokens" label="Service tokens" icon={<IconKey size={18} aria-hidden />} />
            <Item to="/admin/audit" label="Audit log" icon={<IconHistory size={18} aria-hidden />} />
            <Item to="/settings" label="Settings" icon={<IconSettings size={18} aria-hidden />} />
          </>
        )}
      </AppShell.Navbar>

      <AppShell.Main id="main" tabIndex={-1}>
        {config?.open && (
          <Alert color="yellow" mb="md" icon={<IconAlertTriangle aria-hidden />} title="Open mode: no login required" role="status">
            Everyone who can reach this server can read and change everything.{" "}
            <Text component={Link} to="/settings" inherit td="underline">Secure this server</Text> to create the first administrator and require sign-in.
          </Alert>
        )}
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
