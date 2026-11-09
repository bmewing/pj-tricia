import { useKindeAuth } from '@kinde-oss/kinde-auth-react'
import { Anchor, Avatar, Box, Button, Container, Group, Menu } from '@mantine/core'
import { Link, Outlet } from 'react-router'

import { useMe } from '../api/queries'
import { useResumeAfterSignIn } from '../auth/resume'

function UserMenu() {
  const { logout } = useKindeAuth()
  const { data: me } = useMe()
  return (
    <Menu position="bottom-end">
      <Menu.Target>
        <Button variant="subtle" px="xs" leftSection={<Avatar src={me?.avatar_url} size="sm" />}>
          {me?.display_name ?? '…'}
        </Button>
      </Menu.Target>
      <Menu.Dropdown>
        <Menu.Item component={Link} to="/">
          My groups
        </Menu.Item>
        <Menu.Item component={Link} to="/profile">
          Profile
        </Menu.Item>
        <Menu.Divider />
        <Menu.Item onClick={() => void logout()}>Sign out</Menu.Item>
      </Menu.Dropdown>
    </Menu>
  )
}

export function Layout() {
  const { isAuthenticated, login } = useKindeAuth()
  useResumeAfterSignIn()
  return (
    <Box pb="xl">
      <Container size="md" py="sm">
        <Group justify="space-between">
          <Anchor component={Link} to="/" underline="never" aria-label="PJ Tricia home">
            <img src="/logo.png" alt="PJ Tricia" height={48} style={{ display: 'block' }} />
          </Anchor>
          {isAuthenticated ? (
            <UserMenu />
          ) : (
            <Button variant="light" onClick={() => void login()}>
              Sign in
            </Button>
          )}
        </Group>
      </Container>
      <Container size="md">
        <Outlet />
      </Container>
    </Box>
  )
}
