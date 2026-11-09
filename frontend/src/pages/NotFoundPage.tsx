import { Anchor, Stack, Text, Title } from '@mantine/core'
import { Link } from 'react-router'

export function NotFoundPage() {
  return (
    <Stack mt="xl">
      <Title order={2}>That's not on the board</Title>
      <Text>
        This page doesn't exist.{' '}
        <Anchor component={Link} to="/">
          Back home
        </Anchor>
      </Text>
    </Stack>
  )
}
