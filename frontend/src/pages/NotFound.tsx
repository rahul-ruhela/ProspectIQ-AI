import { Link } from 'react-router-dom'

export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      <p className="text-5xl font-semibold tracking-tight">404</p>
      <p className="text-muted">That page does not exist.</p>
      <Link className="btn-primary mt-2" to="/">
        Back to the dashboard
      </Link>
    </div>
  )
}
