import { Card, SimpleGrid, Stack, Text, Title } from '@mantine/core'

const RULES = [
  {
    title: 'Have fun!',
    body: "If you're not having fun, close the browser, take a deep breath, and come back in.",
  },
  {
    title: 'No Googling',
    body: "This is a game about what's in your brain, not a googling contest. I know you're sitting in front of a screen, but c'mon… please?",
  },
  {
    title: 'The final say',
    body: "The host's call is final. Facts and feelings don't come into it.",
  },
]

export function HouseRules() {
  return (
    <Card>
      <Title order={3} className="gold-title" mb="sm">
        Rules
      </Title>
      <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
        {RULES.map((rule) => (
          <Stack key={rule.title} gap={4}>
            <Text className="marker" c="marker.4" fz="lg">
              {rule.title}
            </Text>
            <Text size="sm">{rule.body}</Text>
          </Stack>
        ))}
      </SimpleGrid>
    </Card>
  )
}
