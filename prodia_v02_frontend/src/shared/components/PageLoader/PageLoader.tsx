import { Spinner } from '../primitives/Spinner/Spinner';

export function PageLoader() {
  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
      }}
    >
      <Spinner size="lg" />
    </div>
  );
}
