export interface User {
  id: number
  discord_id: string
  discord_username: string
  ecampus_id: string
  status: 'pending' | 'approved' | 'rejected'
  agreed_at: string
  created_at: string
}
