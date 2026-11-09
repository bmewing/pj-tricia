import { useKindeAuth } from '@kinde-oss/kinde-auth-react'
import { Button, Card, Stack, Text, Title } from '@mantine/core'
import { useQuery } from '@tanstack/react-query'
import { Navigate, useNavigate, useParams } from 'react-router'

import { api, call } from '../api/client'
import { useApi } from '../api/queries'
import { SignInCard } from '../auth/RequireAuth'
import { ErrorNote, Loading } from '../components/common'
import { formatWhen } from '../components/format'

function Watch({ token }: { token: string }) {
  const navigate = useNavigate()
  const preview = useQuery({
    queryKey: ['watch', token],
    queryFn: () => call(api.GET('/api/watch/{token}', { params: { path: { token } } })),
    retry: false,
  })
  const join = useApi(() => call(api.POST('/api/watch/{token}', { params: { path: { token } } })))
  if (preview.isLoading) return <Loading />
  if (!preview.data) return <ErrorNote error={preview.error} />
  const event = preview.data
  if (event.already_in) return <Navigate to={`/events/${event.event_id}/play`} replace />
  return (
    <Card maw={460} mx="auto" mt="xl" p="xl">
      <Stack>
        <Text c="dimmed">{event.group_name}</Text>
        <Title order={2}>{event.title}</Title>
        <Text>{formatWhen(event.starts_at)}</Text>
        <Text size="sm">
          Spectators see the questions, the answers once they're revealed, and the scores, but don't
          play.
        </Text>
        <Button
          loading={join.isPending}
          onClick={() =>
            join.mutate(undefined, { onSuccess: (e) => navigate(`/events/${e.id}/play`) })
          }
        >
          Watch the game
        </Button>
        <ErrorNote error={join.error} />
      </Stack>
    </Card>
  )
}

export function WatchPage() {
  const { token = '' } = useParams()
  const { isAuthenticated, isLoading } = useKindeAuth()
  if (isLoading) return <Loading />
  if (!isAuthenticated)
    return <SignInCard message="Sign in or create an account to watch this game." />
  return <Watch token={token} />
}
