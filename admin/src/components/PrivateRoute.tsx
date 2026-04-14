import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'

function isTokenValid(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}

export default function PrivateRoute({ children }: { children: ReactNode }) {
  const token = localStorage.getItem('token')
  if (!token || !isTokenValid(token)) {
    localStorage.removeItem('token')
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}
