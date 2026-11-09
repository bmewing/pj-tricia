import { useKindeAuth } from '@kinde-oss/kinde-auth-react'
import { Button, Card, Center, Loader, Stack, Text, Title } from '@mantine/core'
import type { ReactNode } from 'react'
import { useLocation } from 'react-router'

import { remember } from './resume'

export function SignInCard({ message }: { message: string }) {
  const { login, register } = useKindeAuth()
  const { pathname } = useLocation()
  return (
    <Center mt="xl">
      <Card maw={420} w="100%" p="xl">
        <Stack>
          <Title order={3}>Sign in first</Title>
          <Text>{message}</Text>
          <Button
            onClick={() => {
              remember(pathname)
              void login()
            }}
          >
            Sign in
          </Button>
          <Button
            variant="light"
            onClick={() => {
              remember(pathname)
              void register()
            }}
          >
            Create an account
          </Button>
        </Stack>
      </Card>
    </Center>
  )
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { isAuthenticated, isLoading } = useKindeAuth()
  if (isLoading) {
    return (
      <Center mt="xl">
        <Loader />
      </Center>
    )
  }
  if (!isAuthenticated) {
    return <SignInCard message="Sign in to see this page." />
  }
  return children
}
