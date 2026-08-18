import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: '12px',
      }}
    >
      <h1 style={{ fontSize: '2rem', margin: 0 }}>404</h1>
      <p style={{ color: '#6b7280', margin: 0 }}>Página no encontrada.</p>
      <Link to="/" style={{ color: '#004236' }}>
        Volver al inicio
      </Link>
    </div>
  );
}
