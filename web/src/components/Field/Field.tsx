import { useId, type InputHTMLAttributes } from 'react';
import { cx } from '../../lib/streams';
import styles from './Field.module.css';

export interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  /** Shown under the input; marks the input invalid. */
  error?: string;
  id?: string;
  className?: string;
}

export function Field({ label, error, id, className, type = 'text', ...rest }: FieldProps) {
  const auto = useId();
  const inputId = id ?? `field-${auto}`;
  const errorId = `${inputId}-error`;
  return (
    <div className={cx(styles.field, className)}>
      <label htmlFor={inputId} className={styles.label}>
        {label}
      </label>
      <input
        {...rest}
        id={inputId}
        type={type}
        className={cx(styles.input, error && styles.invalid)}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
      />
      {error && (
        <div id={errorId} className={styles.error}>
          {error}
        </div>
      )}
    </div>
  );
}
