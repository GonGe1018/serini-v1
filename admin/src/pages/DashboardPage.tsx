import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api'
import type { User } from '../types'
import '../styles/dashboard.scss'

type Tab = 'pending' | 'approved'

export default function DashboardPage() {
  const [tab, setTab] = useState<Tab>('pending')
  const [users, setUsers] = useState<User[]>([])
  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState<number | null>(null)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get<User[]>(`/users/${tab}`)
      setUsers(data)
    } catch {
      setError('유저 목록을 불러오는데 실패했습니다.')
    } finally {
      setLoading(false)
    }
  }, [tab])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  async function updateStatus(id: number, status: 'approved' | 'rejected') {
    setActionLoading(id)
    try {
      await api.patch(`/users/${id}`, { status })
      fetchUsers()
    } catch {
      setError(`상태 변경에 실패했습니다. (ID: ${id})`)
    } finally {
      setActionLoading(null)
    }
  }

  async function deleteUser(id: number) {
    if (!confirm('정말 삭제하시겠습니까?')) return
    setActionLoading(id)
    try {
      await api.delete(`/users/${id}`)
      fetchUsers()
    } catch {
      setError(`유저 삭제에 실패했습니다. (ID: ${id})`)
    } finally {
      setActionLoading(null)
    }
  }

  function logout() {
    localStorage.removeItem('token')
    navigate('/login')
  }

  return (
    <div className="dashboard">
      <header>
        <h1>🦒 세린이 어드민</h1>
        <button className="logout-btn" onClick={logout}>로그아웃</button>
      </header>

      <div className="tabs">
        <button className={tab === 'pending' ? 'active' : ''} onClick={() => setTab('pending')}>
          가입 신청
        </button>
        <button className={tab === 'approved' ? 'active' : ''} onClick={() => setTab('approved')}>
          승인된 유저
        </button>
      </div>

      {error && <p className="error-banner">{error}</p>}

      {loading ? (
        <p className="empty">불러오는 중...</p>
      ) : users.length === 0 ? (
        <p className="empty">항목이 없습니다.</p>
      ) : (
        <table className="user-table">
          <thead>
            <tr>
              <th>디스코드</th>
              <th>학번</th>
              <th>신청일</th>
              <th>액션</th>
            </tr>
          </thead>
          <tbody>
            {users.map(u => (
              <tr key={u.id}>
                <td>{u.discord_username}</td>
                <td>{u.ecampus_id}</td>
                <td>{new Date(u.created_at).toLocaleDateString('ko-KR')}</td>
                <td className="actions">
                  {tab === 'pending' && (
                    <>
                      <button className="approve-btn" disabled={actionLoading === u.id} onClick={() => updateStatus(u.id, 'approved')}>
                        {actionLoading === u.id ? '...' : '승인'}
                      </button>
                      <button className="reject-btn" disabled={actionLoading === u.id} onClick={() => updateStatus(u.id, 'rejected')}>
                        {actionLoading === u.id ? '...' : '거절'}
                      </button>
                    </>
                  )}
                  <button className="delete-btn" disabled={actionLoading === u.id} onClick={() => deleteUser(u.id)}>
                    {actionLoading === u.id ? '...' : '삭제'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
