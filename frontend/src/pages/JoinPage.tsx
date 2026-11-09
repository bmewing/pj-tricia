import { useKindeAuth } from '@kinde-oss/kinde-auth-react'
import { Button, Card, Stack, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router'

import { api, call } from '../api/client'
import { keys, useApi } from '../api/queries'
import { SignInCard } from '../auth/RequireAuth'
import { ErrorNote, Loading } from '../components/common'

function Join({ code }: { code: string }) {
  const navigate = useNavigate()
  const preview = useQuery({
    queryKey: ['join', code],
    queryFn: () => call(api.GET('/api/join/{code}', { params: { path: { code } } })),
    retry: false,
  })
  const join = useApi(() => call(api.POST('/api/join/{code}', { params: { path: { code } } })), {
    invalidate: [keys.groups],
  })
  if (preview.isLoading) return <Loading />
  if (!preview.data) return <ErrorNote error={preview.error} />
  const group = preview.data
  if (group.already_member) return <Navigate to={`/groups/${group.group_id}`} replace />
  return (
    <Card maw={460} mx="auto" mt="xl" p="xl">
      <Stack>
        <Text c="dimmed">You're invited to join</Text>
        <Title order={2}>{group.name}</Title>
        {group.description && <Text>{group.description}</Text>}
        <Text size="sm">{group.member_count} members</Text>
        <Button
          loading={join.isPending}
          onClick={() => join.mutate(undefined, { onSuccess: (g) => navigate(`/groups/${g.id}`) })}
        >
          Join the group
        </Button>
        <ErrorNote error={join.error} />
      </Stack>
    </Card>
  )
}

export function JoinPage() {
  const { code = '' } = useParams()
  const { isAuthenticated, isLoading } = useKindeAuth()
  if (isLoading) return <Loading />
  if (!isAuthenticated)
    return <SignInCard message="Sign in or create an account to join this trivia group." />
  return <Join code={code} />
}
