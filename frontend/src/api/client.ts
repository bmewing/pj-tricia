import createClient from 'openapi-fetch'

import type { components, paths } from './schema'

export type Schemas = components['schemas']
export type UserRead = Schemas['UserRead']
export type GroupSummary = Schemas['GroupSummary']
export type GroupRead = Schemas['GroupRead']
export type EventRead = Schemas['EventRead']
export type EventBrief = Schemas['EventBrief']
export type QuestionRead = Schemas['QuestionRead']
export type QuestionsRead = Schemas['QuestionsRead']
export type LiveState = Schemas['LiveState']
export type ScoreRow = Schemas['ScoreRow']
export type HostAnswer = Schemas['HostAnswer']

type TokenGetter = () => Promise<string | undefined | null>

let getAccessToken: TokenGetter = async () => undefined

/** Called by the auth provider so API requests carry the signed-in user's token. */
export function setAccessTokenGetter(getter: TokenGetter) {
  getAccessToken = getter
}

// Typed client generated from the FastAPI OpenAPI schema (`npm run gen:api`). In production
// the API is a DigitalOcean function reached through VITE_API_BASE (/api/core/app); locally
// it's empty and Vite proxies /api to the dev server.
export const api = createClient<paths>({
  baseUrl: window.location.origin + (import.meta.env.VITE_API_BASE ?? ''),
})

api.use({
  async onRequest({ request }) {
    const token = await getAccessToken()
    if (token) request.headers.set('Authorization', `Bearer ${token}`)
    return request
  },
})

export class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

function detailOf(error: unknown): string | null {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = (error as { detail: unknown }).detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0] && typeof detail[0].msg === 'string') {
      return String(detail[0].msg).replace(/^Value error, /, '')
    }
  }
  return null
}

/** The data of a successful response; anything else throws an ApiError with its detail. */
export async function call<T>(
  request: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await request
  if (!response.ok) {
    throw new ApiError(
      detailOf(error) ?? `Something went wrong (${response.status})`,
      response.status,
    )
  }
  return data as T
}
