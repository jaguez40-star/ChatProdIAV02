import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { ArrowRight, Droplet, Eye, EyeOff, Lock, User } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';

import { useAuthStore } from '../../../app/store/authStore';
import { ApiError } from '../../../shared/services/apiClient';
import { Button } from '../../../shared/components/primitives/Button/Button';
import { Input } from '../../../shared/components/primitives/Input/Input';
import { Toast } from '../../../shared/components/primitives/Toast/Toast';
import { useLogin } from '../hooks/useLogin';
import { loginSchema, type LoginFormValues } from '../schemas/loginSchema';
import styles from './LoginPage.module.scss';

/**
 * Estructura y comportamiento idénticos a Robustez V02 (mismo formulario,
 * mismos primitivos, mismo flujo de sesión expirada/error). Decisión D1:
 * SIN el panel decorativo `DashboardPreview` (~500 líneas + 2 hooks de KPIs
 * de mercado que ProdIA no tiene) — el panel izquierdo queda como área de
 * marca estática. Branding propio (ProdIA, no «ROBUSTEZ · ROBUSTEZ
 * OPERATIVO V2.0»).
 */
export default function LoginPage() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const loginMutation = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [toastError, setToastError] = useState<string | null>(null);
  const [showPassword, setShowPassword] = useState(false);

  const sessionExpiredMsg = (location.state as { sessionExpired?: boolean } | null)
    ?.sessionExpired
    ? 'Tu sesión ha expirado. Inicia sesión nuevamente.'
    : null;

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: '', password: '', remember: false },
  });

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const onSubmit = (data: LoginFormValues) => {
    setToastError(null);
    // remember es UI-only: no se envía al service
    loginMutation.mutate(
      { username: data.username, password: data.password },
      {
        onSuccess: () => void navigate('/'),
        onError: (error) => {
          // Mejora sobre Robustez V02 (C2): si el error trae correlationId,
          // se muestra — convierte un ticket de soporte en 30 s de grep.
          const correlationId = error instanceof ApiError ? error.correlationId : null;
          setToastError(
            correlationId ? `${error.message} (ref. ${correlationId})` : error.message,
          );
        },
      },
    );
  };

  return (
    <div className={styles.loginPage}>
      <div className={styles.grid}>
        <div className={styles.brandPanel}>
          <div className={styles.brandContent}>
            <span className={styles.brandIcon} aria-hidden="true">
              <Droplet size={48} />
            </span>
            <h2 className={styles.brandTitle}>ProdIA V02</h2>
            <p className={styles.brandTagline}>
              Análisis de producción petrolera para Ecopetrol.
            </p>
          </div>
        </div>

        <div className={styles.formPanel}>
          <div className={styles.formContent}>
            <div className={styles.logoHeader}>
              <span className={styles.logoIcon} aria-hidden="true">
                <Droplet size={28} />
              </span>
              <div className={styles.logoText}>
                <span className={styles.logoName}>PRODIA</span>
                <span className={styles.logoSub}>ANÁLISIS DE PRODUCCIÓN · V02</span>
              </div>
            </div>

            <div className={styles.formHeader}>
              <h1 className={styles.formTitle}>Iniciar sesión</h1>
              <p className={styles.formSubtitle}>
                Ingresa con tu cuenta corporativa Ecopetrol.
              </p>
            </div>

            <form
              onSubmit={(e) => void handleSubmit(onSubmit)(e)}
              className={styles.form}
              noValidate
            >
              <Input
                label="Usuario de red *"
                placeholder="usuario.apellido"
                autoComplete="username"
                fullWidth
                hint="LDAP"
                leftIcon={<User size={16} />}
                error={errors.username?.message}
                {...register('username')}
              />

              <div className={styles.passwordWrapper}>
                <Input
                  label="Contraseña *"
                  type={showPassword ? 'text' : 'password'}
                  placeholder="Contraseña corporativa"
                  autoComplete="current-password"
                  fullWidth
                  leftIcon={<Lock size={16} />}
                  error={errors.password?.message}
                  {...register('password')}
                />
                <button
                  type="button"
                  className={styles.eyeToggle}
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>

              <div className={styles.rememberRow}>
                <label className={styles.rememberLabel}>
                  <input type="checkbox" {...register('remember')} />
                  <span>Mantener sesión iniciada</span>
                </label>
                <button type="button" className={styles.forgotLink}>
                  ¿Olvidaste tu contraseña?
                </button>
              </div>

              <Button
                type="submit"
                variant="primary"
                size="lg"
                fullWidth
                loading={loginMutation.isPending}
              >
                Iniciar sesión
                {!loginMutation.isPending && <ArrowRight size={16} aria-hidden="true" />}
              </Button>
            </form>

            <div className={styles.notice}>
              <span>¿Sin acceso?</span>
              <button type="button" className={styles.adminLink}>
                Solicítalo al administrador
              </button>
            </div>
          </div>

          <p className={styles.formFooter}>
            <span>© 2026 ECOPETROL S.A.</span>
            <span>v0.1.0</span>
          </p>
        </div>
      </div>

      {sessionExpiredMsg ? (
        <div className={styles.toastContainer}>
          <Toast message={sessionExpiredMsg} variant="warning" duration={0} onClose={() => {}} />
        </div>
      ) : null}

      {toastError ? (
        <div className={styles.toastContainer}>
          <Toast
            message={toastError}
            variant="error"
            duration={6000}
            onClose={() => setToastError(null)}
          />
        </div>
      ) : null}
    </div>
  );
}
