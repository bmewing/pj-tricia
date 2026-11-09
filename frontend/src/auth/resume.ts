import { useKindeAuth } from '@kinde-oss/kinde-auth-react'
import { useEffect } from 'react'
import { useNavigate } from 'react-router'

// Signing in through Kinde always returns to the home page, so a link opened while signed
// out (a group invite, a spectator link) is remembered for this tab and resumed afterward.
const KEY = 'pjtricia:return-to'

export function remember(path: string) {
  try {
    window.sessionStorage.setItem(KEY, path)
  } catch {
    // Without storage they'll just open the link again.
  }
}

export function useResumeAfterSignIn() {
  const { isAuthenticated } = useKindeAuth()
  const navigate = useNavigate()
  useEffect(() => {
    if (!isAuthenticated) return
    try {
      const path = window.sessionStorage.getItem(KEY)
      if (path) {
        window.sessionStorage.removeItem(KEY)
        navigate(path, { replace: true })
      }
    } catch {
      // Nothing remembered.
    }
  }, [isAuthenticated, navigate])
}
