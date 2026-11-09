import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'

import { api, call, type LiveState } from './client'

export const keys = {
  me: ['me'] as const,
  groups: ['groups'] as const,
  group: (id: string) => ['group', id] as const,
  event: (id: string) => ['event', id] as const,
  questions: (id: string) => ['questions', id] as const,
  live: (id: string) => ['live', id] as const,
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => call(api.GET('/api/me')) })
}

export function useGroups() {
  return useQuery({ queryKey: keys.groups, queryFn: () => call(api.GET('/api/groups')) })
}

export function useGroup(groupId: string) {
  return useQuery({
    queryKey: keys.group(groupId),
    queryFn: () =>
      call(api.GET('/api/groups/{group_id}', { params: { path: { group_id: groupId } } })),
  })
}

export function useEvent(eventId: string) {
  return useQuery({
    queryKey: keys.event(eventId),
    queryFn: () =>
      call(api.GET('/api/events/{event_id}', { params: { path: { event_id: eventId } } })),
  })
}

export function useQuestions(eventId: string, enabled = true) {
  return useQuery({
    queryKey: keys.questions(eventId),
    enabled,
    queryFn: () =>
      call(
        api.GET('/api/events/{event_id}/questions', { params: { path: { event_id: eventId } } }),
      ),
  })
}

/** How often to poll: quicker for the host while answers are coming in. */
export function pollInterval(state: LiveState | undefined): number {
  if (!state || state.status === 'finished' || state.status === 'cancelled') return 15000
  if (state.status === 'scheduled') return 4000
  if (state.role === 'host' && state.phase === 'open') return 1500
  return 2000
}

/**
 * The game, kept fresh by polling. Each poll sends the version it has; the server answers
 * 204 when nothing changed, and the state we already have is kept.
 */
export function useLive(eventId: string) {
  const client = useQueryClient()
  return useQuery({
    queryKey: keys.live(eventId),
    queryFn: async () => {
      const previous = client.getQueryData<LiveState>(keys.live(eventId))
      const { data, error, response } = await api.GET('/api/events/{event_id}/live', {
        params: {
          path: { event_id: eventId },
          query: previous ? { since: previous.version } : {},
        },
      })
      if (response.status === 204 && previous) return previous
      return call(
        Promise.resolve({ data: data ?? undefined, error, response }),
      ) as Promise<LiveState>
    },
    refetchInterval: (query) => pollInterval(query.state.data),
    refetchIntervalInBackground: true,
  })
}

/** A mutation that refreshes the given queries afterward; or, for the game, sets the state
 * it returns straight away. */
export function useApi<TVars, TData>(
  fn: (vars: TVars) => Promise<TData>,
  options: { invalidate?: QueryKey[]; liveFor?: string } = {},
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (data) => {
      if (options.liveFor) client.setQueryData(keys.live(options.liveFor), data)
      for (const key of options.invalidate ?? []) void client.invalidateQueries({ queryKey: key })
    },
  })
}
