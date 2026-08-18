import type { HTMLAttributes, ReactNode } from 'react';

import styles from './Card.module.scss';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padding?: 'sm' | 'md' | 'lg' | 'none';
  elevation?: 'base' | 'raised' | 'modal';
}

export function Card({
  children,
  padding = 'md',
  elevation = 'base',
  className,
  ...rest
}: CardProps) {
  const cls = [styles.card, styles[padding], styles[elevation], className ?? '']
    .filter(Boolean)
    .join(' ');
  return (
    <div className={cls} {...rest}>
      {children}
    </div>
  );
}
