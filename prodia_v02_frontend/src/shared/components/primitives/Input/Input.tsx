import { forwardRef } from 'react';
import type { InputHTMLAttributes, ReactNode } from 'react';

import styles from './Input.module.scss';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  fullWidth?: boolean;
  leftIcon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, hint, fullWidth = false, leftIcon, id, className, ...rest }, ref) => {
    const inputId = id ?? `input-${Math.random().toString(36).slice(2, 9)}`;
    const cls = [
      styles.input,
      error ? styles.hasError : '',
      fullWidth ? styles.fullWidth : '',
      leftIcon ? styles.hasLeftIcon : '',
      className ?? '',
    ]
      .filter(Boolean)
      .join(' ');

    return (
      <div className={`${styles.wrapper} ${fullWidth ? styles.fullWidth : ''}`}>
        {label ? (
          <label htmlFor={inputId} className={styles.label}>
            {label}
          </label>
        ) : null}
        <div className={styles.inputContainer}>
          {leftIcon ? (
            <span className={styles.leftIcon} aria-hidden="true">
              {leftIcon}
            </span>
          ) : null}
          <input
            ref={ref}
            id={inputId}
            className={cls}
            aria-describedby={error ? `${inputId}-error` : hint ? `${inputId}-hint` : undefined}
            aria-invalid={error ? true : undefined}
            {...rest}
          />
        </div>
        {error ? (
          <p id={`${inputId}-error`} className={styles.errorText} role="alert">
            {error}
          </p>
        ) : null}
        {hint && !error ? (
          <p id={`${inputId}-hint`} className={styles.hintText}>
            {hint}
          </p>
        ) : null}
      </div>
    );
  },
);
Input.displayName = 'Input';
