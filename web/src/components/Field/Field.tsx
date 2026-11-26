import { useId, type InputHTMLAttributes, type Ref } from 'react';
import { cx } from '../../lib/streams';
import styles from './Field.module.css';

export interface FieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: string;
  /** Shown under the input; marks the input invalid. */
  error?: string;
  /** One line of help under the input (12px/500 slate, as card labels), read with it. */
  hint?: string;
  id?: string;
  className?: string;
  ref?: Ref<HTMLInputElement>;
}

export function Field({ label, error, hint, id, className, type = 'text', ...rest }: FieldProps) {
  const auto = useId();
  const inputId = id ?? `field-${auto}`;
  const errorId = `${inputId}-error`;
  const hintId = `${inputId}-hint`;
  const described = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined;
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
        aria-describedby={described}
      />
      {hint && (
        <div id={hintId} className={styles.hint}>
          {hint}
        </div>
      )}
      {error && (
        <div id={errorId} className={styles.error}>
          {error}
        </div>
      )}
    </div>
  );
}
